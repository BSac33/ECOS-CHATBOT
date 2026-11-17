# case_publishing.py
"""
Versions figées d'un cas compilé depuis sa fiche (case_sheet.CaseSheet).

- snapshot()  : fige la fiche compilée dans une CaseVersion ("published" ou "test")
- publish()   : nouvelle version publiée + mise à jour des champs d'exécution du cas,
                de sa grille et de ses items EDN

Utilisé par les routes d'édition (authoring_routes.py) et par le seed.
Aucune vérification ici : l'appelant a déjà refusé les fiches avec des erreurs.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlmodel import Session, select

from case_sheet import CaseSheet, compile_case
from models import CaseEdnLink, CaseVersion, ClinicalCase, EDNItem, EvaluationGrid, StationType


def runtime(version: Optional[CaseVersion]) -> Optional[dict]:
    """Champs compilés d'une version (interlocuteur, échelles, documents...), depuis sa fiche figée."""
    if version is None or not version.sheet:
        return None
    return compile_case(CaseSheet.model_validate(version.sheet))


def versions(session: Session, case_id: int) -> List[CaseVersion]:
    stmt = select(CaseVersion).where(CaseVersion.case_id == case_id).order_by(CaseVersion.id.desc())
    return list(session.exec(stmt).all())


def snapshot(session: Session, case: ClinicalCase, sheet: CaseSheet, status: str, user_id: int) -> CaseVersion:
    compiled = compile_case(sheet)
    number = max((v.version for v in versions(session, case.id) if v.status == status), default=0) + 1
    version = CaseVersion(
        case_id=case.id, version=number, status=status, sheet=sheet.model_dump(mode="json"),
        title=compiled["title"] or case.title, student_instructions=compiled["student_instructions"],
        scenario_context=compiled["scenario_context"], patient_prompt=compiled["patient_prompt"] or "",
        duration_seconds=compiled["duration_seconds"], exam_findings=compiled["exam_findings"],
        grid_items=compiled["grid_items"], total_points=compiled["total_points"],
        voice_id=compiled["voice_id"], created_by=user_id,
    )
    session.add(version)
    session.flush()
    return version


def publish(session: Session, case: ClinicalCase, sheet: CaseSheet, user_id: int) -> CaseVersion:
    """Publie la fiche : les nouvelles tentatives joueront cette version (pas de commit)."""
    case.sheet = sheet.model_dump(mode="json")
    version = snapshot(session, case, sheet, "published", user_id)
    compiled = compile_case(sheet)

    # Champs d'exécution du cas = dernière version publiée (listes, CLI, anciennes routes)
    case.title = compiled["title"]
    case.station_type = StationType(compiled["station_type"])
    case.student_instructions = compiled["student_instructions"]
    case.scenario_context = compiled["scenario_context"]
    case.patient_prompt = compiled["patient_prompt"]
    case.duration_seconds = compiled["duration_seconds"]
    case.exam_findings = compiled["exam_findings"]
    case.voice_id = compiled["voice_id"]
    case.status = "published"
    session.add(case)

    total = int(round(compiled["total_points"]))
    grid = session.exec(select(EvaluationGrid).where(EvaluationGrid.case_id == case.id)).first()
    if grid is None:
        grid = EvaluationGrid(case_id=case.id, version=float(version.version), total_points=total,
                              items=compiled["grid_items"])
    else:
        grid.version = float(version.version)
        grid.total_points = total
        grid.items = compiled["grid_items"]
        grid.is_active = True
        grid.updated_at = datetime.now()
    session.add(grid)

    # Items EDN de la fiche connus de la base
    for link in session.exec(select(CaseEdnLink).where(CaseEdnLink.case_id == case.id)).all():
        session.delete(link)
    numbers = sheet.station.edn_items or [-1]
    for item in session.exec(select(EDNItem).where(EDNItem.number.in_(numbers))).all():
        session.add(CaseEdnLink(case_id=case.id, edn_id=item.id))
    session.flush()
    return version
