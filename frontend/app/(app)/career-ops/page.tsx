'use client'
import { useEffect, useState } from 'react'
import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import {
  Sparkles, Target, BookOpen, Handshake, Radar, Loader2, CheckCircle2,
  AlertTriangle, ChevronRight, GitCompare, Lightbulb, GraduationCap,
  Search, BarChart3, Mail, Users, Info,
} from 'lucide-react'

type Tab =
  | 'evaluate' | 'compare' | 'tailor' | 'scan'
  | 'stories' | 'negotiate' | 'project' | 'training'
  | 'deep' | 'patterns' | 'followup' | 'contact'

const TABS: { id: Tab; label: string; icon: any; tagline: string }[] = [
  { id: 'evaluate',  label: 'Evaluate Offer',  icon: Target,        tagline: 'A–G scoring of a single JD' },
  { id: 'compare',   label: 'Compare Offers',  icon: GitCompare,    tagline: '10-dim weighted matrix across multiple offers' },
  { id: 'tailor',    label: 'Tailor CV',       icon: Sparkles,      tagline: 'Surgical CV rewrites per JD' },
  { id: 'scan',      label: 'Portal Scan',     icon: Radar,         tagline: 'Find target companies + portal URLs' },
  { id: 'stories',   label: 'Story Bank',      icon: BookOpen,      tagline: 'STAR + Reflection interview stories' },
  { id: 'negotiate', label: 'Negotiation',     icon: Handshake,     tagline: 'Counter / geo / leverage scripts' },
  { id: 'project',   label: 'Project Eval',    icon: Lightbulb,     tagline: '6-dim portfolio project scoring' },
  { id: 'training',  label: 'Training Eval',   icon: GraduationCap, tagline: 'DO / TIMEBOX / DON\'T verdict for courses' },
  { id: 'deep',      label: 'Deep Research',   icon: Search,        tagline: 'Perplexity-ready research prompt' },
  { id: 'patterns',  label: 'Patterns',        icon: BarChart3,     tagline: 'Rejection-pattern detector across applications' },
  { id: 'followup',  label: 'Follow-up',       icon: Mail,          tagline: 'Cadence + tailored draft generator' },
  { id: 'contact',   label: 'Outreach',        icon: Users,         tagline: 'LinkedIn 3-sentence opener' },
]

const DESCRIPTIONS: Record<Tab, { title: string; what: string; how: string; out: string }> = {
  evaluate:  { title: 'Evaluate Offer (A–G)',
    what: 'Reads a job description and grades it across 7 blocks: Role summary (A), CV match (B), Level strategy (C), Comp & demand (D), Personalization (E), Interview prep (F), Legitimacy (G).',
    how: 'Paste the JD (and optionally company/role/URL). The AI uses your saved CV for the match score.',
    out: 'A 0–5 overall score, an apply / tailor-first / skip recommendation, and STAR stories auto-saved to your Story Bank.' },
  compare:   { title: 'Compare Offers',
    what: 'Multi-offer ranking across 10 weighted dimensions — North-Star alignment, CV match, level, comp, growth, remote quality, reputation, tech, speed-to-offer, culture.',
    how: 'Add 2 or more offers (company + role + JD text). Optionally include comp/remote hints.',
    out: 'A ranked table with weighted totals + a PURSUE / HOLD / DROP verdict per offer and a time-to-offer recommendation.' },
  tailor:    { title: 'Tailor CV',
    what: 'Surgical, non-fabricating rewrites of your CV for one specific JD. No invented experience.',
    how: 'Paste the JD. The AI reads your stored profile and proposes a new summary, keywords to inject, bullet rewrites, and section reorder.',
    out: 'Tailored summary, keyword chips, XYZ-formula bullet rewrites, and ATS tips.' },
  scan:      { title: 'Portal Scan',
    what: 'Suggests well-known target companies and concrete career-portal URLs (Ashby/Greenhouse/Lever) for a given archetype.',
    how: 'Type an archetype query like "applied AI, agentic, llm-ops" and optionally seed companies.',
    out: '10 prioritised companies with portal links and an example query string for each.' },
  stories:   { title: 'Story Bank (STAR + R)',
    what: 'Reusable interview stories using the STAR + Reflection framework. Auto-populated when you run an evaluation.',
    how: 'Add stories manually, or let evaluations seed the bank automatically.',
    out: 'Searchable story library you can mine before any interview.' },
  negotiate: { title: 'Negotiation Scripts',
    what: 'Generates three concrete scripts: counter the current offer, push back on a geographic discount, leverage a competing offer.',
    how: 'Fill in the offer details — current, target, competing, geo context.',
    out: 'Three ready-to-send scripts, plus a walk-away line and concrete number anchors.' },
  project:   { title: 'Portfolio Project Eval',
    what: 'Scores a portfolio idea on 6 dimensions: signal-for-role, uniqueness, demoability, metrics potential, time-to-MVP, STAR potential.',
    how: 'Describe the project idea and (optionally) the target role you\'re aiming at.',
    out: 'BUILD / SKIP / PIVOT verdict, weekly milestones, and a 2-week interview pack plan.' },
  training:  { title: 'Training / Cert Eval',
    what: 'Evaluates a course or certification on North-Star alignment, recruiter signal, time/effort, opportunity cost, risks, portfolio deliverable.',
    how: 'Enter the course or cert name, target role, and weeks available.',
    out: 'DO / DO_TIMEBOXED / DON\'T verdict with a weekly plan or a better alternative.' },
  deep:      { title: 'Deep Research Prompt',
    what: 'Builds a personalised Perplexity / Claude / ChatGPT research brief covering AI strategy, recent moves, eng culture, challenges, competitors, and your candidate angle.',
    how: 'Enter company + role and optionally paste the JD.',
    out: 'A copy-paste-ready research prompt plus a list of suggested sources.' },
  patterns:  { title: 'Rejection Pattern Detector',
    what: 'Surfaces actionable patterns from your tracked applications — what\'s converting, what\'s wasting time, recommended score floor.',
    how: 'Paste a JSON list of at least 5 applications with status + score + blockers. (Auto-loaded from your tracker in v2.)',
    out: 'Funnel, archetype performance, top blockers, tech-stack gaps, score threshold, and ranked recommendations.' },
  followup:  { title: 'Follow-up Cadence',
    what: 'Generates a follow-up draft tuned to the cadence stage (applied = 7d, responded = 3d, interview = 1d).',
    how: 'Enter company, role, current status, days since last action, and optionally the last message they sent.',
    out: 'Urgency tag, email + LinkedIn drafts, suggested next-followup date, and close-loop advice.' },
  contact:   { title: 'LinkedIn Outreach',
    what: 'Three-sentence opener for cold outreach. Different framing for recruiter / hiring manager / peer / interviewer.',
    how: 'Enter the company, role, contact type, and optionally a specific signal about them (a talk, blog post, hire).',
    out: 'A ≤300-char primary message, two alternates, and the rationale for the framing.' },
}

export default function CareerOpsPage() {
  const [tab, setTab] = useState<Tab>('evaluate')
  const desc = DESCRIPTIONS[tab]
  return (
    <div className="p-6 lg:p-10 max-w-6xl mx-auto">
      <header className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">Career-Ops</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Full AI filter + tailoring + outreach layer ported from the career-ops CLI.
          12 modes covering every stage from offer-discovery to follow-up.
        </p>
      </header>

      <div className="flex flex-wrap gap-2 mb-4 border-b border-border pb-3">
        {TABS.map((t) => {
          const Icon = t.icon
          const active = tab === t.id
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              title={t.tagline}
              className={`inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition ${
                active ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'
              }`}
            >
              <Icon className="w-4 h-4" />
              {t.label}
            </button>
          )
        })}
      </div>

      {/* Per-tab description card */}
      <div className="mb-6 rounded-lg border border-border bg-card/50 p-4">
        <div className="flex items-start gap-3">
          <Info className="w-5 h-5 mt-0.5 text-primary shrink-0" />
          <div className="text-sm space-y-1.5">
            <p className="font-semibold">{desc.title}</p>
            <p className="text-muted-foreground"><span className="font-medium text-foreground">What it does:</span> {desc.what}</p>
            <p className="text-muted-foreground"><span className="font-medium text-foreground">How to use:</span> {desc.how}</p>
            <p className="text-muted-foreground"><span className="font-medium text-foreground">Output:</span> {desc.out}</p>
          </div>
        </div>
      </div>

      {tab === 'evaluate'  && <EvaluatePanel />}
      {tab === 'compare'   && <ComparePanel />}
      {tab === 'tailor'    && <TailorPanel />}
      {tab === 'scan'      && <ScanPanel />}
      {tab === 'stories'   && <StoryBankPanel />}
      {tab === 'negotiate' && <NegotiatePanel />}
      {tab === 'project'   && <ProjectPanel />}
      {tab === 'training'  && <TrainingPanel />}
      {tab === 'deep'      && <DeepPanel />}
      {tab === 'patterns'  && <PatternsPanel />}
      {tab === 'followup'  && <FollowupPanel />}
      {tab === 'contact'   && <ContactPanel />}
    </div>
  )
}

// ── Generic helpers ──────────────────────────────────────────────────────────
function Err({ msg }: { msg: string }) {
  if (!msg) return null
  return <p className="text-sm text-red-500 break-words">{msg}</p>
}
function JsonView({ data }: { data: any }) {
  return (
    <pre className="px-4 pb-4 text-xs text-muted-foreground whitespace-pre-wrap font-mono border border-border rounded-lg p-4 bg-card">
      {JSON.stringify(data, null, 2)}
    </pre>
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
      const { data } = await api.post('/career-ops/evaluate', { jd_text: jd, company, role, url })
      setResult(data.evaluation)
    } catch (e: any) { setErr(e?.response?.data?.detail || e.message) }
    finally { setLoading(false) }
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <input className="rounded border border-border bg-background px-3 py-2 text-sm" placeholder="Company (optional)" value={company} onChange={(e) => setCompany(e.target.value)} />
        <input className="rounded border border-border bg-background px-3 py-2 text-sm" placeholder="Role (optional)" value={role} onChange={(e) => setRole(e.target.value)} />
        <input className="rounded border border-border bg-background px-3 py-2 text-sm" placeholder="URL (optional)" value={url} onChange={(e) => setUrl(e.target.value)} />
      </div>
      <textarea className="w-full min-h-64 rounded border border-border bg-background px-3 py-2 text-sm font-mono" placeholder="Paste full job description here…" value={jd} onChange={(e) => setJd(e.target.value)} />
      <Button onClick={run} disabled={loading || jd.length < 40}>
        {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Target className="w-4 h-4 mr-2" />}
        Evaluate (A–G)
      </Button>
      <Err msg={err} />
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
      {open && <pre className="px-4 pb-4 text-xs text-muted-foreground whitespace-pre-wrap font-mono">{JSON.stringify(obj, null, 2)}</pre>}
    </div>
  )
}

// ── Compare Offers ───────────────────────────────────────────────────────────
function ComparePanel() {
  const [offers, setOffers] = useState<any[]>([
    { company: '', role: '', jd_text: '', comp: '', remote: '' },
    { company: '', role: '', jd_text: '', comp: '', remote: '' },
  ])
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [err, setErr] = useState('')

  const update = (i: number, k: string, v: string) => {
    const next = [...offers]; next[i] = { ...next[i], [k]: v }; setOffers(next)
  }
  const addOffer = () => setOffers([...offers, { company: '', role: '', jd_text: '', comp: '', remote: '' }])
  const removeOffer = (i: number) => setOffers(offers.filter((_, idx) => idx !== i))

  const run = async () => {
    setLoading(true); setErr(''); setResult(null)
    try {
      const { data } = await api.post('/career-ops/compare', { offers })
      setResult(data)
    } catch (e: any) { setErr(e?.response?.data?.detail || e.message) }
    finally { setLoading(false) }
  }

  const ready = offers.every((o) => o.company && o.role && o.jd_text.length > 30)
  return (
    <div className="space-y-4">
      {offers.map((o, i) => (
        <div key={i} className="border border-border rounded-lg p-4 space-y-2 bg-card">
          <div className="flex justify-between">
            <h3 className="font-semibold text-sm">Offer #{i + 1}</h3>
            {offers.length > 2 && <button onClick={() => removeOffer(i)} className="text-xs text-red-500">remove</button>}
          </div>
          <div className="grid md:grid-cols-2 gap-2">
            <input className="rounded border border-border bg-background px-3 py-2 text-sm" placeholder="Company" value={o.company} onChange={(e) => update(i, 'company', e.target.value)} />
            <input className="rounded border border-border bg-background px-3 py-2 text-sm" placeholder="Role" value={o.role} onChange={(e) => update(i, 'role', e.target.value)} />
            <input className="rounded border border-border bg-background px-3 py-2 text-sm" placeholder="Comp (optional)" value={o.comp} onChange={(e) => update(i, 'comp', e.target.value)} />
            <input className="rounded border border-border bg-background px-3 py-2 text-sm" placeholder="Remote policy (optional)" value={o.remote} onChange={(e) => update(i, 'remote', e.target.value)} />
          </div>
          <textarea className="w-full min-h-24 rounded border border-border bg-background px-3 py-2 text-sm font-mono" placeholder="JD text" value={o.jd_text} onChange={(e) => update(i, 'jd_text', e.target.value)} />
        </div>
      ))}
      <div className="flex gap-2">
        <Button variant="outline" onClick={addOffer}>+ Add another offer</Button>
        <Button onClick={run} disabled={loading || !ready}>
          {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <GitCompare className="w-4 h-4 mr-2" />}
          Rank offers
        </Button>
      </div>
      <Err msg={err} />
      {result && (
        <div className="space-y-3">
          {(result.ranking || []).map((r: any, i: number) => (
            <div key={i} className="border border-border rounded-lg p-4 bg-card">
              <div className="flex justify-between items-start gap-2">
                <div>
                  <p className="text-xs text-muted-foreground">Rank #{r.rank} · {r.verdict}</p>
                  <h3 className="font-semibold">{r.company} — {r.role}</h3>
                </div>
                <p className="text-2xl font-bold">{r.weighted_total?.toFixed?.(1) ?? r.weighted_total}</p>
              </div>
              <p className="text-sm mt-2 text-muted-foreground">{r.rationale}</p>
            </div>
          ))}
          {result.recommendation && (
            <div className="border-l-4 border-primary bg-primary/5 p-4 rounded text-sm">{result.recommendation}</div>
          )}
        </div>
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
      <textarea className="w-full min-h-64 rounded border border-border bg-background px-3 py-2 text-sm font-mono" placeholder="Paste JD…" value={jd} onChange={(e) => setJd(e.target.value)} />
      <Button onClick={run} disabled={loading || jd.length < 40}>
        {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Sparkles className="w-4 h-4 mr-2" />}
        Tailor my CV
      </Button>
      <Err msg={err} />
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
      <input className="w-full rounded border border-border bg-background px-3 py-2 text-sm" placeholder="Query e.g. 'applied AI, agentic, llm-ops'" value={query} onChange={e => setQuery(e.target.value)} />
      <input className="w-full rounded border border-border bg-background px-3 py-2 text-sm" placeholder="Companies (comma-separated, optional)" value={companies} onChange={e => setCompanies(e.target.value)} />
      <Button onClick={run} disabled={loading || !query}>
        {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Radar className="w-4 h-4 mr-2" />}
        Suggest targets
      </Button>
      <Err msg={err} />
      {result?.suggestions && (
        <div className="grid md:grid-cols-2 gap-3">
          {result.suggestions.map((s: any, i: number) => (
            <div key={i} className="border border-border rounded-lg p-4 bg-card">
              <h3 className="font-semibold">{s.company}</h3>
              <p className="text-xs text-muted-foreground mt-1">{s.why}</p>
              <div className="mt-2 space-y-1">
                {(s.portals || []).map((url: string, j: number) => (
                  <a key={j} href={url} target="_blank" rel="noreferrer" className="block text-xs text-primary hover:underline truncate">{url}</a>
                ))}
              </div>
              {s.example_query && <p className="text-xs mt-2 font-mono text-muted-foreground">"{s.example_query}"</p>}
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
          <textarea key={f} className="w-full rounded border border-border bg-background px-3 py-2 text-sm" rows={f === 'title' ? 1 : 2} placeholder={f[0].toUpperCase() + f.slice(1)} value={(form as any)[f]} onChange={(e) => setForm({ ...form, [f]: e.target.value })} />
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
  const [form, setForm] = useState({ company: '', role: '', current_offer: '', target: '', competing_offers: '', geo_context: '' })
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
          <input key={f} className="rounded border border-border bg-background px-3 py-2 text-sm" placeholder={f.replace('_', ' ')} value={(form as any)[f]} onChange={(e) => setForm({ ...form, [f]: e.target.value })} />
        ))}
      </div>
      <Button onClick={run} disabled={loading || !form.company}>
        {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Handshake className="w-4 h-4 mr-2" />}
        Generate scripts
      </Button>
      <Err msg={err} />
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

// ── Project Eval ─────────────────────────────────────────────────────────────
function ProjectPanel() {
  const [idea, setIdea] = useState('')
  const [role, setRole] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [err, setErr] = useState('')
  const run = async () => {
    setLoading(true); setErr(''); setResult(null)
    try {
      const { data } = await api.post('/career-ops/project-eval', { project_idea: idea, target_role: role })
      setResult(data)
    } catch (e: any) { setErr(e?.response?.data?.detail || e.message) }
    finally { setLoading(false) }
  }
  return (
    <div className="space-y-3">
      <input className="w-full rounded border border-border bg-background px-3 py-2 text-sm" placeholder="Target role (optional)" value={role} onChange={e => setRole(e.target.value)} />
      <textarea className="w-full min-h-40 rounded border border-border bg-background px-3 py-2 text-sm font-mono" placeholder="Describe the project idea…" value={idea} onChange={e => setIdea(e.target.value)} />
      <Button onClick={run} disabled={loading || idea.length < 20}>
        {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Lightbulb className="w-4 h-4 mr-2" />}
        Evaluate project
      </Button>
      <Err msg={err} />
      {result && (
        <div className="border border-border rounded-xl p-5 space-y-3 bg-card">
          <div className="flex items-center justify-between">
            <span className={`px-3 py-1 rounded-full text-xs font-semibold ${
              result.verdict === 'BUILD' ? 'bg-green-500/15 text-green-600' :
              result.verdict === 'SKIP' ? 'bg-red-500/15 text-red-600' :
              'bg-amber-500/15 text-amber-600'
            }`}>{result.verdict}</span>
            <p className="text-2xl font-bold">{result.weighted_total}/5</p>
          </div>
          {result.pivot_to && <p className="text-sm"><strong>Pivot to:</strong> {result.pivot_to}</p>}
          {result.milestones && (
            <div className="text-sm">
              <p><strong>Week 1:</strong> {result.milestones.week_1}</p>
              <p><strong>Week 2:</strong> {result.milestones.week_2}</p>
            </div>
          )}
          <JsonView data={result} />
        </div>
      )}
    </div>
  )
}

// ── Training Eval ────────────────────────────────────────────────────────────
function TrainingPanel() {
  const [item, setItem] = useState('')
  const [role, setRole] = useState('')
  const [weeks, setWeeks] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [err, setErr] = useState('')
  const run = async () => {
    setLoading(true); setErr(''); setResult(null)
    try {
      const { data } = await api.post('/career-ops/training-eval', {
        course_or_cert: item, target_role: role,
        weeks_available: weeks ? parseInt(weeks) : undefined,
      })
      setResult(data)
    } catch (e: any) { setErr(e?.response?.data?.detail || e.message) }
    finally { setLoading(false) }
  }
  return (
    <div className="space-y-3">
      <input className="w-full rounded border border-border bg-background px-3 py-2 text-sm" placeholder="Course or certification name" value={item} onChange={e => setItem(e.target.value)} />
      <div className="grid md:grid-cols-2 gap-3">
        <input className="rounded border border-border bg-background px-3 py-2 text-sm" placeholder="Target role (optional)" value={role} onChange={e => setRole(e.target.value)} />
        <input className="rounded border border-border bg-background px-3 py-2 text-sm" type="number" placeholder="Weeks available (optional)" value={weeks} onChange={e => setWeeks(e.target.value)} />
      </div>
      <Button onClick={run} disabled={loading || !item}>
        {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <GraduationCap className="w-4 h-4 mr-2" />}
        Evaluate
      </Button>
      <Err msg={err} />
      {result && (
        <div className="border border-border rounded-xl p-5 space-y-3 bg-card">
          <span className={`px-3 py-1 rounded-full text-xs font-semibold inline-block ${
            result.verdict === 'DO' ? 'bg-green-500/15 text-green-600' :
            result.verdict === 'DONT' ? 'bg-red-500/15 text-red-600' :
            'bg-amber-500/15 text-amber-600'
          }`}>{result.verdict}{result.max_weeks ? ` (max ${result.max_weeks}w)` : ''}</span>
          <JsonView data={result} />
        </div>
      )}
    </div>
  )
}

// ── Deep Research ────────────────────────────────────────────────────────────
function DeepPanel() {
  const [company, setCompany] = useState('')
  const [role, setRole] = useState('')
  const [jd, setJd] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [err, setErr] = useState('')
  const run = async () => {
    setLoading(true); setErr(''); setResult(null)
    try {
      const { data } = await api.post('/career-ops/deep-research', { company, role, jd_text: jd })
      setResult(data)
    } catch (e: any) { setErr(e?.response?.data?.detail || e.message) }
    finally { setLoading(false) }
  }
  return (
    <div className="space-y-3">
      <div className="grid md:grid-cols-2 gap-3">
        <input className="rounded border border-border bg-background px-3 py-2 text-sm" placeholder="Company" value={company} onChange={e => setCompany(e.target.value)} />
        <input className="rounded border border-border bg-background px-3 py-2 text-sm" placeholder="Role" value={role} onChange={e => setRole(e.target.value)} />
      </div>
      <textarea className="w-full min-h-32 rounded border border-border bg-background px-3 py-2 text-sm font-mono" placeholder="JD text (optional)" value={jd} onChange={e => setJd(e.target.value)} />
      <Button onClick={run} disabled={loading || !company || !role}>
        {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Search className="w-4 h-4 mr-2" />}
        Generate research prompt
      </Button>
      <Err msg={err} />
      {result?.research_prompt && (
        <div className="border border-border rounded-xl p-5 bg-card space-y-3">
          <div className="flex justify-between items-center">
            <h3 className="font-semibold">Copy-paste into Perplexity / Claude / ChatGPT</h3>
            <Button variant="outline" size="sm" onClick={() => navigator.clipboard.writeText(result.research_prompt)}>Copy</Button>
          </div>
          <pre className="text-xs whitespace-pre-wrap font-mono bg-muted/50 p-3 rounded">{result.research_prompt}</pre>
          {result.suggested_sources && (
            <div>
              <h4 className="text-sm font-semibold">Suggested sources</h4>
              <ul className="list-disc list-inside text-sm text-muted-foreground">
                {result.suggested_sources.map((s: string, i: number) => <li key={i}>{s}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Patterns ─────────────────────────────────────────────────────────────────
function PatternsPanel() {
  const [json, setJson] = useState('[\n  {"company":"","role":"","archetype":"","score":0,"status":"Applied","blockers":[],"remote_policy":"global"}\n]')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [err, setErr] = useState('')
  const run = async () => {
    setLoading(true); setErr(''); setResult(null)
    try {
      const apps = JSON.parse(json)
      const { data } = await api.post('/career-ops/patterns', { applications: apps })
      setResult(data)
    } catch (e: any) { setErr(e?.response?.data?.detail || e.message) }
    finally { setLoading(false) }
  }
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        Paste a JSON array (≥5 items) of past applications. Each entry needs <code>status</code>;
        <code>score</code>, <code>archetype</code>, <code>blockers</code>, <code>remote_policy</code> are optional.
      </p>
      <textarea className="w-full min-h-48 rounded border border-border bg-background px-3 py-2 text-xs font-mono" value={json} onChange={e => setJson(e.target.value)} />
      <Button onClick={run} disabled={loading}>
        {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <BarChart3 className="w-4 h-4 mr-2" />}
        Analyze patterns
      </Button>
      <Err msg={err} />
      {result && <JsonView data={result} />}
    </div>
  )
}

// ── Follow-up ────────────────────────────────────────────────────────────────
function FollowupPanel() {
  const [form, setForm] = useState({ company: '', role: '', status: 'applied', days_since_action: 7, last_message: '' })
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [err, setErr] = useState('')
  const run = async () => {
    setLoading(true); setErr(''); setResult(null)
    try {
      const { data } = await api.post('/career-ops/followup', form)
      setResult(data)
    } catch (e: any) { setErr(e?.response?.data?.detail || e.message) }
    finally { setLoading(false) }
  }
  return (
    <div className="space-y-3">
      <div className="grid md:grid-cols-2 gap-3">
        <input className="rounded border border-border bg-background px-3 py-2 text-sm" placeholder="Company" value={form.company} onChange={e => setForm({ ...form, company: e.target.value })} />
        <input className="rounded border border-border bg-background px-3 py-2 text-sm" placeholder="Role" value={form.role} onChange={e => setForm({ ...form, role: e.target.value })} />
        <select className="rounded border border-border bg-background px-3 py-2 text-sm" value={form.status} onChange={e => setForm({ ...form, status: e.target.value })}>
          <option value="applied">applied (cadence 7d)</option>
          <option value="responded">responded (cadence 3d)</option>
          <option value="interview">interview (cadence 1d)</option>
        </select>
        <input type="number" className="rounded border border-border bg-background px-3 py-2 text-sm" placeholder="Days since last action" value={form.days_since_action} onChange={e => setForm({ ...form, days_since_action: parseInt(e.target.value || '0') })} />
      </div>
      <textarea className="w-full min-h-24 rounded border border-border bg-background px-3 py-2 text-sm" placeholder="Last message they sent (optional)" value={form.last_message} onChange={e => setForm({ ...form, last_message: e.target.value })} />
      <Button onClick={run} disabled={loading || !form.company}>
        {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Mail className="w-4 h-4 mr-2" />}
        Draft follow-up
      </Button>
      <Err msg={err} />
      {result && (
        <div className="border border-border rounded-xl p-5 bg-card space-y-3">
          <span className={`px-3 py-1 rounded-full text-xs font-semibold inline-block ${
            result.urgency === 'URGENT' ? 'bg-red-500/15 text-red-600' :
            result.urgency === 'OVERDUE' ? 'bg-amber-500/15 text-amber-600' :
            result.urgency === 'COLD' ? 'bg-zinc-500/15 text-zinc-500' :
            'bg-blue-500/15 text-blue-600'
          }`}>{result.urgency}</span>
          {result.email_draft && (
            <div>
              <h4 className="font-semibold text-sm">Email draft</h4>
              <p className="text-sm font-medium mt-1">Subject: {result.email_draft.subject}</p>
              <pre className="text-sm whitespace-pre-wrap mt-2 bg-muted/50 p-3 rounded">{result.email_draft.body}</pre>
            </div>
          )}
          {result.linkedin_draft && (
            <div>
              <h4 className="font-semibold text-sm">LinkedIn draft</h4>
              <pre className="text-sm whitespace-pre-wrap mt-1 bg-muted/50 p-3 rounded">{result.linkedin_draft}</pre>
            </div>
          )}
          {result.next_followup_in_days != null && (
            <p className="text-xs text-muted-foreground">Next follow-up in {result.next_followup_in_days} days · {result.close_loop_advice}</p>
          )}
        </div>
      )}
    </div>
  )
}

// ── Contact / LinkedIn Outreach ──────────────────────────────────────────────
function ContactPanel() {
  const [form, setForm] = useState({
    company: '', role: '', contact_type: 'recruiter', contact_name: '', contact_signal: '', language: 'en',
  })
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [err, setErr] = useState('')
  const run = async () => {
    setLoading(true); setErr(''); setResult(null)
    try {
      const { data } = await api.post('/career-ops/contact-strategy', form)
      setResult(data)
    } catch (e: any) { setErr(e?.response?.data?.detail || e.message) }
    finally { setLoading(false) }
  }
  return (
    <div className="space-y-3">
      <div className="grid md:grid-cols-2 gap-3">
        <input className="rounded border border-border bg-background px-3 py-2 text-sm" placeholder="Company" value={form.company} onChange={e => setForm({ ...form, company: e.target.value })} />
        <input className="rounded border border-border bg-background px-3 py-2 text-sm" placeholder="Role" value={form.role} onChange={e => setForm({ ...form, role: e.target.value })} />
        <select className="rounded border border-border bg-background px-3 py-2 text-sm" value={form.contact_type} onChange={e => setForm({ ...form, contact_type: e.target.value })}>
          <option value="recruiter">Recruiter</option>
          <option value="hiring_manager">Hiring Manager</option>
          <option value="peer">Peer (referral)</option>
          <option value="interviewer">Interviewer</option>
        </select>
        <select className="rounded border border-border bg-background px-3 py-2 text-sm" value={form.language} onChange={e => setForm({ ...form, language: e.target.value })}>
          <option value="en">English</option>
          <option value="es">Spanish</option>
        </select>
        <input className="rounded border border-border bg-background px-3 py-2 text-sm" placeholder="Contact name (optional)" value={form.contact_name} onChange={e => setForm({ ...form, contact_name: e.target.value })} />
        <input className="rounded border border-border bg-background px-3 py-2 text-sm" placeholder="Specific signal — talk, post, hire (optional)" value={form.contact_signal} onChange={e => setForm({ ...form, contact_signal: e.target.value })} />
      </div>
      <Button onClick={run} disabled={loading || !form.company}>
        {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Users className="w-4 h-4 mr-2" />}
        Generate opener
      </Button>
      <Err msg={err} />
      {result && (
        <div className="border border-border rounded-xl p-5 bg-card space-y-3">
          <div>
            <h4 className="font-semibold text-sm">Primary message ({result.primary_message?.length} chars)</h4>
            <p className="text-sm whitespace-pre-wrap mt-1 bg-muted/50 p-3 rounded">{result.primary_message}</p>
          </div>
          {(result.alternates || []).length > 0 && (
            <div>
              <h4 className="font-semibold text-sm">Alternates</h4>
              {result.alternates.map((a: string, i: number) => (
                <p key={i} className="text-sm mt-1 bg-muted/50 p-2 rounded">{a}</p>
              ))}
            </div>
          )}
          <p className="text-xs text-muted-foreground italic">{result.rationale}</p>
        </div>
      )}
    </div>
  )
}
