/**
 * Client du mode vocal (WebSocket /chat/attempts/{id}/voice).
 *
 * Deux façons de parler :
 * - appuyer pour parler : startTalking() / stopTalking() ;
 * - consultation mains libres : startConversation() ouvre le micro en continu, le
 *   serveur détecte la fin des phrases et les interruptions.
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
  /** Niveau du micro (0..1), pour l'animation */
  onLevel: (level: number) => void = () => {};

  private ws: WebSocket | null = null;
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private capture: AudioWorkletNode | null = null;
  private recording = false;
  private conversation = false;
  private muted = false;
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

  get isMuted(): boolean {
    return this.muted;
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
      this.conversation = false;
      this.onEvent({ type: 'closed' });
    };
  }

  /** Micro : AudioWorklet à 24 kHz, trames de 80 ms envoyées tant que l'on enregistre. */
  private async ensureMic(): Promise<void> {
    const ctx = this.ctx!;
    await ctx.resume();
    if (this.stream) return;
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
    });
    const moduleUrl = URL.createObjectURL(new Blob([CAPTURE_WORKLET], { type: 'application/javascript' }));
    await ctx.audioWorklet.addModule(moduleUrl);
    URL.revokeObjectURL(moduleUrl);
    const source = ctx.createMediaStreamSource(this.stream);
    this.capture = new AudioWorkletNode(ctx, 'mic-capture');
    this.capture.port.onmessage = (e: MessageEvent<Float32Array<ArrayBuffer>>) => {
      const frame = e.data;
      let sum = 0;
      for (let i = 0; i < frame.length; i++) sum += frame[i]! * frame[i]!;
      this.onLevel(this.recording ? Math.min(1, Math.sqrt(sum / frame.length) * 6) : 0);
      if (this.recording && this.isConnected) this.ws!.send(frame.buffer);
    };
    // Relié à la sortie via un gain nul : le graphe est bien traité, sans retour du micro
    const mute = ctx.createGain();
    mute.gain.value = 0;
    source.connect(this.capture).connect(mute).connect(ctx.destination);
  }

  /** Début de prise de parole (coupe la voix du patient s'il parle). */
  async startTalking(): Promise<void> {
    await this.connect();
    await this.ensureMic();
    this.stopPlayback();
    this.send({ type: 'start' });
    this.recording = true;
  }

  /** Consultation mains libres : micro ouvert en continu jusqu'à stopConversation(). */
  async startConversation(): Promise<void> {
    await this.connect();
    await this.ensureMic();
    this.send({ type: 'conversation_start' });
    this.conversation = true;
    this.muted = false;
    this.recording = true;
  }

  stopConversation(): void {
    if (!this.conversation) return;
    this.conversation = false;
    this.recording = false;
    this.onLevel(0);
    this.send({ type: 'conversation_stop' });
  }

  /** Couper / rétablir le micro pendant la consultation mains libres. */
  setMuted(muted: boolean): void {
    this.muted = muted;
    if (this.conversation) this.recording = !muted;
    if (muted) this.onLevel(0);
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
    this.conversation = false;
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
    if (!wasSpeaking) this.setSpeaking(true);
    source.onended = () => {
      this.sources.delete(source);
      if (!this.isSpeaking) this.setSpeaking(false);
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
    if (wasSpeaking) this.setSpeaking(false);
  }

  /** Le serveur ne sait pas quand le navigateur a fini de jouer ce qu'il a reçu :
   * on le lui dit (filtre d'écho, interruption de la voix par la parole). */
  private setSpeaking(speaking: boolean): void {
    this.send({ type: 'playback', state: speaking ? 'started' : 'ended' });
    this.onSpeakingChange(speaking);
  }
}
