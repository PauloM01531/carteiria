import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { Button, Logo, cx } from './ui'
import { ThemeToggle } from './ThemeToggle'

export function PublicLayout() {
  const { user } = useAuth()
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between gap-3 px-4 py-4 sm:px-6">
        <Link to="/" aria-label="CarteirIA — início">
          <Logo />
        </Link>
        <nav className="flex items-center gap-1 sm:gap-2">
          <ThemeToggle compact />
          {user ? (
            <Link to="/painel" className="rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-brand-contrast">
              Abrir painel
            </Link>
          ) : (
            <>
              <Link to="/entrar" className="rounded-xl px-3 py-2.5 text-sm font-semibold hover:bg-surface-2">
                Entrar
              </Link>
              <Link to="/cadastro" className="rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-brand-contrast">
                Criar conta
              </Link>
            </>
          )}
        </nav>
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-6 text-sm text-muted sm:flex-row sm:justify-between sm:px-6">
          <p>© {new Date().getFullYear()} CarteirIA · versão de testes</p>
          <div className="flex gap-4">
            <Link to="/privacidade" className="hover:text-ink">Privacidade</Link>
            <Link to="/termos" className="hover:text-ink">Termos de uso</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}

const icons = {
  painel: 'M3 13h8V3H3zm0 8h8v-6H3zm10 0h8V11h-8zm0-18v6h8V3z',
  lancamentos: 'M4 6h16v2H4zm0 5h16v2H4zm0 5h10v2H4z',
  cartoes: 'M3 5h18a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zm-1 4v3h20V9zm3 6v2h5v-2z',
  contas: 'M7 2h10l4 4v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zm1 8v2h8v-2zm0 4v2h8v-2zm0-8v2h5V6z',
  relatorios: 'M4 20V10h3v10zm6.5 0V4h3v16zM17 20v-7h3v7z',
  planejamento: 'M12 2a10 10 0 1 0 10 10h-10z M14 0v10h10A10 10 0 0 0 14 0z',
  categorias: 'M4 4h7v7H4zm9 0h7v7h-7zM4 13h7v7H4zm9 0h7v7h-7z',
  perfil: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm0 2c-4 0-8 2-8 5v1h16v-1c0-3-4-5-8-5z',
  admin: 'M12 2 4 5v6c0 5 3.4 9.7 8 11 4.6-1.3 8-6 8-11V5z',
}

function NavIcon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor" aria-hidden>
      <path d={d} />
    </svg>
  )
}

export function AppLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const items = [
    { to: '/painel', label: 'Painel', icon: icons.painel },
    { to: '/lancamentos', label: 'Lançamentos', icon: icons.lancamentos },
    { to: '/cartoes', label: 'Cartões', icon: icons.cartoes },
    { to: '/contas', label: 'Contas', icon: icons.contas },
    { to: '/relatorios', label: 'Relatórios', icon: icons.relatorios, desktopOnly: true },
    { to: '/orcamentos', label: 'Planejamento', icon: icons.planejamento, desktopOnly: true },
    { to: '/categorias', label: 'Categorias', icon: icons.categorias, desktopOnly: true },
    { to: '/perfil', label: 'Perfil', icon: icons.perfil },
    ...(user?.role === 'ADMIN' ? [{ to: '/admin', label: 'Admin', icon: icons.admin, desktopOnly: true }] : []),
  ]
  async function onLogout() {
    await logout()
    navigate('/entrar', { replace: true })
  }
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    cx(
      'flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition',
      isActive ? 'bg-brand text-brand-contrast' : 'text-muted hover:bg-surface-2 hover:text-ink',
    )

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[16rem_1fr]">
      {/* Barra lateral (computador) */}
      <aside className="sticky top-0 hidden h-dvh flex-col border-r border-line bg-surface p-4 lg:flex">
        <Link to="/painel" className="px-2 py-2">
          <Logo />
        </Link>
        <nav className="mt-6 flex flex-col gap-1" aria-label="Navegação principal">
          {items.map((i) => (
            <NavLink key={i.to} to={i.to} className={linkClass}>
              <NavIcon d={i.icon} />
              {i.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto flex flex-col gap-3 border-t border-line pt-4">
          <ThemeToggle />
          <div className="px-1 text-sm">
            <p className="truncate font-semibold">{user?.display_name}</p>
            <p className="truncate text-muted">{user?.email}</p>
          </div>
          <Button variant="secondary" onClick={onLogout}>
            Sair
          </Button>
        </div>
      </aside>

      {/* Topo (celular) */}
      <header className="sticky top-0 z-20 flex items-center justify-between border-b border-line bg-surface/95 px-4 py-3 backdrop-blur lg:hidden">
        <Link to="/painel">
          <Logo className="text-lg" />
        </Link>
        <div className="flex items-center gap-1">
          <ThemeToggle compact />
          <Button variant="ghost" onClick={onLogout} className="min-h-10 px-3">
            Sair
          </Button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl px-4 pb-28 pt-6 sm:px-6 lg:pb-10 lg:pt-8">
        <Outlet />
      </main>

      {/* Navegação inferior (celular) */}
      <nav
        aria-label="Navegação principal"
        className="fixed inset-x-0 bottom-0 z-20 flex justify-around border-t border-line bg-surface/95 px-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] pt-2 backdrop-blur lg:hidden"
      >
        {items.filter((i) => !('desktopOnly' in i && i.desktopOnly)).map((i) => (
          <NavLink
            key={i.to}
            to={i.to}
            className={({ isActive }) =>
              cx('flex min-w-0 flex-1 flex-col items-center gap-1 rounded-xl px-1 py-1.5 text-[11px] font-semibold', isActive ? 'text-accent' : 'text-muted')
            }
          >
            <NavIcon d={i.icon} />
            {i.label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
