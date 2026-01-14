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
    CaseEdnLink, CaseDisciplineLink, EdnDisciplineLink
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
    session.query(User).delete()
    
    session.commit()
    print("✅ Base de données nettoyée")


def seed_users(session: Session):
    """Crée les utilisateurs de test"""
    print("\n👤 Création des utilisateurs...")
    
    users = [
        User(
            id=2,
            username="etudiant_test",
            full_name="Étudiant Test",
            email="etudiant@test.com",
            is_active=True,
            is_superuser=False
        ),
        User(
            id=1
            username="admin",
            full_name="Administrateur",
            email="admin@test.com",
            is_active=True,
            is_superuser=True
        )
    ]
    
    for user in users:
        session.add(user)
    
    session.commit()
    print(f"✅ {len(users)} utilisateurs créés")
    return users


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


def create_case_douleur_thoracique(session: Session, disciplines: list, edn_items: list, admin_user):
    """Cas 1 : Douleur thoracique - Interrogatoire cardiologique"""
    
    case = ClinicalCase(
        id=1,
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


def create_case_dyspnee(session: Session, disciplines: list, edn_items: list, admin_user):
    """Cas 2 : Dyspnée aiguë - Suspicion d'embolie pulmonaire"""
    
    case = ClinicalCase(
        title="Dyspnée aiguë post-opératoire",
        station_type=StationType.patient_interview,
        status="published",
        created_by=admin_user.id,
        scenario_context="""Mme Martin, 45 ans, consulte aux urgences pour une dyspnée brutale apparue ce matin.
Elle a été opérée d'une prothèse totale de hanche gauche il y a 8 jours.
Elle prend des anticoagulants en prévention depuis l'opération.""",
        
        student_instructions="""Vous êtes l'interne de garde aux urgences.
Réalisez un interrogatoire complet face à cette patiente consultant pour dyspnée.
Recherchez les éléments en faveur ou contre une embolie pulmonaire.
Durée : 6 minutes""",
        
        patient_prompt="""Tu es Mme Martin, 45 ans, opérée il y a 8 jours d'une prothèse de hanche.
Tu as du mal à respirer depuis ce matin et ça t'inquiète beaucoup.

DYSPNÉE :
- Début : Brutal ce matin vers 8h, en te levant du lit
- Type : Difficulté à inspirer profondément, sensation de manquer d'air
- Intensité : Tu es gênée même au repos, tu ne peux pas faire 3 pas sans être essoufflée
- Aggravation : À l'effort (impossible de monter les escaliers)
- Position : Pas de différence couché/debout
- Pas d'orthopnée (tu peux dormir à plat)

SYMPTÔMES ASSOCIÉS :
- Douleur thoracique droite, latérale, qui augmente à l'inspiration profonde (point de côté)
- PAS de toux
- PAS d'expectoration
- PAS de fièvre
- Anxiété importante ("J'ai peur de mourir")
- Palpitations (tu sens ton cœur battre vite)

CONTEXTE CHIRURGICAL :
- Prothèse totale de hanche gauche il y a 8 jours (usure du cartilage)
- Opération bien passée, sortie de l'hôpital il y a 5 jours
- Cicatrice normale, pas de rougeur
- Kiné à domicile depuis hier
- Traitement anticoagulant : Lovenox 1 injection/jour (tu fais toi-même dans le ventre)

FACTEURS DE RISQUE :
- Immobilisation : 3 premiers jours complètement alitée, maintenant tu te lèves un peu
- Tabac : NON
- Pilule contraceptive : OUI (Leeloo depuis 10 ans)
- Voyage récent : NON
- Obésité : NON (poids normal)
- Cancer : NON
- Antécédent de phlébite/EP : NON

JAMBE OPÉRÉE :
- Pas de douleur particulière au mollet
- Pas de gonflement
- Pas de rougeur
- Tu arrives à bouger normalement (enfin, dans la limite du post-op)

ANTÉCÉDENTS :
- RAS avant l'opération
- Arthrose de hanche depuis 3 ans (d'où la prothèse)
- Pas d'asthme, pas de problème cardiaque
- 2 accouchements normaux il y a 20 et 18 ans

TRAITEMENT :
- Lovenox 0.6ml/jour en sous-cutané (anticoagulant préventif)
- Doliprane 1g si douleur
- Tramadol 50mg si douleur forte (tu n'en as plus pris depuis 3 jours)

COMPORTEMENT :
- Tu es inquiète et ça se voit
- Tu expliques clairement tes symptômes si on te pose les bonnes questions
- Tu te demandes si c'est lié à l'opération
- Tu précises que le chirurgien t'avait prévenue du risque de phlébite

RÉPONSES AUX QUESTIONS FRÉQUENTES :
- "Depuis quand ?" → Ce matin vers 8h, d'un coup
- "Vous avez de la fièvre ?" → Non, j'ai pris ma température, 37.2°
- "Vous toussez ?" → Non, pas du tout
- "Vous fumez ?" → Non, jamais fumé
- "La jambe opérée est gonflée ?" → Non, ça va, pas de gonflement particulier
- "Vous prenez bien vos anticoagulants ?" → Oui, tous les jours, je fais l'injection moi-même
- "Vous avez eu d'autres symptômes ?" → J'ai mal sur le côté quand je respire fort

Reste naturelle et montre ton inquiétude.""",
        
        duration_seconds=360
    )
    
    session.add(case)
    session.flush()
    
    # Lier aux disciplines
    pneumo = next((d for d in disciplines if d.name == Discipline.pneumologie), None)
    urgences = next((d for d in disciplines if d.name == Discipline.urgences), None)
    
    if pneumo:
        session.add(CaseDisciplineLink(case_id=case.id, discipline_id=pneumo.id))
    if urgences:
        session.add(CaseDisciplineLink(case_id=case.id, discipline_id=urgences.id))
    
    # Lier aux EDN
    edn_dyspnee = next((e for e in edn_items if e.number == 199), None)
    if edn_dyspnee:
        session.add(CaseEdnLink(case_id=case.id, edn_id=edn_dyspnee.id))
    
    # Grille d'évaluation sur 20
    grid = EvaluationGrid(
        case_id=case.id,
        version=1.0,
        total_points=20,
        is_active=True,
        items=[
            {
                "id": "item_1",
                "criterion": "Présentation et mise en confiance",
                "points": 1,
                "description": "Se présente, explique la démarche, rassure la patiente"
            },
            {
                "id": "item_2",
                "edn_code": "199",
                "criterion": "Caractérisation de la dyspnée - Début et mode d'installation",
                "points": 2,
                "description": "Heure de début, brutal/progressif, circonstances déclenchantes"
            },
            {
                "id": "item_3",
                "edn_code": "199",
                "criterion": "Caractérisation de la dyspnée - Type et intensité",
                "points": 2,
                "description": "Type (inspiratoire/expiratoire), intensité, gêne au repos/à l'effort"
            },
            {
                "id": "item_4",
                "edn_code": "199",
                "criterion": "Douleur thoracique associée",
                "points": 2,
                "description": "Recherche douleur thoracique, ses caractéristiques (pleurale si EP)"
            },
            {
                "id": "item_5",
                "edn_code": "199",
                "criterion": "Symptômes respiratoires associés",
                "points": 2,
                "description": "Toux, expectoration, hémoptysie, wheezing, stridor"
            },
            {
                "id": "item_6",
                "edn_code": "199",
                "criterion": "Signes généraux",
                "points": 1,
                "description": "Fièvre, sueurs, palpitations, malaise, syncope"
            },
            {
                "id": "item_7",
                "edn_code": "199",
                "criterion": "Contexte chirurgical et immobilisation",
                "points": 2,
                "description": "Détails opération, durée immobilisation, traitement anticoagulant"
            },
            {
                "id": "item_8",
                "edn_code": "199",
                "criterion": "Facteurs de risque de MTEV",
                "points": 3,
                "description": "Chirurgie, immobilisation, pilule, cancer, thrombophilie, ATCD MTEV"
            },
            {
                "id": "item_9",
                "edn_code": "199",
                "criterion": "Signes de phlébite",
                "points": 2,
                "description": "Douleur/gonflement mollet, chaleur, rougeur, diminution ballottement"
            },
            {
                "id": "item_10",
                "edn_code": "199",
                "criterion": "Antécédents respiratoires et cardiovasculaires",
                "points": 1,
                "description": "Asthme, BPCO, insuffisance cardiaque, cardiopathie"
            },
            {
                "id": "item_11",
                "criterion": "Traitements et allergies",
                "points": 1,
                "description": "Anticoagulants en cours, autres traitements, allergies"
            },
            {
                "id": "item_12",
                "criterion": "Qualité de l'interrogatoire",
                "points": 1,
                "description": "Structure logique, questions pertinentes, écoute, empathie"
            }
        ],
        created_at=datetime.now()
    )
    
    session.add(grid)
    session.commit()
    
    print(f"✅ Cas créé : {case.title} (ID: {case.id})")
    return case


def create_case_malaise(session: Session, disciplines: list, edn_items: list, admin_user):
    """Cas 3 : Malaise - Suspicion d'hypoglycémie"""
    
    case = ClinicalCase(
        title="Malaise chez un patient diabétique",
        station_type=StationType.patient_interview,
        status="published",
        created_by=admin_user.id,
        scenario_context="""Mr. Leblanc, 62 ans, diabétique de type 2 sous insuline, a fait un malaise ce matin.
Il a été amené aux urgences par les pompiers après un appel de sa femme.
Il est maintenant conscient et cohérent.""",
        
        student_instructions="""Vous êtes l'interne de garde aux urgences.
Réalisez un interrogatoire complet pour comprendre l'origine de ce malaise.
Recherchez les étiologies les plus fréquentes et graves.
Durée : 6 minutes""",
        
        patient_prompt="""Tu es Mr. Leblanc, 62 ans, diabétique depuis 15 ans.
Tu as fait un malaise ce matin et tu te sens mieux maintenant mais un peu fatigué.

LE MALAISE :
- Heure : Ce matin vers 9h30
- Circonstances : Tu étais dans la cuisine en train de préparer le café
- Prodromes : Sensation de faiblesse, sueurs, tremblements, tu voyais flou
- Tu t'es assis parce que tu sentais que tu allais tomber
- Perte de connaissance : OUI, ta femme dit que tu es "parti" pendant 2-3 minutes
- Pendant : Ta femme dit que tu étais pâle, les yeux fermés, tu ne répondais pas mais tu n'as pas fait de crise (pas de mouvements anormaux)
- Réveil : Progressif, tu étais confus au début, maintenant ça va mieux
- Après : Ta femme t'a donné du sucre (3 morceaux) et du jus d'orange

SYMPTÔMES AVANT LE MALAISE :
- Sueurs importantes
- Tremblements des mains
- Sensation de faim ("j'avais un petit creux")
- Vision floue
- Sensation de faiblesse dans les jambes
- PAS de douleur thoracique
- PAS de palpitations
- PAS de vertiges rotatoires
- PAS de céphalées

CONTEXTE CE MATIN :
- Tu t'es levé à 7h comme d'habitude
- Tu as fait ton injection d'insuline à 7h15 (dose habituelle : Lantus 24 unités)
- Tu N'AS PAS PRIS ton petit-déjeuner (tu n'avais pas faim, tu voulais juste un café)
- Normalement tu prends toujours ton petit-déjeuner après l'insuline
- Hier soir tu as mangé normalement

DIABÈTE :
- Diabète de type 2 depuis 15 ans
- Traité par : Metformine 1000mg matin et soir + Lantus (insuline lente) 24 unités le matin
- Suivi régulier, dernière HbA1c il y a 2 mois : 7.2% (plutôt bien équilibré)
- Tu te mesures la glycémie 2 fois par jour (matin et soir)
- Ce matin tu n'avais pas encore fait ta glycémie
- Dernière hypoglycémie : Il y a 6 mois, même contexte (oubli petit-déjeuner)
- Tu connais bien les signes d'hypoglycémie

AUTRES ANTÉCÉDENTS :
- Hypertension artérielle : Oui, depuis 10 ans
- Dyslipidémie : Oui, traité
- Problèmes cardiaques : NON, ECG normal il y a 6 mois
- AVC : NON
- Épilepsie : NON
- Rétinopathie diabétique débutante (tu vois un ophtalmo tous les ans)

TRAITEMENTS :
- Metformine 1000mg : 1cp matin et soir pendant les repas
- Lantus (insuline) : 24 unités le matin à 7h
- Amlodipine 5mg : 1/jour pour la tension
- Atorvastatine 20mg : 1/soir pour le cholestérol
- Aspirine 75mg : 1/jour en prévention

FACTEURS DÉCLENCHANTS POSSIBLES :
- Oubli du petit-déjeuner (facteur principal)
- Insuline faite normalement
- Pas d'effort physique inhabituel
- Pas de changement de traitement
- Pas de maladie intercurrente
- Pas d'alcool

COMPORTEMENT :
- Tu es rassuré maintenant car tu te sens mieux
- Tu reconnais que c'est de ta faute ("J'aurais dû déjeuner")
- Tu es un peu gêné d'avoir inquiété tout le monde
- Tu expliques bien ton diabète car tu le connais depuis longtemps
- Tu es coopératif

RÉPONSES AUX QUESTIONS FRÉQUENTES :
- "Vous avez perdu connaissance ?" → Oui, ma femme dit que je ne répondais plus pendant 2-3 minutes
- "Vous avez eu des convulsions ?" → Non, je n'ai pas bougé, j'étais juste inconscient
- "Vous aviez déjeuné ?" → Non justement, c'est ça le problème, j'ai oublié et j'avais fait mon insuline
- "C'est déjà arrivé ?" → Oui, il y a 6 mois, même situation
- "Vous avez mal à la poitrine ?" → Non, rien du tout
- "Vous prenez bien votre insuline ?" → Oui, tous les matins à 7h, 24 unités

Reste naturel et un peu gêné de cette erreur.""",
        
        duration_seconds=360
    )
    
    session.add(case)
    session.flush()
    
    # Lier aux disciplines
    med_interne = next((d for d in disciplines if d.name == Discipline.medecine_interne), None)
    urgences = next((d for d in disciplines if d.name == Discipline.urgences), None)
    
    if med_interne:
        session.add(CaseDisciplineLink(case_id=case.id, discipline_id=med_interne.id))
    if urgences:
        session.add(CaseDisciplineLink(case_id=case.id, discipline_id=urgences.id))
    
    # Lier aux EDN
    edn_malaise = next((e for e in edn_items if e.number == 209), None)
    if edn_malaise:
        session.add(CaseEdnLink(case_id=case.id, edn_id=edn_malaise.id))
    
    # Grille d'évaluation sur 20
    grid = EvaluationGrid(
        case_id=case.id,
        version=1.0,
        total_points=20,
        is_active=True,
        items=[
            {
                "id": "item_1",
                "criterion": "Présentation et mise en confiance",
                "points": 1,
                "description": "Se présente, explique l'objectif de l'interrogatoire"
            },
            {
                "id": "item_2",
                "edn_code": "209",
                "criterion": "Caractérisation du malaise - Circonstances",
                "points": 2,
                "description": "Heure, lieu, activité en cours, position (debout/assis/couché)"
            },
            {
                "id": "item_3",
                "edn_code": "209",
                "criterion": "Prodromes",
                "points": 2,
                "description": "Signes annonciateurs : sueurs, pâleur, vertiges, troubles visuels, nausées"
            },
            {
                "id": "item_4",
                "edn_code": "209",
                "criterion": "Perte de connaissance",
                "points": 2,
                "description": "Présence, durée, complète/incomplète, témoin"
            },
            {
                "id": "item_5",
                "edn_code": "209",
                "criterion": "Pendant le malaise (signes critiques)",
                "points": 2,
                "description": "Mouvements anormaux, morsure langue, perte urines, cyanose, traumatisme"
            },
            {
                "id": "item_6",
                "edn_code": "209",
                "criterion": "Récupération",
                "points": 1,
                "description": "Rapide/lente, confusion post-critique, amnésie de l'épisode"
            },
            {
                "id": "item_7",
                "edn_code": "209",
                "criterion": "Signes neurovégétatifs d'hypoglycémie",
                "points": 2,
                "description": "Sueurs, tremblements, pâleur, faim, palpitations"
            },
            {
                "id": "item_8",
                "edn_code": "209",
                "criterion": "Contexte diabétique et traitement",
                "points": 2,
                "description": "Ancienneté diabète, traitement (insuline/ADO), équilibre, auto-surveillance"
            },
            {
                "id": "item_9",
                "edn_code": "209",
                "criterion": "Facteurs déclenchants de l'hypoglycémie",
                "points": 2,
                "description": "Repas sauté, dose insuline, effort physique, erreur traitement"
            },
            {
                "id": "item_10",
                "edn_code": "209",
                "criterion": "Élimination causes cardiovasculaires",
                "points": 2,
                "description": "Douleur thoracique, palpitations, dyspnée, ATCD cardiaques"
            },
            {
                "id": "item_11",
                "edn_code": "209",
                "criterion": "Élimination causes neurologiques",
                "points": 1,
                "description": "Céphalées, déficit moteur, troubles parole, ATCD épilepsie/AVC"
            },
            {
                "id": "item_12",
                "criterion": "Qualité de l'interrogatoire",
                "points": 1,
                "description": "Structure logique, questions ouvertes puis ciblées, écoute, synthèse"
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
        
        # Création des données de base
        users = seed_users(session)
        admin_user = users[1]  # L'utilisateur admin est le deuxième dans la liste
        disciplines = seed_disciplines(session)
        edn_items = seed_edn_items(session)
        
        # Création des cas cliniques avec grilles
        print("\n🏥 Création des cas cliniques d'interrogatoire...\n")
        
        case1 = create_case_douleur_thoracique(session, disciplines, edn_items, admin_user)
        case2 = create_case_dyspnee(session, disciplines, edn_items, admin_user)
        case3 = create_case_malaise(session, disciplines, edn_items, admin_user)
        
        print("\n" + "="*60)
        print("✅ SEED TERMINÉ AVEC SUCCÈS!")
        print("="*60)
        print(f"\n📊 Résumé:")
        print(f"   - {len(users)} utilisateurs")
        print(f"   - {len(disciplines)} disciplines")
        print(f"   - {len(edn_items)} items EDN")
        print(f"   - 3 cas cliniques d'interrogatoire")
        print(f"   - 3 grilles d'évaluation (20 points chacune)")
        
        print(f"\n🎯 Cas disponibles pour le CLI:")
        print(f"   1. {case1.title} (ID: {case1.id})")
        print(f"   2. {case2.title} (ID: {case2.id})")
        print(f"   3. {case3.title} (ID: {case3.id})")
        
        print(f"\n👤 Utilisateur de test:")
        print(f"   - Username: etudiant_test")
        print(f"   - ID: {users[0].id}")
        
        print(f"\n💡 Pour tester:")
        print(f"   python ecos_cli.py chat-loop {case1.id}")
        print()


if __name__ == "__main__":
    main()
