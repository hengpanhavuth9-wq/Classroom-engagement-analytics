'use client';
import { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { api } from '@/lib/api';
import { ClassroomSummary } from '@/lib/types';
import Link from 'next/link';
import { ArrowLeft, TrendingUp } from 'lucide-react';

export default function AdminOverview() {
  const [classrooms, setClassrooms] = useState<ClassroomSummary[]>([]);
  const [loading, setLoading]       = useState(true);

  useEffect(() => {
    api.getClassroomsSummary()
      .then((data) => setClassrooms(data as ClassroomSummary[]))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const getBarColor = (val: number) =>
    val >= 70 ? '#3ecf8e' : val >= 45 ? '#e8a33d' : '#ef5f6b';

  return (
    <main className="min-h-screen bg-gray-950 text-white">
      <header className="border-b border-[#181a1f] px-6 py-4 flex items-center gap-4">
        <Link href="/" className="text-gray-500 hover:text-gray-300 transition-colors">
          <ArrowLeft className="w-4.5 h-4.5" />
        </Link>
        <h1 className="text-[15px] font-semibold tracking-tight">ReLi <span className="text-gray-600 font-normal">/ Admin</span></h1>
        <TrendingUp className="w-4 h-4 text-indigo-400 ml-auto" />
      </header>

      <div className="p-6 space-y-5 max-w-[1400px] mx-auto">
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <>
            {/* Bar Chart */}
            <section className="surface p-6">
              <h2 className="text-[11px] font-medium text-gray-500 uppercase tracking-[0.08em] mb-6">
                Average engagement by classroom
              </h2>
              {classrooms.length === 0 ? (
                <p className="text-gray-600 text-sm text-center py-12">No classroom data yet. Start a session to see analytics.</p>
              ) : (
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={classrooms} barSize={28}>
                    <XAxis dataKey="classroom_name" stroke="#3a3d45" tick={{ fill: '#8b8f99', fontSize: 12 }} />
                    <YAxis domain={[0, 100]} stroke="#3a3d45" tick={{ fill: '#8b8f99' }} unit="%" />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#15171c', border: '1px solid #22252b', borderRadius: 10, fontSize: 12 }}
                      formatter={(v: number) => [`${v.toFixed(1)}%`, 'Avg engagement']}
                    />
                    <Bar dataKey="avg_engagement" radius={[5, 5, 0, 0]}>
                      {classrooms.map((c, i) => (
                        <Cell key={i} fill={getBarColor(c.avg_engagement)} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </section>

            {/* Classroom Cards */}
            <section className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3.5">
              {classrooms.map((c) => (
                <div
                  key={c.classroom_name}
                  className="surface-quiet p-5 transition-card"
                >
                  <p className="text-sm text-gray-400 font-medium">{c.classroom_name}</p>
                  <p
                    className="text-[34px] leading-none font-semibold mt-2.5 tabular-nums"
                    style={{ color: getBarColor(c.avg_engagement) }}
                  >
                    {c.avg_engagement.toFixed(0)}%
                  </p>
                  <p className="text-xs text-gray-600 mt-1.5">{c.sessions_today} sessions today</p>
                </div>
              ))}
            </section>
          </>
        )}
      </div>
    </main>
  );
}
