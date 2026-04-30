import { getToken } from './auth'

const BASE = ''

function headers(): HeadersInit {
  const token = getToken()
  return {
    'Content-Type': 'application/json',
    ...(token ? { 'X-Admin-Token': token } : {}),
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: headers(),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (res.status === 204) return undefined as T
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = err.detail
    const msg = Array.isArray(detail)
      ? detail.map((e: { msg?: string; loc?: string[] }) => e.msg ?? JSON.stringify(e)).join('; ')
      : detail || 'Request failed'
    throw new Error(msg)
  }
  return res.json()
}

export const api = {
  auth: {
    verify: (token: string) =>
      request<{ ok: boolean }>('POST', '/api/auth/verify', { token }),
  },
  dashboard: {
    stats: () => request<DashboardStats>('GET', '/api/dashboard/stats'),
    recentActivity: () => request<ActivityItem[]>('GET', '/api/dashboard/recent-activity'),
  },
  repos: {
    list: () => request<RepoSummary[]>('GET', '/api/repos'),
    get: (id: number) => request<RepoDetail>('GET', `/api/repos/${id}`),
    create: (data: RepoCreate) => request<RepoDetail>('POST', '/api/repos', data),
    update: (id: number, data: Partial<RepoCreate>) =>
      request<RepoDetail>('PUT', `/api/repos/${id}`, data),
    delete: (id: number) => request<void>('DELETE', `/api/repos/${id}`),
    testToken: (token: string) =>
      request<TestConnectionResponse>('POST', '/api/repos/test-token', { github_token: token }),
    testConnection: (id: number) =>
      request<TestConnectionResponse>('POST', `/api/repos/${id}/test-connection`),
    testWebhook: (id: number) => request<{ ok: boolean }>('POST', `/api/repos/${id}/test-webhook`),
    reveal: (id: number, field: string) =>
      request<{ value: string }>('POST', `/api/repos/${id}/reveal`, { field }),
  },
  logs: {
    list: (params?: { repo_id?: number; verdict?: string; page?: number; per_page?: number }) => {
      const qs = new URLSearchParams()
      if (params?.repo_id) qs.set('repo_id', String(params.repo_id))
      if (params?.verdict) qs.set('verdict', params.verdict)
      if (params?.page) qs.set('page', String(params.page))
      if (params?.per_page) qs.set('per_page', String(params.per_page))
      return request<LogListResponse>('GET', `/api/logs?${qs}`)
    },
    get: (id: number) => request<LogDetail>('GET', `/api/logs/${id}`),
  },
  settings: {
    get: () => request<Record<string, string>>('GET', '/api/settings'),
    update: (data: Record<string, string>) => request<{ ok: boolean }>('PUT', '/api/settings', data),
  },
}

// Types
export interface DashboardStats {
  repos_total: number
  repos_active: number
  prs_reviewed_today: number
  prs_reviewed_this_week: number
  approvals_today: number
  blocks_today: number
  critical_issues_today: number
  avg_score_today: number | null
}

export interface ActivityItem {
  id: number
  repo_full_name: string
  pr_number: number
  pr_title: string | null
  verdict: string | null
  score: number | null
  reviewed_at: string
}

export interface EmailRecipient {
  id?: number
  email: string
  role: string
}

export interface RepoSummary {
  id: number
  repo_full_name: string
  display_name: string | null
  webhook_active: boolean
  github_hook_id: number | null
  auto_merge: boolean
  created_at: string
  updated_at: string
  recipient_count: number
  last_verdict: string | null
  last_score: number | null
  last_reviewed_at: string | null
}

export interface RepoDetail extends RepoSummary {
  auto_merge_strategy: string
  require_tests: boolean
  block_on_severity: string[]
  protected_files: string[]
  custom_rules: string[]
  max_file_changes: number
  github_token_masked: string
  webhook_secret_masked: string
  email_recipients: EmailRecipient[]
}

export interface RepoCreate {
  repo_full_name: string
  display_name?: string
  github_token: string
  webhook_secret?: string
  auto_merge: boolean
  auto_merge_strategy: string
  require_tests: boolean
  block_on_severity: string[]
  protected_files: string[]
  custom_rules: string[]
  max_file_changes: number
  email_recipients: EmailRecipient[]
}

export interface TestConnectionResponse {
  valid: boolean
  login: string | null
  error: string | null
}

export interface LogSummary {
  id: number
  repo_full_name: string
  pr_number: number
  pr_title: string | null
  author: string | null
  verdict: string | null
  score: number | null
  issues_count: number
  critical_count: number
  high_count: number
  merged: boolean
  reviewed_at: string
}

export interface LogDetail extends LogSummary {
  review_json: string | null
}

export interface LogListResponse {
  total: number
  page: number
  per_page: number
  items: LogSummary[]
}
