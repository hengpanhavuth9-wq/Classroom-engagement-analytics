import { Alert } from '@/lib/types';
import { AlertTriangle } from 'lucide-react';

interface Props { alert: Alert }

export function AlertBanner({ alert }: Props) {
  return (
    <div className="animate-fade-in flex items-center gap-3 bg-red-500/[0.07] border border-red-500/20 rounded-[14px] px-4 py-3">
      <span className="grid place-items-center w-8 h-8 rounded-full bg-red-500/10 shrink-0">
        <AlertTriangle className="w-4 h-4 text-red-400" />
      </span>
      <div className="min-w-0">
        <p className="text-sm font-medium text-red-300">Low engagement</p>
        <p className="text-xs text-gray-500 truncate">{alert.message}</p>
      </div>
      <span className="ml-auto text-xl font-semibold text-red-400 tabular-nums">{alert.score.toFixed(0)}%</span>
    </div>
  );
}
