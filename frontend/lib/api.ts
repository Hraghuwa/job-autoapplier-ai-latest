import axios from 'axios'
import { toast } from '@/lib/use-toast'

// Extend axios request config with a `silent` flag so background queries
// (graph, analytics) can suppress the global error toast when they legitimately
// fail for empty users.
declare module 'axios' {
  export interface AxiosRequestConfig {
    silent?: boolean
  }
}

// ── API base URL strategy ──────────────────────────────────────────────────
//
// PRODUCTION (Vercel + Railway):
//   Do NOT set NEXT_PUBLIC_API_URL.
//   Set BACKEND_URL (private, server-only) in Vercel → the Next.js rewrite
//   proxy (next.config.mjs) forwards /api/* → BACKEND_URL/* server-side.
//   Browser only ever talks to its own origin (nutriblend.store) → no CORS.
//
// LOCAL DEV (direct backend):
//   Set NEXT_PUBLIC_API_URL=http://localhost:8000 in frontend/.env.local
//   to bypass the proxy and hit the backend directly.
//
// The trick: axios paths like `/auth/login` start with `/`, so they ignore
// a relative baseURL.  We handle the proxy case via a request interceptor
// that rewrites `/foo` → `/api/foo` when no explicit URL override is set.

const _directUrl = process.env.NEXT_PUBLIC_API_URL   // e.g. http://localhost:8000
const _proxyMode = !_directUrl                        // true in production

const api = axios.create({
  // In proxy mode baseURL is empty — interceptor prepends /api to every path.
  // In direct mode baseURL is the explicit URL and interceptor is a no-op.
  baseURL: _directUrl || '',
  timeout: 60_000,  // Railway cold-start can take 12-15s; leave generous headroom
})

// ── Proxy-path interceptor ─────────────────────────────────────────────────
// Prepend /api so requests go through the Next.js rewrite → Railway backend.
// Skip if:  already absolute URL, or NEXT_PUBLIC_API_URL is set (direct mode).
api.interceptors.request.use((config) => {
  if (_proxyMode && config.url && !config.url.startsWith('http')) {
    config.url = '/api' + (config.url.startsWith('/') ? config.url : `/${config.url}`)
  }
  return config
})

// ── Warm-up ping ───────────────────────────────────────────────────────────
// Fire a /health ping on load so the Railway instance is warm by the time
// the user clicks Sign In. Failures are silent.
if (typeof window !== 'undefined') {
  const healthUrl = _directUrl ? `${_directUrl}/health` : '/api/health'
  fetch(healthUrl, { method: 'GET', cache: 'no-store' }).catch(() => {})
}

// ── Token helpers ──────────────────────────────────────────────────────────
function getStoredToken(): string | null {
  try {
    const raw = localStorage.getItem('auth-store')
    if (!raw) return null
    // Zustand persist wraps state as { state: { token, ... }, version: 0 }
    return JSON.parse(raw)?.state?.token ?? null
  } catch {
    return null
  }
}

function getStoredRefresh(): string | null {
  try {
    const raw = localStorage.getItem('auth-store')
    if (!raw) return null
    return JSON.parse(raw)?.state?.refresh_token ?? null
  } catch {
    return null
  }
}

// ── Auth header injection ──────────────────────────────────────────────────
api.interceptors.request.use((config) => {
  if (!config.headers.Authorization) {
    const token = getStoredToken()
    if (token) config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ── 401 → silent refresh, then retry ──────────────────────────────────────
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true
      const refresh = getStoredRefresh()
      if (refresh) {
        try {
          // Refresh endpoint must also go through the proxy in proxy mode
          const refreshUrl = _proxyMode ? '/api/auth/refresh' : `${_directUrl}/auth/refresh`
          const { data } = await axios.post(refreshUrl, { refresh_token: refresh })
          // Patch the stored token (zustand persist format: { state: {...}, version: 0 })
          try {
            const raw = localStorage.getItem('auth-store')
            if (raw) {
              const stored = JSON.parse(raw)
              if (stored?.state) stored.state.token = data.access_token
              localStorage.setItem('auth-store', JSON.stringify(stored))
            }
          } catch {}
          original.headers.Authorization = `Bearer ${data.access_token}`
          return api(original)
        } catch {
          localStorage.removeItem('auth-store')
          window.location.href = '/login'
          return Promise.reject(error)
        }
      }
      localStorage.removeItem('auth-store')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// ── Global error toast for non-401 errors ─────────────────────────────────
// Callers can opt out with { silent: true } — used for background queries
// (graph, analytics) that fail gracefully on empty data.
api.interceptors.response.use(
  (res) => res,
  (error) => {
    const silent = error.config?.silent === true
    if (error.response?.status !== 401 && !silent) {
      const message = error.response?.data?.detail
        || error.response?.data?.message
        || error.message
        || 'Something went wrong'
      toast({
        title: 'Error',
        description: typeof message === 'string' ? message : JSON.stringify(message),
        variant: 'error',
      })
    }
    return Promise.reject(error)
  }
)

export default api
