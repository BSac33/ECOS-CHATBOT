"""
Pièces jointes des stations (ECG, imagerie, documents) : envoi, consultation, suppression.

Accès :
- enseignants et administrateurs : tout lire ; envoyer ou supprimer sur leurs propres
  stations (administrateur : toutes) ;
- étudiants : télécharger SEULEMENT un document qui leur a été montré dans une de leurs
  tentatives (message de l'examinateur). Impossible de consulter les documents d'une
  station avant de la jouer.

Sécurité des fichiers : le type est déterminé par le contenu (octets magiques), pas par le
nom ni par le type déclaré ; l'extension stockée en découle ; les fichiers sont servis avec
nosniff et une politique de sécurité qui interdit tout script.
"""
from __future__ import annotations

import logging
import uuid
from typing import List, Optional
from urllib.parse import quote
from uuid import UUID

from anyio import from_thread
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlmodel import Session, select

from auth import check_authorization
from db import get_session
from models import Attachment, AttachmentOut, AttachmentUploadOut, Attempts, ClinicalCase, Message, User, UserRole
from storage import storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/attachments", tags=["attachments"])

# ==================== TYPES DE FICHIERS ====================

# Type MIME -> (famille, extension stockée, taille maximale)
SAFE_TYPES = {
    "image/png": ("image", ".png", 15 * 2**20),
    "image/jpeg": ("image", ".jpg", 15 * 2**20),
    "image/gif": ("image", ".gif", 15 * 2**20),
    "image/webp": ("image", ".webp", 15 * 2**20),
    "application/pdf": ("document", ".pdf", 20 * 2**20),
    "audio/mpeg": ("audio", ".mp3", 50 * 2**20),
    "audio/wav": ("audio", ".wav", 50 * 2**20),
    "audio/ogg": ("audio", ".ogg", 50 * 2**20),
    "video/mp4": ("video", ".mp4", 200 * 2**20),
    "video/webm": ("video", ".webm", 200 * 2**20),
}

FILE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    # Même si un fichier contenait du HTML ou du script, le navigateur ne l'exécute pas
    "Content-Security-Policy": "default-src 'none'; img-src 'self'; media-src 'self'; style-src 'unsafe-inline'; sandbox",
    "Cache-Control": "private, max-age=3600",
}


def sniff_mime(data: bytes) -> Optional[str]:
    """Type réel d'après les premiers octets, parmi les types acceptés ; None sinon."""
    head = data[:16]
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio/wav"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith(b"ID3") or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg"
    if head.startswith(b"OggS"):
        return "audio/ogg"
    if head[4:8] == b"ftyp":
        return "video/mp4"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm"
    return None


def checked_upload(data: bytes, allowed: Optional[set] = None) -> tuple[str, str, str]:
    """(type MIME réel, famille, extension) d'un fichier envoyé, ou HTTPException 415/413."""
    mime = sniff_mime(data)
    if mime is None or (allowed is not None and mime not in allowed):
        names = sorted({SAFE_TYPES[m][1].lstrip(".").upper() for m in (allowed or SAFE_TYPES)})
        raise HTTPException(415, "Format non accepté. Formats possibles : " + ", ".join(names) + ".")
    kind, ext, max_size = SAFE_TYPES[mime]
    if len(data) > max_size:
        raise HTTPException(413, f"Fichier trop volumineux ({max_size // 2**20} Mo maximum).")
    return mime, kind, ext


def file_response(data: bytes, mime: str, filename: str) -> Response:
    safe_mime = mime if mime in SAFE_TYPES else "application/octet-stream"
    disposition = "inline" if safe_mime in SAFE_TYPES else "attachment"
    ascii_name = "".join(c if c.isascii() and c not in '"\\;' else "_" for c in filename) or "fichier"
    headers = {**FILE_HEADERS,
               "Content-Disposition": f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"}
    return Response(content=data, media_type=safe_mime, headers=headers)


# ==================== DROITS ====================

teacher = check_authorization(UserRole.teacher)


def _can_manage(case: Optional[ClinicalCase], user: User) -> bool:
    return case is not None and (user.role == UserRole.admin or case.created_by == user.id)


def can_download(session: Session, attachment: Attachment, user: User) -> bool:
    if user.role in (UserRole.teacher, UserRole.admin):
        return True
    shown = session.exec(
        select(Message.id).join(Attempts, Attempts.id == Message.attempt_id)
        .where(Message.attachment_id == attachment.id, Attempts.user_id == user.id)
    ).first()
    return shown is not None


def _out(a: Attachment) -> AttachmentOut:
    return AttachmentOut(id=str(a.id), filename=a.filename, display_name=a.display_name, kind=a.kind,
                         mime_type=a.mime_type, size_bytes=a.size_bytes,
                         file_url=f"/attachments/download/{a.id}", uploaded_at=a.uploaded_at.isoformat())


# ==================== ROUTES ====================

@router.post("/upload", response_model=AttachmentUploadOut)
async def upload_attachment(
    file: UploadFile = File(...),
    case_id: int = Form(...),
    display_name: str = Form(..., max_length=200),
    description: Optional[str] = Form(None, max_length=2000),
    trigger_keywords: Optional[str] = Form(None, max_length=500),
    is_available_during_case: bool = Form(True),
    db: Session = Depends(get_session),
    user: User = Depends(teacher),
):
    """Ajoute un fichier à une station (enseignant auteur de la station, ou administrateur)."""
    case = db.get(ClinicalCase, case_id)
    if not _can_manage(case, user):
        raise HTTPException(404, "Station introuvable")
    content = await file.read()
    mime, kind, ext = checked_upload(content)
    stored_filename = f"{uuid.uuid4()}{ext}"
    file_path = f"{kind}/{case_id}/{stored_filename}"
    try:
        file_url = await storage.save_file(content, file_path)
    except Exception:  # noqa: BLE001
        logger.exception("Échec d'écriture du fichier %s", file_path)
        raise HTTPException(500, "Le fichier n'a pas pu être enregistré.")
    attachment = Attachment(case_id=case_id, filename=(file.filename or stored_filename)[:255],
                            stored_filename=stored_filename, display_name=display_name, description=description,
                            kind=kind, mime_type=mime, size_bytes=len(content), file_path=file_path,
                            file_url=file_url, is_available_during_case=is_available_during_case,
                            trigger_keywords=trigger_keywords)
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return AttachmentUploadOut(id=str(attachment.id), filename=attachment.filename,
                               file_url=f"/attachments/download/{attachment.id}", kind=attachment.kind,
                               size_bytes=attachment.size_bytes)


@router.get("/case/{case_id}", response_model=List[AttachmentOut])
def get_case_attachments(case_id: int, available_only: bool = True, db: Session = Depends(get_session),
                         user: User = Depends(teacher)):
    """Pièces jointes d'une station (enseignants et administrateurs)."""
    query = select(Attachment).where(Attachment.case_id == case_id)
    if available_only:
        query = query.where(Attachment.is_available_during_case == True)  # noqa: E712
    return [_out(a) for a in db.exec(query).all()]


@router.get("/download/{attachment_id}")
def download_attachment(attachment_id: UUID, db: Session = Depends(get_session),
                              user: User = Depends(check_authorization())):
    """Fichier d'une pièce jointe ; un étudiant n'obtient que les documents qui lui ont été montrés."""
    attachment = db.get(Attachment, attachment_id)
    if attachment is None or not can_download(db, attachment, user):
        raise HTTPException(404, "Document introuvable")
    try:
        data = from_thread.run(storage.get_file, attachment.file_path)
    except FileNotFoundError:
        raise HTTPException(404, "Document introuvable")
    except Exception:  # noqa: BLE001
        logger.exception("Lecture impossible : %s", attachment.file_path)
        raise HTTPException(500, "Le document n'a pas pu être lu.")
    return file_response(data, attachment.mime_type or "", attachment.filename or "document")


@router.get("/{attachment_id}", response_model=AttachmentOut)
def get_attachment_info(attachment_id: UUID, db: Session = Depends(get_session), user: User = Depends(teacher)):
    attachment = db.get(Attachment, attachment_id)
    if not attachment:
        raise HTTPException(404, "Document introuvable")
    return _out(attachment)


@router.delete("/{attachment_id}")
def delete_attachment(attachment_id: UUID, db: Session = Depends(get_session), user: User = Depends(teacher)):
    attachment = db.get(Attachment, attachment_id)
    if attachment is None or not _can_manage(db.get(ClinicalCase, attachment.case_id), user):
        raise HTTPException(404, "Document introuvable")
    try:
        from_thread.run(storage.delete_file, attachment.file_path)
    except Exception:  # noqa: BLE001
        logger.warning("Fichier non supprimé du stockage : %s", attachment.file_path)
    db.delete(attachment)
    db.commit()
    return {"message": "Document supprimé."}


def find_matching_attachments(message: str, case_id: int, db: Session) -> List[Attachment]:
    """Pièces jointes dont un mot-clé apparaît dans le message (patient sans outils)."""
    attachments = db.exec(
        select(Attachment)
        .where(Attachment.case_id == case_id)
        .where(Attachment.is_available_during_case == True)  # noqa: E712
        .where(Attachment.trigger_keywords.isnot(None))
    ).all()
    message_lower = message.lower()
    return [a for a in attachments
            if a.trigger_keywords and any(k.strip().lower() in message_lower
                                          for k in a.trigger_keywords.split(",") if k.strip())]
