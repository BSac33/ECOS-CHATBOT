// Atelier de création de cas : types de la fiche (miroir de case_sheet.py) et appels /authoring

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'

export type FactCategory =
  | 'motif' | 'histoire' | 'symptome' | 'signe_negatif' | 'antecedent'
  | 'traitement' | 'allergie' | 'mode_de_vie' | 'contexte' | 'autre'

export const CATEGORY_LABELS: Record<FactCategory, string> = {
  motif: 'Motif de consultation',
  histoire: 'Histoire de la maladie',
  symptome: 'Signes associés',
  signe_negatif: 'Ce que le patient n’a pas',
  antecedent: 'Antécédents',
  traitement: 'Traitements',
  allergie: 'Allergies',
  mode_de_vie: 'Mode de vie',
  contexte: 'Contexte personnel et social',
  autre: 'Autre',
}
export const CATEGORY_ORDER = Object.keys(CATEGORY_LABELS) as FactCategory[]

export interface SourceRef { label: string; url?: string | null; chunk_id?: number | null }

export interface Fact {
  id: string
  category: FactCategory
  label: string
  patient_words: string
  disclosure: 'spontane' | 'sur_question'
  asked_about: string
  generated: boolean
  sources: SourceRef[]
}

export interface Reaction { when: string; then: string; generated: boolean }

export interface PatientProfile {
  first_name: string
  last_name: string
  age: number | null
  sex: 'femme' | 'homme' | 'autre'
  occupation: string
  living_situation: string
  personality: string
  emotional_state: string
  language_register: 'courant' | 'familier' | 'soutenu' | 'simple'
  concerns: string[]
  spontaneous_questions: string[]
  reactions: Reaction[]
}

export type Domain =
  | 'entretien_interrogatoire' | 'examen_clinique' | 'synthese_paraclinique' | 'strategie_diagnostique'
  | 'strategie_prise_en_charge' | 'education_prevention' | 'annonce_information' | 'urgence_vitale'
  | 'communication_interprofessionnelle' | 'iconographie' | 'procedure'

export const DOMAIN_LABELS: Record<Domain, string> = {
  entretien_interrogatoire: 'Entretien / interrogatoire',
  examen_clinique: 'Examen clinique',
  synthese_paraclinique: "Synthèse de résultats d'examens paracliniques",
  strategie_diagnostique: 'Stratégie diagnostique',
  strategie_prise_en_charge: 'Stratégie pertinente de la prise en charge',
  education_prevention: 'Éducation / prévention',
  annonce_information: 'Annonce / information du patient',
  urgence_vitale: 'Urgence vitale',
  communication_interprofessionnelle: 'Communication interprofessionnelle',
  iconographie: 'Iconographie',
  procedure: 'Procédure',
}

/** Échelles d'attitude des ECOS nationaux (cotées de 0 à 4) */
export const STANDARD_SCALES: Record<string, string> = {
  ecouter: 'Aptitude à écouter',
  renseigner: 'Aptitude à fournir des renseignements au patient / aux aidants',
  structurer_interrogatoire: "Aptitude à structurer l'interrogatoire",
  questionner: 'Aptitude à questionner',
  procedure: 'Aptitude à réaliser un geste / une procédure',
  planifier_soins: 'Aptitude à planifier les soins',
  proposer_prise_en_charge: 'Aptitude à proposer une prise en charge',
  cooperer: 'Aptitude à coopérer avec les pairs',
  synthese: 'Aptitude à faire la synthèse des données',
  structurer_examen: "Aptitude à structurer l'examen clinique",
  mener_examen: "Aptitude à mener l'examen clinique",
  non_verbale: 'Communication non verbale',
  communication_pairs: 'Communication avec les pairs',
}
export const LEVEL_NAMES = ['inacceptable', 'insuffisante', 'suffisante', 'satisfaisante', 'remarquable']

export interface StationDocument { id: string; label: string; attachment_id: string | null }

export interface StationInfo {
  title: string
  domain: Domain
  interlocutor: 'patient' | 'aucun'
  documents: StationDocument[]
  source: string
  station_type: string
  duration_minutes: number
  setting: string
  student_role: string
  student_instructions: string
  edn_items: number[]
  starting_situations: number[]
  voice_id: string | null
}

export interface ExamFindingEntry { id: string; label: string; findings: string; generated: boolean }

export interface GridItem {
  id: string
  criterion: string
  points: number
  description: string
  fact_ids: string[]
  generated: boolean
  sources: SourceRef[]
}

export interface AttitudeScale { id: string; label: string; levels: string[]; observable: boolean }

export interface TeachingContent {
  objectives: string[]
  key_points: { label: string; text: string }[]
  model_script: string
  comments: string
}

export interface CaseSheet {
  schema_version: number
  station: StationInfo
  patient: PatientProfile
  facts: Fact[]
  never_says: string[]
  exam_findings: ExamFindingEntry[]
  correction: {
    expected_diagnosis: string
    expected_management: string
    grid: GridItem[]
    scales: AttitudeScale[]
    global_rating: boolean
    attitude_weight: number
    teaching: TeachingContent
  }
}

export type IssueLevel = 'erreur' | 'attention' | 'conseil'
export interface Issue { level: IssueLevel; field: string; message: string }

export interface VersionOut { id: number; version: number; status: 'published' | 'test'; created_at: string }

export type ReviewStatus = 'a_relire' | 'relue' | null

export interface ReviewInfo {
  status: ReviewStatus
  requested_at: string | null
  reviewer: string | null
  reviewed_at: string | null
  note: string | null
  changed_since_review: boolean
}

export interface CaseDetail {
  id: number
  status: string
  can_edit: boolean          // auteur ou administrateur ; sinon lecture seule (relecteur)
  can_review: boolean
  author: string
  review: ReviewInfo
  sheet: CaseSheet | null
  legacy: boolean
  preview: {
    patient_prompt: string | null
    scenario_context: string
    student_instructions: string
    grid_items: { id: string; criterion: string; points: number; description: string }[]
    total_points: number
  } | null
  issues: Issue[]
  versions: VersionOut[]
}

export interface CaseSummary {
  id: number
  title: string
  status: string
  latest_version: number | null
  errors: number
  warnings: number
  owned: boolean
  author: string
  review_status: ReviewStatus
}

export type AssistTask = 'interrogatoire' | 'negatifs' | 'langage' | 'personnage' | 'grille' | 'examen'

export interface Proposal {
  task: AssistTask
  title: string
  facts: Fact[]
  rewrites: { fact_id: string; before: string; after: string }[]
  persona: {
    personality: string
    emotional_state: string
    concerns: string[]
    spontaneous_questions: string[]
    reactions: Reaction[]
  } | null
  grid: GridItem[]
  exam_findings: ExamFindingEntry[]
  sources: SourceRef[]
  notes: string[]
}

export interface CorpusHit {
  chunk_id: number
  label: string
  item_number: number | null
  section: string
  rank: string | null
  kind: string
  text: string
  url: string
  score: number
}

export interface ReferenceItem { number: number; title: string }
export interface ReferenceSituation { number: number; title: string; linked: boolean }

/** Erreur d'API : `detail` peut être un texte ou un objet ({message, issues}). */
export class ApiError extends Error {
  status: number
  detail: any
  constructor(status: number, detail: any) {
    super(typeof detail === 'string' ? detail : detail?.message || `Erreur ${status}`)
    this.status = status
    this.detail = detail
  }
}

async function call<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/authoring${endpoint}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers as Record<string, string> || {}) },
    credentials: 'include',
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: 'Erreur réseau' }))
    throw new ApiError(response.status, body.detail)
  }
  return response.json()
}

export const authoringApi = {
  listCases: () => call<CaseSummary[]>('/cases'),
  createCase: (title: string) => call<CaseDetail>('/cases', { method: 'POST', body: JSON.stringify({ title }) }),
  getCase: (id: number) => call<CaseDetail>(`/cases/${id}`),
  saveSheet: (id: number, sheet: CaseSheet) =>
    call<CaseDetail>(`/cases/${id}/sheet`, { method: 'PUT', body: JSON.stringify(sheet) }),
  publish: (id: number) =>
    call<{ version: VersionOut; issues: Issue[] }>(`/cases/${id}/publish`, { method: 'POST' }),
  requestReview: (id: number) => call<CaseDetail>(`/cases/${id}/review/request`, { method: 'POST' }),
  clearReview: (id: number) => call<CaseDetail>(`/cases/${id}/review`, { method: 'DELETE' }),
  markReviewed: (id: number, note: string) =>
    call<CaseDetail>(`/cases/${id}/review`, { method: 'POST', body: JSON.stringify({ note }) }),
  test: (id: number) => call<{ attempt_id: string; version_id: number }>(`/cases/${id}/test`, { method: 'POST' }),
  assist: (id: number, task: AssistTask, sheet: CaseSheet, instructions = '') =>
    call<Proposal>(`/cases/${id}/assist`, { method: 'POST', body: JSON.stringify({ task, sheet, instructions }) }),
  uploadDocument: async (id: number, file: File, label: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('label', label)
    const response = await fetch(`${API_BASE_URL}/authoring/cases/${id}/documents`, {
      method: 'POST', body: form, credentials: 'include',
    })
    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: 'Erreur réseau' }))
      throw new ApiError(response.status, body.detail)
    }
    return response.json() as Promise<{ attachment_id: string; filename: string; mime_type: string; url: string }>
  },
  items: () => call<ReferenceItem[]>('/reference/items'),
  situations: (items: number[]) =>
    call<ReferenceSituation[]>(`/reference/situations?items=${items.join(',')}`),
  searchCorpus: (q: string, items: number[]) =>
    call<CorpusHit[]>(`/corpus/search?q=${encodeURIComponent(q)}&items=${items.join(',')}&limit=8`),
}

/** Identifiant court, même format que le serveur (f_xxxxxxxx, g_xxxxxxxx). */
export function newId(prefix: 'f' | 'g'): string {
  const bytes = new Uint8Array(4)
  crypto.getRandomValues(bytes)
  return `${prefix}_${Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')}`
}

export function emptyFact(category: FactCategory): Fact {
  return {
    id: newId('f'), category, label: '', patient_words: '',
    disclosure: category === 'motif' ? 'spontane' : 'sur_question',
    asked_about: '', generated: false, sources: [],
  }
}

export function emptyGridItem(): GridItem {
  return { id: newId('g'), criterion: '', points: 1, description: '', fact_ids: [], generated: false, sources: [] }
}

export function isTeacher(user: { role?: string } | null | undefined): boolean {
  return user?.role === 'teacher' || user?.role === 'admin'
}

export function newDocumentId(): string {
  return newId('f').replace(/^f_/, 'd_')
}
