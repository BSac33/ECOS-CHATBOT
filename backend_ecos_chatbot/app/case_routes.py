"""
Routes publiques pour les cas cliniques
Accessible à tous les utilisateurs authentifiés
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from auth import get_current_user
from db import get_session
from models import User, ClinicalCase, ClinicalCasePublicOut, DisciplineItem, EDNItem

router = APIRouter()


@router.get("", response_model=List[ClinicalCasePublicOut])
async def list_published_cases(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    station_type: Optional[str] = Query(None, description="Filtrer par type de station"),
    discipline: Optional[str] = Query(None, description="Filtrer par discipline"),
) -> List[ClinicalCasePublicOut]:
    """
    Liste tous les cas cliniques publiés (status='published')
    Retourne uniquement les informations publiques (sans instructions sensibles)
    """
    # Query de base : seulement les cas publiés
    query = select(ClinicalCase).where(ClinicalCase.status == "published")
    
    # Filtres optionnels
    if station_type:
        query = query.where(ClinicalCase.station_type == station_type)
    
    cases = session.exec(query).all()
    
    # Construire la réponse avec les relations
    result = []
    for case in cases:
        # Charger les disciplines
        discipline_names = [d.name.value for d in case.disciplines]
        
        # Filtrer par discipline si spécifié
        if discipline and discipline not in discipline_names:
            continue
        
        # Charger les items EDN
        edn_codes = [edn.number for edn in case.edn_items]
        
        result.append(
            ClinicalCasePublicOut(
                id=case.id,
                title=case.title,
                station_type=case.station_type.value,
                duration_seconds=case.duration_seconds,
                status=case.status,
                disciplines=discipline_names,
                edn_codes=edn_codes,
                has_evaluation_grid=case.evaluation is not None,
            )
        )
    
    return result


@router.get("/{case_id}", response_model=ClinicalCasePublicOut)
async def get_case_public(
    case_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ClinicalCasePublicOut:
    """
    Récupère un cas clinique publié par son ID
    Retourne uniquement les informations publiques
    """
    case = session.get(ClinicalCase, case_id)
    
    if not case:
        raise HTTPException(status_code=404, detail="Cas clinique introuvable")
    
    if case.status != "published":
        raise HTTPException(
            status_code=403,
            detail="Ce cas clinique n'est pas encore publié"
        )
    
    # Charger les relations
    discipline_names = [d.name.value for d in case.disciplines]
    edn_codes = [edn.number for edn in case.edn_items]
    
    return ClinicalCasePublicOut(
        id=case.id,
        title=case.title,
        station_type=case.station_type.value,
        duration_seconds=case.duration_seconds,
        status=case.status,
        disciplines=discipline_names,
        edn_codes=edn_codes,
        has_evaluation_grid=case.evaluation is not None,
    )


@router.get("/{case_id}/instructions", response_model=dict)
async def get_case_instructions(
    case_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Récupère les instructions étudiantes pour un cas clinique
    Accessible uniquement au moment de démarrer une tentative
    """
    case = session.get(ClinicalCase, case_id)
    
    if not case:
        raise HTTPException(status_code=404, detail="Cas clinique introuvable")
    
    if case.status != "published":
        raise HTTPException(
            status_code=403,
            detail="Ce cas clinique n'est pas encore publié"
        )
    
    return {
        "case_id": case.id,
        "title": case.title,
        "student_instructions": case.student_instructions,
        "duration_seconds": case.duration_seconds,
        "station_type": case.station_type.value,
    }
