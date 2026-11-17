"""Fiche de cas : compilation du prompt patient et vérifications."""
from case_examples import dupont_sheet
from case_sheet import CaseSheet, Fact, GridItem, blocking, check_sheet, compile_case, compile_patient_prompt


def levels(issues):
    return [(i.level, i.field) for i in issues]


def test_dupont_compiles_into_a_patient_prompt():
    prompt = compile_patient_prompt(dupont_sheet())
    assert prompt.startswith("Tu es Jean Dupont, 58 ans.")
    assert "La personne en face de toi est l'interne de garde." in prompt
    # Spontané vs seulement sur question
    spont = prompt.split("CE QUE TU DIS DE TOI-MÊME")[1].split("CE QUE TU RÉPONDS")[0]
    assert "douleur dans la poitrine depuis deux heures" in spont
    assert "étau" not in spont
    assert "Si on te pose des questions sur le type de douleur : « Ça serre, comme un étau" in prompt
    assert "Si on te pose des questions sur l'endroit où la douleur se propage" in prompt
    # Signes négatifs, ce qu'il ne dit jamais, règle anti-invention
    assert "CE QUE TU N'AS PAS" in prompt and "Si on te parle de l'essoufflement : « Non, je respire bien. »" in prompt
    assert "Tu n'emploies jamais ces mots : infarctus, syndrome coronarien, angor, SCA." in prompt
    assert "sans inventer" in prompt
    # Le libellé médical n'est jamais donné au patient, seulement ses mots
    assert "rétrosternale" not in prompt.lower()
    assert "8/10" not in prompt


def test_compile_case_fields():
    fields = compile_case(dupont_sheet())
    assert fields["title"] == "Douleur thoracique aux urgences"
    assert fields["duration_seconds"] == 360
    assert fields["total_points"] == 20
    assert fields["grid_items"][2] == {"id": "item_3", "criterion": "Caractéristiques de la douleur : type et intensité",
                                       "points": 2, "description": "Type (constrictive) = 1 ; intensité (EVA) = 1"}
    assert fields["exam_findings"][0]["id"] == "constantes"
    assert "Diagnostic attendu : Syndrome coronarien aigu" in fields["scenario_context"]
    assert "- Douleur rétrosternale" in fields["scenario_context"]   # libellés médicaux pour l'évaluateur
    assert fields["forbidden_terms"] == ["infarctus", "syndrome coronarien", "angor", "SCA"]


def test_dupont_has_no_blocking_issue():
    issues = check_sheet(dupont_sheet())
    assert blocking(issues) == []
    assert not [i for i in issues if i.level == "attention"]


def test_empty_sheet_lists_what_is_missing():
    issues = check_sheet(CaseSheet())
    errors = {f for lvl, f in levels(issues) if lvl == "erreur"}
    assert {"station.title", "station.student_instructions", "facts", "correction.grid"} <= errors
    conseils = [i.message for i in issues if i.level == "conseil"]
    assert any("allergies" in m for m in conseils) and any("signes négatifs" in m for m in conseils)


def test_role_maintenance_checks():
    sheet = dupont_sheet()
    sheet.facts.append(Fact(category="histoire", label="Douleur", patient_words="J'ai une douleur rétrosternale constrictive."))
    sheet.facts.append(Fact(category="histoire", label="Diagnostic", patient_words="Je crois que c'est un infarctus."))
    sheet.facts.append(Fact(category="histoire", label="Sans mots", patient_words=""))
    sheet.correction.grid.append(GridItem(criterion="Recherche une dissection", points=1))
    sheet.correction.grid.append(GridItem(criterion="Fait fantôme", points=1, fact_ids=["f_inexistant"]))
    sheet.facts[0].generated = True
    messages = [(i.level, i.message) for i in check_sheet(sheet)]
    assert any(l == "attention" and "Jargon" in m and "retrosternale" in m for l, m in messages)
    assert any(l == "erreur" and "« infarctus »" in m for l, m in messages)
    assert any(l == "attention" and "écrivez comment le patient le dit" in m for l, m in messages)
    assert any(l == "attention" and "« Recherche une dissection » n'est relié à aucun fait" in m for l, m in messages)
    assert any(l == "erreur" and "faits supprimés" in m for l, m in messages)
    assert any(l == "attention" and "pas encore relus" in m for l, m in messages)


def test_communication_items_do_not_need_facts():
    issues = check_sheet(dupont_sheet())
    assert not any("Présentation du médecin" in i.message for i in issues)
    assert not any("Diagnostic principal" in i.message for i in issues)


def test_sheet_roundtrip_json():
    sheet = dupont_sheet()
    again = CaseSheet.model_validate(sheet.model_dump(mode="json"))
    assert compile_patient_prompt(again) == compile_patient_prompt(sheet)


def test_title_must_not_reveal_the_diagnosis():
    sheet = dupont_sheet()
    sheet.station.title = "Douleur thoracique - Suspicion de SCA"
    issues = check_sheet(sheet)
    assert any(i.field == "station.title" and i.level == "attention" for i in issues)
