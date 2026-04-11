'use client'
import { useParams } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import api from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { Copy, Lock } from 'lucide-react'
import { useState } from 'react'

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { user } = useAuth()
  const [copied, setCopied] = useState(false)

  const { data: job, isLoading } = useQuery({
    queryKey: ['job', id],
    queryFn: () => api.get(`/jobs/${id}`).then((r) => r.data),
  })

  const { data: prep } = useQuery({
    queryKey: ['interview-prep', id],
    queryFn: () => api.get(`/jobs/${id}/interview-prep`).then((r) => r.data),
    enabled: !!job,
  })

  function copyLetter() {
    if (job?.cover_letter_used) {
      navigator.clipboard.writeText(job.cover_letter_used)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-4 max-w-3xl">
        <Skeleton className="h-32" />
        <Skeleton className="h-48" />
      </div>
    )
  }
  if (!job) return <p>Job not found.</p>

  const isPro = user?.plan !== 'free'
  const questions: any[] = prep?.questions || []
  const visibleQs = isPro ? questions : questions.slice(0, 3)

  return (
    <div className="max-w-3xl space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold">{job.job_title}</h1>
            <p className="text-slate-500">
              {job.company}
              {job.location ? ` · ${job.location}` : ''}
            </p>
          </div>
          <div className="flex gap-2 shrink-0">
            <Badge>{job.platform}</Badge>
            <Badge variant="outline">{job.status}</Badge>
          </div>
        </div>
        {job.job_url && (
          <a
            href={job.job_url}
            target="_blank"
            rel="noreferrer"
            className="text-sm text-blue-600 hover:underline"
          >
            View original posting →
          </a>
        )}
      </div>

      {/* Match score */}
      {job.match_score != null && (
        <Card>
          <CardHeader>
            <CardTitle>Match Score</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-start gap-4">
              <div className="text-5xl font-bold text-blue-600">{job.match_score}%</div>
              <div className="flex-1 space-y-2">
                {job.match_reason && (
                  <p className="text-sm text-slate-600">{job.match_reason}</p>
                )}
                {job.matched_skills?.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {job.matched_skills.map((s: string) => (
                      <Badge key={s} className="text-xs">
                        {s}
                      </Badge>
                    ))}
                  </div>
                )}
                {job.missing_skills?.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {job.missing_skills.map((s: string) => (
                      <Badge key={s} variant="destructive" className="text-xs">
                        {s}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Cover letter */}
      {job.cover_letter_used && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Cover Letter Used</CardTitle>
            <Button variant="outline" size="sm" onClick={copyLetter}>
              <Copy className="h-4 w-4 mr-1" />
              {copied ? 'Copied!' : 'Copy'}
            </Button>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-slate-700 whitespace-pre-wrap">
              {job.cover_letter_used}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Interview prep */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Interview Prep
            {!isPro && <Badge variant="secondary">3 / 10 free</Badge>}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {visibleQs.length === 0 && (
            <p className="text-sm text-slate-500">No questions generated yet.</p>
          )}
          {visibleQs.map((q: any, i: number) => (
            <div key={i} className="border rounded-lg p-3 space-y-1">
              <p className="font-medium text-sm">
                Q{i + 1}: {q.question}
              </p>
              <p className="text-sm text-slate-600">{q.answer}</p>
            </div>
          ))}
          {!isPro && questions.length > 3 && (
            <div className="border rounded-lg p-4 bg-amber-50 text-center space-y-2">
              <Lock className="h-5 w-5 text-amber-600 mx-auto" />
              <p className="text-sm font-medium text-amber-800">
                Upgrade to Pro for all {questions.length} questions
              </p>
              <Button
                size="sm"
                onClick={() => (window.location.href = '/settings/billing')}
              >
                Upgrade to Pro — ₹499/mo
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
      {/* Activity Track */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-bold uppercase tracking-wider text-slate-500 flex items-center gap-2">
            Activity Track
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-6">
            {(job.history || []).length === 0 ? (
              <p className="text-sm text-slate-400">No events tracked yet.</p>
            ) : (
              (job.history as any[]).map((event, i) => (
                <div key={i} className="relative pl-6 pb-6 last:pb-0">
                  {/* Timeline line */}
                  {i < job.history.length - 1 && (
                    <div className="absolute left-[7px] top-[14px] bottom-0 w-[2px] bg-slate-100" />
                  )}
                  {/* Dot */}
                  <div className={`absolute left-0 top-[6px] h-4 w-4 rounded-full border-2 border-white ring-2 ring-slate-100 ${
                    event.type === 'status_change' ? 'bg-blue-500' : 'bg-slate-400'
                  }`} />
                  
                  <div className="space-y-1">
                    <p className="text-xs font-semibold text-slate-400">
                      {new Date(event.timestamp).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}
                    </p>
                    <p className="text-sm font-medium text-slate-800">{event.message}</p>
                    {event.data?.reason && (
                      <p className="text-xs text-slate-500 italic">&quot;{event.data.reason}&quot;</p>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>

      {/* JD text */}
      {job.jd_text && (
        <Card>
          <CardHeader>
            <CardTitle>Job Description</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-slate-700 whitespace-pre-wrap">{job.jd_text}</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
