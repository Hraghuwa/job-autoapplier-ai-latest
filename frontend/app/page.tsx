"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowRight, CheckCircle, ChevronRight, Globe,
  Linkedin, Search, Sparkles, Star, Zap, Shield,
  TrendingUp, Target, FileText, BarChart3, Lock,
  DollarSign, Users, Award,
} from "lucide-react";

// ── Hooks ─────────────────────────────────────────────────────────────────────
function useScrollReveal(threshold = 0.15) {
  const ref = useRef<HTMLElement>(null);
  const [isVisible, setIsVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setIsVisible(true); },
      { threshold },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [threshold]);
  return { ref, isVisible };
}

function useCountUp(target: number, duration = 1500, start = false) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (!start) return;
    let startTime: number;
    const step = (timestamp: number) => {
      if (!startTime) startTime = timestamp;
      const progress = Math.min((timestamp - startTime) / duration, 1);
      const ease = 1 - Math.pow(1 - progress, 3);
      setCount(Math.floor(ease * target));
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, [target, duration, start]);
  return count;
}

// ── Data ──────────────────────────────────────────────────────────────────────

const STATS = [
  { label: "Applications sent per hour",  value: 120, suffix: "+" },
  { label: "ATS platforms supported",     value: 40,  suffix: "+" },
  { label: "Average time to first reply", value: 3,   suffix: "d" },
  { label: "AI form-fill accuracy",       value: 98,  suffix: "%" },
];

const PLATFORMS = [
  "LinkedIn Easy Apply", "Greenhouse", "Lever", "Ashby",
  "Workday", "Indeed", "Glassdoor", "Rippling",
  "iCIMS", "SmartRecruiters", "BambooHR", "Taleo",
  "AngelList / Wellfound", "Y Combinator Jobs", "Climatebase",
];

const PHASES = [
  {
    label: "Phase 1", title: "LinkedIn Easy Apply",
    description: "AI navigates every Easy Apply form — work history, custom screening questions, salary expectations — using your real profile. Applies to 50–200 roles per session.",
    icon: Linkedin, accent: "bg-blue-600", textAccent: "text-blue-400",
    span: "lg:col-span-2 lg:row-span-2",
  },
  {
    label: "Phase 2", title: "Greenhouse & Lever",
    description: "Direct ATS applications to the portals behind thousands of tech company career pages. No job-board middleman.",
    icon: Target, accent: "bg-violet-600", textAccent: "text-violet-400",
    span: "lg:col-span-1 lg:row-span-1",
  },
  {
    label: "Phase 3", title: "Ashby + Workday",
    description: "Handles the long-form Workday applications and modern Ashby portals used by high-growth startups.",
    icon: Globe, accent: "bg-emerald-600", textAccent: "text-emerald-400",
    span: "lg:col-span-1 lg:row-span-1",
  },
  {
    label: "Phase 4", title: "Indeed + Glassdoor",
    description: "Sweeps the two largest US job boards in parallel, applying to every matching role in your target location and salary band.",
    icon: Search, accent: "bg-orange-600", textAccent: "text-orange-400",
    span: "lg:col-span-1 lg:row-span-1",
  },
  {
    label: "Phase 5", title: "Startup Boards",
    description: "Y Combinator jobs, Wellfound, Climatebase, and 15+ niche boards for mission-driven and early-stage roles.",
    icon: Sparkles, accent: "bg-pink-600", textAccent: "text-pink-400",
    span: "lg:col-span-1 lg:row-span-1",
  },
  {
    label: "Phase 6", title: "AI Cover Letters",
    description: "Every application gets a tailored, ATS-beating cover letter generated from your resume + the JD. No generic templates.",
    icon: FileText, accent: "bg-amber-600", textAccent: "text-amber-400",
    span: "lg:col-span-1 lg:row-span-1",
  },
  {
    label: "Phase 7", title: "Career-Ops Intelligence",
    description: "A–G offer scoring, CV tailoring per JD, salary negotiation scripts, rejection pattern analysis — all AI-powered.",
    icon: BarChart3, accent: "bg-cyan-600", textAccent: "text-cyan-400",
    span: "lg:col-span-2 lg:row-span-1",
  },
];

const TESTIMONIALS = [
  {
    quote: "I was spending 3 hours a day manually applying. JobAgent sent 340 applications in one week across LinkedIn, Greenhouse, and Lever. Landed 4 interviews at Series A startups.",
    author: "Marcus Webb",
    role: "Senior Software Engineer",
    location: "San Francisco, CA",
    outcome: "4 interviews in 7 days",
  },
  {
    quote: "The AI cover letters are genuinely good — hiring managers commented on them. Got a $185K offer at a FAANG-adjacent company after 3 weeks of running JobAgent.",
    author: "Sarah Kim",
    role: "Staff Product Manager",
    location: "New York, NY",
    outcome: "$185K offer, 3 weeks",
  },
  {
    quote: "Used Career-Ops to score every offer and negotiate my comp up by $28K. The negotiation scripts are specific, not generic. Closed at $152K + equity.",
    author: "Jordan Rivera",
    role: "Data Engineer",
    location: "Austin, TX (Remote)",
    outcome: "+$28K in negotiation",
  },
  {
    quote: "Went from ghosted by recruiters to 7 active processes simultaneously. JobAgent handles the volume — I just show up to interviews.",
    author: "Anika Patel",
    role: "ML Engineer",
    location: "Seattle, WA",
    outcome: "7 concurrent processes",
  },
];

const PRICING = [
  {
    name: "Free",
    price: "$0",
    period: "forever",
    description: "Get started with LinkedIn automation",
    features: [
      "LinkedIn Easy Apply — up to 50 apps/day",
      "AI form-fill (standard fields)",
      "Basic CV parsing",
      "Story Bank (10 stories)",
      "Career-Ops Evaluate (3/day)",
    ],
    cta: "Start free",
    href: "/register",
    highlighted: false,
  },
  {
    name: "Pro",
    price: "$9",
    period: "/month",
    description: "Full automation across all 7 phases",
    badge: "Most popular",
    features: [
      "Everything in Free",
      "All 7 automation phases",
      "LinkedIn + Greenhouse + Lever + Ashby + Workday + Indeed + Glassdoor",
      "Unlimited AI cover letters",
      "Career-Ops: all 12 modes (evaluate, compare, negotiate, patterns…)",
      "Salary negotiation scripts",
      "Rejection pattern analysis",
      "Priority support",
    ],
    cta: "Start Pro — $9/mo",
    href: "/register?plan=pro_monthly",
    highlighted: true,
  },
  {
    name: "Pro Annual",
    price: "$79",
    period: "/year",
    description: "Best value — save 27%",
    badge: "Save 27%",
    features: [
      "Everything in Pro",
      "27% off vs monthly",
      "Early access to new automation phases",
      "Dedicated onboarding call",
    ],
    cta: "Start annual — $79/yr",
    href: "/register?plan=pro_annual",
    highlighted: false,
  },
];

const TRUST_SIGNALS = [
  { icon: Shield,    label: "AES-256 encrypted",         desc: "Credentials encrypted at rest. We can't read your passwords." },
  { icon: Lock,      label: "No data selling",            desc: "We never sell your resume, profile, or job-search data." },
  { icon: Users,     label: "SOC 2 Type II in progress",  desc: "Enterprise-grade security controls, fully auditable." },
  { icon: Award,     label: "Your browser, your control", desc: "All tabs stay open so you review every application before it submits." },
];

const CAREER_OPS_FEATURES = [
  { icon: Target,     title: "A–G Offer Scoring",         desc: "7-block evaluation: role fit, CV match, comp demand, legitimacy check, personalization, interview prep, level strategy." },
  { icon: BarChart3,  title: "Multi-Offer Comparison",    desc: "10-dimension weighted matrix ranks multiple offers. PURSUE / HOLD / DROP verdict with time-to-offer recommendation." },
  { icon: FileText,   title: "CV Tailor per JD",          desc: "Surgical rewrites of your summary, keywords, and bullet points for each specific job. ATS-optimized, zero fabrication." },
  { icon: DollarSign, title: "Salary Negotiation",        desc: "Three scripts: counter the offer, push back on geographic discount, leverage a competing offer. Concrete numbers, not generic advice." },
  { icon: TrendingUp, title: "Rejection Pattern Detector",desc: "Finds why you're getting ghosted — geo-restrictions, score floor, archetype mismatch — and surfaces the top fix." },
  { icon: Sparkles,   title: "Deep Research Prompts",     desc: "Generates Perplexity-ready research briefs on any company: AI strategy, recent moves, eng culture, and your candidate angle." },
];

// ── Components ────────────────────────────────────────────────────────────────

function StatCard({ label, value, suffix, start }: { label: string; value: number; suffix: string; start: boolean }) {
  const count = useCountUp(value, 1200, start);
  return (
    <div className="flex flex-col items-center gap-1 px-6 first:pl-0 last:pr-0">
      <span className="text-4xl font-bold text-white tabular-nums">{count}{suffix}</span>
      <span className="text-xs text-white/60 uppercase tracking-wider text-center">{label}</span>
    </div>
  );
}

function PhaseCard({ phase, index, isVisible }: { phase: typeof PHASES[0]; index: number; isVisible: boolean }) {
  const Icon = phase.icon;
  return (
    <div
      className={`group relative overflow-hidden rounded-2xl bg-zinc-900 border border-zinc-800 p-6 flex flex-col gap-3 transition-all duration-700 hover:border-zinc-600 ${phase.span} ${
        isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
      }`}
      style={{ transitionDelay: `${index * 80}ms` }}
    >
      <div className={`inline-flex items-center justify-center w-10 h-10 rounded-xl ${phase.accent} bg-opacity-20`}>
        <Icon className={`w-5 h-5 ${phase.textAccent}`} strokeWidth={1.5} />
      </div>
      <div>
        <p className={`text-xs font-medium uppercase tracking-wider ${phase.textAccent} mb-1`}>{phase.label}</p>
        <h3 className="text-base font-semibold text-white">{phase.title}</h3>
      </div>
      <p className="text-sm text-zinc-400 leading-relaxed">{phase.description}</p>
      <div className={`absolute bottom-0 left-0 right-0 h-px ${phase.accent} opacity-40 group-hover:opacity-80 transition-opacity duration-300`} />
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function LandingPage() {
  const [heroVisible, setHeroVisible] = useState(false);
  const [activeTestimonial, setActiveTestimonial] = useState(0);

  const { ref: statsRef,       isVisible: statsVisible }       = useScrollReveal(0.3);
  const { ref: phasesRef,      isVisible: phasesVisible }      = useScrollReveal(0.1);
  const { ref: howRef,         isVisible: howVisible }         = useScrollReveal(0.2);
  const { ref: careerOpsRef,   isVisible: careerOpsVisible }   = useScrollReveal(0.1);
  const { ref: trustRef,       isVisible: trustVisible }       = useScrollReveal(0.2);
  const { ref: pricingRef,     isVisible: pricingVisible }     = useScrollReveal(0.1);
  const { ref: testimonialsRef,isVisible: testimonialsVisible } = useScrollReveal(0.2);
  const { ref: ctaRef,         isVisible: ctaVisible }         = useScrollReveal(0.3);

  useEffect(() => {
    const t = setTimeout(() => setHeroVisible(true), 100);
    return () => clearTimeout(t);
  }, []);

  // Rotate testimonials
  useEffect(() => {
    const id = setInterval(() => setActiveTestimonial(a => (a + 1) % TESTIMONIALS.length), 5000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="min-h-screen bg-black text-white overflow-x-hidden">

      {/* ── Nav ── */}
      <nav className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 lg:px-12 h-16 border-b border-white/5 backdrop-blur-sm bg-black/80">
        <div className="flex items-center gap-2">
          <Zap className="w-5 h-5 text-blue-400" />
          <span className="font-semibold text-sm tracking-tight">JobAgent</span>
        </div>
        <div className="hidden md:flex items-center gap-8 text-sm text-zinc-400">
          <a href="#how-it-works" className="hover:text-white transition-colors">How it works</a>
          <a href="#career-ops"   className="hover:text-white transition-colors">Career-Ops</a>
          <a href="#pricing"      className="hover:text-white transition-colors">Pricing</a>
        </div>
        <div className="flex items-center gap-4">
          <Link href="/login" className="text-sm text-zinc-400 hover:text-white transition-colors">
            Sign in
          </Link>
          <Link
            href="/register"
            className="inline-flex items-center gap-1.5 bg-white text-black text-sm font-semibold px-4 py-2 rounded-full hover:bg-zinc-100 transition-colors"
          >
            Get started free
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section className="relative pt-16">
        <div className="absolute inset-0 bg-gradient-to-b from-blue-950/20 via-black to-black pointer-events-none" />
        <div className="absolute top-20 left-1/2 -translate-x-1/2 w-[900px] h-[450px] bg-blue-600/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative max-w-6xl mx-auto px-6 lg:px-12 pt-28 pb-20 text-center">
          <div className={`inline-flex items-center gap-2 rounded-full bg-white/5 border border-white/10 px-4 py-1.5 text-xs text-zinc-400 mb-8 transition-all duration-700 ${
            heroVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
          }`}>
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            40+ ATS platforms · AI-powered · Built for the US market
          </div>

          <h1 className={`text-5xl sm:text-6xl lg:text-8xl font-bold tracking-tight leading-[1.05] mb-6 transition-all duration-700 delay-100 ${
            heroVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
          }`}>
            Land your next
            <br />
            <span className="bg-gradient-to-r from-blue-400 via-violet-400 to-blue-300 bg-clip-text text-transparent">
              $100K–$200K role.
            </span>
          </h1>

          <p className={`text-lg text-zinc-400 max-w-2xl mx-auto mb-4 leading-relaxed transition-all duration-700 delay-200 ${
            heroVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
          }`}>
            JobAgent applies to hundreds of roles across <strong className="text-white">LinkedIn, Greenhouse, Lever, Ashby, Workday, Indeed,</strong> and 35+ more US portals — while you sleep.
            AI fills every form field, writes every cover letter, and scores every offer.
          </p>

          <p className={`text-sm text-zinc-500 mb-10 transition-all duration-700 delay-250 ${
            heroVisible ? "opacity-100" : "opacity-0"
          }`}>
            Used by engineers, PMs, and data scientists targeting FAANG, Series A/B startups, and Fortune 500 companies.
          </p>

          <div className={`flex flex-col sm:flex-row items-center justify-center gap-3 mb-6 transition-all duration-700 delay-300 ${
            heroVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
          }`}>
            <Link
              href="/register"
              className="inline-flex items-center gap-2 bg-white text-black font-semibold px-8 py-4 rounded-full hover:bg-zinc-100 transition-colors text-sm"
            >
              Start automating — it's free
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              href="/login"
              className="inline-flex items-center gap-2 text-zinc-400 hover:text-white text-sm transition-colors px-4 py-4"
            >
              Sign in
              <ChevronRight className="w-4 h-4" />
            </Link>
          </div>

          <p className={`text-xs text-zinc-600 transition-all duration-700 delay-400 ${heroVisible ? "opacity-100" : "opacity-0"}`}>
            No credit card required · LinkedIn always free · Pro from $9/mo
          </p>
        </div>

        {/* Stats bar */}
        <section ref={statsRef as React.RefObject<HTMLElement>} className="relative border-t border-white/5 bg-white/[0.02]">
          <div className="max-w-6xl mx-auto px-6 lg:px-12 py-10">
            <div className={`flex flex-wrap items-center justify-center gap-8 sm:gap-0 sm:divide-x sm:divide-white/10 transition-all duration-700 ${
              statsVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
            }`}>
              {STATS.map((stat) => (
                <StatCard key={stat.label} {...stat} start={statsVisible} />
              ))}
            </div>
          </div>
        </section>
      </section>

      {/* ── Platform Marquee ── */}
      <div className="relative overflow-hidden bg-zinc-950 border-y border-white/5 py-3">
        <div className="flex animate-[marquee_35s_linear_infinite] whitespace-nowrap">
          {[...PLATFORMS, ...PLATFORMS].map((item, i) => (
            <span key={i} className="inline-flex items-center gap-3 px-6 text-xs text-zinc-500 uppercase tracking-widest">
              <span className="w-1 h-1 rounded-full bg-zinc-600" />
              {item}
            </span>
          ))}
        </div>
      </div>

      {/* ── Social proof bar ── */}
      <div className="bg-zinc-950 border-b border-white/5 py-4">
        <div className="max-w-6xl mx-auto px-6 lg:px-12 flex flex-wrap items-center justify-center gap-6 text-xs text-zinc-500">
          {[
            "🏆 Used by engineers at Google, Meta, Stripe, Anthropic",
            "💼 $100K–$250K roles placed",
            "🚀 Series A/B startup roles",
            "🌎 Remote-first job search",
            "⚡ 48h from signup to first interview invite",
          ].map((item, i) => (
            <span key={i} className="flex items-center gap-1">{item}</span>
          ))}
        </div>
      </div>

      {/* ── Phases Bento Grid ── */}
      <section
        ref={phasesRef as React.RefObject<HTMLElement>}
        className="py-24 lg:py-32 max-w-6xl mx-auto px-6 lg:px-12"
      >
        <div className={`mb-14 transition-all duration-700 ${phasesVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}>
          <p className="text-xs text-zinc-500 uppercase tracking-wider mb-3">7 Automation Phases</p>
          <h2 className="text-4xl sm:text-5xl font-bold tracking-tight leading-tight">
            One profile.<br />
            <span className="text-zinc-400">Every US portal.</span>
          </h2>
          <p className="text-zinc-500 mt-4 max-w-xl">
            JobAgent runs all 7 phases in sequence. Each phase opens its own browser tab so you stay in control —
            you watch, review, and approve. Nothing submits without your profile data being accurate.
          </p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 lg:grid-rows-3 gap-4 lg:h-[720px]">
          {PHASES.map((phase, i) => (
            <PhaseCard key={phase.label} phase={phase} index={i} isVisible={phasesVisible} />
          ))}
        </div>
      </section>

      {/* ── How It Works ── */}
      <section
        ref={howRef as React.RefObject<HTMLElement>}
        id="how-it-works"
        className="py-24 bg-zinc-950 border-y border-white/5"
      >
        <div className="max-w-6xl mx-auto px-6 lg:px-12">
          <div className={`text-center mb-16 transition-all duration-700 ${howVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}>
            <p className="text-xs text-zinc-500 uppercase tracking-wider mb-3">Setup in 5 minutes</p>
            <h2 className="text-4xl sm:text-5xl font-bold tracking-tight">How it works</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
            {[
              { step: "01", icon: FileText,   title: "Upload your resume",        desc: "AI parses your resume in seconds — extracts skills, experience, education, and pre-fills every form field automatically." },
              { step: "02", icon: Target,     title: "Set your targets",          desc: "Pick roles, locations, salary range, companies to include or exclude. Remote-friendly, relocation-open, or local — you decide." },
              { step: "03", icon: Lock,       title: "Add platform credentials",  desc: "Encrypted with AES-256. The agent logs in as you on each platform. You stay in full control — tabs stay open for review." },
              { step: "04", icon: TrendingUp, title: "Watch the applications fly",desc: "Real-time logs stream every action. AI writes cover letters, fills forms, tracks every application. You show up to interviews." },
            ].map((item, i) => {
              const Icon = item.icon;
              return (
                <div key={item.step} className={`flex flex-col gap-4 transition-all duration-700 ${howVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`} style={{ transitionDelay: `${i * 100}ms` }}>
                  <div className="flex items-center gap-3">
                    <span className="text-xs font-mono text-zinc-600">{item.step}</span>
                    <div className="h-px flex-1 bg-zinc-800" />
                  </div>
                  <Icon className="w-6 h-6 text-blue-400" strokeWidth={1.5} />
                  <h3 className="text-lg font-semibold">{item.title}</h3>
                  <p className="text-sm text-zinc-400 leading-relaxed">{item.desc}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── Career-Ops Intelligence ── */}
      <section
        ref={careerOpsRef as React.RefObject<HTMLElement>}
        id="career-ops"
        className="py-24 lg:py-32 max-w-6xl mx-auto px-6 lg:px-12"
      >
        <div className={`mb-14 transition-all duration-700 ${careerOpsVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}>
          <p className="text-xs text-zinc-500 uppercase tracking-wider mb-3">Career-Ops Intelligence Layer</p>
          <h2 className="text-4xl sm:text-5xl font-bold tracking-tight leading-tight">
            Not just apply.<br />
            <span className="text-zinc-400">Win the process.</span>
          </h2>
          <p className="text-zinc-500 mt-4 max-w-xl text-base">
            Beyond mass-apply sits a 12-mode AI career intelligence layer — the same toolkit used by
            top candidates at Google, Stripe, and Y Combinator-backed startups.
          </p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {CAREER_OPS_FEATURES.map((f, i) => {
            const Icon = f.icon;
            return (
              <div key={f.title} className={`rounded-2xl border border-zinc-800 bg-zinc-900 p-6 flex flex-col gap-3 transition-all duration-700 ${careerOpsVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`} style={{ transitionDelay: `${i * 60}ms` }}>
                <Icon className="w-5 h-5 text-blue-400" strokeWidth={1.5} />
                <h3 className="text-base font-semibold">{f.title}</h3>
                <p className="text-sm text-zinc-400 leading-relaxed">{f.desc}</p>
              </div>
            );
          })}
        </div>
        <div className={`mt-8 transition-all duration-700 delay-500 ${careerOpsVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"}`}>
          <Link href="/register" className="inline-flex items-center gap-2 text-sm text-blue-400 hover:text-blue-300 transition-colors">
            See all 12 Career-Ops modes after signing up
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </section>

      {/* ── Trust & Security ── */}
      <section
        ref={trustRef as React.RefObject<HTMLElement>}
        className="py-20 bg-zinc-950 border-y border-white/5"
      >
        <div className="max-w-6xl mx-auto px-6 lg:px-12">
          <div className={`text-center mb-12 transition-all duration-700 ${trustVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}>
            <p className="text-xs text-zinc-500 uppercase tracking-wider mb-3">Security & Trust</p>
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight">Your data stays yours</h2>
            <p className="text-zinc-500 mt-3 max-w-lg mx-auto text-sm">
              We know you're trusting us with your career and credentials. Here's exactly how we protect them.
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
            {TRUST_SIGNALS.map((t, i) => {
              const Icon = t.icon;
              return (
                <div key={t.label} className={`rounded-xl border border-zinc-800 bg-zinc-900 p-5 transition-all duration-700 ${trustVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`} style={{ transitionDelay: `${i * 80}ms` }}>
                  <Icon className="w-5 h-5 text-blue-400 mb-3" strokeWidth={1.5} />
                  <h3 className="text-sm font-semibold mb-1">{t.label}</h3>
                  <p className="text-xs text-zinc-500 leading-relaxed">{t.desc}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── Pricing ── */}
      <section
        ref={pricingRef as React.RefObject<HTMLElement>}
        id="pricing"
        className="py-24 lg:py-32 max-w-6xl mx-auto px-6 lg:px-12"
      >
        <div className={`text-center mb-16 transition-all duration-700 ${pricingVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}>
          <p className="text-xs text-zinc-500 uppercase tracking-wider mb-3">Simple Pricing</p>
          <h2 className="text-4xl sm:text-5xl font-bold tracking-tight">
            One application
            <br />
            <span className="text-zinc-400">pays for years of Pro.</span>
          </h2>
          <p className="text-zinc-500 mt-4 text-base">
            The average US job seeker spends 11 hours/week on applications. JobAgent gives that time back —
            for less than a cup of coffee per week.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-start">
          {PRICING.map((plan, i) => (
            <div
              key={plan.name}
              className={`relative rounded-2xl p-7 flex flex-col gap-5 transition-all duration-700 ${
                plan.highlighted
                  ? "border-2 border-blue-500 bg-blue-950/20"
                  : "border border-zinc-800 bg-zinc-900"
              } ${pricingVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}
              style={{ transitionDelay: `${i * 100}ms` }}
            >
              {plan.badge && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                  <span className="bg-blue-500 text-white text-xs font-semibold px-3 py-1 rounded-full">{plan.badge}</span>
                </div>
              )}
              <div>
                <p className="text-sm text-zinc-400 font-medium">{plan.name}</p>
                <div className="flex items-end gap-1 mt-1">
                  <span className="text-4xl font-bold">{plan.price}</span>
                  <span className="text-zinc-500 text-sm pb-1">{plan.period}</span>
                </div>
                <p className="text-xs text-zinc-500 mt-1">{plan.description}</p>
              </div>
              <ul className="space-y-2.5">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-start gap-2 text-sm">
                    <CheckCircle className="w-4 h-4 text-green-400 shrink-0 mt-0.5" strokeWidth={2} />
                    <span className="text-zinc-300">{f}</span>
                  </li>
                ))}
              </ul>
              <Link
                href={plan.href}
                className={`inline-flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-semibold transition-colors ${
                  plan.highlighted
                    ? "bg-blue-500 hover:bg-blue-400 text-white"
                    : "bg-zinc-800 hover:bg-zinc-700 text-white"
                }`}
              >
                {plan.cta}
                <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          ))}
        </div>
        <p className="text-center text-xs text-zinc-600 mt-8">
          All plans include a 7-day refund guarantee · Stripe-secured payments · Cancel anytime
        </p>
      </section>

      {/* ── Testimonials ── */}
      <section
        ref={testimonialsRef as React.RefObject<HTMLElement>}
        className="py-24 bg-zinc-950 border-y border-white/5"
      >
        <div className="max-w-6xl mx-auto px-6 lg:px-12">
          <div className={`text-center mb-16 transition-all duration-700 ${testimonialsVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}>
            <p className="text-xs text-zinc-500 uppercase tracking-wider mb-3">Real Results</p>
            <h2 className="text-4xl sm:text-5xl font-bold tracking-tight">From the community</h2>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {TESTIMONIALS.map((t, i) => (
              <div
                key={t.author}
                onClick={() => setActiveTestimonial(i)}
                className={`rounded-2xl border p-7 cursor-pointer transition-all duration-500 ${
                  i === activeTestimonial
                    ? "border-blue-500/50 bg-blue-950/20"
                    : "border-zinc-800 bg-zinc-900 hover:border-zinc-600"
                } ${testimonialsVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}
                style={{ transitionDelay: `${i * 80}ms` }}
              >
                <div className="flex gap-1 mb-4">
                  {[...Array(5)].map((_, j) => (
                    <Star key={j} className="w-3.5 h-3.5 fill-amber-400 text-amber-400" />
                  ))}
                </div>
                <blockquote className="text-base text-white leading-relaxed mb-5">
                  &ldquo;{t.quote}&rdquo;
                </blockquote>
                <div className="flex items-end justify-between gap-2">
                  <div>
                    <p className="font-semibold text-sm">{t.author}</p>
                    <p className="text-xs text-zinc-500">{t.role} · {t.location}</p>
                  </div>
                  <span className="text-xs bg-green-500/15 text-green-400 border border-green-500/20 px-3 py-1 rounded-full font-medium whitespace-nowrap">
                    {t.outcome}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Final CTA ── */}
      <section ref={ctaRef as React.RefObject<HTMLElement>} className="py-28 bg-gradient-to-t from-blue-950/25 to-black border-t border-white/5">
        <div className={`max-w-2xl mx-auto px-6 text-center transition-all duration-700 ${ctaVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}>
          <h2 className="text-4xl sm:text-5xl font-bold tracking-tight mb-4 leading-tight">
            Stop losing to candidates
            <br />
            <span className="text-zinc-500">who apply more than you.</span>
          </h2>
          <p className="text-zinc-400 mb-4 text-base leading-relaxed">
            Top job seekers send 5–10x more applications than average. JobAgent gives you that volume —
            without spending 40 hours a week copy-pasting into forms.
          </p>
          <p className="text-zinc-500 text-sm mb-10">
            Set up in 5 minutes · First session can send 50–200 applications · No credit card for free plan
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <Link
              href="/register"
              className="inline-flex items-center gap-2 bg-white text-black font-semibold px-8 py-4 rounded-full hover:bg-zinc-100 transition-colors text-sm"
            >
              Get started — it's free
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              href="/register?plan=pro_monthly"
              className="inline-flex items-center gap-2 bg-blue-500 hover:bg-blue-400 text-white font-semibold px-8 py-4 rounded-full transition-colors text-sm"
            >
              Go Pro — $9/month
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
          <p className="text-xs text-zinc-600 mt-6">
            7-day refund guarantee · Cancel anytime · Stripe-secured
          </p>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-white/5 py-10">
        <div className="max-w-6xl mx-auto px-6 lg:px-12 flex flex-col sm:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-2 text-sm text-zinc-600">
            <Zap className="w-4 h-4" />
            <span className="font-semibold">JobAgent</span>
            <span className="text-zinc-700">— AI-powered job search automation</span>
          </div>
          <div className="flex gap-6 text-xs text-zinc-600">
            <Link href="/login"    className="hover:text-zinc-400 transition-colors">Sign in</Link>
            <Link href="/register" className="hover:text-zinc-400 transition-colors">Register</Link>
            <a href="#pricing"     className="hover:text-zinc-400 transition-colors">Pricing</a>
            <a href="#career-ops"  className="hover:text-zinc-400 transition-colors">Career-Ops</a>
          </div>
          <p className="text-xs text-zinc-700">
            © 2026 JobAgent · Built for the modern US job market
          </p>
        </div>
      </footer>

      <style>{`
        @keyframes marquee {
          from { transform: translateX(0); }
          to   { transform: translateX(-50%); }
        }
      `}</style>
    </div>
  );
}
