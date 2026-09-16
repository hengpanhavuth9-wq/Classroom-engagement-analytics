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
  fps:     16,
  quality: 0.8,
} as const;

export class CameraClient {
  private ws:         WebSocket;
  private stream:     MediaStream | null = null;
  private canvas:     HTMLCanvasElement;
  private ctx:        CanvasRenderingContext2D;
  private intervalId: ReturnType<typeof setInterval> | null = null;
  private video:      HTMLVideoElement;

  constructor(private sessionId: string, private wsUrl: string) {
    this.canvas = document.createElement('canvas');
    this.ctx    = this.canvas.getContext('2d')!;
    this.video  = document.createElement('video');
    this.video.muted = true;
    this.ws = new WebSocket(`${wsUrl}/ws/video/${sessionId}`);
  }

  /**
   * Begin streaming frames.
   *
   * The canvas is sized from the track's real resolution rather than a fixed
   * 640x360. A back-row face at 1080p is ~40-60px across; downscaling to 360p
   * puts it under the detector's floor entirely, and an undetected student is
   * dropped from the metric rather than counted as disengaged. Resolution is
   * kept high for detector coverage; fps is set for a live-feeling video
   * preview rather than the engagement metric itself, which is read over
   * multi-second windows and gains nothing from the extra frames.
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
