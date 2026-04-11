'use client'
import { useEffect, useRef, useState } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  LayoutDashboard, FileText, Sparkles, BarChart3, Settings, Shield,
  LogOut, PenTool, ChevronLeft, ChevronRight, Mail, Menu, X,
  User as UserIcon, Zap, Key, Briefcase, ShieldCheck
} from 'lucide-react'
import { BugReportButton } from '@/components/BugReportButton'
import { TokenBadge } from '@/components/TokenBadge'

const navItems = [
  { name: 'Command Center', href: '/dashboard', icon: BarChart3 },
  { name: 'AI Missions', href: '/automation', icon: Zap },
  { name: 'Applications', href: '/jobs', icon: Briefcase },
  { name: 'Knowledge Graph', href: '/graph', icon: Sparkles },
  { name: 'Credentials', href: '/credentials', icon: ShieldCheck },
  { name: 'Settings', href: '/settings', icon: Settings },
]

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const { user, token, logout, _hasHydrated } = useAuth()
  const redirecting = useRef(false)
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    if (!_hasHydrated) return
    if (!token && !redirecting.current) {
      redirecting.current = true
      router.replace('/login')
    }
    if (token) {
      redirecting.current = false
    }
  }, [_hasHydrated, token, router])

  // Close mobile menu on route change
  useEffect(() => {
    setMobileOpen(false)
  }, [pathname])

  if (!_hasHydrated || !token) {
    return (
      <div className="flex h-screen items-center justify-center" style={{ background: 'hsl(var(--color-surface))' }}>
        <div className="flex flex-col items-center gap-4">
          <div className="relative h-10 w-10">
            <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-[hsl(var(--color-accent))] animate-spin" />
            <div className="absolute inset-1 rounded-full border-2 border-transparent border-b-[hsl(var(--color-brand))] animate-spin" style={{ animationDirection: 'reverse', animationDuration: '0.8s' }} />
          </div>
          <p className="text-sm text-muted-foreground animate-pulse-subtle">Loading...</p>
        </div>
      </div>
    )
  }

  function handleLogout() {
    logout()
    router.replace('/login')
  }

  const isActive = (href: string) => pathname === href || pathname.startsWith(href + '/')

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'hsl(var(--color-surface))' }}>
      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/40 backdrop-blur-sm z-40 lg:hidden animate-fade-in"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed lg:relative z-50 h-full flex flex-col shrink-0
          bg-white dark:bg-[hsl(234,28%,12%)] border-r border-border
          transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]
          ${collapsed ? 'w-[72px]' : 'w-64'}
          ${mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
        `}
      >
        {/* Logo */}
        <div className={`flex items-center border-b border-border h-16 shrink-0 ${collapsed ? 'justify-center px-2' : 'px-5'}`}>
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-[hsl(var(--color-accent))] to-[hsl(var(--color-brand))] flex items-center justify-center shrink-0">
              <Zap className="h-4 w-4 text-white" />
            </div>
            {!collapsed && (
              <span className="font-display text-xl font-bold tracking-tight">Job<span className="text-[hsl(var(--color-accent))] font-black tracking-widest">AGENT</span></span>
            )}
          </div>
          {/* Mobile close */}
          <button
            className="lg:hidden ml-auto p-1 rounded-md hover:bg-muted"
            onClick={() => setMobileOpen(false)}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
          {navItems.map((item) => {
            const Icon = item.icon
            return (
              <Link key={item.href} href={item.href}>
                <div
                  className={`
                    group flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium
                    transition-all duration-200
                    ${isActive(item.href)
                      ? 'bg-gradient-to-r from-[hsl(var(--color-accent))] to-[hsl(var(--color-accent-hover))] text-white shadow-sm'
                      : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                    }
                    ${collapsed ? 'justify-center' : ''}
                  `}
                  title={collapsed ? item.name : undefined}
                >
                  <Icon className={`h-[18px] w-[18px] shrink-0 ${isActive(item.href) ? '' : 'group-hover:scale-110'} transition-transform`} />
                  {!collapsed && (
                    <>
                      <span>{item.name}</span>
                    </>
                  )}
                </div>
              </Link>
            )
          })}

          {/* Admin link */}
          {user?.is_admin && (
            <>
              <div className="my-3 border-t border-border" />
              <Link href="/admin">
                <div
                  className={`
                    group flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium
                    transition-all duration-200
                    ${isActive('/admin')
                      ? 'bg-gradient-to-r from-[hsl(var(--color-brand))] to-[hsl(var(--color-brand-light))] text-white shadow-sm'
                      : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                    }
                    ${collapsed ? 'justify-center' : ''}
                  `}
                  title={collapsed ? 'Admin' : undefined}
                >
                  <Shield className="h-[18px] w-[18px] shrink-0" />
                  {!collapsed && <span>Admin Panel</span>}
                </div>
              </Link>
            </>
          )}
        </nav>

        {/* Collapse toggle (desktop) */}
        <div className="hidden lg:flex justify-center py-2 border-t border-border">
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
          >
            {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          </button>
        </div>

        {/* User area */}
        <div className={`border-t border-border p-3 space-y-2 ${collapsed ? 'px-2' : ''}`}>
          <div className={`flex items-center ${collapsed ? 'justify-center' : 'gap-3'}`}>
            <div className="h-9 w-9 rounded-full bg-gradient-to-br from-[hsl(var(--color-accent))] to-[hsl(var(--color-brand))] flex items-center justify-center text-sm font-semibold text-white shrink-0 shadow-sm">
              {user?.name?.[0]?.toUpperCase() || 'U'}
            </div>
            {!collapsed && (
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{user?.name}</p>
                <div className="flex items-center gap-1.5">
                  <Badge
                    variant={user?.plan === 'pro' ? 'default' : 'secondary'}
                    className={`text-[10px] px-1.5 py-0 ${
                      user?.plan === 'pro'
                        ? 'bg-gradient-to-r from-amber-500 to-orange-500 text-white border-0'
                        : ''
                    }`}
                  >
                    {user?.plan?.toUpperCase() || 'FREE'}
                  </Badge>
                </div>
              </div>
            )}
          </div>
          {!collapsed && (
            <Button
              variant="ghost"
              size="sm"
              className="w-full justify-start gap-2 text-muted-foreground hover:text-[hsl(var(--color-error))] hover:bg-error-light transition-colors"
              onClick={handleLogout}
            >
              <LogOut className="h-4 w-4" />
              Logout
            </Button>
          )}
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar (mobile) */}
        <header className="lg:hidden flex items-center gap-3 h-14 px-4 border-b border-border bg-white dark:bg-[hsl(234,28%,12%)] shrink-0">
          <button
            onClick={() => setMobileOpen(true)}
            className="p-2 -ml-2 rounded-lg hover:bg-muted transition-colors"
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="flex items-center gap-2">
            <div className="h-7 w-7 rounded-md bg-gradient-to-br from-[hsl(var(--color-accent))] to-[hsl(var(--color-brand))] flex items-center justify-center">
              <Zap className="h-3.5 w-3.5 text-white" />
            </div>
            <span className="font-display text-base font-bold">JobAgent</span>
          </div>
        </header>

        {/* Top bar desktop — shows token/credit balance */}
        <div className="hidden lg:flex items-center justify-end gap-3 h-12 px-6 border-b border-border bg-white/60 dark:bg-[hsl(234,28%,12%)]/60 backdrop-blur-sm shrink-0">
          <TokenBadge />
        </div>

        {/* Page content */}
        <main className="flex-1 overflow-auto">
          <div className="page-enter p-4 sm:p-6 lg:p-8 max-w-[1600px] mx-auto">
            {children}
          </div>
        </main>
      </div>

      {/* Global bug-report button + self-learn dialog (every authenticated page) */}
      <BugReportButton />
    </div>
  )
}
