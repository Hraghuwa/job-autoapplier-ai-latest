'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { FileText, Eye, EyeOff, ArrowRight, Loader2, Sparkles } from 'lucide-react'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [slowHint, setSlowHint] = useState(false)
  const router = useRouter()
  const { setAuth } = useAuth()

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    setSlowHint(false)
    const slowTimer = setTimeout(() => setSlowHint(true), 4000)

    try {
      const { data } = await api.post('/auth/login', { email, password })
      const meRes = await api.get('/auth/me', {
        headers: { Authorization: `Bearer ${data.access_token}` },
      })
      setAuth(data.access_token, data.refresh_token, meRes.data)
      router.replace('/dashboard')
    } catch (err: any) {
      // Distinguish backend errors (got a response) from network errors
      // (couldn't reach the API at all). The latter usually means
      // NEXT_PUBLIC_API_URL is misconfigured on Vercel or the backend
      // is down — surface that explicitly so it's debuggable from the UI.
      if (err.response?.data?.detail) {
        setError(err.response.data.detail)
      } else if (err.code === 'ERR_NETWORK' || err.message === 'Network Error') {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || '(unset — falling back to localhost)'
        setError(
          `Can't reach the API at ${apiUrl}. ` +
          `Set NEXT_PUBLIC_API_URL in Vercel to your Railway backend URL, ` +
          `or check that the backend is running.`
        )
      } else if (err.code === 'ECONNABORTED') {
        setError('Server took too long to respond. Please try again — the backend is warming up.')
      } else {
        setError('Login failed. Please try again.')
      }
    } finally {
      clearTimeout(slowTimer)
      setLoading(false)
      setSlowHint(false)
    }
  }

  return (
    <div className="min-h-screen flex" style={{ background: 'hsl(var(--color-surface))' }}>
      {/* Left side — branding */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden items-center justify-center"
        style={{ background: 'linear-gradient(135deg, hsl(var(--color-brand)), hsl(var(--color-brand-light)))' }}>
        {/* Decorative elements */}
        <div className="absolute inset-0 opacity-10">
          <div className="absolute top-20 left-20 w-64 h-64 rounded-full border border-white/30" />
          <div className="absolute bottom-32 right-16 w-96 h-96 rounded-full border border-white/20" />
          <div className="absolute top-1/3 right-1/4 w-48 h-48 rounded-full border border-white/25" />
        </div>

        <div className="relative z-10 max-w-lg px-12 text-white">
          <div className="flex items-center gap-3 mb-8">
            <div className="h-12 w-12 rounded-xl bg-white/10 backdrop-blur flex items-center justify-center">
              <FileText className="h-6 w-6 text-white" />
            </div>
            <span className="font-display text-2xl font-bold tracking-tight">JobAgent</span>
          </div>

          <h1 className="font-display text-4xl font-bold leading-tight mb-4">
            Automate your job search <br />
            <span className="text-[hsl(var(--color-accent))]">get hired faster.</span>
          </h1>

          <p className="text-white/70 text-lg leading-relaxed mb-8">
            AI-powered career agents that apply for you, optimize your profile,
            and manage applications on LinkedIn, Wellfound, and more.
          </p>

          <div className="space-y-4">
            {[
              'One-Click Mass Apply',
              'AI Profile Optimization',
              'Multi-Platform Support',
              'Live Application Tracking',
            ].map((feature) => (
              <div key={feature} className="flex items-center gap-3">
                <div className="h-5 w-5 rounded-full bg-[hsl(var(--color-accent))]/20 flex items-center justify-center">
                  <Sparkles className="h-3 w-3 text-[hsl(var(--color-accent))]" />
                </div>
                <span className="text-white/80 text-sm">{feature}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right side — form */}
      <div className="flex-1 flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-md">
          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-2.5 mb-8 justify-center">
            <div className="h-10 w-10 rounded-lg bg-gradient-to-br from-[hsl(var(--color-accent))] to-[hsl(var(--color-brand))] flex items-center justify-center">
              <FileText className="h-5 w-5 text-white" />
            </div>
            <span className="font-display text-xl font-bold">JobAgent</span>
          </div>

          <div className="mb-8">
            <h2 className="font-display text-2xl font-bold mb-2">Welcome back</h2>
            <p className="text-muted-foreground">Sign in to your account to launch your next mission.</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            {error && (
              <div className="px-4 py-3 rounded-lg text-sm font-medium animate-fade-up"
                style={{ background: 'hsl(var(--color-error-light))', color: 'hsl(var(--color-error))' }}>
                {error}
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="email" className="text-sm font-medium">Email address</Label>
              <Input
                id="email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="h-11 px-4 bg-white dark:bg-[hsl(234,28%,14%)] border-border focus:ring-2 focus:ring-[hsl(var(--color-accent))]/20 focus:border-[hsl(var(--color-accent))] transition-all"
              />
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="password" className="text-sm font-medium">Password</Label>
                <Link href="/forgot-password" className="text-xs font-medium text-[hsl(var(--color-accent))] hover:underline">
                  Forgot password?
                </Link>
              </div>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="h-11 px-4 pr-10 bg-white dark:bg-[hsl(234,28%,14%)] border-border focus:ring-2 focus:ring-[hsl(var(--color-accent))]/20 focus:border-[hsl(var(--color-accent))] transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <Button
              type="submit"
              disabled={loading}
              className="w-full h-11 font-semibold text-white gap-2 transition-all duration-200"
              style={{
                background: loading
                  ? 'hsl(var(--color-accent) / 0.7)'
                  : 'linear-gradient(135deg, hsl(var(--color-accent)), hsl(var(--color-accent-hover)))',
              }}
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  Sign in
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </Button>

            {slowHint && (
              <p className="text-xs text-center text-muted-foreground animate-fade-up">
                Backend is warming up — this can take 10–15 seconds on first request.
              </p>
            )}
          </form>

          <p className="mt-6 text-center text-sm text-muted-foreground">
            Don&apos;t have an account?{' '}
            <Link href="/register" className="font-semibold text-[hsl(var(--color-accent))] hover:underline">
              Sign up free
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
