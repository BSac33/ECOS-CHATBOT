"""
Routes pour la gestion des fichiers/attachements
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import Response, StreamingResponse
from sqlmodel import Session, select
from typing import Optional, List
from uuid import UUID
import uuid
from pathlib import Path
import mimetypes

from db import get_session
from models import Attachment, AttachmentUploadOut, AttachmentOut, ClinicalCase
from storage import storage

router = APIRouter(prefix="/attachments", tags=["attachments"])

# Configuration
MAX_FILE_SIZE = {
    "image": 10 * 1024 * 1024,      # 10 MB
    "video": 200 * 1024 * 1024,     # 200 MB
    "document": 20 * 1024 * 1024,   # 20 MB
    "audio": 50 * 1024 * 1024,      # 50 MB
    "transcript": 10 * 1024 * 1024, # 10 MB
}

ALLOWED_EXTENSIONS = {
    "image": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"},
    "video": {".mp4", ".webm", ".mov", ".avi"},
    "document": {".pdf", ".txt", ".json", ".docx"},
    "audio": {".mp3", ".wav", ".ogg", ".m4a"},
    "transcript": {".json", ".txt"}
}


def detect_file_kind(filename: str, mime_type: str) -> str:
    """Détecte le type de fichier basé sur l'extension et le MIME type"""
    ext = Path(filename).suffix.lower()
    
    if mime_type.startswith("image/"):
        return "image"
    elif mime_type.startswith("video/"):
        return "video"
    elif mime_type.startswith("audio/"):
        return "audio"
    elif ext in {".pdf", ".doc", ".docx", ".txt"}:
        return "document"
    elif ext in {".json"} and "transcript" in filename.lower():
        return "transcript"
    else:
        return "document"


def validate_file(filename: str, kind: str) -> bool:
    """Valide l'extension du fichier"""
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_EXTENSIONS.get(kind, set())


@router.post("/upload", response_model=AttachmentUploadOut)
async def upload_attachment(
    file: UploadFile = File(...),
    case_id: int = Form(...),
    display_name: str = Form(...),
    description: Optional[str] = Form(None),
    trigger_keywords: Optional[str] = Form(None),
    is_available_during_case: bool = Form(True),
    show_at_start: bool = Form(False),
    db: Session = Depends(get_session)
):
    """
    Upload un fichier et crée un Attachment en base de données.
    
    - **file**: Le fichier à uploader
    - **case_id**: ID du cas clinique associé
    - **display_name**: Nom affiché (ex: "Électrocardiogramme")
    - **description**: Description pour aider le LLM (optionnel)
    - **trigger_keywords**: Mots-clés pour détection auto (séparés par virgules)
    - **is_available_during_case**: Le fichier est-il disponible pendant l'examen ?
    """
    
    # Vérifier que le cas existe
    case = db.get(ClinicalCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    
    # Lire le fichier
    content = await file.read()
    file_size = len(content)
    
    # Déterminer le type de fichier
    mime_type = file.content_type or mimetypes.guess_type(file.filename)[0] or "application/octet-stream"
    kind = detect_file_kind(file.filename, mime_type)
    
    # Valider l'extension
    if not validate_file(file.filename, kind):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file extension for type '{kind}'. Allowed: {ALLOWED_EXTENSIONS[kind]}"
        )
    
    # Vérifier la taille
    max_size = MAX_FILE_SIZE.get(kind, 10_000_000)
    if file_size > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size for {kind}: {max_size / 1024 / 1024:.1f} MB"
        )
    
    # Générer un nom unique
    file_ext = Path(file.filename).suffix
    stored_filename = f"{uuid.uuid4()}{file_ext}"
    
    # Chemin organisé par type et case_id
    file_path = f"{kind}/{case_id}/{stored_filename}"
    
    # Sauvegarder le fichier
    try:
        file_url = await storage.save_file(content, file_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    
    # Créer l'entrée en base de données
    attachment = Attachment(
        case_id=case_id,
        filename=file.filename,
        stored_filename=stored_filename,
        display_name=display_name,
        description=description,
        kind=kind,
        mime_type=mime_type,
        size_bytes=file_size,
        file_path=file_path,
        file_url=file_url,
        is_available_during_case=is_available_during_case,
        show_at_start=show_at_start,
        trigger_keywords=trigger_keywords
    )
    
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    
    return AttachmentUploadOut(
        id=str(attachment.id),  # Sérialiser UUID en string
        filename=attachment.filename,
        file_url=attachment.file_url,
        kind=attachment.kind,
        size_bytes=attachment.size_bytes
    )


@router.get("/{attachment_id}", response_model=AttachmentOut)
async def get_attachment_info(
    attachment_id: UUID,
    db: Session = Depends(get_session)
):
    """Récupère les informations d'un attachment par son ID"""
    attachment = db.get(Attachment, attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    
    return AttachmentOut(
        id=str(attachment.id),  # Sérialiser UUID
        filename=attachment.filename,
        display_name=attachment.display_name,
        kind=attachment.kind,
        mime_type=attachment.mime_type,
        size_bytes=attachment.size_bytes,
        file_url=attachment.file_url,
        uploaded_at=attachment.uploaded_at.isoformat(),
        show_at_start=attachment.show_at_start,
    )


@router.get("/case/{case_id}", response_model=List[AttachmentOut])
async def get_case_attachments(
    case_id: int,
    available_only: bool = True,
    db: Session = Depends(get_session)
):
    """Récupère tous les attachments d'un cas clinique"""
    query = select(Attachment).where(Attachment.case_id == case_id)
    
    if available_only:
        query = query.where(Attachment.is_available_during_case == True)
    
    attachments = db.exec(query).all()
    
    return [
        AttachmentOut(
            id=str(a.id),  # Sérialiser UUID
            filename=a.filename,
            display_name=a.display_name,
            kind=a.kind,
            mime_type=a.mime_type,
            size_bytes=a.size_bytes,
            file_url=a.file_url,
            uploaded_at=a.uploaded_at.isoformat(),
            show_at_start=a.show_at_start,
        )
        for a in attachments
    ]


@router.get("/download/{attachment_id}")
async def download_attachment(
    attachment_id: UUID,
    db: Session = Depends(get_session)
):
    """Télécharge le fichier d'un attachment"""
    attachment = db.get(Attachment, attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    
    try:
        file_data = await storage.get_file(attachment.file_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found on storage")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")
    
    return Response(
        content=file_data,
        media_type=attachment.mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{attachment.filename}"'
        }
    )


@router.delete("/{attachment_id}")
async def delete_attachment(
    attachment_id: UUID,
    db: Session = Depends(get_session)
):
    """Supprime un attachment et son fichier"""
    attachment = db.get(Attachment, attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    
    # Supprimer le fichier du stockage
    try:
        await storage.delete_file(attachment.file_path)
    except Exception as e:
        # Log l'erreur mais continue la suppression de la DB
        print(f"Warning: Could not delete file {attachment.file_path}: {e}")
    
    # Supprimer l'entrée de la base de données
    db.delete(attachment)
    db.commit()
    
    return {"message": "Attachment deleted successfully"}


def find_matching_attachments(
    message: str,
    case_id: int,
    db: Session
) -> List[Attachment]:
    """
    Trouve les attachments dont les mots-clés correspondent au message de l'étudiant.
    Utilisé pour attacher automatiquement des fichiers aux réponses du LLM.
    """
    # Récupérer tous les attachments disponibles pour ce cas
    attachments = db.exec(
        select(Attachment)
        .where(Attachment.case_id == case_id)
        .where(Attachment.is_available_during_case == True)
        .where(Attachment.trigger_keywords.isnot(None))
    ).all()
    
    message_lower = message.lower()
    matched = []
    
    for attachment in attachments:
        if not attachment.trigger_keywords:
            continue
            
        keywords = [k.strip().lower() for k in attachment.trigger_keywords.split(",")]
        
        # Vérifier si un des mots-clés est présent dans le message
        if any(keyword in message_lower for keyword in keywords):
            matched.append(attachment)
    
    return matched
