'use client';
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ReferenceLine, ResponsiveContainer, CartesianGrid,
} from 'recharts';
import { LiveMetrics } from '@/lib/types';

type TimelineDataPoint = LiveMetrics | { time: number; engagement: number };

interface Props { data: TimelineDataPoint[] }

export function TimelineLine({ data }: Props) {
  if (data.length === 0) {
    return (
      <div className="h-44 flex items-center justify-center text-gray-600 text-sm">
        Timeline will appear here…
      </div>
    );
  }

  const isLiveMetrics = (d: TimelineDataPoint): d is LiveMetrics =>
    'class_engagement' in d;

  const chartData = data.map((m, i) => ({
    index:      i,
    engagement: isLiveMetrics(m) ? m.class_engagement : m.engagement,
  }));

  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={chartData} margin={{ top: 4, right: 4, left: -18, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1b1d22" vertical={false} />
        <XAxis dataKey="index" hide />
        <YAxis domain={[0, 100]} stroke="#3a3d45" tick={{ fill: '#5b5f6b', fontSize: 11 }} unit="%" />
        <Tooltip
          contentStyle={{ backgroundColor: '#15171c', border: '1px solid #22252b', borderRadius: 10, fontSize: 12 }}
          labelFormatter={() => ''}
          formatter={(v: number) => [`${v.toFixed(1)}%`, 'Engagement']}
        />
        <ReferenceLine y={50} stroke="#ef5f6b" strokeDasharray="4 4" strokeOpacity={0.4} />
        <Line
          type="monotone" dataKey="engagement"
          stroke="#6d7bfa" strokeWidth={2} dot={false}
          activeDot={{ r: 4, fill: '#6d7bfa' }}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
