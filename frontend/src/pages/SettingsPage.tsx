import { useState, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Eye, EyeOff, Save, Loader2, CheckCircle2, Send } from 'lucide-react'
import { api } from '@/lib/api'

interface FieldConfig {
  key: string
  label: string
  placeholder: string
  sensitive: boolean
  help?: string
}

const FIELDS: FieldConfig[] = [
  {
    key: 'webhook_base_url',
    label: 'Webhook Base URL',
    placeholder: 'https://pr-automotion-production.up.railway.app',
    sensitive: false,
    help: 'The public URL of this server. GitHub sends PR events to {this URL}/webhook',
  },
  {
    key: 'anthropic_api_key',
    label: 'Anthropic API Key',
    placeholder: 'sk-ant-…',
    sensitive: true,
    help: 'Used by the Claude AI agent to review PRs. Get it from console.anthropic.com',
  },
  {
    key: 'smtp_host',
    label: 'SMTP Host',
    placeholder: 'smtp.office365.com',
    sensitive: false,
    help: 'Office 365: smtp.office365.com  |  Gmail: smtp.gmail.com  |  Port 587 (TLS) or 465 (SSL)',
  },
  {
    key: 'smtp_port',
    label: 'SMTP Port',
    placeholder: '587',
    sensitive: false,
    help: '587 for STARTTLS (recommended) or 465 for SSL',
  },
  {
    key: 'smtp_username',
    label: 'SMTP Username',
    placeholder: 'pr-review-bot@yourcompany.com',
    sensitive: false,
    help: 'The email account used to log in to the SMTP server (usually the sender email)',
  },
  {
    key: 'smtp_password',
    label: 'SMTP Password',
    placeholder: 'Enter email password or app password…',
    sensitive: true,
    help: 'For Office 365 with MFA: generate an App Password in your account security settings',
  },
  {
    key: 'smtp_sender_email',
    label: 'Sender Email (From)',
    placeholder: 'pr-review-bot@yourcompany.com',
    sensitive: false,
    help: 'The email address that appears in the From field of review notification emails',
  },
]

function SettingField({
  config,
  currentValue,
  value,
  onChange,
}: {
  config: FieldConfig
  currentValue: string
  value: string
  onChange: (v: string) => void
}) {
  const [show, setShow] = useState(false)
  const isMasked = currentValue === '••••••••'

  return (
    <div className="space-y-1.5">
      <label className="block text-sm font-medium text-slate-700">{config.label}</label>
      <div className="relative">
        <input
          type={config.sensitive && !show ? 'password' : 'text'}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={isMasked ? '(already set — enter new value to change)' : config.placeholder}
          className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 pr-10"
        />
        {config.sensitive && (
          <button
            type="button"
            onClick={() => setShow(v => !v)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
          >
            {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        )}
      </div>
      {config.help && <p className="text-xs text-slate-400">{config.help}</p>}
    </div>
  )
}

export default function SettingsPage() {
  const [values, setValues] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState(false)
  const [testEmailTo, setTestEmailTo] = useState('')
  const [testResult, setTestResult] = useState<{ ok: boolean; error?: string } | null>(null)

  const { data: current, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: api.settings.get,
  })

  useEffect(() => {
    if (current) {
      const init: Record<string, string> = {}
      FIELDS.forEach(f => { init[f.key] = '' })
      setValues(init)
    }
  }, [current])

  const mutation = useMutation({
    mutationFn: (data: Record<string, string>) => api.settings.update(data),
    onSuccess: () => {
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    },
  })

  function handleSave(e: React.FormEvent) {
    e.preventDefault()
    const toSave: Record<string, string> = {}
    FIELDS.forEach(f => {
      const v = values[f.key]?.trim()
      if (v) toSave[f.key] = v
    })
    mutation.mutate(toSave)
  }

  function field(key: string) {
    return {
      config: FIELDS.find(f => f.key === key)!,
      currentValue: current?.[key] ?? '',
      value: values[key] ?? '',
      onChange: (v: string) => setValues(p => ({ ...p, [key]: v })),
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Settings</h1>
        <p className="text-sm text-slate-500 mt-0.5">Global configuration for the PR Review Agent</p>
      </div>

      <form onSubmit={handleSave} className="space-y-5">
        {/* Server */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm px-6 py-5 space-y-4">
          <h3 className="font-semibold text-slate-700 text-sm">Server</h3>
          <SettingField {...field('webhook_base_url')} />
        </div>

        {/* Anthropic */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm px-6 py-5 space-y-4">
          <h3 className="font-semibold text-slate-700 text-sm">Anthropic / Claude AI</h3>
          <SettingField {...field('anthropic_api_key')} />
        </div>

        {/* SMTP Email */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm px-6 py-5 space-y-4">
          <div>
            <h3 className="font-semibold text-slate-700 text-sm">Email (SMTP)</h3>
            <p className="text-xs text-slate-400 mt-1">
              Use your company SMTP credentials. For Office 365 with MFA enabled, generate an
              <a href="https://support.microsoft.com/en-us/account-billing/manage-app-passwords-for-two-step-verification-d6dc8c6d-4bf7-4851-ad95-6d07799387e9"
                target="_blank" rel="noopener noreferrer" className="text-indigo-500 hover:underline ml-1">
                App Password →
              </a>
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2 sm:col-span-1">
              <SettingField {...field('smtp_host')} />
            </div>
            <div className="col-span-2 sm:col-span-1">
              <SettingField {...field('smtp_port')} />
            </div>
          </div>
          <SettingField {...field('smtp_username')} />
          <SettingField {...field('smtp_password')} />
          <SettingField {...field('smtp_sender_email')} />

          {/* Quick fill hints */}
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
            <p className="text-xs font-medium text-slate-600 mb-2">Common SMTP settings:</p>
            <div className="space-y-1 text-xs text-slate-500 font-mono">
              <p>Office 365 → smtp.office365.com : 587</p>
              <p>Gmail → smtp.gmail.com : 587</p>
              <p>Outlook.com → smtp-mail.outlook.com : 587</p>
            </div>
          </div>

          {/* Test email */}
          <div className="border-t border-slate-100 pt-4">
            <p className="text-xs font-medium text-slate-600 mb-2">Test email delivery</p>
            <div className="flex gap-2">
              <input
                type="email"
                placeholder="send test to…"
                value={testEmailTo}
                onChange={e => { setTestEmailTo(e.target.value); setTestResult(null) }}
                className="flex-1 px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
              <button
                type="button"
                disabled={!testEmailTo}
                onClick={async () => {
                  setTestResult(null)
                  const r = await api.settings.testEmail(testEmailTo)
                  setTestResult(r)
                }}
                className="flex items-center gap-1.5 text-sm border border-slate-200 px-3 py-2 rounded-lg hover:bg-slate-50 disabled:opacity-40 transition whitespace-nowrap"
              >
                <Send className="w-3.5 h-3.5" /> Send Test
              </button>
            </div>
            {testResult && (
              <p className={`text-xs mt-1.5 ${testResult.ok ? 'text-emerald-600' : 'text-red-500'}`}>
                {testResult.ok ? '✓ Test email sent successfully' : `✗ ${testResult.error}`}
              </p>
            )}
          </div>
        </div>

        {/* Save */}
        <div className="flex items-center justify-end gap-3 pb-4">
          {saved && (
            <span className="flex items-center gap-1.5 text-sm text-emerald-600">
              <CheckCircle2 className="w-4 h-4" /> Saved
            </span>
          )}
          {mutation.isError && (
            <span className="text-sm text-red-500">{(mutation.error as Error)?.message}</span>
          )}
          <button
            type="submit"
            disabled={mutation.isPending}
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium px-5 py-2.5 rounded-lg transition-colors"
          >
            {mutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save Settings
          </button>
        </div>
      </form>
    </div>
  )
}
