import { wsToken } from './api';

export interface CameraClientOptions {
  /** Capture resolution requested from the camera and sent to the backend. */
  width?:  number;
  height?: number;
  /** Frames per second sent over the socket. */
  fps?:    number;
  /** JPEG quality, 0-1. */
  quality?: number;
}

const DEFAULTS = {
  width:   1920,
  height:  1080,
  // Matches TRACK_MAX_LOST_FRAMES / EMA_ALPHA / eval/run_eval.py's default,
  // all tuned assuming ~2 FPS (see config.py's comments). This does NOT
  // control how smooth the on-screen preview looks — the <video> element
  // renders the live camera stream directly, independent of this interval,
  // which only governs how often a frame is snapshotted and sent for
  // analysis. Raising it desyncs tracking/smoothing from the settings built
  // around it; if you want faster-refreshing overlays, scale
  // TRACK_MAX_LOST_FRAMES and EMA_ALPHA on the backend to match.
  fps:     2,
  quality: 0.8,
} as const;

export class CameraClient {
  private ws:         WebSocket;
  private stream:     MediaStream | null = null;
  private canvas:     HTMLCanvasElement;
  private ctx:        CanvasRenderingContext2D;
  private intervalId: ReturnType<typeof setInterval> | null = null;
  private video:      HTMLVideoElement;
  private onPipelineError?: (message: string) => void;

  constructor(private sessionId: string, private wsUrl: string, onPipelineError?: (message: string) => void) {
    this.canvas = document.createElement('canvas');
    this.ctx    = this.canvas.getContext('2d')!;
    this.video  = document.createElement('video');
    this.video.muted = true;
    this.onPipelineError = onPipelineError;

    const token = wsToken();
    const url = token
      ? `${wsUrl}/ws/video/${sessionId}?token=${encodeURIComponent(token)}`
      : `${wsUrl}/ws/video/${sessionId}`;
    this.ws = new WebSocket(url);

    // The backend sends a JSON error (e.g. AI pipeline / weights missing,
    // or an unauthorized close) and then closes the socket. Previously
    // nothing read this: the dashboard kept showing "Camera + AI active"
    // with a live-looking preview even though no frame was ever processed.
    this.ws.onmessage = (event: MessageEvent<string>) => {
      try {
        const data = JSON.parse(event.data);
        if (data.error) this.onPipelineError?.(String(data.error));
      } catch {
        // not JSON — ignore
      }
    };
    this.ws.onclose = (event: CloseEvent) => {
      if (event.code === 4401) this.onPipelineError?.('Unauthorized — check the API token.');
    };
    this.ws.onerror = () => this.onPipelineError?.('Video connection error.');
  }

  /**
   * Begin streaming frames.
   *
   * The canvas is sized from the track's real resolution rather than a fixed
   * 640x360. A back-row face at 1080p is ~40-60px across; downscaling to 360p
   * puts it under the detector's floor entirely, and an undetected student is
   * dropped from the metric rather than counted as disengaged. Resolution is
   * kept high for detector coverage; fps governs the analysis send rate, not
   * the preview — see DEFAULTS.fps.
   */
  async start(options: CameraClientOptions = {}): Promise<void> {
    const { width, height, fps, quality } = { ...DEFAULTS, ...options };

    this.stream = await navigator.mediaDevices.getUserMedia({
      video: {
        width:  { ideal: width },
        height: { ideal: height },
        facingMode: 'environment',
      },
      audio: false,
    });

    this.video.srcObject = this.stream;
    await this.video.play();

    const settings = this.stream.getVideoTracks()[0]?.getSettings();
    this.canvas.width  = settings?.width  ?? this.video.videoWidth  ?? width;
    this.canvas.height = settings?.height ?? this.video.videoHeight ?? height;

    this.intervalId = setInterval(() => {
      if (this.ws.readyState !== WebSocket.OPEN) return;
      this.ctx.drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);
      this.canvas.toBlob(
        (blob) => {
          if (blob) this.ws.send(blob);
        },
        'image/jpeg',
        quality,
      );
    }, 1000 / fps);
  }

  /** Ask the backend to capture each student's "looking at the board" reference. */
  calibrate(): void {
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action: 'calibrate' }));
    }
  }

  getCaptureSize(): { width: number; height: number } {
    return { width: this.canvas.width, height: this.canvas.height };
  }

  getVideoElement(): HTMLVideoElement {
    return this.video;
  }

  stop(): void {
    if (this.intervalId) clearInterval(this.intervalId);
    this.stream?.getTracks().forEach((t) => t.stop());
    this.ws.close();
  }
}
