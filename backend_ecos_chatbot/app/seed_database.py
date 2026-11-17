#!/usr/bin/env python3
"""
Script de seed pour la base de données ECOS.
Crée des cas cliniques d'interrogatoire avec leurs grilles d'évaluation.

Usage:
    python seed_database.py
"""

import os
import sys
from datetime import datetime
from sqlmodel import Session, create_engine, select
# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import (
    User, ClinicalCase, StationType, EvaluationGrid, CaseVersion, CorpusChunk,
    EDNItem, DisciplineItem, Discipline,
    CaseEdnLink, CaseDisciplineLink, EdnDisciplineLink, UserRole
)
import case_publishing
from case_examples import dupont_sheet

def get_engine():
    """Récupère l'engine de base de données"""
    database_url = os.getenv("DATABASE_URL", "postgresql://ecos_chatbot:ecos_password@localhost:5432/ecos_chatbot_db")
    return create_engine(database_url, echo=True)


def clear_database(session: Session):
    """Supprime toutes les données existantes"""
    print("🗑️  Nettoyage de la base de données...")
    
    # Supprimer dans l'ordre inverse des dépendances
    from models import Message, Attempts, Attachment, ModerationEvent
    
    session.query(ModerationEvent).delete()
    session.query(Message).delete()
    session.query(Attempts).delete()
    session.query(CaseVersion).delete()
    session.query(Attachment).delete()
    session.query(CaseEdnLink).delete()
    session.query(CaseDisciplineLink).delete()
    session.query(EdnDisciplineLink).delete()
    session.query(EvaluationGrid).delete()
    session.query(ClinicalCase).delete()
    session.query(EDNItem).delete()
    session.query(DisciplineItem).delete()
    
    session.commit()
    print("✅ Base de données nettoyée")

def seed_disciplines(session: Session):
    """Crée les disciplines médicales"""
    print("\n🏥 Création des disciplines...")
    
    disciplines_to_create = [
        Discipline.cardiologie,
        Discipline.pneumologie,
        Discipline.urgences,
        Discipline.medecine_interne,
        Discipline.neurologie
    ]
    
    disciplines = []
    for disc in disciplines_to_create:
        discipline = DisciplineItem(name=disc)
        session.add(discipline)
        disciplines.append(discipline)
    
    session.commit()
    print(f"✅ {len(disciplines)} disciplines créées")
    return disciplines


def seed_edn_items(session: Session):
    """Items EDN (numérotation R2C). Les titres officiels viennent du corpus importé
    (scripts/ingest_corpus.py) s'il est présent ; les tables du corpus ne sont pas vidées."""
    print("\n📚 Création des items EDN...")

    titles = {
        339: "Syndromes coronariens aigus",
        230: "Douleur thoracique aiguë",
        203: "Dyspnée aiguë et chronique",
        221: "Hypertension artérielle de l'adulte et de l'enfant",
    }
    for number, title in session.exec(select(CorpusChunk.item_number, CorpusChunk.chapter_title).distinct()).all():
        if number:
            titles[number] = title

    edn_items = [EDNItem(number=n, title=t) for n, t in sorted(titles.items())]
    for item in edn_items:
        session.add(item)

    session.commit()
    print(f"✅ {len(edn_items)} items EDN créés")
    return edn_items


def create_case_douleur_thoracique(session: Session, disciplines: list, edn_items: list):
    """Cas 1 : Douleur thoracique - Interrogatoire cardiologique.

    Construit depuis sa fiche structurée (case_examples.dupont_sheet) et publié comme
    le ferait l'atelier de création : version 1 figée, grille compilée, items EDN liés."""
    author = session.exec(select(User).where(User.username == "bensac")).first()
    if author is None:
        author = session.exec(select(User).where(User.role == UserRole.admin)).first()
    if author is None:
        raise SystemExit("Aucun compte administrateur : créez-en un avant le seed.")

    sheet = dupont_sheet()
    case = ClinicalCase(title=sheet.station.title, created_by=author.id, student_instructions="",
                        scenario_context="", duration_seconds=sheet.station.duration_minutes * 60)
    session.add(case)
    session.flush()
    version = case_publishing.publish(session, case, sheet, author.id)

    for name in (Discipline.cardiologie, Discipline.urgences):
        discipline = next((d for d in disciplines if d.name == name), None)
        if discipline:
            session.add(CaseDisciplineLink(case_id=case.id, discipline_id=discipline.id))

    session.commit()
    print(f"✅ Cas créé : {case.title} (ID: {case.id}, version publiée {version.version})")
    return case


def main():
    """Fonction principale de seed"""
    print("🌱 Démarrage du seed de la base de données ECOS...\n")
    
    engine = get_engine()
    
    with Session(engine) as session:
        # Nettoyage
        clear_database(session)

        disciplines = seed_disciplines(session)
        edn_items = seed_edn_items(session)
        
        # Création des cas cliniques avec grilles
        print("\n🏥 Création des cas cliniques d'interrogatoire...\n")
        
        case1 = create_case_douleur_thoracique(session, disciplines, edn_items)
        
        print("\n" + "="*60)
        print("✅ SEED TERMINÉ AVEC SUCCÈS!")
        print("="*60)
        print(f"\n📊 Résumé:")
        print(f" - Disciplines créées : {len(disciplines)}")
        print(f" - Items EDN créés : {len(edn_items)}")
        print(f" - Cas cliniques créés : 1")
        print("\n💡 Pour tester le cas créé, utilisez les commandes CLI suivantes :")
        print(f"   python ecos_cli.py chat-loop {case1.id}")
        print()


if __name__ == "__main__":
    main()
