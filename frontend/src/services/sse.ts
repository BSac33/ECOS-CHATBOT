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

/** Aucun octet reçu pendant le délai d'inactivité : le flux est abandonné. */
export class SSETimeoutError extends Error {
  constructor(message = 'Pas de réponse du serveur depuis un moment. Réessayez.') {
    super(message);
    this.name = 'SSETimeoutError';
  }
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

export interface ReadSSEOptions {
  /** Abandon si aucun octet n'arrive pendant ce délai (ms). Désactivé si absent. */
  idleTimeoutMs?: number;
  /** Message de l'erreur de délai */
  timeoutMessage?: string;
}

async function readChunk(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  options: ReadSSEOptions,
): Promise<ReadableStreamReadResult<Uint8Array>> {
  const { idleTimeoutMs } = options;
  if (!idleTimeoutMs) return reader.read();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new SSETimeoutError(options.timeoutMessage)), idleTimeoutMs);
  });
  try {
    return await Promise.race([reader.read(), timeout]);
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Consomme le corps d'une réponse SSE et appelle onEvent pour chaque événement.
 * Se termine quand le serveur ferme le flux ; lève SSETimeoutError si le flux reste muet.
 */
export async function readSSE(
  response: Response,
  onEvent: (message: SSEMessage) => void,
  options: ReadSSEOptions = {},
): Promise<void> {
  if (!response.body) {
    throw new Error('Réponse sans corps : streaming non supporté');
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { value, done } = await readChunk(reader, options);
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const { events, rest } = parseSSEChunk(buffer);
      buffer = rest;
      events.forEach(onEvent);
    }
  } catch (error) {
    // Flux abandonné (délai, coupure) : on libère la connexion
    reader.cancel().catch(() => {});
    throw error;
  }

  buffer += decoder.decode();
  const { events } = parseSSEChunk(buffer + '\n\n');
  events.forEach(onEvent);
}
