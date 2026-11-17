/**
 * Client du mode vocal « appuyer pour parler » (WebSocket /chat/attempts/{id}/voice).
 *
 * - Micro : AudioContext à 24 kHz (le navigateur rééchantillonne), un AudioWorklet
 *   découpe le signal en trames de 1920 échantillons (80 ms), envoyées en float32.
 * - Voix du patient : trames float32 24 kHz reçues du serveur, planifiées bout à bout.
 * - Couper la parole : appuyer sur le bouton pendant que le patient parle coupe
 *   immédiatement sa voix (côté navigateur) et prévient le serveur.
 */

export const SAMPLE_RATE = 24000;
const FRAME_SIZE = 1920;

export interface VoiceEvent {
  type: string;
  [key: string]: unknown;
}

// Code de l'AudioWorklet, chargé depuis un Blob (pas de fichier séparé à servir)
const CAPTURE_WORKLET = `
class MicCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.frame = new Float32Array(${FRAME_SIZE});
    this.filled = 0;
  }
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) {
      for (let i = 0; i < channel.length; i++) {
        this.frame[this.filled++] = channel[i];
        if (this.filled === ${FRAME_SIZE}) {
          const out = this.frame;
          this.port.postMessage(out, [out.buffer]);
          this.frame = new Float32Array(${FRAME_SIZE});
          this.filled = 0;
        }
      }
    }
    return true;
  }
}
registerProcessor('mic-capture', MicCapture);
`;

export class VoiceClient {
  onEvent: (event: VoiceEvent) => void = () => {};
  onSpeakingChange: (speaking: boolean) => void = () => {};

  private ws: WebSocket | null = null;
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private capture: AudioWorkletNode | null = null;
  private recording = false;
  private playHead = 0;
  private sources = new Set<AudioBufferSourceNode>();
  voice: string | null = null;
  private readonly attemptId: string;

  constructor(attemptId: string) {
    this.attemptId = attemptId;
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  get isSpeaking(): boolean {
    return this.sources.size > 0;
  }

  /** Ouvre la connexion ; résolu au message "ready" du serveur. */
  async connect(): Promise<void> {
    if (this.isConnected) return;
    this.ctx ??= new AudioContext({ sampleRate: SAMPLE_RATE });

    const url = new URL(`/chat/attempts/${this.attemptId}/voice`, window.location.href);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(url);
    ws.binaryType = 'arraybuffer';
    this.ws = ws;

    await new Promise<void>((resolve, reject) => {
      ws.onmessage = (message) => {
        if (typeof message.data === 'string') {
          const event = JSON.parse(message.data) as VoiceEvent;
          if (event.type === 'ready') {
            this.voice = (event.voice as string) ?? null;
            ws.onmessage = (m) => this.handleMessage(m);
            resolve();
          }
        }
      };
      ws.onerror = () => reject(new Error('Connexion au mode vocal impossible'));
      ws.onclose = (e) => reject(new Error(e.reason || 'Mode vocal refusé par le serveur'));
    });

    ws.onclose = () => {
      this.recording = false;
      this.onEvent({ type: 'closed' });
    };
  }

  /** Début de prise de parole (coupe la voix du patient s'il parle). */
  async startTalking(): Promise<void> {
    await this.connect();
    const ctx = this.ctx!;
    await ctx.resume();
    if (!this.stream) {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
      });
      const moduleUrl = URL.createObjectURL(new Blob([CAPTURE_WORKLET], { type: 'application/javascript' }));
      await ctx.audioWorklet.addModule(moduleUrl);
      URL.revokeObjectURL(moduleUrl);
      const source = ctx.createMediaStreamSource(this.stream);
      this.capture = new AudioWorkletNode(ctx, 'mic-capture');
      this.capture.port.onmessage = (e: MessageEvent<Float32Array<ArrayBuffer>>) => {
        if (this.recording && this.isConnected) this.ws!.send(e.data.buffer);
      };
      // Relié à la sortie via un gain nul : le graphe est bien traité, sans retour du micro
      const mute = ctx.createGain();
      mute.gain.value = 0;
      source.connect(this.capture).connect(mute).connect(ctx.destination);
    }
    this.stopPlayback();
    this.send({ type: 'start' });
    this.recording = true;
  }

  /** Fin de prise de parole : le serveur transcrit puis fait répondre le patient. */
  stopTalking(): void {
    if (!this.recording) return;
    this.recording = false;
    this.send({ type: 'stop' });
  }

  /** Coupe la voix du patient sans reprendre la parole. */
  interrupt(): void {
    this.stopPlayback();
    this.send({ type: 'interrupt' });
  }

  close(): void {
    this.recording = false;
    this.stopPlayback();
    this.ws?.close();
    this.ws = null;
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    void this.ctx?.close();
    this.ctx = null;
  }

  private send(data: object): void {
    if (this.isConnected) this.ws!.send(JSON.stringify(data));
  }

  private handleMessage(message: MessageEvent): void {
    if (message.data instanceof ArrayBuffer) {
      this.play(new Float32Array(message.data as ArrayBuffer));
      return;
    }
    const event = JSON.parse(message.data) as VoiceEvent;
    if (event.type === 'interrupted') this.stopPlayback();
    this.onEvent(event);
  }

  private play(pcm: Float32Array<ArrayBuffer>): void {
    const ctx = this.ctx;
    if (!ctx || pcm.length === 0) return;
    const buffer = ctx.createBuffer(1, pcm.length, SAMPLE_RATE);
    buffer.copyToChannel(pcm, 0);
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    // Petite marge au démarrage pour absorber la gigue réseau
    const startAt = Math.max(ctx.currentTime + 0.05, this.playHead);
    source.start(startAt);
    this.playHead = startAt + buffer.duration;
    const wasSpeaking = this.isSpeaking;
    this.sources.add(source);
    if (!wasSpeaking) this.onSpeakingChange(true);
    source.onended = () => {
      this.sources.delete(source);
      if (!this.isSpeaking) this.onSpeakingChange(false);
    };
  }

  private stopPlayback(): void {
    const wasSpeaking = this.isSpeaking;
    for (const source of this.sources) {
      source.onended = null;
      try {
        source.stop();
      } catch {
        // déjà arrêtée
      }
    }
    this.sources.clear();
    this.playHead = 0;
    if (wasSpeaking) this.onSpeakingChange(false);
  }
}
