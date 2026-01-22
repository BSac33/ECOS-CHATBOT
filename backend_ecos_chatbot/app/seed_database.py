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
    User, ClinicalCase, StationType, EvaluationGrid,
    EDNItem, DisciplineItem, Discipline,
    CaseEdnLink, CaseDisciplineLink, EdnDisciplineLink, UserRole
)

def get_engine():
    """Récupère l'engine de base de données"""
    database_url = os.getenv("DATABASE_URL", "postgresql://ecos_chatbot:ecos_password@localhost:5432/ecos_chatbot_db")
    return create_engine(database_url, echo=True)


def clear_database(session: Session):
    """Supprime toutes les données existantes"""
    print("🗑️  Nettoyage de la base de données...")
    
    # Supprimer dans l'ordre inverse des dépendances
    from models import Message, Attempts, Attachment
    
    session.query(Message).delete()
    session.query(Attempts).delete()
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
    """Crée des items EDN de base"""
    print("\n📚 Création des items EDN...")
    
    edn_items = [
        EDNItem(number=132, title="Angine de poitrine et infarctus du myocarde"),
        EDNItem(number=199, title="Dyspnée aiguë et chronique"),
        EDNItem(number=209, title="Malaise, perte de connaissance, crise comitiale"),
        EDNItem(number=103, title="Prévention du risque cardiovasculaire"),
    ]
    
    for item in edn_items:
        session.add(item)
    
    session.commit()
    print(f"✅ {len(edn_items)} items EDN créés")
    return edn_items


def create_case_douleur_thoracique(session: Session, disciplines: list, edn_items: list):
    """Cas 1 : Douleur thoracique - Interrogatoire cardiologique"""
    
    statement = select(User).where(User.username == "bensac")
    admin_user = session.exec(statement).first()
    
    print(admin_user)
    
    case = ClinicalCase(
        id=0,
        title="Douleur thoracique - Suspicion de SCA",
        station_type=StationType.patient_interview,
        status="published",
        created_by=admin_user.id,
        scenario_context="""Mr. Dupont, 58 ans, consulte aux urgences pour une douleur thoracique survenue il y a 2 heures.
Il est fumeur (30 PA), hypertendu traité par IEC, et a un père décédé d'infarctus à 52 ans.
La douleur est rétrosternale, constrictive, avec irradiation dans le bras gauche.""",
        
        student_instructions="""Vous êtes l'interne de garde aux urgences. 
Réalisez un interrogatoire complet face à ce patient consultant pour douleur thoracique. Enoncez le diagnostic le plus probable et l'examen complémentaire à réaliser en priorité.
Durée : 6 minutes""",
        
        patient_prompt="""Tu es Mr. Dupont, 58 ans, fumeur.
Tu as une douleur dans la poitrine depuis 2h qui te fait très peur.

CARACTÉRISTIQUES DE LA DOULEUR :
- Siège : Derrière le sternum (rétrosternale)
- Type : Serrement, poids sur la poitrine, "comme un étau"
- Intensité : 8/10
- Irradiation : Bras gauche et mâchoire
- Début : Brutal il y a 2h, au repos en regardant la télé
- Durée : Continue depuis 2h
- Facteurs déclenchants : Rien de particulier, tu étais tranquille
- Facteurs calmants : Rien ne calme, tu as pris du Doliprane sans effet

SYMPTÔMES ASSOCIÉS :
- Sueurs importantes (ton front est mouillé)
- Nausées légères
- Angoisse importante ("J'ai peur de mourir")
- PAS d'essoufflement
- PAS de fièvre

ANTÉCÉDENTS :
- Hypertension depuis 5 ans, traité par Ramipril 5mg
- Hypercholestérolémie non traitée (tu ne voulais pas prendre de médicaments)
- Tabac : 1 paquet/jour depuis 40 ans (tu as essayé d'arrêter plusieurs fois)
- Père décédé d'infarctus à 52 ans
- PAS de diabète

TRAITEMENT HABITUEL :
- Ramipril 5mg : 1/jour le matin
- Doliprane si besoin

CONTEXTE :
- Tu travailles comme comptable
- Pas d'activité physique régulière
- Tu es marié, 2 enfants adultes
- Tu n'as jamais eu de douleur comme ça avant
- Il y a 6 mois, tu avais eu une petite douleur à l'effort mais qui passait vite (tu n'en as jamais parlé)

COMPORTEMENT :
- Tu es anxieux et tu le montres
- Tu poses la question : "C'est grave docteur ? C'est le cœur ?"
- Tu es coopératif et réponds honnêtement aux questions
- Si l'étudiant te rassure, tu te calmes un peu

Reste naturel et humain. Tu as peur mais tu fais confiance au médecin.""",
        
        duration_seconds=360  # 6 minutes
    )
    
    session.add(case)
    session.flush()  # Pour obtenir l'ID
    
    # Lier aux disciplines
    cardio = next((d for d in disciplines if d.name == Discipline.cardiologie), None)
    urgences = next((d for d in disciplines if d.name == Discipline.urgences), None)
    
    if cardio:
        session.add(CaseDisciplineLink(case_id=case.id, discipline_id=cardio.id))
    if urgences:
        session.add(CaseDisciplineLink(case_id=case.id, discipline_id=urgences.id))
    
    # Lier aux EDN
    edn_angine = next((e for e in edn_items if e.number == 132), None)
    edn_risque = next((e for e in edn_items if e.number == 103), None)
    
    if edn_angine:
        session.add(CaseEdnLink(case_id=case.id, edn_id=edn_angine.id))
    if edn_risque:
        session.add(CaseEdnLink(case_id=case.id, edn_id=edn_risque.id))
    
    # Grille d'évaluation sur 20
    grid = EvaluationGrid(
        case_id=case.id,
        version=1.0,
        total_points=20,
        is_active=True,
        items=[
            {
                "id": "item_1",
                "criterion": "Présentation du médecin",
                "points": 1,
                "description": "L'étudiant se présente (Nom prénom, cite sa fonction) = bien fait; se présente partiellement = 0.5; dit seulement bonjour / ne se présente pas = 0"
            },
            {
                "id": "item_2",
                "criterion": "Compétences relationnelles",
                "points": 1, 
                "description": "L'étudiant adopte un comportement facilitant la communication (politesse, écoute, empathie)"
            },
            {
                "id": "item_3",
                "criterion": "Caractéristiques de la douleur - Type et intensité",
                "points": 2,
                "description": "Précise le type (constrictive, serrement) = 1 pt et l'intensité (Echelle de 0-10) = 1 pt"
            },
            {
                "id": "item_4",
                "criterion": "Caractéristiques de la douleur - Chronologie",
                "points": 1,
                "description": "Heure de début, durée, mode d'installation (brutal/progressif)"
            },
            {
                "id": "item_5",
                "criterion": "Circonstances déclenchantes et facteurs modulants",
                "points": 1,
                "description": "Recherche facteurs déclenchants (effort, repos) et calmants (position, nitrés)"
            },
            {
                "id": "item_6",
                "criterion": "Symptômes associés",
                "points": 1,
                "description": "Recherche sueurs, nausées, dyspnée, palpitations, malaise, syncope (au moins un) : 1 pt"
            },
            {
                "id": "item_7",
                "criterion": "Facteurs de risque cardiovasculaires - Majeurs",
                "points": 2,
                "description": "Recherche les facteurs de risque cardiovasculaires: Tabac, HTA, diabète, dyslipidémie, hérédité"
            },
            {
                "id": "item_8",
                "criterion": "Antécédents cardiovasculaires personnels et familiaux",
                "points": 1,
                "description": "Angor, IDM, revascularisation, AVC, AOMI, douleurs similaires antérieures, antécédents familiaux"
            },
            {
                "id": "item_9",
                "criterion": "Recherche des allergies",
                "points": 1,
                "description": "Demande si antécédent d'allergie médicamenteuse ou autre"
            },
            {
                "id": "item_10",
                "criterion": "Traitements habituels et allergies",
                "points": 2,
                "description": "Liste les traitements actuels (=1 pt) et recherche allergies médicamenteuses (=1 pt)"
            },
            {
                "id": "item_11",
                "criterion": "Contexte psychosocial",
                "points": 1,
                "description": "Demande la profession: 0.5 pt, situation familiale: 0.5 pt)"
            },
            {
                "id": "item_12",
                "criterion": "Diagnostic principal suspecté",
                "points": 2,
                "description": "Suspecte la survenue d'un syndrome coronarien aigu / infarctus du myocarde"
            },
            {
                "id": "item_13",
                "criterion": "Demande d'examen complémentaire pertinent",
                "points": 4,
                "description": "Demande un électrocardiogramme  = 2 pts, 18 dérivations = 4 pts"
            },
            {
                "id": "item_14",
                "criterion": "Recherche d'un angor d'effort",
                "points": 1,
                "description": "Recherche si le patient a déjà eu des douleurs thoraciques à l'effort auparavant"
            }
        ],
        created_at=datetime.now()
    )
    
    session.add(grid)
    session.commit()
    
    print(f"✅ Cas créé : {case.title} (ID: {case.id})")
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
