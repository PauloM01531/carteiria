import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, ApiError, setCsrfToken, setUnauthorizedHandler } from '../lib/api'

export interface User {
  id: string
  email: string
  display_name: string
  role: 'USER' | 'ADMIN'
  status: string
  created_at: string
}

interface SessionResponse {
  user: User
  csrf_token: string
}

interface AuthState {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<void>
  setUser: (u: User | null) => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const clear = useCallback(() => {
    setCsrfToken(null)
    setUser(null)
  }, [])

  const refresh = useCallback(async () => {
    try {
      const s = await api<SessionResponse>('/auth/session', { skipAuthRedirect: true })
      setCsrfToken(s.csrf_token)
      setUser(s.user)
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) clear()
      else throw e
    }
  }, [clear])

  useEffect(() => {
    refresh()
      .catch(() => clear())
      .finally(() => setLoading(false))
  }, [refresh, clear])

  // Sessão expirada em qualquer chamada: volta ao estado deslogado.
  useEffect(() => {
    setUnauthorizedHandler(clear)
    return () => setUnauthorizedHandler(null)
  }, [clear])

  const login = useCallback(async (email: string, password: string) => {
    const s = await api<SessionResponse>('/auth/login', { method: 'POST', body: { email, password }, skipAuthRedirect: true })
    setCsrfToken(s.csrf_token)
    setUser(s.user)
  }, [])

  const logout = useCallback(async () => {
    try {
      await api('/auth/logout', { method: 'POST', skipAuthRedirect: true })
    } finally {
      clear()
    }
  }, [clear])

  const value = useMemo(() => ({ user, loading, login, logout, refresh, setUser }), [user, loading, login, logout, refresh])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth fora do AuthProvider')
  return ctx
}
