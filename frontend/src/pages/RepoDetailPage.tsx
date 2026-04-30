import { useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ExternalLink, Trash2, Zap, CheckCircle2, XCircle, Eye, EyeOff,
  Loader2, ArrowLeft, Shield,
} from 'lucide-react'
import { api } from '@/lib/api'
import { cn, formatDate, VERDICT_COLORS, VERDICT_LABELS, ROLE_LABELS, ROLE_COLORS } from '@/lib/utils'

type Tab = 'overview' | 'config' | 'recipients'

export default function RepoDetailPage() {
  const { id } = useParams<{ id: string }>()
  const repoId = Number(id)
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [tab, setTab] = useState<Tab>('overview')
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [revealed, setRevealed] = useState<Record<string, string>>({})
  const [revealing, setRevealing] = useState<string | null>(null)

  const { data: repo, isLoading } = useQuery({
    queryKey: ['repos', repoId],
    queryFn: () => api.repos.get(repoId),
    enabled: !!repoId,
  })

  const { data: logs } = useQuery({
    queryKey: ['logs', repoId],
    queryFn: () => api.logs.list({ repo_id: repoId, per_page: 5 }),
    enabled: !!repoId,
  })

  const deleteMutation = useMutation({
    mutationFn: () => api.repos.delete(repoId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['repos'] })
      navigate('/', { replace: true })
    },
  })

  const testWebhookMutation = useMutation({
    mutationFn: () => api.repos.testWebhook(repoId),
  })

  async function revealField(field: string) {
    setRevealing(field)
    try {
      const r = await api.repos.reveal(repoId, field)
      setRevealed(prev => ({ ...prev, [field]: r.value }))
    } finally {
      setRevealing(null)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
      </div>
    )
  }

  if (!repo) {
    return <div className="text-slate-500 text-center py-20">Repository not found</div>
  }

  const TABS: { id: Tab; label: string }[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'config', label: 'Configuration' },
    { id: 'recipients', label: 'Email Recipients' },
  ]

  return (
    <div className="max-w-3xl mx-auto space-y-5">
      {/* Header */}
      <div>
        <Link to="/" className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-600 mb-3 transition-colors">
          <ArrowLeft className="w-4 h-4" /> Dashboard
        </Link>
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-xl font-bold text-slate-900">
              {repo.display_name ?? repo.repo_full_name}
            </h1>
            {repo.display_name && <p className="text-sm text-slate-400 mt-0.5">{repo.repo_full_name}</p>}
          </div>
          <div className="flex items-center gap-2">
            {repo.webhook_active ? (
              <span className="flex items-center gap-1.5 text-xs text-emerald-600 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-full">
                <CheckCircle2 className="w-3.5 h-3.5" /> Webhook Active
              </span>
            ) : (
              <span className="flex items-center gap-1.5 text-xs text-slate-400 bg-slate-100 px-2.5 py-1 rounded-full">
                <XCircle className="w-3.5 h-3.5" /> Inactive
              </span>
            )}
            <a
              href={`https://github.com/${repo.repo_full_name}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-slate-400 hover:text-slate-600 transition-colors"
            >
              <ExternalLink className="w-4 h-4" />
            </a>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-200 gap-0">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              'px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors',
              tab === t.id
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-slate-500 hover:text-slate-700',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Overview Tab */}
      {tab === 'overview' && (
        <div className="space-y-5">
          {/* Metrics */}
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: 'Last Verdict', value: repo.last_verdict
                ? <span className={cn('text-xs font-medium px-2 py-0.5 rounded-full border', VERDICT_COLORS[repo.last_verdict])}>{VERDICT_LABELS[repo.last_verdict]}</span>
                : '—' },
              { label: 'Last Score', value: repo.last_score != null ? `${repo.last_score}/100` : '—' },
              { label: 'Last Review', value: formatDate(repo.last_reviewed_at) },
            ].map(m => (
              <div key={m.label} className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
                <p className="text-xs text-slate-500 font-medium">{m.label}</p>
                <div className="mt-1 text-sm font-semibold text-slate-800">{m.value}</div>
              </div>
            ))}
          </div>

          {/* Credentials (masked) */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-4">
            <h3 className="font-semibold text-slate-700 text-sm flex items-center gap-2">
              <Shield className="w-4 h-4" /> Credentials
            </h3>
            {(['github_token', 'webhook_secret'] as const).map(field => (
              <div key={field} className="flex items-center justify-between">
                <span className="text-sm text-slate-600 capitalize">{field.replace('_', ' ')}</span>
                <div className="flex items-center gap-2">
                  <code className="text-xs bg-slate-100 px-2 py-1 rounded font-mono text-slate-700">
                    {revealed[field] ? revealed[field] : '••••••••••••••••'}
                  </code>
                  <button
                    onClick={() => revealed[field] ? setRevealed(p => { const n = { ...p }; delete n[field]; return n }) : revealField(field)}
                    className="text-slate-400 hover:text-slate-600 transition-colors"
                    disabled={revealing === field}
                  >
                    {revealing === field
                      ? <Loader2 className="w-4 h-4 animate-spin" />
                      : revealed[field] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />
                    }
                  </button>
                </div>
              </div>
            ))}
            <div className="flex items-center justify-between text-sm text-slate-500 pt-1 border-t border-slate-100">
              <span>Webhook Hook ID</span>
              <code className="text-xs bg-slate-100 px-2 py-1 rounded font-mono">{repo.github_hook_id ?? '—'}</code>
            </div>
          </div>

          {/* Recent reviews */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
            <h3 className="font-semibold text-slate-700 text-sm mb-4">Recent Reviews</h3>
            {!logs?.items?.length ? (
              <p className="text-sm text-slate-400 text-center py-4">No reviews yet</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="text-left pb-2 text-xs text-slate-500 font-medium">PR</th>
                    <th className="text-left pb-2 text-xs text-slate-500 font-medium">Verdict</th>
                    <th className="text-left pb-2 text-xs text-slate-500 font-medium">Score</th>
                    <th className="text-left pb-2 text-xs text-slate-500 font-medium">Date</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {logs.items.map(l => (
                    <tr key={l.id}>
                      <td className="py-2 text-slate-700">#{l.pr_number} <span className="text-slate-400 text-xs">{l.pr_title}</span></td>
                      <td className="py-2">
                        {l.verdict ? (
                          <span className={cn('text-xs px-2 py-0.5 rounded-full border', VERDICT_COLORS[l.verdict] ?? 'bg-slate-100 text-slate-600')}>
                            {VERDICT_LABELS[l.verdict] ?? l.verdict}
                          </span>
                        ) : '—'}
                      </td>
                      <td className="py-2 text-slate-600">{l.score ?? '—'}</td>
                      <td className="py-2 text-xs text-slate-400">{formatDate(l.reviewed_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <div className="mt-3 pt-3 border-t border-slate-100">
              <Link to="/logs" state={{ repo_id: repoId }} className="text-xs text-indigo-600 hover:text-indigo-700">
                View all logs →
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Config Tab */}
      {tab === 'config' && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-4">
          {[
            { label: 'Auto Merge', value: repo.auto_merge ? `Yes (${repo.auto_merge_strategy})` : 'Disabled' },
            { label: 'Require Tests', value: repo.require_tests ? 'Yes' : 'No' },
            { label: 'Block on Severity', value: repo.block_on_severity.join(', ') || '—' },
            { label: 'Max File Changes', value: String(repo.max_file_changes) },
            { label: 'Protected Files', value: repo.protected_files.join(', ') || '—' },
            { label: 'Custom Rules', value: repo.custom_rules.join('\n') || '—' },
          ].map(({ label, value }) => (
            <div key={label} className="flex items-start gap-4">
              <span className="text-sm text-slate-500 w-40 flex-shrink-0">{label}</span>
              <span className={cn('text-sm text-slate-800 font-medium whitespace-pre-wrap', value === '—' && 'text-slate-400 font-normal')}>{value}</span>
            </div>
          ))}
          <div className="pt-3 border-t border-slate-100">
            <p className="text-xs text-slate-400">To update configuration, use the API or re-add the repository</p>
          </div>
        </div>
      )}

      {/* Recipients Tab */}
      {tab === 'recipients' && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
          {repo.email_recipients.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-6">No recipients configured</p>
          ) : (
            <div className="space-y-2">
              {repo.email_recipients.map(r => (
                <div key={r.id} className="flex items-center justify-between py-2 border-b border-slate-50 last:border-0">
                  <span className="text-sm text-slate-700">{r.email}</span>
                  <span className={cn('text-xs font-medium px-2 py-0.5 rounded-full', ROLE_COLORS[r.role] ?? 'bg-slate-100 text-slate-600')}>
                    {ROLE_LABELS[r.role] ?? r.role}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Danger Zone */}
      <div className="bg-white rounded-xl border border-red-200 p-5">
        <h3 className="font-semibold text-red-600 text-sm mb-3">Danger Zone</h3>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-slate-700 font-medium">Test Webhook Delivery</p>
            <p className="text-xs text-slate-400">Sends a ping event from GitHub to verify connectivity</p>
          </div>
          <button
            onClick={() => testWebhookMutation.mutate()}
            disabled={testWebhookMutation.isPending}
            className="flex items-center gap-2 text-sm border border-slate-200 px-3 py-2 rounded-lg hover:bg-slate-50 text-slate-600 transition"
          >
            {testWebhookMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
            Ping
          </button>
        </div>
        {testWebhookMutation.isSuccess && (
          <p className="text-xs text-emerald-600 mt-2">Ping sent successfully!</p>
        )}

        <div className="border-t border-slate-100 mt-4 pt-4 flex items-center justify-between">
          <div>
            <p className="text-sm text-slate-700 font-medium">Remove Webhook & Delete</p>
            <p className="text-xs text-slate-400">Removes the GitHub webhook and deletes this configuration</p>
          </div>
          {!showDeleteConfirm ? (
            <button
              onClick={() => setShowDeleteConfirm(true)}
              className="flex items-center gap-2 text-sm bg-red-50 border border-red-200 text-red-600 px-3 py-2 rounded-lg hover:bg-red-100 transition"
            >
              <Trash2 className="w-4 h-4" /> Remove
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">Sure?</span>
              <button
                onClick={() => deleteMutation.mutate()}
                disabled={deleteMutation.isPending}
                className="text-sm bg-red-600 text-white px-3 py-2 rounded-lg hover:bg-red-700 transition flex items-center gap-1"
              >
                {deleteMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                Yes, remove
              </button>
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="text-sm text-slate-500 hover:text-slate-700 px-3 py-2"
              >
                Cancel
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
