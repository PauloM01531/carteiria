import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth, type User } from '../auth/AuthContext'
import { Alert, Button, Card, ConfirmDialog, Field, PasswordStrength, Spinner } from '../components/ui'
import { api } from '../lib/api'
import { formatDate, formatDateTime } from '../lib/format'
import { applyTheme, type Theme } from '../lib/theme'
import { passwordStrength, validateName, validatePassword } from '../lib/validation'

const msg = (e: unknown) => (e instanceof Error ? e.message : 'Erro inesperado.')

function ProfileCard() {
  const { user, setUser } = useAuth()
  const [name, setName] = useState(user?.display_name ?? '')
  const [error, setError] = useState<string | null>(null)
  const [ok, setOk] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const v = validateName(name)
    setError(v)
    setOk(null)
    if (v) return
    setLoading(true)
    try {
      const u = await api<User>('/me', { method: 'PATCH', body: { display_name: name.trim() } })
      setUser(u)
      setOk('Nome atualizado.')
    } catch (err) {
      setError(msg(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card>
      <h2 className="font-display text-xl font-semibold">Dados da conta</h2>
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-muted">E-mail</dt>
          <dd className="font-semibold break-all">{user?.email}</dd>
        </div>
        <div>
          <dt className="text-muted">Membro desde</dt>
          <dd className="font-semibold">{user && formatDate(user.created_at)}</dd>
        </div>
      </dl>
      <form onSubmit={onSubmit} noValidate className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-end">
        <Field label="Nome de exibição" className="flex-1" maxLength={80} value={name} onChange={(e) => setName(e.target.value)} error={error} />
        <Button type="submit" loading={loading} variant="secondary">
          Salvar
        </Button>
      </form>
      {ok && <div className="mt-3"><Alert kind="success">{ok}</Alert></div>}
    </Card>
  )
}

function PreferencesCard() {
  const [theme, setTheme] = useState<Theme | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    api<{ theme: Theme }>('/me/preferences').then((p) => setTheme(p.theme)).catch((e) => setError(msg(e)))
  }, [])
  async function choose(t: Theme) {
    setTheme(t)
    applyTheme(t)
    try {
      await api('/me/preferences', { method: 'PUT', body: { theme: t } })
    } catch (e) {
      setError(msg(e))
    }
  }
  const options: { value: Theme; label: string }[] = [
    { value: 'system', label: 'Igual ao sistema' },
    { value: 'light', label: 'Claro' },
    { value: 'dark', label: 'Escuro' },
  ]
  return (
    <Card>
      <h2 className="font-display text-xl font-semibold">Preferências</h2>
      {error && <div className="mt-3"><Alert kind="error">{error}</Alert></div>}
      <fieldset className="mt-4">
        <legend className="text-sm font-semibold">Tema</legend>
        {theme === null ? (
          <Spinner className="mt-3 h-5 w-5" />
        ) : (
          <div className="mt-2 flex flex-wrap gap-2">
            {options.map((o) => (
              <label key={o.value} className={`cursor-pointer rounded-xl border px-4 py-2.5 text-sm font-semibold ${theme === o.value ? 'border-accent bg-accent-soft' : 'border-line'}`}>
                <input type="radio" name="theme" className="sr-only" checked={theme === o.value} onChange={() => choose(o.value)} />
                {o.label}
              </label>
            ))}
          </div>
        )}
      </fieldset>
    </Card>
  )
}

function PasswordCard() {
  const [form, setForm] = useState({ current: '', next: '', confirm: '' })
  const [errors, setErrors] = useState<Record<string, string | null>>({})
  const [error, setError] = useState<string | null>(null)
  const [ok, setOk] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const v = {
      current: form.current ? null : 'Informe a senha atual.',
      next: validatePassword(form.next),
      confirm: form.next !== form.confirm ? 'As senhas não conferem.' : null,
    }
    setErrors(v)
    setOk(null)
    setError(null)
    if (Object.values(v).some(Boolean)) return
    setLoading(true)
    try {
      const r = await api<{ message: string }>('/auth/change-password', {
        method: 'POST',
        body: { current_password: form.current, new_password: form.next },
      })
      setOk(r.message)
      setForm({ current: '', next: '', confirm: '' })
    } catch (err) {
      setError(msg(err))
    } finally {
      setLoading(false)
    }
  }
  return (
    <Card>
      <h2 className="font-display text-xl font-semibold">Alterar senha</h2>
      <form onSubmit={onSubmit} noValidate className="mt-4 grid gap-4 sm:grid-cols-2">
        {error && <div className="sm:col-span-2"><Alert kind="error">{error}</Alert></div>}
        {ok && <div className="sm:col-span-2"><Alert kind="success">{ok}</Alert></div>}
        <Field label="Senha atual" type="password" autoComplete="current-password" className="sm:col-span-2" value={form.current} onChange={(e) => setForm({ ...form, current: e.target.value })} error={errors.current} />
        <div className="flex flex-col gap-2">
          <Field label="Nova senha" type="password" autoComplete="new-password" value={form.next} onChange={(e) => setForm({ ...form, next: e.target.value })} error={errors.next} />
          {form.next && <PasswordStrength score={passwordStrength(form.next)} />}
        </div>
        <Field label="Confirme a nova senha" type="password" autoComplete="new-password" value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} error={errors.confirm} />
        <div className="sm:col-span-2">
          <Button type="submit" loading={loading}>Alterar senha</Button>
        </div>
      </form>
    </Card>
  )
}

interface DeviceSession {
  id: string
  created_at: string
  last_seen_at: string
  user_agent: string | null
  current: boolean
}

function describeAgent(ua: string | null): string {
  if (!ua) return 'Dispositivo desconhecido'
  const browser = /Edg\//.test(ua) ? 'Edge' : /Chrome\//.test(ua) ? 'Chrome' : /Firefox\//.test(ua) ? 'Firefox' : /Safari\//.test(ua) ? 'Safari' : 'Navegador'
  const os = /Windows/.test(ua) ? 'Windows' : /Android/.test(ua) ? 'Android' : /iPhone|iPad/.test(ua) ? 'iOS' : /Mac OS/.test(ua) ? 'macOS' : /Linux/.test(ua) ? 'Linux' : ''
  return os ? `${browser} · ${os}` : browser
}

function SessionsCard() {
  const [items, setItems] = useState<DeviceSession[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const load = () => api<DeviceSession[]>('/me/sessions').then(setItems).catch((e) => setError(msg(e)))
  useEffect(() => {
    load()
  }, [])
  async function revoke(id: string) {
    try {
      await api(`/me/sessions/${id}`, { method: 'DELETE' })
      await load()
    } catch (e) {
      setError(msg(e))
    }
  }
  return (
    <Card>
      <h2 className="font-display text-xl font-semibold">Sessões ativas</h2>
      <p className="mt-1 text-sm text-muted">Encerre acessos que você não reconhece.</p>
      {error && <div className="mt-3"><Alert kind="error">{error}</Alert></div>}
      {items === null ? (
        <Spinner className="mt-4 h-5 w-5" />
      ) : (
        <ul className="mt-4 divide-y divide-line">
          {items.map((s) => (
            <li key={s.id} className="flex items-center justify-between gap-3 py-3 text-sm">
              <div>
                <p className="font-semibold">
                  {describeAgent(s.user_agent)} {s.current && <span className="ml-1 rounded-full bg-accent-soft px-2 py-0.5 text-xs">esta sessão</span>}
                </p>
                <p className="text-muted">Último acesso em {formatDateTime(s.last_seen_at)}</p>
              </div>
              {!s.current && (
                <Button variant="secondary" className="min-h-9 px-3" onClick={() => revoke(s.id)}>
                  Encerrar
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function DangerCard() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function doDelete() {
    setLoading(true)
    setError(null)
    try {
      await api('/me', { method: 'DELETE', body: { password, confirmation } })
      await logout().catch(() => undefined)
      navigate('/', { replace: true })
    } catch (e) {
      setError(msg(e))
      setOpen(false)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card className="border-negative/40">
      <h2 className="font-display text-xl font-semibold">Seus dados</h2>
      <p className="mt-1 text-sm text-muted">
        Baixe todos os seus dados (lançamentos, cartões, faturas, contas, orçamentos e metas) em planilhas CSV. A exclusão remove
        definitivamente sua conta e todos os registros associados.
      </p>
      <a href="/api/v1/export/all.zip" download className="mt-4 inline-flex min-h-11 items-center rounded-xl border border-line bg-surface px-4 text-sm font-semibold hover:bg-surface-2">
        Exportar meus dados (ZIP)
      </a>
      {user?.role === 'ADMIN' ? (
        <p className="mt-4 text-sm text-muted">A conta do administrador principal não pode ser excluída por aqui.</p>
      ) : (
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          {error && <div className="sm:col-span-2"><Alert kind="error">{error}</Alert></div>}
          <Field label="Sua senha" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <Field label='Digite "EXCLUIR" para confirmar' value={confirmation} onChange={(e) => setConfirmation(e.target.value)} />
          <div className="sm:col-span-2">
            <Button variant="danger" disabled={!password || confirmation !== 'EXCLUIR'} onClick={() => setOpen(true)}>
              Excluir minha conta
            </Button>
          </div>
        </div>
      )}
      <ConfirmDialog open={open} title="Excluir conta definitivamente?" confirmLabel="Excluir para sempre" danger loading={loading} onConfirm={doDelete} onCancel={() => setOpen(false)}>
        Todos os seus dados serão apagados e não poderão ser recuperados.
      </ConfirmDialog>
    </Card>
  )
}

/** Atalhos para telas que não cabem na navegação do celular. */
function QuickLinks() {
  const { user } = useAuth()
  return (
    <div className="flex flex-wrap gap-2 lg:hidden">
      <Link to="/relatorios" className="rounded-xl border border-line bg-surface px-4 py-2.5 text-sm font-semibold">Relatórios</Link>
      <Link to="/orcamentos" className="rounded-xl border border-line bg-surface px-4 py-2.5 text-sm font-semibold">Orçamentos e metas</Link>
      <Link to="/categorias" className="rounded-xl border border-line bg-surface px-4 py-2.5 text-sm font-semibold">Categorias</Link>
      {user?.role === 'ADMIN' && <Link to="/admin" className="rounded-xl border border-line bg-surface px-4 py-2.5 text-sm font-semibold">Administração</Link>}
    </div>
  )
}

export default function Profile() {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="font-display text-3xl font-semibold tracking-tight">Perfil</h1>
      <QuickLinks />
      <ProfileCard />
      <PreferencesCard />
      <PasswordCard />
      <SessionsCard />
      <DangerCard />
    </div>
  )
}
