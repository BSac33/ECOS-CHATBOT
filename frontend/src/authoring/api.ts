// Atelier de création de cas : types de la fiche (miroir de case_sheet.py) et appels /authoring
import { http, LONG_TIMEOUT_MS, request } from '../services/http'
import type { User } from '../types'

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
  interlocutor: 'patient' | 'professionnel' | 'aucun'
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

const UPLOAD_TIMEOUT_MS = 120_000

/** Appels /authoring : passent par le client HTTP unique (erreurs en français, 401, délais). */
export const authoringApi = {
  listCases: () => http.get<CaseSummary[]>('/authoring/cases'),
  createCase: (title: string) => http.post<CaseDetail>('/authoring/cases', { title }),
  getCase: (id: number) => http.get<CaseDetail>(`/authoring/cases/${id}`),
  saveSheet: (id: number, sheet: CaseSheet) => http.put<CaseDetail>(`/authoring/cases/${id}/sheet`, sheet),
  publish: (id: number) => http.post<{ version: VersionOut; issues: Issue[] }>(`/authoring/cases/${id}/publish`),
  requestReview: (id: number) => http.post<CaseDetail>(`/authoring/cases/${id}/review/request`),
  clearReview: (id: number) => http.delete<CaseDetail>(`/authoring/cases/${id}/review`),
  markReviewed: (id: number, note: string) => http.post<CaseDetail>(`/authoring/cases/${id}/review`, { note }),
  test: (id: number) => http.post<{ attempt_id: string; version_id: number }>(`/authoring/cases/${id}/test`),
  /** Assistant « Générer » : appel au modèle, délai long */
  assist: (id: number, task: AssistTask, sheet: CaseSheet, instructions = '') =>
    http.post<Proposal>(`/authoring/cases/${id}/assist`, { task, sheet, instructions }, { timeout: LONG_TIMEOUT_MS }),
  uploadDocument: (id: number, file: File, label: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('label', label)
    return request<{ attachment_id: string; filename: string; mime_type: string; url: string }>(
      `/authoring/cases/${id}/documents`, { method: 'POST', body: form, timeout: UPLOAD_TIMEOUT_MS },
    )
  },
  items: () => http.get<ReferenceItem[]>('/authoring/reference/items'),
  situations: (items: number[]) =>
    http.get<ReferenceSituation[]>(`/authoring/reference/situations?items=${items.join(',')}`),
  searchCorpus: (q: string, items: number[]) =>
    http.get<CorpusHit[]>(`/authoring/corpus/search?q=${encodeURIComponent(q)}&items=${items.join(',')}&limit=8`),
}

/** Lien externe affichable : seulement http(s) (jamais javascript:, data:...). */
export function safeExternalUrl(url: string | null | undefined): string | null {
  const value = url?.trim()
  if (!value || !/^https?:\/\//i.test(value)) return null
  try {
    const parsed = new URL(value)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : null
  } catch {
    return null
  }
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

export function isTeacher(user: Pick<User, 'role'> | null | undefined): boolean {
  return user?.role === 'teacher' || user?.role === 'admin'
}

export function newDocumentId(): string {
  return newId('f').replace(/^f_/, 'd_')
}
