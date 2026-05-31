'use client'
import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import {
  BarChart3, TrendingUp, Target, CheckCircle2,
  Briefcase, Calendar, ArrowUpRight, Loader2
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell
} from 'recharts'

interface Analytics {
  total: number
  total_applied: number
  this_week: number
  this_month: number
  by_status: Record<string, number>
  by_platform: Record<string, number>
  response_rate: number
  top_companies: string[]
  avg_match_score: number | null
  daily_applies: { date: string; count: number }[]
}

const STATUS_COLORS: Record<string, string> = {
  applied: '#3B82F6',
  shortlisted: '#10B981',
  interview: '#8B5CF6',
  rejected: '#EF4444',
  offered: '#F59E0B',
}

const PLATFORM_COLORS = ['#0077B5', '#4285F4', '#FF5733', '#000000', '#6366F1']

export default function AnalyticsPage() {
  const { data: analytics, isLoading } = useQuery<Analytics>({
    queryKey: ['job-analytics'],
    queryFn: async () => {
      const { data } = await api.get('/jobs/analytics', { silent: true })
      return data
    },
    retry: false,
  })

  const statusData = analytics?.by_status
    ? Object.entries(analytics.by_status).map(([name, value]) => ({ name, value }))
    : []

  const platformData = analytics?.by_platform
    ? Object.entries(analytics.by_platform).map(([name, value]) => ({ name, value }))
    : []

  const dailyData = analytics?.daily_applies || []

  const metrics = [
    {
      label: 'Total Applications',
      value: analytics?.total ?? '—',
      icon: Briefcase,
      gradient: 'from-[hsl(var(--color-accent))] to-[hsl(var(--color-accent-hover))]',
    },
    {
      label: 'Shortlisted',
      value: analytics?.by_status?.shortlisted ?? 0,
      icon: CheckCircle2,
      gradient: 'from-emerald-500 to-teal-500',
    },
    {
      label: 'Interviews',
      value: analytics?.by_status?.interview ?? 0,
      icon: Target,
      gradient: 'from-violet-500 to-purple-500',
    },
    {
      label: 'Success Rate',
      value: analytics?.total
        ? `${Math.round(((analytics.by_status?.shortlisted || 0) + (analytics.by_status?.interview || 0) + (analytics.by_status?.offered || 0)) / analytics.total * 100)}%`
        : '—',
      icon: TrendingUp,
      gradient: 'from-amber-500 to-orange-500',
    },
  ]

  return (
    <div className="page-enter space-y-8">
      <div>
        <h1 className="font-display text-2xl font-bold tracking-tight">Analytics</h1>
        <p className="text-[hsl(var(--muted-foreground))] mt-1">
          Track your job application performance and trends.
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {metrics.map(({ label, value, icon: Icon, gradient }) => (
          <div
            key={label}
            className="rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-5 hover-lift"
          >
            <div className={`inline-flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br ${gradient} mb-3`}>
              <Icon className="h-4 w-4 text-white" />
            </div>
            <p className="font-display text-2xl font-bold">
              {isLoading ? <span className="skeleton inline-block w-12 h-7" /> : value}
            </p>
            <p className="text-xs text-[hsl(var(--muted-foreground))] mt-0.5">{label}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Daily Applications Chart */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Calendar className="h-4 w-4 text-[hsl(var(--color-accent))]" />
              Daily Applications (Last 7 Days)
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-64 flex items-center justify-center">
                <Loader2 className="h-6 w-6 animate-spin text-[hsl(var(--muted-foreground))]" />
              </div>
            ) : dailyData.length === 0 ? (
              <div className="h-64 flex items-center justify-center border border-dashed border-[hsl(var(--border))] rounded-lg">
                <div className="text-center">
                  <BarChart3 className="h-10 w-10 text-[hsl(var(--muted-foreground))]/30 mx-auto mb-3" />
                  <p className="text-sm text-[hsl(var(--muted-foreground))]">No data yet. Start applying to see trends.</p>
                </div>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={264}>
                <BarChart data={dailyData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="date" fontSize={11} tick={{ fill: 'hsl(var(--muted-foreground))' }} />
                  <YAxis fontSize={11} tick={{ fill: 'hsl(var(--muted-foreground))' }} />
                  <Tooltip
                    contentStyle={{
                      background: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                  />
                  <Bar dataKey="count" fill="hsl(var(--color-accent))" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Status Breakdown */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ArrowUpRight className="h-4 w-4 text-emerald-500" />
              Status Breakdown
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-64 flex items-center justify-center">
                <Loader2 className="h-6 w-6 animate-spin text-[hsl(var(--muted-foreground))]" />
              </div>
            ) : statusData.length === 0 ? (
              <div className="h-64 flex items-center justify-center border border-dashed border-[hsl(var(--border))] rounded-lg">
                <p className="text-sm text-[hsl(var(--muted-foreground))]">No applications tracked yet.</p>
              </div>
            ) : (
              <div className="flex items-center gap-6">
                <ResponsiveContainer width="50%" height={200}>
                  <PieChart>
                    <Pie
                      data={statusData}
                      cx="50%"
                      cy="50%"
                      innerRadius={50}
                      outerRadius={80}
                      paddingAngle={3}
                      dataKey="value"
                    >
                      {statusData.map((entry, i) => (
                        <Cell key={entry.name} fill={STATUS_COLORS[entry.name] || PLATFORM_COLORS[i % PLATFORM_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
                <div className="space-y-2">
                  {statusData.map((entry) => (
                    <div key={entry.name} className="flex items-center gap-2 text-sm">
                      <div
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: STATUS_COLORS[entry.name] || '#6B7280' }}
                      />
                      <span className="capitalize text-[hsl(var(--muted-foreground))]">{entry.name}</span>
                      <span className="font-bold ml-auto">{entry.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Platform Breakdown */}
      {platformData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Applications by Platform</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-4">
              {platformData.map((entry, i) => (
                <div key={entry.name} className="flex items-center gap-3 px-4 py-3 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--color-surface-2))]">
                  <div
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: PLATFORM_COLORS[i % PLATFORM_COLORS.length] }}
                  />
                  <span className="text-sm font-medium capitalize">{entry.name}</span>
                  <span className="text-lg font-bold">{entry.value}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
