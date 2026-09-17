import { clsx } from 'clsx';

interface Props {
  label:    string;
  value:    string | number;
  accent?:  'green' | 'yellow' | 'indigo' | 'red';
  hint?:    string;
}

const ACCENT_BAR = {
  green:  'bg-emerald-400',
  yellow: 'bg-amber-400',
  indigo: 'bg-indigo-400',
  red:    'bg-red-400',
};

export function KPICard({ label, value, accent, hint }: Props) {
  return (
    <div className="surface-quiet relative overflow-hidden p-4 transition-card">
      {accent && <span className={clsx('absolute top-0 left-0 h-0.5 w-full', ACCENT_BAR[accent])} />}
      <p className="text-[11px] font-medium text-gray-500 uppercase tracking-[0.08em] mb-2">{label}</p>
      <p className="text-[28px] leading-none font-semibold text-white tabular-nums">{value}</p>
      {hint && <p className="text-xs text-gray-600 mt-1.5">{hint}</p>}
    </div>
  );
}
