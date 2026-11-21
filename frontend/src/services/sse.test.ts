import { describe, expect, it } from 'vitest'
import { parseSSEChunk, readSSE, SSETimeoutError, type SSEMessage } from './sse'

function streamOf(chunks: string[], { close = true } = {}): Response {
  const encoder = new TextEncoder()
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      chunks.forEach((c) => controller.enqueue(encoder.encode(c)))
      if (close) controller.close()
    },
  })
  return new Response(body, { headers: { 'Content-Type': 'text/event-stream' } })
}

describe('parseSSEChunk', () => {
  it('découpe des événements complets et décode le JSON', () => {
    const { events, rest } = parseSSEChunk(
      'event: delta\ndata: {"text": "Bonjour"}\n\nevent: done\ndata: {"patient_reply": "Bonjour"}\n\n',
    )
    expect(events).toEqual([
      { event: 'delta', data: { text: 'Bonjour' } },
      { event: 'done', data: { patient_reply: 'Bonjour' } },
    ])
    expect(rest).toBe('')
  })

  it("garde l'événement incomplet pour le morceau suivant", () => {
    const { events, rest } = parseSSEChunk('event: delta\ndata: {"text": "A"}\n\nevent: delta\ndata: {"te')
    expect(events).toHaveLength(1)
    expect(rest).toBe('event: delta\ndata: {"te')
    const next = parseSSEChunk(rest + 'xt": "B"}\n\n')
    expect(next.events).toEqual([{ event: 'delta', data: { text: 'B' } }])
  })

  it('accepte les fins de ligne CRLF, le type par défaut et les données non JSON', () => {
    const { events } = parseSSEChunk('data: texte brut\r\n\r\n')
    expect(events).toEqual([{ event: 'message', data: 'texte brut' }])
  })

  it('joint les lignes data multiples et ignore les blocs sans donnée', () => {
    const { events } = parseSSEChunk(': commentaire\n\nevent: note\ndata: ligne 1\ndata: ligne 2\n\n')
    expect(events).toEqual([{ event: 'note', data: 'ligne 1\nligne 2' }])
  })
})

describe('readSSE', () => {
  it('relaie les événements même coupés entre deux morceaux', async () => {
    const received: SSEMessage[] = []
    await readSSE(streamOf(['event: delta\nda', 'ta: {"text": "Bon"}\n\nevent: delta\ndata: {"text": "jour"}\n\n']),
      (m) => received.push(m))
    expect(received.map((m) => (m.data as { text: string }).text).join('')).toBe('Bonjour')
  })

  it('traite un dernier événement sans ligne vide finale', async () => {
    const received: SSEMessage[] = []
    await readSSE(streamOf(['event: done\ndata: {"ok": true}']), (m) => received.push(m))
    expect(received).toEqual([{ event: 'done', data: { ok: true } }])
  })

  it("abandonne le flux s'il reste muet trop longtemps", async () => {
    const received: SSEMessage[] = []
    const silent = streamOf(['event: delta\ndata: {"text": "Bon"}\n\n'], { close: false })
    await expect(readSSE(silent, (m) => received.push(m), { idleTimeoutMs: 30, timeoutMessage: 'Trop long' }))
      .rejects.toThrow(SSETimeoutError)
    expect(received).toHaveLength(1)
  })
})
