'use client';
import { PieChart, Pie, Cell, Legend, Tooltip, ResponsiveContainer } from 'recharts';
import { LiveMetrics } from '@/lib/types';

const STATE_COLORS: Record<string, string> = {
  on_task:   '#3ecf8e',
  desk_work: '#6d9bfa',
  off_task:  '#e8a33d',
  unknown:   '#4b4f58',
};

const STATE_LABELS: Record<string, string> = {
  on_task:   'On task',
  desk_work: 'Desk work',
  off_task:  'Off task',
  unknown:   'Unknown (not scored)',
};

interface Props {
  counts?: LiveMetrics['state_counts'];
}

export function AttentionBreakdown({ counts }: Props) {
  if (!counts) {
    return (
      <div className="h-44 flex items-center justify-center text-gray-600 text-sm">
        Waiting for data…
      </div>
    );
  }

  const data = Object.entries(counts)
    .filter(([, v]) => v > 0)
    .map(([name, value]) => ({ name, value }));

  if (data.length === 0) {
    return (
      <div className="h-44 flex items-center justify-center text-gray-600 text-sm">
        No faces detected
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={180}>
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="name"
          cx="50%" cy="50%"
          outerRadius={64}
          innerRadius={40}
          paddingAngle={3}
          stroke="none"
        >
          {data.map((entry) => (
            <Cell
              key={entry.name}
              fill={STATE_COLORS[entry.name] ?? '#4b4f58'}
            />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{ backgroundColor: '#15171c', border: '1px solid #22252b', borderRadius: 10, fontSize: 12 }}
          formatter={(v: number, name: string) => [v, STATE_LABELS[name] ?? name]}
        />
        <Legend
          iconSize={8}
          formatter={(value) => (
            <span className="text-xs text-gray-400">{STATE_LABELS[value] ?? value}</span>
          )}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
