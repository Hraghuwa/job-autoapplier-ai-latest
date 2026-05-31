'use client'

import Link from 'next/link'
import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import {
  Zap, Briefcase, Search, Sparkles, TrendingUp, ArrowRight,
  Loader2, CheckCircle2, PlayCircle, BarChart3,
  ShieldCheck, Globe, Linkedin, FileText
} from 'lucide-react'
import { GraphMiniMap } from '@/components/GraphMiniMap'

// --- Types ---
interface Analytics {
  total: number
  this_week: number
  response_rate: number
  avg_match_score: number | null
  by_platform: Record<string, number>
}

interface RunStatus {
  id: string
  phase: number
  status: string
  applied_count: number
  skipped_count: number
}

interface Application {
  id: string
  job_title: string
  company: string
  platform: string
  status: string
  match_score: number | null
  applied_at: string
}

const PHASE_ICONS: Record<number, any> = {
  1: Linkedin,
  2: Search,
  3: FileText,
  4: Sparkles
}

export default function DashboardPage() {
  useAuth() // keep auth guard active

  // Queries
  const { data: analytics } = useQuery<Analytics>({
    queryKey: ['job-analytics'],
    queryFn: () => api.get('/jobs/analytics', { silent: true }).then(r => r.data),
    retry: false,
  })

  const { data: activeRuns = [] } = useQuery<RunStatus[]>({
    queryKey: ['active-runs'],
    queryFn: () => api.get('/agents/runs', { silent: true }).then(r => r.data.filter((run: any) => run.status === 'running' || run.status === 'queued')),
    refetchInterval: 5000,
    retry: false,
  })

  const { data: recentJobs = [], isLoading: loadingJobs } = useQuery<Application[]>({
    queryKey: ['recent-jobs'],
    queryFn: () => api.get('/jobs', { params: { limit: 5 }, silent: true }).then(r => r.data),
    retry: false,
  })

  const { data: graphStats, isLoading: loadingGraph } = useQuery({
    queryKey: ['graph-stats'],
    queryFn: () => api.get('/graph/stats', { silent: true }).then(r => r.data),
    retry: false,
  })

  const stats = [
    {
      label: 'Total Applied',
      value: analytics?.total || 0,
      icon: Briefcase,
      color: 'text-blue-600',
      bg: 'bg-blue-100/50'
    },
    {
      label: 'Success Rate',
      value: `${analytics?.response_rate || 0}%`,
      icon: TrendingUp,
      color: 'text-emerald-600',
      bg: 'bg-emerald-100/50'
    },
    {
      label: 'Avg Match',
      value: analytics?.avg_match_score ? `${Math.round(analytics.avg_match_score)}%` : '—',
      icon: ShieldCheck,
      color: 'text-purple-600',
      bg: 'bg-purple-100/50'
    },
    {
      label: 'Active Agents',
      value: activeRuns.length,
      icon: Zap,
      color: 'text-amber-600',
      bg: 'bg-amber-100/50'
    }
  ]

  return (
    <div className="page-enter space-y-8 pb-10">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-bold tracking-tight">
            Mission <span className="text-[hsl(var(--color-accent))]">Control</span>
          </h1>
          <p className="text-muted-foreground mt-1">AI Agents are scanning for your next opportunity.</p>
        </div>
        <div className="flex gap-3">
          <Link href="/automation">
            <Button 
                className="gap-2 h-11 px-6 font-bold text-white shadow-xl shadow-[hsl(var(--color-accent))]/20"
                style={{ background: 'linear-gradient(135deg, hsl(var(--color-accent)), hsl(var(--color-accent-hover)))' }}
            >
                <PlayCircle className="h-4 w-4" />
                Launch New Agent
            </Button>
          </Link>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat) => (
          <div key={stat.label} className="bg-white dark:bg-[hsl(234,28%,14%)] border border-border rounded-2xl p-5 hover:shadow-lg transition-all duration-300">
            <div className={`p-2 w-fit rounded-lg ${stat.bg} ${stat.color} mb-3`}>
              <stat.icon className="h-5 w-5" />
            </div>
            <div className="space-y-1">
              <p className="text-2xl font-black">{stat.value}</p>
              <p className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">{stat.label}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Main Feed: Active Missions & Recent Jobs */}
        <div className="lg:col-span-2 space-y-8">
          
          {/* Active Missions */}
          {activeRuns.length > 0 && (
            <section className="space-y-4">
              <h2 className="text-xl font-bold flex items-center gap-2">
                <Zap className="h-5 w-5 text-amber-500 animate-pulse" />
                Running Agents
              </h2>
              <div className="grid gap-4">
                {activeRuns.map(run => {
                   const Icon = PHASE_ICONS[run.phase] || Zap
                   return (
                     <div key={run.id} className="bg-white dark:bg-[hsl(234,28%,14%)] border border-[hsl(var(--color-accent))]/20 rounded-2xl p-5 flex items-center justify-between shadow-sm relative overflow-hidden group hover:border-[hsl(var(--color-accent))]/40 transition-colors">
                        <div className="absolute top-0 left-0 bottom-0 w-1 bg-[hsl(var(--color-accent))]" />
                        <div className="flex items-center gap-4">
                           <div className="p-3 rounded-xl bg-[hsl(var(--color-accent))]/10">
                              <Icon className="h-6 w-6 text-[hsl(var(--color-accent))]" />
                           </div>
                           <div>
                              <p className="font-bold">Phase {run.phase} Agent</p>
                              <p className="text-sm text-muted-foreground flex items-center gap-2">
                                <span className="flex h-2 w-2 rounded-full bg-blue-500 animate-pulse" /> 
                                {run.applied_count} applied • scanning...
                              </p>
                           </div>
                        </div>
                        <Link href="/automation">
                            <Button variant="ghost" size="sm" className="gap-1 text-xs opacity-0 group-hover:opacity-100 transition-opacity">
                               Details <ArrowRight className="h-3 w-3" />
                            </Button>
                        </Link>
                     </div>
                   )
                })}
              </div>
            </section>
          )}

          {/* Recent Applications */}
          <section className="space-y-4">
            <div className="flex items-center justify-between">
                <h2 className="text-xl font-bold flex items-center gap-2">
                    <Briefcase className="h-5 w-5 text-blue-500" />
                    Latest Applications
                </h2>
                <Link href="/jobs" className="text-xs font-bold text-[hsl(var(--color-accent))] hover:underline flex items-center gap-1">
                    View All <ArrowRight className="h-3 w-3" />
                </Link>
            </div>
            
            <div className="bg-white dark:bg-[hsl(234,28%,14%)] border border-border rounded-2xl overflow-hidden divide-y divide-border">
              {loadingJobs ? (
                [1, 2, 3].map(i => <div key={i} className="p-5 h-16 animate-pulse" />)
              ) : recentJobs.length === 0 ? (
                <div className="p-10 text-center">
                    <p className="text-muted-foreground italic">No applications yet. Start an agent to begin.</p>
                </div>
              ) : (
                recentJobs.map(job => (
                  <Link key={job.id} href={`/jobs/${job.id}`}>
                      <div className="p-5 hover:bg-slate-50 dark:hover:bg-slate-900/50 transition-colors flex items-center justify-between group">
                          <div className="flex items-center gap-4 truncate">
                              <div className="h-10 w-10 shrink-0 rounded-lg bg-slate-100 dark:bg-slate-800 flex items-center justify-center font-bold text-slate-500">
                                  {job.company?.[0]}
                              </div>
                              <div className="truncate">
                                  <p className="font-bold truncate group-hover:text-[hsl(var(--color-accent))] transition-colors">{job.job_title}</p>
                                  <p className="text-xs text-muted-foreground truncate">{job.company} • {job.platform}</p>
                              </div>
                          </div>
                          <div className="flex items-center gap-4 shrink-0">
                              <Badge variant="outline" className="text-[10px] uppercase font-bold px-2 py-0.5">{job.status}</Badge>
                              {job.match_score && (
                                <div className="text-xs font-bold flex items-center gap-1">
                                    <Sparkles className="h-3 w-3 text-amber-500" />
                                    {job.match_score}%
                                </div>
                              )}
                          </div>
                      </div>
                  </Link>
                ))
              )}
            </div>
          </section>
        </div>

        {/* Right Sidebar: Profile Status & Tips */}
        <div className="space-y-8">
            <section className="bg-gradient-to-br from-slate-900 to-black p-6 rounded-2xl text-white shadow-xl">
                <h3 className="font-bold flex items-center gap-2 mb-4">
                    <ShieldCheck className="h-5 w-5 text-emerald-400" />
                    Agent Readiness
                </h3>
                <div className="space-y-4">
                    <div className="flex items-center justify-between">
                        <span className="text-sm text-slate-400">Knowledge Uploaded</span>
                        <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                    </div>
                    <div className="flex items-center justify-between">
                        <span className="text-sm text-slate-400">LinkedIn Connected</span>
                        <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                    </div>
                    <div className="flex items-center justify-between">
                        <span className="text-sm text-slate-400">Account Plan</span>
                        <Badge className="bg-amber-500 text-black border-0 text-[10px] font-bold">PRO</Badge>
                    </div>
                    <Progress value={100} className="h-1.5 bg-slate-800" />
                    <p className="text-[10px] text-slate-500 italic">Your agent is in peak condition for auto-applying.</p>
                </div>
            </section>

            <section className="bg-white dark:bg-[hsl(234,28%,14%)] border border-border p-6 rounded-2xl relative overflow-hidden">
                <div className="absolute top-0 right-0 p-3 opacity-10">
                    <Globe className="h-12 w-12 text-indigo-500" />
                </div>
                <h3 className="font-bold flex items-center gap-2 mb-4">
                    <Sparkles className="h-4 w-4 text-indigo-500" />
                    Professional Ecosystem
                </h3>
                
                {loadingGraph ? (
                    <div className="h-40 flex items-center justify-center">
                        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                    </div>
                ) : (
                    <div className="space-y-4 relative z-10">
                        <div className="h-40 w-full mb-4 border border-slate-100 dark:border-slate-800 rounded-xl overflow-hidden bg-slate-50/30 dark:bg-slate-900/10 relative group-hover:border-indigo-200/50 transition-colors">
                            <GraphMiniMap />
                        </div>

                        <div className="grid grid-cols-3 gap-2">
                            <div className="text-center p-2 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
                                <p className="text-lg font-bold text-emerald-600">{graphStats?.entity_counts?.skills || 0}</p>
                                <p className="text-[10px] text-muted-foreground font-medium">Skills</p>
                            </div>
                            <div className="text-center p-2 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
                                <p className="text-lg font-bold text-blue-600">{graphStats?.entity_counts?.companies || 0}</p>
                                <p className="text-[10px] text-muted-foreground font-medium">Targets</p>
                            </div>
                            <div className="text-center p-2 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
                                <p className="text-lg font-bold text-amber-600">{graphStats?.entity_counts?.applications || 0}</p>
                                <p className="text-[10px] text-muted-foreground font-medium">Nodes</p>
                            </div>
                        </div>
                        
                        <p className="text-xs text-muted-foreground leading-relaxed">
                            Your knowledge graph has mapped <span className="font-bold text-foreground">{graphStats?.entity_counts?.skills || 0} skills</span> across <span className="font-bold text-foreground">{graphStats?.entity_counts?.companies || 0} organizations</span>.
                        </p>
                        
                        <Link href="/graph">
                            <Button variant="outline" size="sm" className="w-full h-8 text-xs font-bold gap-2 hover:bg-indigo-50 hover:text-indigo-600 hover:border-indigo-200 transition-all">
                                Open Visualizer <ArrowRight className="h-3 w-3" />
                            </Button>
                        </Link>
                    </div>
                )}
            </section>

            <section className="bg-[hsl(var(--color-accent))]/5 border border-[hsl(var(--color-accent))]/20 p-6 rounded-2xl relative overflow-hidden group">
                <Zap className="absolute -right-4 -bottom-4 h-24 w-24 text-[hsl(var(--color-accent))]/10 group-hover:scale-110 transition-transform duration-500" />
                <h3 className="font-bold text-lg mb-2 flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-[hsl(var(--color-accent))]" />
                    Pro Tip
                </h3>
                <p className="text-sm text-muted-foreground leading-relaxed relative z-10">
                    Your AI Agent automatically tailors your application data for each specific job to bypass ATS filters and match keywords.
                </p>
                <Link href="/analytics">
                    <Button variant="link" className="px-0 text-xs font-bold text-[hsl(var(--color-accent))] mt-4">
                        View Detailed Insights <ArrowRight className="h-3 w-3 ml-1" />
                    </Button>
                </Link>
            </section>

            {/* Agent Log Shortcut */}
            <section className="bg-white dark:bg-[hsl(234,28%,14%)] border border-border p-6 rounded-2xl">
                <h3 className="font-bold flex items-center gap-2 mb-4">
                    <BarChart3 className="h-4 w-4 text-purple-500" />
                    System Status
                </h3>
                <div className="space-y-4">
                    <div className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">Gateway Connection</span>
                        <span className="font-bold text-emerald-500">STABLE</span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">AI Matching Engine</span>
                        <span className="font-bold text-blue-500">READY</span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">Browser Agents</span>
                        <span className="font-bold text-amber-500">IDLE</span>
                    </div>
                </div>
                <Link href="/automation">
                    <Button variant="ghost" size="sm" className="w-full mt-4 text-[10px] uppercase font-bold text-muted-foreground">
                        Check All Systems
                    </Button>
                </Link>
            </section>
        </div>
      </div>
    </div>
  )
}
