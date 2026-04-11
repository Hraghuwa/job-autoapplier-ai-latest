'use client'

import { useState, useRef, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import {
  CheckCircle2, XCircle, AlertCircle, User, FileText,
  KeyRound, Briefcase, Zap, ChevronDown, ChevronUp, X, Plus,
} from 'lucide-react'

// ── Constants ──────────────────────────────────────────────────────────────────

const PLATFORMS = ['linkedin', 'wellfound', 'internshala', 'unstop', 'naukri'] as const
type Platform = typeof PLATFORMS[number]

const PLATFORM_LABELS: Record<Platform, string> = {
  linkedin: 'LinkedIn',
  wellfound: 'Wellfound',
  internshala: 'Internshala',
  unstop: 'Unstop',
  naukri: 'Naukri',
}

const EMPLOYMENT_TYPES = ['Full-time', 'Internship', 'Part-time', 'Contract', 'Trainee', 'Fresher']
const WORK_MODES = ['Remote', 'Hybrid', 'On-site']
const JOB_ROLE_SUGGESTIONS = [
  'Software Engineer', 'Frontend Developer', 'Backend Developer', 'Full Stack Developer',
  'Data Scientist', 'Machine Learning Engineer', 'DevOps Engineer', 'Product Manager',
  'UI/UX Designer', 'Data Analyst', 'Mobile Developer', 'Cloud Engineer',
  'QA Engineer', 'Security Engineer', 'Blockchain Developer', 'AI Engineer',
]
const LOCATION_SUGGESTIONS = ['Bangalore', 'Mumbai', 'Delhi', 'Hyderabad', 'Pune', 'Chennai', 'Remote']

// ── Types ─────────────────────────────────────────────────────────────────────

interface Profile {
  resume_url: string | null
  resume_filename: string | null
  extracted_data: Record<string, any> | null
  job_preferences: Record<string, any> | null
  autofill_bank: Record<string, any> | null
  cover_letter: string | null
}

interface CredStatus {
  linkedin: boolean
  wellfound: boolean
  internshala: boolean
  unstop: boolean
  naukri: boolean
}

// ── Small helpers ─────────────────────────────────────────────────────────────

function StatusIcon({ ok, warn }: { ok: boolean; warn?: boolean }) {
  if (ok) return <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />
  if (warn) return <AlertCircle className="h-4 w-4 text-amber-500 shrink-0" />
  return <XCircle className="h-4 w-4 text-red-400 shrink-0" />
}

function Section({ title, icon: Icon, children }: { title: string; icon: any; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Icon className="h-4 w-4 text-blue-600" />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

// ── TagInput ──────────────────────────────────────────────────────────────────

interface TagInputProps {
  tags: string[]
  onAdd: (val: string) => void
  onRemove: (val: string) => void
  input: string
  setInput: (v: string) => void
  placeholder: string
  suggestions?: string[]
}

function TagInput({ tags, onAdd, onRemove, input, setInput, placeholder, suggestions }: TagInputProps) {
  return (
    <div className="space-y-2">
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {tags.map(t => (
            <span
              key={t}
              className="flex items-center gap-1 bg-blue-50 text-blue-700 text-xs px-2 py-1 rounded-full"
            >
              {t}
              <button type="button" onClick={() => onRemove(t)} aria-label={`Remove ${t}`}>
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="flex gap-2">
        <Input
          placeholder={placeholder}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') {
              e.preventDefault()
              onAdd(input)
            }
          }}
          className="h-8 text-sm"
        />
        <Button size="sm" variant="outline" onClick={() => onAdd(input)} type="button">
          <Plus className="h-3 w-3" />
        </Button>
      </div>
      {suggestions && suggestions.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {suggestions.filter(s => !tags.includes(s)).map(s => (
            <button
              key={s}
              type="button"
              onClick={() => onAdd(s)}
              className="text-xs border border-dashed border-slate-300 px-2 py-0.5 rounded-full hover:bg-slate-50 text-slate-600 transition-colors"
            >
              + {s}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function CredentialsPage() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const router = useRouter()

  // ── Job targeting state ──────────────────────────────────────────────────
  const [jobTitles, setJobTitles] = useState<string[]>([])
  const [employmentTypes, setEmploymentTypes] = useState<string[]>([])
  const [locations, setLocations] = useState<string[]>([])
  const [remote, setRemote] = useState(false)
  const [workMode, setWorkMode] = useState('')
  const [keywords, setKeywords] = useState<string[]>([])
  const [targetCompanies, setTargetCompanies] = useState<string[]>([])
  const [excludeCompanies, setExcludeCompanies] = useState<string[]>([])
  const [minStipend, setMinStipend] = useState('')
  const [matchThreshold, setMatchThreshold] = useState(60)
  const [showAdvanced, setShowAdvanced] = useState(false)

  // per-input states for tag inputs
  const [titleInput, setTitleInput] = useState('')
  const [locationInput, setLocationInput] = useState('')
  const [keywordInput, setKeywordInput] = useState('')
  const [targetInput, setTargetInput] = useState('')
  const [excludeInput, setExcludeInput] = useState('')

  // saving states
  const [savingTargeting, setSavingTargeting] = useState(false)
  const [targetingSaved, setTargetingSaved] = useState(false)
  const [targetingError, setTargetingError] = useState('')

  // cover letter state
  const [coverLetter, setCoverLetter] = useState('')
  const [savingCoverLetter, setSavingCoverLetter] = useState(false)
  const [coverLetterSaved, setCoverLetterSaved] = useState(false)

  // ── Resume upload state ──────────────────────────────────────────────────
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [uploadState, setUploadState] = useState<'idle' | 'uploading' | 'done' | 'error'>('idle')
  const [uploadError, setUploadError] = useState('')

  // ── LinkedIn cookie bypass state ─────────────────────────────────────────
  const [cookiesText, setCookiesText] = useState('')
  const [cookieStatus, setCookieStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [cookieMsg, setCookieMsg] = useState('')
  const [cookiesStored, setCookiesStored] = useState(false)
  const [cookiePanelOpen, setCookiePanelOpen] = useState(false)

  // ── Platform credentials state ───────────────────────────────────────────
  const [credForm, setCredForm] = useState<Record<Platform, { email: string; password: string }>>({
    linkedin: { email: '', password: '' },
    wellfound: { email: '', password: '' },
    internshala: { email: '', password: '' },
    unstop: { email: '', password: '' },
    naukri: { email: '', password: '' },
  })
  const [showPwd, setShowPwd] = useState<Record<Platform, boolean>>({
    linkedin: false, wellfound: false, internshala: false, unstop: false, naukri: false,
  })
  const [expandedPlatform, setExpandedPlatform] = useState<Platform | null>(null)
  const [savingCred, setSavingCred] = useState<Platform | null>(null)
  const [credMsg, setCredMsg] = useState<Record<Platform, string>>({
    linkedin: '', wellfound: '', internshala: '', unstop: '', naukri: '',
  })

  // ── Queries ──────────────────────────────────────────────────────────────
  const { data: profile } = useQuery<Profile>({
    queryKey: ['profile'],
    queryFn: () => api.get('/users/profile', { silent: true }).then(r => r.data),
    retry: false,
  })

  const { data: credStatus } = useQuery<CredStatus>({
    queryKey: ['cred-status'],
    queryFn: () => api.get('/onboarding/credentials-status', { silent: true }).then(r => r.data),
    retry: false,
  })

  const { data: usage } = useQuery<{ plan: string; applies_today: number; applies_limit: number }>({
    queryKey: ['usage'],
    queryFn: () => api.get('/users/usage', { silent: true }).then(r => r.data),
    retry: false,
  })

  const { data: liCookieStatus } = useQuery<{ stored: boolean }>({
    queryKey: ['li-cookies'],
    queryFn: () => api.get('/onboarding/linkedin-cookies-status', { silent: true }).then(r => r.data),
    retry: false,
  })

  useEffect(() => {
    if (liCookieStatus?.stored !== undefined) setCookiesStored(liCookieStatus.stored)
  }, [liCookieStatus?.stored])

  // ── Populate from profile ────────────────────────────────────────────────
  useEffect(() => {
    if (!profile?.job_preferences) return
    const p = profile.job_preferences
    if (p.job_titles) setJobTitles(p.job_titles)
    if (p.employment_types) setEmploymentTypes(p.employment_types)
    if (p.locations) setLocations(p.locations)
    if (p.remote !== undefined) setRemote(p.remote)
    if (p.work_mode) setWorkMode(p.work_mode)
    if (p.keywords) setKeywords(p.keywords)
    if (p.target_companies) setTargetCompanies(p.target_companies)
    if (p.exclude_companies) setExcludeCompanies(p.exclude_companies)
    if (p.min_stipend) setMinStipend(String(p.min_stipend))
    if (p.match_threshold) setMatchThreshold(p.match_threshold)
    
    if (profile.cover_letter) setCoverLetter(profile.cover_letter)
  }, [profile?.job_preferences, profile?.cover_letter])

  // ── Derived ──────────────────────────────────────────────────────────────
  const hasResume = !!profile?.resume_url
  const hasAnyCred = credStatus && Object.values(credStatus).some(Boolean)

  // ── Handlers: resume upload ───────────────────────────────────────────────
  async function handleUpload() {
    if (!selectedFile) return
    setUploadState('uploading')
    setUploadError('')
    try {
      const fd = new FormData()
      fd.append('file', selectedFile)
      await api.post('/onboarding/resume', fd)
      qc.invalidateQueries({ queryKey: ['profile'] })
      setUploadState('done')
      setSelectedFile(null)
    } catch (err: any) {
      setUploadState('error')
      const d = err?.response?.data?.detail
      setUploadError(typeof d === 'string' ? d : d?.message || 'Upload failed. Please try again.')
    }
  }

  // ── Handler: save ALL job targeting preferences at once ─────────────────
  async function saveAllTargeting() {
    setSavingTargeting(true)
    setTargetingSaved(false)
    setTargetingError('')
    
    // Auto-add current inputs if user forgot to press Enter
    const finalTitles = titleInput && !jobTitles.includes(titleInput) ? [...jobTitles, titleInput] : jobTitles;
    const finalLocations = locationInput && !locations.includes(locationInput) ? [...locations, locationInput] : locations;
    const finalKeywords = keywordInput && !keywords.includes(keywordInput) ? [...keywords, keywordInput] : keywords;
    const finalTargets = targetInput && !targetCompanies.includes(targetInput) ? [...targetCompanies, targetInput] : targetCompanies;
    const finalExcludes = excludeInput && !excludeCompanies.includes(excludeInput) ? [...excludeCompanies, excludeInput] : excludeCompanies;

    try {
      await api.post('/onboarding/preferences', {
        job_titles: finalTitles,
        employment_types: employmentTypes,
        locations: finalLocations,
        remote,
        work_mode: workMode,
        keywords: finalKeywords,
        target_companies: finalTargets,
        exclude_companies: finalExcludes,
        min_stipend: minStipend ? Number(minStipend) : undefined,
        match_threshold: matchThreshold,
      })
      qc.invalidateQueries({ queryKey: ['profile'] })
      setTargetingSaved(true)
      
      // Clear inputs if they were added
      if (titleInput) setTitleInput("");
      if (locationInput) setLocationInput("");
      if (keywordInput) setKeywordInput("");
      if (targetInput) setTargetInput("");
      if (excludeInput) setExcludeInput("");
      
      setTimeout(() => setTargetingSaved(false), 3000)
    } catch {
      setTargetingError('Failed to save. Please try again.')
    } finally {
      setSavingTargeting(false)
    }
  }

  // ── Handler: platform credentials ────────────────────────────────────────
  async function savePlatformCred(platform: Platform) {
    const { email, password } = credForm[platform]
    if (!email || !password) {
      setCredMsg(m => ({ ...m, [platform]: 'Email and password are required.' }))
      return
    }
    setSavingCred(platform)
    try {
      await api.post('/onboarding/credentials', {
        platforms: { [platform]: { email, password } },
      })
      setCredMsg(m => ({ ...m, [platform]: 'Saved successfully.' }))
      qc.invalidateQueries({ queryKey: ['cred-status'] })
      setExpandedPlatform(null)
    } catch {
      setCredMsg(m => ({ ...m, [platform]: 'Failed to save. Try again.' }))
    } finally {
      setSavingCred(null)
    }
  }

  // ── Handler: save cover letter ───────────────────────────────────────────
  async function saveCoverLetterField() {
    setSavingCoverLetter(true)
    setCoverLetterSaved(false)
    try {
      await api.post('/onboarding/autofill', {
        cover_letter: coverLetter
      })
      qc.invalidateQueries({ queryKey: ['profile'] })
      setCoverLetterSaved(true)
      setTimeout(() => setCoverLetterSaved(false), 3000)
    } catch {
      // ignore
    } finally {
      setSavingCoverLetter(false)
    }
  }

  // ── LinkedIn cookie bypass handlers ──────────────────────────────────────
  async function saveLinkedInCookies() {
    const text = cookiesText.trim()
    if (!text) { setCookieMsg('Paste your LinkedIn cookies JSON first.'); setCookieStatus('error'); return }
    try {
      JSON.parse(text)
    } catch {
      setCookieMsg('Invalid JSON. Copy the exact output from the cookie export extension.')
      setCookieStatus('error')
      return
    }
    setCookieStatus('saving')
    setCookieMsg('')
    try {
      const res = await api.post('/onboarding/linkedin-cookies', { cookies_json: text })
      setCookieMsg(`Saved ${res.data.count} cookies. LinkedIn will now use these to log in.`)
      setCookieStatus('saved')
      setCookiesStored(true)
      setCookiesText('')
      qc.invalidateQueries({ queryKey: ['li-cookies'] })
    } catch (err: any) {
      const d = err?.response?.data?.detail
      setCookieMsg(typeof d === 'string' ? d : 'Failed to save cookies.')
      setCookieStatus('error')
    }
  }

  async function deleteLinkedInCookies() {
    try {
      await api.delete('/onboarding/linkedin-cookies')
      setCookiesStored(false)
      setCookieMsg('Cookies removed.')
      setCookieStatus('idle')
      qc.invalidateQueries({ queryKey: ['li-cookies'] })
    } catch {
      setCookieMsg('Failed to remove.')
    }
  }

  // ── Tag helpers ───────────────────────────────────────────────────────────
  function makeTagHandlers(
    tags: string[],
    setTags: React.Dispatch<React.SetStateAction<string[]>>,
    setInput: React.Dispatch<React.SetStateAction<string>>,
  ) {
    return {
      onAdd: (val: string) => {
        const v = val.trim()
        if (!v || tags.includes(v)) return
        setTags(prev => [...prev, v])
        setInput('')
      },
      onRemove: (val: string) => setTags(prev => prev.filter(x => x !== val)),
    }
  }

  const titleHandlers = makeTagHandlers(jobTitles, setJobTitles, setTitleInput)
  const locationHandlers = makeTagHandlers(locations, setLocations, setLocationInput)
  const keywordHandlers = makeTagHandlers(keywords, setKeywords, setKeywordInput)
  const targetHandlers = makeTagHandlers(targetCompanies, setTargetCompanies, setTargetInput)
  const excludeHandlers = makeTagHandlers(excludeCompanies, setExcludeCompanies, setExcludeInput)

  // ── Agent readiness ───────────────────────────────────────────────────────
  const readinessItems = [
    { label: 'Resume uploaded', ok: hasResume },
    { label: 'Job titles set', ok: jobTitles.length > 0 },
    { label: 'Employment type set', ok: employmentTypes.length > 0 },
    { label: 'At least one platform credential', ok: !!hasAnyCred, warn: !hasAnyCred },
  ]
  const allReady = readinessItems.every(i => i.ok)

  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Credentials &amp; Profile</h1>
        <p className="text-sm text-slate-500 mt-1">
          Your account info, resume, job targeting preferences, and platform credentials.
        </p>
      </div>

      {/* ── 1. Account ───────────────────────────────────────────────────────── */}
      <Section title="Account" icon={User}>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-slate-500">Name</p>
            <p className="font-medium">{user?.name || '—'}</p>
          </div>
          <div>
            <p className="text-slate-500">Email</p>
            <p className="font-medium">{user?.email || '—'}</p>
          </div>
          <div>
            <p className="text-slate-500">Plan</p>
            <Badge variant={user?.plan === 'pro' ? 'default' : 'secondary'}>
              {user?.plan?.toUpperCase() || 'FREE'}
            </Badge>
          </div>
          <div>
            <p className="text-slate-500">Applications today</p>
            <p className="font-medium">
              {usage ? `${usage.applies_today} / ${usage.applies_limit}` : '—'}
            </p>
          </div>
        </div>
      </Section>

      {/* ── 2. Resume ────────────────────────────────────────────────────────── */}
      <Section title="Resume" icon={FileText}>
        <div className="space-y-4">
          {/* Upload subsection */}
          <div className="space-y-3">
            <p className="text-xs font-medium text-slate-600 uppercase tracking-wide">Upload</p>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.doc,.docx"
              className="hidden"
              onChange={e => {
                const f = e.target.files?.[0] ?? null
                setSelectedFile(f)
                setUploadState('idle')
                setUploadError('')
              }}
            />
            {!selectedFile ? (
              <Button
                size="sm"
                variant="outline"
                onClick={() => fileInputRef.current?.click()}
                type="button"
              >
                Upload Resume
              </Button>
            ) : (
              <div className="flex items-center gap-3">
                <span className="text-sm text-slate-700 truncate max-w-xs">{selectedFile.name}</span>
                <Button
                  size="sm"
                  onClick={handleUpload}
                  disabled={uploadState === 'uploading'}
                  type="button"
                >
                  {uploadState === 'uploading' ? 'Uploading...' : 'Upload'}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => { setSelectedFile(null); setUploadState('idle') }}
                  type="button"
                >
                  <X className="h-3 w-3" />
                </Button>
              </div>
            )}
            {uploadState === 'done' && (
              <p className="text-xs text-green-600 flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" /> Resume uploaded successfully.
              </p>
            )}
            {uploadState === 'error' && (
              <p className="text-xs text-red-500 flex items-center gap-1">
                <XCircle className="h-3 w-3" /> {typeof uploadError === 'string' ? uploadError : JSON.stringify(uploadError)}
              </p>
            )}
          </div>

          {/* Analysis subsection */}
          {profile?.resume_url && (
            <>
              <Separator />
              <div className="space-y-3 text-sm">
                <p className="text-xs font-medium text-slate-600 uppercase tracking-wide">Analysis</p>
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />
                  <span className="font-medium">{profile.resume_filename}</span>
                </div>

                {profile.extracted_data?.error ? (
                  <div className="flex items-center gap-2 text-amber-700 bg-amber-50 rounded p-2 text-xs">
                    <AlertCircle className="h-4 w-4 shrink-0" />
                    {profile.extracted_data.error}
                  </div>
                ) : profile.extracted_data ? (
                  <div className="space-y-3">
                    {/* Contact row */}
                    <div className="grid grid-cols-2 gap-3">
                      {profile.extracted_data.name && (
                        <div>
                          <p className="text-slate-500 text-xs">Name</p>
                          <p>{profile.extracted_data.name}</p>
                        </div>
                      )}
                      {profile.extracted_data.email && (
                        <div>
                          <p className="text-slate-500 text-xs">Email</p>
                          <p className="truncate">{profile.extracted_data.email}</p>
                        </div>
                      )}
                      {profile.extracted_data.phone && (
                        <div>
                          <p className="text-slate-500 text-xs">Phone</p>
                          <p>{profile.extracted_data.phone}</p>
                        </div>
                      )}
                      {profile.extracted_data.location && (
                        <div>
                          <p className="text-slate-500 text-xs">Location</p>
                          <p>{profile.extracted_data.location}</p>
                        </div>
                      )}
                    </div>

                    {/* Skills */}
                    {profile.extracted_data.skills?.length > 0 && (
                      <div>
                        <p className="text-slate-500 text-xs mb-1">Skills</p>
                        <div className="flex flex-wrap gap-1">
                          {profile.extracted_data.skills.map((s: string) => (
                            <Badge key={s} variant="secondary" className="text-xs">{s}</Badge>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Experience */}
                    {profile.extracted_data.experience?.length > 0 && (
                      <div>
                        <p className="text-slate-500 text-xs mb-1">Experience</p>
                        <ul className="list-disc list-inside space-y-0.5">
                          {profile.extracted_data.experience.slice(0, 4).map((e: any, i: number) => (
                            <li key={i} className="truncate">
                              {typeof e === 'string'
                                ? e
                                : [e.role, e.company, e.duration].filter(Boolean).join(' · ')}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Education */}
                    {profile.extracted_data.education?.length > 0 && (
                      <div>
                        <p className="text-slate-500 text-xs mb-1">Education</p>
                        <ul className="list-disc list-inside space-y-0.5">
                          {profile.extracted_data.education.slice(0, 3).map((e: any, i: number) => (
                            <li key={i}>
                              {typeof e === 'string'
                                ? e
                                : [e.degree, e.institution, e.year].filter(Boolean).join(' · ')}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ) : null}
              </div>
            </>
          )}
        </div>
      </Section>

      {/* ── 2.5 Cover Letter ─────────────────────────────────────────────────── */}
      <Section title="Cover Letter" icon={FileText}>
        <div className="space-y-4">
          <p className="text-sm text-slate-500">
            Write a generic cover letter that the agent will use for applications.
          </p>
          <div className="space-y-1.5">
            <Label className="text-xs text-slate-500">Default Cover Letter</Label>
            <textarea
              className="w-full min-h-[200px] p-3 text-sm border rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
              value={coverLetter}
              onChange={e => setCoverLetter(e.target.value)}
              placeholder="I am excited to apply for..."
            />
          </div>
          <div className="flex items-center gap-3">
            <Button
              size="sm"
              onClick={saveCoverLetterField}
              disabled={savingCoverLetter}
            >
              {savingCoverLetter ? 'Saving...' : 'Save Cover Letter'}
            </Button>
            {coverLetterSaved && (
              <span className="flex items-center gap-1 text-sm text-green-600">
                <CheckCircle2 className="h-4 w-4" /> Saved!
              </span>
            )}
          </div>
        </div>
      </Section>

      {/* ── 3. Job Targeting ─────────────────────────────────────────────────── */}
      <Section title="Job Targeting" icon={Briefcase}>
        <div className="space-y-6">

          {/* ── What roles? ── */}
          <div className="space-y-4">
            <p className="text-sm font-semibold text-slate-700">What roles?</p>

            {/* Job Titles */}
            <div className="space-y-1.5">
              <Label className="text-xs text-slate-500">Job Titles</Label>
              <TagInput
                tags={jobTitles}
                onAdd={titleHandlers.onAdd}
                onRemove={titleHandlers.onRemove}
                input={titleInput}
                setInput={setTitleInput}
                placeholder="Type a role and press Enter..."
                suggestions={JOB_ROLE_SUGGESTIONS}
              />
            </div>

            {/* Job Type */}
            <div className="space-y-1.5">
              <Label className="text-xs text-slate-500">Job Type</Label>
              <div className="flex flex-wrap gap-2">
                {EMPLOYMENT_TYPES.map(type => {
                  const active = employmentTypes.includes(type)
                  return (
                    <button
                      key={type}
                      type="button"
                      onClick={() =>
                        setEmploymentTypes(prev =>
                          active ? prev.filter(t => t !== type) : [...prev, type]
                        )
                      }
                      className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                        active
                          ? 'bg-blue-600 text-white border-blue-600'
                          : 'border-dashed border-slate-300 text-slate-600 hover:bg-slate-50'
                      }`}
                    >
                      {type}
                    </button>
                  )
                })}
              </div>
            </div>

          </div>

          <Separator />

          {/* ── Where & How? ── */}
          <div className="space-y-4">
            <p className="text-sm font-semibold text-slate-700">Where &amp; How?</p>

            {/* Locations */}
            <div className="space-y-1.5">
              <Label className="text-xs text-slate-500">Locations</Label>
              <TagInput
                tags={locations}
                onAdd={locationHandlers.onAdd}
                onRemove={locationHandlers.onRemove}
                input={locationInput}
                setInput={setLocationInput}
                placeholder="Add a city or region..."
                suggestions={LOCATION_SUGGESTIONS}
              />
            </div>

            {/* Remote toggle */}
            <div className="flex items-center gap-2">
              <input
                id="remote-toggle"
                type="checkbox"
                checked={remote}
                onChange={e => setRemote(e.target.checked)}
                className="h-4 w-4 accent-blue-600"
              />
              <Label htmlFor="remote-toggle" className="text-sm cursor-pointer">
                Open to remote
              </Label>
            </div>

            {/* Work Mode */}
            <div className="space-y-1.5">
              <Label className="text-xs text-slate-500">Work Mode</Label>
              <div className="flex gap-2">
                {WORK_MODES.map(mode => {
                  const active = workMode === mode
                  return (
                    <button
                      key={mode}
                      type="button"
                      onClick={() => setWorkMode(active ? '' : mode)}
                      className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                        active
                          ? 'bg-blue-600 text-white border-blue-600'
                          : 'border-dashed border-slate-300 text-slate-600 hover:bg-slate-50'
                      }`}
                    >
                      {mode}
                    </button>
                  )
                })}
              </div>
            </div>

          </div>

          <Separator />

          {/* ── Advanced (collapsible) ── */}
          <div className="space-y-3">
            <button
              type="button"
              onClick={() => setShowAdvanced(v => !v)}
              className="flex items-center gap-1 text-sm font-semibold text-slate-700 hover:text-slate-900 transition-colors"
            >
              {showAdvanced ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              Advanced
            </button>

            {showAdvanced && (
              <div className="space-y-4 pl-1">
                {/* Keywords */}
                <div className="space-y-1.5">
                  <Label className="text-xs text-slate-500">Keywords (skills/tech terms)</Label>
                  <TagInput
                    tags={keywords}
                    onAdd={keywordHandlers.onAdd}
                    onRemove={keywordHandlers.onRemove}
                    input={keywordInput}
                    setInput={setKeywordInput}
                    placeholder="e.g. React, Python..."
                  />
                </div>

                {/* Target Companies */}
                <div className="space-y-1.5">
                  <Label className="text-xs text-slate-500">Target Companies</Label>
                  <TagInput
                    tags={targetCompanies}
                    onAdd={targetHandlers.onAdd}
                    onRemove={targetHandlers.onRemove}
                    input={targetInput}
                    setInput={setTargetInput}
                    placeholder="e.g. Google, Stripe..."
                  />
                </div>

                {/* Exclude Companies */}
                <div className="space-y-1.5">
                  <Label className="text-xs text-slate-500">Exclude Companies</Label>
                  <TagInput
                    tags={excludeCompanies}
                    onAdd={excludeHandlers.onAdd}
                    onRemove={excludeHandlers.onRemove}
                    input={excludeInput}
                    setInput={setExcludeInput}
                    placeholder="Companies to skip..."
                  />
                </div>

                {/* Min Stipend */}
                <div className="space-y-1.5 max-w-xs">
                  <Label className="text-xs text-slate-500">Min Stipend / Salary</Label>
                  <Input
                    type="number"
                    placeholder="e.g. 20000"
                    value={minStipend}
                    onChange={e => setMinStipend(e.target.value)}
                    className="h-8 text-sm"
                  />
                </div>

                {/* Match Threshold */}
                <div className="space-y-1.5 max-w-xs">
                  <Label className="text-xs text-slate-500">Min match score (%)</Label>
                  <Input
                    type="number"
                    min={0}
                    max={100}
                    value={matchThreshold}
                    onChange={e => setMatchThreshold(Number(e.target.value))}
                    className="h-8 text-sm"
                  />
                </div>

              </div>
            )}
          </div>

          <Separator />

          {/* ── Save All ── */}
          <div className="flex items-center gap-3 pt-1">
            <Button
              onClick={saveAllTargeting}
              disabled={savingTargeting}
              className="min-w-[160px]"
            >
              {savingTargeting ? 'Saving...' : 'Save Job Targeting'}
            </Button>
            {targetingSaved && (
              <span className="flex items-center gap-1 text-sm text-green-600">
                <CheckCircle2 className="h-4 w-4" /> Saved!
              </span>
            )}
            {targetingError && (
              <span className="flex items-center gap-1 text-sm text-red-500">
                <XCircle className="h-4 w-4" /> {targetingError}
              </span>
            )}
          </div>
        </div>
      </Section>

      {/* ── 4. Platform Credentials ──────────────────────────────────────────── */}
      <Section title="Platform Credentials" icon={KeyRound}>
        {!hasAnyCred && (
          <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 rounded p-3 mb-4">
            <XCircle className="h-4 w-4 shrink-0" />
            No platform credentials found. The agent cannot log in to apply for jobs until you add them below.
          </div>
        )}
        <div className="space-y-3">
          {PLATFORMS.map(platform => {
            const stored = credStatus?.[platform] ?? false
            const isOpen = expandedPlatform === platform
            return (
              <div key={platform} className="border rounded-lg overflow-hidden">
                <button
                  type="button"
                  className="w-full flex items-center justify-between p-3 hover:bg-slate-50 transition-colors"
                  onClick={() => setExpandedPlatform(isOpen ? null : platform)}
                >
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <StatusIcon ok={stored} />
                    {PLATFORM_LABELS[platform]}
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={stored ? 'default' : 'secondary'} className="text-xs">
                      {stored ? 'Configured' : 'Not set'}
                    </Badge>
                    {isOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                  </div>
                </button>
                {isOpen && (
                  <div className="px-3 pb-3 pt-1 border-t bg-slate-50 space-y-3">
                    <div className="space-y-2">
                      <div>
                        <Label className="text-xs">Email</Label>
                        <Input
                          type="email"
                          className="h-8 text-sm mt-1"
                          placeholder={`${PLATFORM_LABELS[platform]} email`}
                          value={credForm[platform].email}
                          onChange={e =>
                            setCredForm(f => ({ ...f, [platform]: { ...f[platform], email: e.target.value } }))
                          }
                        />
                      </div>
                      <div>
                        <Label className="text-xs">Password</Label>
                        <div className="flex gap-2 mt-1">
                          <Input
                            type={showPwd[platform] ? 'text' : 'password'}
                            className="h-8 text-sm"
                            placeholder="Password"
                            value={credForm[platform].password}
                            onChange={e =>
                              setCredForm(f => ({ ...f, [platform]: { ...f[platform], password: e.target.value } }))
                            }
                          />
                          <Button
                            size="sm"
                            variant="ghost"
                            type="button"
                            className="h-8 px-2 text-xs"
                            onClick={() => setShowPwd(s => ({ ...s, [platform]: !s[platform] }))}
                          >
                            {showPwd[platform] ? 'Hide' : 'Show'}
                          </Button>
                        </div>
                      </div>
                    </div>
                    {credMsg[platform] && (
                      <p
                        className={`text-xs ${
                          credMsg[platform].includes('success') ? 'text-green-600' : 'text-red-500'
                        }`}
                      >
                        {credMsg[platform]}
                      </p>
                    )}
                    <Button
                      size="sm"
                      className="w-full h-8"
                      disabled={savingCred === platform}
                      onClick={() => savePlatformCred(platform)}
                    >
                      {savingCred === platform
                        ? 'Saving...'
                        : stored
                        ? 'Update Credentials'
                        : 'Save Credentials'}
                    </Button>
                    <p className="text-xs text-slate-400">Credentials are encrypted before storage.</p>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </Section>

      {/* ── 4.5 LinkedIn Cookie Bypass ──────────────────────────────────────── */}
      <Section title="LinkedIn Login Boost (Fix CAPTCHA)" icon={KeyRound}>
        <div className="space-y-4">
          <div className={`flex items-start gap-3 rounded p-3 text-sm ${cookiesStored ? 'bg-green-50 text-green-800' : 'bg-amber-50 text-amber-800'}`}>
            {cookiesStored ? (
              <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5 text-green-600" />
            ) : (
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-amber-600" />
            )}
            <div>
              {cookiesStored ? (
                <p>LinkedIn session cookies are saved. The agent will use them to bypass CAPTCHA/security challenges.</p>
              ) : (
                <p>
                  LinkedIn blocks automated logins with a security challenge (CAPTCHA). Provide your session cookies
                  to let the agent log in as you — no password needed.
                </p>
              )}
            </div>
          </div>

          <button
            type="button"
            className="w-full flex items-center justify-between text-sm font-medium text-slate-700 py-1"
            onClick={() => setCookiePanelOpen(o => !o)}
          >
            <span>{cookiesStored ? 'Update / Remove Cookies' : 'How to get your cookies'}</span>
            {cookiePanelOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>

          {cookiePanelOpen && (
            <div className="space-y-4 border-t pt-4">
              <ol className="list-decimal list-inside space-y-1.5 text-sm text-slate-600">
                <li>Install <strong>Cookie-Editor</strong> extension in Chrome/Firefox (free, open source)</li>
                <li>Log in to <strong>linkedin.com</strong> in your browser normally</li>
                <li>Click the Cookie-Editor icon → click <strong>Export → Export as JSON</strong></li>
                <li>Copy the entire JSON text and paste it below</li>
              </ol>

              <div className="space-y-1.5">
                <Label className="text-xs text-slate-500">Paste Cookies JSON</Label>
                <textarea
                  className="w-full h-32 p-2 text-xs font-mono border rounded-md focus:ring-2 focus:ring-blue-500 outline-none"
                  placeholder='[{"name":"li_at","value":"AQED...","domain":".linkedin.com",...}]'
                  value={cookiesText}
                  onChange={e => { setCookiesText(e.target.value); setCookieStatus('idle'); setCookieMsg('') }}
                />
              </div>

              {cookieMsg && (
                <p className={`text-xs ${cookieStatus === 'saved' ? 'text-green-600' : cookieStatus === 'error' ? 'text-red-500' : 'text-slate-500'}`}>
                  {cookieMsg}
                </p>
              )}

              <div className="flex gap-2">
                <Button size="sm" onClick={saveLinkedInCookies} disabled={cookieStatus === 'saving'}>
                  {cookieStatus === 'saving' ? 'Saving...' : 'Save Cookies'}
                </Button>
                {cookiesStored && (
                  <Button size="sm" variant="outline" onClick={deleteLinkedInCookies} className="text-red-600 border-red-200 hover:bg-red-50">
                    Remove
                  </Button>
                )}
              </div>
              <p className="text-xs text-slate-400">Cookies are encrypted before storage. They expire when you log out of LinkedIn.</p>
            </div>
          )}
        </div>
      </Section>

      {/* ── 5. Autofill Bank ─────────────────────────────────────────────────── */}
      {profile?.autofill_bank && Object.keys(profile.autofill_bank).length > 0 && (
        <Section title="Autofill Bank" icon={FileText}>
          <div className="grid grid-cols-2 gap-3 text-sm">
            {Object.entries(profile.autofill_bank).map(([k, v]) => {
              if (!v || typeof v === 'object') return null
              return (
                <div key={k}>
                  <p className="text-slate-500 text-xs capitalize">{k.replace(/_/g, ' ')}</p>
                  <p className="truncate">{String(v)}</p>
                </div>
              )
            })}
          </div>
        </Section>
      )}

      {/* ── 6. Agent Readiness ───────────────────────────────────────────────── */}
      <Section title="Agent Readiness" icon={Zap}>
        <div className="space-y-3">
          <div className="space-y-2">
            {readinessItems.map(item => (
              <div key={item.label} className="flex items-center gap-2 text-sm">
                <StatusIcon ok={item.ok} warn={item.warn} />
                <span className={item.ok ? '' : 'text-slate-500'}>{item.label}</span>
              </div>
            ))}
          </div>
          <Separator />
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">
                {allReady
                  ? 'Ready to run'
                  : `${readinessItems.filter(i => i.ok).length} / ${readinessItems.length} checks passed`}
              </p>
              {!allReady && (
                <p className="text-xs text-slate-500 mt-0.5">
                  Complete the items above before running the agent.
                </p>
              )}
            </div>
            <Button
              size="sm"
              disabled={!allReady}
              onClick={() => router.push('/dashboard')}
              className="gap-1"
            >
              <Zap className="h-3 w-3" />
              Go to Dashboard
            </Button>
          </div>
        </div>
      </Section>
    </div>
  )
}
