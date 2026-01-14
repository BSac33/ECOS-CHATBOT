"""
Routes d'administration pour les enseignants/admins.
Gestion des cas cliniques, grilles d'évaluation et attachments.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List, Optional
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
    StationType
)

router = APIRouter()

def get_current_admin_id() -> int:
    """TODO: remplacer par vraie auth admin/teacher"""
    return 43


# ============= CLINICAL CASES =============

@router.get("/cases", response_model=List[ClinicalCaseOut])
def list_cases(
    status: Optional[str] = None,  # Filter by draft/published
    session: Session = Depends(get_session)
):
    """Liste tous les cas cliniques créés par l'utilisateur actuel"""
    admin_id = get_current_admin_id()
    
    stmt = select(ClinicalCase).where(ClinicalCase.created_by == admin_id)
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
def get_case(case_id: int, session: Session = Depends(get_session)):
    """Récupère un cas clinique (vérifie que l'utilisateur en est le créateur)"""
    admin_id = get_current_admin_id()
    
    case = session.get(ClinicalCase, case_id)
    if not case:
        raise HTTPException(404, "Cas clinique introuvable")
    
    if case.created_by != admin_id:
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
    session: Session = Depends(get_session)
):
    """Crée un nouveau cas clinique (attribué au créateur)"""
    admin_id = get_current_admin_id()
    
    # Vérifier que le titre est unique
    existing = session.exec(
        select(ClinicalCase).where(ClinicalCase.title == payload.title)
    ).first()
    if existing:
        raise HTTPException(400, "Un cas avec ce titre existe déjà")
    
    # Vérifier que le station_type est valide
    try:
        station_type_enum = StationType(payload.station_type)
    except ValueError:
        raise HTTPException(400, f"Type de station invalide: {payload.station_type}")
    
    # Créer le cas
    case = ClinicalCase(
        title=payload.title,
        station_type=station_type_enum,
        student_instructions=payload.student_instructions,
        scenario_context=payload.scenario_context,
        patient_prompt=payload.patient_prompt,
        duration_seconds=payload.duration_seconds,
        status=payload.status,
        created_by=admin_id  # Attribuer le créateur
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


@router.patch("/cases/{case_id}", response_model=ClinicalCaseOut)
def update_case(
    case_id: int,
    payload: ClinicalCaseUpdateIn,
    session: Session = Depends(get_session)
):
    """Met à jour un cas clinique (seulement si créé par l'utilisateur)"""
    admin_id = get_current_admin_id()
    
    case = session.get(ClinicalCase, case_id)
    if not case:
        raise HTTPException(404, "Cas clinique introuvable")
    
    if case.created_by != admin_id:
        raise HTTPException(403, "Vous n'avez pas la permission de modifier ce cas")
    
    # Vérifier si on essaie de publier sans grille d'évaluation
    if payload.status == "published" and not case.evaluation:
        raise HTTPException(
            400,
            "Impossible de publier un cas sans grille d'évaluation. "
            "Créez d'abord une grille d'évaluation pour ce cas."
        )
    
    # Appliquer les mises à jour
    update_data = payload.model_dump(exclude_unset=True)
    
    if "station_type" in update_data:
        try:
            update_data["station_type"] = StationType(update_data["station_type"])
        except ValueError:
            raise HTTPException(400, f"Type de station invalide: {update_data['station_type']}")
    
    for key, value in update_data.items():
        setattr(case, key, value)
    
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
        has_evaluation_grid=case.evaluation is not None
    )


@router.delete("/cases/{case_id}")
def delete_case(case_id: int, session: Session = Depends(get_session)):
    """Supprime un cas clinique (seulement si créé par l'utilisateur)"""
    admin_id = get_current_admin_id()
    
    case = session.get(ClinicalCase, case_id)
    if not case:
        raise HTTPException(404, "Cas clinique introuvable")
    
    if case.created_by != admin_id:
        raise HTTPException(403, "Vous n'avez pas la permission de supprimer ce cas")
    
    session.delete(case)
    session.commit()
    
    return {"status": "ok", "message": f"Cas {case_id} supprimé"}


# ============= EVALUATION GRIDS =============

@router.get("/cases/{case_id}/evaluation-grid", response_model=EvaluationGridOut)
def get_evaluation_grid(case_id: int, session: Session = Depends(get_session)):
    """Récupère la grille d'évaluation d'un cas"""
    case = session.get(ClinicalCase, case_id)
    if not case:
        raise HTTPException(404, "Cas clinique introuvable")
    
    if not case.evaluation:
        raise HTTPException(404, "Aucune grille d'évaluation pour ce cas")
    
    grid = case.evaluation
    return EvaluationGridOut(
        id=grid.id,
        case_id=grid.case_id,
        version=grid.version,
        total_points=grid.total_points,
        is_active=grid.is_active,
        items=grid.items
    )


@router.post("/evaluation-grids", response_model=EvaluationGridOut)
def create_evaluation_grid(
    payload: EvaluationGridCreateIn,
    session: Session = Depends(get_session)
):
    """Crée une grille d'évaluation pour un cas"""
    # Vérifier que le cas existe
    case = session.get(ClinicalCase, payload.case_id)
    if not case:
        raise HTTPException(404, "Cas clinique introuvable")
    
    # Vérifier qu'il n'y a pas déjà une grille
    if case.evaluation:
        raise HTTPException(
            400,
            "Ce cas a déjà une grille d'évaluation. "
            "Utilisez PATCH pour la mettre à jour ou DELETE pour la supprimer."
        )
    
    # Créer la grille
    grid = EvaluationGrid(
        case_id=payload.case_id,
        version=payload.version,
        total_points=payload.total_points,
        is_active=True,
        items=payload.items
    )
    
    session.add(grid)
    session.commit()
    session.refresh(grid)
    
    return EvaluationGridOut(
        id=grid.id,
        case_id=grid.case_id,
        version=grid.version,
        total_points=grid.total_points,
        is_active=grid.is_active,
        items=grid.items
    )


@router.patch("/evaluation-grids/{grid_id}", response_model=EvaluationGridOut)
def update_evaluation_grid(
    grid_id: int,
    payload: EvaluationGridUpdateIn,
    session: Session = Depends(get_session)
):
    """Met à jour une grille d'évaluation"""
    grid = session.get(EvaluationGrid, grid_id)
    if not grid:
        raise HTTPException(404, "Grille d'évaluation introuvable")
    
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(grid, key, value)
    
    session.add(grid)
    session.commit()
    session.refresh(grid)
    
    return EvaluationGridOut(
        id=grid.id,
        case_id=grid.case_id,
        version=grid.version,
        total_points=grid.total_points,
        is_active=grid.is_active,
        items=grid.items
    )


@router.delete("/evaluation-grids/{grid_id}")
def delete_evaluation_grid(grid_id: int, session: Session = Depends(get_session)):
    """Supprime une grille d'évaluation"""
    grid = session.get(EvaluationGrid, grid_id)
    if not grid:
        raise HTTPException(404, "Grille d'évaluation introuvable")
    
    case_id = grid.case_id
    session.delete(grid)
    session.commit()
    
    return {
        "status": "ok",
        "message": f"Grille d'évaluation supprimée",
        "warning": f"Le cas {case_id} est maintenant en brouillon (pas de grille)"
    }


# ============= ATTACHMENTS =============

@router.get("/cases/{case_id}/attachments", response_model=List[AttachmentOut])
def list_case_attachments(case_id: int, session: Session = Depends(get_session)):
    """Liste tous les attachments d'un cas"""
    case = session.get(ClinicalCase, case_id)
    if not case:
        raise HTTPException(404, "Cas clinique introuvable")
    
    stmt = select(Attachment).where(Attachment.case_id == case_id)
    attachments = session.exec(stmt).all()
    
    return [
        AttachmentOut(
            id=str(att.id),
            filename=att.filename,
            display_name=att.display_name,
            kind=att.kind,
            mime_type=att.mime_type,
            size_bytes=att.size_bytes,
            file_url=f"/attachments/{att.id}/download",
            uploaded_at=att.uploaded_at.isoformat() if att.uploaded_at else ""
        )
        for att in attachments
    ]


@router.delete("/attachments/{attachment_id}")
def delete_attachment(attachment_id: str, session: Session = Depends(get_session)):
    """Supprime un attachment"""
    from uuid import UUID
    try:
        att_uuid = UUID(attachment_id)
    except ValueError:
        raise HTTPException(400, "ID d'attachment invalide")
    
    attachment = session.get(Attachment, att_uuid)
    if not attachment:
        raise HTTPException(404, "Attachment introuvable")
    
    # TODO: Supprimer le fichier physique du système de fichiers
    
    session.delete(attachment)
    session.commit()
    
    return {"status": "ok", "message": "Attachment supprimé"}
