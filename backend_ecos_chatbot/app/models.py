from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4
from click import Option
from sqlalchemy import false
from sqlmodel import Field, Relationship, SQLModel
from datetime import date, datetime
from sqlalchemy import Column
from sqlalchemy.types import JSON
from pydantic import BaseModel
from pydantic import Field as PydanticField

class AttemptCreateIn(BaseModel):
    case_id: int

class AttemptOut(BaseModel):
    id: str  # UUID sérialisé
    case_id: int
    created_at: str
    is_completed: bool

class ChatIn(BaseModel):
    message: str

class ExaminerNoteOut(BaseModel):
    """Information transmise par l'examinateur (hors personnage patient).

    kind = "exam_findings" : résultats d'examen clinique demandés par l'étudiant
    kind = "document"      : examen complémentaire / document affiché (ECG, bio, imagerie...)
    """
    kind: str
    title: str
    content: str
    attachment_id: Optional[str] = None
    file_url: Optional[str] = None
    mime_type: Optional[str] = None

class ChatOut(BaseModel):
    patient_reply: str
    attachments: Optional[List[str]] = None  # UUIDs des fichiers attachés
    # True si le message étudiant a été bloqué par les garde-fous :
    # patient_reply contient alors le message de l'examinateur (hors personnage)
    blocked: bool = False
    examiner_notes: List[ExaminerNoteOut] = []
    # Identifiant du message patient enregistré (mode vocal : marquage d'une coupure)
    patient_message_id: Optional[str] = None

class AttachmentUploadOut(BaseModel):
    id: str  # UUID sérialisé
    filename: str
    file_url: str
    kind: str
    size_bytes: int

class AttachmentOut(BaseModel):
    id: str  # UUID sérialisé
    filename: str
    display_name: str
    kind: str
    mime_type: str
    size_bytes: int
    file_url: str
    uploaded_at: str

class EvaluationItemOut(BaseModel):
    """Un item individuel de la grille d'évaluation avec le résultat"""
    item_id: str
    criterion: str
    points_awarded: float
    points_possible: float
    is_validated: bool
    justification: str

class EvaluationResultOut(BaseModel):
    """Résultat complet de l'évaluation d'une tentative"""
    items: List[EvaluationItemOut]
    total_score: float
    total_possible: float
    percentage: float
    general_feedback: str

class EvaluationOut(BaseModel):
    """Enveloppe pour le résultat d'évaluation"""
    evaluation: EvaluationResultOut
    
class UserOut(BaseModel):
    id: int
    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    is_active: bool
    role: str

# ============= ADMIN MODELS =============

class ExamFindingIn(BaseModel):
    """Résultat d'examen clinique communiqué par l'examinateur si l'étudiant le demande.

    Ex: {"id": "auscultation_cardiaque", "label": "Auscultation cardiaque",
         "findings": "Bruits du cœur réguliers, pas de souffle."}
    """
    id: str = PydanticField(pattern=r"^[a-z0-9_]+$", max_length=64)
    label: str
    findings: str

class ClinicalCaseCreateIn(BaseModel):
    """Création d'un nouveau cas clinique"""
    title: str
    station_type: str  # "patient_interview" | "exam_analysis" | etc.
    student_instructions: str
    scenario_context: str
    patient_prompt: Optional[str] = None
    exam_findings: Optional[List[ExamFindingIn]] = None
    voice_id: Optional[str] = None  # voix du patient (chemin dans kyutai/tts-voices)
    duration_seconds: int = 900  # 15 min par défaut
    status: str = "draft"  # "draft" | "published"
    # created_by sera ajouté automatiquement depuis l'auth


class ClinicalCaseUpdateIn(BaseModel):
    """Mise à jour d'un cas clinique"""
    title: Optional[str] = None
    station_type: Optional[str] = None
    student_instructions: Optional[str] = None
    scenario_context: Optional[str] = None
    patient_prompt: Optional[str] = None
    exam_findings: Optional[List[ExamFindingIn]] = None
    voice_id: Optional[str] = None
    duration_seconds: Optional[int] = None
    status: Optional[str] = None


class ClinicalCaseOut(BaseModel):
    """Sortie complète d'un cas clinique"""
    id: int
    title: str
    station_type: str
    student_instructions: str
    scenario_context: str
    patient_prompt: Optional[str]
    exam_findings: Optional[List[dict]] = None
    voice_id: Optional[str] = None
    duration_seconds: int
    status: str
    created_by: int
    has_evaluation_grid: bool


class ClinicalCasePublicOut(BaseModel):
    """Sortie publique d'un cas clinique (sans les instructions sensibles)"""
    id: int
    title: str
    station_type: str
    duration_seconds: int
    status: str
    disciplines: List[str] = []  # Noms des disciplines
    edn_codes: List[int] = []  # Numéros des items EDN
    has_evaluation_grid: bool


class EvaluationGridCreateIn(BaseModel):
    """Création d'une grille d'évaluation"""
    case_id: int
    version: float = 1.0
    total_points: int
    items: List[dict]  # Liste d'items avec id, criterion, points, description


class EvaluationGridUpdateIn(BaseModel):
    """Mise à jour d'une grille d'évaluation"""
    version: Optional[float] = None
    total_points: Optional[int] = None
    items: Optional[List[dict]] = None
    is_active: Optional[bool] = None


class EvaluationGridOut(BaseModel):
    """Sortie d'une grille d'évaluation"""
    id: int
    case_id: int
    version: float
    total_points: int
    is_active: bool
    items: List[dict]


class Discipline(str, Enum): 
    cardiologie = "Cardiologie"
    pneumologie = "Pneumologie"
    nephrologie = "Néphrologie"
    infectiologie = "Infectiologie"
    hepatogastroenterologie = "Hépatogastroentérologie"
    neurologie = "Neurologie"
    geriatrie = "Gériatrie"
    endocrinologie = "Endocrinologie"
    rhumatologie = "Rhumatologie"
    hematologie = "Hématologie"
    oncologie = "Oncologie"
    psychiatrie = "Psychiatrie"
    sante_publique = "Santé Publique"
    urgences = "Urgences"
    reanimation = "Réanimation"
    urologie = "Urologie"
    gynecologie = "Gynécologie"
    pediatrie = "Pédiatrie"
    medecine_legale = "Médecine Légale"
    medecine_interne = "Médecine Interne"
    optalmologie = "Ophtalmologie"
    orl = "ORL"
    dermatologie = "Dermatologie"
    orthopedie = "Orthopédie"
    stomatologie = "Stomatologie"
    mpr = "MPR"
    soins_palliatifs = "Soins Palliatifs"
    medecine_travail = "Médecine du Travail"

class ChatRole(str, Enum):
    system = "system"
    student = "student"
    patient = "patient"
    # Informations données par l'examinateur (résultats d'examen clinique, documents affichés)
    examiner = "examiner"
    
class UserRole(str, Enum):
    student = "student"
    teacher = "teacher"
    admin = "admin"

class StationType(str, Enum):
    """Type de station ECOS"""
    patient_interview = "patient_interview"  # Interrogatoire patient (nécessite impersonation)
    exam_analysis = "exam_analysis"  # Analyse d'examens (radio, ECG, labo)
    procedure = "procedure"  # Démonstration de geste technique
    diagnosis_announcement = "diagnosis_announcement"  # Annonce de diagnostic
    mixed = "mixed"  # Station mixte (ex: interrogatoire puis examen)

### ============================ LINK TABLES ============================ ###

class CaseEdnLink(SQLModel, table=True):
    case_id: Optional[int] = Field(
        default=None, foreign_key="clinical_cases.id", primary_key=True
    )
    edn_id: Optional[int] = Field(
        default=None, foreign_key="edn_items.id", primary_key=True
    )
    
class CaseDisciplineLink(SQLModel, table=True):
    case_id: Optional[int] = Field(
        default=None, foreign_key="clinical_cases.id", primary_key=True
    )
    discipline_id: Optional[int] = Field(
        default=None, foreign_key="disciplines.id", primary_key=True
    )
    
class EdnDisciplineLink(SQLModel, table=True):
    edn_id: Optional[int] = Field(
        default=None, foreign_key="edn_items.id", primary_key=True
    )
    discipline_id: Optional[int] = Field(
        default=None, foreign_key="disciplines.id", primary_key=True
    )

##============================ MAIN TABLES ============================##

class ClinicalCase(SQLModel, table=True):
    __tablename__ = "clinical_cases"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True, unique=True)
    
    # Créateur du cas (enseignant/admin)
    created_by: int = Field(foreign_key="users.id", index=True)
    
    # Statut de publication (draft = brouillon, published = accessible aux étudiants)
    status: str = Field(default="draft", index=True)  # "draft" | "published"
    
    # Type de station
    station_type: StationType = Field(default=StationType.patient_interview, index=True)
    
    # Consignes pour l'étudiant (toujours présentes)
    student_instructions: str
    
    # Context initial du scénario (toujours présent)
    # Ex: "Mr. G vient pour une toux depuis 3 semaines..."
    scenario_context: str
    
    # Prompt pour le role-play patient (optionnel, seulement si station_type le nécessite)
    # Pour patient_interview, diagnosis_announcement, mixed : obligatoire
    # Pour exam_analysis, procedure : non utilisé (pas de chat en temps réel)
    patient_prompt: Optional[str] = None
    
    # Résultats d'examen clinique communiqués par l'examinateur à la demande de l'étudiant
    # (outil `resultat_examen_clinique` de l'agent patient).
    # Format : [{"id": "constantes", "label": "Constantes vitales", "findings": "..."}]
    exam_findings: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON, nullable=True))
    
    # Voix du patient en mode vocal : chemin relatif au dépôt Hugging Face kyutai/tts-voices
    # (ex. "cml-tts/fr/12977_10625_000037-0001.wav"). None = voix par défaut du serveur.
    voice_id: Optional[str] = None

    # Fiche de cas structurée en cours d'édition (case_sheet.CaseSheet). Les champs
    # d'exécution ci-dessus en sont compilés à chaque publication (voir case_versions).
    sheet: Optional[dict] = Field(default=None, sa_column=Column(JSON, nullable=True))
    
    duration_seconds: int
    
    edn_items: List["EDNItem"] = Relationship(
        back_populates="cases", link_model=CaseEdnLink
    )
    
    disciplines : List["DisciplineItem"] = Relationship(
        back_populates="cases", link_model=CaseDisciplineLink
    )
    
    evaluation: Optional["EvaluationGrid"] = Relationship(back_populates="case")
    attachments: List["Attachment"] = Relationship(back_populates="case")
    
class EDNItem(SQLModel, table=True):
    __tablename__ = "edn_items"
    
    id:  Optional[int] = Field(default=None, primary_key=True)
    number: int = Field(index=True, unique=True)
    title: str = Field(index=True, unique=True)
    
    disciplines: List["DisciplineItem"] = Relationship(
        back_populates="edn_items", link_model=EdnDisciplineLink
    )
    
    cases: List["ClinicalCase"] = Relationship(
        back_populates="edn_items", link_model=CaseEdnLink
    )

class DisciplineItem(SQLModel, table=True):
    __tablename__ = "disciplines"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: Discipline = Field(unique=True)
    cases: List["ClinicalCase"] = Relationship(back_populates="disciplines", link_model=CaseDisciplineLink)
    edn_items: List["EDNItem"] = Relationship(back_populates="disciplines", link_model=EdnDisciplineLink)

class User(SQLModel, table=True):
    __tablename__ = "users"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    hashed_password: str = Field()
    full_name: Optional[str] = None
    email: Optional[str] = Field(default=None, index=True, unique=True)
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    
    role: UserRole = Field(default=UserRole.student, index=True)
    
class Role(SQLModel, table=True):
    __tablename__ = "roles"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: UserRole = Field(index=True, unique=True)
    description: Optional[str] = None
    
class Attempts(SQLModel, table=True):
    __tablename__ = "attempts"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    case_id: int = Field(foreign_key="clinical_cases.id")
    created_at: datetime | None = Field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None  # Heure de fin du temps imparti
    completed_at: Optional[datetime] = None  # Timestamp de finalisation
    score: Optional[float] = None
    is_completed: bool = Field(default=False)
    # Version du cas jouée (publiée, ou brouillon testé par un enseignant)
    case_version_id: Optional[int] = Field(default=None, foreign_key="case_versions.id")
    # Tentative de test d'un enseignant : exclue des statistiques
    is_test: bool = Field(default=False)
    
class Message(SQLModel, table=True):
    __tablename__ = "chat_messages"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    attempt_id: UUID = Field(foreign_key="attempts.id")
    role: ChatRole = Field(index=True)
    content: str
    attachment_id: Optional[UUID] = Field(foreign_key="attachments.id", default=None)
    created_at: datetime | None = Field(default_factory=datetime.now)
    is_active: bool = Field(default=True)
    # "text" (saisi au clavier) ou "voice" (dit à l'oral / prononcé par la synthèse vocale)
    modality: str = Field(default="text")
    # Réplique du patient coupée par l'étudiant (faute de communication en ECOS) :
    # "voice" (parle par-dessus), "push_to_talk" (reprend le micro), "button" (coupe la voix)
    interrupted_by: Optional[str] = None
    # Ce que le patient a réellement prononcé avant d'être coupé (content = réplique complète)
    spoken_content: Optional[str] = None
    
    
class CaseVersion(SQLModel, table=True):
    """Version figée d'un cas : ce qui a été joué et noté ne change plus.

    status = "published" : version proposée aux étudiants (la plus récente fait foi)
    status = "test"      : brouillon testé par un enseignant avant publication
    """
    __tablename__ = "case_versions"

    id: Optional[int] = Field(default=None, primary_key=True)
    case_id: int = Field(foreign_key="clinical_cases.id", index=True)
    version: int
    status: str = Field(default="published", index=True)
    sheet: dict = Field(sa_column=Column(JSON, nullable=False))
    title: str
    student_instructions: str
    scenario_context: str
    patient_prompt: str
    duration_seconds: int
    exam_findings: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON, nullable=True))
    grid_items: List[dict] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    total_points: float = 0
    voice_id: Optional[str] = None
    created_by: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.now)


# ==================== CORPUS OFFICIEL (assistant de création de cas) ====================

class CorpusSource(SQLModel, table=True):
    """Source documentaire et ses droits d'usage."""
    __tablename__ = "corpus_sources"

    id: str = Field(primary_key=True)          # ex. "sfc-cardio-dfasm"
    title: str
    publisher: str
    license_note: str                           # accord obtenu, conditions d'usage
    homepage: Optional[str] = None
    retrieved_at: Optional[datetime] = None


class CorpusChunk(SQLModel, table=True):
    """Passage d'un cours, rattaché à un item R2C, une section et un rang."""
    __tablename__ = "corpus_chunks"

    id: Optional[int] = Field(default=None, primary_key=True)
    source_id: str = Field(foreign_key="corpus_sources.id", index=True)
    url: str
    item_number: Optional[int] = Field(default=None, index=True)
    chapter_title: str
    section: str                                 # chemin des titres : « IV. Diagnostic > A. Présentation clinique »
    rank: Optional[str] = None                   # "A" | "B" | "C"
    kind: str = Field(default="cours", index=True)  # cours | objectif | points_cles | vignette
    position: int = 0
    text: str


class StartingSituation(SQLModel, table=True):
    """Situation de départ (SDD) des ECOS."""
    __tablename__ = "starting_situations"

    number: int = Field(primary_key=True)
    title: str


class ItemSituationLink(SQLModel, table=True):
    """Situations de départ associées à un item R2C (d'après le corpus)."""
    __tablename__ = "item_situation_links"

    item_number: int = Field(primary_key=True)
    situation_number: int = Field(primary_key=True)


class ModerationEvent(SQLModel, table=True):
    """Trace des écarts de l'étudiant (insultes, hors sujet, tentative de triche...).

    source = "arbiter"       : détecté par le LLM arbitre (message bloqué ou ton agressif)
    source = "patient_agent" : signalé par le patient via l'outil `signaler_hors_cadre`
    action = "blocked"       : message refusé, absent du transcript
    action = "flagged"       : message conservé dans le transcript mais signalé
    """
    __tablename__ = "moderation_events"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    attempt_id: UUID = Field(foreign_key="attempts.id", index=True)
    message_id: Optional[UUID] = Field(default=None, foreign_key="chat_messages.id")
    source: str = Field(index=True)
    category: str = Field(index=True)
    severity: Optional[str] = None
    action: str
    detail: Optional[str] = None
    # Contenu du message étudiant (utile surtout pour les messages bloqués, absents du transcript)
    student_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class EvaluationGrid(SQLModel, table=True):
    __tablename__ = "evaluation_grids"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    case_id: int = Field(foreign_key="clinical_cases.id", unique=True, index=True)
    version: float
    total_points: int
    items: List[dict] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    is_active: bool = Field(default=True)  # Permet de désactiver une grille sans la supprimer
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    
    case: Optional["ClinicalCase"] = Relationship(back_populates="evaluation")
    
class Attachment(SQLModel, table=True):
    __tablename__ = "attachments"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    attempt_id: Optional[UUID] = Field(foreign_key="attempts.id", default=None)
    case_id: int = Field(foreign_key="clinical_cases.id", index=True)
    
    # Informations fichier
    filename: str  # Nom original du fichier
    stored_filename: str  # Nom unique sur le disque (UUID)
    display_name: str  # Nom affiché (ex: "Électrocardiogramme")
    description: Optional[str] = None  # Description pour le LLM
    
    kind: str = Field(index=True)  # image, video, document, audio, transcript
    mime_type: str = Field(index=True)
    size_bytes: Optional[int]
    
    # Chemins
    file_path: str  # Chemin relatif dans storage/
    file_url: str  # URL pour accès
    
    # Métadonnées
    uploaded_at: datetime = Field(default_factory=datetime.now)
    is_available_during_case: bool = Field(default=True)  # Disponible pendant l'examen ?
    trigger_keywords: Optional[str] = None  # Mots-clés pour détection automatique (séparés par ,)
    
    case: ClinicalCase = Relationship(back_populates="attachments")

class EvaluationResult(SQLModel, table=True):
    __tablename__ = "evaluation_results"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    attempt_id: UUID = Field(foreign_key="attempts.id", unique=True, index=True)
    case_id: int = Field(foreign_key="clinical_cases.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    
    # Résultat de l'évaluation au format JSON
    evaluation_data: dict = Field(sa_column=Column(JSON, nullable=False))
    
    # Champs dénormalisés pour analytics SQL
    points_obtained: float = Field(default=0.0, index=True)
    points_possible: float = Field(default=0.0, index=True)
    
    # Métadonnées
    created_at: datetime = Field(default_factory=datetime.now)
    evaluated_at: datetime = Field(default_factory=datetime.now)

class EvaluationItemResult(SQLModel, table=True):
    """Stockage individuel des résultats de chaque item d'évaluation pour analytics granulaires."""
    __tablename__ = "evaluation_item_results"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    evaluation_result_id: int = Field(foreign_key="evaluation_results.id", index=True)
    attempt_id: UUID = Field(foreign_key="attempts.id", index=True)
    case_id: int = Field(foreign_key="clinical_cases.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    
    # Identification de l'item
    edn_code: str = Field(index=True)  # Code EDN pour regroupement (ex: "EDN 197")
    item_name: str  # Nom de l'item évalué
    
    # Résultat
    points_obtained: float = Field(index=True)
    points_possible: float = Field(index=True)
    justification: str  # Justification avec citations du transcript
    
    # Métadonnées
    evaluated_at: datetime = Field(default_factory=datetime.now)
