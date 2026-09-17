import Link from 'next/link';
import { Brain, BarChart3, Shield, Crosshair } from 'lucide-react';

const FEATURES = [
  { icon: Crosshair, title: 'Gaze-calibrated',  desc: 'Head pose + eye gaze, relative to each student’s own "looking at the board" reference' },
  { icon: Shield,     title: 'Privacy-first',    desc: 'Raw video never touches disk or leaves the process — only aggregates cross the boundary' },
  { icon: Brain,      title: 'Real-time',        desc: 'WebSocket updates to the dashboard as each frame is scored' },
  { icon: BarChart3,  title: 'Class insights',   desc: 'Trends, session history, and low-engagement alerts' },
];

export default function HomePage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center bg-gray-950 px-6">
      {/* Hero */}
      <div className="text-center mb-14 animate-fade-in">
        <div className="inline-flex items-center gap-2 bg-indigo-500/10 border border-indigo-500/20 rounded-full px-3.5 py-1 text-indigo-300 text-xs font-medium mb-6">
          <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse-dot" />
          Privacy-preserving · Real-time
        </div>
        <h1 className="text-6xl font-semibold tracking-tight text-white mb-3">
          Re<span className="text-indigo-500">Li</span>
        </h1>
        <p className="text-xl font-normal text-gray-400 mb-2.5">Classroom engagement analytics</p>
        <p className="text-gray-500 max-w-md mx-auto text-sm leading-relaxed">
          Real-time engagement monitoring from where students are looking.
          No video stored. No faces identified. Only class-level insight.
        </p>
      </div>

      {/* CTA Buttons */}
      <div className="flex flex-col sm:flex-row gap-3 mb-16">
        <Link
          href="/teacher"
          className="px-7 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white font-medium rounded-[10px] transition-colors text-center text-sm"
        >
          Teacher dashboard
        </Link>
        <Link
          href="/admin"
          className="px-7 py-2.5 bg-transparent hover:bg-white/5 text-gray-300 font-medium rounded-[10px] border border-[#22252b] transition-colors text-center text-sm"
        >
          Admin overview
        </Link>
      </div>

      {/* Feature Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 max-w-4xl w-full">
        {FEATURES.map(({ icon: Icon, title, desc }) => (
          <div
            key={title}
            className="surface-quiet p-5 transition-card"
          >
            <Icon className="w-5 h-5 text-indigo-400 mb-3" strokeWidth={1.75} />
            <p className="font-medium text-white mb-1 text-sm">{title}</p>
            <p className="text-xs text-gray-500 leading-relaxed">{desc}</p>
          </div>
        ))}
      </div>
    </main>
  );
}
