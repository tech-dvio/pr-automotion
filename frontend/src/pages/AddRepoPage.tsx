import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm, useFieldArray, Controller } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Eye, EyeOff, RefreshCw, Plus, Trash2, CheckCircle2, XCircle, Loader2,
} from 'lucide-react'
import { api, type RepoCreate } from '@/lib/api'
import { cn, ROLE_LABELS } from '@/lib/utils'

const schema = z.object({
  repo_full_name: z.string().regex(/^[\w\-\.]+\/[\w\-\.]+$/, 'Must be "owner/repo" format'),
  display_name: z.string().optional(),
  github_token: z.string().min(1, 'Required'),
  webhook_secret: z.string().optional(),
  auto_merge: z.boolean(),
  auto_merge_strategy: z.enum(['squash', 'merge', 'rebase']),
  require_tests: z.boolean(),
  block_on_severity: z.array(z.string()),
  protected_files: z.array(z.string()),
  custom_rules: z.string(),
  max_file_changes: z.coerce.number().min(1).max(500),
  email_recipients: z.array(z.object({
    email: z.string().email('Invalid email'),
    role: z.string().min(1),
  })),
})

type FormValues = z.infer<typeof schema>

function SectionCard({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm">
      <div className="px-6 py-4 border-b border-slate-100">
        <h3 className="font-semibold text-slate-800">{title}</h3>
        {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
      </div>
      <div className="px-6 py-5 space-y-4">{children}</div>
    </div>
  )
}

function Label({ children, required }: { children: React.ReactNode; required?: boolean }) {
  return (
    <label className="block text-sm font-medium text-slate-700 mb-1.5">
      {children}{required && <span className="text-red-500 ml-0.5">*</span>}
    </label>
  )
}

function FieldError({ message }: { message?: string }) {
  return message ? <p className="text-xs text-red-500 mt-1">{message}</p> : null
}

function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        'w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition',
        className,
      )}
      {...props}
    />
  )
}

function generateSecret() {
  const arr = new Uint8Array(32)
  crypto.getRandomValues(arr)
  return Array.from(arr).map(b => b.toString(16).padStart(2, '0')).join('')
}

export default function AddRepoPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [showToken, setShowToken] = useState(false)
  const [showSecret, setShowSecret] = useState(false)
  const [tokenTest, setTokenTest] = useState<{ valid: boolean; login?: string | null; error?: string | null } | null>(null)
  const [testingToken, setTestingToken] = useState(false)
  const [protectedInput, setProtectedInput] = useState('')
  const [protectedFiles, setProtectedFiles] = useState<string[]>([])

  const { register, control, handleSubmit, watch, setValue, formState: { errors } } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      auto_merge: false,
      auto_merge_strategy: 'squash',
      require_tests: true,
      block_on_severity: ['critical', 'high'],
      protected_files: [],
      custom_rules: '',
      max_file_changes: 50,
      email_recipients: [],
    },
  })

  const { fields, append, remove } = useFieldArray({ control, name: 'email_recipients' })
  const autoMerge = watch('auto_merge')
  const githubToken = watch('github_token')

  const mutation = useMutation({
    mutationFn: (data: RepoCreate) => api.repos.create(data),
    onSuccess: (repo) => {
      qc.invalidateQueries({ queryKey: ['repos'] })
      qc.invalidateQueries({ queryKey: ['stats'] })
      navigate(`/repos/${repo.id}`)
    },
  })

  async function testToken() {
    if (!githubToken) return
    setTestingToken(true)
    setTokenTest(null)
    try {
      const r = await api.repos.testToken(githubToken)
      setTokenTest(r)
    } finally {
      setTestingToken(false)
    }
  }

  function onSubmit(values: FormValues) {
    const payload: RepoCreate = {
      ...values,
      custom_rules: values.custom_rules.split('\n').map(s => s.trim()).filter(Boolean),
      protected_files: protectedFiles,
    }
    mutation.mutate(payload)
  }

  function addProtected() {
    const val = protectedInput.trim()
    if (val && !protectedFiles.includes(val)) {
      setProtectedFiles(prev => [...prev, val])
    }
    setProtectedInput('')
  }

  const SEVERITIES = ['critical', 'high', 'medium', 'low']
  const blockOn = watch('block_on_severity')

  function toggleSeverity(s: string) {
    const current = blockOn || []
    setValue(
      'block_on_severity',
      current.includes(s) ? current.filter(x => x !== s) : [...current, s],
    )
  }

  const SEVERITY_COLORS: Record<string, string> = {
    critical: 'bg-red-100 border-red-300 text-red-700',
    high: 'bg-orange-100 border-orange-300 text-orange-700',
    medium: 'bg-amber-100 border-amber-300 text-amber-700',
    low: 'bg-blue-100 border-blue-300 text-blue-700',
  }

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Add Repository</h1>
        <p className="text-sm text-slate-500 mt-0.5">Configure a new repo to inject the PR Review Agent</p>
      </div>

      {mutation.isError && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-600">
          {mutation.error?.message ?? 'Failed to add repository'}
        </div>
      )}

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
        {/* Section 1: Repository */}
        <SectionCard title="Repository" subtitle="GitHub repository to monitor">
          <div>
            <Label required>Repository (owner/repo)</Label>
            <Input placeholder="octocat/my-repo" {...register('repo_full_name')} />
            <FieldError message={errors.repo_full_name?.message} />
          </div>
          <div>
            <Label>Display Name</Label>
            <Input placeholder="My Project (optional)" {...register('display_name')} />
          </div>
        </SectionCard>

        {/* Section 2: GitHub Credentials */}
        <SectionCard title="GitHub Credentials" subtitle="Token needs repo + admin:repo_hook scopes">
          <div>
            <Label required>GitHub Personal Access Token</Label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Input
                  type={showToken ? 'text' : 'password'}
                  placeholder="ghp_xxxxxxxxxxxx"
                  {...register('github_token')}
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowToken(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                >
                  {showToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <button
                type="button"
                onClick={testToken}
                disabled={testingToken || !githubToken}
                className="flex items-center gap-1.5 text-sm text-indigo-600 border border-indigo-200 px-3 py-2 rounded-lg hover:bg-indigo-50 disabled:opacity-50 transition whitespace-nowrap"
              >
                {testingToken ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                Test
              </button>
            </div>
            {tokenTest && (
              <div className={cn('flex items-center gap-2 mt-2 text-xs', tokenTest.valid ? 'text-emerald-600' : 'text-red-500')}>
                {tokenTest.valid
                  ? <><CheckCircle2 className="w-3.5 h-3.5" /> Connected as @{tokenTest.login}</>
                  : <><XCircle className="w-3.5 h-3.5" /> {tokenTest.error}</>
                }
              </div>
            )}
            <FieldError message={errors.github_token?.message} />
          </div>
        </SectionCard>

        {/* Section 3: Webhook */}
        <SectionCard title="Webhook Secret" subtitle="Used to verify that events come from GitHub">
          <div>
            <Label>Webhook Secret</Label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Input
                  type={showSecret ? 'text' : 'password'}
                  placeholder="Leave blank to auto-generate"
                  {...register('webhook_secret')}
                  className="pr-10 font-mono"
                />
                <button
                  type="button"
                  onClick={() => setShowSecret(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                >
                  {showSecret ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <button
                type="button"
                onClick={() => { setValue('webhook_secret', generateSecret()); setShowSecret(true) }}
                className="flex items-center gap-1.5 text-sm text-slate-600 border border-slate-200 px-3 py-2 rounded-lg hover:bg-slate-50 transition whitespace-nowrap"
              >
                <RefreshCw className="w-3.5 h-3.5" /> Generate
              </button>
            </div>
            <p className="text-xs text-slate-400 mt-1">If left blank, a secure random secret is generated automatically</p>
          </div>
        </SectionCard>

        {/* Section 4: Email Recipients */}
        <SectionCard title="Email Recipients" subtitle="Who gets notified for each type of review event">
          {fields.map((field, i) => (
            <div key={field.id} className="flex gap-2 items-start">
              <div className="flex-1">
                <Input
                  placeholder="engineer@company.com"
                  {...register(`email_recipients.${i}.email`)}
                />
                <FieldError message={errors.email_recipients?.[i]?.email?.message} />
              </div>
              <Controller
                control={control}
                name={`email_recipients.${i}.role`}
                render={({ field }) => (
                  <select
                    {...field}
                    className="border border-slate-200 rounded-lg text-sm px-2 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white text-slate-700"
                  >
                    {Object.entries(ROLE_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                )}
              />
              <button type="button" onClick={() => remove(i)} className="text-slate-400 hover:text-red-500 transition mt-2">
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => append({ email: '', role: 'critical' })}
            className="flex items-center gap-2 text-sm text-indigo-600 hover:text-indigo-700 font-medium"
          >
            <Plus className="w-4 h-4" /> Add Recipient
          </button>
        </SectionCard>

        {/* Section 5: Review Config */}
        <SectionCard title="Review Configuration" subtitle="Customize how the agent reviews pull requests">
          {/* Auto-merge */}
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-700">Auto-Merge</p>
              <p className="text-xs text-slate-400">Automatically merge PRs that pass review</p>
            </div>
            <Controller
              control={control}
              name="auto_merge"
              render={({ field }) => (
                <button
                  type="button"
                  role="switch"
                  aria-checked={field.value}
                  onClick={() => field.onChange(!field.value)}
                  className={cn(
                    'relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2',
                    field.value ? 'bg-indigo-600' : 'bg-slate-200',
                  )}
                >
                  <span className={cn('inline-block h-4 w-4 transform rounded-full bg-white shadow transition', field.value ? 'translate-x-6' : 'translate-x-1')} />
                </button>
              )}
            />
          </div>

          {autoMerge && (
            <div>
              <Label>Merge Strategy</Label>
              <select
                {...register('auto_merge_strategy')}
                className="border border-slate-200 rounded-lg text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white text-slate-700 w-full"
              >
                <option value="squash">Squash and merge</option>
                <option value="merge">Create a merge commit</option>
                <option value="rebase">Rebase and merge</option>
              </select>
            </div>
          )}

          {/* Require Tests */}
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-700">Require Tests</p>
              <p className="text-xs text-slate-400">Flag PRs that don't include test changes</p>
            </div>
            <Controller
              control={control}
              name="require_tests"
              render={({ field }) => (
                <button
                  type="button"
                  role="switch"
                  aria-checked={field.value}
                  onClick={() => field.onChange(!field.value)}
                  className={cn(
                    'relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2',
                    field.value ? 'bg-indigo-600' : 'bg-slate-200',
                  )}
                >
                  <span className={cn('inline-block h-4 w-4 transform rounded-full bg-white shadow transition', field.value ? 'translate-x-6' : 'translate-x-1')} />
                </button>
              )}
            />
          </div>

          {/* Block on Severity */}
          <div>
            <Label>Block PR on Severity</Label>
            <div className="flex flex-wrap gap-2">
              {SEVERITIES.map(s => (
                <button
                  key={s}
                  type="button"
                  onClick={() => toggleSeverity(s)}
                  className={cn(
                    'px-3 py-1 rounded-full border text-xs font-medium transition',
                    blockOn?.includes(s)
                      ? SEVERITY_COLORS[s]
                      : 'bg-white border-slate-200 text-slate-400 hover:border-slate-300',
                  )}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* Max file changes */}
          <div>
            <Label>Max Files Changed</Label>
            <Input type="number" min={1} max={500} {...register('max_file_changes')} className="w-32" />
            <p className="text-xs text-slate-400 mt-1">Flag PRs that touch more than this many files</p>
          </div>

          {/* Protected Files */}
          <div>
            <Label>Protected Files</Label>
            <div className="flex gap-2">
              <Input
                placeholder="src/auth.py or config/"
                value={protectedInput}
                onChange={e => setProtectedInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addProtected() } }}
              />
              <button type="button" onClick={addProtected} className="text-sm text-indigo-600 border border-indigo-200 px-3 py-2 rounded-lg hover:bg-indigo-50 transition">Add</button>
            </div>
            {protectedFiles.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {protectedFiles.map(f => (
                  <span key={f} className="flex items-center gap-1 bg-slate-100 text-slate-600 text-xs px-2 py-1 rounded-full font-mono">
                    {f}
                    <button type="button" onClick={() => setProtectedFiles(prev => prev.filter(x => x !== f))} className="text-slate-400 hover:text-red-500">×</button>
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Custom rules */}
          <div>
            <Label>Custom Review Rules</Label>
            <textarea
              {...register('custom_rules')}
              placeholder={"No hardcoded credentials\nAll API endpoints must have auth\nUse TypeScript strict mode"}
              rows={3}
              className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
            />
            <p className="text-xs text-slate-400 mt-1">One rule per line — passed to the AI reviewer</p>
          </div>
        </SectionCard>

        {/* Submit */}
        <div className="flex items-center justify-end gap-3 pb-4">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="text-sm text-slate-500 hover:text-slate-700 transition px-4 py-2"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={mutation.isPending}
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium px-5 py-2.5 rounded-lg transition-colors"
          >
            {mutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
            {mutation.isPending ? 'Injecting webhook…' : 'Add Repository'}
          </button>
        </div>
      </form>
    </div>
  )
}
