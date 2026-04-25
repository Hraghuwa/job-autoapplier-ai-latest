'use client'
import { useQuery } from '@tanstack/react-query'
import Link from 'next/link'
import { Zap, Coins } from 'lucide-react'
import api from '@/lib/api'

export function TokenBadge() {
  const { data: quota } = useQuery({
    queryKey: ['quota'],
    queryFn: () => api.get('/users/quota', { silent: true } as any).then((r) => r.data),
    retry: false,
    staleTime: 60_000,
  })

  if (!quota) return null

  const unlimitedCredits = (quota.apply_credits_daily_limit ?? 0) >= 999999

  return (
    <Link href="/settings/billing" className="flex items-center gap-3 text-xs">
      <span className="flex items-center gap-1 px-2.5 py-1 rounded-full bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300 border border-purple-200 dark:border-purple-800 font-medium hover:bg-purple-100 transition-colors">
        <Zap className="h-3 w-3" />
        {quota.ai_tokens_balance} tokens
      </span>
      <span className="flex items-center gap-1 px-2.5 py-1 rounded-full bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800 font-medium hover:bg-amber-100 transition-colors">
        <Coins className="h-3 w-3" />
        {unlimitedCredits ? '∞' : quota.apply_credits_balance} credits
      </span>
    </Link>
  )
}
