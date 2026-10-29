import { lazy, Suspense } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { GuestOnly, RequireAdmin, RequireAuth } from './auth/guards'
import { AppLayout, PublicLayout } from './components/layouts'
import { FullPageSpinner } from './components/ui'
import Landing from './pages/Landing'
import { ForgotPasswordPage, LoginPage, RegisterPage, ResetPasswordPage, VerifyEmailPage } from './pages/auth'
import { NotFoundPage, PrivacyPage, TermsPage } from './pages/legal'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Profile = lazy(() => import('./pages/Profile'))
const TransactionsPage = lazy(() => import('./pages/transactions/TransactionsPage'))
const AdminPage = lazy(() => import('./pages/admin/AdminPage'))
const CardsPage = lazy(() => import('./pages/cards/CardsPage'))
const StatementPage = lazy(() => import('./pages/cards/StatementPage'))
const BillsPage = lazy(() => import('./pages/bills/BillsPage'))
const CategoriesPage = lazy(() => import('./pages/CategoriesPage'))
const ReportsPage = lazy(() => import('./pages/ReportsPage'))
const PlanningPage = lazy(() => import('./pages/PlanningPage'))
const PlannedPurchasesPage = lazy(() => import('./pages/planned/PlannedPurchasesPage'))

export function AppRoutes() {
  return (
    <Suspense fallback={<FullPageSpinner />}>
      <Routes>
        <Route element={<PublicLayout />}>
          <Route path="/" element={<Landing />} />
          <Route path="/entrar" element={<GuestOnly><LoginPage /></GuestOnly>} />
          <Route path="/cadastro" element={<GuestOnly><RegisterPage /></GuestOnly>} />
          <Route path="/verificar-email" element={<VerifyEmailPage />} />
          <Route path="/esqueci-senha" element={<ForgotPasswordPage />} />
          <Route path="/redefinir-senha" element={<ResetPasswordPage />} />
          <Route path="/privacidade" element={<PrivacyPage />} />
          <Route path="/termos" element={<TermsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
        <Route element={<RequireAuth><AppLayout /></RequireAuth>}>
          <Route path="/painel" element={<Dashboard />} />
          <Route path="/lancamentos" element={<TransactionsPage />} />
          <Route path="/cartoes" element={<CardsPage />} />
          <Route path="/cartoes/faturas/:id" element={<StatementPage />} />
          <Route path="/contas" element={<BillsPage />} />
          <Route path="/categorias" element={<CategoriesPage />} />
          <Route path="/relatorios" element={<ReportsPage />} />
          <Route path="/orcamentos" element={<PlanningPage />} />
          <Route path="/compras-planejadas" element={<PlannedPurchasesPage />} />
          <Route path="/perfil" element={<Profile />} />
          <Route path="/admin" element={<RequireAdmin><AdminPage /></RequireAdmin>} />
        </Route>
      </Routes>
    </Suspense>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}
