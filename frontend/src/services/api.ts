// Appels à l'API (étudiants, compte, correction, relecture) : tous passent par le client unique http.ts
import { http, LONG_TIMEOUT_MS, request } from './http'
import type {
  Attempt, AttemptCaseInfo, AttemptReview, AttemptTranscript, CaseAttemptRow, CaseInstructions, ChatMessage,
  ClinicalCase, EvaluationEnvelope, Teaching, TimeRemaining, User,
} from '../types'

export interface LoginCredentials {
  username: string
  password: string
}

const attempt = (id: string) => `/chat/attempts/${encodeURIComponent(id)}`
const evaluation = (id: string) => `/evaluation/attempts/${encodeURIComponent(id)}`

export const apiService = {
  // ---------- Session ----------

  /** POST /auth/token (formulaire OAuth2) : le serveur pose le cookie HttpOnly. */
  login(credentials: LoginCredentials): Promise<{ message: string }> {
    const form = new URLSearchParams()
    form.append('username', credentials.username)
    form.append('password', credentials.password)
    // 401 = identifiants refusés : pas de redirection, le formulaire affiche l'erreur
    return request('/auth/token', { method: 'POST', body: form, skipAuthRedirect: true })
  },

  logout(): Promise<unknown> {
    return http.post('/auth/logout', undefined, { skipAuthRedirect: true })
  },

  /** Vérification de session : 401 signifie simplement « non connecté ». */
  getCurrentUser(): Promise<User> {
    return http.get<User>('/api/users/me', { skipAuthRedirect: true })
  },

  // ---------- Compte ----------

  /** Export RGPD : le fichier JSON tel que renvoyé par le serveur. */
  exportMyData(): Promise<Blob> {
    return http.get<Blob>('/api/users/me/export', { responseType: 'blob' })
  },

  /** Suppression du compte (mot de passe demandé). Un mot de passe faux ne déconnecte pas. */
  deleteMyAccount(password: string): Promise<void> {
    return http.delete<void>('/api/users/me', { password }, { skipAuthRedirect: true })
  },

  // ---------- Stations ----------

  getClinicalCases(filters?: { station_type?: string; discipline?: string }): Promise<ClinicalCase[]> {
    const params = new URLSearchParams()
    if (filters?.station_type) params.append('station_type', filters.station_type)
    if (filters?.discipline) params.append('discipline', filters.discipline)
    const query = params.toString()
    return http.get<ClinicalCase[]>(`/api/cases${query ? `?${query}` : ''}`)
  },

  getClinicalCase(id: number): Promise<ClinicalCase> {
    return http.get<ClinicalCase>(`/api/cases/${id}`)
  },

  getCaseInstructions(id: number): Promise<CaseInstructions> {
    return http.get<CaseInstructions>(`/api/cases/${id}/instructions`)
  },

  /** Tentative en cours pour ce cas (null s'il n'y en a pas). */
  getActiveAttempt(caseId: number): Promise<Attempt | null> {
    return http.get<Attempt | null>(`/chat/cases/${caseId}/active-attempt`)
  },

  createAttempt(caseId: number): Promise<Attempt> {
    return http.post<Attempt>('/chat/attempts', { case_id: caseId })
  },

  // ---------- Station en cours ----------

  getMessages(attemptId: string): Promise<ChatMessage[]> {
    return http.get<ChatMessage[]>(`${attempt(attemptId)}/messages`)
  },

  getAttemptCaseInfo(attemptId: string): Promise<AttemptCaseInfo> {
    return http.get<AttemptCaseInfo>(`${attempt(attemptId)}/case-info`)
  },

  getTimeRemaining(attemptId: string): Promise<TimeRemaining> {
    return http.get<TimeRemaining>(`${attempt(attemptId)}/time-remaining`)
  },

  finalizeAttempt(attemptId: string): Promise<{ status: string; completed_at: string }> {
    return http.post(`${attempt(attemptId)}/finalize`)
  },

  /** Station sans interlocuteur : réponse écrite rendue en une fois (termine la station). */
  submitAnswer(attemptId: string, answer: string): Promise<{ status: string; completed_at: string }> {
    return http.post(`${attempt(attemptId)}/answer`, { answer })
  },

  // ---------- Correction et débriefing ----------

  /** Correction (mise en cache côté serveur) : peut prendre plusieurs minutes. */
  evaluateAttempt(attemptId: string): Promise<EvaluationEnvelope> {
    return http.post<EvaluationEnvelope>(`${evaluation(attemptId)}/evaluate`, undefined, { timeout: LONG_TIMEOUT_MS })
  },

  getAttemptTeaching(attemptId: string): Promise<Teaching> {
    return http.get<Teaching>(`${evaluation(attemptId)}/teaching`)
  },

  getAttemptTranscript(attemptId: string): Promise<AttemptTranscript> {
    return http.get<AttemptTranscript>(`${evaluation(attemptId)}/transcript`)
  },

  // ---------- Relecture des corrections (enseignants) ----------

  getCaseAttempts(caseId: number): Promise<CaseAttemptRow[]> {
    return http.get<CaseAttemptRow[]>(`/authoring/cases/${caseId}/attempts`)
  },

  getAttemptReview(attemptId: string): Promise<AttemptReview> {
    return http.get<AttemptReview>(`${evaluation(attemptId)}/review`)
  },

  updateEvaluationItem(
    attemptId: string, itemId: string, change: { points_awarded: number; justification: string },
  ): Promise<EvaluationEnvelope> {
    return http.patch<EvaluationEnvelope>(`${evaluation(attemptId)}/items/${encodeURIComponent(itemId)}`, change)
  },

  reevaluateAttempt(attemptId: string): Promise<EvaluationEnvelope> {
    return http.post<EvaluationEnvelope>(`${evaluation(attemptId)}/reevaluate`, undefined, { timeout: LONG_TIMEOUT_MS })
  },
}
