"""Import de packs privés de stations (pack fictif construit pour le test)."""
import json
import shutil

import pytest

from case_sheet import AttitudeScale, CaseSheet, Fact, GridItem, StationDocument

PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


def _patient_station() -> dict:
    sheet = CaseSheet()
    sheet.station.title, sheet.station.domain = "Conseils fictifs", "education_prevention"
    sheet.station.student_instructions = "Expliquez les règles de vie."
    sheet.patient.age = 60
    sheet.facts = [Fact(id="f_tabac", category="mode_de_vie", label="Tabac", patient_words="Je fume un peu.",
                        asked_about="le tabac")]
    sheet.correction.grid = [GridItem(id="i1", criterion="Propose une aide au sevrage")]
    sheet.correction.scales = [AttitudeScale(id="ecouter", label="Aptitude à écouter")]
    return {"key": "s1", "sheet": sheet.model_dump(mode="json"), "review": "a_relire"}


def _silent_station() -> dict:
    sheet = CaseSheet()
    sheet.station.title, sheet.station.domain, sheet.station.interlocutor = "Tracé fictif", "iconographie", "aucun"
    sheet.station.student_instructions = "Interprétez le document 1."
    sheet.station.documents = [StationDocument(id="d_1", label="Document 1 : tracé")]
    sheet.correction.expected_diagnosis = "Normal"
    sheet.correction.grid = [GridItem(id="i1", criterion="Conclut à un tracé normal")]
    return {"key": "s2", "sheet": sheet.model_dump(mode="json"), "files": {"d_1": "images/trace.png"}}


@pytest.fixture
def pack(tmp_path):
    root = tmp_path / "pack-fictif"
    (root / "stations").mkdir(parents=True)
    (root / "images").mkdir()
    (root / "images" / "trace.png").write_bytes(PNG)
    (root / "pack.json").write_text(json.dumps({"id": "fictif", "title": "Recueil fictif",
                                                "license_note": "test",
                                                "stations": ["stations/s1.json", "stations/s2.json"]}))
    (root / "stations" / "s1.json").write_text(json.dumps(_patient_station()))
    (root / "stations" / "s2.json").write_text(json.dumps(_silent_station()))
    return root


@pytest.fixture
def admin(session):
    from models import User, UserRole
    user = User(username="admin", hashed_password="x", role=UserRole.admin)
    session.add(user)
    session.commit()
    return user


def test_import_is_idempotent(session, pack, admin):
    from sqlmodel import select

    import case_publishing
    from models import Attachment, CaseVersion, ClinicalCase
    from station_packs import find_packs, import_pack

    saved = {}

    def save(data, path):
        saved[path] = data
        return f"/files/{path}"

    report = import_pack(session, pack, admin, save_file=save)
    assert sorted(report.created) == ["fictif/s1", "fictif/s2"] and not report.drafts

    s1 = session.exec(select(ClinicalCase).where(ClinicalCase.source_key == "fictif/s1")).one()
    s2 = session.exec(select(ClinicalCase).where(ClinicalCase.source_key == "fictif/s2")).one()
    assert s1.status == s2.status == "published"
    assert s1.review_status == "a_relire" and s2.review_status is None
    att = session.exec(select(Attachment).where(Attachment.case_id == s2.id)).one()
    assert saved == {"packs/fictif/s2/trace.png": PNG} and att.mime_type == "image/png"
    info = case_publishing.runtime(case_publishing.versions(session, s2.id)[0])
    assert info["interlocutor"] == "aucun" and info["documents"][0]["attachment_id"] == str(att.id)
    assert s2.sheet["station"]["source"] == "Recueil fictif"

    # Réimport à l'identique : pas de nouvelle version, pas de nouvelle pièce jointe
    report = import_pack(session, pack, admin, save_file=save)
    assert sorted(report.unchanged) == ["fictif/s1", "fictif/s2"]
    assert len(session.exec(select(CaseVersion)).all()) == 2
    assert len(session.exec(select(Attachment)).all()) == 1

    # Station modifiée : republiée (version 2) ; statut de relecture inchangé
    s1.review_status = "relue"
    session.add(s1)
    session.commit()
    station = _patient_station()
    station["sheet"]["patient"]["age"] = 61
    (pack / "stations" / "s1.json").write_text(json.dumps(station))
    report = import_pack(session, pack, admin, save_file=save)
    assert report.updated == ["fictif/s1"]
    assert [v.version for v in case_publishing.versions(session, s1.id)] == [2, 1]
    assert session.get(ClinicalCase, s1.id).review_status == "relue"

    # Archive .zip et découverte dans un dossier
    shutil.make_archive(str(pack.parent / "fictif"), "zip", pack.parent, pack.name)
    assert [p.name for p in find_packs(pack.parent)] == ["fictif.zip", "pack-fictif"]
    report = import_pack(session, pack.parent / "fictif.zip", admin, save_file=save)
    assert sorted(report.unchanged) == ["fictif/s1", "fictif/s2"]


def test_station_with_errors_stays_draft(session, pack, admin):
    from station_packs import import_pack

    broken = _patient_station()
    broken["sheet"]["correction"]["grid"] = []
    (pack / "stations" / "s1.json").write_text(json.dumps(broken))
    report = import_pack(session, pack, admin, save_file=lambda d, p: "/files/x")
    assert report.drafts == ["fictif/s1"] and "grille" in report.messages[0]
