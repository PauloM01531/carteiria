/**
 * Proteção de rotas no navegador. É só conveniência de navegação: quem decide o acesso
 * de verdade é o backend, que valida a sessão e o papel em toda requisição.
 */
import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { FullPageSpinner } from '../components/ui'
import { useAuth } from './AuthContext'

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <FullPageSpinner />
  if (!user) return <Navigate to="/entrar" replace state={{ from: location.pathname }} />
  return <>{children}</>
}

export function RequireAdmin({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <FullPageSpinner />
  if (!user) return <Navigate to="/entrar" replace />
  if (user.role !== 'ADMIN') return <Navigate to="/painel" replace />
  return <>{children}</>
}

export function GuestOnly({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <FullPageSpinner />
  if (user) return <Navigate to="/painel" replace />
  return <>{children}</>
}
