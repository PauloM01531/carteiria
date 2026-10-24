/** Verificação em duas etapas (MFA) e confirmação de identidade para operações críticas. */
import QRCode from 'qrcode'
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { useAuth } from '../auth/AuthContext'
import { api, ApiError } from '../lib/api'
import { Alert, Button, Card, Field, Modal, Spinner } from './ui'

const msg = (e: unknown) => (e instanceof ApiError ? e.message : 'Não foi possível concluir.')

export function MfaCard() {
  const { user, refresh } = useAuth()
  const [status, setStatus] = useState<{ enabled: boolean; required: boolean } | null>(null)
  const [step, setStep] = useState<'idle' | 'password' | 'scan' | 'disable'>('idle')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [setup, setSetup] = useState<{ secret: string; qr: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [ok, setOk] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(() => api<{ enabled: boolean; required: boolean }>('/me/mfa').then(setStatus).catch((e) => setError(msg(e))), [])
  useEffect(() => { load() }, [load])

  async function startSetup(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const r = await api<{ secret: string; otpauth_uri: string }>('/me/mfa/setup', { method: 'POST', body: { password } })
      // O QR code é gerado no próprio navegador: o segredo não é enviado a nenhum serviço externo.
      const qr = await QRCode.toDataURL(r.otpauth_uri, { margin: 1, width: 220 })
      setSetup({ secret: r.secret, qr })
      setPassword('')
      setStep('scan')
    } catch (err) {
      setError(msg(err))
    } finally {
      setLoading(false)
    }
  }

  async function confirm(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await api('/me/mfa/enable', { method: 'POST', body: { code: code.trim() } })
      setOk('Verificação em duas etapas ativada. As outras sessões foram encerradas.')
      setStep('idle')
      setSetup(null)
      setCode('')
      await Promise.all([load(), refresh()])
    } catch (err) {
      setError(msg(err))
    } finally {
      setLoading(false)
    }
  }

  async function disable(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await api('/me/mfa/disable', { method: 'POST', body: { password, code: code.trim() } })
      setOk('Verificação em duas etapas desativada.')
      setStep('idle')
      setPassword('')
      setCode('')
      await Promise.all([load(), refresh()])
    } catch (err) {
      setError(msg(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card>
      <h2 className="font-display text-xl font-semibold">Verificação em duas etapas</h2>
      <p className="mt-1 text-sm text-muted">
        Além da senha, pede um código de 6 números do aplicativo autenticador (Google Authenticator, Microsoft Authenticator, Aegis, 2FAS…).
        {user?.role === 'ADMIN' && ' Obrigatória para a administração.'}
      </p>
      {error && <div className="mt-3"><Alert kind="error">{error}</Alert></div>}
      {ok && <div className="mt-3"><Alert kind="success">{ok}</Alert></div>}
      {status === null ? (
        <Spinner className="mt-3 h-5 w-5" />
      ) : step === 'password' ? (
        <form onSubmit={startSetup} noValidate className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end">
          <Field label="Confirme sua senha" type="password" autoComplete="current-password" className="flex-1" value={password} onChange={(e) => setPassword(e.target.value)} />
          <Button type="submit" loading={loading}>Continuar</Button>
        </form>
      ) : step === 'scan' && setup ? (
        <form onSubmit={confirm} noValidate className="mt-4 grid gap-4 sm:grid-cols-[auto_1fr] sm:items-start">
          <img src={setup.qr} alt="QR code para o aplicativo autenticador" className="h-52 w-52 rounded-xl bg-white p-2" />
          <div className="flex flex-col gap-3">
            <p className="text-sm">1. No aplicativo autenticador, escaneie o QR code.</p>
            <p className="text-sm text-muted">Sem câmera? Digite a chave: <code className="break-all rounded bg-surface-2 px-1.5 py-0.5 text-ink">{setup.secret}</code></p>
            <p className="text-sm">2. Digite o código de 6 números que aparece no aplicativo.</p>
            <Field label="Código" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} />
            <div className="flex gap-2">
              <Button type="submit" loading={loading}>Ativar</Button>
              <Button type="button" variant="ghost" onClick={() => { setStep('idle'); setSetup(null) }}>Cancelar</Button>
            </div>
          </div>
        </form>
      ) : step === 'disable' ? (
        <form onSubmit={disable} noValidate className="mt-4 grid gap-3 sm:grid-cols-2">
          <Field label="Senha" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <Field label="Código do aplicativo" inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} />
          <div className="flex gap-2 sm:col-span-2">
            <Button type="submit" variant="danger" loading={loading}>Desativar</Button>
            <Button type="button" variant="ghost" onClick={() => setStep('idle')}>Cancelar</Button>
          </div>
        </form>
      ) : status.enabled ? (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <span className="rounded-full bg-positive/15 px-3 py-1 text-sm font-semibold text-positive">✓ Ativada</span>
          {!status.required && <Button variant="ghost" onClick={() => { setStep('disable'); setOk(null) }}>Desativar</Button>}
        </div>
      ) : (
        <Button className="mt-4" onClick={() => { setStep('password'); setOk(null) }}>Ativar verificação em duas etapas</Button>
      )}
    </Card>
  )
}

/** Executa uma ação; se o servidor pedir reautenticação, abre o diálogo e repete a ação depois. */
export function useReauth() {
  const [open, setOpen] = useState(false)
  const pending = useRef<(() => Promise<unknown>) | null>(null)

  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    try {
      return await fn()
    } catch (e) {
      if (e instanceof ApiError && e.code === 'reauth_required') {
        pending.current = fn
        setOpen(true)
        return undefined
      }
      throw e
    }
  }, [])

  const dialog = (
    <ReauthDialog
      open={open}
      onClose={() => { setOpen(false); pending.current = null }}
      onConfirmed={async () => {
        setOpen(false)
        const fn = pending.current
        pending.current = null
        if (fn) await fn()
      }}
    />
  )
  return { run, dialog }
}

function ReauthDialog({ open, onClose, onConfirmed }: { open: boolean; onClose: () => void; onConfirmed: () => Promise<void> }) {
  const { user } = useAuth()
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await api('/auth/reauth', { method: 'POST', body: { password, code: code || null } })
      setPassword('')
      setCode('')
      await onConfirmed()
    } catch (err) {
      setError(msg(err))
    } finally {
      setLoading(false)
    }
  }
  return (
    <Modal open={open} title="Confirme sua identidade" onClose={onClose}>
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <p className="text-sm text-muted">Esta é uma operação administrativa sensível. Confirme sua senha{user?.mfa_enabled ? ' e o código do aplicativo' : ''}.</p>
        {error && <Alert kind="error">{error}</Alert>}
        <Field label="Senha" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        {user?.mfa_enabled && (
          <Field label="Código do aplicativo" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} />
        )}
        <Button type="submit" loading={loading}>Confirmar</Button>
      </form>
    </Modal>
  )
}
