import { useLocation, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { cn } from '@/lib/utils'

const CRUMBS: Record<string, string> = {
  '/': 'Dashboard',
  '/repos/add': 'Add Repository',
  '/logs': 'Review Logs',
  '/settings': 'Settings',
}

export default function TopBar() {
  const { pathname } = useLocation()
  const label = pathname.startsWith('/repos/') && pathname !== '/repos/add'
    ? 'Repository Detail'
    : (CRUMBS[pathname] ?? 'Dashboard')

  const { data, isError } = useQuery({
    queryKey: ['health'],
    queryFn: () => fetch('/health').then(r => r.json()),
    refetchInterval: 60_000,
    retry: false,
  })

  const healthy = !isError && !!data

  return (
    <header className="sticky top-0 z-20 flex items-center justify-between h-14 px-6 bg-white border-b border-slate-200">
      <div className="flex items-center gap-2 text-sm">
        <Link to="/" className="text-slate-400 hover:text-slate-600 transition-colors">Dashboard</Link>
        {label !== 'Dashboard' && (
          <>
            <span className="text-slate-300">/</span>
            <span className="text-slate-700 font-medium">{label}</span>
          </>
        )}
      </div>
      <div className="flex items-center gap-2">
        <span
          className={cn(
            'w-2 h-2 rounded-full',
            healthy ? 'bg-emerald-400' : 'bg-slate-300',
          )}
        />
        <span className="text-xs text-slate-400">{healthy ? 'Agent online' : 'Connecting…'}</span>
      </div>
    </header>
  )
}
