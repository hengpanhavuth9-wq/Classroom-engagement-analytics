'use client';
import { useEffect, useRef, useCallback } from 'react';
import { useEngagementStore } from '@/store/engagementStore';
import { LiveMetrics, Alert } from '@/lib/types';
import { wsToken } from '@/lib/api';

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000';

export function useEngagementSocket(sessionId: string | null) {
  const { setMetrics, addAlert, setConnected } = useEngagementStore();
  const wsRef     = useRef<WebSocket | null>(null);
  const retryRef  = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Set right before we close the socket ourselves, so its `onclose` knows
  // not to schedule a reconnect. Without this, unmounting (e.g. ending the
  // session) still fired onclose *after* cleanup ran, which reconnected to
  // the now-stale sessionId forever.
  const closingRef = useRef(false);

  const connect = useCallback(() => {
    if (!sessionId) return;
    closingRef.current = false;

    const token = wsToken();
    const url = token
      ? `${WS_BASE}/ws/dashboard/${sessionId}?token=${encodeURIComponent(token)}`
      : `${WS_BASE}/ws/dashboard/${sessionId}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);

    ws.onclose = () => {
      setConnected(false);
      if (closingRef.current) return;
      // Auto-reconnect after 3 seconds
      retryRef.current = setTimeout(connect, 3000);
    };

    ws.onerror = () => ws.close();

    ws.onmessage = (event: MessageEvent<string>) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'low_engagement') {
          addAlert(data as Alert);
        } else {
          setMetrics({ ...data, timestamp: Date.now() } as LiveMetrics);
        }
      } catch {
        // Ignore malformed messages
      }
    };
  }, [sessionId, setMetrics, addAlert, setConnected]);

  useEffect(() => {
    connect();
    return () => {
      closingRef.current = true;
      if (retryRef.current) clearTimeout(retryRef.current);
      wsRef.current?.close();
    };
  }, [connect]);
}
