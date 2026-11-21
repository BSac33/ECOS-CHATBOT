import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import {
  ApiError, apiUrl, attachmentUrl, directUrl, http, messageFromDetail, NETWORK_MESSAGE, setUnauthorizedHandler,
  TIMEOUT_MESSAGE, websocketUrl,
} from './http'
import { apiService } from './api'
import { createAppRouter, safeRedirect } from '../router'
import { useAuthStore } from '../stores/auth'

function json(status: number, body: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const fetchMock = vi.fn<typeof fetch>()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthorizedHandler(null)
})

describe('URL', () => {
  it("préfixe /api pour l'API, appels directs sans préfixe", () => {
    expect(apiUrl('/chat/attempts')).toBe('/api/chat/attempts')
    expect(directUrl('/chat/attempts/1/chat/stream')).toBe('/chat/attempts/1/chat/stream')
    expect(attachmentUrl('abc')).toBe('/attachments/download/abc')
    expect(websocketUrl('/chat/attempts/1/voice', 'https://ecos.example.fr/chat/1'))
      .toBe('wss://ecos.example.fr/chat/attempts/1/voice')
  })
})

describe('requêtes', () => {
  it('envoie le cookie, le JSON et renvoie la réponse', async () => {
    fetchMock.mockResolvedValueOnce(json(200, { id: 'a1' }))
    await expect(http.post('/chat/attempts', { case_id: 3 })).resolves.toEqual({ id: 'a1' })
    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toBe('/api/chat/attempts')
    expect(init?.credentials).toBe('include')
    expect(init?.method).toBe('POST')
    expect(init?.body).toBe('{"case_id":3}')
    expect((init?.headers as Record<string, string>)['Content-Type']).toBe('application/json')
  })

  it('renvoie undefined pour une réponse 204', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }))
    await expect(http.delete('/api/users/me', { password: 'x' })).resolves.toBeUndefined()
  })
})

describe("messages d'erreur en français", () => {
  it('affiche le detail texte de l’API', async () => {
    fetchMock.mockResolvedValueOnce(json(503, { detail: "La correction automatique n'a pas abouti." }))
    const error = await http.post('/evaluation/attempts/1/evaluate').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(503)
    expect((error as ApiError).message).toBe("La correction automatique n'a pas abouti.")
  })

  it('remplace un detail non textuel (validation 422) par un message générique', async () => {
    fetchMock.mockResolvedValueOnce(json(422, { detail: [{ loc: ['body', 'message'], msg: 'too long' }] }))
    await expect(http.post('/x')).rejects.toThrow('Les données envoyées sont invalides.')
  })

  it('utilise le message des objets {message} (atelier) et un message par code sinon', () => {
    expect(messageFromDetail(422, { message: 'Corrigez les erreurs.', issues: [] })).toBe('Corrigez les erreurs.')
    expect(messageFromDetail(404, null)).toBe('Ressource introuvable.')
    expect(messageFromDetail(410, null)).toBe('Le temps de la station est écoulé.')
    expect(messageFromDetail(418, undefined)).toBe('La requête a échoué (code 418).')
  })

  it('signale un serveur injoignable', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    const error = await http.get('/api/cases').catch((e: unknown) => e) as ApiError
    expect(error.kind).toBe('network')
    expect(error.message).toBe(NETWORK_MESSAGE)
  })
})

describe('délai maximal', () => {
  it('abandonne la requête après le délai (AbortController)', async () => {
    let signal: AbortSignal | undefined
    fetchMock.mockImplementationOnce((_url, init) => new Promise((_resolve, reject) => {
      signal = init?.signal ?? undefined
      signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
    }))
    const error = await http.get('/api/cases', { timeout: 20 }).catch((e: unknown) => e) as ApiError
    expect(error).toBeInstanceOf(ApiError)
    expect(error.kind).toBe('timeout')
    expect(error.message).toBe(TIMEOUT_MESSAGE)
    expect(signal?.aborted).toBe(true)
  })
})

describe('session expirée (401)', () => {
  const user = { id: 1, username: 'etu1', full_name: 'Alice Martin', email: null, is_active: true, role: 'student' }

  it('vide la session et redirige vers /login?redirect=<page courante>', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const router = createAppRouter(pinia, createMemoryHistory())
    fetchMock.mockImplementation(async (input) => {
      if (String(input) === '/api/api/users/me') return json(200, user)
      return json(401, { detail: 'Not authenticated' })
    })

    await router.push('/compte?onglet=1')
    expect(router.currentRoute.value.name).toBe('account')
    const auth = useAuthStore(pinia)
    expect(auth.user?.full_name).toBe('Alice Martin')

    await expect(apiService.getMessages('abc')).rejects.toMatchObject({ status: 401 })
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('login'))
    expect(router.currentRoute.value.query.redirect).toBe('/compte?onglet=1')
    expect(auth.user).toBeNull()
  })

  it('ne redirige pas pour la vérification de session ni la connexion', async () => {
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    fetchMock.mockImplementation(async () => json(401, { detail: 'Identifiants incorrects' }))
    await expect(apiService.getCurrentUser()).rejects.toMatchObject({ status: 401 })
    await expect(apiService.login({ username: 'a', password: 'b' })).rejects.toThrow('Identifiants incorrects')
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it("n'accepte que des chemins internes au retour de connexion", () => {
    expect(safeRedirect('/chat/abc')).toBe('/chat/abc')
    expect(safeRedirect('https://exemple.org')).toBe('/')
    expect(safeRedirect('//exemple.org')).toBe('/')
    expect(safeRedirect('/login?redirect=/x')).toBe('/')
    expect(safeRedirect(undefined)).toBe('/')
  })
})
