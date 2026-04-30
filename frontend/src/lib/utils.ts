import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export const VERDICT_COLORS: Record<string, string> = {
  approve: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  request_changes: 'bg-amber-100 text-amber-700 border-amber-200',
  block: 'bg-red-100 text-red-700 border-red-200',
}

export const VERDICT_LABELS: Record<string, string> = {
  approve: 'Approved',
  request_changes: 'Changes Requested',
  block: 'Blocked',
}

export const ROLE_LABELS: Record<string, string> = {
  critical: 'Critical Alerts',
  high: 'High Severity',
  block: 'PR Blocked',
  merge: 'PR Merged',
  approve: 'PR Approved',
  digest: 'Daily Digest',
}

export const ROLE_COLORS: Record<string, string> = {
  critical: 'bg-red-100 text-red-700',
  high: 'bg-orange-100 text-orange-700',
  block: 'bg-red-100 text-red-700',
  merge: 'bg-blue-100 text-blue-700',
  approve: 'bg-emerald-100 text-emerald-700',
  digest: 'bg-slate-100 text-slate-700',
}
