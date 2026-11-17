# authoring_assistant.py
"""
Assistant de rédaction des cas (bouton « Générer » de l'atelier).

L'enseignant ne rédige pas de prompt : il choisit une action, l'assistant propose des
éléments de fiche (faits, reformulations, personnage, grille, examen clinique) appuyés
sur le corpus officiel. Rien n'entre dans la fiche sans l'accord de l'enseignant, et
ce qui y entre reste marqué « à relire » (generated=True) jusqu'à sa validation.

Chaîne d'une action :
  1. recherche des extraits utiles (corpus.search_corpus, filtrée par les items EDN)
  2. appel du LLM en sortie structurée (schéma JSON par action)
  3. filtrage déterministe : termes interdits, doublons, faits inconnus, sources non
     fournies, jargon dans la bouche du patient

LLM : tout serveur compatible OpenAI (AUTHORING_BASE_URL / AUTHORING_MODEL /
AUTHORING_API_KEY) ; par défaut le serveur vLLM du patient (VLLM_*).
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Literal, Optional

from openai import AsyncOpenAI
from pydantic import BaseModel, Field, ValidationError

import corpus
from case_sheet import (
    ANAMNESIS_CHECKLIST, CATEGORY_LABELS, CaseSheet, ExamFindingEntry, Fact, FactCategory,
    GridItem, JARGON, Reaction, SourceRef, _contains_term, _norm,
)

Task = Literal["interrogatoire", "negatifs", "langage", "personnage", "grille", "examen"]

TASK_LABELS: Dict[str, str] = {
    "interrogatoire": "Compléter l'interrogatoire",
    "negatifs": "Signes négatifs pertinents",
    "langage": "Mots du patient",
    "personnage": "Compléter le personnage",
    "grille": "Proposer la grille",
    "examen": "Proposer l'examen clinique",
}


class AssistantError(RuntimeError):
    """Le modèle de rédaction n'a pas répondu correctement."""


class AssistantInputError(ValueError):
    """La fiche ne contient pas encore ce qu'il faut pour cette action."""


# ==================== SCHÉMAS DE SORTIE DU LLM ====================

class _FactDraft(BaseModel):
    category: FactCategory
    label: str = Field(description="formulation médicale courte, pour l'enseignant")
    patient_words: str = Field(description="ce que dit le patient, avec ses mots, à la première personne")
    disclosure: Literal["spontane", "sur_question"] = "sur_question"
    asked_about: str = Field(description="thème neutre de la question, ex. « le tabac »")
    source_ids: List[int] = []


class _FactsOut(BaseModel):
    facts: List[_FactDraft]


class _Rewrite(BaseModel):
    fact_id: str
    patient_words: str


class _RewritesOut(BaseModel):
    rewrites: List[_Rewrite]


class _ReactionDraft(BaseModel):
    when: str
    then: str


class _PersonaOut(BaseModel):
    personality: str
    emotional_state: str
    concerns: List[str]
    spontaneous_questions: List[str]
    reactions: List[_ReactionDraft]


class _GridDraft(BaseModel):
    criterion: str
    points: float
    description: str
    fact_ids: List[str] = []
    source_ids: List[int] = []


class _GridOut(BaseModel):
    grid: List[_GridDraft]


class _ExamDraft(BaseModel):
    id: str = Field(description="identifiant court : constantes, cardio, pulmonaire, abdomen...")
    label: str
    findings: str


class _ExamOut(BaseModel):
    exam_findings: List[_ExamDraft]


# ==================== PROPOSITION RENVOYÉE À L'ÉDITEUR ====================

class FactRewrite(BaseModel):
    fact_id: str
    before: str
    after: str


class PersonaProposal(BaseModel):
    personality: str = ""
    emotional_state: str = ""
    concerns: List[str] = []
    spontaneous_questions: List[str] = []
    reactions: List[Reaction] = []


class Proposal(BaseModel):
    task: Task
    title: str
    facts: List[Fact] = []
    rewrites: List[FactRewrite] = []
    persona: Optional[PersonaProposal] = None
    grid: List[GridItem] = []
    exam_findings: List[ExamFindingEntry] = []
    sources: List[SourceRef] = []        # extraits fournis au LLM
    notes: List[str] = []                # éléments écartés et pourquoi


# ==================== CLIENT LLM ====================

def _config() -> Dict[str, str]:
    return {
        "base_url": os.getenv("AUTHORING_BASE_URL") or os.getenv("VLLM_BASE_URL", "http://localhost:8001/v1"),
        "model": os.getenv("AUTHORING_MODEL") or os.getenv("VLLM_MODEL", "Qwen/Qwen3-8B"),
        "api_key": os.getenv("AUTHORING_API_KEY") or os.getenv("VLLM_API_KEY", "dummy-key"),
    }


@lru_cache(maxsize=4)
def _client(base_url: str, api_key: str) -> AsyncOpenAI:
    return AsyncOpenAI(base_url=base_url, api_key=api_key,
                       timeout=float(os.getenv("AUTHORING_TIMEOUT", "120")), max_retries=1)


async def _complete(client, model: str, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
    kwargs: Dict[str, Any] = {}
    if "qwen3" in model.lower():
        kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_schema",
                             "json_schema": {"name": schema.__name__.strip("_"), "schema": schema.model_json_schema()}},
            temperature=0.4,
            max_tokens=2500,
            **kwargs,
        )
    except Exception as exc:
        raise AssistantError(f"Le modèle de rédaction ne répond pas ({exc.__class__.__name__}).") from exc
    content = response.choices[0].message.content or ""
    try:
        return schema.model_validate(json.loads(content))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise AssistantError("Réponse du modèle de rédaction illisible, réessayez.") from exc


# ==================== CONTEXTE ====================

SYSTEM = """Tu aides un enseignant de médecine à rédiger une station d'ECOS (examen clinique objectif structuré) \
pour des étudiants de 2e cycle. Un modèle jouera le patient à partir de la fiche ; tu proposes des éléments de \
cette fiche, jamais des consignes pour ce modèle.

Règles :
- Reste strictement cohérent avec la fiche existante (âge, histoire, diagnostic attendu) : ne contredis rien.
- Appuie-toi sur les extraits du référentiel fournis ; cite leurs numéros dans source_ids quand ils justifient \
une proposition. N'invente pas de recommandation médicale absente des extraits.
- Ce que dit le patient (patient_words) : première personne, mots simples d'un patient non médecin, une ou deux \
phrases courtes, aucun terme médical technique, jamais le diagnostic.
- Ne propose rien qui existe déjà dans la fiche.
- Réponds uniquement en JSON, en français."""

TASK_PROMPTS: Dict[str, str] = {
    "interrogatoire": """Propose les faits d'interrogatoire qui manquent pour que le patient puisse répondre à un \
interrogatoire complet sur ce motif : caractéristiques du symptôme, signes associés, antécédents, traitements, \
allergies, mode de vie, contexte. Catégories manquantes à couvrir en priorité : {missing}. \
Entre 4 et 10 faits ; disclosure = "sur_question" sauf ce que le patient dirait de lui-même.""",
    "negatifs": """Propose les signes négatifs pertinents (catégorie signe_negatif) : ce que le patient n'a PAS \
et qu'un étudiant doit rechercher pour éliminer les diagnostics différentiels de ce motif. \
Entre 3 et 6 faits ; patient_words = la réponse du patient quand on lui demande (« Non, pas du tout... »).""",
    "langage": """Réécris patient_words des faits listés ci-dessous pour qu'ils sonnent comme le patient décrit \
dans la fiche : mots simples, première personne, sans jargon, sans révéler le diagnostic. Garde le sens médical \
exact (même durée, même intensité, même localisation). Faits à réécrire :
{targets}""",
    "personnage": """Complète le personnage pour que le jeu soit naturel et constant : caractère, état émotionnel \
au moment de la consultation, 2 ou 3 inquiétudes, 1 à 3 questions qu'il pose lui-même à l'étudiant, 2 à 4 \
réactions (« si l'étudiant ... » -> « il ... »). Cohérent avec l'âge, la profession, la situation et le motif.""",
    "grille": """Propose une grille d'évaluation de la station (8 à 15 items, total sur 20 points environ), \
inspirée des objectifs de rang A et des notions indispensables fournis. Chaque item est observable dans le \
transcript ; relie-le (fact_ids) aux faits de la fiche que l'étudiant doit obtenir pour le valider. Inclus la \
présentation et la communication, la synthèse/diagnostic et l'examen complémentaire prioritaire si pertinent. \
N'utilise que des identifiants de faits existants.""",
    "examen": """Propose les résultats de l'examen clinique que l'examinateur communique si l'étudiant le \
demande : constantes et appareils pertinents, cohérents avec le diagnostic attendu et l'histoire. Formulation \
médicale concise (c'est l'examinateur qui parle, pas le patient). 3 à 7 entrées.""",
}

QUERIES: Dict[str, str] = {
    "interrogatoire": "interrogatoire antécédents facteurs de risque signes associés caractéristiques",
    "negatifs": "diagnostic différentiel signes de gravité éliminer",
    "grille": "interrogatoire examen complémentaire prise en charge urgence",
    "examen": "examen physique clinique constantes auscultation",
}
SOURCE_KINDS = ["cours", "notions", "points_cles", "objectif"]


def _motif(sheet: CaseSheet) -> str:
    facts = [f for f in sheet.facts if f.category == "motif"] or [f for f in sheet.facts if f.disclosure == "spontane"]
    return " ; ".join(f.label or f.patient_words for f in facts[:2]) or sheet.station.title


def _missing_categories(sheet: CaseSheet) -> List[str]:
    present = {f.category for f in sheet.facts}
    return [CATEGORY_LABELS[c] for c in ANAMNESIS_CHECKLIST if c not in present]


def _language_targets(sheet: CaseSheet) -> List[Fact]:
    targets = []
    for f in sheet.facts:
        words = f.patient_words.strip()
        if (not words or len(words) < 12 or _norm(words) == _norm(f.label)
                or any(_contains_term(words, t) for t in JARGON)):
            targets.append(f)
    return targets


def _sheet_summary(sheet: CaseSheet) -> str:
    p, s, c = sheet.patient, sheet.station, sheet.correction
    lines = [
        f"Station : {s.title} ({s.setting}) ; rôle de l'étudiant : {s.student_role}",
        f"Consignes : {s.student_instructions}",
        f"Patient : {p.first_name} {p.last_name}, {p.age or '?'} ans, {p.sex}, {p.occupation} ; {p.living_situation}",
        f"Caractère : {p.personality} ; état : {p.emotional_state} ; registre : {p.language_register}",
        f"Diagnostic attendu : {c.expected_diagnosis or 'non précisé'}",
        f"Prise en charge attendue : {c.expected_management or 'non précisée'}",
        "Faits déjà dans la fiche :",
    ]
    lines += [f"  [{f.id}] ({f.category}, {f.disclosure}) {f.label} — « {f.patient_words} »" for f in sheet.facts] or ["  (aucun)"]
    if sheet.never_says:
        lines.append("Le patient ne dit jamais : " + ", ".join(sheet.never_says))
    if c.grid:
        lines.append("Grille actuelle : " + " ; ".join(f"{g.criterion} ({g.points} pt)" for g in c.grid))
    if sheet.exam_findings:
        lines.append("Examen clinique déjà saisi : " + " ; ".join(e.label for e in sheet.exam_findings))
    return "\n".join(lines)


def retrieve(session, sheet: CaseSheet, task: str, limit: int = 8) -> List[corpus.CorpusHit]:
    if task not in QUERIES or session is None:
        return []
    items = sheet.station.edn_items
    query = f"{_motif(sheet)} {sheet.correction.expected_diagnosis} {QUERIES[task]}"
    hits = corpus.search_corpus(session, query, items=items, kinds=SOURCE_KINDS, limit=limit)
    if task == "grille" and items:
        # Objectifs de rang A : base de la grille
        seen = {h.chunk_id for h in hits}
        for o in corpus.objectives(session, items):
            if o.rank == "A" and o.id not in seen and len(hits) < limit + 8:
                hits.append(corpus.CorpusHit(chunk_id=o.id, item_number=o.item_number, chapter_title=o.chapter_title,
                                             section=o.section, rank=o.rank, kind=o.kind, text=o.text, url=o.url,
                                             source_id=o.source_id, score=0.0))
    return hits


def _excerpts(hits: List[corpus.CorpusHit]) -> str:
    if not hits:
        return "(aucun extrait du référentiel disponible)"
    out = []
    for h in hits:
        rank = f", rang {h.rank}" if h.rank else ""
        kind = "objectif" if h.kind == "objectif" else h.kind.replace("_", " ")
        out.append(f"[{h.chunk_id}] {h.label} ({kind}{rank})\n{h.text}")
    return "\n\n".join(out)


def _source_ref(hit: corpus.CorpusHit) -> SourceRef:
    return SourceRef(label=hit.label, url=hit.url, chunk_id=hit.chunk_id)


# ==================== ACTION ====================

async def assist(sheet: CaseSheet, task: str, session=None, instructions: str = "",
                 client=None, model: Optional[str] = None) -> Proposal:
    if task not in TASK_LABELS:
        raise AssistantInputError(f"Action inconnue : {task}")
    proposal = Proposal(task=task, title=TASK_LABELS[task])

    targets: List[Fact] = []
    if task == "langage":
        targets = _language_targets(sheet)
        if not targets:
            proposal.notes.append("Tous les faits sont déjà formulés avec les mots du patient.")
            return proposal
    if task in ("interrogatoire", "negatifs", "langage") and not sheet.facts and not sheet.station.title:
        raise AssistantInputError("Indiquez au moins le titre ou le motif de consultation.")
    if task == "grille" and not sheet.facts:
        raise AssistantInputError("Ajoutez d'abord les faits du cas : la grille s'appuie dessus.")

    hits = retrieve(session, sheet, task)
    by_id = {h.chunk_id: h for h in hits}
    proposal.sources = [_source_ref(h) for h in hits]

    prompt = TASK_PROMPTS[task].format(
        missing=", ".join(_missing_categories(sheet)) or "aucune",
        targets="\n".join(f"  [{f.id}] {f.label} — actuellement : « {f.patient_words} »" for f in targets),
    )
    user = f"FICHE DU CAS\n{_sheet_summary(sheet)}\n\nEXTRAITS DU RÉFÉRENTIEL\n{_excerpts(hits)}\n\nDEMANDE\n{prompt}"
    if instructions.strip():
        user += f"\n\nPrécision de l'enseignant : {instructions.strip()}"

    schema = {"interrogatoire": _FactsOut, "negatifs": _FactsOut, "langage": _RewritesOut,
              "personnage": _PersonaOut, "grille": _GridOut, "examen": _ExamOut}[task]
    if client is None:
        cfg = _config()
        client, model = _client(cfg["base_url"], cfg["api_key"]), model or cfg["model"]
    out = await _complete(client, model or _config()["model"], SYSTEM, user, schema)

    never = [t for t in sheet.never_says if t.strip()]

    def refs(ids: List[int]) -> List[SourceRef]:
        return [_source_ref(by_id[i]) for i in dict.fromkeys(ids) if i in by_id]

    def forbidden(text: str) -> Optional[str]:
        return next((t for t in never if _contains_term(text, t)), None)

    if task in ("interrogatoire", "negatifs"):
        known = {(f.category, _norm(f.asked_about or f.label)) for f in sheet.facts}
        known_labels = {_norm(f.label) for f in sheet.facts if f.label}
        for d in out.facts:
            if task == "negatifs" and d.category != "signe_negatif":
                d.category = "signe_negatif"
            term = forbidden(d.patient_words)
            if term:
                proposal.notes.append(f"Écarté « {d.label} » : le patient dirait « {term} ».")
                continue
            key = (d.category, _norm(d.asked_about or d.label))
            if key in known or _norm(d.label) in known_labels:
                proposal.notes.append(f"Écarté « {d.label} » : déjà dans la fiche.")
                continue
            known.add(key)
            known_labels.add(_norm(d.label))
            proposal.facts.append(Fact(category=d.category, label=d.label.strip(), patient_words=d.patient_words.strip(),
                                       disclosure=d.disclosure, asked_about=d.asked_about.strip(),
                                       generated=True, sources=refs(d.source_ids)))
            jargon = [t for t in JARGON if _contains_term(d.patient_words, t)]
            if jargon:
                proposal.notes.append(f"« {d.label} » : jargon à reformuler ({', '.join(jargon)}).")

    elif task == "langage":
        current = {f.id: f for f in targets}
        for r in out.rewrites:
            fact = current.get(r.fact_id)
            if fact is None or not r.patient_words.strip():
                continue
            term = forbidden(r.patient_words) or next((t for t in JARGON if _contains_term(r.patient_words, t)), None)
            if term:
                proposal.notes.append(f"Reformulation de « {fact.label} » écartée : « {term} ».")
                continue
            proposal.rewrites.append(FactRewrite(fact_id=fact.id, before=fact.patient_words, after=r.patient_words.strip()))

    elif task == "personnage":
        reactions = [Reaction(when=r.when.strip(), then=r.then.strip(), generated=True)
                     for r in out.reactions if r.when.strip() and r.then.strip()]
        texts = [out.personality, out.emotional_state, *out.concerns, *out.spontaneous_questions]
        term = next((forbidden(t) for t in texts if forbidden(t)), None)
        if term:
            proposal.notes.append(f"Personnage écarté : il mentionnerait « {term} ».")
        else:
            proposal.persona = PersonaProposal(personality=out.personality.strip(), emotional_state=out.emotional_state.strip(),
                                               concerns=[c.strip() for c in out.concerns if c.strip()],
                                               spontaneous_questions=[q.strip() for q in out.spontaneous_questions if q.strip()],
                                               reactions=reactions)

    elif task == "grille":
        fact_ids = {f.id for f in sheet.facts}
        existing = {_norm(g.criterion) for g in sheet.correction.grid}
        for d in out.grid:
            if not d.criterion.strip() or _norm(d.criterion) in existing:
                continue
            unknown = [i for i in d.fact_ids if i not in fact_ids]
            if unknown:
                proposal.notes.append(f"« {d.criterion} » : faits inconnus ignorés ({', '.join(unknown)}).")
            proposal.grid.append(GridItem(criterion=d.criterion.strip(), points=max(d.points, 0.5),
                                          description=d.description.strip(),
                                          fact_ids=[i for i in dict.fromkeys(d.fact_ids) if i in fact_ids],
                                          generated=True, sources=refs(d.source_ids)))

    elif task == "examen":
        existing = {_norm(e.id) for e in sheet.exam_findings} | {_norm(e.label) for e in sheet.exam_findings}
        for d in out.exam_findings:
            if not d.findings.strip() or _norm(d.id) in existing or _norm(d.label) in existing:
                continue
            existing.add(_norm(d.id))
            proposal.exam_findings.append(ExamFindingEntry(id=d.id.strip(), label=d.label.strip(),
                                                           findings=d.findings.strip(), generated=True))
    return proposal
