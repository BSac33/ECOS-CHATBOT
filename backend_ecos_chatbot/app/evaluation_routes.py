"""
Routes pour l'évaluation des tentatives ECOS.

L'évaluateur ne parle JAMAIS avec l'étudiant pendant l'examen.
L'évaluation se fait après la fin de la station en analysant le transcript complet.
"""

from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from uuid import UUID
from datetime import datetime
from db import get_session
from models import (
    CaseVersion,
    ClinicalCase, 
    Attempts, 
    Message, 
    EvaluationGrid,
    EvaluationOut,
    EvaluationResult,
    EvaluationItemResult,
    StationType
)
import case_publishing
from ai_chat_utils import evaluate_attempt_with_llm
from scoring import score_evaluation
from auth import check_authorization
from models import UserRole, User


router = APIRouter()

INTERRUPTION_LABEL = "coupé par l'étudiant"


def _spoken_text(msg) -> str:
    return msg.spoken_content if msg.interrupted_by and msg.spoken_content is not None else msg.content


NO_INTERLOCUTOR_HEADER = ("[STATION SANS INTERLOCUTEUR] L'étudiant expose son raisonnement à voix haute "
                          "devant les examinateurs, qui n'interviennent pas.")


def build_evaluation_transcript(messages: list, no_interlocutor: bool = False,
                                professional: Optional[str] = None) -> tuple[str, int]:
    """Transcript soumis à l'évaluateur, et nombre de fois où l'étudiant a coupé la
    parole au patient. Une réplique coupée n'y figure que pour ce qui a été prononcé."""
    parts = []
    interruptions = 0
    spoken_mode = any(getattr(m, "modality", "text") == "voice" for m in messages)
    for msg in messages:
        # Filtrer les commandes CLI (/end, /finalize, etc.)
        if msg.content.startswith('/'):
            continue
        role = msg.role.value
        if role == "student":
            parts.append(f"ÉTUDIANT: {msg.content}")
        elif role == "patient" and professional:
            # Professionnel de santé simulé : même canal que le patient, autre rôle
            parts.append(f"PROFESSIONNEL DE SANTÉ ({professional}): {_spoken_text(msg)}")
        elif role == "patient":
            if msg.interrupted_by:
                interruptions += 1
                spoken = msg.spoken_content if msg.spoken_content is not None else msg.content
                parts.append(f"PATIENT ({INTERRUPTION_LABEL}): {spoken}")
            else:
                parts.append(f"PATIENT: {msg.content}")
        elif role == "examiner":
            # Résultats d'examen clinique / documents montrés à l'étudiant
            parts.append(f"EXAMINATEUR: {msg.content}")
        # On ignore les messages system
    transcript = "\n\n".join(parts)
    if no_interlocutor:
        return f"{NO_INTERLOCUTOR_HEADER}\n\n{transcript}", 0
    if spoken_mode:
        header = (f"[COMMUNICATION ORALE] L'étudiant a coupé la parole au patient {interruptions} fois"
                  if interruptions else
                  "[COMMUNICATION ORALE] L'étudiant n'a jamais coupé la parole au patient")
        transcript = f"{header}\n\n{transcript}"
    return transcript, interruptions


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
    
    # Vérifier si une évaluation existe déjà pour cette tentative
    existing_eval_stmt = select(EvaluationResult).where(
        EvaluationResult.attempt_id == attempt_id
    )
    existing_eval = session.exec(existing_eval_stmt).first()
    
    if existing_eval:
        # Retourner l'évaluation existante directement sans recalcul
        return existing_eval.evaluation_data
    
    # Récupérer le cas clinique
    case = session.get(ClinicalCase, attempt.case_id)
    if not case:
        raise HTTPException(500, "Cas clinique introuvable (erreur d'intégrité)")
    
    # Grille et contexte : ceux de la version du cas qui a été jouée (une
    # republication ne change pas la correction d'une tentative passée)
    version = session.get(CaseVersion, attempt.case_version_id) if attempt.case_version_id else None
    info = case_publishing.runtime(version) or {}
    if version is not None:
        grid_structure = {"items": version.grid_items, "version": float(version.version),
                          "total_points": version.total_points,
                          # Échelles d'attitude et évaluation globale (format des ECOS nationaux)
                          "scales": info.get("scales") or [],
                          "global_rating": bool(info.get("global_rating")),
                          "attitude_weight": info.get("attitude_weight", 0.25)}
        title, instructions, scenario = version.title, version.student_instructions, version.scenario_context
    else:
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
        grid_structure = {"items": eval_grid.items, "version": eval_grid.version,
                          "total_points": eval_grid.total_points}
        title, instructions, scenario = case.title, case.student_instructions, case.scenario_context
    
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
    
    # Construire le transcript (commandes filtrées, coupures de parole signalées)
    transcript, _ = build_evaluation_transcript(
        messages, no_interlocutor=info.get("interlocutor") == "aucun",
        professional=info.get("interlocutor_label") if info.get("interlocutor") == "professionnel" else None)
    
    # Préparer le contexte du cas
    case_context = f"""
Titre: {title}
Type de station: {case.station_type.value}

Consignes pour l'étudiant:
{instructions}

Contexte du scénario:
{scenario}
"""
    
    # Appeler le LLM pour évaluer
    try:
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
    
    # Totaux recalculés, échelles d'attitude, note /20 (jamais les sommes du LLM)
    evaluation_result = score_evaluation(evaluation_result, grid_structure)
    points_obtained = evaluation_result["evaluation"]["score_20"]
    points_possible = 20.0
    
    # Sauvegarder le résultat de l'évaluation dans la base de données
    # Créer une nouvelle évaluation
    new_evaluation = EvaluationResult(
        attempt_id=attempt_id,
        case_id=case.id,
        user_id=user_id,
        evaluation_data=evaluation_result,
        points_obtained=points_obtained,
        points_possible=points_possible
    )
    session.add(new_evaluation)
    session.commit()
    session.refresh(new_evaluation)
    evaluation_result_id = new_evaluation.id
    
    # Créer les résultats individuels pour chaque item
    evaluation_items = evaluation_result["evaluation"].get("items", [])
    for item in evaluation_items:
        item_result = EvaluationItemResult(
            evaluation_result_id=evaluation_result_id,
            attempt_id=attempt_id,
            case_id=case.id,
            user_id=user_id,
            edn_code=item.get("edn_code", ""),
            item_name=item.get("criterion", ""),
            points_obtained=item.get("points_obtained", 0.0),
            points_possible=item.get("points_possible", 0.0),
            justification=item.get("justification", ""),
            evaluated_at=datetime.now()
        )
        session.add(item_result)
    
    session.commit()
    
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
    interruptions = []
    for msg in messages:
        if msg.role.value != "system":
            transcript.append({
                "id": msg.id,
                "role": msg.role.value,
                "content": msg.content,
                "modality": msg.modality,
                "interrupted_by": msg.interrupted_by,
                "spoken_content": msg.spoken_content,
                "timestamp": msg.created_at.isoformat() if msg.created_at else None
            })
            if msg.interrupted_by:
                interruptions.append({
                    "message_id": str(msg.id),
                    "reason": msg.interrupted_by,
                    "spoken_content": msg.spoken_content,
                    "full_reply": msg.content,
                })
    
    return {
        "attempt_id": attempt_id,
        "case_id": attempt.case_id,
        "is_completed": attempt.is_completed,
        "transcript": transcript,
        # En ECOS, on ne coupe pas la parole au patient
        "interruptions": interruptions,
    }


@router.get("/attempts/{attempt_id}/teaching")
def get_teaching(attempt_id: UUID, session: Session = Depends(get_session), user: User = Depends(check_authorization())):
    """Contenu pédagogique de la station (objectifs, éléments clés, script, commentaires).
    Seulement après la fin de la tentative : il ne doit pas aider pendant la station."""
    attempt = session.get(Attempts, attempt_id)
    if not attempt or attempt.user_id != user.id:
        raise HTTPException(404, "Tentative non trouvée")
    if not attempt.is_completed:
        raise HTTPException(400, "Disponible après la fin de la station.")
    version = session.get(CaseVersion, attempt.case_version_id) if attempt.case_version_id else None
    sheet = (version.sheet or {}) if version else {}
    teaching = (sheet.get("correction") or {}).get("teaching") or {}
    station = sheet.get("station") or {}
    return {
        "title": version.title if version else None,
        "source": station.get("source") or None,
        "objectives": teaching.get("objectives") or [],
        "key_points": teaching.get("key_points") or [],
        "model_script": teaching.get("model_script") or "",
        "comments": teaching.get("comments") or "",
    }
