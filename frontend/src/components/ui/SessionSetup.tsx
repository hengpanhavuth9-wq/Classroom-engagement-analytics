'use client';
import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { Classroom } from '@/lib/types';
import { Brain, Loader2, Zap } from 'lucide-react';
import Link from 'next/link';

// Demo classrooms shown when backend is offline
const DEMO_CLASSROOMS: Classroom[] = [
  { id: 'demo-1', name: 'Room 101 — Computer Science', school_name: 'Demo School', capacity: 30 },
  { id: 'demo-2', name: 'Room 202 — Mathematics',      school_name: 'Demo School', capacity: 25 },
  { id: 'demo-3', name: 'Room 305 — Physics',          school_name: 'Demo School', capacity: 28 },
];

interface Props {
  onStart:  (classroomId: string, teacher: string, subject: string) => void;
  onDemo?:  () => void;
  loading:  boolean;
}

export function SessionSetup({ onStart, onDemo, loading }: Props) {
  const [classrooms, setClassrooms]   = useState<Classroom[]>(DEMO_CLASSROOMS);
  const [classroomId, setClassroomId] = useState(DEMO_CLASSROOMS[0].id);
  const [teacher, setTeacher]         = useState('');
  const [subject, setSubject]         = useState('');
  const [offline, setOffline]         = useState(false);

  useEffect(() => {
    api.listClassrooms().then((data) => {
      const list = data as Classroom[];
      if (list.length > 0) {
        setClassrooms(list);
        setClassroomId(list[0].id);
        setOffline(false);
      } else {
        setOffline(true);
      }
    }).catch(() => {
      setOffline(true);
      setClassrooms(DEMO_CLASSROOMS);
      setClassroomId(DEMO_CLASSROOMS[0].id);
    });
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!classroomId) return;
    onStart(classroomId, teacher, subject);
  };

  return (
    <main className="min-h-screen bg-gray-950 flex items-center justify-center px-6">
      <div className="w-full max-w-sm">
        <div className="mb-8">
          <div className="w-10 h-10 rounded-full bg-indigo-500/10 border border-indigo-500/20 grid place-items-center mb-4">
            <Brain className="w-5 h-5 text-indigo-400" />
          </div>
          <h1 className="text-xl font-semibold text-white">Start a session</h1>
          <p className="text-gray-500 text-sm mt-1">Set up monitoring for this classroom.</p>
        </div>

        {offline && (
          <div className="mb-4 flex items-center gap-2 bg-amber-500/10 border border-amber-500/20 rounded-[10px] px-3.5 py-2.5 text-amber-400 text-xs">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />
            Backend offline — showing demo classrooms.
          </div>
        )}

        <form onSubmit={handleSubmit} className="surface p-6 space-y-4">
          <div>
            <label className="block text-[11px] font-medium text-gray-500 mb-1.5 uppercase tracking-[0.08em]">Classroom</label>
            <select
              value={classroomId}
              onChange={(e) => setClassroomId(e.target.value)}
              className="focus-ring w-full bg-[#0c0d10] border border-[#22252b] rounded-[10px] px-3 py-2.5 text-white text-sm focus:outline-none focus:border-indigo-500/60 transition-colors"
              required
            >
              {classrooms.map((c) => (
                <option key={c.id} value={c.id}>{c.name} · {c.school_name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-medium text-gray-500 mb-1.5 uppercase tracking-[0.08em]">Teacher name</label>
            <input
              type="text"
              value={teacher}
              onChange={(e) => setTeacher(e.target.value)}
              placeholder="e.g. Ms. Nguyen"
              className="focus-ring w-full bg-[#0c0d10] border border-[#22252b] rounded-[10px] px-3 py-2.5 text-white text-sm placeholder:text-gray-600 focus:outline-none focus:border-indigo-500/60 transition-colors"
            />
          </div>

          <div>
            <label className="block text-[11px] font-medium text-gray-500 mb-1.5 uppercase tracking-[0.08em]">Subject</label>
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="e.g. Mathematics"
              className="focus-ring w-full bg-[#0c0d10] border border-[#22252b] rounded-[10px] px-3 py-2.5 text-white text-sm placeholder:text-gray-600 focus:outline-none focus:border-indigo-500/60 transition-colors"
            />
          </div>

          <div className="flex gap-2.5 pt-2">
            {/* Demo Mode button — always available */}
            {onDemo && (
              <button
                type="button"
                onClick={onDemo}
                className="flex-1 py-2.5 bg-indigo-500/10 hover:bg-indigo-500/15 border border-indigo-500/20 text-indigo-300 font-medium rounded-[10px] transition-colors flex items-center justify-center gap-1.5 text-sm"
              >
                <Zap className="w-3.5 h-3.5" />
                Demo mode
              </button>
            )}
            <button
              type="submit"
              disabled={loading || !classroomId}
              className="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-medium rounded-[10px] transition-colors flex items-center justify-center gap-1.5 text-sm"
            >
              {loading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              {loading ? 'Starting…' : 'Start session'}
            </button>
          </div>
        </form>

        <p className="text-center text-xs text-gray-600 mt-5">
          <Link href="/admin" className="hover:text-gray-400 transition-colors">Admin overview →</Link>
        </p>
      </div>
    </main>
  );
}
