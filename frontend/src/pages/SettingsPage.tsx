import { useState, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Eye, EyeOff, Save, Loader2, CheckCircle2 } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

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
    placeholder: 'https://your-app.fly.dev',
    sensitive: false,
    help: 'The public URL of this server. GitHub will send PR events to {this URL}/webhook',
  },
  {
    key: 'anthropic_api_key',
    label: 'Anthropic API Key',
    placeholder: 'sk-ant-…',
    sensitive: true,
    help: 'Used by the Claude AI agent to review PRs. Can be overridden per-repo.',
  },
  {
    key: 'azure_tenant_id',
    label: 'Azure Tenant ID',
    placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx',
    sensitive: false,
    help: 'Microsoft 365 / Azure AD tenant ID for Outlook email notifications',
  },
  {
    key: 'azure_client_id',
    label: 'Azure Client ID',
    placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx',
    sensitive: false,
    help: 'App registration client ID with Mail.Send permission',
  },
  {
    key: 'azure_client_secret',
    label: 'Azure Client Secret',
    placeholder: 'Enter new secret…',
    sensitive: true,
    help: 'Client secret for the Azure app registration',
  },
  {
    key: 'outlook_sender_email',
    label: 'Outlook Sender Email',
    placeholder: 'prreviewer@yourcompany.com',
    sensitive: false,
    help: 'The licensed Microsoft 365 mailbox that sends review notification emails',
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
        {/* Webhook URL */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm px-6 py-5 space-y-4">
          <h3 className="font-semibold text-slate-700 text-sm">Server Configuration</h3>
          <SettingField
            config={FIELDS[0]}
            currentValue={current?.webhook_base_url ?? ''}
            value={values.webhook_base_url ?? ''}
            onChange={v => setValues(p => ({ ...p, webhook_base_url: v }))}
          />
        </div>

        {/* Anthropic */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm px-6 py-5 space-y-4">
          <h3 className="font-semibold text-slate-700 text-sm">Anthropic / Claude</h3>
          <SettingField
            config={FIELDS[1]}
            currentValue={current?.anthropic_api_key ?? ''}
            value={values.anthropic_api_key ?? ''}
            onChange={v => setValues(p => ({ ...p, anthropic_api_key: v }))}
          />
        </div>

        {/* Email / Outlook */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm px-6 py-5 space-y-4">
          <h3 className="font-semibold text-slate-700 text-sm">Outlook / Microsoft 365 Email</h3>
          <p className="text-xs text-slate-400 -mt-2">
            Set up Azure app registration with Mail.Send permission.{' '}
            <a
              href="https://learn.microsoft.com/en-us/graph/auth-register-app-v2"
              target="_blank"
              rel="noopener noreferrer"
              className="text-indigo-500 hover:underline"
            >
              Instructions →
            </a>
          </p>
          {FIELDS.slice(2).map(f => (
            <SettingField
              key={f.key}
              config={f}
              currentValue={current?.[f.key] ?? ''}
              value={values[f.key] ?? ''}
              onChange={v => setValues(p => ({ ...p, [f.key]: v }))}
            />
          ))}
        </div>

        {/* Save */}
        <div className="flex items-center justify-end gap-3 pb-4">
          {saved && (
            <span className="flex items-center gap-1.5 text-sm text-emerald-600">
              <CheckCircle2 className="w-4 h-4" /> Saved
            </span>
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
