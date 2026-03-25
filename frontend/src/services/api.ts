const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface AuthResponse {
  message: string;
}

export interface User {
  id: number;
  username: string;
  fullName: string;
  email: string;
  role: string;
}

export interface ClinicalCase {
  id: number;
  title: string;
  station_type: string;
  duration_seconds: number;
  status: string;
  student_instructions?: string;
  disciplines: string[];
  edn_codes: number[];
  has_evaluation_grid: boolean;
}

export interface Attempt {
  id: string;
  case_id: number;
  created_at: string;
  is_completed: boolean;
}

export interface TimeRemaining {
  seconds_remaining: number | null;
  is_expired: boolean;
  message?: string;
}

export interface CaseInstructions {
  case_id: number;
  title: string;
  student_instructions: string;
  duration_seconds: number;
  station_type: string;
}

export interface ExamAttachment {
  id: string;
  filename: string;
  display_name: string;
  kind: string;
  mime_type: string;
  size_bytes: number;
  file_url: string;
  uploaded_at: string;
  show_at_start: boolean;
}

export const stationType : Record<string, string> = {
    "patient_interview": "Interrogatoire patient",
    "exam_analysis": "Analyse d'examens (radio, ECG, labo)",
    "procedure": "Démonstration de geste technique",
    "diagnosis_announcement": "Annonce de diagnostic",
    "mixed": "Station mixte (ex: interrogatoire puis examen)"
};

/** Types de stations qui utilisent la vue réponse écrite (pas de chat patient) */
export const WRITTEN_EXAM_STATION_TYPES = ['exam_analysis', 'procedure'];

class ApiService {
  constructor() {
    // Le token est maintenant géré par les cookies HttpOnly
    // Plus besoin de localStorage
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string> || {}),
    };

    // credentials: 'include' permet d'envoyer les cookies avec chaque requête
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers,
      credentials: 'include',
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Erreur réseau' }));
      throw new Error(error.detail || `Erreur ${response.status}`);
    }

    return response.json();
  }

  async login(credentials: LoginCredentials): Promise<AuthResponse> {
    // OAuth2 attend form-data, pas JSON
    const formData = new URLSearchParams();
    formData.append('username', credentials.username);
    formData.append('password', credentials.password);

    const response = await fetch(`${API_BASE_URL}/auth/token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: formData,
      credentials: 'include', // Important: permet de recevoir et stocker le cookie
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Erreur réseau' }));
      throw new Error(error.detail || 'Échec de la connexion');
    }

    const data = await response.json();
    // Le token est maintenant dans un cookie HttpOnly, pas besoin de le stocker
    return data;
  }

  async getCurrentUser(): Promise<User> {
    return this.request<User>('/api/users/me');
  }

  async getClinicalCases(filters?: {
    station_type?: string;
    discipline?: string;
  }): Promise<ClinicalCase[]> {
    const params = new URLSearchParams();
    if (filters?.station_type) params.append('station_type', filters.station_type);
    if (filters?.discipline) params.append('discipline', filters.discipline);
    
    const queryString = params.toString();
    const endpoint = `/api/cases${queryString ? `?${queryString}` : ''}`;
    
    return this.request<ClinicalCase[]>(endpoint);
  }

  async getClinicalCase(id: number): Promise<ClinicalCase> {
    return this.request<ClinicalCase>(`/api/cases/${id}`);
  }

  async getCaseInstructions(id: number | null): Promise<CaseInstructions> {
    return this.request<CaseInstructions>(`/api/cases/${id}/instructions`);
  }

  async getActiveAttempt(caseId: number): Promise<Attempt | null> {
    try {
      return await this.request<Attempt>(`/chat/cases/${caseId}/active-attempt`);
    } catch (error) {
      // Si 404 ou autre erreur, pas d'attempt actif
      return null;
    }
  }

  async createAttempt(caseId: number): Promise<Attempt> {
    return this.request<Attempt>('/chat/attempts', {
      method: 'POST',
      body: JSON.stringify({ case_id: caseId }),
    });
  }

  async getTimeRemaining(attemptId: string): Promise<TimeRemaining> {
    return this.request<TimeRemaining>(`/chat/attempts/${attemptId}/time-remaining`);
  }

  async logout() {
    // Appel au backend pour supprimer le cookie
    try {
      await this.request('/auth/logout', {
        method: 'POST',
      });
    } catch (error) {
      console.error('Erreur lors de la déconnexion:', error);
    }
  }

  async getAttemptEvaluation(attemptId: string): Promise<any> {
    return this.request<any>(`/evaluation/attempts/${attemptId}/evaluate`, {
      method: 'POST',
    });
  }

  async getAttemptTranscript(attemptId: string): Promise<any> {
    return this.request<any>(`/evaluation/attempts/${attemptId}/transcript`);
  }

  async submitWrittenAnswer(attemptId: string, answer: string): Promise<any> {
    return this.request<any>(`/chat/attempts/${attemptId}/submit-answer`, {
      method: 'POST',
      body: JSON.stringify({ answer }),
    });
  }

  async getExamAttachments(attemptId: string): Promise<ExamAttachment[]> {
    return this.request<ExamAttachment[]>(`/chat/attempts/${attemptId}/exam-attachments`);
  }

  async finalizeAttempt(attemptId: string): Promise<any> {
    return this.request<any>(`/chat/attempts/${attemptId}/finalize`, {
      method: 'POST',
    });
  }
}

export const apiService = new ApiService();
