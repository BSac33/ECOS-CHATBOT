# patient_checks.py
"""
Contrôles automatiques d'une réplique du personnage (patient ou professionnel simulé).

Déterministes, sans LLM : ils repèrent les sorties de route visibles dans le texte
(mot interdit, jargon, sortie de rôle, fuite technique, diagnostic, langue) et les défauts
de style (trop long, mise en forme). Ils ne repèrent pas un fait médical inventé : c'est
le rôle du juge du banc d'essai (scripts/bench_patient.py).

Utilisés par le banc d'essai pour compter les écarts, et prévus pour le garde-fou de
production (contrôle de chaque réplique avant envoi).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from case_sheet import JARGON, CaseSheet, _contains_term, _norm

VIOLATION = "violation"   # sortie de route : ne doit jamais arriver
STYLE = "style"           # nuit au naturel

CODES = {
    "terme_interdit": (VIOLATION, "mot que le personnage ne dit jamais (fiche)"),
    "diagnostic_revele": (VIOLATION, "diagnostic attendu énoncé"),
    "sortie_de_role": (VIOLATION, "parle comme une IA, un assistant ou de la simulation"),
    "fuite_technique": (VIOLATION, "balise, nom d'outil ou identifiant interne"),
    "langue": (VIOLATION, "réponse qui n'est pas en français"),
    "jargon": (STYLE, "terme médical qu'un patient n'emploie pas"),
    "trop_long": (STYLE, "plus de 3 phrases ou 60 mots"),
    "mise_en_forme": (STYLE, "liste, titres ou gras"),
    "vide": (STYLE, "réponse vide (réplique de secours)"),
}


@dataclass(frozen=True)
class Finding:
    code: str
    detail: str = ""

    @property
    def severity(self) -> str:
        return CODES[self.code][0]

    @property
    def is_violation(self) -> bool:
        return self.severity == VIOLATION


# Texte normalisé : minuscules, sans accents
_ROLE_BREAK = [
    r"\ben tant qu.?(ia|intelligence artificielle|assistant|modele|programme)\b",
    r"\b(je suis|je ne suis qu.?) ?(une|un) (ia|intelligence artificielle|assistant|modele|chatbot|programme|robot)\b",
    r"\bmodele de (langage|langue)\b", r"\bintelligence artificielle\b", r"\bchat ?gpt\b", r"\bqwen\b", r"\bllm\b",
    r"\bprompt\b", r"\bmes (instructions|directives)\b", r"\b(ce|le|du) scenario\b", r"\bjeu de role\b",
    r"\bsimulation\b", r"\bje joue (le role|un patient|une patiente)\b",
    r"\bgrille (d.?evaluation|de correction|de notation)\b", r"\bl.?examinateur\b",
]
# Mode assistant (patient seulement : un collègue peut proposer son aide)
_ASSISTANT = [
    r"\bcomment (puis-je|est-ce que je peux|je peux) vous aider\b", r"\bn.?hesitez pas\b",
    r"\bje suis (la|ici) pour vous aider\b", r"\bje reste a votre disposition\b",
]
_TECHNICAL = [
    r"</?think>", r"</?tool_call>", r"<\|", r"\bafficher_document\b", r"\bresultat_examen_clinique\b",
    r"\bsignaler_hors_cadre\b", r"\bdoc_\d+\b", r"\{\s*\"",
]
_ROLE_BREAK_RE = re.compile("|".join(_ROLE_BREAK))
_ASSISTANT_RE = re.compile("|".join(_ASSISTANT))
_TECHNICAL_RE = re.compile("|".join(_TECHNICAL), re.IGNORECASE)

_EN_WORDS = {"the", "and", "you", "your", "i'm", "is", "are", "what", "with", "have", "this", "that", "not",
             "my", "it", "of", "to", "do", "feel", "pain", "doctor", "yes", "no", "don't", "i"}
_FR_WORDS = {"le", "la", "les", "et", "je", "vous", "de", "des", "un", "une", "est", "pas", "ne", "mon", "ma",
             "mes", "j'ai", "c'est", "oui", "non", "docteur", "que", "qui", "en", "du", "ca", "ça", "il", "elle"}
_SENTENCE_RE = re.compile(r"[^.!?…]+[.!?…]+|[^.!?…]+$")
_FORMAT_RE = re.compile(r"(^|\n)\s*([-*•]|\d+[.)])\s+|\*\*|(^|\n)#+\s")

FALLBACK_REPLIES = {"D'accord…"}


def _words(text: str) -> List[str]:
    return re.findall(r"[a-zàâäçéèêëîïôöùûüÿœ']+", text.lower())


def _is_english(text: str) -> bool:
    words = _words(text)
    en = sum(w in _EN_WORDS for w in words)
    fr = sum(w in _FR_WORDS for w in words)
    return en >= 3 and en > 2 * fr


def _sentences(text: str) -> List[str]:
    return [s for s in (m.group(0).strip() for m in _SENTENCE_RE.finditer(text)) if len(_words(s)) >= 2]


def _echoed(term: str, student_message: str) -> bool:
    """Le personnage peut reprendre un mot que l'étudiant vient d'employer (« Une dyspnée ? »)."""
    return bool(student_message) and _contains_term(student_message, term)


def check_reply(reply: str, sheet: Optional[CaseSheet] = None, *, student_message: str = "",
                role: str = "patient") -> List[Finding]:
    """Contrôles d'une réplique ; liste vide = rien à signaler."""
    text = (reply or "").strip()
    if not text or text in FALLBACK_REPLIES:
        return [Finding("vide")]
    norm = _norm(text)
    found: List[Finding] = []

    if sheet is not None:
        for term in (t.strip() for t in sheet.never_says):
            if term and _contains_term(text, term) and not _echoed(term, student_message):
                found.append(Finding("terme_interdit", term))
        diagnosis = sheet.correction.expected_diagnosis.strip()
        if diagnosis and _norm(diagnosis) in norm:
            found.append(Finding("diagnostic_revele", diagnosis))

    match = _ROLE_BREAK_RE.search(norm) or (role == "patient" and _ASSISTANT_RE.search(norm))
    if match:
        found.append(Finding("sortie_de_role", match.group(0)))
    match = _TECHNICAL_RE.search(text)
    if match:
        found.append(Finding("fuite_technique", match.group(0)))
    if _is_english(text):
        found.append(Finding("langue", "anglais"))

    if role == "patient":
        allowed = " ".join(f.patient_words for f in sheet.facts) if sheet is not None else ""
        for term in JARGON:
            if _contains_term(text, term) and not _echoed(term, student_message) \
                    and not (allowed and _contains_term(allowed, term)):
                found.append(Finding("jargon", term))

    n_sentences, n_words = len(_sentences(text)), len(_words(text))
    if n_sentences > 3 or n_words > 60:
        found.append(Finding("trop_long", f"{n_sentences} phrases, {n_words} mots"))
    if _FORMAT_RE.search(text):
        found.append(Finding("mise_en_forme"))
    return found


def violations(findings: List[Finding]) -> List[Finding]:
    return [f for f in findings if f.is_violation]
