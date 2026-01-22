"""
Routes pour l'évaluation des tentatives ECOS.

L'évaluateur ne parle JAMAIS avec l'étudiant pendant l'examen.
L'évaluation se fait après la fin de la station en analysant le transcript complet.
"""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from uuid import UUID
from db import get_session
from models import (
    ClinicalCase, 
    Attempts, 
    Message, 
    EvaluationGrid,
    EvaluationOut,
    StationType
)
from ai_chat_utils import evaluate_attempt_with_llm
from auth import check_authorization
from models import UserRole, User


router = APIRouter()


@router.post("/attempts/{attempt_id}/evaluate", response_model=EvaluationOut)
def evaluate_attempt(attempt_id: UUID, session: Annotated[Session, Depends(get_session)], user: Annotated[User, Depends(check_authorization(UserRole.student))]):
    """
    Évalue une tentative ECOS en analysant le transcript complet.
    
    Cette route doit être appelée APRÈS la finalisation de la tentative.
    L'évaluateur ne parle pas avec l'étudiant : il analyse silencieusement
    le transcript et remplit la grille d'évaluation.
    
    Pour les stations avec patient (patient_interview, diagnosis_announcement, mixed):
        - Analyse le transcript complet de la conversation étudiant-patient
        
    Pour les stations sans patient (exam_analysis, procedure):
        - Analyse la réponse écrite de l'étudiant
    
    Retourne un JSON structuré avec:
        - Les points attribués pour chaque item de la grille
        - La justification avec citations du transcript
        - Le score total et le feedback général
    """
    
    user_id = user.id
    
    # Vérifier que la tentative existe et appartient à l'utilisateur
    attempt = session.get(Attempts, attempt_id)
    if not attempt or attempt.user_id != user_id:
        raise HTTPException(404, "Tentative non trouvée")
    
    if not attempt.is_completed:
        raise HTTPException(
            400, 
            "La tentative doit être finalisée avant l'évaluation. "
            "Appelez d'abord POST /attempts/{attempt_id}/finalize"
        )
    
    # Récupérer le cas clinique
    case = session.get(ClinicalCase, attempt.case_id)
    if not case:
        raise HTTPException(500, "Cas clinique introuvable (erreur d'intégrité)")
    
    # Récupérer la grille d'évaluation
    eval_grid_stmt = select(EvaluationGrid).where(
        EvaluationGrid.case_id == case.id,
        EvaluationGrid.is_active == True
    )
    eval_grid = session.exec(eval_grid_stmt).first()
    
    if not eval_grid:
        raise HTTPException(
            404, 
            f"Aucune grille d'évaluation active pour le cas '{case.title}'"
        )
    
    # Récupérer tous les messages de la tentative pour construire le transcript
    messages_stmt = select(Message).where(
        Message.attempt_id == attempt_id
    ).order_by(Message.created_at)
    messages = session.exec(messages_stmt).all()
    
    print(messages)
    
    if not messages:
        raise HTTPException(
            400, 
            "Aucun message dans cette tentative. Impossible d'évaluer."
        )
    
    # Construire le transcript (en filtrant les commandes)
    transcript_parts = []
    
    for msg in messages:
        # Filtrer les commandes CLI (/end, /finalize, etc.)
        if msg.content.startswith('/'):
            continue
            
        if msg.role.value == "student":
            transcript_parts.append(f"ÉTUDIANT: {msg.content}")
        elif msg.role.value == "patient":
            transcript_parts.append(f"PATIENT: {msg.content}")
        # On ignore les messages system
    
    transcript = "\n\n".join(transcript_parts)
    
    # Préparer le contexte du cas
    case_context = f"""
Titre: {case.title}
Type de station: {case.station_type.value}

Consignes pour l'étudiant:
{case.student_instructions}

Contexte du scénario:
{case.scenario_context}
"""
    
    # Appeler le LLM pour évaluer
    try:
        # Convertir la liste d'items en un dict avec la structure attendue
        grid_structure = {
            "items": eval_grid.items,
            "version": eval_grid.version,
            "total_points": eval_grid.total_points
        }
        
        evaluation_result = evaluate_attempt_with_llm(
            transcript=transcript,
            evaluation_grid=grid_structure,
            case_context=case_context
        )
    except Exception as e:
        raise HTTPException(
            500, 
            f"Erreur lors de l'évaluation par le LLM: {str(e)}"
        )
    
    # TODO: Sauvegarder le résultat de l'évaluation dans la base de données
    # (créer une table EvaluationResults si nécessaire)
    
    return evaluation_result


@router.get("/attempts/{attempt_id}/transcript")
def get_transcript(attempt_id: UUID, session: Session = Depends(get_session), user: User = Depends(check_authorization())):
    """
    Récupère le transcript complet d'une tentative.
    Utile pour visualiser ce qui sera évalué.
    """
    user_id = user.id
    
    attempt = session.get(Attempts, attempt_id)
    if not attempt or attempt.user_id != user_id:
        raise HTTPException(404, "Tentative non trouvée")
    
    messages_stmt = select(Message).where(
        Message.attempt_id == attempt_id
    ).order_by(Message.created_at)
    messages = session.exec(messages_stmt).all()
    
    transcript = []
    for msg in messages:
        if msg.role.value != "system":
            transcript.append({
                "id": msg.id,
                "role": msg.role.value,
                "content": msg.content,
                "timestamp": msg.created_at.isoformat() if msg.created_at else None
            })
    
    return {
        "attempt_id": attempt_id,
        "case_id": attempt.case_id,
        "is_completed": attempt.is_completed,
        "transcript": transcript
    }
