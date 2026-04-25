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

const _apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const api = axios.create({ baseURL: _apiBase })

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

// Inject stored token — but never overwrite an explicitly-set Authorization header
api.interceptors.request.use((config) => {
  if (!config.headers.Authorization) {
    const token = getStoredToken()
    if (token) config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// On 401: attempt silent token refresh once; on failure, redirect to login
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true
      const refresh = getStoredRefresh()
      if (refresh) {
        try {
          const { data } = await axios.post(`${_apiBase}/auth/refresh`, {
            refresh_token: refresh,
          })
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
          // Refresh failed — clear auth and hard-redirect to login
          localStorage.removeItem('auth-store')
          window.location.href = '/login'
          return Promise.reject(error)
        }
      }
      // No refresh token — go to login
      localStorage.removeItem('auth-store')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// Global error toast for non-401 errors.
// Callers can opt out by passing `{ silent: true }` in the axios config — useful
// for background queries (graph, analytics) that fail gracefully on empty data.
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
