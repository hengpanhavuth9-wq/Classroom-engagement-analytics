'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, Download, Upload, Check } from 'lucide-react';
import RecordingPicker from '@/components/review/RecordingPicker';
import SegmentRater from '@/components/review/SegmentRater';
import { api } from '@/lib/api';
import type { SegmentReview } from '@/lib/types';

const SEGMENT_SECONDS = 300;

type SubmitState = { kind: 'idle' | 'sending' } | { kind: 'done'; saved: string } | { kind: 'error'; message: string };

function csvCell(value: string): string {
  return /[",\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

export default function ReviewPage() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [videoUrl, setVideoUrl] = useState('');
  const [duration, setDuration] = useState(0);
  const [index, setIndex] = useState(0);
  const [reviews, setReviews] = useState<SegmentReview[]>([]);
  const [sessionId, setSessionId] = useState('');
  const [submit, setSubmit] = useState<SubmitState>({ kind: 'idle' });

  useEffect(() => {
    const fromUrl = new URLSearchParams(window.location.search).get('session');
    if (fromUrl) setSessionId(fromUrl);
  }, []);

  useEffect(() => () => { if (videoUrl) URL.revokeObjectURL(videoUrl); }, [videoUrl]);

  const segmentCount = duration ? Math.max(1, Math.ceil(duration / SEGMENT_SECONDS)) : 0;

  const startS = index * SEGMENT_SECONDS;
  const endS = Math.min(startS + SEGMENT_SECONDS, duration);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !duration) return;
    video.pause();
    video.currentTime = Math.min(startS, Math.max(0, duration - 0.1));
  }, [index, duration, startS]);

  function handlePick(picked: File) {
    if (videoUrl) URL.revokeObjectURL(videoUrl);
    setFile(picked);
    setVideoUrl(URL.createObjectURL(picked));
    setDuration(0);
    setIndex(0);
    setReviews([]);
    setSubmit({ kind: 'idle' });
  }

  function handleMetadata() {
    const video = videoRef.current;
    if (!video) return;
    setDuration(video.duration);
    const count = Math.max(1, Math.ceil(video.duration / SEGMENT_SECONDS));
    setReviews(Array.from({ length: count }, () => ({ rating: null, confidence: 'sure', note: '' })));
  }

  function handleTimeUpdate() {
    const video = videoRef.current;
    if (!video || !duration) return;
    if (video.currentTime >= endS) {
      video.pause();
      video.currentTime = Math.max(startS, endS - 0.1);
    }
  }

  const rows = useMemo(
    () =>
      reviews
        .map((review, i) => ({
          segment_start_s: i * SEGMENT_SECONDS,
          segment_end_s: Math.min((i + 1) * SEGMENT_SECONDS, Math.ceil(duration)),
          ...review,
        }))
        .filter((row): row is typeof row & { rating: NonNullable<SegmentReview['rating']> } => row.rating !== null),
    [reviews, duration],
  );

  const ratedCount = rows.length;
  const effectiveSessionId = sessionId.trim() || 'unnamed';

  function downloadCsv() {
    const header = 'session_id,segment_start_s,segment_end_s,rating,confidence,note';
    const body = rows
      .map((r) =>
        [effectiveSessionId, r.segment_start_s, r.segment_end_s, r.rating, r.confidence, r.note]
          .map((v) => csvCell(String(v)))
          .join(','),
      )
      .join('\n');
    const blob = new Blob([`${header}\n${body}\n`], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'segment_ratings.csv';
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function submitToTeam() {
    setSubmit({ kind: 'sending' });
    try {
      const result = await api.submitRatings({
        session_id: effectiveSessionId,
        segments: rows.map((r) => ({
          segment_start_s: r.segment_start_s,
          segment_end_s: r.segment_end_s,
          rating: r.rating,
          confidence: r.confidence,
          note: r.note,
        })),
      });
      setSubmit({ kind: 'done', saved: result.saved });
    } catch (err) {
      setSubmit({ kind: 'error', message: err instanceof Error ? err.message : 'Could not reach the server' });
    }
  }

  return (
    <main className="min-h-screen bg-gray-950 text-white">
      <header className="border-b border-[#181a1f] px-6 py-4 flex items-center gap-4">
        <Link href="/" className="text-gray-500 hover:text-gray-300 transition-colors">
          <ArrowLeft className="w-4.5 h-4.5" />
        </Link>
        <h1 className="text-[15px] font-semibold tracking-tight">ReLi <span className="text-gray-600 font-normal">/ Review a recording</span></h1>
      </header>

      <div className="p-6 max-w-5xl mx-auto space-y-6">
        <section className="bg-gray-900 border border-gray-800 rounded-2xl p-6 space-y-4">
          <p className="text-sm text-gray-400">
            Pick the recording we sent you. It stays on your computer — nothing is uploaded when you play it.
            Watch each 5-minute stretch and say how engaged the class was. When you are done, download the
            ratings and send them back, or submit them straight to the team.
          </p>
          <RecordingPicker fileName={file?.name} onPick={handlePick} />
          <div>
            <label className="text-xs text-gray-500 uppercase tracking-widest">Lesson name</label>
            <input
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              placeholder="e.g. 5B Math, 17 Sept"
              className="mt-1 w-full max-w-sm bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-indigo-500"
            />
          </div>
        </section>

        {videoUrl && (
          <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
              <video
                ref={videoRef}
                src={videoUrl}
                controls
                onLoadedMetadata={handleMetadata}
                onTimeUpdate={handleTimeUpdate}
                className="w-full bg-black"
              />
              <p className="text-xs text-gray-500 px-4 py-3">
                Playback is kept inside the current 5-minute segment. Use Next segment to move on.
              </p>
            </div>

            <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
              {segmentCount > 0 && reviews.length === segmentCount ? (
                <SegmentRater
                  index={index}
                  count={segmentCount}
                  startS={startS}
                  endS={endS}
                  value={reviews[index]}
                  onChange={(review) =>
                    setReviews((prev) => prev.map((r, i) => (i === index ? review : r)))
                  }
                  onPrev={() => setIndex((i) => Math.max(0, i - 1))}
                  onNext={() => setIndex((i) => Math.min(segmentCount - 1, i + 1))}
                />
              ) : (
                <p className="text-sm text-gray-500">Loading the recording…</p>
              )}
            </div>
          </section>
        )}

        {videoUrl && (
          <section className="bg-gray-900 border border-gray-800 rounded-2xl p-6 flex items-center justify-between flex-wrap gap-4">
            <p className="text-sm text-gray-400">
              {ratedCount} of {segmentCount} segments rated
            </p>
            <div className="flex items-center gap-3 flex-wrap">
              <button
                onClick={downloadCsv}
                disabled={ratedCount === 0}
                className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm font-medium disabled:opacity-40 transition-colors"
              >
                <Download className="w-4 h-4" /> Download ratings
              </button>
              <button
                onClick={submitToTeam}
                disabled={ratedCount === 0 || submit.kind === 'sending'}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm font-medium disabled:opacity-40 transition-colors"
              >
                {submit.kind === 'done' ? <Check className="w-4 h-4" /> : <Upload className="w-4 h-4" />}
                {submit.kind === 'sending' ? 'Sending…' : submit.kind === 'done' ? 'Submitted' : 'Submit to team'}
              </button>
            </div>
            {submit.kind === 'done' && (
              <p className="w-full text-xs text-green-400">Saved to {submit.saved} on the server.</p>
            )}
            {submit.kind === 'error' && (
              <p className="w-full text-xs text-red-400">
                {submit.message}. Your ratings are safe — use Download ratings and send the file instead.
              </p>
            )}
          </section>
        )}
      </div>
    </main>
  );
}
