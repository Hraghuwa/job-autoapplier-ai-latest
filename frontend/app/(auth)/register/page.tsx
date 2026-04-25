'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { FileText, Eye, EyeOff, ArrowRight, Loader2, Check } from 'lucide-react'

export default function RegisterPage() {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [referralCode, setReferralCode] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const router = useRouter()
  const { setAuth } = useAuth()

  const passwordChecks = [
    { label: 'At least 8 characters', met: password.length >= 8 },
    { label: 'Contains a number', met: /\d/.test(password) },
    { label: 'Contains uppercase', met: /[A-Z]/.test(password) },
  ]

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')

    if (password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }

    setLoading(true)
    try {
      const { data } = await api.post('/auth/register', {
        name,
        email,
        password,
        referral_code: referralCode || undefined,
      })
      const meRes = await api.get('/auth/me', {
        headers: { Authorization: `Bearer ${data.access_token}` },
      })
      setAuth(data.access_token, data.refresh_token, meRes.data)
      router.replace('/dashboard')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Registration failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex" style={{ background: 'hsl(var(--color-surface))' }}>
      {/* Left side — branding */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden items-center justify-center"
        style={{ background: 'linear-gradient(135deg, hsl(var(--color-brand)), hsl(var(--color-brand-light)))' }}>
        <div className="absolute inset-0 opacity-10">
          <div className="absolute top-20 left-20 w-64 h-64 rounded-full border border-white/30" />
          <div className="absolute bottom-32 right-16 w-96 h-96 rounded-full border border-white/20" />
        </div>

        <div className="relative z-10 max-w-lg px-12 text-white">
          <div className="flex items-center gap-3 mb-8">
            <div className="h-12 w-12 rounded-xl bg-white/10 backdrop-blur flex items-center justify-center">
              <FileText className="h-6 w-6 text-white" />
            </div>
            <span className="font-display text-2xl font-bold tracking-tight">JobAgent</span>
          </div>

          <h1 className="font-display text-4xl font-bold leading-tight mb-4">
            Start your next <br />
            <span className="text-[hsl(var(--color-accent))]">career mission.</span>
          </h1>

          <p className="text-white/70 text-lg leading-relaxed mb-8">
            Join thousands of professionals who automated their job search
            and landed dream roles with AI-powered application agents.
          </p>

          <div className="grid grid-cols-2 gap-6">
            {[
              { num: '1M+', label: 'Apps Submitted' },
              { num: '85%', label: 'Interview Rate' },
              { num: '10+', label: 'Platforms' },
              { num: '24/7', label: 'Agent Activity' },
            ].map(({ num, label }) => (
              <div key={label}>
                <p className="font-display text-2xl font-bold text-[hsl(var(--color-accent))]">{num}</p>
                <p className="text-white/60 text-sm">{label}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right side — form */}
      <div className="flex-1 flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-md">
          <div className="lg:hidden flex items-center gap-2.5 mb-8 justify-center">
            <div className="h-10 w-10 rounded-lg bg-gradient-to-br from-[hsl(var(--color-accent))] to-[hsl(var(--color-brand))] flex items-center justify-center">
              <FileText className="h-5 w-5 text-white" />
            </div>
            <span className="font-display text-xl font-bold">JobAgent</span>
          </div>

          <div className="mb-8">
            <h2 className="font-display text-2xl font-bold mb-2">Create your account</h2>
            <p className="text-muted-foreground">Free forever. No credit card required.</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            {error && (
              <div className="px-4 py-3 rounded-lg text-sm font-medium animate-fade-up"
                style={{ background: 'hsl(var(--color-error-light))', color: 'hsl(var(--color-error))' }}>
                {error}
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="name" className="text-sm font-medium">Full name</Label>
              <Input
                id="name"
                type="text"
                placeholder="John Doe"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                className="h-11 px-4 bg-white dark:bg-[hsl(234,28%,14%)]"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="reg-email" className="text-sm font-medium">Email address</Label>
              <Input
                id="reg-email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="h-11 px-4 bg-white dark:bg-[hsl(234,28%,14%)]"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="reg-password" className="text-sm font-medium">Password</Label>
              <div className="relative">
                <Input
                  id="reg-password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Create a strong password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="h-11 px-4 pr-10 bg-white dark:bg-[hsl(234,28%,14%)]"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>

              {password.length > 0 && (
                <div className="space-y-1.5 mt-2 animate-fade-up">
                  {passwordChecks.map(({ label, met }) => (
                    <div key={label} className="flex items-center gap-2 text-xs">
                      <div className={`h-3.5 w-3.5 rounded-full flex items-center justify-center transition-colors ${
                        met ? 'bg-[hsl(var(--color-success))]' : 'bg-muted'
                      }`}>
                        {met && <Check className="h-2.5 w-2.5 text-white" />}
                      </div>
                      <span className={met ? 'text-foreground' : 'text-muted-foreground'}>{label}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="referral" className="text-sm font-medium">
                Referral code <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Input
                id="referral"
                type="text"
                placeholder="Enter code"
                value={referralCode}
                onChange={(e) => setReferralCode(e.target.value)}
                className="h-11 px-4 bg-white dark:bg-[hsl(234,28%,14%)]"
              />
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
                  Create account
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </Button>

            <p className="text-xs text-muted-foreground text-center">
              By signing up, you agree to our Terms of Service and Privacy Policy.
            </p>
          </form>

          <p className="mt-6 text-center text-sm text-muted-foreground">
            Already have an account?{' '}
            <Link href="/login" className="font-semibold text-[hsl(var(--color-accent))] hover:underline">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
