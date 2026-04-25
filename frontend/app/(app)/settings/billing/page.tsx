'use client'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Progress } from '@/components/ui/progress'
import api from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { Check, Zap, CreditCard, Coins, Crown, Sparkles, Globe } from 'lucide-react'
import { useToast } from '@/lib/use-toast'
import { useState } from 'react'

declare global {
  interface Window {
    Razorpay: new (opts: Record<string, unknown>) => { open(): void }
  }
}

type Gateway = 'razorpay' | 'stripe'

const FREE_FEATURES = [
  { label: 'LinkedIn auto-apply only', included: true },
  { label: '20 applies per 48 hours', included: true },
  { label: '50 AI tokens / month', included: true },
  { label: 'Basic job tracking', included: true },
  { label: '3 interview prep questions', included: true },
  { label: 'Web search (30+ boards)', included: false },
  { label: 'AI cover letter generation', included: false },
  { label: 'Scheduled runs', included: false },
  { label: 'Analytics dashboard', included: false },
]

const PRO_FEATURES = [
  { label: 'All platforms (LinkedIn, Wellfound, Internshala, Web)', included: true },
  { label: 'Unlimited daily applies', included: true },
  { label: '2,000 AI tokens / month', included: true },
  { label: 'Web search — 30+ job boards', included: true },
  { label: 'AI cover letter generation', included: true },
  { label: 'Scheduled auto-runs', included: true },
  { label: 'Full analytics dashboard', included: true },
  { label: 'Career-Ops evaluation suite', included: true },
  { label: 'Priority support', included: true },
]

const ADD_ONS = [
  {
    id: 'credits_100', icon: Coins, label: '100 Apply Credits',
    description: 'Extra apply credits, no expiry',
    color: 'text-amber-600', bg: 'bg-amber-50 dark:bg-amber-950/30 border-amber-200',
  },
  {
    id: 'credits_500', icon: Coins, label: '500 Apply Credits',
    description: 'Bulk credits — best per-credit value',
    color: 'text-amber-600', bg: 'bg-amber-50 dark:bg-amber-950/30 border-amber-200',
    badge: 'Best Value',
  },
  {
    id: 'tokens_500', icon: Zap, label: '500 AI Tokens',
    description: 'Top up AI tokens for form fill & cover letters',
    color: 'text-purple-600', bg: 'bg-purple-50 dark:bg-purple-950/30 border-purple-200',
  },
]

function loadRazorpayScript(): Promise<void> {
  return new Promise((resolve) => {
    if (typeof window !== 'undefined' && window.Razorpay) { resolve(); return }
    const s = document.createElement('script')
    s.src = 'https://checkout.razorpay.com/v1/checkout.js'
    s.onload = () => resolve()
    document.body.appendChild(s)
  })
}

function formatPrice(plan: any, gateway: Gateway) {
  if (!plan) return '—'
  if (gateway === 'razorpay') return `₹${Math.round(plan.razorpay_amount / 100)}`
  return `$${(plan.stripe_amount / 100).toFixed(2)}`
}

export default function BillingPage() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const { toast } = useToast()
  const [gateway, setGateway] = useState<Gateway>('razorpay')

  const { data: quota, isLoading: loadingQuota } = useQuery({
    queryKey: ['quota'],
    queryFn: () => api.get('/users/quota', { silent: true } as any).then(r => r.data),
    retry: false,
  })

  const { data: plans = [], isLoading: loadingPlans } = useQuery({
    queryKey: ['plans'],
    queryFn: () => api.get('/payments/plans', { silent: true } as any).then(r => r.data),
    retry: false,
  })

  const { data: payConfig } = useQuery({
    queryKey: ['pay-config'],
    queryFn: () => api.get('/payments/config', { silent: true } as any).then(r => r.data),
    retry: false,
  })

  const razorpayAvailable = payConfig?.razorpay_available ?? false
  const stripeAvailable = payConfig?.stripe_available ?? false

  const purchase = useMutation({
    mutationFn: async (plan_id: string) => {
      if (gateway === 'razorpay') {
        // ── Razorpay modal ──
        const order = await api
          .post('/payments/razorpay/create-order', { plan_id })
          .then(r => r.data)
        await loadRazorpayScript()
        return new Promise<void>((resolve, reject) => {
          const rzp = new window.Razorpay({
            key: order.key_id,
            amount: order.amount,
            currency: 'INR',
            order_id: order.order_id,
            name: 'JobAgent AI',
            description: plan_id,
            handler: async (response: Record<string, string>) => {
              try {
                const result = await api
                  .post('/payments/razorpay/verify', { ...response, plan_id })
                  .then(r => r.data)
                toast({ title: '✅ Payment successful!', description: result.message })
                qc.invalidateQueries({ queryKey: ['quota'] })
                resolve()
              } catch (e) { reject(e) }
            },
            prefill: { email: user?.email, name: user?.name },
            theme: { color: '#6366f1' },
          })
          rzp.open()
        })
      } else {
        // ── Stripe hosted checkout (redirect) ──
        const origin = window.location.origin
        const { data } = await api.post('/payments/stripe/create-session', {
          plan_id,
          success_url: `${origin}/settings/billing?payment=success`,
          cancel_url:  `${origin}/settings/billing?payment=cancelled`,
        })
        window.location.href = data.url
      }
    },
    onError: () => {
      toast({ title: 'Payment failed', description: 'Please try again.', variant: 'error' })
    },
  })

  const isPro = user?.plan === 'pro'
  const tokenBalance = quota?.ai_tokens_balance ?? 0
  const tokenLimit   = quota?.ai_tokens_monthly_limit ?? 50
  const creditBalance = quota?.apply_credits_balance ?? 0
  const creditLimit   = quota?.apply_credits_daily_limit ?? 20
  const unlimitedCredits = creditLimit >= 999999

  const proPlans = (plans as any[]).filter(p => p.plan === 'pro')

  return (
    <div className="max-w-3xl space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">Billing &amp; Credits</h1>
        <p className="text-muted-foreground mt-1">
          Current plan:{' '}
          <span className={`font-semibold capitalize ${isPro ? 'text-indigo-500' : ''}`}>
            {user?.plan || 'free'}
          </span>
          {isPro && <Crown className="inline h-4 w-4 ml-1 mb-0.5 text-amber-500" />}
        </p>
      </div>

      {/* Live balances */}
      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2 text-purple-600">
              <Zap className="h-4 w-4" /> AI Tokens
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loadingQuota ? <Skeleton className="h-10 w-24" /> : (
              <>
                <p className="text-3xl font-bold">{tokenBalance}</p>
                <p className="text-xs text-muted-foreground mb-2">of {tokenLimit} / month</p>
                <Progress value={Math.min(100, Math.round((tokenBalance / tokenLimit) * 100))} className="h-1.5" />
                {quota?.tokens_reset_at && (
                  <p className="text-xs text-muted-foreground mt-1">
                    Resets {new Date(quota.tokens_reset_at).toLocaleDateString()}
                  </p>
                )}
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2 text-amber-600">
              <Coins className="h-4 w-4" /> Apply Credits
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loadingQuota ? <Skeleton className="h-10 w-24" /> : (
              <>
                <p className="text-3xl font-bold">{unlimitedCredits ? '∞' : creditBalance}</p>
                <p className="text-xs text-muted-foreground mb-2">
                  {unlimitedCredits ? 'Unlimited (Pro)' : `of ${creditLimit} / 48h`}
                </p>
                <Progress
                  value={unlimitedCredits ? 100 : Math.min(100, Math.round((creditBalance / creditLimit) * 100))}
                  className="h-1.5"
                />
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Gateway selector */}
      <div className="flex items-center gap-3">
        <p className="text-sm font-medium text-muted-foreground">Pay with:</p>
        <div className="flex rounded-lg border border-border overflow-hidden">
          <button
            onClick={() => setGateway('razorpay')}
            disabled={!razorpayAvailable}
            className={`px-4 py-2 text-sm flex items-center gap-2 transition-colors ${
              gateway === 'razorpay'
                ? 'bg-primary text-primary-foreground'
                : 'hover:bg-muted disabled:opacity-40'
            }`}
          >
            <CreditCard className="w-4 h-4" />
            Razorpay <span className="text-xs opacity-70">(₹ INR)</span>
          </button>
          <button
            onClick={() => setGateway('stripe')}
            disabled={!stripeAvailable}
            className={`px-4 py-2 text-sm flex items-center gap-2 transition-colors border-l border-border ${
              gateway === 'stripe'
                ? 'bg-primary text-primary-foreground'
                : 'hover:bg-muted disabled:opacity-40'
            }`}
          >
            <Globe className="w-4 h-4" />
            Stripe <span className="text-xs opacity-70">($ USD)</span>
          </button>
        </div>
        {!razorpayAvailable && !stripeAvailable && (
          <p className="text-xs text-amber-500">Payments not configured yet</p>
        )}
      </div>

      {/* Plan cards */}
      {loadingPlans ? (
        <div className="grid md:grid-cols-2 gap-4">
          {[1, 2].map(i => <Skeleton key={i} className="h-80" />)}
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {/* Free */}
          <Card className={!isPro ? 'border-indigo-400 ring-1 ring-indigo-300' : ''}>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg">Free</CardTitle>
                {!isPro && <Badge variant="outline">Current plan</Badge>}
              </div>
              <p className="text-2xl font-bold mt-1">
                {gateway === 'razorpay' ? '₹0' : '$0'}
                <span className="text-sm font-normal text-muted-foreground"> / forever</span>
              </p>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2">
                {FREE_FEATURES.map(f => (
                  <li key={f.label} className="flex items-start gap-2 text-sm">
                    <span className={f.included ? 'text-green-500 font-bold' : 'text-muted-foreground/40'}>
                      {f.included ? '✓' : '✗'}
                    </span>
                    <span className={f.included ? '' : 'text-muted-foreground/60'}>{f.label}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          {/* Pro */}
          <Card className="border-indigo-500 shadow-lg">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg flex items-center gap-2">
                  Pro <Sparkles className="h-4 w-4 text-amber-500" />
                </CardTitle>
                <Badge className="bg-indigo-600 text-white">Most popular</Badge>
              </div>
              <div className="space-y-2 mt-2">
                {proPlans.length > 0 ? proPlans.map((p: any) => (
                  <div key={p.id} className="flex items-center justify-between">
                    <span className="text-xl font-bold">
                      {formatPrice(p, gateway)}
                      <span className="text-sm font-normal text-muted-foreground"> / {p.period}</span>
                    </span>
                    <Button
                      size="sm"
                      onClick={() => purchase.mutate(p.id)}
                      disabled={isPro || purchase.isPending || (!razorpayAvailable && !stripeAvailable)}
                      className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs"
                    >
                      {isPro ? 'Active' : `Get ${p.period === 'month' ? 'Monthly' : 'Annual'}`}
                    </Button>
                  </div>
                )) : (
                  <div className="flex items-center justify-between">
                    <span className="text-xl font-bold">
                      {gateway === 'razorpay' ? '₹499' : '$9.99'}
                      <span className="text-sm font-normal text-muted-foreground"> / month</span>
                    </span>
                    <Button size="sm" disabled className="text-xs bg-indigo-600 text-white">
                      {isPro ? 'Active' : 'Upgrade'}
                    </Button>
                  </div>
                )}
              </div>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2">
                {PRO_FEATURES.map(f => (
                  <li key={f.label} className="flex items-start gap-2 text-sm">
                    <Check className="h-4 w-4 text-green-500 shrink-0 mt-0.5" />
                    {f.label}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Add-on packs */}
      <div>
        <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
          <CreditCard className="h-5 w-5 text-muted-foreground" /> Add-ons &amp; Packs
        </h2>
        <p className="text-sm text-muted-foreground mb-4">
          Top up credits or AI tokens any time — no subscription needed, packs never expire.
        </p>
        <div className="grid md:grid-cols-3 gap-3">
          {ADD_ONS.map(addon => {
            const plan = (plans as any[]).find(p => p.id === addon.id)
            const price = plan ? formatPrice(plan, gateway) : '—'
            return (
              <Card key={addon.id} className={`${addon.bg} border`}>
                <CardContent className="pt-4 pb-4">
                  <div className="flex items-start justify-between mb-2">
                    <addon.icon className={`h-5 w-5 ${addon.color}`} />
                    {'badge' in addon && addon.badge && (
                      <Badge variant="outline" className="text-xs">{addon.badge}</Badge>
                    )}
                  </div>
                  <p className="font-semibold text-sm">{addon.label}</p>
                  <p className="text-xs text-muted-foreground mb-3">{addon.description}</p>
                  <Button
                    size="sm" variant="outline" className="w-full text-sm"
                    onClick={() => purchase.mutate(addon.id)}
                    disabled={purchase.isPending || (!razorpayAvailable && !stripeAvailable)}
                  >
                    Buy — {price}
                  </Button>
                </CardContent>
              </Card>
            )
          })}
        </div>
      </div>

      {/* How it works */}
      <Card>
        <CardContent className="pt-5 pb-5">
          <p className="text-sm font-semibold mb-2">How the credit system works</p>
          <ul className="text-sm text-muted-foreground space-y-1.5">
            <li>
              <span className="font-medium text-purple-600">AI Tokens</span> — consumed by Gemini calls:
              cover letter (~5 tokens), form-fill (~2/field), vision (~3 tokens). Resets monthly.
            </li>
            <li>
              <span className="font-medium text-amber-600">Apply Credits</span> — 1 credit per application.
              Free: 20 per 48h. Pro: unlimited. Bought packs never expire.
            </li>
            <li>
              <span className="font-medium">Gateway</span> — Razorpay for INR payments (India).
              Stripe for USD / international cards.
            </li>
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}
