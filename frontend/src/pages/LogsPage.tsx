import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, ChevronLeft, ChevronRight, FileJson } from 'lucide-react'
import { api, type LogSummary, type LogDetail } from '@/lib/api'
import { cn, formatDate, VERDICT_COLORS, VERDICT_LABELS } from '@/lib/utils'

export default function LogsPage() {
  const [page, setPage] = useState(1)
  const [verdict, setVerdict] = useState('')
  const [selected, setSelected] = useState<LogDetail | null>(null)
  const PER_PAGE = 20

  const { data, isLoading } = useQuery({
    queryKey: ['logs', page, verdict],
    queryFn: () => api.logs.list({ page, per_page: PER_PAGE, verdict: verdict || undefined }),
  })

  const totalPages = data ? Math.ceil(data.total / PER_PAGE) : 1

  async function openDetail(item: LogSummary) {
    const detail = await api.logs.get(item.id)
    setSelected(detail)
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Review Logs</h1>
          <p className="text-sm text-slate-500 mt-0.5">{data?.total ?? 0} total reviews</p>
        </div>
        <select
          value={verdict}
          onChange={e => { setVerdict(e.target.value); setPage(1) }}
          className="border border-slate-200 rounded-lg text-sm px-3 py-2 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="">All verdicts</option>
          <option value="approve">Approved</option>
          <option value="request_changes">Changes Requested</option>
          <option value="block">Blocked</option>
        </select>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
          </div>
        ) : !data?.items?.length ? (
          <div className="text-center py-16 text-slate-400">No review logs yet</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50">
                {['Repository', 'PR', 'Verdict', 'Score', 'Issues', 'Date'].map(h => (
                  <th key={h} className="text-left px-4 py-3 font-medium text-slate-500 text-xs">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {data.items.map(l => (
                <tr
                  key={l.id}
                  className="hover:bg-slate-50/50 transition-colors cursor-pointer"
                  onClick={() => openDetail(l)}
                >
                  <td className="px-4 py-3 text-slate-700 font-medium">{l.repo_full_name}</td>
                  <td className="px-4 py-3 text-slate-500">
                    #{l.pr_number}
                    {l.pr_title && <span className="block text-xs text-slate-400 truncate max-w-48">{l.pr_title}</span>}
                  </td>
                  <td className="px-4 py-3">
                    {l.verdict ? (
                      <span className={cn('text-xs font-medium px-2 py-0.5 rounded-full border', VERDICT_COLORS[l.verdict] ?? 'bg-slate-100 text-slate-600')}>
                        {VERDICT_LABELS[l.verdict] ?? l.verdict}
                      </span>
                    ) : '—'}
                  </td>
                  <td className="px-4 py-3 text-slate-600">{l.score ?? '—'}</td>
                  <td className="px-4 py-3">
                    <span className="text-slate-500">{l.issues_count}</span>
                    {l.critical_count > 0 && (
                      <span className="ml-1 text-xs text-red-500">({l.critical_count} critical)</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-400">{formatDate(l.reviewed_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-40 transition"
          >
            <ChevronLeft className="w-4 h-4 text-slate-500" />
          </button>
          <span className="text-sm text-slate-500">Page {page} of {totalPages}</span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-40 transition"
          >
            <ChevronRight className="w-4 h-4 text-slate-500" />
          </button>
        </div>
      )}

      {/* Detail drawer */}
      {selected && (
        <div className="fixed inset-0 bg-black/30 z-50 flex" onClick={() => setSelected(null)}>
          <div
            className="ml-auto w-full max-w-lg bg-white h-full shadow-2xl overflow-y-auto"
            onClick={e => e.stopPropagation()}
          >
            <div className="sticky top-0 bg-white border-b border-slate-200 px-5 py-4 flex items-center justify-between">
              <div>
                <p className="font-semibold text-slate-800">
                  {selected.repo_full_name} #{selected.pr_number}
                </p>
                <p className="text-xs text-slate-400 mt-0.5">{selected.pr_title}</p>
              </div>
              <button onClick={() => setSelected(null)} className="text-slate-400 hover:text-slate-600 text-xl">×</button>
            </div>
            <div className="p-5 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: 'Verdict', value: selected.verdict ? <span className={cn('text-xs px-2 py-0.5 rounded-full border', VERDICT_COLORS[selected.verdict] ?? '')}>{VERDICT_LABELS[selected.verdict] ?? selected.verdict}</span> : '—' },
                  { label: 'Score', value: selected.score ?? '—' },
                  { label: 'Issues', value: selected.issues_count },
                  { label: 'Critical', value: selected.critical_count },
                  { label: 'Merged', value: selected.merged ? 'Yes' : 'No' },
                  { label: 'Author', value: selected.author ?? '—' },
                ].map(({ label, value }) => (
                  <div key={label} className="bg-slate-50 rounded-lg p-3">
                    <p className="text-xs text-slate-400">{label}</p>
                    <div className="text-sm font-semibold text-slate-800 mt-1">{value}</div>
                  </div>
                ))}
              </div>
              {selected.review_json && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <FileJson className="w-4 h-4 text-slate-400" />
                    <span className="text-sm font-medium text-slate-600">Full Review JSON</span>
                  </div>
                  <pre className="bg-slate-900 text-slate-300 text-xs p-4 rounded-xl overflow-x-auto scrollbar-thin max-h-80">
                    {JSON.stringify(JSON.parse(selected.review_json), null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
