import { NavLink, useNavigate } from 'react-router-dom'
import { LayoutDashboard, GitFork, ScrollText, Settings, LogOut, Zap } from 'lucide-react'
import { clearToken } from '@/lib/auth'
import { cn } from '@/lib/utils'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

const NAV = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard', end: true },
  { to: '/repos/add', icon: GitFork, label: 'Add Repository' },
  { to: '/logs', icon: ScrollText, label: 'Review Logs' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export default function Sidebar() {
  const navigate = useNavigate()
  const { data: stats } = useQuery({
    queryKey: ['stats'],
    queryFn: api.dashboard.stats,
    refetchInterval: 30_000,
  })

  function handleLogout() {
    clearToken()
    navigate('/login', { replace: true })
  }

  return (
    <aside className="fixed inset-y-0 left-0 w-60 flex flex-col bg-navy-900 text-slate-300 z-30">
      {/* Logo */}
      <div className="flex items-center gap-3 px-6 py-5 border-b border-navy-700">
        <div className="w-8 h-8 rounded-lg bg-indigo-500 flex items-center justify-center flex-shrink-0">
          <Zap className="w-4 h-4 text-white" />
        </div>
        <div>
          <p className="text-white font-semibold text-sm leading-none">PR Review</p>
          <p className="text-slate-400 text-xs mt-0.5">Agent Dashboard</p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto scrollbar-thin">
        {NAV.map(({ to, icon: Icon, label, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                isActive
                  ? 'bg-indigo-500/20 text-indigo-300'
                  : 'hover:bg-navy-700 hover:text-slate-100',
              )
            }
          >
            <Icon className="w-4 h-4 flex-shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Status footer */}
      <div className="px-5 py-4 border-t border-navy-700">
        <div className="flex items-center gap-2 mb-3">
          <span
            className={cn(
              'w-2 h-2 rounded-full',
              (stats?.repos_active ?? 0) > 0 ? 'bg-emerald-400' : 'bg-slate-500',
            )}
          />
          <span className="text-xs text-slate-400">
            {stats?.repos_active ?? 0} webhook{stats?.repos_active !== 1 ? 's' : ''} active
          </span>
        </div>
        <button
          onClick={handleLogout}
          className="flex items-center gap-2 text-xs text-slate-400 hover:text-slate-200 transition-colors"
        >
          <LogOut className="w-3.5 h-3.5" />
          Sign out
        </button>
      </div>
    </aside>
  )
}
