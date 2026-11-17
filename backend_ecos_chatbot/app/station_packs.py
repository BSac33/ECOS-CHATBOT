# station_packs.py
"""
Packs privés de stations : contenus protégés (livre, banque d'une faculté) importés en
base sans jamais passer par le dépôt git.

Format d'un pack (dossier, ou archive .zip du dossier) :

    pack.json                 {"id", "title", "license_note", "stations": ["stations/ecos01.json", ...]}
    stations/ecos01.json      {"key": "ecos01", "sheet": {...fiche CaseSheet...},
                               "files": {"<id du document>": "images/ecos01_doc1.png"},
                               "review": "a_relire"}
    images/...                documents de la vignette (ECG, imagerie)

Import idempotent : chaque station est retrouvée par sa clé (clinical_cases.source_key =
"<id du pack>/<clé>"). Une fiche modifiée est republiée (nouvelle version) ; une fiche
inchangée ne crée pas de version. Les documents deviennent des pièces jointes du cas.

Emplacement conventionnel : backend_ecos_chatbot/app/private/stations/ (ignoré par git,
visible dans le conteneur). Le seed importe tous les packs qui s'y trouvent.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from sqlmodel import Session, select

import case_publishing
from case_sheet import CaseSheet, blocking, check_sheet
from models import Attachment, ClinicalCase, User

PRIVATE_DIR = Path(__file__).resolve().parent / "private" / "stations"


@dataclass
class ImportReport:
    pack: str
    created: List[str] = field(default_factory=list)
    updated: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    drafts: List[str] = field(default_factory=list)      # erreurs bloquantes : non publiées
    messages: List[str] = field(default_factory=list)

    def summary(self) -> str:
        return (f"{self.pack} : {len(self.created)} créée(s), {len(self.updated)} republiée(s), "
                f"{len(self.unchanged)} inchangée(s), {len(self.drafts)} en brouillon")


def find_packs(directory: Path = PRIVATE_DIR) -> List[Path]:
    """Packs d'un dossier : sous-dossiers contenant pack.json, et archives .zip."""
    if not directory.is_dir():
        return []
    found = [p for p in sorted(directory.iterdir())
             if (p.is_dir() and (p / "pack.json").is_file()) or (p.is_file() and p.suffix == ".zip")]
    return found


def _open(path: Path) -> tuple[Path, Optional[tempfile.TemporaryDirectory]]:
    if path.is_dir():
        return path, None
    tmp = tempfile.TemporaryDirectory()
    with zipfile.ZipFile(path) as z:
        z.extractall(tmp.name)
    root = Path(tmp.name)
    if not (root / "pack.json").is_file():                 # archive d'un dossier
        inner = [p for p in root.iterdir() if (p / "pack.json").is_file()]
        if inner:
            root = inner[0]
    return root, tmp


def _sheet_hash(sheet: dict) -> str:
    return hashlib.sha256(json.dumps(sheet, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _default_save(data: bytes, path: str) -> str:
    from storage import storage
    return asyncio.run(storage.save_file(data, path))


def import_pack(session: Session, path: Path, author: User,
                save_file: Callable[[bytes, str], str] = _default_save) -> ImportReport:
    root, tmp = _open(Path(path))
    try:
        manifest = json.loads((root / "pack.json").read_text(encoding="utf-8"))
        pack_id = manifest["id"]
        report = ImportReport(pack=manifest.get("title") or pack_id)
        files = manifest.get("stations") or [str(p.relative_to(root)) for p in sorted((root / "stations").glob("*.json"))]
        for rel in files:
            station = json.loads((root / rel).read_text(encoding="utf-8"))
            _import_station(session, root, pack_id, manifest, station, author, save_file, report)
        session.commit()
        return report
    finally:
        if tmp is not None:
            tmp.cleanup()


def _import_station(session: Session, root: Path, pack_id: str, manifest: dict, station: dict, author: User,
                    save_file: Callable[[bytes, str], str], report: ImportReport) -> None:
    key = f"{pack_id}/{station['key']}"
    sheet = CaseSheet.model_validate(station["sheet"])
    if not sheet.station.source and manifest.get("title"):
        sheet.station.source = manifest["title"]

    case = session.exec(select(ClinicalCase).where(ClinicalCase.source_key == key)).first()
    created = case is None
    if created:
        case = ClinicalCase(title=f"Import {key}", created_by=author.id, status="draft", source_key=key,
                            student_instructions="", scenario_context="",
                            duration_seconds=sheet.station.duration_minutes * 60)
        session.add(case)
        session.flush()

    # Documents de la vignette -> pièces jointes du cas (chemin stable : réimport = remplacement)
    for doc in sheet.station.documents:
        rel = (station.get("files") or {}).get(doc.id)
        if not rel:
            continue
        source = root / rel
        data = source.read_bytes()
        file_path = f"packs/{pack_id}/{station['key']}/{source.name}"
        attachment = session.exec(select(Attachment).where(Attachment.case_id == case.id,
                                                           Attachment.file_path == file_path)).first()
        url = save_file(data, file_path)
        if attachment is None:
            mime = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
            attachment = Attachment(case_id=case.id, filename=source.name, stored_filename=source.name,
                                    display_name=doc.label or source.stem, kind="image" if mime.startswith("image/") else "document",
                                    mime_type=mime, size_bytes=len(data), file_path=file_path, file_url=url,
                                    description=doc.label)
        else:
            attachment.size_bytes, attachment.display_name, attachment.uploaded_at = len(data), doc.label, datetime.now()
        session.add(attachment)
        session.flush()
        doc.attachment_id = str(attachment.id)

    sheet_dict = sheet.model_dump(mode="json")
    latest = next((v for v in case_publishing.versions(session, case.id) if v.status == "published"), None)
    if latest is not None and _sheet_hash(latest.sheet or {}) == _sheet_hash(sheet_dict):
        report.unchanged.append(key)
        return

    case.sheet = sheet_dict
    if created and station.get("review") == "a_relire":
        case.review_status, case.review_requested_at = "a_relire", datetime.now()
    session.add(case)

    errors = blocking(check_sheet(sheet))
    title = sheet.station.title.strip()
    clash = session.exec(select(ClinicalCase).where(ClinicalCase.title == title, ClinicalCase.id != case.id)).first()
    if errors or clash:
        report.drafts.append(key)
        reason = "titre déjà pris" if clash else "; ".join(e.message for e in errors)
        report.messages.append(f"{key} reste en brouillon : {reason}")
        return
    case_publishing.publish(session, case, sheet, author.id)
    (report.created if created else report.updated).append(key)
