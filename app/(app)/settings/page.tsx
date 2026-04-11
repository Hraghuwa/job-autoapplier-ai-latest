'use client'
import { useState } from 'react'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Save, Loader2, Check, User, Lock, CreditCard, Bell, Key, Trash2 } from 'lucide-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

export default function SettingsPage() {
  const { user, setAuth, token, refresh_token } = useAuth()
  const [name, setName] = useState(user?.name || '')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [activeTab, setActiveTab] = useState('profile')

  async function handleSave() {
    setSaving(true)
    try {
      await api.put('/users/me', { name })
      const meRes = await api.get('/auth/me')
      setAuth(token!, refresh_token!, meRes.data)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err) {
      console.error('Failed to save:', err)
    } finally {
      setSaving(false)
    }
  }

  // ── API Keys state ──
  const qc = useQueryClient()
  const { data: apiKeysStatus } = useQuery({
    queryKey: ['api-keys'],
    queryFn: () => api.get('/users/api-keys', { silent: true }).then(r => r.data),
    enabled: activeTab === 'api-keys',
    retry: false,
  })
  const [geminiKey, setGeminiKey] = useState('')
  const [groqKey, setGroqKey] = useState('')
  const [savingKey, setSavingKey] = useState<string | null>(null)
  const [keyMsg, setKeyMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)

  async function handleSaveKey(provider: 'gemini' | 'groq') {
    const key = provider === 'gemini' ? geminiKey : groqKey
    if (!key.trim()) return
    setSavingKey(provider)
    setKeyMsg(null)
    try {
      await api.post(`/users/${provider}-key`, { api_key: key.trim() })
      setKeyMsg({ type: 'ok', text: `${provider === 'gemini' ? 'Gemini' : 'Groq'} key saved & validated.` })
      provider === 'gemini' ? setGeminiKey('') : setGroqKey('')
      qc.invalidateQueries({ queryKey: ['api-keys'] })
    } catch (err: any) {
      setKeyMsg({ type: 'err', text: err?.response?.data?.detail || `Failed to save ${provider} key` })
    } finally {
      setSavingKey(null)
    }
  }

  async function handleDeleteKey(provider: 'gemini' | 'groq') {
    try {
      await api.delete(`/users/${provider}-key`)
      qc.invalidateQueries({ queryKey: ['api-keys'] })
      setKeyMsg({ type: 'ok', text: `${provider === 'gemini' ? 'Gemini' : 'Groq'} key removed.` })
    } catch {
      setKeyMsg({ type: 'err', text: `Failed to remove ${provider} key` })
    }
  }

  const tabs = [
    { id: 'profile', label: 'Profile', icon: User },
    { id: 'api-keys', label: 'API Keys', icon: Key },
    { id: 'security', label: 'Security', icon: Lock },
    { id: 'billing', label: 'Billing', icon: CreditCard },
    { id: 'notifications', label: 'Notifications', icon: Bell },
  ]

  return (
    <>
      <div className="mb-8">
        <h1 className="font-display text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground mt-1">Manage your account preferences.</p>
      </div>

      <div className="flex flex-col lg:flex-row gap-6">
        {/* Tabs */}
        <div className="lg:w-56 shrink-0">
          <nav className="flex lg:flex-col gap-1">
            {tabs.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                className={`flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                  activeTab === id
                    ? 'bg-[hsl(var(--color-accent))]/10 text-[hsl(var(--color-accent))]'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                }`}
              >
                <Icon className="h-4 w-4" />
                {label}
              </button>
            ))}
          </nav>
        </div>

        {/* Content */}
        <div className="flex-1 max-w-2xl">
          {activeTab === 'profile' && (
            <div className="rounded-xl border border-border bg-white dark:bg-[hsl(234,28%,14%)] p-6 space-y-6">
              <div>
                <h3 className="font-display text-lg font-semibold mb-1">Profile Information</h3>
                <p className="text-sm text-muted-foreground">Update your personal details.</p>
              </div>

              <div className="flex items-center gap-4">
                <div className="h-16 w-16 rounded-full bg-gradient-to-br from-[hsl(var(--color-accent))] to-[hsl(var(--color-brand))] flex items-center justify-center text-2xl font-bold text-white shadow-lg">
                  {user?.name?.[0]?.toUpperCase() || 'U'}
                </div>
                <div>
                  <p className="font-semibold">{user?.name}</p>
                  <p className="text-sm text-muted-foreground">{user?.email}</p>
                </div>
              </div>

              <div className="space-y-4">
                <div className="space-y-2">
                  <Label className="text-sm font-medium">Full Name</Label>
                  <Input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="h-10 bg-white dark:bg-[hsl(234,28%,14%)]"
                  />
                </div>

                <div className="space-y-2">
                  <Label className="text-sm font-medium">Email</Label>
                  <Input
                    value={user?.email || ''}
                    disabled
                    className="h-10 bg-muted/50"
                  />
                  <p className="text-xs text-muted-foreground">Email cannot be changed.</p>
                </div>
              </div>

              <div className="flex justify-end pt-2">
                <Button
                  onClick={handleSave}
                  disabled={saving}
                  className="gap-2 font-semibold text-white"
                  style={{ background: 'linear-gradient(135deg, hsl(var(--color-accent)), hsl(var(--color-accent-hover)))' }}
                >
                  {saving ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : saved ? (
                    <Check className="h-4 w-4" />
                  ) : (
                    <Save className="h-4 w-4" />
                  )}
                  {saved ? 'Saved!' : 'Save Changes'}
                </Button>
              </div>
            </div>
          )}

          {activeTab === 'api-keys' && (
            <div className="rounded-xl border border-border bg-white dark:bg-[hsl(234,28%,14%)] p-6 space-y-6">
              <div>
                <h3 className="font-display text-lg font-semibold mb-1">API Keys</h3>
                <p className="text-sm text-muted-foreground">
                  Configure AI provider keys for intelligent form filling. Groq is used first (faster), Gemini as fallback.
                </p>
              </div>

              {keyMsg && (
                <div className={`p-3 rounded-lg text-sm ${keyMsg.type === 'ok' ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400' : 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400'}`}>
                  {keyMsg.text}
                </div>
              )}

              {/* Gemini */}
              <div className="space-y-3 p-4 rounded-lg border border-border bg-muted/20">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-semibold text-sm">Google Gemini</p>
                    <p className="text-xs text-muted-foreground">Used for form fill, vision analysis, cover letters</p>
                  </div>
                  {apiKeysStatus?.gemini ? (
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-emerald-600 bg-emerald-50 dark:bg-emerald-900/20 px-2 py-0.5 rounded-full">Configured</span>
                      <button onClick={() => handleDeleteKey('gemini')} className="text-muted-foreground hover:text-red-500 transition-colors">
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ) : (
                    <span className="text-xs font-medium text-amber-600 bg-amber-50 dark:bg-amber-900/20 px-2 py-0.5 rounded-full">Not set</span>
                  )}
                </div>
                <div className="flex gap-2">
                  <Input
                    type="password"
                    placeholder="AIza..."
                    value={geminiKey}
                    onChange={(e) => setGeminiKey(e.target.value)}
                    className="h-9 bg-white dark:bg-[hsl(234,28%,14%)] text-sm"
                  />
                  <Button
                    size="sm"
                    onClick={() => handleSaveKey('gemini')}
                    disabled={!geminiKey.trim() || savingKey === 'gemini'}
                    className="gap-1.5 font-semibold text-white shrink-0"
                    style={{ background: 'linear-gradient(135deg, hsl(var(--color-accent)), hsl(var(--color-accent-hover)))' }}
                  >
                    {savingKey === 'gemini' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                    Save
                  </Button>
                </div>
              </div>

              {/* Groq */}
              <div className="space-y-3 p-4 rounded-lg border border-border bg-muted/20">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-semibold text-sm">Groq</p>
                    <p className="text-xs text-muted-foreground">Fast LLM for form fields (Llama 3.1 70B) — optional, falls back to Gemini</p>
                  </div>
                  {apiKeysStatus?.groq ? (
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-emerald-600 bg-emerald-50 dark:bg-emerald-900/20 px-2 py-0.5 rounded-full">Configured</span>
                      <button onClick={() => handleDeleteKey('groq')} className="text-muted-foreground hover:text-red-500 transition-colors">
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ) : (
                    <span className="text-xs font-medium text-amber-600 bg-amber-50 dark:bg-amber-900/20 px-2 py-0.5 rounded-full">Not set</span>
                  )}
                </div>
                <div className="flex gap-2">
                  <Input
                    type="password"
                    placeholder="gsk_..."
                    value={groqKey}
                    onChange={(e) => setGroqKey(e.target.value)}
                    className="h-9 bg-white dark:bg-[hsl(234,28%,14%)] text-sm"
                  />
                  <Button
                    size="sm"
                    onClick={() => handleSaveKey('groq')}
                    disabled={!groqKey.trim() || savingKey === 'groq'}
                    className="gap-1.5 font-semibold text-white shrink-0"
                    style={{ background: 'linear-gradient(135deg, hsl(var(--color-accent)), hsl(var(--color-accent-hover)))' }}
                  >
                    {savingKey === 'groq' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                    Save
                  </Button>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'security' && (
            <div className="rounded-xl border border-border bg-white dark:bg-[hsl(234,28%,14%)] p-6">
              <h3 className="font-display text-lg font-semibold mb-1">Security</h3>
              <p className="text-sm text-muted-foreground mb-6">Manage your password and security settings.</p>
              <p className="text-sm text-muted-foreground">Password change coming soon.</p>
            </div>
          )}

          {activeTab === 'billing' && (
            <div className="rounded-xl border border-border bg-white dark:bg-[hsl(234,28%,14%)] p-6">
              <h3 className="font-display text-lg font-semibold mb-1">Billing & Plan</h3>
              <p className="text-sm text-muted-foreground mb-6">Manage your subscription.</p>

              <div className="p-4 rounded-lg border border-border bg-muted/20">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-semibold">{user?.plan?.toUpperCase() || 'FREE'} Plan</p>
                    <p className="text-sm text-muted-foreground mt-0.5">
                      {user?.plan === 'pro' ? 'Unlimited resumes, all templates, AI features' : '3 resumes, basic templates'}
                    </p>
                  </div>
                  {user?.plan !== 'pro' && (
                    <Button
                      size="sm"
                      className="font-semibold text-white"
                      style={{ background: 'linear-gradient(135deg, hsl(var(--color-accent)), hsl(var(--color-accent-hover)))' }}
                    >
                      Upgrade to Pro
                    </Button>
                  )}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'notifications' && (
            <div className="rounded-xl border border-border bg-white dark:bg-[hsl(234,28%,14%)] p-6">
              <h3 className="font-display text-lg font-semibold mb-1">Notifications</h3>
              <p className="text-sm text-muted-foreground">Notification preferences coming soon.</p>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
