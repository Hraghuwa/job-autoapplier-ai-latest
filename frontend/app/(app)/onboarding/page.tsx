'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import api from '@/lib/api'
import { Upload, ChevronRight, ChevronLeft, Check } from 'lucide-react'

const STEPS = ['Knowledge Import', 'Preferences', 'Credentials', 'Autofill']

const PLATFORMS = ['linkedin', 'wellfound', 'internshala']

const AUTOFILL_FIELDS = [
  'phone', 'address', 'city', 'state', 'country', 'years_of_experience',
  'github_url', 'linkedin_url', 'portfolio_url', 'expected_salary', 'notice_period',
]

export default function OnboardingPage() {
  const router = useRouter()
  const [step, setStep] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Step 1 state
  const [resumeFile, setResumeFile] = useState<File | null>(null)
  const [extracted, setExtracted] = useState<any>(null)

  // Step 2 state
  const [prefs, setPrefs] = useState({
    titles: '',
    locations: '',
    remote: false,
    types: [] as string[],
  })

  // Step 3 state
  const [creds, setCreds] = useState<Record<string, { email: string; password: string }>>({})
  const [enabledPlatforms, setEnabledPlatforms] = useState<string[]>([])

  // Step 4 state
  const [autofill, setAutofill] = useState<Record<string, string>>({})

  async function handleResume() {
    if (!resumeFile) return
    setLoading(true); setError('')
    try {
      const fd = new FormData()
      fd.append('file', resumeFile)
      const { data } = await api.post('/onboarding/resume', fd)
      setExtracted(data.extracted)
      setStep(1)
    } catch (e: any) {
      const d = e?.response?.data?.detail
      setError(typeof d === 'string' ? d : d?.message || 'Upload failed')
    }
    finally { setLoading(false) }
  }

  async function handlePrefs() {
    setLoading(true); setError('')
    try {
      await api.post('/onboarding/preferences', {
        job_titles: prefs.titles.split(',').map((s) => s.trim()).filter(Boolean),
        locations: prefs.locations.split(',').map((s) => s.trim()).filter(Boolean),
        remote: prefs.remote,
        employment_types: prefs.types,
      })
      setStep(2)
    } catch (e: any) {
      const d = e?.response?.data?.detail
      setError(typeof d === 'string' ? d : d?.message || 'Failed')
    }
    finally { setLoading(false) }
  }

  async function handleCreds() {
    setLoading(true); setError('')
    try {
      const platforms: Record<string, any> = {}
      for (const p of enabledPlatforms) {
        if (creds[p]) platforms[p] = creds[p]
      }
      await api.post('/onboarding/credentials', { platforms })
      setStep(3)
    } catch (e: any) {
      const d = e?.response?.data?.detail
      setError(typeof d === 'string' ? d : d?.message || 'Failed')
    }
    finally { setLoading(false) }
  }

  async function handleAutofill() {
    setLoading(true); setError('')
    try {
      await api.post('/onboarding/autofill', { fields: autofill })
      router.push('/dashboard')
    } catch (e: any) {
      const d = e?.response?.data?.detail
      setError(typeof d === 'string' ? d : d?.message || 'Failed')
    }
    finally { setLoading(false) }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Launch Your Agent</h1>
        <p className="text-slate-500">Complete setup to start automating your applications</p>
      </div>

      {/* Progress */}
      <div className="space-y-2">
        <div className="flex justify-between text-sm">
          {STEPS.map((s, i) => (
            <span key={s} className={i === step ? 'font-medium text-blue-600' : i < step ? 'text-green-600' : 'text-slate-400'}>
              {i < step ? <Check className="inline h-3 w-3" /> : null} {s}
            </span>
          ))}
        </div>
        <Progress value={((step) / STEPS.length) * 100} />
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}

      {step === 0 && (
        <Card>
          <CardHeader><CardTitle>Import Agent Knowledge</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <label className="border-2 border-dashed rounded-lg p-8 flex flex-col items-center gap-2 cursor-pointer hover:bg-slate-50">
              <Upload className="h-8 w-8 text-slate-400" />
              <span className="text-sm text-slate-500">{resumeFile ? resumeFile.name : 'Click to upload PDF'}</span>
              <input type="file" accept=".pdf" className="hidden" onChange={(e) => setResumeFile(e.target.files?.[0] || null)} />
            </label>
            {extracted && (
              <div className="bg-green-50 border border-green-200 rounded p-3 text-sm">
                <p className="font-medium text-green-800">Knowledge parsed successfully</p>
                <p className="text-green-700">Name: {extracted.name || 'N/A'} · Skills: {extracted.skills?.slice(0, 5).join(', ')}</p>
              </div>
            )}
            <Button className="w-full" onClick={handleResume} disabled={!resumeFile || loading}>
              {loading ? 'Uploading…' : 'Upload & Continue'} <ChevronRight className="ml-2 h-4 w-4" />
            </Button>
          </CardContent>
        </Card>
      )}

      {step === 1 && (
        <Card>
          <CardHeader><CardTitle>Job Preferences</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1">
              <Label>Job Titles (comma-separated)</Label>
              <Input value={prefs.titles} onChange={(e) => setPrefs({ ...prefs, titles: e.target.value })} placeholder="Software Engineer, Backend Developer" />
            </div>
            <div className="space-y-1">
              <Label>Locations (comma-separated)</Label>
              <Input value={prefs.locations} onChange={(e) => setPrefs({ ...prefs, locations: e.target.value })} placeholder="Bangalore, Remote" />
            </div>
            <div className="flex items-center gap-2">
              <input type="checkbox" id="remote" checked={prefs.remote} onChange={(e) => setPrefs({ ...prefs, remote: e.target.checked })} />
              <Label htmlFor="remote">Remote only</Label>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep(0)}><ChevronLeft className="h-4 w-4 mr-1" />Back</Button>
              <Button className="flex-1" onClick={handlePrefs} disabled={loading}>
                {loading ? 'Saving…' : 'Continue'} <ChevronRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === 2 && (
        <Card>
          <CardHeader><CardTitle>Platform Credentials</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-slate-500">Credentials are encrypted at rest (AES-256). We never share them.</p>
            {PLATFORMS.map((p) => (
              <div key={p} className="space-y-2 p-3 border rounded-lg">
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id={`en-${p}`}
                    checked={enabledPlatforms.includes(p)}
                    onChange={(e) => setEnabledPlatforms(e.target.checked ? [...enabledPlatforms, p] : enabledPlatforms.filter((x) => x !== p))}
                  />
                  <Label htmlFor={`en-${p}`} className="capitalize font-medium">{p}</Label>
                </div>
                {enabledPlatforms.includes(p) && (
                  <div className="grid grid-cols-2 gap-2 mt-2">
                    <Input placeholder="Email" value={creds[p]?.email || ''} onChange={(e) => setCreds({ ...creds, [p]: { ...creds[p], email: e.target.value } })} />
                    <Input placeholder="Password" type="password" value={creds[p]?.password || ''} onChange={(e) => setCreds({ ...creds, [p]: { ...creds[p], password: e.target.value } })} />
                  </div>
                )}
              </div>
            ))}
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep(1)}><ChevronLeft className="h-4 w-4 mr-1" />Back</Button>
              <Button className="flex-1" onClick={handleCreds} disabled={loading}>
                {loading ? 'Saving…' : 'Continue'} <ChevronRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === 3 && (
        <Card>
          <CardHeader><CardTitle>Autofill Bank</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-slate-500">These values are used to auto-fill application forms.</p>
            <div className="grid grid-cols-2 gap-3">
              {AUTOFILL_FIELDS.map((field) => (
                <div key={field} className="space-y-1">
                  <Label className="capitalize text-xs">{field.replace(/_/g, ' ')}</Label>
                  <Input
                    value={autofill[field] || ''}
                    onChange={(e) => setAutofill({ ...autofill, [field]: e.target.value })}
                    placeholder={field.replace(/_/g, ' ')}
                  />
                </div>
              ))}
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep(2)}><ChevronLeft className="h-4 w-4 mr-1" />Back</Button>
              <Button className="flex-1" onClick={handleAutofill} disabled={loading}>
                {loading ? 'Finishing…' : 'Complete Setup'} <Check className="ml-2 h-4 w-4" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
