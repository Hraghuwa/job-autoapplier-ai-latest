'use client'
import { useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import api from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useRouter } from 'next/navigation'
import { Shield, Users, TrendingUp, Activity } from 'lucide-react'

export default function AdminPage() {
  const { user, _hasHydrated } = useAuth()
  const router = useRouter()
  const qc = useQueryClient()

  useEffect(() => {
    document.title = 'JobAgent Admin Console'
    if (_hasHydrated && user && !user.is_admin) router.replace('/dashboard')
  }, [user, _hasHydrated, router])

  const { data: revenue } = useQuery({
    queryKey: ['admin-revenue'],
    queryFn: () => api.get('/admin/revenue', { silent: true }).then((r) => r.data),
    enabled: !!user?.is_admin,
    retry: false,
  })

  const { data: users = [] } = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => api.get('/admin/users', { silent: true }).then((r) => r.data),
    enabled: !!user?.is_admin,
    retry: false,
  })

  const { data: activeAgents = [] } = useQuery({
    queryKey: ['admin-agents'],
    queryFn: () => api.get('/admin/agents/active', { silent: true }).then((r) => r.data),
    enabled: !!user?.is_admin,
    refetchInterval: 10000,
    retry: false,
  })

  const { data: health } = useQuery({
    queryKey: ['admin-health'],
    queryFn: () => api.get('/admin/platform-health', { silent: true }).then((r) => r.data),
    enabled: !!user?.is_admin,
    retry: false,
  })

  const overridePlan = useMutation({
    mutationFn: ({ id, plan }: { id: string; plan: string }) =>
      api.patch(`/admin/users/${id}/plan`, { plan }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }),
  })

  // Show spinner until hydrated; if not admin, effect above redirects
  if (!_hasHydrated || !user) {
    return (
      <div className="flex h-full items-center justify-center py-20">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    )
  }
  if (!user.is_admin) return null

  const revenueStats = [
    { icon: TrendingUp, label: 'Total Revenue', value: `₹${revenue?.total_revenue_inr || 0}` },
    { icon: TrendingUp, label: 'MRR', value: `₹${revenue?.mrr_inr || 0}` },
    { icon: Users, label: 'Pro Users', value: revenue?.pro_users || 0 },
    { icon: Users, label: 'Total Users', value: revenue?.total_users || 0 },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Shield className="h-6 w-6 text-[hsl(var(--color-accent))]" />
        <h1 className="text-2xl font-bold">JobAgent <span className="text-muted-foreground font-medium">Admin Console</span></h1>
      </div>

      {/* Revenue stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {revenueStats.map(({ icon: Icon, label, value }) => (
          <Card key={label}>
            <CardContent className="pt-6 flex items-start gap-3">
              <Icon className="h-5 w-5 text-blue-600 mt-0.5 shrink-0" />
              <div>
                <p className="text-sm text-slate-500">{label}</p>
                <p className="text-2xl font-bold">{value}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Active agents */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Active Agents ({(activeAgents as any[]).length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {(activeAgents as any[]).length === 0 ? (
            <p className="text-sm text-slate-500">No active agents running.</p>
          ) : (
            <div className="space-y-2">
              {(activeAgents as any[]).map((r) => (
                <div
                  key={r.run_id}
                  className="flex justify-between py-2 border-b last:border-0 text-sm"
                >
                  <span className="font-mono text-xs text-slate-500">
                    {String(r.run_id).slice(0, 8)}
                  </span>
                  <span>
                    Phase {r.phase} · {String(r.user_id).slice(0, 8)}
                  </span>
                  <Badge>running</Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Platform health */}
      {health && (
        <Card>
          <CardHeader>
            <CardTitle>Platform Health</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {Object.entries(health as Record<string, any>).map(([platform, stats]) => (
                <div key={platform} className="flex items-center justify-between py-1">
                  <span className="capitalize font-medium">{platform}</span>
                  <div className="flex items-center gap-3 text-sm text-slate-600">
                    <span>✅ {stats.completed}</span>
                    <span>❌ {stats.failed}</span>
                    <Badge
                      variant={stats.success_rate > 80 ? 'default' : 'destructive'}
                    >
                      {stats.success_rate}%
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* User management */}
      <Card>
        <CardHeader>
          <CardTitle>Users ({(users as any[]).length})</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-1">
            {(users as any[]).map((u) => (
              <div
                key={u.id}
                className="flex items-center justify-between py-3 border-b last:border-0"
              >
                <div>
                  <p className="font-medium text-sm">{u.name}</p>
                  <p className="text-xs text-slate-500">{u.email}</p>
                </div>
                <div className="flex items-center gap-2">
                  {u.is_admin && <Badge variant="secondary">Admin</Badge>}
                  <Select
                    value={u.plan}
                    onValueChange={(plan) =>
                      plan && overridePlan.mutate({ id: u.id, plan })
                    }
                  >
                    <SelectTrigger className="w-24 h-7 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="free">Free</SelectItem>
                      <SelectItem value="pro">Pro</SelectItem>
                      <SelectItem value="team">Team</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
