'use client';
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';

interface Props { value: number }

const TRACK = '#1b1d22';

export function EngagementGauge({ value }: Props) {
  const clamped = Math.min(100, Math.max(0, value));
  const color   = clamped >= 70 ? '#3ecf8e' : clamped >= 45 ? '#e8a33d' : '#ef5f6b';
  const label   = clamped >= 70 ? 'Engaged' : clamped >= 45 ? 'Mixed' : 'Low';
  const data    = [
    { name: 'engaged', value: clamped },
    { name: 'gap',     value: 100 - clamped },
  ];

  return (
    <div className="relative flex items-center justify-center" style={{ height: 180 }}>
      <ResponsiveContainer width="100%" height={180}>
        <PieChart>
          <Pie
            data={data}
            cx="50%" cy="80%"
            startAngle={180} endAngle={0}
            innerRadius={64} outerRadius={78}
            dataKey="value"
            stroke="none"
            paddingAngle={0}
            isAnimationActive
          >
            <Cell fill={color} />
            <Cell fill={TRACK} />
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div className="absolute bottom-4 text-center">
        <p className="text-4xl font-semibold tabular-nums" style={{ color }}>{clamped.toFixed(0)}%</p>
        <p className="text-xs text-gray-500 mt-1">{label} · class engagement</p>
      </div>
    </div>
  );
}
