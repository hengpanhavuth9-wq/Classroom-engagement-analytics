'use client';
import { useState, useEffect, useRef, useCallback } from 'react';
import { useEngagementSocket } from '@/hooks/useEngagementSocket';
import { useSessionControls }  from '@/hooks/useSessionControls';
import { useEngagementStore }  from '@/store/engagementStore';
import { useGazeOverlay }      from '@/hooks/useGazeOverlay';
import { EngagementGauge }     from '@/components/charts/EngagementGauge';
import { AttentionBreakdown }  from '@/components/charts/AttentionBreakdown';
import { TimelineLine }        from '@/components/charts/TimelineLine';
import { AlertBanner }         from '@/components/ui/AlertBanner';
import { KPICard }             from '@/components/ui/KPICard';
import { SessionSetup }        from '@/components/ui/SessionSetup';
import { LiveMetrics, FaceOverlay, AttentionState } from '@/lib/types';
import { CameraClient }        from '@/lib/cameraClient';
import Link from 'next/link';
import { ArrowLeft, Zap, Camera, CameraOff, Crosshair, AlertCircle } from 'lucide-react';

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000';

// ── Demo data simulator ───────────────────────────────────────────────────────────
function makeDemoMetrics(tick: number): LiveMetrics {
  const base  = 68 + Math.sin(tick / 8) * 15 + (Math.random() - 0.5) * 8;
  const eng   = Math.max(20, Math.min(98, base));
  const total = 6;
  const engCt = Math.round(total * eng / 100);

  // Fake face overlays for demo
  const faces: FaceOverlay[] = Array.from({ length: total }, (_, i) => {
    const col   = i % 3;
    const row   = Math.floor(i / 3);
    const isEn  = i < engCt;
    const state: AttentionState = isEn
      ? (i % 4 === 3 ? 'desk_work' : 'on_task')
      : (i === total - 1 ? 'unknown' : 'off_task');
    return {
      bbox:          [0.08 + col * 0.3, 0.15 + row * 0.45, 0.22, 0.32],
      yaw:           isEn ? (Math.random() - 0.5) * 12 : (Math.random() - 0.5) * 70,
      pitch:         isEn ? (Math.random() - 0.5) * 8  : (Math.random() - 0.5) * 40,
      state,
      on_task_ratio: state === 'unknown' ? null : (isEn ? 0.6 + Math.random() * 0.35 : 0.1 + Math.random() * 0.35),
      measured:      state !== 'unknown',
      has_gaze:      row === 0,
    };
  });

  const stateCounts = faces.reduce<Record<AttentionState, number>>(
    (acc, f) => ({ ...acc, [f.state]: acc[f.state] + 1 }),
    { on_task: 0, desk_work: 0, off_task: 0, unknown: 0 },
  );
  const tracked = faces.filter((f) => f.measured).length;

  return {
    session_id: 'demo',
    on_task_ratio: parseFloat((eng / 100).toFixed(4)),
    class_engagement: parseFloat(eng.toFixed(1)),
    student_count: total,
    tracked_count: tracked,
    detected_count: total,
    expected_count: null,
    engaged_count: engCt,
    below_floor_count: tracked - engCt,
    state_counts: stateCounts,
    is_calibrating: false,
    gaze_model_loaded: true,
    faces,
    timestamp: Date.now(),
  };
}

export default function TeacherDashboard() {
  const { metrics, history, alerts, isConnected, sessionId } = useEngagementStore();
  const { startSession, endSession, loading }                 = useSessionControls();

  const [showSetup, setShowSetup]       = useState(!sessionId);
  const [demoMode, setDemoMode]         = useState(false);
  const [demoMetrics, setDemoMetrics]   = useState<LiveMetrics | null>(null);
  const [demoHistory, setDemoHistory]   = useState<LiveMetrics[]>([]);
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraError, setCameraError]   = useState<string | null>(null);
  const [videoEl, setVideoEl]           = useState<HTMLVideoElement | null>(null);

  const tickRef      = useRef(0);
  const cameraRef    = useRef<CameraClient | null>(null);
  const canvasRef    = useRef<HTMLCanvasElement>(null);
  const videoContRef = useRef<HTMLDivElement>(null);

  // Current faces for overlay
  const liveMetrics = demoMode ? demoMetrics : metrics;
  const liveHistory = demoMode ? demoHistory : history;
  const connected   = demoMode ? true : isConnected;
  const currentFaces = (liveMetrics?.faces ?? []) as FaceOverlay[];

  useEngagementSocket(sessionId);

  // Wire the gaze overlay canvas
  useGazeOverlay(canvasRef, videoEl, currentFaces);

  // ── Demo simulator ────────────────────────────────────────────
  useEffect(() => {
    if (!demoMode) return;
    const id = setInterval(() => {
      tickRef.current += 1;
      const m = makeDemoMetrics(tickRef.current);
      setDemoMetrics(m);
      setDemoHistory(prev => [...prev, m].slice(-40));
    }, 1500);
    return () => clearInterval(id);
  }, [demoMode]);

  // ── Camera start ────────────────────────────────────────────────
  const startCamera = useCallback(async (sid: string) => {
    setCameraError(null);
    try {
      // Pipeline failures (missing weights, unauthorized, a dropped socket)
      // surface here instead of leaving the "Camera + AI active" badge lying.
      const client = new CameraClient(sid, WS_BASE, (message) => {
        setCameraError(message);
        setCameraActive(false);
      });
      cameraRef.current = client;
      await client.start();
      const videoEl        = client.getVideoElement();
      videoEl.style.cssText = 'width:100%;height:100%;object-fit:cover;border-radius:16px;';
      setVideoEl(videoEl);
      if (videoContRef.current) {
        videoContRef.current.innerHTML = '';
        videoContRef.current.appendChild(videoEl);
      }
      setCameraActive(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setCameraError(msg.includes('Permission') ? 'Camera permission denied.' : `Camera error: ${msg}`);
    }
  }, []);

  const stopCamera = useCallback(() => {
    cameraRef.current?.stop();
    cameraRef.current = null;
    setCameraActive(false);
    setVideoEl(null);
    if (videoContRef.current) videoContRef.current.innerHTML = '';
  }, []);

  const calibrate = useCallback(() => cameraRef.current?.calibrate(), []);

  // ── Session handlers ───────────────────────────────────────────
  const handleStart = async (classroomId: string, teacher: string, subject: string) => {
    if (classroomId.startsWith('demo-')) { setDemoMode(true); setShowSetup(false); return; }
    const id = await startSession(classroomId, teacher, subject);
    if (id) { setShowSetup(false); await startCamera(id as string); }
  };

  const handleEnd = async () => {
    stopCamera();
    if (demoMode) {
      setDemoMode(false); setDemoMetrics(null); setDemoHistory([]);
      tickRef.current = 0; setShowSetup(true); return;
    }
    if (sessionId) { await endSession(sessionId); setShowSetup(true); }
  };

  if (showSetup) {
    return <SessionSetup onStart={handleStart} onDemo={() => { setDemoMode(true); setShowSetup(false); }} loading={loading} />;
  }

  return (
    <main className="min-h-screen bg-gray-950 text-white">
      {/* ── Header ── */}
      <header className="border-b border-[#181a1f] px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/" className="text-gray-500 hover:text-gray-300 transition-colors">
            <ArrowLeft className="w-4.5 h-4.5" />
          </Link>
          <h1 className="text-[15px] font-semibold tracking-tight">ReLi <span className="text-gray-600 font-normal">/ Teacher</span></h1>
          <div className="flex items-center gap-1.5 pl-1">
            <span className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-emerald-400 animate-pulse-dot' : 'bg-red-500'}`} />
            <span className="text-xs text-gray-500">
              {demoMode ? 'Demo · simulated' : connected ? 'Live' : 'Reconnecting…'}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2.5">
          {demoMode && (
            <span className="flex items-center gap-1.5 text-indigo-300 text-xs bg-indigo-500/10 border border-indigo-500/20 px-3 py-1 rounded-full">
              <Zap className="w-3 h-3" /> Demo mode
            </span>
          )}
          {!demoMode && (
            <span className={`flex items-center gap-1.5 text-xs px-3 py-1 rounded-full border ${cameraActive ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' : 'text-gray-500 bg-[#15171c] border-[#22252b]'}`}>
              {cameraActive ? <Camera className="w-3 h-3" /> : <CameraOff className="w-3 h-3" />}
              {cameraActive ? 'Camera + AI active' : 'No camera'}
            </span>
          )}
          {!demoMode && (
            <button
              onClick={calibrate}
              disabled={!cameraActive}
              className="flex items-center gap-1.5 px-3.5 py-1.5 bg-indigo-500/10 hover:bg-indigo-500/15 disabled:opacity-40 disabled:hover:bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 rounded-[8px] text-xs font-medium transition-colors"
            >
              <Crosshair className="w-3.5 h-3.5" />
              Calibrate
            </button>
          )}
          <button onClick={handleEnd} className="px-3.5 py-1.5 bg-red-500/10 hover:bg-red-500/15 text-red-400 border border-red-500/20 rounded-[8px] text-xs font-medium transition-colors">
            End session
          </button>
        </div>
      </header>

      <div className="p-6 space-y-5 max-w-[1400px] mx-auto">
        {alerts[0] && <AlertBanner alert={alerts[0]} />}

        {cameraError && (
          <div className="animate-fade-in flex items-center gap-3 bg-red-500/[0.07] border border-red-500/20 rounded-[14px] px-4 py-3 text-red-300 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {cameraError}
          </div>
        )}

        {liveMetrics?.is_calibrating && (
          <div className="flex items-center gap-3 bg-indigo-500/[0.07] border border-indigo-500/20 rounded-[14px] px-4 py-3 text-indigo-300 text-sm">
            <Crosshair className="w-4 h-4 shrink-0 animate-pulse" />
            Calibrating — ask everyone to look at the board until this clears.
          </div>
        )}

        {liveMetrics && !liveMetrics.gaze_model_loaded && (
          <div className="flex items-center gap-3 bg-amber-500/[0.07] border border-amber-500/20 rounded-[14px] px-4 py-3 text-amber-300 text-sm">
            Eye-gaze model not loaded — running on head pose alone.
          </div>
        )}

        {/* ── Main grid: camera (with overlay) + KPIs ── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

          {/* Camera Preview with canvas overlay */}
          <div className="surface overflow-hidden relative" style={{ minHeight: 260 }}>
            <div className="absolute top-3 left-3 z-20 flex items-center gap-1.5 bg-black/50 backdrop-blur px-2.5 py-1 rounded-full">
              <span className={`w-1.5 h-1.5 rounded-full ${cameraActive || demoMode ? 'bg-emerald-400 animate-pulse-dot' : 'bg-gray-600'}`} />
              <span className="text-xs text-gray-300">
                {demoMode ? 'Demo · AI overlay' : cameraActive ? 'Live · Gaze tracking' : 'No camera'}
              </span>
            </div>

            {/* Real camera video injected here */}
            <div ref={videoContRef} className="absolute inset-0" />

            {/* Canvas overlay for gaze arrows, face boxes, emotion labels */}
            <canvas
              ref={canvasRef}
              className="absolute inset-0 w-full h-full pointer-events-none z-10"
              style={{ borderRadius: 16 }}
            />

            {/* Demo static placeholder (canvas draws over this) */}
            {demoMode && (
              <div className="absolute inset-0 bg-[#0c0d10] flex items-center justify-center">
                <div className="grid grid-cols-3 gap-4 p-4">
                  {Array.from({ length: 6 }, (_, i) => (
                    <div key={i} className="w-16 h-20 rounded-[10px] bg-[#15171c] border border-[#22252b] flex flex-col items-center justify-center gap-1">
                      <div className="w-8 h-8 rounded-full bg-indigo-500/20 border border-indigo-500/30" />
                      <div className="w-10 h-2.5 rounded bg-[#22252b]" />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {!demoMode && !cameraActive && !cameraError && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-2">
                <Camera className="w-7 h-7 text-gray-700" />
                <p className="text-xs text-gray-600">Starting camera…</p>
              </div>
            )}
            {!demoMode && !cameraActive && cameraError && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-2">
                <CameraOff className="w-7 h-7 text-gray-700" />
                <p className="text-xs text-gray-600">Camera stopped</p>
              </div>
            )}

            {/* Gaze legend */}
            {(cameraActive || demoMode) && currentFaces.length > 0 && (
              <div className="absolute bottom-3 right-3 z-20 flex flex-col gap-1">
                {([
                  ['bg-emerald-400', 'On task'],
                  ['bg-blue-400',    'Desk work'],
                  ['bg-amber-400',   'Off task'],
                  ['bg-gray-500',    'Unknown (not scored)'],
                ] as const).map(([dot, label]) => (
                  <div key={label} className="flex items-center gap-1.5 bg-black/50 backdrop-blur px-2 py-1 rounded-md">
                    <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
                    <span className="text-[10px] text-gray-300">{label}</span>
                  </div>
                ))}
                <div className="flex items-center gap-1.5 bg-black/50 backdrop-blur px-2 py-1 rounded-md">
                  <span className="text-[10px] text-gray-400">→ arrow = deviation from reference</span>
                </div>
              </div>
            )}
          </div>

          {/* KPI Cards */}
          <div className="lg:col-span-2 grid grid-cols-2 gap-3.5 content-start">
            <KPICard label="Students detected"  value={liveMetrics?.detected_count ?? '—'} />
            <KPICard label="Engaged students"   value={liveMetrics ? `${liveMetrics.engaged_count}/${liveMetrics.tracked_count}` : '—'} accent="green" />
            <KPICard label="Tracked / detected" value={liveMetrics ? `${liveMetrics.tracked_count}/${liveMetrics.student_count}` : '—'} accent="yellow" hint="Coverage — not all detected faces have enough history yet" />
            <KPICard label="Class engagement"   value={liveMetrics ? `${liveMetrics.class_engagement.toFixed(0)}%` : '—'} accent="indigo" hint="20s rolling average" />
          </div>
        </div>

        {/* ── Charts ── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          <div className="surface p-6">
            <h2 className="text-[11px] font-medium text-gray-500 uppercase tracking-[0.08em] mb-4">Class engagement</h2>
            <EngagementGauge value={liveMetrics?.class_engagement ?? 0} />
          </div>
          <div className="surface p-6">
            <h2 className="text-[11px] font-medium text-gray-500 uppercase tracking-[0.08em] mb-4">Attention breakdown</h2>
            <AttentionBreakdown counts={liveMetrics?.state_counts} />
          </div>
          <div className="surface p-6">
            <h2 className="text-[11px] font-medium text-gray-500 uppercase tracking-[0.08em] mb-4">Engagement timeline</h2>
            <TimelineLine data={liveHistory} />
          </div>
        </div>

        <p className="text-xs text-gray-600 text-center pt-1">
          {demoMode ? 'Session: demo (simulated · gaze overlay active)' : `Session ID: ${sessionId}`}
        </p>
      </div>
    </main>
  );
}
