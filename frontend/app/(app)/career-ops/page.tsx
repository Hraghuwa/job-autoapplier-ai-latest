'use client'
import { useEffect, useState } from 'react'
import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import {
  Sparkles, Target, BookOpen, Handshake, Radar, Loader2, CheckCircle2,
  AlertTriangle, ChevronRight,
} from 'lucide-react'

type Tab = 'evaluate' | 'tailor' | 'scan' | 'stories' | 'negotiate'

const TABS: { id: Tab; label: string; icon: any }[] = [
  { id: 'evaluate', label: 'Evaluate Offer', icon: Target },
  { id: 'tailor', label: 'Tailor CV', icon: Sparkles },
  { id: 'scan', label: 'Portal Scan', icon: Radar },
  { id: 'stories', label: 'Story Bank', icon: BookOpen },
  { id: 'negotiate', label: 'Negotiation', icon: Handshake },
]

export default function CareerOpsPage() {
  const [tab, setTab] = useState<Tab>('evaluate')
  return (
    <div className="p-6 lg:p-10 max-w-6xl mx-auto">
      <header className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">Career-Ops</h1>
        <p className="text-sm text-muted-foreground mt-1">
          AI filter + tailoring layer. Evaluate offers with A–G scoring, tailor your CV per JD,
          scan portals, and build an interview story bank.
        </p>
      </header>

      <div className="flex flex-wrap gap-2 mb-6 border-b border-border pb-3">
        {TABS.map((t) => {
          const Icon = t.icon
          const active = tab === t.id
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition ${
                active ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'
              }`}
            >
              <Icon className="w-4 h-4" />
              {t.label}
            </button>
          )
        })}
      </div>

      {tab === 'evaluate' && <EvaluatePanel />}
      {tab === 'tailor' && <TailorPanel />}
      {tab === 'scan' && <ScanPanel />}
      {tab === 'stories' && <StoryBankPanel />}
      {tab === 'negotiate' && <NegotiatePanel />}
    </div>
  )
}

// ── Evaluate ─────────────────────────────────────────────────────────────────
function EvaluatePanel() {
  const [jd, setJd] = useState('')
  const [company, setCompany] = useState('')
  const [role, setRole] = useState('')
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [err, setErr] = useState('')

  const run = async () => {
    setLoading(true); setErr(''); setResult(null)
    try {
      const { data } = await api.post('/career-ops/evaluate', {
        jd_text: jd, company, role, url,
      })
      setResult(data.evaluation)
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e.message)
    } finally { setLoading(false) }
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <input className="rounded border border-border bg-background px-3 py-2 text-sm"
          placeholder="Company (optional)" value={company} onChange={(e) => setCompany(e.target.value)} />
        <input className="rounded border border-border bg-background px-3 py-2 text-sm"
          placeholder="Role (optional)" value={role} onChange={(e) => setRole(e.target.value)} />
        <input className="rounded border border-border bg-background px-3 py-2 text-sm"
          placeholder="URL (optional)" value={url} onChange={(e) => setUrl(e.target.value)} />
      </div>
      <textarea className="w-full min-h-64 rounded border border-border bg-background px-3 py-2 text-sm font-mono"
        placeholder="Paste full job description here…" value={jd} onChange={(e) => setJd(e.target.value)} />
      <Button onClick={run} disabled={loading || jd.length < 40}>
        {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Target className="w-4 h-4 mr-2" />}
        Evaluate (A–G)
      </Button>
      {err && <p className="text-sm text-red-500">{err}</p>}
      {result && <EvaluationResult data={result} />}
    </div>
  )
}

function EvaluationResult({ data }: { data: any }) {
  const b = data.blocks || {}
  return (
    <div className="border border-border rounded-xl p-5 space-y-5 bg-card">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <p className="text-xs uppercase text-muted-foreground">Overall</p>
          <p className="text-3xl font-bold">{data.overall_score}/5</p>
          <p className="text-sm mt-1">{data.tldr}</p>
        </div>
        <div className="text-right">
          <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium ${
            data.recommendation === 'apply' ? 'bg-green-500/15 text-green-600' :
            data.recommendation === 'skip' ? 'bg-red-500/15 text-red-600' :
            'bg-amber-500/15 text-amber-600'
          }`}>
            {data.recommendation === 'apply' ? <CheckCircle2 className="w-3.5 h-3.5" /> : <AlertTriangle className="w-3.5 h-3.5" />}
            {data.recommendation}
          </span>
          <p className="text-xs text-muted-foreground mt-2">Archetype: {data.archetype}</p>
        </div>
      </div>

      <Block title="A · Role Summary" obj={b.A_role_summary} />
      <Block title={`B · CV Match (${b.B_cv_match?.score ?? 0}/5)`} obj={b.B_cv_match} />
      <Block title="C · Level & Strategy" obj={b.C_level_strategy} />
      <Block title="D · Comp & Demand" obj={b.D_comp_demand} />
      <Block title="E · Personalization" obj={b.E_personalization} />
      <Block title="F · Interview Prep" obj={b.F_interview_prep} />
      <Block title={`G · Legitimacy (${b.G_legitimacy?.tier ?? '?'})`} obj={b.G_legitimacy} />
    </div>
  )
}

function Block({ title, obj }: { title: string; obj: any }) {
  const [open, setOpen] = useState(true)
  if (!obj) return null
  return (
    <div className="border border-border rounded-lg">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center justify-between px-4 py-3 text-left text-sm font-semibold hover:bg-muted/50">
        {title}
        <ChevronRight className={`w-4 h-4 transition-transform ${open ? 'rotate-90' : ''}`} />
      </button>
      {open && (
        <pre className="px-4 pb-4 text-xs text-muted-foreground whitespace-pre-wrap font-mono">
          {JSON.stringify(obj, null, 2)}
        </pre>
      )}
    </div>
  )
}

// ── Tailor CV ────────────────────────────────────────────────────────────────
function TailorPanel() {
  const [jd, setJd] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [err, setErr] = useState('')
  const run = async () => {
    setLoading(true); setErr(''); setResult(null)
    try {
      const { data } = await api.post('/career-ops/tailor-cv', { jd_text: jd })
      setResult(data)
    } catch (e: any) { setErr(e?.response?.data?.detail || e.message) }
    finally { setLoading(false) }
  }
  return (
    <div className="space-y-4">
      <textarea className="w-full min-h-64 rounded border border-border bg-background px-3 py-2 text-sm font-mono"
        placeholder="Paste JD…" value={jd} onChange={(e) => setJd(e.target.value)} />
      <Button onClick={run} disabled={loading || jd.length < 40}>
        {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Sparkles className="w-4 h-4 mr-2" />}
        Tailor my CV
      </Button>
      {err && <p className="text-sm text-red-500">{err}</p>}
      {result && (
        <div className="border border-border rounded-xl p-5 space-y-4 bg-card">
          <section>
            <h3 className="font-semibold text-sm mb-2">Tailored Summary</h3>
            <p className="text-sm text-muted-foreground">{result.tailored_summary}</p>
          </section>
          <section>
            <h3 className="font-semibold text-sm mb-2">Keywords to Inject</h3>
            <div className="flex flex-wrap gap-1.5">
              {(result.keywords_to_inject || []).map((k: string, i: number) => (
                <span key={i} className="px-2 py-0.5 rounded bg-primary/10 text-primary text-xs">{k}</span>
              ))}
            </div>
          </section>
          <section>
            <h3 className="font-semibold text-sm mb-2">Bullet Rewrites</h3>
            <ul className="space-y-2 text-sm">
              {(result.bullet_rewrites || []).map((b: any, i: number) => (
                <li key={i} className="border-l-2 border-primary pl-3">
                  <p className="text-muted-foreground text-xs">{b.original_hint}</p>
                  <p>{b.rewrite}</p>
                </li>
              ))}
            </ul>
          </section>
          <section>
            <h3 className="font-semibold text-sm mb-2">ATS Tips</h3>
            <ul className="list-disc list-inside text-sm text-muted-foreground">
              {(result.ats_tips || []).map((t: string, i: number) => <li key={i}>{t}</li>)}
            </ul>
          </section>
        </div>
      )}
    </div>
  )
}

// ── Scan ─────────────────────────────────────────────────────────────────────
function ScanPanel() {
  const [query, setQuery] = useState('')
  const [companies, setCompanies] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [err, setErr] = useState('')
  const run = async () => {
    setLoading(true); setErr(''); setResult(null)
    try {
      const { data } = await api.post('/career-ops/scan', {
        query, companies: companies.split(',').map(s => s.trim()).filter(Boolean),
      })
      setResult(data)
    } catch (e: any) { setErr(e?.response?.data?.detail || e.message) }
    finally { setLoading(false) }
  }
  return (
    <div className="space-y-4">
      <input className="w-full rounded border border-border bg-background px-3 py-2 text-sm"
        placeholder="Query e.g. 'applied AI, agentic, llm-ops'" value={query} onChange={e => setQuery(e.target.value)} />
      <input className="w-full rounded border border-border bg-background px-3 py-2 text-sm"
        placeholder="Companies (comma-separated, optional)" value={companies} onChange={e => setCompanies(e.target.value)} />
      <Button onClick={run} disabled={loading || !query}>
        {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Radar className="w-4 h-4 mr-2" />}
        Suggest targets
      </Button>
      {err && <p className="text-sm text-red-500">{err}</p>}
      {result?.suggestions && (
        <div className="grid md:grid-cols-2 gap-3">
          {result.suggestions.map((s: any, i: number) => (
            <div key={i} className="border border-border rounded-lg p-4 bg-card">
              <h3 className="font-semibold">{s.company}</h3>
              <p className="text-xs text-muted-foreground mt-1">{s.why}</p>
              <div className="mt-2 space-y-1">
                {(s.portals || []).map((url: string, j: number) => (
                  <a key={j} href={url} target="_blank" rel="noreferrer" className="block text-xs text-primary hover:underline truncate">
                    {url}
                  </a>
                ))}
              </div>
              {s.example_query && <p className="text-xs mt-2 font-mono text-muted-foreground">“{s.example_query}”</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Story Bank ───────────────────────────────────────────────────────────────
function StoryBankPanel() {
  const [stories, setStories] = useState<any[]>([])
  const [form, setForm] = useState({ title: '', situation: '', task: '', action: '', result: '', reflection: '' })
  const [loading, setLoading] = useState(false)

  const load = async () => {
    const { data } = await api.get('/career-ops/story-bank')
    setStories(data)
  }
  useEffect(() => { load() }, [])

  const add = async () => {
    setLoading(true)
    try {
      await api.post('/career-ops/story-bank', { ...form, tags: [] })
      setForm({ title: '', situation: '', task: '', action: '', result: '', reflection: '' })
      await load()
    } finally { setLoading(false) }
  }
  const del = async (id: string) => {
    await api.delete(`/career-ops/story-bank/${id}`)
    await load()
  }

  return (
    <div className="grid md:grid-cols-2 gap-6">
      <div className="space-y-2">
        <h3 className="font-semibold">Add story (STAR + R)</h3>
        {(['title', 'situation', 'task', 'action', 'result', 'reflection'] as const).map((f) => (
          <textarea key={f} className="w-full rounded border border-border bg-background px-3 py-2 text-sm"
            rows={f === 'title' ? 1 : 2}
            placeholder={f[0].toUpperCase() + f.slice(1)}
            value={(form as any)[f]}
            onChange={(e) => setForm({ ...form, [f]: e.target.value })} />
        ))}
        <Button onClick={add} disabled={loading || !form.title}>Save</Button>
      </div>
      <div className="space-y-3">
        <h3 className="font-semibold">Bank ({stories.length})</h3>
        {stories.map((s: any) => (
          <div key={s.id} className="border border-border rounded-lg p-3 bg-card">
            <div className="flex justify-between items-start gap-2">
              <h4 className="font-medium text-sm">{s.title}</h4>
              <button onClick={() => del(s.id)} className="text-xs text-red-500 hover:underline">delete</button>
            </div>
            <p className="text-xs text-muted-foreground mt-1 line-clamp-3">{s.situation}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Negotiation ──────────────────────────────────────────────────────────────
function NegotiatePanel() {
  const [form, setForm] = useState({
    company: '', role: '', current_offer: '', target: '', competing_offers: '', geo_context: '',
  })
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [err, setErr] = useState('')
  const run = async () => {
    setLoading(true); setErr(''); setResult(null)
    try {
      const { data } = await api.post('/career-ops/negotiation', form)
      setResult(data)
    } catch (e: any) { setErr(e?.response?.data?.detail || e.message) }
    finally { setLoading(false) }
  }
  return (
    <div className="space-y-3">
      <div className="grid md:grid-cols-2 gap-3">
        {(['company', 'role', 'current_offer', 'target', 'competing_offers', 'geo_context'] as const).map((f) => (
          <input key={f} className="rounded border border-border bg-background px-3 py-2 text-sm"
            placeholder={f.replace('_', ' ')}
            value={(form as any)[f]}
            onChange={(e) => setForm({ ...form, [f]: e.target.value })} />
        ))}
      </div>
      <Button onClick={run} disabled={loading || !form.company}>
        {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Handshake className="w-4 h-4 mr-2" />}
        Generate scripts
      </Button>
      {err && <p className="text-sm text-red-500">{err}</p>}
      {result && (
        <div className="space-y-3">
          {(result.scripts || []).map((s: any, i: number) => (
            <div key={i} className="border border-border rounded-lg p-4 bg-card">
              <h3 className="font-semibold text-sm">{s.title}</h3>
              <p className="mt-2 text-sm whitespace-pre-wrap">{s.script}</p>
              <p className="text-xs text-muted-foreground mt-2 italic">Why: {s.why}</p>
            </div>
          ))}
          {result.walk_away_line && (
            <div className="border border-amber-500/50 bg-amber-500/5 rounded-lg p-4">
              <p className="text-xs uppercase text-amber-600 font-semibold">Walk-away line</p>
              <p className="text-sm mt-1">{result.walk_away_line}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
