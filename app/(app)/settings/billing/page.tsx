'use client'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Progress } from '@/components/ui/progress'
import api from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { Check, Zap, CreditCard, Coins, Crown, Sparkles } from 'lucide-react'
import { useToast } from '@/lib/use-toast'

declare global {
  interface Window {
    Razorpay: new (opts: Record<string, unknown>) => { open(): void }
  }
}

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
  { label: '2 000 AI tokens / month', included: true },
  { label: 'Web search — 30+ job boards', included: true },
  { label: 'AI cover letter generation', included: true },
  { label: 'Scheduled auto-runs', included: true },
  { label: 'Full analytics dashboard', included: true },
  { label: '10 interview prep questions', included: true },
  { label: 'Priority support', included: true },
]

const ADD_ONS = [
  {
    id: 'credits_100',
    icon: Coins,
    label: '100 Apply Credits',
    fallbackPrice: '₹199',
    description: 'Extra apply credits, no expiry',
    color: 'text-amber-600',
    bg: 'bg-amber-50 border-amber-200',
  },
  {
    id: 'credits_500',
    icon: Coins,
    label: '500 Apply Credits',
    fallbackPrice: '₹799',
    description: 'Bulk credits — best per-credit value',
    color: 'text-amber-600',
    bg: 'bg-amber-50 border-amber-200',
    badge: 'Best Value',
  },
  {
    id: 'tokens_500',
    icon: Zap,
    label: '500 AI Tokens',
    fallbackPrice: '₹299',
    description: 'Top up AI tokens for form fill & cover letters',
    color: 'text-purple-600',
    bg: 'bg-purple-50 border-purple-200',
  },
]

function loadRazorpayScript(): Promise<void> {
  return new Promise((resolve) => {
    if (typeof window !== 'undefined' && window.Razorpay) { resolve(); return }
    const script = document.createElement('script')
    script.src = 'https://checkout.razorpay.com/v1/checkout.js'
    script.onload = () => resolve()
    document.body.appendChild(script)
  })
}

export default function BillingPage() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const { toast } = useToast()

  const { data: quota, isLoading: loadingQuota } = useQuery({
    queryKey: ['quota'],
    queryFn: () => api.get('/users/quota', { silent: true } as any).then((r) => r.data),
    retry: false,
  })

  const { data: plans = [], isLoading: loadingPlans } = useQuery({
    queryKey: ['plans'],
    queryFn: () => api.get('/payments/plans', { silent: true } as any).then((r) => r.data),
    retry: false,
  })

  const purchase = useMutation({
    mutationFn: async (plan_id: string) => {
      const order = await api.post('/payments/create-order', { plan_id }).then((r) => r.data)
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
                .post('/payments/verify', { ...response, plan_id })
                .then((r) => r.data)
              toast({ title: 'Payment successful!', description: result.message })
              qc.invalidateQueries({ queryKey: ['quota'] })
              resolve()
            } catch (e) {
              reject(e)
            }
          },
          prefill: { email: user?.email, name: user?.name },
          theme: { color: '#6366f1' },
        })
        rzp.open()
      })
    },
    onError: () => {
      toast({ title: 'Payment failed', description: 'Please try again.', variant: 'error' })
    },
  })

  const isPro = user?.plan === 'pro'
  const tokenLimit = quota?.ai_tokens_monthly_limit ?? 50
  const tokenBalance = quota?.ai_tokens_balance ?? 0
  const creditLimit = quota?.apply_credits_daily_limit ?? 20
  const creditBalance = quota?.apply_credits_balance ?? 0
  const unlimitedCredits = creditLimit >= 999999

  const tokenPct = Math.min(100, Math.round((tokenBalance / tokenLimit) * 100))
  const creditPct = unlimitedCredits ? 100 : Math.min(100, Math.round((creditBalance / creditLimit) * 100))

  const proPlans = (plans as any[]).filter((p) => p.plan === 'pro')

  return (
    <div className="max-w-3xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Billing &amp; Credits</h1>
        <p className="text-slate-500 mt-1">
          Current plan:{' '}
          <span className={`font-semibold capitalize ${isPro ? 'text-indigo-600' : ''}`}>
            {user?.plan || 'free'}
          </span>
          {isPro && <Crown className="inline h-4 w-4 ml-1 mb-0.5 text-amber-500" />}
        </p>
      </div>

      {/* Live balance */}
      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2 text-purple-700">
              <Zap className="h-4 w-4" /> AI Tokens
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loadingQuota ? (
              <Skeleton className="h-10 w-24" />
            ) : (
              <>
                <p className="text-3xl font-bold">{tokenBalance}</p>
                <p className="text-xs text-slate-500 mb-2">of {tokenLimit} / month</p>
                <Progress value={tokenPct} className="h-1.5" />
                {quota?.tokens_reset_at && (
                  <p className="text-xs text-slate-400 mt-1">
                    Resets {new Date(quota.tokens_reset_at).toLocaleDateString()}
                  </p>
                )}
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2 text-amber-700">
              <Coins className="h-4 w-4" /> Apply Credits
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loadingQuota ? (
              <Skeleton className="h-10 w-24" />
            ) : (
              <>
                <p className="text-3xl font-bold">
                  {unlimitedCredits ? '∞' : creditBalance}
                </p>
                <p className="text-xs text-slate-500 mb-2">
                  {unlimitedCredits ? 'Unlimited (Pro)' : `of ${creditLimit} / 48h`}
                </p>
                <Progress value={creditPct} className="h-1.5" />
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Plan cards */}
      {loadingPlans ? (
        <div className="grid md:grid-cols-2 gap-4">
          {[1, 2].map((i) => <Skeleton key={i} className="h-80" />)}
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {/* Free */}
          <Card className={!isPro ? 'border-indigo-300 ring-1 ring-indigo-200' : ''}>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg">Free</CardTitle>
                {!isPro && <Badge variant="outline">Current plan</Badge>}
              </div>
              <p className="text-2xl font-bold mt-1">
                &#8377;0
                <span className="text-sm font-normal text-slate-500"> / forever</span>
              </p>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2">
                {FREE_FEATURES.map((f) => (
                  <li key={f.label} className="flex items-start gap-2 text-sm">
                    <span className={f.included ? 'text-green-500 font-bold' : 'text-slate-300'}>
                      {f.included ? '✓' : '✗'}
                    </span>
                    <span className={f.included ? '' : 'text-slate-400'}>{f.label}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          {/* Pro */}
          <Card className="border-indigo-500 shadow-md">
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
                      &#8377;{Math.round(p.amount / 100)}
                      <span className="text-sm font-normal text-slate-500"> / {p.period}</span>
                    </span>
                    <Button
                      size="sm"
                      onClick={() => purchase.mutate(p.id)}
                      disabled={isPro || purchase.isPending}
                      className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs"
                    >
                      {isPro ? 'Active' : `Get ${p.period === 'month' ? 'Monthly' : 'Annual'}`}
                    </Button>
                  </div>
                )) : (
                  <div className="flex items-center justify-between">
                    <span className="text-xl font-bold">
                      &#8377;499
                      <span className="text-sm font-normal text-slate-500"> / month</span>
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
                {PRO_FEATURES.map((f) => (
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
          <CreditCard className="h-5 w-5 text-slate-500" /> Add-ons &amp; Packs
        </h2>
        <p className="text-sm text-slate-500 mb-4">
          Top up credits or AI tokens any time — no subscription needed, packs never expire.
        </p>
        <div className="grid md:grid-cols-3 gap-3">
          {ADD_ONS.map((addon) => {
            const plan = (plans as any[]).find((p) => p.id === addon.id)
            const price = plan
              ? `\u20b9${Math.round(plan.amount / 100)}`
              : addon.fallbackPrice
            return (
              <Card key={addon.id} className={`${addon.bg} border`}>
                <CardContent className="pt-4 pb-4">
                  <div className="flex items-start justify-between mb-2">
                    <addon.icon className={`h-5 w-5 ${addon.color}`} />
                    {addon.badge && (
                      <Badge variant="outline" className="text-xs">{addon.badge}</Badge>
                    )}
                  </div>
                  <p className="font-semibold text-sm">{addon.label}</p>
                  <p className="text-xs text-slate-500 mb-3">{addon.description}</p>
                  <Button
                    size="sm"
                    variant="outline"
                    className="w-full text-sm"
                    onClick={() => purchase.mutate(addon.id)}
                    disabled={purchase.isPending}
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
      <Card className="bg-slate-50 border-slate-200">
        <CardContent className="pt-5 pb-5">
          <p className="text-sm font-semibold mb-2">How the credit system works</p>
          <ul className="text-sm text-slate-600 space-y-1.5">
            <li>
              <span className="font-medium text-purple-700">AI Tokens</span> — consumed by
              Gemini calls: cover letter generation (~5 tokens), form-fill AI (~2 tokens/field),
              vision analysis (~3 tokens). Resets monthly.
            </li>
            <li>
              <span className="font-medium text-amber-700">Apply Credits</span> — 1 credit per
              job application. Free plan: 20 per 48 h. Pro: unlimited. Bought packs never expire.
            </li>
            <li>
              <span className="font-medium">Token packs</span> stack on top of your monthly
              allocation and carry over to next month.
            </li>
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}
