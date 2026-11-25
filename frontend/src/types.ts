// Types partagés de l'application (miroir des réponses de l'API)

// ---------- Comptes ----------

export type UserRole = 'student' | 'teacher' | 'admin'

export interface User {
  id: number
  username: string
  full_name: string | null
  email: string | null
  is_active: boolean
  role: UserRole | string
}

export const ROLE_LABELS: Record<string, string> = {
  student: 'Étudiant',
  teacher: 'Enseignant',
  admin: 'Administrateur',
}

// ---------- Stations ----------

export interface ClinicalCase {
  id: number
  title: string
  station_type: string
  duration_seconds: number
  status: string
  disciplines: string[]
  edn_codes: number[]
  has_evaluation_grid: boolean
}

export interface CaseInstructions {
  case_id: number
  title: string
  student_instructions: string
  duration_seconds: number
  station_type: string
}

export interface Attempt {
  id: string
  case_id: number
  created_at: string
  is_completed: boolean
}

export interface TimeRemaining {
  seconds_remaining: number | null
  is_expired: boolean
  expires_at?: string | null
  message?: string
}

export type Interlocutor = 'patient' | 'professionnel' | 'aucun'

/** GET /chat/attempts/{id}/case-info */
export interface AttemptCaseInfo {
  case_id: number
  title: string
  station_type: string
  duration_seconds: number
  is_test: boolean
  interlocutor: Interlocutor
  interlocutor_label: string
  domain: string | null
  /** Énoncé remis à l'étudiant (volet des stations sans interlocuteur) */
  student_instructions?: string
}

export const STATION_TYPE_LABELS: Record<string, string> = {
  patient_interview: 'Interrogatoire patient',
  exam_analysis: "Analyse d'examens (radio, ECG, labo)",
  procedure: 'Démonstration de geste technique',
  diagnosis_announcement: 'Annonce de diagnostic',
  mixed: 'Station mixte (ex. : interrogatoire puis examen)',
}

// ---------- Chat ----------

export type ChatRole = 'student' | 'patient' | 'system' | 'examiner'
export type InterruptionReason = 'voice' | 'push_to_talk' | 'button'

/** Message de la conversation (GET /messages, ou ajouté en direct pendant la station). */
export interface ChatMessage {
  id: string
  role: ChatRole
  content: string
  created_at: string
  attachment_id?: string | null
  attachment_mime_type?: string | null
  /** « text » ou « voice » */
  modality?: string | null
  /** Message étudiant refusé par les garde-fous (non transmis au patient) */
  blocked?: boolean
  /** Transcription vocale en cours */
  pending?: boolean
  /** Message étudiant qui n'a pas pu être envoyé (réseau, serveur) : « Réessayer » */
  failed?: boolean
  /** Identifiant en base (les messages ajoutés en direct ont un identifiant temporaire) */
  server_id?: string | null
  /** Réplique du patient coupée par l'étudiant */
  interrupted_by?: InterruptionReason | string | null
  spoken_content?: string | null
}

/** Information transmise par l'examinateur (résultat d'examen, document affiché) */
export interface ExaminerNote {
  kind: 'exam_findings' | 'document'
  title: string
  content: string
  attachment_id?: string | null
  file_url?: string | null
  mime_type?: string | null
}

/** Fin d'un tour (ChatOut) : réponse complète telle qu'enregistrée */
export interface ChatResponse {
  patient_reply: string
  attachments?: string[]
  blocked?: boolean
  examiner_notes?: ExaminerNote[]
  patient_message_id?: string | null
  /** Station sans interlocuteur : la parole de l'étudiant est enregistrée, personne ne répond */
  silent?: boolean
}

// ---------- Correction ----------

export interface EvaluationItemResult {
  item_id: string
  criterion: string
  points_awarded: number
  points_possible: number
  is_validated: boolean
  justification: string
  /** Passage de la transcription sur lequel s'appuie la correction */
  citation?: string | null
  /** false : la citation n'a pas été retrouvée telle quelle dans la transcription */
  citation_found?: boolean | null
  /** Points ou justification modifiés par un enseignant */
  overridden?: boolean | null
}

export interface ScaleRating {
  scale_id: string
  label: string
  observable: boolean
  level: number | null
  level_name: string | null
  justification: string | null
}

export interface GlobalPerformance {
  label: string
  level: number | null
  level_name: string | null
  justification: string | null
}

/** EvaluationResultOut */
export interface EvaluationResult {
  items: EvaluationItemResult[]
  total_score: number
  total_possible: number
  percentage: number
  general_feedback: string
  items_score?: number | null
  items_possible?: number | null
  scales?: ScaleRating[]
  global_performance?: GlobalPerformance | null
  attitude_weight?: number | null
  score_20?: number | null
  reviewed_by?: string | null
  reviewed_at?: string | null
  needs_review?: boolean | null
}

export interface EvaluationEnvelope {
  evaluation: EvaluationResult
}

export interface TranscriptEntry {
  id: string
  role: ChatRole
  content: string
  modality?: string | null
  interrupted_by?: string | null
  spoken_content?: string | null
  timestamp: string | null
}

/** Réplique du patient coupée par l'étudiant (consultation orale) */
export interface Interruption {
  message_id: string
  reason: InterruptionReason | string
  spoken_content: string
  full_reply: string
}

/** GET /evaluation/attempts/{id}/transcript */
export interface AttemptTranscript {
  attempt_id: string
  case_id: number
  is_completed: boolean
  transcript: TranscriptEntry[]
  interruptions: Interruption[]
}

/** GET /evaluation/attempts/{id}/teaching */
export interface Teaching {
  title: string | null
  source: string | null
  objectives: string[]
  key_points: { label: string; text: string }[]
  model_script: string
  comments: string
}

// ---------- Relecture des corrections (enseignants) ----------

/** GET /authoring/cases/{case_id}/attempts */
export interface CaseAttemptRow {
  attempt_id: string
  username: string
  full_name: string | null
  is_test: boolean
  started_at: string
  completed_at: string | null
  evaluated: boolean
  score_20: number | null
  reviewed: boolean
}

/** GET /evaluation/attempts/{id}/review */
export interface AttemptReview {
  attempt_id: string
  case_id: number
  case_title: string
  username: string
  full_name: string | null
  completed_at: string | null
  transcript: TranscriptEntry[]
  evaluation: EvaluationResult | null
}
