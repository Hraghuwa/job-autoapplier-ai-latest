'use client'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import api from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { Check } from 'lucide-react'

declare global {
  interface Window {
    Razorpay: new (opts: Record<string, unknown>) => { open(): void }
  }
}

const PLAN_FEATURES: Record<string, string[]> = {
  pro_monthly: [
    'All platforms (LinkedIn, Wellfound, Internshala, Web)',
    'Unlimited daily applies',
    'AI match scoring',
    'Interview prep (10 questions)',
    'Priority support',
  ],
  pro_annual: [
    'Everything in Pro monthly',
    '2 months free (₹998 savings)',
    'All platforms',
    'Unlimited applies',
  ],
  credits_100: [
    '100 extra apply credits',
    'No subscription required',
    'Works with free plan',
    'Never expires',
  ],
}

export default function BillingPage() {
  const { user } = useAuth()

  const { data: plans = [], isLoading } = useQuery({
    queryKey: ['plans'],
    queryFn: () => api.get('/payments/plans').then((r) => r.data),
  })

  const createOrder = useMutation({
    mutationFn: (plan_id: string) =>
      api.post('/payments/create-order', { plan_id }).then((r) => r.data),
    onSuccess: (data) => {
      const script = document.createElement('script')
      script.src = 'https://checkout.razorpay.com/v1/checkout.js'
      script.onload = () => {
        const rzp = new window.Razorpay({
          key: data.key_id,
          amount: data.amount,
          currency: data.currency,
          order_id: data.order_id,
          name: 'JobAgent',
          description: data.plan_id,
          handler: async (response: Record<string, string>) => {
            await api.post('/payments/verify', { ...response, plan_id: data.plan_id })
            window.location.reload()
          },
          prefill: { email: user?.email, name: user?.name },
        })
        rzp.open()
      }
      document.body.appendChild(script)
    },
  })

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Billing</h1>
        <p className="text-slate-500">
          Current plan:{' '}
          <strong className="capitalize">{user?.plan || 'free'}</strong>
        </p>
      </div>

      {isLoading ? (
        <div className="grid md:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-64" />)}
        </div>
      ) : (
        <div className="grid md:grid-cols-3 gap-4">
          {(plans as any[]).map((plan) => {
            const isPopular = plan.id === 'pro_monthly'
            const isCurrent = user?.plan === plan.plan
            const features = PLAN_FEATURES[plan.id] || []
            return (
              <Card
                key={plan.id}
                className={isPopular ? 'border-blue-500 shadow-md' : ''}
              >
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-lg">{plan.name}</CardTitle>
                    {isPopular && <Badge>Popular</Badge>}
                  </div>
                  <p className="text-2xl font-bold mt-1">
                    ₹{Math.round(plan.amount / 100)}
                    <span className="text-sm font-normal text-slate-500">
                      /{plan.period}
                    </span>
                  </p>
                </CardHeader>
                <CardContent className="space-y-4">
                  <ul className="space-y-2">
                    {features.map((f) => (
                      <li key={f} className="flex items-start gap-2 text-sm">
                        <Check className="h-4 w-4 text-green-500 shrink-0 mt-0.5" />
                        {f}
                      </li>
                    ))}
                  </ul>
                  <Button
                    className="w-full"
                    variant={isPopular ? 'default' : 'outline'}
                    onClick={() => createOrder.mutate(plan.id)}
                    disabled={isCurrent || createOrder.isPending}
                  >
                    {isCurrent ? 'Current Plan' : `Upgrade — ₹${Math.round(plan.amount / 100)}`}
                  </Button>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      {/* Free plan features */}
      <Card className="bg-slate-50">
        <CardContent className="pt-6">
          <p className="text-sm font-medium text-slate-700 mb-2">Free plan includes:</p>
          <ul className="text-sm text-slate-600 space-y-1">
            <li>• LinkedIn only</li>
            <li>• 20 applies per 48 hours</li>
            <li>• Basic job tracking</li>
            <li>• 3 interview prep questions per job</li>
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}
