/** Painel administrativo. A proteção real está no backend (papel ADMIN verificado em toda rota). */
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Alert, Button, Card, ConfirmDialog, EmptyState, Field, Spinner, cx } from '../../components/ui'
import { api } from '../../lib/api'
import { formatDate, formatDateTime } from '../../lib/format'
import { validateEmail } from '../../lib/validation'

const msg = (e: unknown) => (e instanceof Error ? e.message : 'Erro inesperado.')

interface AdminUser {
  id: string
  email: string
  display_name: string
  role: string
  status: string
  email_verified: boolean
  created_at: string
  last_login_at: string | null
}
interface Invite {
  id: string
  email: string
  expires_at: string
  used_at: string | null
  revoked_at: string | null
  created_at: string
}
interface AuditEntry {
  id: number
  actor_email: string | null
  action: string
  result: string
  details: Record<string, unknown>
  created_at: string
}

const STATUS_LABEL: Record<string, string> = {
  pending_approval: 'Aguardando aprovação',
  active: 'Ativa',
  suspended: 'Suspensa',
  rejected: 'Rejeitada',
}
const MODE_INFO: Record<string, { label: string; text: string }> = {
  closed: { label: 'Fechado', text: 'Ninguém pode criar conta, nem por convite.' },
  approval: { label: 'Aprovação manual', text: 'Qualquer pessoa pode solicitar; o acesso só é liberado após sua aprovação.' },
  invite: { label: 'Somente convites', text: 'Apenas quem recebeu um convite pode criar conta.' },
}
const ACTION_LABEL: Record<string, string> = {
  user_registered: 'Cadastro solicitado',
  user_approved: 'Cadastro aprovado',
  user_rejected: 'Cadastro rejeitado',
  user_suspended: 'Conta suspensa',
  user_reactivated: 'Conta reativada',
  invite_created: 'Convite criado',
  invite_revoked: 'Convite revogado',
  registration_mode_changed: 'Modo de cadastro alterado',
  admin_access_denied: 'Acesso administrativo negado',
  admin_promoted: 'Conta promovida a admin',
  login: 'Login',
  login_failed: 'Falha de login',
  password_reset_requested: 'Redefinição de senha pedida',
  password_reset: 'Senha redefinida',
  password_changed: 'Senha alterada',
  account_deleted: 'Conta excluída',
}

function StatusBadge({ status }: { status: string }) {
  const color =
    status === 'active' ? 'bg-positive/15 text-positive' : status === 'pending_approval' ? 'bg-accent-soft text-ink' : 'bg-negative/15 text-negative'
  return <span className={cx('rounded-full px-2.5 py-0.5 text-xs font-semibold', color)}>{STATUS_LABEL[status] ?? status}</span>
}

// ------------------------------------------------------------------ Visão geral
function Overview() {
  const [stats, setStats] = useState<{ total_users: number; by_status: Record<string, number>; pending_invites: number } | null>(null)
  const [mode, setMode] = useState<string | null>(null)
  const [pendingMode, setPendingMode] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api<typeof stats>('/admin/stats').then(setStats).catch((e) => setError(msg(e)))
    api<{ mode: string }>('/admin/registration-mode').then((r) => setMode(r.mode)).catch((e) => setError(msg(e)))
  }, [])

  async function saveMode() {
    if (!pendingMode) return
    setSaving(true)
    try {
      const r = await api<{ mode: string }>('/admin/registration-mode', { method: 'PUT', body: { mode: pendingMode } })
      setMode(r.mode)
    } catch (e) {
      setError(msg(e))
    } finally {
      setSaving(false)
      setPendingMode(null)
    }
  }

  const tiles = stats
    ? [
        { label: 'Contas', value: stats.total_users },
        { label: 'Aguardando aprovação', value: stats.by_status.pending_approval ?? 0 },
        { label: 'Suspensas', value: stats.by_status.suspended ?? 0 },
        { label: 'Convites pendentes', value: stats.pending_invites },
      ]
    : []

  return (
    <div className="flex flex-col gap-6">
      {error && <Alert kind="error">{error}</Alert>}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {stats === null ? (
          <Spinner />
        ) : (
          tiles.map((t) => (
            <Card key={t.label} className="p-4">
              <p className="text-sm text-muted">{t.label}</p>
              <p className="tabular mt-1 font-display text-3xl font-semibold">{t.value}</p>
            </Card>
          ))
        )}
      </div>
      <Card>
        <h2 className="font-display text-xl font-semibold">Modo de cadastro</h2>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          {Object.entries(MODE_INFO).map(([key, info]) => (
            <button
              key={key}
              type="button"
              onClick={() => key !== mode && setPendingMode(key)}
              className={cx('rounded-xl border p-4 text-left transition', key === mode ? 'border-accent bg-accent-soft' : 'border-line hover:bg-surface-2')}
              aria-pressed={key === mode}
            >
              <p className="font-semibold">{info.label}</p>
              <p className="mt-1 text-sm text-muted">{info.text}</p>
            </button>
          ))}
        </div>
      </Card>
      <ConfirmDialog
        open={!!pendingMode}
        title="Alterar o modo de cadastro?"
        loading={saving}
        onConfirm={saveMode}
        onCancel={() => setPendingMode(null)}
      >
        O modo passará a ser <strong>{pendingMode && MODE_INFO[pendingMode].label}</strong>. A alteração fica registrada na auditoria.
      </ConfirmDialog>
    </div>
  )
}

// ------------------------------------------------------------------ Usuários
type UserAction = 'approve' | 'reject' | 'suspend' | 'reactivate'
const ACTION_TEXT: Record<UserAction, { label: string; question: string; danger?: boolean }> = {
  approve: { label: 'Aprovar', question: 'Aprovar o acesso de' },
  reject: { label: 'Rejeitar', question: 'Rejeitar a solicitação de', danger: true },
  suspend: { label: 'Suspender', question: 'Suspender a conta de', danger: true },
  reactivate: { label: 'Reativar', question: 'Reativar a conta de' },
}

function actionsFor(u: AdminUser): UserAction[] {
  if (u.role === 'ADMIN') return []
  if (u.status === 'pending_approval') return ['approve', 'reject']
  if (u.status === 'active') return ['suspend']
  return ['reactivate']
}

function Users() {
  const [users, setUsers] = useState<AdminUser[] | null>(null)
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState<{ user: AdminUser; action: UserAction } | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    const params = new URLSearchParams()
    if (q.trim()) params.set('q', q.trim())
    if (status) params.set('status', status)
    setUsers(null)
    api<AdminUser[]>(`/admin/users?${params}`).then(setUsers).catch((e) => setError(msg(e)))
  }, [q, status])

  useEffect(() => {
    const t = setTimeout(load, 250)
    return () => clearTimeout(t)
  }, [load])

  async function run() {
    if (!pending) return
    setBusy(true)
    try {
      await api(`/admin/users/${pending.user.id}/${pending.action}`, { method: 'POST' })
      load()
    } catch (e) {
      setError(msg(e))
    } finally {
      setBusy(false)
      setPending(null)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <Field label="Buscar por nome ou e-mail" className="flex-1" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="flex flex-col gap-1.5">
          <label htmlFor="status-filter" className="text-sm font-semibold">Situação</label>
          <select id="status-filter" value={status} onChange={(e) => setStatus(e.target.value)} className="min-h-11 rounded-xl border border-line bg-surface px-3">
            <option value="">Todas</option>
            {Object.entries(STATUS_LABEL).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </div>
      </div>
      {error && <Alert kind="error">{error}</Alert>}
      {users === null ? (
        <Spinner />
      ) : users.length === 0 ? (
        <EmptyState title="Nenhuma conta encontrada">Ajuste a busca ou o filtro de situação.</EmptyState>
      ) : (
        <ul className="flex flex-col gap-3">
          {users.map((u) => (
            <li key={u.id} className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="flex flex-wrap items-center gap-2 font-semibold">
                  {u.display_name} <StatusBadge status={u.status} />
                  {u.role === 'ADMIN' && <span className="rounded-full bg-brand px-2 py-0.5 text-xs text-brand-contrast">Admin</span>}
                  {!u.email_verified && <span className="text-xs text-muted">e-mail não confirmado</span>}
                </p>
                <p className="truncate text-sm text-muted">{u.email}</p>
                <p className="text-xs text-muted">
                  Cadastro em {formatDate(u.created_at)}
                  {u.last_login_at && ` · último acesso ${formatDateTime(u.last_login_at)}`}
                </p>
              </div>
              <div className="flex gap-2">
                {actionsFor(u).map((a) => (
                  <Button key={a} variant={ACTION_TEXT[a].danger ? 'secondary' : 'primary'} className="min-h-9 px-3" onClick={() => setPending({ user: u, action: a })}>
                    {ACTION_TEXT[a].label}
                  </Button>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog
        open={!!pending}
        title={pending ? `${ACTION_TEXT[pending.action].label} conta?` : ''}
        confirmLabel={pending ? ACTION_TEXT[pending.action].label : ''}
        danger={pending ? ACTION_TEXT[pending.action].danger : false}
        loading={busy}
        onConfirm={run}
        onCancel={() => setPending(null)}
      >
        {pending && `${ACTION_TEXT[pending.action].question} ${pending.user.display_name} (${pending.user.email})?`}
        {pending?.action === 'suspend' && ' Todas as sessões dessa pessoa serão encerradas imediatamente.'}
      </ConfirmDialog>
    </div>
  )
}

// ------------------------------------------------------------------ Convites
function Invites() {
  const [items, setItems] = useState<Invite[] | null>(null)
  const [email, setEmail] = useState('')
  const [fieldError, setFieldError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [link, setLink] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [loading, setLoading] = useState(false)
  const [revoking, setRevoking] = useState<Invite | null>(null)

  const load = () => api<Invite[]>('/admin/invites').then(setItems).catch((e) => setError(msg(e)))
  useEffect(() => {
    load()
  }, [])

  async function create(e: FormEvent) {
    e.preventDefault()
    const v = validateEmail(email)
    setFieldError(v)
    if (v) return
    setLoading(true)
    setError(null)
    setCopied(false)
    try {
      const r = await api<{ link: string }>('/admin/invites', { method: 'POST', body: { email: email.trim() } })
      setLink(r.link)
      setEmail('')
      load()
    } catch (err) {
      setError(msg(err))
    } finally {
      setLoading(false)
    }
  }

  async function revoke() {
    if (!revoking) return
    try {
      await api(`/admin/invites/${revoking.id}`, { method: 'DELETE' })
      load()
    } catch (e) {
      setError(msg(e))
    } finally {
      setRevoking(null)
    }
  }

  function inviteState(i: Invite): string {
    if (i.used_at) return 'Usado'
    if (i.revoked_at) return 'Revogado'
    if (new Date(i.expires_at) < new Date()) return 'Expirado'
    return 'Pendente'
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <h2 className="font-display text-xl font-semibold">Novo convite</h2>
        <p className="mt-1 text-sm text-muted">O convite vale por 7 dias, uma única vez e somente para o e-mail informado.</p>
        <form onSubmit={create} noValidate className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end">
          <Field label="E-mail da pessoa" type="email" className="flex-1" value={email} onChange={(e) => setEmail(e.target.value)} error={fieldError} />
          <Button type="submit" loading={loading}>Enviar convite</Button>
        </form>
        {link && (
          <div className="mt-4">
            <Alert kind="success">
              Convite enviado por e-mail. Se preferir, copie o link abaixo e envie você mesmo. Ele só é exibido agora.
              <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                <code className="block flex-1 overflow-x-auto rounded-lg bg-surface px-2 py-1.5 text-xs">{link}</code>
                <Button
                  variant="secondary"
                  className="min-h-9 px-3"
                  onClick={() => navigator.clipboard?.writeText(link).then(() => setCopied(true))}
                >
                  {copied ? 'Copiado' : 'Copiar'}
                </Button>
              </div>
            </Alert>
          </div>
        )}
      </Card>
      {error && <Alert kind="error">{error}</Alert>}
      {items === null ? (
        <Spinner />
      ) : items.length === 0 ? (
        <EmptyState title="Nenhum convite enviado">Use o formulário acima para convidar alguém.</EmptyState>
      ) : (
        <ul className="divide-y divide-line rounded-2xl border border-line bg-surface">
          {items.map((i) => (
            <li key={i.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
              <div className="min-w-0">
                <p className="truncate font-semibold">{i.email}</p>
                <p className="text-muted">
                  {inviteState(i)} · criado em {formatDate(i.created_at)} · expira em {formatDate(i.expires_at)}
                </p>
              </div>
              {inviteState(i) === 'Pendente' && (
                <Button variant="secondary" className="min-h-9 px-3" onClick={() => setRevoking(i)}>Revogar</Button>
              )}
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog open={!!revoking} title="Revogar convite?" confirmLabel="Revogar" danger onConfirm={revoke} onCancel={() => setRevoking(null)}>
        O link enviado para {revoking?.email} deixará de funcionar.
      </ConfirmDialog>
    </div>
  )
}

// ------------------------------------------------------------------ Auditoria
function Audit() {
  const [items, setItems] = useState<AuditEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    api<AuditEntry[]>('/admin/audit-logs?limit=200').then(setItems).catch((e) => setError(msg(e)))
  }, [])
  if (error) return <Alert kind="error">{error}</Alert>
  if (items === null) return <Spinner />
  if (!items.length) return <EmptyState title="Sem eventos">Os eventos administrativos aparecerão aqui.</EmptyState>
  return (
    <ul className="divide-y divide-line rounded-2xl border border-line bg-surface">
      {items.map((a) => (
        <li key={a.id} className="flex flex-col gap-0.5 px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="font-semibold">
              {ACTION_LABEL[a.action] ?? a.action}
              {a.result !== 'success' && <span className="ml-2 text-xs text-negative">({a.result === 'denied' ? 'negado' : 'falhou'})</span>}
            </p>
            {a.actor_email && <p className="text-muted">por {a.actor_email}</p>}
          </div>
          <time className="tabular text-muted">{formatDateTime(a.created_at)}</time>
        </li>
      ))}
    </ul>
  )
}

const TABS = [
  { key: 'overview', label: 'Visão geral', el: <Overview /> },
  { key: 'users', label: 'Contas', el: <Users /> },
  { key: 'invites', label: 'Convites', el: <Invites /> },
  { key: 'audit', label: 'Auditoria', el: <Audit /> },
]

export default function AdminPage() {
  const [tab, setTab] = useState('overview')
  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="font-display text-3xl font-semibold tracking-tight">Administração</h1>
        <p className="mt-1 text-sm text-muted">Gestão de acessos. Dados financeiros dos usuários não são exibidos aqui.</p>
      </header>
      <div role="tablist" className="-mx-4 flex gap-1 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={cx('whitespace-nowrap rounded-xl px-4 py-2 text-sm font-semibold', tab === t.key ? 'bg-brand text-brand-contrast' : 'text-muted hover:bg-surface-2')}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel">{TABS.find((t) => t.key === tab)?.el}</div>
    </div>
  )
}
