'use client';
import { useEffect, useRef } from 'react';
import { AttentionState, FaceOverlay } from '@/lib/types';

const STATE_COLORS: Record<AttentionState, string> = {
  on_task:   '#3ecf8e',
  desk_work: '#6d9bfa',
  off_task:  '#e8a33d',
  unknown:   '#8b8f99',
};

const STATE_LABELS: Record<AttentionState, string> = {
  on_task:   'On task',
  desk_work: 'Desk work',
  off_task:  'Off task',
  unknown:   'Unknown',
};

const DEG = Math.PI / 180;

function drawArrow(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number,
  yawDeg: number, pitchDeg: number,
  len: number, color: string,
) {
  const ex = cx + Math.sin(yawDeg * DEG) * len;
  const ey = cy + Math.sin(pitchDeg * DEG) * len;

  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(ex, ey);
  ctx.strokeStyle = color;
  ctx.lineWidth   = 2.5;
  ctx.stroke();

  // Arrow head
  const angle  = Math.atan2(ey - cy, ex - cx);
  const hLen   = 10;
  ctx.beginPath();
  ctx.moveTo(ex, ey);
  ctx.lineTo(ex - hLen * Math.cos(angle - 0.4), ey - hLen * Math.sin(angle - 0.4));
  ctx.lineTo(ex - hLen * Math.cos(angle + 0.4), ey - hLen * Math.sin(angle + 0.4));
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.fill();
}

/**
 * Draw face boxes and head-pose deviation arrows over the camera preview.
 *
 * `video` is passed as a value rather than a ref so the draw loop starts when
 * the element is actually attached — a ref's identity never changes, so an
 * effect keyed on one would run only on mount, before the camera exists.
 */
export function useGazeOverlay(
  canvasRef: React.RefObject<HTMLCanvasElement>,
  video:     HTMLVideoElement | null,
  faces:     FaceOverlay[],
) {
  const animRef  = useRef<number | null>(null);
  const facesRef = useRef<FaceOverlay[]>(faces);
  facesRef.current = faces;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !video) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const draw = () => {
      // Match canvas to video size
      if (canvas.width !== video.videoWidth || canvas.height !== video.videoHeight) {
        canvas.width  = video.videoWidth  || canvas.offsetWidth;
        canvas.height = video.videoHeight || canvas.offsetHeight;
      }

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const W = canvas.width;
      const H = canvas.height;

      facesRef.current.forEach((face) => {
        const [nx, ny, nw, nh] = face.bbox;
        const x  = nx * W;
        const y  = ny * H;
        const bw = nw * W;
        const bh = nh * H;
        const cx = x + bw / 2;
        const cy = y + bh / 2;

        const color = STATE_COLORS[face.state] ?? STATE_COLORS.unknown;

        // ── Bounding box ───────────────────────────────────────────────
        ctx.strokeStyle = color;
        ctx.lineWidth   = 2;
        ctx.setLineDash(face.measured ? [] : [5, 4]);
        ctx.strokeRect(x, y, bw, bh);
        ctx.setLineDash([]);

        // Corner accents
        const clen = 12;
        ctx.lineWidth = 3;
        [[x, y, 1, 1], [x + bw, y, -1, 1], [x, y + bh, 1, -1], [x + bw, y + bh, -1, -1]].forEach(
          ([cx2, cy2, dx, dy]) => {
            ctx.beginPath();
            ctx.moveTo(cx2 as number, cy2 as number);
            ctx.lineTo((cx2 as number) + (dx as number) * clen, cy2 as number);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(cx2 as number, cy2 as number);
            ctx.lineTo(cx2 as number, (cy2 as number) + (dy as number) * clen);
            ctx.stroke();
          }
        );

        // ── Deviation arrow ─────────────────────────────────────────────
        drawArrow(ctx, cx, cy, face.yaw, face.pitch, Math.min(bw, bh) * 0.6, color);

        // ── Labels ────────────────────────────────────────────────────
        const ratioStr = face.on_task_ratio === null
          ? '—'
          : `${Math.round(face.on_task_ratio * 100)}%`;
        const label = `${STATE_LABELS[face.state] ?? face.state} ${ratioStr}${face.has_gaze ? ' 👁' : ''}`;

        // Label background
        ctx.font       = 'bold 13px Inter, system-ui, sans-serif';
        const tw       = ctx.measureText(label).width + 10;
        const lx       = x;
        const ly       = y - 24;
        ctx.fillStyle  = 'rgba(0,0,0,0.6)';
        ctx.beginPath();
        ctx.roundRect(lx, ly, tw, 20, 4);
        ctx.fill();

        ctx.fillStyle  = '#ffffff';
        ctx.fillText(label, lx + 5, ly + 14);

        // On-task ratio bar at bottom of face box
        if (face.on_task_ratio !== null) {
          const barH  = 4;
          const barY  = y + bh + 4;
          ctx.fillStyle = 'rgba(255,255,255,0.15)';
          ctx.fillRect(x, barY, bw, barH);
          ctx.fillStyle = color;
          ctx.fillRect(x, barY, bw * face.on_task_ratio, barH);
        }
      });

      animRef.current = requestAnimationFrame(draw);
    };

    animRef.current = requestAnimationFrame(draw);
    return () => {
      if (animRef.current) cancelAnimationFrame(animRef.current);
    };
  }, [canvasRef, video]);
}
