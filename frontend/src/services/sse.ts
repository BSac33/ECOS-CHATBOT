/**
 * Lecture d'un flux Server-Sent Events renvoyé par une requête POST.
 *
 * EventSource ne gère que GET (sans corps de requête) : on lit donc le corps
 * de la réponse fetch au fil de l'eau et on découpe les événements à la main.
 * Format attendu (une donnée JSON par événement) :
 *
 *   event: delta
 *   data: {"text": "Bonjour"}
 *
 */

export interface SSEMessage {
  event: string;
  data: unknown;
}

/**
 * Découpe un tampon texte en événements SSE complets.
 * Retourne les événements trouvés et le reste (événement incomplet).
 */
export function parseSSEChunk(buffer: string): { events: SSEMessage[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, '\n');
  const blocks = normalized.split('\n\n');
  const rest = blocks.pop() ?? '';
  const events: SSEMessage[] = [];

  for (const block of blocks) {
    let event = 'message';
    const dataLines: string[] = [];
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) {
        event = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).replace(/^ /, ''));
      }
    }
    if (dataLines.length === 0) continue;
    const raw = dataLines.join('\n');
    let data: unknown = raw;
    try {
      data = JSON.parse(raw);
    } catch {
      // donnée non JSON : on la transmet telle quelle
    }
    events.push({ event, data });
  }
  return { events, rest };
}

/**
 * Consomme le corps d'une réponse SSE et appelle onEvent pour chaque événement.
 * Se termine quand le serveur ferme le flux.
 */
export async function readSSE(
  response: Response,
  onEvent: (message: SSEMessage) => void,
): Promise<void> {
  if (!response.body) {
    throw new Error('Réponse sans corps : streaming non supporté');
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const { events, rest } = parseSSEChunk(buffer);
    buffer = rest;
    events.forEach(onEvent);
  }

  buffer += decoder.decode();
  const { events } = parseSSEChunk(buffer + '\n\n');
  events.forEach(onEvent);
}
