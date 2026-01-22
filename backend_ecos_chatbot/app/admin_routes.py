"""
Routes d'administration pour les enseignants/admins.
Gestion des cas cliniques, grilles d'évaluation et attachments.
"""

from tabnanny import check
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import Annotated, List, Optional
from db import get_session
from models import (
    ClinicalCase,
    ClinicalCaseCreateIn,
    ClinicalCaseUpdateIn,
    ClinicalCaseOut,
    EvaluationGrid,
    EvaluationGridCreateIn,
    EvaluationGridUpdateIn,
    EvaluationGridOut,
    Attachment,
    AttachmentOut,
    StationType,
    User,
    UserRole
)
from auth import check_authorization

router = APIRouter()

# ============= CLINICAL CASES =============

@router.get("/cases", response_model=List[ClinicalCaseOut])
def list_cases(
  # Filter by draft/published
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[User, Depends(check_authorization())],
    status: Optional[str] = None,
):
    """Liste tous les cas cliniques créés par l'utilisateur actuel"""
    
    stmt = select(ClinicalCase).where(ClinicalCase.created_by == user.id)
    if status:
        stmt = stmt.where(ClinicalCase.status == status)
    
    cases = session.exec(stmt).all()
    
    return [
        ClinicalCaseOut(
            id=case.id,
            title=case.title,
            station_type=case.station_type.value,
            student_instructions=case.student_instructions,
            scenario_context=case.scenario_context,
            patient_prompt=case.patient_prompt,
            duration_seconds=case.duration_seconds,
            status=case.status,
            created_by=case.created_by,
            has_evaluation_grid=case.evaluation is not None
        )
        for case in cases
    ]

@router.get("/cases/{case_id}", response_model=ClinicalCaseOut)
def get_case(
    case_id: int, 
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[User, Depends(check_authorization())]):
    """Récupère un cas clinique (vérifie que l'utilisateur en est le créateur)"""
    
    case = session.get(ClinicalCase, case_id)
    
    if not case:
        raise HTTPException(404, "Cas clinique introuvable")
    
    if case.created_by != user.id:
        raise HTTPException(403, "Vous n'avez pas la permission de consulter ce cas")
    
    return ClinicalCaseOut(
        id=case.id,
        title=case.title,
        station_type=case.station_type.value,
        student_instructions=case.student_instructions,
        scenario_context=case.scenario_context,
        patient_prompt=case.patient_prompt,
        duration_seconds=case.duration_seconds,
        status=case.status,
        created_by=case.created_by,
        has_evaluation_grid=case.evaluation is not None
    )


@router.post("/cases", response_model=ClinicalCaseOut)
def create_case(
    payload: ClinicalCaseCreateIn,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[User, Depends(check_authorization(UserRole.admin))]
):
    """Crée un nouveau cas clinique"""
    
    data=payload.model_dump()
    case = ClinicalCase(
        **data,
        created_by=user.id
    )
    
    session.add(case)
    session.commit()
    session.refresh(case)
    
    return ClinicalCaseOut(
        id=case.id,
        title=case.title,
        station_type=case.station_type.value,
        student_instructions=case.student_instructions,
        scenario_context=case.scenario_context,
        patient_prompt=case.patient_prompt,
        duration_seconds=case.duration_seconds,
        status=case.status,
        created_by=case.created_by,
        has_evaluation_grid=False
    )
