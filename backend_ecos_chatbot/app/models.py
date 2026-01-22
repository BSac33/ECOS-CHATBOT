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

class AttemptCreateIn(BaseModel):
    case_id: int

class AttemptOut(BaseModel):
    id: str  # UUID sérialisé
    case_id: int
    created_at: str
    is_completed: bool

class ChatIn(BaseModel):
    message: str

class ChatOut(BaseModel):
    patient_reply: str
    attachments: Optional[List[str]] = None  # UUIDs des fichiers attachés

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

class ClinicalCaseCreateIn(BaseModel):
    """Création d'un nouveau cas clinique"""
    title: str
    station_type: str  # "patient_interview" | "exam_analysis" | etc.
    student_instructions: str
    scenario_context: str
    patient_prompt: Optional[str] = None
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
    
class Message(SQLModel, table=True):
    __tablename__ = "chat_messages"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    attempt_id: UUID = Field(foreign_key="attempts.id")
    role: ChatRole = Field(index=True)
    content: str
    attachment_id: Optional[UUID] = Field(foreign_key="attachments.id", default=None)
    created_at: datetime | None = Field(default_factory=datetime.now)
    is_active: bool = Field(default=True)
    
    
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