// Tour de chat écrit en flux SSE : POST /chat/attempts/{id}/chat/stream (appel direct, sans /api)
import { ApiError, directUrl, NETWORK_MESSAGE, notifyUnauthorized } from './http'
import { readSSE, SSETimeoutError } from './sse'
import type { ChatResponse, ExaminerNote } from '../types'

/** Pas de réponse (ni octet) pendant ce délai : le tour échoue proprement. */
export const CHAT_IDLE_TIMEOUT_MS = 60_000
export const CHAT_TIMEOUT_MESSAGE = 'Pas de réponse depuis 60 secondes : le message n’a pas été transmis. Réessayez.'
export const INTERRUPTED_MESSAGE = 'La connexion a été interrompue avant la fin de la réponse. Réessayez.'
export const EXPIRED_MESSAGE = 'Le temps de la station est écoulé.'
export const TOO_LONG_MESSAGE = 'Message trop long : 2000 caractères au maximum.'
export const MAX_MESSAGE_LENGTH = 2000

export interface TurnHandlers {
  /** Réponse acceptée par le serveur : la réplique va arriver */
  onStart?: () => void
  onDelta: (text: string) => void
  onNote: (note: ExaminerNote) => void
}

export interface StreamOptions {
  signal?: AbortSignal
  idleTimeoutMs?: number
}

function chatError(status: number, detail: unknown): ApiError {
  // Tentative expirée : 410 (anciennement 408)
  if (status === 410 || status === 408) return new ApiError(status, detail, 'http', EXPIRED_MESSAGE)
  // Validation : message trop long ou vide
  if (status === 422 && typeof detail !== 'string') return new ApiError(status, detail, 'http', TOO_LONG_MESSAGE)
  return new ApiError(status, detail)
}

async function readDetail(response: Response): Promise<unknown> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    return body?.detail ?? null
  } catch {
    return null
  }
}

/**
 * Envoie un message et relaie la réplique au fil de l'eau.
 * Résout avec la réponse finale (événement « done ») ; rejette avec une ApiError en français.
 */
export async function streamChatTurn(
  attemptId: string,
  message: string,
  handlers: TurnHandlers,
  options: StreamOptions = {},
): Promise<ChatResponse> {
  const idleTimeoutMs = options.idleTimeoutMs ?? CHAT_IDLE_TIMEOUT_MS
  const controller = new AbortController()
  const onAbort = () => controller.abort()
  options.signal?.addEventListener('abort', onAbort, { once: true })

  // Délai d'attente des en-têtes de la réponse (le flux a ensuite son propre délai d'inactivité)
  let timedOut = false
  const headerTimer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, idleTimeoutMs)

  try {
    let response: Response
    try {
      response = await fetch(directUrl(`/chat/attempts/${encodeURIComponent(attemptId)}/chat/stream`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        credentials: 'include',
        body: JSON.stringify({ message }),
        signal: controller.signal,
      })
    } catch {
      if (timedOut) throw new ApiError(0, null, 'timeout', CHAT_TIMEOUT_MESSAGE)
      if (controller.signal.aborted) throw new ApiError(0, null, 'aborted', 'Envoi annulé.')
      throw new ApiError(0, null, 'network', NETWORK_MESSAGE)
    } finally {
      clearTimeout(headerTimer)
    }

    // Erreurs de validation (temps écoulé, tentative terminée...) : réponses HTTP classiques
    if (!response.ok) {
      const detail = await readDetail(response)
      if (response.status === 401) notifyUnauthorized()
      throw chatError(response.status, detail)
    }

    handlers.onStart?.()
    // Rempli par les événements (objet : TypeScript ne suit pas les affectations dans un rappel)
    const outcome: { final: ChatResponse | null; error: ApiError | null } = { final: null, error: null }
    try {
      await readSSE(response, ({ event, data }) => {
        switch (event) {
          case 'delta':
            handlers.onDelta((data as { text: string }).text)
            break
          case 'examiner_note':
            handlers.onNote(data as ExaminerNote)
            break
          case 'done':
            outcome.final = data as ChatResponse
            break
          case 'error': {
            const { status, message: text } = (data ?? {}) as { status?: number; message?: string }
            outcome.error = new ApiError(status ?? 502, text ?? null)
            break
          }
        }
      }, { idleTimeoutMs, timeoutMessage: CHAT_TIMEOUT_MESSAGE })
    } catch (error) {
      if (error instanceof SSETimeoutError) throw new ApiError(0, null, 'timeout', CHAT_TIMEOUT_MESSAGE)
      if (controller.signal.aborted) throw new ApiError(0, null, 'aborted', 'Envoi annulé.')
      throw new ApiError(0, null, 'network', INTERRUPTED_MESSAGE)
    }

    if (outcome.final) return outcome.final
    // Échec ou flux coupé : rien n'a été enregistré côté serveur
    throw outcome.error ?? new ApiError(0, null, 'network', INTERRUPTED_MESSAGE)
  } finally {
    options.signal?.removeEventListener('abort', onAbort)
  }
}
