'use client'

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { toast } from '@/lib/use-toast'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Progress } from '@/components/ui/progress'
import {
  Zap, Square, RefreshCcw, CheckCircle2, XCircle, AlertCircle,
  Clock, Linkedin, Search, Sparkles, FileText, ArrowRight,
  Loader2, PlayCircle, History, Settings, CheckCircle, Calendar,
  BrainCircuit, ChevronRight, Lock, GraduationCap, Trophy, Briefcase,
  Terminal, ChevronDown, ChevronUp
} from 'lucide-react'
import { useRef } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import Link from 'next/link'
import { wsManager } from '@/lib/ws'

// ── Types ───────────────────────────────────────────────────────────────────

interface RunStatusResponse {
  id: string
  phase: number
  platform: string | null
  status: 'queued' | 'running' | 'completed' | 'failed' | 'paused' | 'limit_reached'
  applied_count: number
  skipped_count: number
  error_count: number
  started_at: string | null
  completed_at: string | null
}

interface Profile {
  resume_url: string | null
}

interface CredStatus {
  linkedin: boolean
  wellfound: boolean
  internshala: boolean
  unstop: boolean
  naukri: boolean
}

interface LiCookieStatus {
  stored: boolean
  has_li_at: boolean
  ready: boolean
  count: number
  expiry?: number | null
}

interface Schedule {
  cron: string
  phases: number[]
  enabled: boolean
}

interface RunLog {
  id: string
  event_type: string
  message: string
  created_at: string
}

// ── Constants ────────────────────────────────────────────────────────────────

// Phase IDs must match backend PHASE_PLATFORM: 1=linkedin, 2=internshala, 3=wellfound,
// 4=naukri, 5=unstop, 6=web_search, 7=form_fill
const PHASE_MAP = [
  { id: 1, label: 'LinkedIn', icon: Linkedin, color: '#0077B5', description: 'Apply to Easy Apply jobs on LinkedIn' },
  { id: 2, label: 'Internshala', icon: GraduationCap, color: '#00A1C1', description: 'Apply to internships on Internshala' },
  { id: 3, label: 'Wellfound', icon: Sparkles, color: '#000000', description: 'Apply to startup jobs on Wellfound' },
  { id: 4, label: 'Naukri', icon: Briefcase, color: '#2C3E50', description: 'Apply to jobs on Naukri' },
  { id: 5, label: 'Unstop', icon: Trophy, color: '#0078FF', description: 'Apply to opportunities on Unstop' },
  { id: 6, label: 'Web Search', icon: Search, color: '#4285F4', description: 'Find and apply to jobs across the web (ATS/career pages)' },
  { id: 7, label: 'Form Fill', icon: FileText, color: '#FF5733', description: 'Auto-fill open application forms in browser tabs' },
]

export default function AutomationPage() {
  const { user, token } = useAuth()
  const qc = useQueryClient()
  const [selectedPhases, setSelectedPhases] = useState<number[]>([1])
  const [isStarting, setIsStarting] = useState(false)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)

  // Live log state — keyed by run_id
  const [liveLogsOpen, setLiveLogsOpen] = useState<Record<string, boolean>>({})
  const [liveLogs, setLiveLogs] = useState<Record<string, Array<{ev: string; msg: string; ts: string}>>>({})
  const logPanelRefs = useRef<Record<string, HTMLDivElement | null>>({})
  // Error reasons collected from WS complete/error events — keyed by run_id,
  // rendered as a collapsible "Why this run failed" panel on each run card.
  const [runErrorReasons, setRunErrorReasons] = useState<Record<string, string[]>>({})

  // Schedule state
  const [schedCron, setSchedCron] = useState("0 9 * * *")
  const [schedPhases, setSchedPhases] = useState<number[]>([1])
  const [schedEnabled, setSchedEnabled] = useState(false)

  // ── WebSocket — live agent progress ──────────────────────────────────────
  useEffect(() => {
    if (!user?.id || !token) return
    const wsBase = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000'
    wsManager.connect(`${wsBase}/ws/${user.id}?token=${token}`)

    const unsub = wsManager.on('_message', (data: any) => {
      const ev = data.event || data.type
      const runId = (data.run_id as string | undefined)

      if (ev === 'applied' || ev === 'complete' || ev === 'error' || ev === 'run_complete' || ev === 'login_challenge') {
        qc.invalidateQueries({ queryKey: ['agent-runs'] })
      }
      if (ev === 'applied') {
        toast({ title: `✅ Applied: ${data.job_title || 'job'}`, description: data.company || data.message || '', variant: 'success' })
      }
      // Login/CAPTCHA challenge — surface ONCE with clear instructions,
      // don't flood the user with `error` toasts for every challenge line.
      if (ev === 'login_challenge') {
        const platform = (data.platform || 'platform').toString()
        toast({
          title: `⚠️ ${platform.charAt(0).toUpperCase() + platform.slice(1)} challenge`,
          description: data.action_required || 'Solve the security challenge in the Chrome window, then click Run again.',
          variant: 'error',
        })
        if (runId) {
          setRunErrorReasons(prev => ({
            ...prev,
            [runId]: [...(prev[runId] || []), `LOGIN CHALLENGE [${platform}]: ${data.message || ''}`].slice(-10),
          }))
        }
      }
      // Capture error_reasons on `error` events so they render even before completion
      if (ev === 'error' && runId && data.message) {
        setRunErrorReasons(prev => ({
          ...prev,
          [runId]: [...(prev[runId] || []), String(data.message)].slice(-10),
        }))
      }
      if (ev === 'complete' || ev === 'run_complete') {
        const reasons: string[] = Array.isArray(data.error_reasons) ? data.error_reasons : []
        const appliedCount = Number(data.applied_count ?? 0)
        const ok = appliedCount > 0
        const reasonText = reasons.length
          ? `\n• ${reasons.slice(0, 3).join('\n• ')}`
          : ''
        toast({
          title: ok ? `🏁 Agent finished — ${appliedCount} applied` : '⚠️ Finished with 0 applications',
          description: (data.summary || data.message || '') + reasonText,
          variant: ok ? 'default' : 'error',
        })
        if (runId && reasons.length) {
          setRunErrorReasons(prev => ({
            ...prev,
            [runId]: [...(prev[runId] || []), ...reasons].slice(-10),
          }))
        }
      }

      // Capture event logs by run_id (do not broadcast to all run panels)
      const msg: string = data.message || data.job_title || data.summary || ''
      if (msg) {
        const ts = new Date().toLocaleTimeString('en-US', { hour12: false })
        setLiveLogs(prev => {
          const updated = { ...prev }

          // Keep a global latest buffer for newly opened panels
          updated['__latest__'] = [...(updated['__latest__'] || []).slice(-499), { ev, msg, ts }]

          // Route to specific run only when run_id is available
          if (runId) {
            updated[runId] = [...(updated[runId] || []).slice(-499), { ev, msg, ts }]
          } else {
            // Fallback for legacy events without run_id: append only to currently open panels
            Object.keys(updated)
              .filter((k) => k !== '__latest__')
              .forEach((rid) => {
                updated[rid] = [...(updated[rid] || []).slice(-499), { ev, msg, ts }]
              })
          }

          return updated
        })
      }
    })

    return () => {
      unsub()
      wsManager.disconnect()
    }
  }, [user?.id, token, qc])

  // ── Queries ──────────────────────────────────────────────────────────────

  const { data: runs = [], isLoading: loadingRuns } = useQuery<RunStatusResponse[]>({
    queryKey: ['agent-runs'],
    queryFn: () => api.get('/agents/runs', { silent: true }).then(r => r.data),
    retry: false,
    refetchInterval: (query) => {
        const data = query.state.data as RunStatusResponse[] | undefined
        return data?.some(r => r.status === 'running' || r.status === 'queued') ? 3000 : false
    }
  })

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

  // LinkedIn session-cookie status — rich shape from /onboarding/linkedin-cookies-status
  const { data: liCookieStatus } = useQuery<LiCookieStatus>({
    queryKey: ['li-cookies'],
    queryFn: () => api.get('/onboarding/linkedin-cookies-status', { silent: true }).then(r => r.data),
    retry: false,
    staleTime: 30_000,
  })

  // Schedule query
  useQuery<Schedule>({
    queryKey: ['schedule'],
    queryFn: () => api.get('/agents/schedule', { silent: true }).then(r => {
      if (r.data) {
        setSchedCron(r.data.cron || "0 9 * * *")
        setSchedPhases(r.data.phases || [1])
        setSchedEnabled(r.data.enabled || false)
      }
      return r.data
    }),
    retry: false,
  })

  const { data: runLogs = [], isLoading: loadingLogs } = useQuery<RunLog[]>({
    queryKey: ['run-logs', selectedRunId],
    queryFn: () => api.get(`/agents/runs/${selectedRunId}/logs`, { silent: true }).then(r => r.data),
    enabled: !!selectedRunId,
    retry: false,
  })

  // ── Mutations ────────────────────────────────────────────────────────────

  const startMutation = useMutation({
    mutationFn: (phases: number[]) => api.post('/agents/run', { phases }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agent-runs'] })
      setIsStarting(false)
      toast({ title: 'Agents launched', description: 'Your automation is now running.', variant: 'success' })
    },
    onError: () => setIsStarting(false)
  })

  const stopMutation = useMutation({
    mutationFn: (id: string) => api.post(`/agents/pause/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agent-runs'] })
      toast({ title: 'Agent stopped', description: 'The automation has been paused.', variant: 'default' })
    },
  })

  const scheduleMutation = useMutation({
    mutationFn: (data: Schedule) => api.post('/agents/schedule', data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['schedule'] })
      toast({ title: 'Schedule saved', description: 'Automation schedule updated.', variant: 'success' })
    }
  })

  const analyzeMutation = useMutation({
    mutationFn: (runId: string) => api.post(`/agents/runs/${runId}/analyze`).then(r => r.data),
  })

  // ── Handlers ─────────────────────────────────────────────────────────────

  const togglePhase = (id: number) => {
    setSelectedPhases(prev =>
      prev.includes(id) ? prev.filter(p => p !== id) : [...prev, id]
    )
  }

  const handleStart = () => {
    if (selectedPhases.length === 0) return
    setIsStarting(true)
    startMutation.mutate(selectedPhases)
  }

  const toggleLiveLogs = (runId: string) => {
    setLiveLogsOpen(prev => {
      const opening = !prev[runId]
      if (opening) {
        // Seed this run's log panel with the global __latest__ buffer
        setLiveLogs(prev2 => ({
          ...prev2,
          [runId]: prev2['__latest__'] ? [...prev2['__latest__']] : [],
        }))
      }
      return { ...prev, [runId]: opening }
    })
  }

  const handleSaveSchedule = (enabled: boolean) => {
    setSchedEnabled(enabled)
    scheduleMutation.mutate({ cron: schedCron, phases: schedPhases, enabled })
  }

  // ── Derived ──────────────────────────────────────────────────────────────

  const hasResume = !!profile?.resume_url
  // Accept EITHER a stored password-credential OR valid LinkedIn session cookies.
  // Without this, users who set up cookie-auth see "Setup Required" forever.
  const hasLinkedInCookies = liCookieStatus?.ready === true
  const hasCreds = !!(
    (credStatus && (credStatus.linkedin || credStatus.wellfound || credStatus.internshala)) ||
    hasLinkedInCookies
  )
  const isReady = hasResume && hasCreds

  const activeRuns = runs.filter(r => r.status === 'running' || r.status === 'queued')
  const completedRuns = runs.filter(r => r.status !== 'running' && r.status !== 'queued')

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running': return 'bg-blue-500 animate-pulse'
      case 'queued': return 'bg-amber-500'
      case 'completed': return 'bg-emerald-500'
      case 'failed': return 'bg-red-500'
      case 'paused': return 'bg-slate-400'
      default: return 'bg-slate-400'
    }
  }

  return (
    <div className="max-w-5xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Automation Center</h1>
          <p className="text-muted-foreground mt-1 text-lg">Deploy AI agents to find and apply for jobs automatically.</p>
        </div>
        <div className="flex gap-2">
            <Link href="/credentials">
                <Button variant="outline" size="sm" className="gap-2">
                    <Settings className="h-4 w-4" /> Credentials
                </Button>
            </Link>
        </div>
      </div>

      {!isReady && (
        <Card className="border-amber-200 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-900/50">
          <CardContent className="pt-6">
            <div className="flex gap-4">
              <div className="flex-shrink-0">
                <AlertCircle className="h-6 w-6 text-amber-600 dark:text-amber-400" />
              </div>
              <div>
                <CardTitle className="text-amber-800 dark:text-amber-300 text-lg">Setup Required</CardTitle>
                <CardDescription className="text-amber-700 dark:text-amber-400 mt-1">
                    To start the automation, you need to upload your resume and set up your platform credentials.
                </CardDescription>
                <div className="flex flex-wrap gap-4 mt-4">
                    <div className="flex items-center gap-2 text-sm">
                        {hasResume ? <CheckCircle className="h-4 w-4 text-emerald-600" /> : <XCircle className="h-4 w-4 text-red-500" />}
                        Resume Uploaded
                    </div>
                    <div className="flex items-center gap-2 text-sm">
                        {hasCreds ? <CheckCircle className="h-4 w-4 text-emerald-600" /> : <XCircle className="h-4 w-4 text-red-500" />}
                        {hasLinkedInCookies ? 'LinkedIn Cookies ✓' : 'Platform Credentials'}
                    </div>
                </div>
                <Link href="/credentials" className="mt-4 inline-block">
                    <Button variant="outline" size="sm" className="bg-white hover:bg-amber-100 border-amber-300 text-amber-800">
                      Complete Setup <ArrowRight className="h-4 w-4 ml-2" />
                    </Button>
                </Link>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column: Start Run */}
        <div className="lg:col-span-2 space-y-8">
          <Card className="overflow-hidden border-2 border-[hsl(var(--color-accent))]/10 shadow-lg">
            <CardHeader className="bg-slate-50/50 dark:bg-slate-900/50 border-b">
              <CardTitle className="flex items-center gap-2">
                <Zap className="h-5 w-5 text-[hsl(var(--color-accent))]" />
                Start New Automation
              </CardTitle>
              <CardDescription>Select the platforms you want the AI to target.</CardDescription>
            </CardHeader>
            <CardContent className="pt-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
                {PHASE_MAP.map((phase) => (
                  <div 
                    key={phase.id}
                    onClick={() => togglePhase(phase.id)}
                    className={`
                      relative group cursor-pointer p-4 rounded-xl border-2 transition-all duration-200
                      ${selectedPhases.includes(phase.id) 
                        ? 'border-[hsl(var(--color-accent))] bg-[hsl(var(--color-accent))]/5 shadow-md' 
                        : 'border-border hover:border-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800/50'
                      }
                    `}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        <div className={`p-2 rounded-lg bg-white dark:bg-slate-800 shadow-sm border ${selectedPhases.includes(phase.id) ? 'border-[hsl(var(--color-accent))]/30' : 'border-border'}`}>
                            <phase.icon className="h-5 w-5" style={{ color: phase.color }} />
                        </div>
                        <div>
                          <p className="font-bold">{phase.label}</p>
                          <p className="text-xs text-muted-foreground mt-0.5">{phase.description}</p>
                        </div>
                      </div>
                      <Checkbox 
                        checked={selectedPhases.includes(phase.id)} 
                        className="rounded-full h-5 w-5 mt-1"
                        id={`phase-${phase.id}`}
                      />
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-900/50 rounded-xl border border-dashed">
                <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                        <Sparkles className="h-5 w-5 text-blue-600" />
                    </div>
                    <div>
                        <p className="text-sm font-semibold">AI Match Score Enabled</p>
                        <p className="text-xs text-muted-foreground">Agents will only apply to jobs with {'>'}60% match score.</p>
                    </div>
                </div>
                <Button 
                    onClick={handleStart}
                    disabled={!isReady || selectedPhases.length === 0 || isStarting}
                    className="gap-2 h-11 px-8 font-bold shadow-xl shadow-[hsl(var(--color-accent))]/20"
                    style={{ background: 'linear-gradient(135deg, hsl(var(--color-accent)), hsl(var(--color-accent-hover)))' }}
                >
                    {isStarting ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                        <PlayCircle className="h-4 w-4" />
                    )}
                    Launch Agents
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Active Runs */}
          {activeRuns.length > 0 && (
            <div className="space-y-4">
              <h2 className="text-xl font-bold flex items-center gap-2 px-1">
                <RefreshCcw className="h-5 w-5 text-blue-500" style={{ animation: 'spin-slow 3s linear infinite' }} />
                Active Missions
              </h2>
              <div className="space-y-4">
                {activeRuns.map((run) => (
                  <Card key={run.id} className="relative overflow-hidden group border-blue-500/20 bg-blue-50/10 dark:bg-blue-900/5 shadow-md">
                    <div className="absolute top-0 left-0 w-1 h-full bg-blue-500" />
                    <CardContent className="p-5">
                      <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-3">
                          <div className="p-2 rounded-lg bg-blue-100 dark:bg-blue-900/40">
                             {(() => {
                                 // Cast to string for safe comparison with potentially mixed types
                                 const phaseObj = PHASE_MAP.find(p => String(p.id) === String(run.phase));
                                 const Icon = phaseObj?.icon || Zap;
                                 return <Icon className="h-5 w-5 text-blue-600" />;
                             })()}
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                                <span className="font-bold">{PHASE_MAP.find(p => String(p.id) === String(run.phase))?.label || `Phase ${run.phase}`} Agent</span>
                                <Badge variant="secondary" className={`${getStatusColor(run.status)} text-white border-0 text-[10px] uppercase font-bold py-0 h-4`}>{run.status}</Badge>
                            </div>
                            <p className="text-xs text-muted-foreground mt-0.5 font-mono">ID: {run.id.split('-')[0]}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => toggleLiveLogs(run.id)}
                            className="text-blue-500 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                          >
                            <Terminal className="h-4 w-4 mr-1" />
                            {liveLogsOpen[run.id] ? 'Hide Logs' : 'View Live'}
                            {liveLogsOpen[run.id] ? <ChevronUp className="h-3 w-3 ml-1" /> : <ChevronDown className="h-3 w-3 ml-1" />}
                          </Button>
                          <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => stopMutation.mutate(run.id)}
                              disabled={stopMutation.isPending}
                              className="text-red-500 hover:text-red-600 hover:bg-red-50 transition-colors disabled:opacity-50"
                          >
                              {stopMutation.isPending
                                ? <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                : <Square className="h-4 w-4 mr-2 fill-current" />
                              }
                              {stopMutation.isPending ? 'Stopping…' : 'Stop'}
                          </Button>
                        </div>
                      </div>

                      <div className="grid grid-cols-3 gap-4 py-3 bg-white dark:bg-slate-900/50 rounded-lg border px-4">
                        <div className="text-center border-r">
                           <p className="text-lg font-black text-emerald-600">{run.applied_count}</p>
                           <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">Applied</p>
                        </div>
                        <div className="text-center border-r">
                           <p className="text-lg font-black text-slate-500">{run.skipped_count}</p>
                           <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">Skipped</p>
                        </div>
                        <div className="text-center">
                           <p className="text-lg font-black text-red-500">{run.error_count}</p>
                           <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">Errors</p>
                        </div>
                      </div>

                      <div className="mt-4 space-y-1.5">
                        <div className="flex justify-between text-[10px] font-bold uppercase tracking-widest text-muted-foreground px-0.5">
                            <span>Processing...</span>
                            <span>{Math.min(100, Math.round(((run.applied_count + run.skipped_count + run.error_count) / 20) * 100))}%</span>
                        </div>
                        <Progress value={Math.min(100, ((run.applied_count + run.skipped_count + run.error_count) / 20) * 100)} className="h-1.5 bg-blue-100 dark:bg-blue-900/20 shadow-inner" />
                      </div>

                      {/* ── Error Reasons Panel (shown whenever errors surfaced via WS) ── */}
                      {(runErrorReasons[run.id] || []).length > 0 && (
                        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 dark:bg-red-950/20 dark:border-red-900/40 p-3">
                          <p className="text-[10px] font-bold uppercase tracking-wider text-red-600 dark:text-red-400 mb-1.5 flex items-center gap-1">
                            <AlertCircle className="h-3 w-3" /> Why this run hit errors
                          </p>
                          <ul className="space-y-0.5">
                            {runErrorReasons[run.id].map((r, i) => (
                              <li key={i} className="text-[11px] text-red-700 dark:text-red-300 font-mono break-all">• {r}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* ── Live Log Panel ── */}
                      {liveLogsOpen[run.id] && (
                        <div className="mt-4">
                          <div
                            ref={el => { logPanelRefs.current[run.id] = el }}
                            className="bg-slate-950 rounded-xl border border-slate-800 p-3 font-mono text-[11px] max-h-56 overflow-y-auto scroll-smooth"
                            style={{ scrollbarWidth: 'thin' }}
                          >
                            {(liveLogs[run.id] || []).length === 0 ? (
                              <div className="flex items-center gap-2 text-slate-500 py-4 justify-center">
                                <Loader2 className="h-3 w-3 animate-spin" />
                                <span>Waiting for agent output…</span>
                              </div>
                            ) : (
                              <div className="space-y-0.5">
                                {(liveLogs[run.id] || []).map((entry, i) => {
                                  const color =
                                    entry.ev === 'applied'  ? 'text-emerald-400' :
                                    entry.ev === 'skipped'  ? 'text-amber-400'   :
                                    entry.ev === 'error'    ? 'text-red-400'     :
                                    entry.ev === 'complete' || entry.ev === 'run_complete' ? 'text-purple-400' :
                                    'text-slate-300'
                                  return (
                                    <div key={i} className="flex gap-2 leading-relaxed">
                                      <span className="text-slate-600 shrink-0 select-none w-16">{entry.ts}</span>
                                      <span className={`shrink-0 w-12 uppercase font-bold ${color}`}>{entry.ev.slice(0,6)}</span>
                                      <span className={`${color} break-all`}>{entry.msg}</span>
                                    </div>
                                  )
                                })}
                                {/* Auto-scroll anchor */}
                                <div ref={el => {
                                  if (el) {
                                    const panel = logPanelRefs.current[run.id]
                                    if (panel) panel.scrollTop = panel.scrollHeight
                                  }
                                }} />
                              </div>
                            )}
                          </div>
                          <p className="text-[10px] text-slate-400 mt-1 px-1">
                            Live stream · {(liveLogs[run.id] || []).length} lines captured
                          </p>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )}

          {/* Schedule Automation Block */}
          <Card className="border shadow-sm">
            <CardHeader className="bg-slate-50/50 dark:bg-slate-900/50 border-b">
              <CardTitle className="flex items-center gap-2">
                <Calendar className="h-5 w-5 text-indigo-500" />
                Automated Schedule
              </CardTitle>
              <CardDescription>Run AI agents daily on a schedule.</CardDescription>
            </CardHeader>
            <CardContent className="pt-6">
               <div className="flex flex-col sm:flex-row gap-4 items-center justify-between">
                  <div className="flex gap-4 items-center w-full">
                     <Select value={schedCron} onValueChange={(v) => { setSchedCron(v as string); if (user?.plan === 'pro') handleSaveSchedule(schedEnabled); }}>
                       <SelectTrigger className="w-32">
                         <SelectValue />
                       </SelectTrigger>
                       <SelectContent>
                         <SelectItem value="0 9 * * *">9:00 AM</SelectItem>
                         <SelectItem value="0 13 * * *">1:00 PM</SelectItem>
                         <SelectItem value="0 18 * * *">6:00 PM</SelectItem>
                       </SelectContent>
                     </Select>
                     
                     <div className="flex flex-wrap gap-2">
                       {PHASE_MAP.map(p => (
                         <Button
                           key={`sched-${p.id}`}
                           variant={schedPhases.includes(p.id) ? 'default' : 'outline'}
                           size="sm"
                           className="h-9 px-3"
                           onClick={() => {
                              const newPhases = schedPhases.includes(p.id) ? schedPhases.filter(x => x !== p.id) : [...schedPhases, p.id]
                              setSchedPhases(newPhases)
                              if (user?.plan === 'pro') scheduleMutation.mutate({ cron: schedCron, phases: newPhases, enabled: schedEnabled })
                           }}
                         >
                           {p.label}
                         </Button>
                       ))}
                     </div>
                  </div>
                  
                  <div className="flex gap-2 items-center">
                    <span className="text-sm font-medium text-muted-foreground whitespace-nowrap">
                       {schedEnabled ? 'Active' : 'Paused'}
                    </span>
                    <Button 
                       disabled={user?.plan !== 'pro'}
                       variant={schedEnabled ? 'outline' : 'default'} 
                       onClick={() => handleSaveSchedule(!schedEnabled)}
                    >
                       {schedEnabled ? 'Disable' : 'Enable'}
                    </Button>
                  </div>
               </div>
               {user?.plan !== 'pro' && (
                 <p className="text-xs text-amber-600 mt-4 flex items-center gap-1">
                   <Lock className="h-3 w-3"/> Automated scheduling requires Pro plan.
                 </p>
               )}
            </CardContent>
          </Card>
        </div>

        {/* Right Column: History & Stats */}

        <div className="space-y-8">
          <Card className="shadow-lg border-2 border-slate-100 dark:border-slate-800">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-lg">
                <History className="h-4 w-4 text-slate-500" />
                Recent History
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
               {loadingRuns ? (
                 <div className="p-6 space-y-4">
                   {[...Array(3)].map((_, i) => (
                        <div key={i} className="h-12 bg-slate-100 dark:bg-slate-800 animate-pulse rounded-lg" />
                   ))}
                 </div>
               ) : completedRuns.length === 0 ? (
                 <div className="p-8 text-center bg-slate-50/50 dark:bg-slate-900/50">
                    <Clock className="h-8 w-8 text-slate-300 mx-auto mb-2" />
                    <p className="text-sm text-slate-500">No activity yet.</p>
                 </div>
               ) : (
                 <div className="divide-y">
                   {completedRuns.slice(0, 8).map((run) => (
                     <div 
                        key={run.id} 
                        className="p-4 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors cursor-pointer group"
                        onClick={() => setSelectedRunId(run.id)}
                     >
                        <div className="flex items-center justify-between mb-1">
                           <div className="flex items-center gap-2">
                               {(() => {
                                   const phaseObj = PHASE_MAP.find(p => String(p.id) === String(run.phase));
                                   const Icon = phaseObj?.icon;
                                   return Icon ? <Icon className="h-3.5 w-3.5 text-slate-500" /> : null;
                               })()}
                               <span className="text-sm font-bold group-hover:text-blue-600 transition-colors">{PHASE_MAP.find(p => String(p.id) === String(run.phase))?.label || run.platform || `Phase ${run.phase}`}</span>
                           </div>
                           <Badge variant="outline" className={`text-[9px] uppercase h-4 px-1.5 font-bold ${
                             run.status === 'completed' ? 'text-emerald-600 border-emerald-200' : 'text-red-500 border-red-200'
                           }`}>
                             {run.status}
                           </Badge>
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-muted-foreground mt-2">
                           <span className="flex items-center gap-1">
                             <CheckCircle2 className="h-3 w-3 text-emerald-500" /> {run.applied_count} applied
                           </span>
                           <span className="flex items-center gap-1">
                              {run.started_at ? new Date(run.started_at).toLocaleDateString() : '—'}
                              <ChevronRight className="h-3 w-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                           </span>
                        </div>
                        {/* Show failure reason inline in history if available */}
                        {run.status === 'failed' && (runErrorReasons[run.id] || []).length > 0 && (
                          <p className="text-[10px] text-red-500 mt-1 truncate">
                            ↳ {runErrorReasons[run.id][0]}
                          </p>
                        )}
                     </div>
                   ))}
                 </div>
               )}
               {completedRuns.length > 0 && (
                 <div className="p-3 bg-slate-50 dark:bg-slate-900/50 border-t text-center">
                    <Link href="/jobs">
                        <Button variant="ghost" size="sm" className="text-xs font-semibold hover:text-[hsl(var(--color-accent))]">
                            View All Applications <ArrowRight className="h-3 w-3 ml-1" />
                        </Button>
                    </Link>
                 </div>
               )}
            </CardContent>
          </Card>

          {/* Quick Tips */}
          <Card className="bg-gradient-to-br from-indigo-500 to-purple-600 text-white shadow-xl shadow-indigo-500/20 animate-pulse-subtle">
            <CardContent className="pt-6">
                <Sparkles className="h-8 w-8 mb-4 opacity-50" />
                <h3 className="font-bold text-lg mb-2">Pro Tip</h3>
                <p className="text-indigo-100 text-sm leading-relaxed">
                    Personalized cover letters are auto-generated for jobs with high match scores to increase your callback rate.
                </p>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Logs Modal */}
      <Dialog open={!!selectedRunId} onOpenChange={(open) => !open && setSelectedRunId(null)}>
        <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col p-4 md:p-6">
          <DialogHeader>
            <DialogTitle>Run Diagnostics</DialogTitle>
            <DialogDescription>
              Detailed logs and actions performed during this run.
            </DialogDescription>
          </DialogHeader>
          
          <div className="flex-1 overflow-y-auto bg-slate-950 rounded-md p-4 mt-2 mb-4 font-mono text-xs">
            {loadingLogs ? (
               <div className="flex items-center justify-center h-full text-slate-400 gap-2">
                 <Loader2 className="h-4 w-4 animate-spin" /> Loading logs...
               </div>
            ) : runLogs.length === 0 ? (
               <div className="text-slate-500 text-center mt-10">No logs found for this run.</div>
            ) : (
               <div className="space-y-1.5">
                 {runLogs.map(log => (
                   <div key={log.id} className="flex gap-3">
                     <span className="opacity-50 shrink-0 select-none">
                       {new Date(log.created_at).toLocaleTimeString()}
                     </span>
                     <span className={`shrink-0 w-16 uppercase ${
                       log.event_type === 'error' ? 'text-red-400' :
                       log.event_type === 'applied' ? 'text-green-400' : 
                       log.event_type === 'skipped' ? 'text-amber-400' : 'text-blue-400'
                     }`}>
                       [{log.event_type}]
                     </span>
                     <span className="text-slate-300 whitespace-pre-wrap">{log.message}</span>
                   </div>
                 ))}
               </div>
            )}
          </div>
          
          <div className="flex items-center justify-between">
            <div className="text-sm text-muted-foreground max-w-[70%]">
              {analyzeMutation.data?.advice && (
                <div className="bg-indigo-50 dark:bg-indigo-950/30 text-indigo-700 dark:text-indigo-300 p-3 rounded border border-indigo-200 dark:border-indigo-800 text-xs">
                  <span className="font-bold block mb-1">Agent Learned:</span>
                  {analyzeMutation.data.advice}
                </div>
              )}
            </div>
            <Button 
               onClick={() => selectedRunId && analyzeMutation.mutate(selectedRunId)}
               disabled={analyzeMutation.isPending || loadingLogs}
               className="gap-2 shrink-0 bg-blue-600 hover:bg-blue-700 text-white"
            >
              {analyzeMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <BrainCircuit className="h-4 w-4" />}
              Self Label / Learn
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
