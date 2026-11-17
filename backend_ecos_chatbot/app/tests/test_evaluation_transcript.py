"""Transcript d'évaluation : coupures de parole du patient."""
from types import SimpleNamespace

from evaluation_routes import build_evaluation_transcript
from models import ChatRole


def msg(role, content, modality="voice", interrupted_by=None, spoken_content=None):
    return SimpleNamespace(role=ChatRole(role), content=content, modality=modality,
                           interrupted_by=interrupted_by, spoken_content=spoken_content)


def test_interrupted_replies_show_only_what_was_said():
    transcript, count = build_evaluation_transcript([
        msg("system", "Consignes", "text"),
        msg("student", "Où avez-vous mal ?"),
        msg("patient", "Ça serre dans la poitrine et ça part dans le bras.",
            interrupted_by="voice", spoken_content="Ça serre dans …"),
        msg("student", "Depuis quand ?"),
        msg("patient", "Deux heures."),
        msg("examiner", "Document affiché – ECG"),
    ])
    assert count == 1
    assert transcript.startswith("[COMMUNICATION ORALE] L'étudiant a coupé la parole au patient 1 fois")
    assert "PATIENT (coupé par l'étudiant): Ça serre dans …" in transcript
    assert "le bras" not in transcript              # jamais prononcé
    assert "PATIENT: Deux heures." in transcript
    assert "EXAMINATEUR: Document affiché – ECG" in transcript
    assert "Consignes" not in transcript


def test_voice_consultation_without_interruption_is_stated():
    transcript, count = build_evaluation_transcript([msg("student", "Bonjour"), msg("patient", "Bonjour docteur.")])
    assert count == 0
    assert transcript.startswith("[COMMUNICATION ORALE] L'étudiant n'a jamais coupé la parole au patient")


def test_text_consultation_has_no_oral_section():
    transcript, count = build_evaluation_transcript([
        msg("student", "Bonjour", "text"), msg("patient", "Bonjour docteur.", "text"), msg("student", "/end", "text")])
    assert count == 0
    assert transcript == "ÉTUDIANT: Bonjour\n\nPATIENT: Bonjour docteur."
