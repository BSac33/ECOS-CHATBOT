/**
 * Client HTTP unique de l'application.
 *
 * - Base d'URL : VITE_API_URL, sinon « /api » (nginx et le proxy de dev retirent ce préfixe).
 * - Cookie JWT HttpOnly : toutes les requêtes partent avec credentials: 'include'.
 * - 401 : le gestionnaire installé par le routeur vide la session et renvoie vers /login.
 * - Délai maximal par AbortController (30 s par défaut).
 * - Erreurs : ApiError, avec un message en français (le `detail` de l'API s'il est un texte).
 */

export const API_BASE_URL: string = (import.meta.env.VITE_API_URL || '/api').replace(/\/+$/, '')

/**
 * Base des appels directs (flux SSE du chat, WebSocket du mode vocal, documents) :
 * la même API, sans le préfixe « /api » que nginx retire. En production, nginx les
 * sert sur des routes dédiées (/chat/attempts/, /attachments/) sans tampon ni délai court.
 */
export const DIRECT_BASE_URL: string = API_BASE_URL.replace(/\/api$/, '')

/** URL d'un appel REST (préfixe de l'API compris). */
export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`
}

/** URL d'un appel direct : flux SSE, WebSocket, téléchargement de documents. */
export function directUrl(path: string): string {
  return `${DIRECT_BASE_URL}${path}`
}

/** URL WebSocket (ws:// ou wss://) d'un appel direct, résolue par rapport à la page. */
export function websocketUrl(path: string, base: string = window.location.href): string {
  const url = new URL(directUrl(path), base)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.toString()
}

/** Document (ECG, imagerie...) affiché dans le chat ou l'atelier. */
export function attachmentUrl(attachmentId: string): string {
  return directUrl(`/attachments/download/${encodeURIComponent(attachmentId)}`)
}

export const DEFAULT_TIMEOUT_MS = 30_000
/** Correction automatique et assistant de l'atelier : appels au modèle, plus longs. */
export const LONG_TIMEOUT_MS = 240_000

export type ApiErrorKind = 'http' | 'timeout' | 'network' | 'aborted'

const STATUS_MESSAGES: Record<number, string> = {
  400: 'La requête est invalide.',
  401: 'Votre session a expiré. Reconnectez-vous.',
  403: "Vous n'avez pas accès à cette ressource.",
  404: 'Ressource introuvable.',
  408: 'Le temps de la station est écoulé.',
  409: 'Cette action est impossible dans l’état actuel.',
  410: 'Le temps de la station est écoulé.',
  413: 'Le fichier est trop volumineux.',
  422: 'Les données envoyées sont invalides.',
  429: 'Trop de requêtes : patientez quelques instants.',
  500: 'Erreur interne du serveur. Réessayez plus tard.',
  502: 'Le service est momentanément indisponible. Réessayez.',
  503: 'Le service est momentanément indisponible. Réessayez.',
  504: 'Le serveur a mis trop de temps à répondre. Réessayez.',
}

export const TIMEOUT_MESSAGE = 'Le serveur met trop de temps à répondre. Réessayez.'
export const NETWORK_MESSAGE = 'Impossible de joindre le serveur. Vérifiez votre connexion.'
export const ABORTED_MESSAGE = 'Requête annulée.'
export const UNEXPECTED_MESSAGE = 'Réponse inattendue du serveur. Réessayez.'

/** Message générique, en français, pour un code HTTP. */
export function statusMessage(status: number): string {
  const known = STATUS_MESSAGES[status]
  if (known) return known
  if (status >= 500) return 'Erreur du serveur. Réessayez plus tard.'
  return `La requête a échoué (code ${status}).`
}

/** `detail` de FastAPI : un texte, un objet {message} (atelier), ou une liste (validation). */
export function messageFromDetail(status: number, detail: unknown): string {
  if (typeof detail === 'string' && detail.trim()) return detail
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const message = (detail as { message?: unknown }).message
    if (typeof message === 'string' && message.trim()) return message
  }
  return statusMessage(status)
}

export class ApiError extends Error {
  readonly status: number
  readonly detail: unknown
  readonly kind: ApiErrorKind

  constructor(status: number, detail: unknown, kind: ApiErrorKind = 'http', message?: string) {
    super(message ?? messageFromDetail(status, detail))
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.kind = kind
  }
}

/** Message affichable pour n'importe quelle erreur attrapée. */
export function errorMessage(error: unknown, fallback = 'Une erreur est survenue. Réessayez.'): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error && error.message) return error.message
  return fallback
}

// ---------- Session expirée ----------

type UnauthorizedHandler = () => void
let unauthorizedHandler: UnauthorizedHandler | null = null

/** Installé par le routeur : vider le store d'authentification et aller sur /login. */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler
}

/** Pour les flux SSE / WebSocket, qui ne passent pas par request(). */
export function notifyUnauthorized(): void {
  unauthorizedHandler?.()
}

// ---------- Requête ----------

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  /** Corps JSON (sérialisé) */
  json?: unknown
  /** Corps déjà construit (FormData, URLSearchParams) : le navigateur fixe le Content-Type */
  body?: BodyInit
  headers?: Record<string, string>
  /** Délai maximal en millisecondes (défaut 30 s) */
  timeout?: number
  signal?: AbortSignal
  /** Ne pas rediriger vers /login sur 401 (connexion, vérification de session, mot de passe faux) */
  skipAuthRedirect?: boolean
  /** Format de la réponse (défaut : JSON, ou rien pour 204) */
  responseType?: 'json' | 'blob' | 'text'
}

async function readErrorDetail(response: Response): Promise<unknown> {
  const text = await response.text().catch(() => '')
  if (!text) return null
  try {
    const body = JSON.parse(text) as { detail?: unknown }
    return body && typeof body === 'object' && 'detail' in body ? body.detail : null
  } catch {
    return null
  }
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', json, body, timeout = DEFAULT_TIMEOUT_MS, signal, skipAuthRedirect = false } = options
  const headers: Record<string, string> = { Accept: 'application/json', ...(options.headers ?? {}) }
  let payload: BodyInit | undefined = body
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(json)
  }

  const controller = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeout)
  const onAbort = () => controller.abort()
  if (signal) {
    if (signal.aborted) controller.abort()
    else signal.addEventListener('abort', onAbort, { once: true })
  }

  try {
    let response: Response
    try {
      response = await fetch(apiUrl(path), {
        method,
        headers,
        body: payload,
        credentials: 'include',
        signal: controller.signal,
      })
    } catch {
      if (timedOut) throw new ApiError(0, null, 'timeout', TIMEOUT_MESSAGE)
      if (controller.signal.aborted) throw new ApiError(0, null, 'aborted', ABORTED_MESSAGE)
      throw new ApiError(0, null, 'network', NETWORK_MESSAGE)
    }

    if (!response.ok) {
      const detail = await readErrorDetail(response)
      if (response.status === 401 && !skipAuthRedirect) notifyUnauthorized()
      throw new ApiError(response.status, detail)
    }

    if (response.status === 204) return undefined as T
    switch (options.responseType) {
      case 'blob':
        return (await response.blob()) as T
      case 'text':
        return (await response.text()) as T
      default: {
        const text = await response.text()
        if (!text) return null as T
        try {
          return JSON.parse(text) as T
        } catch {
          throw new ApiError(response.status, null, 'http', UNEXPECTED_MESSAGE)
        }
      }
    }
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (timedOut) throw new ApiError(0, null, 'timeout', TIMEOUT_MESSAGE)
    throw new ApiError(0, null, 'network', NETWORK_MESSAGE)
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', onAbort)
  }
}

type Options = Omit<RequestOptions, 'method' | 'json'>

export const http = {
  get: <T>(path: string, options?: Options) => request<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, json?: unknown, options?: Options) => request<T>(path, { ...options, method: 'POST', json }),
  put: <T>(path: string, json?: unknown, options?: Options) => request<T>(path, { ...options, method: 'PUT', json }),
  patch: <T>(path: string, json?: unknown, options?: Options) => request<T>(path, { ...options, method: 'PATCH', json }),
  delete: <T>(path: string, json?: unknown, options?: Options) => request<T>(path, { ...options, method: 'DELETE', json }),
}
