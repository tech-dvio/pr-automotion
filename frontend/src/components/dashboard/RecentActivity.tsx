import { CheckCircle2, XCircle, AlertCircle, Clock } from 'lucide-react'
import { cn, formatRelative, VERDICT_COLORS } from '@/lib/utils'
import type { ActivityItem } from '@/lib/api'

const ICONS: Record<string, React.ElementType> = {
  approve: CheckCircle2,
  request_changes: AlertCircle,
  block: XCircle,
}

const ICON_COLORS: Record<string, string> = {
  approve: 'text-emerald-500',
  request_changes: 'text-amber-500',
  block: 'text-red-500',
}

export default function RecentActivity({ items }: { items: ActivityItem[] }) {
  if (items.length === 0) {
    return (
      <div className="py-8 text-center text-slate-400 text-sm">
        No review activity yet
      </div>
    )
  }
  return (
    <div className="space-y-3">
      {items.map(item => {
        const Icon = item.verdict ? (ICONS[item.verdict] ?? Clock) : Clock
        const iconColor = item.verdict ? (ICON_COLORS[item.verdict] ?? 'text-slate-400') : 'text-slate-400'
        return (
          <div key={item.id} className="flex items-start gap-3">
            <Icon className={cn('w-4 h-4 mt-0.5 flex-shrink-0', iconColor)} />
            <div className="min-w-0 flex-1">
              <p className="text-sm text-slate-800 truncate">
                <span className="font-medium">{item.repo_full_name}</span>
                {' '}<span className="text-slate-500">#{item.pr_number}</span>
                {item.pr_title && <span className="text-slate-500"> — {item.pr_title}</span>}
              </p>
              <div className="flex items-center gap-2 mt-0.5">
                {item.verdict && (
                  <span className={cn('text-xs font-medium px-1.5 py-0.5 rounded border', VERDICT_COLORS[item.verdict] ?? 'bg-slate-100 text-slate-600')}>
                    {item.verdict.replace('_', ' ')}
                  </span>
                )}
                {item.score != null && (
                  <span className="text-xs text-slate-400">Score: {item.score}</span>
                )}
                <span className="text-xs text-slate-400">{formatRelative(item.reviewed_at)}</span>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
