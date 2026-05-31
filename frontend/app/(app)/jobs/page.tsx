'use client'
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import Link from 'next/link'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import api from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { Search, ExternalLink, Lock } from 'lucide-react'
import { DndContext, DragEndEvent, closestCenter } from '@dnd-kit/core'
import { DroppableColumn } from './_components/DroppableColumn'
import { DraggableCard } from './_components/DraggableCard'

const STATUS_VARIANTS: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  applied: 'secondary',
  viewed: 'secondary',
  shortlisted: 'default',
  interview: 'default',
  offer: 'default',
  rejected: 'destructive',
}

const KANBAN_COLS = ['applied', 'viewed', 'shortlisted', 'interview', 'offer', 'rejected']

export default function JobsPage() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const [view, setView] = useState<'list' | 'kanban'>('list')
  const [search, setSearch] = useState('')
  const [platform, setPlatform] = useState('all')
  const [status, setStatus] = useState('all')

  const { data: jobs = [], isLoading } = useQuery({
    queryKey: ['jobs', platform, status, search],
    queryFn: () => {
      const params: Record<string, string> = {}
      if (platform !== 'all') params.platform = platform
      if (status !== 'all') params.status = status
      if (search) params.search = search
      return api.get('/jobs', { params, silent: true }).then((r) => r.data)
    },
    retry: false,
  })

  const updateStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api.patch(`/jobs/${id}/status`, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs'] }),
  })

  const isPro = user?.plan !== 'free'

  return (
    <div className="page-enter space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight">Applications</h1>
          <p className="text-[hsl(var(--muted-foreground))] mt-1 text-sm">
            Track and manage your automated job applications.
          </p>
        </div>
        <Tabs value={view} onValueChange={(v) => setView(v as 'list' | 'kanban')} className="w-full sm:w-auto">
          <TabsList className="grid w-full sm:w-48 grid-cols-2 p-1 bg-[hsl(var(--color-surface-2))] border border-[hsl(var(--border))] rounded-xl">
            <TabsTrigger value="list" className="rounded-lg text-sm font-medium">List</TabsTrigger>
            <TabsTrigger value="kanban" disabled={!isPro} className="rounded-lg text-sm font-medium">
              Kanban {!isPro && <Lock className="ml-1.5 h-3 w-3 text-[hsl(var(--muted-foreground))]" />}
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3.5 top-3 h-4 w-4 text-[hsl(var(--muted-foreground))]" />
          <Input
            className="pl-10 h-10 w-full bg-[hsl(var(--color-surface))] border-[hsl(var(--border))] rounded-xl focus:ring-2 focus:ring-[hsl(var(--color-accent))]/30 transition-all font-medium"
            placeholder="Search applications by title or company..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="flex gap-3 sm:w-auto w-full">
          <Select value={platform} onValueChange={(v) => v && setPlatform(v)}>
            <SelectTrigger className="h-10 w-full sm:w-40 rounded-xl bg-[hsl(var(--color-surface))] border-[hsl(var(--border))] focus:ring-[hsl(var(--color-accent))]/30">
              <SelectValue placeholder="Platform" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Platforms</SelectItem>
              <SelectItem value="linkedin">LinkedIn</SelectItem>
              <SelectItem value="wellfound">Wellfound</SelectItem>
              <SelectItem value="internshala">Internshala</SelectItem>
              <SelectItem value="web_search">Web Search</SelectItem>
            </SelectContent>
          </Select>
          <Select value={status} onValueChange={(v) => v && setStatus(v)}>
            <SelectTrigger className="h-10 w-full sm:w-40 rounded-xl bg-[hsl(var(--color-surface))] border-[hsl(var(--border))] focus:ring-[hsl(var(--color-accent))]/30">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Statuses</SelectItem>
              {KANBAN_COLS.map((s) => (
                <SelectItem key={s} value={s} className="capitalize">
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* List view */}
      {view === 'list' && (
        <div className="space-y-3">
          {isLoading ? (
             <div className="grid gap-3 animate-pulse">
                {[1, 2, 3].map(i => (
                  <div key={i} className="h-20 rounded-xl bg-[hsl(var(--color-surface-2))] border border-[hsl(var(--border))] w-full"></div>
                ))}
             </div>
          ) : jobs.length === 0 ? (
            <div className="text-center py-16 rounded-2xl border border-dashed border-[hsl(var(--border))] bg-[hsl(var(--card))]">
              <div className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-[hsl(var(--color-surface-2))] mb-4">
                <Search className="h-6 w-6 text-[hsl(var(--muted-foreground))]" />
              </div>
              <p className="text-[hsl(var(--muted-foreground))] font-medium">No applications found.</p>
              <p className="text-sm text-[hsl(var(--muted-foreground))]/70 mt-1">Start a run from your Dashboard to see jobs here.</p>
            </div>
          ) : (
            <div className="grid gap-3">
              {(jobs as any[]).map((job, idx) => (
                <Link key={job.id} href={`/jobs/${job.id}`}>
                  <Card 
                    className="group border border-[hsl(var(--border))] bg-[hsl(var(--card))] hover:bg-[hsl(var(--color-surface))]/50 hover:border-[hsl(var(--color-accent))]/30 transition-all duration-300 rounded-xl overflow-hidden animate-fade-up"
                    style={{ animationDelay: `${Math.min(idx * 50, 400)}ms` }}
                  >
                    <CardContent className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <p className="font-display font-semibold text-base truncate group-hover:text-[hsl(var(--color-accent))] transition-colors">
                            {job.job_title}
                          </p>
                          {job.job_url && <ExternalLink className="h-3.5 w-3.5 text-[hsl(var(--muted-foreground))] opacity-0 group-hover:opacity-100 transition-opacity" />}
                        </div>
                        <p className="text-sm text-[hsl(var(--muted-foreground))] truncate">
                          <span className="font-medium text-[hsl(var(--foreground))]">{job.company}</span>
                          {job.location ? ` • ${job.location}` : ''}
                        </p>
                      </div>
                      
                      <div className="flex flex-wrap items-center gap-2 sm:gap-3 shrink-0">
                        <Badge variant="outline" className="px-2.5 py-1 bg-[hsl(var(--color-surface-2))] border-[hsl(var(--border))] text-xs font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]">
                          {job.platform}
                        </Badge>
                        <Badge 
                          className="px-2.5 py-1 text-xs font-semibold capitalize"
                          style={{
                             backgroundColor: STATUS_VARIANTS[job.status] === 'default' ? 'hsl(var(--color-accent))' : 
                                              STATUS_VARIANTS[job.status] === 'destructive' ? 'hsl(0, 84%, 60%)' :
                                              'hsl(var(--color-surface-2))',
                             color: STATUS_VARIANTS[job.status] === 'secondary' ? 'hsl(var(--foreground))' : '#fff'
                          }}
                        >
                          {job.status}
                        </Badge>
                        {job.match_score != null && (
                          <div className="flex items-center gap-1.5 bg-[hsl(var(--color-surface-2))] px-2.5 py-1 rounded-full border border-[hsl(var(--border))]">
                            <span className="relative flex h-2 w-2">
                              {job.match_score > 70 && <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[hsl(var(--color-success))] opacity-75"></span>}
                              <span className={`relative inline-flex rounded-full h-2 w-2 ${job.match_score > 70 ? 'bg-[hsl(var(--color-success))]' : 'bg-[hsl(var(--muted-foreground))]'}`}></span>
                            </span>
                            <span className="text-xs font-bold">{job.match_score}%</span>
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Kanban view (Pro) */}
      {view === 'kanban' && isPro && (
        <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <div className="flex gap-4 overflow-x-auto pb-6 h-[calc(100vh-240px)] hide-scrollbar snap-x">
            {KANBAN_COLS.map((col) => {
              const colJobs = (jobs as any[]).filter((j) => j.status === col)
              return (
                <div key={col} className="snap-start shrink-0">
                  <DroppableColumn id={col} title={col} count={colJobs.length}>
                    {colJobs.map((job) => (
                      <DraggableCard key={job.id} job={job} updateStatus={updateStatus} statusVariants={STATUS_VARIANTS} kanbanCols={KANBAN_COLS} />
                    ))}
                  </DroppableColumn>
                </div>
              )
            })}
          </div>
        </DndContext>
      )}
    </div>
  )

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event
    if (!over) return

    const jobId = active.id as string
    const newStatus = over.id as string

    const job = (jobs as any[]).find(j => j.id === jobId)
    if (job && job.status !== newStatus) {
      updateStatus.mutate({ id: jobId, status: newStatus })
    }
  }
}
