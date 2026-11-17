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

export interface StationInfo {
  title: string
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

export interface CaseSheet {
  schema_version: number
  station: StationInfo
  patient: PatientProfile
  facts: Fact[]
  never_says: string[]
  exam_findings: ExamFindingEntry[]
  correction: { expected_diagnosis: string; expected_management: string; grid: GridItem[] }
}

export type IssueLevel = 'erreur' | 'attention' | 'conseil'
export interface Issue { level: IssueLevel; field: string; message: string }

export interface VersionOut { id: number; version: number; status: 'published' | 'test'; created_at: string }

export interface CaseDetail {
  id: number
  status: string
  sheet: CaseSheet | null
  legacy: boolean
  preview: {
    patient_prompt: string
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
  test: (id: number) => call<{ attempt_id: string; version_id: number }>(`/cases/${id}/test`, { method: 'POST' }),
  assist: (id: number, task: AssistTask, sheet: CaseSheet, instructions = '') =>
    call<Proposal>(`/cases/${id}/assist`, { method: 'POST', body: JSON.stringify({ task, sheet, instructions }) }),
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
