import { Link } from 'react-router-dom'
import { ExternalLink, CheckCircle2, XCircle, Circle } from 'lucide-react'
import type { RepoSummary } from '@/lib/api'
import { cn, VERDICT_COLORS, VERDICT_LABELS, formatRelative } from '@/lib/utils'

interface Props {
  repos: RepoSummary[]
}

function ScoreBadge({ score }: { score: number | null }) {
  if (score == null) return <span className="text-slate-400 text-sm">—</span>
  const color = score >= 80 ? 'text-emerald-600' : score >= 60 ? 'text-amber-600' : 'text-red-600'
  return <span className={cn('font-semibold text-sm', color)}>{score}</span>
}

function WebhookStatus({ active }: { active: boolean }) {
  return active ? (
    <span className="flex items-center gap-1.5 text-xs text-emerald-600">
      <CheckCircle2 className="w-3.5 h-3.5" /> Active
    </span>
  ) : (
    <span className="flex items-center gap-1.5 text-xs text-slate-400">
      <Circle className="w-3.5 h-3.5" /> Inactive
    </span>
  )
}

export default function RepoTable({ repos }: Props) {
  if (repos.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
        <XCircle className="w-10 h-10 text-slate-300 mx-auto mb-3" />
        <p className="text-slate-500 font-medium">No repositories yet</p>
        <p className="text-slate-400 text-sm mt-1">Add your first repo to get started</p>
        <Link
          to="/repos/add"
          className="inline-block mt-4 bg-indigo-600 text-white text-sm font-medium px-4 py-2 rounded-lg hover:bg-indigo-700 transition-colors"
        >
          Add Repository
        </Link>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-100 bg-slate-50">
            <th className="text-left px-4 py-3 font-medium text-slate-500">Repository</th>
            <th className="text-left px-4 py-3 font-medium text-slate-500">Status</th>
            <th className="text-left px-4 py-3 font-medium text-slate-500">Last Verdict</th>
            <th className="text-left px-4 py-3 font-medium text-slate-500">Score</th>
            <th className="text-left px-4 py-3 font-medium text-slate-500">Last Review</th>
            <th className="text-left px-4 py-3 font-medium text-slate-500">Recipients</th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-50">
          {repos.map(repo => (
            <tr key={repo.id} className="hover:bg-slate-50/50 transition-colors">
              <td className="px-4 py-3">
                <Link to={`/repos/${repo.id}`} className="font-medium text-slate-800 hover:text-indigo-600 transition-colors">
                  {repo.display_name || repo.repo_full_name}
                </Link>
                {repo.display_name && (
                  <p className="text-xs text-slate-400 mt-0.5">{repo.repo_full_name}</p>
                )}
              </td>
              <td className="px-4 py-3">
                <WebhookStatus active={repo.webhook_active} />
              </td>
              <td className="px-4 py-3">
                {repo.last_verdict ? (
                  <span className={cn('inline-block text-xs font-medium px-2 py-0.5 rounded-full border', VERDICT_COLORS[repo.last_verdict] ?? 'bg-slate-100 text-slate-600')}>
                    {VERDICT_LABELS[repo.last_verdict] ?? repo.last_verdict}
                  </span>
                ) : (
                  <span className="text-slate-400 text-xs">No reviews yet</span>
                )}
              </td>
              <td className="px-4 py-3">
                <ScoreBadge score={repo.last_score} />
              </td>
              <td className="px-4 py-3 text-slate-500 text-xs">
                {formatRelative(repo.last_reviewed_at)}
              </td>
              <td className="px-4 py-3 text-slate-500 text-xs">
                {repo.recipient_count} recipient{repo.recipient_count !== 1 ? 's' : ''}
              </td>
              <td className="px-4 py-3">
                <Link to={`/repos/${repo.id}`} className="text-slate-400 hover:text-indigo-600 transition-colors">
                  <ExternalLink className="w-4 h-4" />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
