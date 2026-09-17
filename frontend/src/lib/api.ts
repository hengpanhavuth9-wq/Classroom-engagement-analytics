import type { RatingConfidence, SegmentRating } from './types';

const BASE  = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
// Shared dev token — see backend/app/api/security.py. A real deployment
// replaces this with a per-teacher session, not a single shared secret.
const TOKEN = process.env.NEXT_PUBLIC_API_TOKEN ?? '';

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {}),
    },
    ...options,
  });
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json() as Promise<T>;
}

export function wsToken(): string {
  return TOKEN;
}

export const api = {
  // Sessions
  createSession: (body: { classroom_id: string; teacher_name?: string; subject?: string }) =>
    apiFetch('/api/sessions/', { method: 'POST', body: JSON.stringify(body) }),

  endSession: (sessionId: string) =>
    apiFetch(`/api/sessions/${sessionId}/end`, { method: 'PATCH' }),

  getSession: (sessionId: string) =>
    apiFetch(`/api/sessions/${sessionId}`),

  // Classrooms
  listClassrooms: () =>
    apiFetch<{ id: string; name: string; school_name: string; capacity: number }[]>('/api/classrooms/'),

  createClassroom: (body: { name: string; school_name: string; capacity: number }) =>
    apiFetch('/api/classrooms/', { method: 'POST', body: JSON.stringify(body) }),

  // Analytics
  getSessionMetrics: (sessionId: string, limit = 200) =>
    apiFetch(`/api/analytics/sessions/${sessionId}/metrics?limit=${limit}`),

  getClassroomsSummary: () =>
    apiFetch('/api/analytics/classrooms/summary'),

  // Model feedback
  submitRatings: (body: {
    session_id: string;
    segments: {
      segment_start_s: number;
      segment_end_s: number;
      rating: SegmentRating;
      confidence: RatingConfidence;
      note: string;
    }[];
  }) => apiFetch<{ saved: string; segments: number }>('/api/eval/ratings', {
    method: 'POST',
    body: JSON.stringify(body),
  }),
};
