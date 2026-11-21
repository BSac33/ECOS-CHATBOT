import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, setUnauthorizedHandler } from './http'
import { CHAT_TIMEOUT_MESSAGE, EXPIRED_MESSAGE, streamChatTurn, TOO_LONG_MESSAGE } from './chat'

const fetchMock = vi.fn<typeof fetch>()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthorizedHandler(null)
})

function sse(chunks: string[], { close = true } = {}): Response {
  const encoder = new TextEncoder()
  return new Response(new ReadableStream<Uint8Array>({
    start(controller) {
      chunks.forEach((c) => controller.enqueue(encoder.encode(c)))
      if (close) controller.close()
    },
  }), { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
}

const handlers = () => ({ onStart: vi.fn(), onDelta: vi.fn(), onNote: vi.fn() })

describe('streamChatTurn', () => {
  it('relaie les morceaux et renvoie la réponse finale', async () => {
    fetchMock.mockResolvedValueOnce(sse([
      'event: delta\ndata: {"text": "Bon"}\n\n',
      'event: delta\ndata: {"text": "jour"}\n\nevent: done\ndata: {"patient_reply": "Bonjour", "patient_message_id": "p1"}\n\n',
    ]))
    const h = handlers()
    const final = await streamChatTurn('a1', 'Bonjour', h)
    expect(final).toEqual({ patient_reply: 'Bonjour', patient_message_id: 'p1' })
    expect(h.onStart).toHaveBeenCalledOnce()
    expect(h.onDelta.mock.calls.map((c) => c[0]).join('')).toBe('Bonjour')
    expect(fetchMock.mock.calls[0]![0]).toBe('/chat/attempts/a1/chat/stream')
    expect(fetchMock.mock.calls[0]![1]?.credentials).toBe('include')
  })

  it('tentative expirée (410) : « Le temps de la station est écoulé. »', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Attempt expired' }), { status: 410 }))
    await expect(streamChatTurn('a1', 'Bonjour', handlers())).rejects.toMatchObject({ status: 410, message: EXPIRED_MESSAGE })
  })

  it('message trop long (422) : message en français', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: [{ msg: 'too long' }] }), { status: 422 }))
    await expect(streamChatTurn('a1', 'x'.repeat(2001), handlers())).rejects.toThrow(TOO_LONG_MESSAGE)
  })

  it("événement d'erreur du serveur : échec avec son message", async () => {
    fetchMock.mockResolvedValueOnce(sse(['event: error\ndata: {"status": 502, "message": "Le patient ne répond pas."}\n\n']))
    await expect(streamChatTurn('a1', 'Bonjour', handlers())).rejects.toMatchObject({ status: 502, message: 'Le patient ne répond pas.' })
  })

  it('flux coupé avant « done » : échec propre', async () => {
    fetchMock.mockResolvedValueOnce(sse(['event: delta\ndata: {"text": "Bon"}\n\n']))
    await expect(streamChatTurn('a1', 'Bonjour', handlers())).rejects.toBeInstanceOf(ApiError)
  })

  it('aucune réponse dans le délai : échec avec un message de délai', async () => {
    fetchMock.mockResolvedValueOnce(sse(['event: delta\ndata: {"text": "Bon"}\n\n'], { close: false }))
    await expect(streamChatTurn('a1', 'Bonjour', handlers(), { idleTimeoutMs: 30 }))
      .rejects.toMatchObject({ kind: 'timeout', message: CHAT_TIMEOUT_MESSAGE })
  })

  it('401 : prévient le gestionnaire de session expirée', async () => {
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Not authenticated' }), { status: 401 }))
    await expect(streamChatTurn('a1', 'Bonjour', handlers())).rejects.toMatchObject({ status: 401 })
    expect(onUnauthorized).toHaveBeenCalledOnce()
  })
})
