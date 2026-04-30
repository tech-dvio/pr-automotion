import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { GitPullRequest, CheckCircle2, XCircle, Shield, BarChart2, Plus } from 'lucide-react'
import { api } from '@/lib/api'
import StatCard from '@/components/dashboard/StatCard'
import RepoTable from '@/components/dashboard/RepoTable'
import RecentActivity from '@/components/dashboard/RecentActivity'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

export default function DashboardPage() {
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['stats'],
    queryFn: api.dashboard.stats,
    refetchInterval: 30_000,
  })
  const { data: repos = [] } = useQuery({
    queryKey: ['repos'],
    queryFn: api.repos.list,
    refetchInterval: 30_000,
  })
  const { data: activity = [] } = useQuery({
    queryKey: ['activity'],
    queryFn: api.dashboard.recentActivity,
    refetchInterval: 30_000,
  })

  const chartData = [
    { label: 'Approved', value: stats?.approvals_today ?? 0, color: '#10B981' },
    { label: 'Changes', value: (stats?.prs_reviewed_today ?? 0) - (stats?.approvals_today ?? 0) - (stats?.blocks_today ?? 0), color: '#F59E0B' },
    { label: 'Blocked', value: stats?.blocks_today ?? 0, color: '#EF4444' },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Dashboard</h1>
          <p className="text-sm text-slate-500 mt-0.5">Overview of your PR review agent</p>
        </div>
        <Link
          to="/repos/add"
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          Add Repository
        </Link>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard
          title="Repos Monitored"
          value={statsLoading ? '…' : (stats?.repos_active ?? 0)}
          subtitle={`${stats?.repos_total ?? 0} total`}
          icon={GitPullRequest}
          iconBg="bg-indigo-100"
          iconColor="text-indigo-600"
        />
        <StatCard
          title="PRs Reviewed Today"
          value={statsLoading ? '…' : (stats?.prs_reviewed_today ?? 0)}
          subtitle={`${stats?.prs_reviewed_this_week ?? 0} this week`}
          icon={BarChart2}
          iconBg="bg-blue-100"
          iconColor="text-blue-600"
        />
        <StatCard
          title="Approved Today"
          value={statsLoading ? '…' : (stats?.approvals_today ?? 0)}
          icon={CheckCircle2}
          iconBg="bg-emerald-100"
          iconColor="text-emerald-600"
        />
        <StatCard
          title="Blocked Today"
          value={statsLoading ? '…' : (stats?.blocks_today ?? 0)}
          icon={XCircle}
          iconBg="bg-red-100"
          iconColor="text-red-600"
        />
        <StatCard
          title="Avg Score Today"
          value={statsLoading ? '…' : (stats?.avg_score_today != null ? `${stats.avg_score_today}` : '—')}
          subtitle="out of 100"
          icon={Shield}
          iconBg="bg-violet-100"
          iconColor="text-violet-600"
        />
      </div>

      {/* Main content grid */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Repo table (takes 2/3) */}
        <div className="xl:col-span-2 space-y-3">
          <h2 className="text-sm font-semibold text-slate-700">Active Repositories</h2>
          <RepoTable repos={repos} />
        </div>

        {/* Right column */}
        <div className="space-y-6">
          {/* Score distribution chart */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
            <h2 className="text-sm font-semibold text-slate-700 mb-4">Today's Outcomes</h2>
            <ResponsiveContainer width="100%" height={120}>
              <BarChart data={chartData} barCategoryGap="30%">
                <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#94A3B8' }} axisLine={false} tickLine={false} />
                <YAxis hide />
                <Tooltip
                  cursor={{ fill: '#F1F5F9' }}
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #E2E8F0' }}
                />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  {chartData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Recent activity */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
            <h2 className="text-sm font-semibold text-slate-700 mb-4">Recent Activity</h2>
            <RecentActivity items={activity} />
          </div>
        </div>
      </div>
    </div>
  )
}
