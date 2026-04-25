'use client'
/**
 * Floating "Report a bug" button + dialog, mounted globally in the app layout.
 *
 * What it does:
 *   1. Captures the current route (`window.location.pathname`) and user agent
 *      automatically so the user only has to type a title + description.
 *   2. POSTs to /bugs/report, which persists the report AND runs a Gemini
 *      self-learn pass that converts the bug into an agent rule and appends
 *      it to `agent_custom_instructions`. That field is injected into every
 *      future agent LLM prompt, so reporting a bug literally makes the
 *      agent smarter on the next run — the "self learn" loop the user asked for.
 *   3. Surfaces the generated rule back to the user in a success toast so
 *      they can see what the agent learned from their report.
 */
import { useState } from 'react'
import { usePathname } from 'next/navigation'
import { Bug, Send, X } from 'lucide-react'

import api from '@/lib/api'
import { useToast } from '@/lib/use-toast'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'

type Severity = 'low' | 'medium' | 'high'

export function BugReportButton() {
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [severity, setSeverity] = useState<Severity>('medium')
  const [submitting, setSubmitting] = useState(false)
  const pathname = usePathname()
  const { toast } = useToast()

  function reset() {
    setTitle('')
    setDescription('')
    setSeverity('medium')
  }

  async function submit() {
    if (title.trim().length < 3 || description.trim().length < 5) {
      toast({
        title: 'Missing details',
        description: 'Please add a short title and a description of what went wrong.',
        variant: 'error',
      })
      return
    }
    setSubmitting(true)
    try {
      // Call silently so the global axios interceptor won't show a generic
      // "Network Error" toast on top of our own handling.
      const { data } = await api.post(
        '/bugs/report',
        {
          title: title.trim(),
          description: description.trim(),
          page: pathname || (typeof window !== 'undefined' ? window.location.pathname : null),
          severity,
          user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : null,
        },
        { silent: true },
      )

      if (data?.advice) {
        toast({
          title: 'Bug logged — agent learned from it',
          description: `New rule added to agent instructions:\n${data.advice.slice(0, 240)}`,
        })
      } else {
        toast({
          title: 'Bug logged',
          description: 'Thanks — we saved your report.',
        })
      }
      reset()
      setOpen(false)
    } catch (err: any) {
      toast({
        title: 'Could not submit bug',
        description: err?.response?.data?.detail || 'Please try again in a moment.',
        variant: 'error',
      })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      {/* Floating trigger — bottom-right, visible on every page */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-40 flex items-center gap-2 rounded-full
                   bg-[hsl(var(--color-accent))] text-white px-4 py-2.5 shadow-lg
                   hover:bg-[hsl(var(--color-accent-hover))] hover:shadow-xl
                   transition-all duration-200 text-sm font-medium"
        title="Report a bug"
        aria-label="Report a bug"
      >
        <Bug className="h-4 w-4" />
        <span className="hidden sm:inline">Report bug</span>
      </button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-[520px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Bug className="h-5 w-5 text-[hsl(var(--color-accent))]" />
              Report a bug
            </DialogTitle>
            <DialogDescription>
              Tell us what went wrong. Our agent will analyze your report and
              automatically learn a rule to avoid repeating the mistake.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-2">
            <div className="grid gap-1.5">
              <Label htmlFor="bug-title">Title</Label>
              <Input
                id="bug-title"
                placeholder="e.g. Agent closed the job tab before I could review"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={200}
              />
            </div>

            <div className="grid gap-1.5">
              <Label htmlFor="bug-desc">What happened?</Label>
              <Textarea
                id="bug-desc"
                placeholder="Describe the bug. Steps to reproduce, what you expected, what you saw..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={6}
                maxLength={4000}
              />
            </div>

            <div className="grid gap-1.5">
              <Label htmlFor="bug-severity">Severity</Label>
              <select
                id="bug-severity"
                value={severity}
                onChange={(e) => setSeverity(e.target.value as Severity)}
                className="h-10 rounded-md border border-input bg-background px-3 text-sm
                           focus:outline-none focus:ring-2 focus:ring-[hsl(var(--color-accent))]"
              >
                <option value="low">Low — minor annoyance</option>
                <option value="medium">Medium — noticeable problem</option>
                <option value="high">High — blocks me from applying</option>
              </select>
            </div>

            <p className="text-xs text-muted-foreground">
              We automatically include the current page
              (<code className="px-1 py-0.5 rounded bg-muted">{pathname}</code>) and your browser info.
            </p>
          </div>

          <DialogFooter className="gap-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setOpen(false)}
              disabled={submitting}
            >
              <X className="h-4 w-4 mr-1" />
              Cancel
            </Button>
            <Button type="button" onClick={submit} disabled={submitting}>
              <Send className="h-4 w-4 mr-1" />
              {submitting ? 'Submitting…' : 'Submit & learn'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
