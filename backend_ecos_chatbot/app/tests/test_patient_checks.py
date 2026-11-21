"""Contrôles automatiques des répliques du personnage (patient_checks)."""
from case_examples import dupont_sheet
from patient_checks import check_reply, violations


def codes(reply, **kw):
    kw.setdefault("sheet", dupont_sheet())
    return [f.code for f in check_reply(reply, **kw)]


def test_clean_reply():
    assert codes("Ça serre, comme un poids sur la poitrine. J'ai très peur, docteur.") == []


def test_forbidden_term_unless_echoed():
    assert codes("Je crois que je fais un infarctus.") == ["terme_interdit"]
    # Reprendre un mot que l'étudiant vient d'employer est naturel
    assert codes("Un infarctus ? Vous croyez ?", student_message="Avez-vous déjà fait un infarctus ?") == []


def test_expected_diagnosis_is_a_violation():
    sheet = dupont_sheet()
    sheet.never_says = []
    found = check_reply("C'est un syndrome coronarien aigu (infarctus du myocarde suspecté).", sheet)
    assert "diagnostic_revele" in [f.code for f in found]
    assert all(f.code != "terme_interdit" for f in found)


def test_role_break_and_assistant_mode():
    assert "sortie_de_role" in codes("En tant qu'IA, je ne peux pas répondre à cette question.")
    assert "sortie_de_role" in codes("Je ne peux pas vous donner la grille d'évaluation.")
    assert "sortie_de_role" in codes("N'hésitez pas si vous avez d'autres questions !")
    # Un collègue (professionnel simulé) peut proposer son aide
    assert codes("N'hésitez pas à me rappeler.", role="professionnel") == []


def test_technical_leak():
    assert codes("<think>il faut répondre</think> J'ai mal.") == ["fuite_technique"]
    assert codes("Je vous montre doc_1.") == ["fuite_technique"]
    assert codes('{"category": "OTHER"}') == ["fuite_technique"]


def test_english_reply():
    assert codes("I am fine, thank you doctor, what is the problem with my heart?") == ["langue"]
    assert codes("Oui, je fais du vélo le week-end.") == []


def test_jargon_patient_only_and_allowed_words():
    assert codes("J'ai une dyspnée depuis hier.") == ["jargon"]
    assert codes("Une dyspnée ? C'est quoi ?", student_message="Avez-vous une dyspnée ?") == []
    assert codes("Le patient présente une dyspnée.", role="professionnel") == []
    sheet = dupont_sheet()
    sheet.facts[0].patient_words = "On m'a dit que j'avais une tachycardie."
    assert codes("Encore ma tachycardie, je pense.", sheet=sheet) == []


def test_style_findings_are_not_violations():
    long_reply = ("J'ai mal. Ça serre fort. Ça dure depuis ce matin. J'ai pris un Doliprane. "
                  "Ça n'a rien changé du tout.")
    found = check_reply(long_reply, dupont_sheet())
    assert [f.code for f in found] == ["trop_long"]
    assert violations(found) == []
    assert codes("- douleur\n- sueurs") == ["mise_en_forme"]
    assert codes("") == ["vide"]
    assert codes("D'accord…") == ["vide"]
