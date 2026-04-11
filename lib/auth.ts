import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export type User = {
  id: string
  email: string
  name: string
  plan: 'free' | 'pro' | 'team'
  is_admin: boolean
}

type AuthStore = {
  token: string | null
  refresh_token: string | null
  user: User | null
  _hasHydrated: boolean
  setHasHydrated: (v: boolean) => void
  setAuth: (token: string, refresh: string, user: User) => void
  setUser: (user: User) => void
  logout: () => void
}

export const useAuth = create<AuthStore>()(
  persist(
    (set) => ({
      token: null,
      refresh_token: null,
      user: null,
      _hasHydrated: false,
      setHasHydrated: (v) => set({ _hasHydrated: v }),
      setAuth: (token, refresh_token, user) =>
        set({ token, refresh_token, user, _hasHydrated: true }),
      setUser: (user) => set({ user }),
      logout: () =>
        set({ token: null, refresh_token: null, user: null }),
    }),
    {
      name: 'auth-store',
      storage: createJSONStorage(() => localStorage),
      // Only persist these fields — _hasHydrated is always recomputed client-side
      partialize: (s) => ({
        token: s.token,
        refresh_token: s.refresh_token,
        user: s.user,
      }),
      onRehydrateStorage: () => (state) => {
        // Called after localStorage is read — mark as hydrated regardless of outcome
        if (state) state.setHasHydrated(true)
      },
    }
  )
)
