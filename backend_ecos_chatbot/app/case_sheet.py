# case_sheet.py
"""
Fiche de cas structurée : l'enseignant décrit des FAITS, jamais un prompt.

La fiche est compilée en :
- prompt du patient (persona, faits à révéler spontanément / seulement sur question,
  signes négatifs, réactions, ce qu'il ne dit jamais) ;
- contexte de l'évaluateur (diagnostic et prise en charge attendus) ;
- grille d'évaluation (items + échelles d'attitude), examen clinique, consignes, voix,
  documents de la vignette.

Une station peut ne pas avoir d'interlocuteur (« station sans PS ni PSS ») : l'étudiant
expose son raisonnement à voix haute devant les examinateurs (interprétation d'ECG...).

`check_sheet` signale ce qui manque ou ce qui fragilise le maintien du rôle
(question sans réponse dans la fiche, jargon dans la bouche du patient, item de
grille impossible à obtenir...).
"""
from __future__ import annotations

import re
import unicodedata
from typing import List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


# ==================== SCHÉMA ====================

FactCategory = Literal[
    "motif", "histoire", "symptome", "signe_negatif", "antecedent",
    "traitement", "allergie", "mode_de_vie", "contexte", "autre",
]

CATEGORY_LABELS = {
    "motif": "Motif de consultation",
    "histoire": "Histoire de la maladie",
    "symptome": "Symptômes associés",
    "signe_negatif": "Signes négatifs",
    "antecedent": "Antécédents",
    "traitement": "Traitements",
    "allergie": "Allergies",
    "mode_de_vie": "Mode de vie",
    "contexte": "Contexte personnel et social",
    "autre": "Autre",
}

# Ce qu'un étudiant demande dans presque tout interrogatoire : sans réponse dans la
# fiche, le patient risque d'inventer.
ANAMNESIS_CHECKLIST = {
    "antecedent": "ses antécédents médicaux et familiaux",
    "traitement": "ses traitements habituels",
    "allergie": "ses allergies",
    "mode_de_vie": "son mode de vie (tabac, alcool, activité)",
    "contexte": "sa vie personnelle et professionnelle",
}


# Les 11 domaines de compétence des ECOS
DOMAIN_LABELS = {
    "entretien_interrogatoire": "Entretien / interrogatoire",
    "examen_clinique": "Examen clinique",
    "synthese_paraclinique": "Synthèse de résultats d'examens paracliniques",
    "strategie_diagnostique": "Stratégie diagnostique",
    "strategie_prise_en_charge": "Stratégie pertinente de la prise en charge",
    "education_prevention": "Éducation / prévention",
    "annonce_information": "Annonce / information du patient",
    "urgence_vitale": "Urgence vitale",
    "communication_interprofessionnelle": "Communication interprofessionnelle",
    "iconographie": "Iconographie",
    "procedure": "Procédure",
}
Domain = Literal[
    "entretien_interrogatoire", "examen_clinique", "synthese_paraclinique", "strategie_diagnostique",
    "strategie_prise_en_charge", "education_prevention", "annonce_information", "urgence_vitale",
    "communication_interprofessionnelle", "iconographie", "procedure",
]
# Interlocuteur de l'étudiant : patient (ou proche) standardisé, professionnel de santé simulé
# (collègue, externe, médecin d'un autre service...), ou personne (examinateurs muets)
Interlocutor = Literal["patient", "professionnel", "aucun"]

# Échelles d'attitude des ECOS nationaux (cotées de 0 à 4)
LEVEL_NAMES = ["inacceptable", "insuffisante", "suffisante", "satisfaisante", "remarquable"]
GENERIC_LEVELS = [
    "Performance inacceptable : délétère, dangereuse",
    "Performance insuffisante : en dessous des attentes",
    "Performance suffisante : tout juste aux attentes",
    "Performance satisfaisante : au-dessus des attentes sans être impressionnante",
    "Performance remarquable : impressionnante",
]
STANDARD_SCALES = {
    "ecouter": "Aptitude à écouter",
    "renseigner": "Aptitude à fournir des renseignements au patient / aux aidants",
    "structurer_interrogatoire": "Aptitude à structurer l'interrogatoire",
    "questionner": "Aptitude à questionner",
    "procedure": "Aptitude à réaliser un geste / une procédure",
    "planifier_soins": "Aptitude à planifier les soins",
    "proposer_prise_en_charge": "Aptitude à proposer une prise en charge",
    "cooperer": "Aptitude à coopérer avec les pairs",
    "synthese": "Aptitude à faire la synthèse des données",
    "structurer_examen": "Aptitude à structurer l'examen clinique",
    "mener_examen": "Aptitude à mener l'examen clinique",
    "non_verbale": "Communication non verbale",
    "communication_pairs": "Communication avec les pairs",
}
# Ce que la plateforme ne peut pas observer (regard, posture) : échelle affichée, non notée
NOT_OBSERVABLE_SCALES = {"non_verbale"}


class SourceRef(BaseModel):
    """Passage du corpus officiel ayant servi à une proposition de l'assistant."""
    label: str
    url: Optional[str] = None
    chunk_id: Optional[int] = None


class Fact(BaseModel):
    id: str = Field(default_factory=lambda: _id("f"))
    category: FactCategory = "histoire"
    label: str = ""              # formulation médicale (enseignant, évaluateur)
    patient_words: str = ""      # ce que dit le patient, avec ses mots
    disclosure: Literal["spontane", "sur_question"] = "sur_question"
    asked_about: str = ""        # thème de la question, forme neutre : « le tabac », « les allergies »
    generated: bool = False      # proposé par l'assistant, pas encore relu
    sources: List[SourceRef] = []


class Reaction(BaseModel):
    when: str = ""               # ex. « si l'étudiant le rassure »
    then: str = ""               # ex. « il se détend un peu »
    generated: bool = False


class PatientProfile(BaseModel):
    first_name: str = ""
    last_name: str = ""
    age: Optional[int] = None
    sex: Literal["femme", "homme", "autre"] = "homme"
    occupation: str = ""
    living_situation: str = ""
    personality: str = ""
    emotional_state: str = ""
    language_register: Literal["courant", "familier", "soutenu", "simple"] = "courant"
    concerns: List[str] = []                 # inquiétudes
    spontaneous_questions: List[str] = []    # questions qu'il pose de lui-même
    reactions: List[Reaction] = []


class StationDocument(BaseModel):
    """Document remis avec la vignette (ECG, imagerie...), montré dès le début de la station."""
    id: str = Field(default_factory=lambda: _id("d"))
    label: str = ""                          # ex. « Document 1 : tracé-ECG »
    attachment_id: Optional[str] = None      # pièce jointe du cas (fichier)


class StationInfo(BaseModel):
    title: str = ""
    domain: Domain = "entretien_interrogatoire"
    interlocutor: Interlocutor = "patient"
    station_type: str = "patient_interview"  # dérivé du domaine à la compilation
    duration_minutes: int = 8
    setting: str = ""                        # lieu : urgences, cabinet...
    student_role: str = ""                   # ex. « interne de garde aux urgences »
    student_instructions: str = ""
    edn_items: List[int] = []                # items R2C
    starting_situations: List[int] = []      # situations de départ
    voice_id: Optional[str] = None
    documents: List[StationDocument] = []
    source: str = ""                         # ex. « Livre ECOS cardiologie – ECOS 4 »


class ExamFindingEntry(BaseModel):
    id: str = ""
    label: str = ""
    findings: str = ""
    generated: bool = False


class GridItem(BaseModel):
    id: str = Field(default_factory=lambda: _id("g"))
    criterion: str = ""
    points: float = 1
    description: str = ""
    fact_ids: List[str] = []                 # faits qui permettent d'obtenir l'item
    generated: bool = False
    sources: List[SourceRef] = []


class AttitudeScale(BaseModel):
    """Échelle d'attitude cotée de 0 (inacceptable) à 4 (remarquable)."""
    id: str = ""                             # clé de STANDARD_SCALES ou libre
    label: str = ""
    levels: List[str] = []                   # 5 descripteurs (0 à 4) ; vide = descripteurs génériques
    observable: bool = True                  # False : non évaluable sur la plateforme (non verbal)


class KeyPoint(BaseModel):
    label: str = ""
    text: str = ""


class TeachingContent(BaseModel):
    """Montré à l'étudiant au débriefing, après la correction."""
    model_config = ConfigDict(protected_namespaces=())

    objectives: List[str] = []
    key_points: List[KeyPoint] = []
    model_script: str = ""                   # proposition de script
    comments: str = ""                       # commentaires pédagogiques


class CorrectionInfo(BaseModel):
    expected_diagnosis: str = ""
    expected_management: str = ""
    grid: List[GridItem] = []
    scales: List[AttitudeScale] = []
    global_rating: bool = True               # évaluation globale de la performance (0 à 4, non comptée)
    attitude_weight: float = 0.25            # part des échelles dans la note /20 (ECOS-N : 20 à 30 %)
    teaching: TeachingContent = TeachingContent()


class CaseSheet(BaseModel):
    schema_version: int = SCHEMA_VERSION
    station: StationInfo = StationInfo()
    patient: PatientProfile = PatientProfile()
    facts: List[Fact] = []
    never_says: List[str] = []               # diagnostic, termes que le patient n'emploie jamais
    exam_findings: List[ExamFindingEntry] = []
    correction: CorrectionInfo = CorrectionInfo()

    def fact(self, fact_id: str) -> Optional[Fact]:
        return next((f for f in self.facts if f.id == fact_id), None)


# ==================== COMPILATION ====================

REGISTER_TEXT = {
    "courant": "langage courant, phrases simples",
    "familier": "langage familier, expressions du quotidien",
    "soutenu": "langage soigné, phrases construites",
    "simple": "vocabulaire très simple, phrases courtes, tu peux mal comprendre les mots compliqués",
}


def _patient_name(p: PatientProfile) -> str:
    name = " ".join(x for x in (p.first_name.strip(), p.last_name.strip()) if x)
    if name:
        return name
    return "une patiente" if p.sex == "femme" else "un patient"


def _quote(text: str) -> str:
    text = text.strip()
    return f"« {text} »" if text and not text.startswith("«") else text


def _topic(fact: Fact) -> str:
    return (fact.asked_about or fact.label or CATEGORY_LABELS[fact.category]).strip().rstrip(".")


def compile_patient_prompt(sheet: CaseSheet) -> str:
    """Contexte du patient (inséré dans les règles générales de jeu de rôle)."""
    p, s = sheet.patient, sheet.station
    lines: List[str] = []

    identity = f"Tu es {_patient_name(p)}"
    if p.age:
        identity += f", {p.age} ans"
    lines.append(identity + ".")
    for extra in (p.occupation, p.living_situation):
        if extra.strip():
            lines.append(extra.strip().rstrip(".") + ".")
    if s.setting.strip():
        lines.append(f"Tu consultes : {s.setting.strip().rstrip('.')}.")
    if s.student_role.strip():
        lines.append(f"La personne en face de toi est {s.student_role.strip().rstrip('.')}.")

    def section(title: str, items: List[str]) -> None:
        if items:
            lines.append("")
            lines.append(title)
            lines.extend(f"- {i}" for i in items)

    section("TON CARACTÈRE ET TON ÉTAT", [x.strip() for x in (p.personality, p.emotional_state) if x.strip()]
            + [f"Ta façon de parler : {REGISTER_TEXT[p.language_register]}."])

    with_words = [f for f in sheet.facts if f.patient_words.strip()]
    section("CE QUE TU DIS DE TOI-MÊME (dès qu'on te demande ce qui t'amène)",
            [_quote(f.patient_words) for f in with_words if f.disclosure == "spontane"])

    asked = [f for f in with_words if f.disclosure == "sur_question" and f.category != "signe_negatif"]
    order = list(CATEGORY_LABELS)
    asked.sort(key=lambda f: order.index(f.category))
    section("CE QUE TU RÉPONDS SEULEMENT SI ON TE LE DEMANDE",
            [f"Si on te pose des questions sur {_topic(f)} : {_quote(f.patient_words)}" for f in asked])

    section("CE QUE TU N'AS PAS (si on te le demande, tu réponds non)",
            [f"Si on te parle de {_topic(f)} : {_quote(f.patient_words)}" for f in with_words
             if f.category == "signe_negatif" and f.disclosure == "sur_question"])

    section("TES INQUIÉTUDES (tu peux les exprimer)", [c.strip() for c in p.concerns if c.strip()])
    section("QUESTIONS QUE TU POSES TOI-MÊME", [_quote(q) for q in p.spontaneous_questions if q.strip()])
    section("TES RÉACTIONS", [f"{r.when.strip()} : {r.then.strip()}" for r in p.reactions
                             if r.when.strip() and r.then.strip()])

    never = [t.strip() for t in sheet.never_says if t.strip()]
    rules = ["Tu ne connais pas ton diagnostic et tu ne le devines pas."]
    if never:
        rules.append("Tu n'emploies jamais ces mots : " + ", ".join(never) + ".")
    rules.append("Si on te demande quelque chose qui n'est pas décrit ici, réponds simplement sans inventer "
                 "de nouvel élément médical : « je ne sais pas », « je ne crois pas », « on ne m'en a jamais parlé ».")
    section("CE QUE TU NE SAIS PAS", rules)
    return "\n".join(lines).strip()


def compile_professional_prompt(sheet: CaseSheet) -> str:
    """Rôle d'un professionnel de santé simulé (PSS) : un collègue, pas un patient."""
    p, s = sheet.patient, sheet.station
    lines: List[str] = []
    name = " ".join(x for x in (p.first_name.strip(), p.last_name.strip()) if x)
    role = p.occupation.strip().rstrip(".") or "un professionnel de santé"
    lines.append(f"Tu es {name}, {role}." if name else f"Tu es {role}.")
    if s.setting.strip():
        lines.append(f"Contexte : {s.setting.strip().rstrip('.')}.")
    if s.student_role.strip():
        lines.append(f"La personne qui s'adresse à toi est {s.student_role.strip().rstrip('.')}.")

    def section(title: str, items: List[str]) -> None:
        if items:
            lines.append("")
            lines.append(title)
            lines.extend(f"- {i}" for i in items)

    section("TON ÉTAT D'ESPRIT", [x.strip() for x in (p.personality, p.emotional_state) if x.strip()])
    with_words = [f for f in sheet.facts if f.patient_words.strip()]
    section("CE QUE TU DIS EN PREMIER", [_quote(f.patient_words) for f in with_words if f.disclosure == "spontane"])
    section("CE QUE TU SAIS (tu le dis si on te le demande)",
            [f"Si on t'interroge sur {_topic(f)} : {_quote(f.patient_words)}" for f in with_words
             if f.disclosure == "sur_question"])
    section("QUESTIONS QUE TU POSES (une à la fois, au fil de la discussion)",
            [_quote(q) for q in p.spontaneous_questions if q.strip()])
    section("TES RÉACTIONS", [f"{r.when.strip()} : {r.then.strip()}" for r in p.reactions
                             if r.when.strip() and r.then.strip()])
    never = [t.strip() for t in sheet.never_says if t.strip()]
    rules = ["C'est l'étudiant qui est évalué : tu ne fais pas son travail. Tu ne donnes ni l'interprétation des "
             "examens, ni le diagnostic, ni la conduite à tenir ; si on te demande ton avis, retourne la question.",
             "Si on te demande une information qui n'est pas décrite ici, dis simplement que tu ne l'as pas."]
    if never:
        rules.append("Tu n'emploies jamais ces mots : " + ", ".join(never) + ".")
    section("CE QUE TU NE FAIS PAS", rules)
    return "\n".join(lines).strip()


def interlocutor_label(sheet: CaseSheet) -> Optional[str]:
    """Nom affiché de l'interlocuteur (« Patient », « Externe de garde »...) ; None sans interlocuteur."""
    s, p = sheet.station, sheet.patient
    if s.interlocutor == "aucun":
        return None
    if s.interlocutor == "professionnel":
        role = p.occupation.strip().rstrip(".")
        return (role[0].upper() + role[1:]) if role else "Professionnel de santé"
    return "Patiente" if p.sex == "femme" else "Patient"


def compile_scenario_context(sheet: CaseSheet) -> str:
    """Contexte pour l'évaluateur (jamais montré au patient ni à l'étudiant)."""
    p, c, s = sheet.patient, sheet.correction, sheet.station
    if s.interlocutor == "aucun":
        parts = ["Station sans interlocuteur : l'étudiant expose son raisonnement à voix haute aux examinateurs."]
    elif s.interlocutor == "professionnel":
        parts = [f"Interlocuteur : professionnel de santé simulé ({interlocutor_label(sheet)}). "
                 "Communication entre soignants : vocabulaire médical attendu."]
    else:
        parts = [f"Patient : {_patient_name(p)}" + (f", {p.age} ans" if p.age else "")]
    if c.expected_diagnosis.strip():
        parts.append(f"Diagnostic attendu : {c.expected_diagnosis.strip()}")
    if c.expected_management.strip():
        parts.append(f"Prise en charge attendue : {c.expected_management.strip()}")
    facts = [f"- {f.label.strip()}" for f in sheet.facts if f.label.strip()]
    if facts:
        parts.append("Éléments du dossier :\n" + "\n".join(facts))
    return "\n".join(parts)


DOMAIN_STATION_TYPE = {
    "procedure": "procedure",
    "iconographie": "exam_analysis",
    "synthese_paraclinique": "exam_analysis",
    "annonce_information": "diagnosis_announcement",
}

INSTRUCTION_NO_INTERLOCUTOR = ("Sur la plateforme : station sans interlocuteur. Exposez votre raisonnement à voix "
                               "haute (ou par écrit) ; les examinateurs vous écoutent sans intervenir.")
INSTRUCTION_GESTURES = ("Sur la plateforme : décrivez à voix haute chaque geste que vous réalisez, "
                        "les examinateurs n'évaluent que ce que vous dites.")


def station_type_for(sheet: CaseSheet) -> str:
    s = sheet.station
    if s.domain in DOMAIN_STATION_TYPE:
        return DOMAIN_STATION_TYPE[s.domain]
    return "patient_interview" if s.interlocutor == "patient" else "exam_analysis"


def compile_instructions(sheet: CaseSheet) -> str:
    s = sheet.station
    text = s.student_instructions.strip()
    if not text:
        return ""
    gestures = s.domain in ("procedure", "examen_clinique", "urgence_vitale")
    if s.interlocutor == "aucun":
        return f"{text}\n\n{INSTRUCTION_NO_INTERLOCUTOR}" + (f"\n{INSTRUCTION_GESTURES}" if gestures else "")
    if gestures:
        return f"{text}\n\n{INSTRUCTION_GESTURES}"
    return text


def compile_scales(sheet: CaseSheet) -> List[dict]:
    out = []
    for sc in sheet.correction.scales:
        label = sc.label.strip() or STANDARD_SCALES.get(sc.id, "")
        if not label:
            continue
        levels = [lv.strip() for lv in sc.levels] if len(sc.levels) == 5 else list(GENERIC_LEVELS)
        out.append({"id": sc.id or _slug(label), "label": label, "levels": levels,
                    "observable": sc.observable and sc.id not in NOT_OBSERVABLE_SCALES})
    return out


def compile_grid_items(sheet: CaseSheet) -> List[dict]:
    """Format historique des grilles (evaluation_grids.items)."""
    return [
        {"id": g.id, "criterion": g.criterion.strip(), "points": g.points, "description": g.description.strip()}
        for g in sheet.correction.grid if g.criterion.strip()
    ]


def compile_case(sheet: CaseSheet) -> dict:
    """Tous les champs d'exécution d'un cas, dérivés de la fiche."""
    grid = compile_grid_items(sheet)
    interlocutor = sheet.station.interlocutor
    persona_prompt = (compile_patient_prompt(sheet) if interlocutor == "patient"
                      else compile_professional_prompt(sheet) if interlocutor == "professionnel" else None)
    return {
        "title": sheet.station.title.strip(),
        "station_type": station_type_for(sheet),
        "domain": sheet.station.domain,
        "interlocutor": interlocutor,
        "interlocutor_label": interlocutor_label(sheet),
        "duration_seconds": max(60, int(sheet.station.duration_minutes * 60)),
        "student_instructions": compile_instructions(sheet),
        "scenario_context": compile_scenario_context(sheet),
        "patient_prompt": persona_prompt,
        "exam_findings": [
            {"id": e.id or _slug(e.label), "label": e.label.strip(), "findings": e.findings.strip()}
            for e in sheet.exam_findings if e.label.strip() and e.findings.strip()
        ] or None,
        "voice_id": sheet.station.voice_id or None,
        "grid_items": grid,
        "total_points": sum(g["points"] for g in grid),
        "forbidden_terms": [t.strip() for t in sheet.never_says if t.strip()],
        "scales": compile_scales(sheet),
        "global_rating": sheet.correction.global_rating,
        "attitude_weight": sheet.correction.attitude_weight,
        "documents": [{"id": d.id, "label": d.label.strip(), "attachment_id": d.attachment_id}
                      for d in sheet.station.documents if d.attachment_id],
    }


# ==================== VÉRIFICATIONS ====================

class Issue(BaseModel):
    level: Literal["erreur", "attention", "conseil"]
    field: str
    message: str


# Termes médicaux qu'un patient n'emploie pas spontanément
# (pas les mots qu'un patient connaît pour ses propres antécédents : diabète, embolie...)
JARGON = [
    "retrosternal", "retrosternale", "constrictive", "constrictif", "dyspnee", "syncope",
    "lipothymie", "angor", "angineuse", "syndrome coronarien", "tachycardie", "bradycardie",
    "precordial", "precordiale", "irradiation", "hemoptysie", "asthenie", "orthopnee",
    "hematemese", "melena", "dysurie", "pollakiurie", "cephalee", "cephalees", "hyperthermie",
    "febrile", "paresthesie", "paresthesies", "epigastralgie", "dyslipidemie", "sca", "idm",
]

# Items de grille qui ne dépendent pas d'un fait du dossier (communication, synthèse)
_NO_FACT_NEEDED = re.compile(
    r"presente|presentation|empathi|relationnel|ecoute|politesse|reformul|synthese|"
    r"diagnosti|hypothese|examen complementaire|prescri|annonce|explique|information|conclu|rassur|"
    r"mecanisme|test|procedure|critere|contre-indication|ecg|trace|document|interpret|analys|segment|onde|rythme",
)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _norm(text)).strip("_")[:64] or _id("x")


def _contains_term(text: str, term: str) -> bool:
    return re.search(rf"\b{re.escape(_norm(term))}\b", _norm(text)) is not None


def check_sheet(sheet: CaseSheet) -> List[Issue]:
    issues: List[Issue] = []

    def add(level, field, message):
        issues.append(Issue(level=level, field=field, message=message))

    s, p, c = sheet.station, sheet.patient, sheet.correction
    if not s.title.strip():
        add("erreur", "station.title", "Donnez un titre à la station.")
    else:
        # Le titre est affiché aux étudiants avant la station
        revealing = [t for t in sheet.never_says if t.strip() and _contains_term(s.title, t)]
        if revealing:
            add("attention", "station.title", f"Le titre, visible des étudiants, révèle « {revealing[0]} » : "
                "donnez plutôt le motif ou le contexte (ex. « Douleur thoracique aux urgences »).")
    if not s.student_instructions.strip():
        add("erreur", "station.student_instructions", "Rédigez les consignes données à l'étudiant.")
    if not s.edn_items:
        add("attention", "station.edn_items", "Rattachez la station à au moins un item EDN (sert aussi à l'assistant).")
    has_patient = s.interlocutor == "patient"
    professional = s.interlocutor == "professionnel"
    interview = s.domain == "entretien_interrogatoire"
    for i, d in enumerate(s.documents):
        if not d.attachment_id:
            add("attention", f"station.documents[{i}]", f"« {d.label or 'Document'} » : ajoutez le fichier.")
    if professional and not p.occupation.strip():
        add("erreur", "patient.occupation", "Indiquez le rôle du professionnel simulé (ex. « cardiologue de garde au CHU »).")
    if s.interlocutor == "aucun" and not s.documents and s.domain in ("iconographie", "synthese_paraclinique"):
        add("conseil", "station.documents", "Ajoutez les documents à interpréter (ECG, imagerie...).")

    if has_patient:
        if p.age is None:
            add("attention", "patient.age", "Indiquez l'âge du patient.")
        if not (p.personality.strip() or p.emotional_state.strip()):
            add("conseil", "patient.personality", "Décrivez le caractère ou l'état émotionnel du patient : son jeu sera plus naturel.")
        if not sheet.facts:
            add("erreur", "facts", "Ajoutez les faits que connaît le patient.")
        if not any(f.disclosure == "spontane" or f.category == "motif" for f in sheet.facts):
            if interview:
                add("erreur", "facts", "Indiquez le motif de consultation (ce que le patient dit de lui-même).")
            elif sheet.facts:
                add("conseil", "facts", "Indiquez ce que le patient dit en premier (phrase d'accroche), s'il en a une.")

    ids = [f.id for f in sheet.facts]
    if len(ids) != len(set(ids)):
        add("erreur", "facts", "Deux faits ont le même identifiant.")

    never = [t for t in sheet.never_says if t.strip()]
    for i, f in enumerate(sheet.facts):
        where = f"facts[{i}]"
        if not f.patient_words.strip():
            add("attention", where, f"« {f.label or 'Fait sans libellé'} » : écrivez comment le patient le dit.")
            continue
        for term in never:
            if _contains_term(f.patient_words, term):
                add("erreur", where, f"Le patient dirait « {term} », qui fait partie de ce qu'il ne doit jamais dire.")
        jargon = [t for t in JARGON if _contains_term(f.patient_words, t)] if has_patient else []
        if jargon:
            add("attention", where, f"Jargon dans la bouche du patient ({', '.join(jargon)}) : reformulez avec ses mots.")

    categories = {f.category for f in sheet.facts}
    if has_patient and interview and "signe_negatif" not in categories:
        add("conseil", "facts", "Ajoutez des signes négatifs (« pas de fièvre »...) : sans eux, le patient risque d'inventer.")
    for category, question in ANAMNESIS_CHECKLIST.items():
        if has_patient and category not in categories:
            add("conseil", "facts", f"Le patient ne saura pas quoi répondre si on l'interroge sur {question}.")

    if not c.grid:
        add("erreur", "correction.grid", "Construisez la grille d'évaluation.")
    for i, g in enumerate(c.grid):
        where = f"correction.grid[{i}]"
        if not g.criterion.strip():
            add("erreur", where, "Critère sans intitulé.")
        if g.points <= 0:
            add("erreur", where, f"« {g.criterion} » : le nombre de points doit être positif.")
        missing = [fid for fid in g.fact_ids if sheet.fact(fid) is None]
        if missing:
            add("erreur", where, f"« {g.criterion} » renvoie à des faits supprimés.")
        if interview and has_patient and not g.fact_ids and g.criterion.strip() \
                and not _NO_FACT_NEEDED.search(_norm(g.criterion + " " + g.description)):
            add("attention", where, f"« {g.criterion} » n'est relié à aucun fait : l'étudiant peut-il l'obtenir en interrogeant le patient ?")
    if not c.expected_diagnosis.strip() and s.domain in ("entretien_interrogatoire", "strategie_diagnostique",
                                                        "iconographie", "synthese_paraclinique"):
        add("attention", "correction.expected_diagnosis", "Indiquez le diagnostic attendu (pour l'évaluateur).")
    for i, sc in enumerate(c.scales):
        if sc.levels and len(sc.levels) != 5:
            add("erreur", f"correction.scales[{i}]", f"« {sc.label or sc.id} » : il faut 5 niveaux (0 à 4), ou aucun.")
        if not (sc.label.strip() or sc.id in STANDARD_SCALES):
            add("erreur", f"correction.scales[{i}]", "Échelle sans intitulé.")
    if not 0 <= c.attitude_weight <= 0.5:
        add("erreur", "correction.attitude_weight", "La part des échelles d'attitude doit être comprise entre 0 et 50 %.")

    pending = sum(f.generated for f in sheet.facts) + sum(g.generated for g in c.grid) \
        + sum(e.generated for e in sheet.exam_findings) + sum(r.generated for r in p.reactions)
    if pending:
        add("attention", "sheet", f"{pending} élément(s) proposé(s) par l'assistant ne sont pas encore relus.")
    return issues


def blocking(issues: List[Issue]) -> List[Issue]:
    return [i for i in issues if i.level == "erreur"]
