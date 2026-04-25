"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Bot,
  BriefcaseBusiness,
  CheckCircle,
  ChevronRight,
  Globe,
  Linkedin,
  Search,
  Sparkles,
  Star,
  Zap,
} from "lucide-react";

// ── Scroll-reveal hook (adapted from Lumera) ──────────────────────────────────
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

// ── Counter animation hook ────────────────────────────────────────────────────
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

const PHASES = [
  {
    id: 1,
    icon: Linkedin,
    label: "Phase 1",
    title: "LinkedIn Auto-Apply",
    description: "AI fills every Easy Apply form — work experience, education, custom questions — using your real profile.",
    span: "lg:col-span-2 lg:row-span-2",
    accent: "bg-blue-600",
    textAccent: "text-blue-400",
  },
  {
    id: 2,
    icon: BriefcaseBusiness,
    label: "Phase 2",
    title: "Internshala",
    description: "Scans and applies to relevant internships and fresher roles automatically.",
    span: "lg:col-span-1 lg:row-span-1",
    accent: "bg-emerald-600",
    textAccent: "text-emerald-400",
  },
  {
    id: 3,
    icon: Globe,
    label: "Phase 3",
    title: "Wellfound Connect",
    description: "Discovers startup roles and sends AI-crafted connection messages.",
    span: "lg:col-span-1 lg:row-span-1",
    accent: "bg-violet-600",
    textAccent: "text-violet-400",
  },
  {
    id: 4,
    icon: Search,
    label: "Phase 4–5",
    title: "Naukri + Unstop",
    description: "Covers India's largest job portals — Naukri and Unstop — in parallel.",
    span: "lg:col-span-1 lg:row-span-1",
    accent: "bg-orange-600",
    textAccent: "text-orange-400",
  },
  {
    id: 5,
    icon: Bot,
    label: "Phase 6",
    title: "Web Search Apply",
    description: "Searches Greenhouse, Lever, Ashby, and 40+ company career pages for fresh postings.",
    span: "lg:col-span-2 lg:row-span-1",
    accent: "bg-rose-600",
    textAccent: "text-rose-400",
  },
  {
    id: 6,
    icon: Sparkles,
    label: "Phase 7",
    title: "Form Auto-Fill",
    description: "Opens application tabs and fills every form field with your profile data — including AI-answered custom questions.",
    span: "lg:col-span-1 lg:row-span-1",
    accent: "bg-amber-600",
    textAccent: "text-amber-400",
  },
];

const STATS = [
  { label: "Platforms Automated", value: 7, suffix: "" },
  { label: "Company Direct Scans", value: 45, suffix: "+" },
  { label: "Minutes per Phase", value: 15, suffix: "" },
  { label: "AI Form Fields Filled", value: 98, suffix: "%" },
];

const MARQUEE_ITEMS = [
  "LinkedIn Easy Apply",
  "Internshala",
  "Wellfound",
  "Naukri",
  "Unstop",
  "Greenhouse API",
  "Lever",
  "Ashby",
  "Workday",
  "AI Form Fill",
  "Anthropic",
  "OpenAI",
  "Razorpay",
  "Freshworks",
  "Postman",
];

const TESTIMONIALS = [
  {
    quote:
      "Applied to 47 jobs in 60 minutes across 5 platforms. Got 3 interview calls that same week. The AI form filler is the real deal.",
    author: "Arjun Mehta",
    role: "MBA Fresher",
    location: "Bangalore, India",
  },
  {
    quote:
      "I was spending 4 hours a day copy-pasting the same answers. JobAgent cut that to zero and got me a Wellfound startup role.",
    author: "Priya Sharma",
    role: "Product Management Intern",
    location: "Mumbai, India",
  },
  {
    quote:
      "The LinkedIn phase alone is worth it. It clicks through every Easy Apply step including those unexpected dialogs.",
    author: "Rahul Gupta",
    role: "Business Analyst",
    location: "Delhi, India",
  },
];

// ── Components ────────────────────────────────────────────────────────────────

function StatCard({ label, value, suffix, start }: { label: string; value: number; suffix: string; start: boolean }) {
  const count = useCountUp(value, 1200, start);
  return (
    <div className="flex flex-col items-center gap-1 px-6 first:pl-0 last:pr-0">
      <span className="text-4xl font-bold text-white tabular-nums">
        {count}{suffix}
      </span>
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
  const [scrollProgress, setScrollProgress] = useState(0);

  const { ref: statsRef, isVisible: statsVisible } = useScrollReveal(0.3);
  const { ref: phasesRef, isVisible: phasesVisible } = useScrollReveal(0.1);
  const { ref: howRef, isVisible: howVisible } = useScrollReveal(0.2);
  const { ref: testimonialsRef, isVisible: testimonialsVisible } = useScrollReveal(0.2);
  const { ref: ctaRef, isVisible: ctaVisible } = useScrollReveal(0.3);

  const [activeTestimonial, setActiveTestimonial] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => setHeroVisible(true), 100);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    const onScroll = () => {
      const progress = Math.min(window.scrollY / 500, 1);
      const ease = progress < 0.5 ? 2 * progress * progress : 1 - Math.pow(-2 * progress + 2, 2) / 2;
      setScrollProgress(ease);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div className="min-h-screen bg-black text-white overflow-x-hidden">

      {/* ── Nav ── */}
      <nav className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 lg:px-12 h-16 border-b border-white/5 backdrop-blur-sm bg-black/80">
        <div className="flex items-center gap-2">
          <Zap className="w-5 h-5 text-blue-400" />
          <span className="font-semibold text-sm tracking-tight">JobAgent</span>
        </div>
        <div className="flex items-center gap-4">
          <Link href="/login" className="text-sm text-zinc-400 hover:text-white transition-colors">
            Sign in
          </Link>
          <Link
            href="/register"
            className="inline-flex items-center gap-1.5 bg-white text-black text-sm font-medium px-4 py-2 rounded-full hover:bg-zinc-100 transition-colors"
          >
            Get Started
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section className="relative pt-16 -mb-1">
        {/* Background gradient */}
        <div className="absolute inset-0 bg-gradient-to-b from-blue-950/20 via-black to-black pointer-events-none" />
        <div className="absolute top-20 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-blue-600/10 rounded-full blur-3xl pointer-events-none" />

        <div
          className="relative max-w-6xl mx-auto px-6 lg:px-12 pt-28 pb-20 text-center"
          style={{
            paddingLeft: `${scrollProgress * 0}px`, // No horizontal morphing for hero text
          }}
        >
          <div
            className={`inline-flex items-center gap-2 rounded-full bg-white/5 border border-white/10 px-4 py-1.5 text-xs text-zinc-400 mb-8 transition-all duration-700 ${
              heroVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
            }`}
          >
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            7 platforms · AI-powered · Real-time progress
          </div>

          <h1
            className={`text-5xl sm:text-6xl lg:text-8xl font-bold tracking-tight leading-[1.05] mb-6 transition-all duration-700 delay-100 ${
              heroVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
            }`}
          >
            Your job search,
            <br />
            <span className="bg-gradient-to-r from-blue-400 via-violet-400 to-blue-300 bg-clip-text text-transparent">
              automated.
            </span>
          </h1>

          <p
            className={`text-lg text-zinc-400 max-w-xl mx-auto mb-10 leading-relaxed transition-all duration-700 delay-200 ${
              heroVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
            }`}
          >
            JobAgent applies to hundreds of jobs across LinkedIn, Internshala, Wellfound, and 40+ company career pages — while you sleep.
          </p>

          <div
            className={`flex flex-col sm:flex-row items-center justify-center gap-3 transition-all duration-700 delay-300 ${
              heroVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
            }`}
          >
            <Link
              href="/register"
              className="inline-flex items-center gap-2 bg-white text-black font-semibold px-7 py-3.5 rounded-full hover:bg-zinc-100 transition-colors text-sm"
            >
              Start Automating
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              href="/login"
              className="inline-flex items-center gap-2 text-zinc-400 hover:text-white text-sm transition-colors px-4 py-3.5"
            >
              Already have an account
              <ChevronRight className="w-4 h-4" />
            </Link>
          </div>
        </div>

        {/* Stats bar */}
        <section
          ref={statsRef as React.RefObject<HTMLElement>}
          className="relative border-t border-white/5 bg-white/3"
        >
          <div className="max-w-6xl mx-auto px-6 lg:px-12 py-10">
            <div
              className={`flex flex-wrap items-center justify-center gap-8 sm:gap-0 sm:divide-x sm:divide-white/10 transition-all duration-700 ${
                statsVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
              }`}
            >
              {STATS.map((stat) => (
                <StatCard key={stat.label} {...stat} start={statsVisible} />
              ))}
            </div>
          </div>
        </section>
      </section>

      {/* ── Marquee ── */}
      <div className="relative overflow-hidden bg-zinc-950 border-y border-white/5 py-3">
        <div className="flex animate-[marquee_30s_linear_infinite] whitespace-nowrap">
          {[...MARQUEE_ITEMS, ...MARQUEE_ITEMS].map((item, i) => (
            <span key={i} className="inline-flex items-center gap-3 px-6 text-xs text-zinc-500 uppercase tracking-widest">
              <span className="w-1 h-1 rounded-full bg-zinc-600" />
              {item}
            </span>
          ))}
        </div>
      </div>

      {/* ── Phases Bento Grid ── */}
      <section
        ref={phasesRef as React.RefObject<HTMLElement>}
        className="py-24 lg:py-32 max-w-6xl mx-auto px-6 lg:px-12"
      >
        <div
          className={`mb-14 transition-all duration-700 ${
            phasesVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
          }`}
        >
          <p className="text-xs text-zinc-500 uppercase tracking-wider mb-3">7 Automation Phases</p>
          <h2 className="text-4xl sm:text-5xl font-bold tracking-tight leading-tight">
            One click.<br />
            <span className="text-zinc-400">Every platform.</span>
          </h2>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 lg:grid-rows-3 gap-4 lg:h-[680px]">
          {PHASES.map((phase, i) => (
            <PhaseCard key={phase.id} phase={phase} index={i} isVisible={phasesVisible} />
          ))}
        </div>
      </section>

      {/* ── How it Works ── */}
      <section
        ref={howRef as React.RefObject<HTMLElement>}
        className="py-24 bg-zinc-950 border-y border-white/5"
      >
        <div className="max-w-6xl mx-auto px-6 lg:px-12">
          <div
            className={`text-center mb-16 transition-all duration-700 ${
              howVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
            }`}
          >
            <p className="text-xs text-zinc-500 uppercase tracking-wider mb-3">Simple Setup</p>
            <h2 className="text-4xl sm:text-5xl font-bold tracking-tight">How it works</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {[
              {
                step: "01",
                title: "Set up your profile",
                desc: "Add your resume, credentials for each platform, and configure target roles and locations.",
                icon: CheckCircle,
              },
              {
                step: "02",
                title: "Choose your phases",
                desc: "Select which platforms to run. Free plan includes LinkedIn. Pro unlocks all 7 phases.",
                icon: Zap,
              },
              {
                step: "03",
                title: "Watch it apply",
                desc: "Real-time logs stream every action. All browsers stay open so you can review before submitting.",
                icon: Bot,
              },
            ].map((item, i) => {
              const Icon = item.icon;
              return (
                <div
                  key={item.step}
                  className={`flex flex-col gap-4 transition-all duration-700 ${
                    howVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
                  }`}
                  style={{ transitionDelay: `${i * 120}ms` }}
                >
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

      {/* ── Testimonials ── */}
      <section
        ref={testimonialsRef as React.RefObject<HTMLElement>}
        className="py-24 lg:py-32 max-w-6xl mx-auto px-6 lg:px-12"
      >
        <div
          className={`text-center mb-16 transition-all duration-700 ${
            testimonialsVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
          }`}
        >
          <p className="text-xs text-zinc-500 uppercase tracking-wider mb-3">Success Stories</p>
          <h2 className="text-4xl sm:text-5xl font-bold tracking-tight">Real results</h2>
        </div>

        <div
          className={`relative transition-all duration-700 delay-200 ${
            testimonialsVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
          }`}
        >
          <div className="bg-zinc-900 border border-zinc-800 rounded-3xl p-10 lg:p-16 max-w-3xl mx-auto">
            <div className="flex gap-1 mb-6">
              {[...Array(5)].map((_, i) => (
                <Star key={i} className="w-4 h-4 fill-amber-400 text-amber-400" />
              ))}
            </div>
            <blockquote className="text-xl lg:text-2xl font-medium leading-relaxed text-white mb-8">
              &ldquo;{TESTIMONIALS[activeTestimonial].quote}&rdquo;
            </blockquote>
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold text-sm">{TESTIMONIALS[activeTestimonial].author}</p>
                <p className="text-xs text-zinc-500">
                  {TESTIMONIALS[activeTestimonial].role} · {TESTIMONIALS[activeTestimonial].location}
                </p>
              </div>
              <div className="flex gap-2">
                {TESTIMONIALS.map((_, i) => (
                  <button
                    key={i}
                    onClick={() => setActiveTestimonial(i)}
                    className={`w-2 h-2 rounded-full transition-colors ${
                      i === activeTestimonial ? "bg-white" : "bg-zinc-700 hover:bg-zinc-500"
                    }`}
                  />
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section
        ref={ctaRef as React.RefObject<HTMLElement>}
        className="py-24 bg-gradient-to-t from-blue-950/20 to-black border-t border-white/5"
      >
        <div
          className={`max-w-2xl mx-auto px-6 text-center transition-all duration-700 ${
            ctaVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
          }`}
        >
          <h2 className="text-4xl sm:text-5xl font-bold tracking-tight mb-4 leading-tight">
            Stop applying manually.
            <br />
            <span className="text-zinc-500">Start landing interviews.</span>
          </h2>
          <p className="text-zinc-400 mb-10 text-base leading-relaxed">
            Set up in 5 minutes. JobAgent handles the rest — across every platform, with AI that knows your profile.
          </p>
          <Link
            href="/register"
            className="inline-flex items-center gap-2 bg-white text-black font-semibold px-8 py-4 rounded-full hover:bg-zinc-100 transition-colors text-sm"
          >
            Get started free
            <ArrowRight className="w-4 h-4" />
          </Link>
          <p className="text-xs text-zinc-600 mt-4">No credit card required · LinkedIn phase always free</p>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-white/5 py-8">
        <div className="max-w-6xl mx-auto px-6 lg:px-12 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2 text-sm text-zinc-600">
            <Zap className="w-4 h-4" />
            JobAgent
          </div>
          <div className="flex gap-6 text-xs text-zinc-600">
            <Link href="/login" className="hover:text-zinc-400 transition-colors">Sign in</Link>
            <Link href="/register" className="hover:text-zinc-400 transition-colors">Register</Link>
          </div>
        </div>
      </footer>

      {/* Marquee animation */}
      <style>{`
        @keyframes marquee {
          from { transform: translateX(0); }
          to { transform: translateX(-50%); }
        }
      `}</style>
    </div>
  );
}
