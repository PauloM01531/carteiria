/** Páginas de autenticação: entrar, cadastro, verificação, recuperação e redefinição de senha. */
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { Alert, Button, Field, FullPageSpinner, PasswordStrength } from '../components/ui'
import { api, ApiError, takeHashParam } from '../lib/api'
import { passwordStrength, validateEmail, validateName, validatePassword } from '../lib/validation'

function AuthShell({ title, subtitle, children, footer }: { title: string; subtitle?: ReactNode; children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="mx-auto flex w-full max-w-md flex-col px-4 py-8 sm:py-14">
      <h1 className="font-display text-3xl font-semibold tracking-tight">{title}</h1>
      {subtitle && <p className="mt-2 text-muted">{subtitle}</p>}
      <div className="mt-6 rounded-2xl border border-line bg-surface p-5 sm:p-6">{children}</div>
      {footer && <div className="mt-5 text-center text-sm text-muted">{footer}</div>}
    </div>
  )
}

const messageFor = (e: unknown) => (e instanceof Error ? e.message : 'Erro inesperado.')

// ------------------------------------------------------------------ Entrar
export function LoginPage() {
  const { login, loginMfa } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [challenge, setChallenge] = useState<string | null>(null)
  const [mfaCode, setMfaCode] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<Record<string, string | null>>({})
  const [error, setError] = useState<string | null>(null)
  const [code, setCode] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [resent, setResent] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const v = { email: validateEmail(email), password: password ? null : 'Informe sua senha.' }
    setErrors(v)
    if (v.email || v.password) return
    setLoading(true)
    setError(null)
    setCode(null)
    try {
      const r = await login(email.trim(), password)
      if (r.challenge) {
        setChallenge(r.challenge)
        setPassword('')
        return
      }
      goNext()
    } catch (err) {
      setError(messageFor(err))
      if (err instanceof ApiError) setCode(err.code)
    } finally {
      setLoading(false)
    }
  }

  function goNext() {
    const from = (location.state as { from?: string } | null)?.from
    navigate(from && from.startsWith('/') ? from : '/painel', { replace: true })
  }

  async function onSubmitCode(e: FormEvent) {
    e.preventDefault()
    if (!/^\d{6}$/.test(mfaCode.trim())) return setError('Digite os 6 números do aplicativo.')
    setLoading(true)
    setError(null)
    try {
      await loginMfa(challenge!, mfaCode.trim())
      goNext()
    } catch (err) {
      setError(messageFor(err))
      if (err instanceof ApiError && err.code === 'invalid_challenge') setChallenge(null)
    } finally {
      setLoading(false)
    }
  }

  async function resend() {
    await api('/auth/resend-verification', { method: 'POST', body: { email: email.trim() } }).catch(() => undefined)
    setResent(true)
  }

  if (challenge) {
    return (
      <AuthShell title="Verificação em duas etapas" subtitle="Abra o aplicativo autenticador e digite o código de 6 números.">
        <form onSubmit={onSubmitCode} noValidate className="flex flex-col gap-4">
          {error && <Alert kind="error">{error}</Alert>}
          <Field label="Código" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={mfaCode} onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, ''))} autoFocus />
          <Button type="submit" loading={loading}>Confirmar</Button>
          <button type="button" className="text-sm font-semibold text-muted underline" onClick={() => { setChallenge(null); setMfaCode(''); setError(null) }}>Voltar</button>
        </form>
      </AuthShell>
    )
  }

  return (
    <AuthShell
      title="Entrar"
      subtitle="Bom te ver de novo."
      footer={
        <>
          Não tem conta? <Link to="/cadastro" className="font-semibold text-ink underline">Solicite acesso</Link>
        </>
      }
    >
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        {error && (
          <Alert kind="error">
            {error}
            {code === 'email_not_verified' && !resent && (
              <button type="button" onClick={resend} className="ml-1 font-semibold underline">
                Reenviar e-mail
              </button>
            )}
            {resent && <span className="ml-1">Enviamos um novo link.</span>}
          </Alert>
        )}
        <Field label="E-mail" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} error={errors.email} />
        <Field
          label="Senha"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
        />
        <Link to="/esqueci-senha" className="-mt-1 self-end text-sm font-semibold text-muted hover:text-ink">
          Esqueci minha senha
        </Link>
        <Button type="submit" loading={loading}>
          Entrar
        </Button>
      </form>
    </AuthShell>
  )
}

// ------------------------------------------------------------------ Cadastro
export function RegisterPage() {
  const [inviteToken] = useState(() => takeHashParam('convite'))
  const [form, setForm] = useState({ name: '', email: '', password: '', confirm: '' })
  const [errors, setErrors] = useState<Record<string, string | null>>({})
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value })

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const v = {
      name: validateName(form.name),
      email: validateEmail(form.email),
      password: validatePassword(form.password, form.email),
      confirm: form.password !== form.confirm ? 'As senhas não conferem.' : null,
    }
    setErrors(v)
    if (Object.values(v).some(Boolean)) return
    setLoading(true)
    setError(null)
    try {
      const r = await api<{ message: string }>('/auth/register', {
        method: 'POST',
        body: { display_name: form.name.trim(), email: form.email.trim(), password: form.password, ...(inviteToken ? { invite_token: inviteToken } : {}) },
      })
      setDone(r.message)
    } catch (err) {
      if (err instanceof ApiError && err.fields.length) {
        const map: Record<string, string> = { display_name: 'name', email: 'email', password: 'password' }
        setErrors(Object.fromEntries(err.fields.map((f) => [map[f.field] ?? f.field, 'Valor inválido.'])))
      }
      setError(messageFor(err))
    } finally {
      setLoading(false)
    }
  }

  if (done) {
    return (
      <AuthShell title="Confira seu e-mail" subtitle="Falta pouco.">
        <Alert kind="success">{done}</Alert>
        <p className="mt-4 text-sm text-muted">
          Abra o link enviado para confirmar seu endereço.
          {!inviteToken && ' Depois disso, sua conta passará pela aprovação do administrador.'}
        </p>
        <Link to="/entrar" className="mt-5 inline-block text-sm font-semibold underline">
          Ir para a tela de entrada
        </Link>
      </AuthShell>
    )
  }

  return (
    <AuthShell
      title={inviteToken ? 'Aceitar convite' : 'Solicitar acesso'}
      subtitle={inviteToken ? 'Use o mesmo e-mail que recebeu o convite.' : 'A CarteirIA está em testes: novas contas passam por aprovação.'}
      footer={
        <>
          Já tem conta? <Link to="/entrar" className="font-semibold text-ink underline">Entrar</Link>
        </>
      }
    >
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        {error && <Alert kind="error">{error}</Alert>}
        <Field label="Como quer ser chamado(a)?" autoComplete="nickname" maxLength={80} value={form.name} onChange={set('name')} error={errors.name} />
        <Field label="E-mail" type="email" autoComplete="email" value={form.email} onChange={set('email')} error={errors.email} />
        <div className="flex flex-col gap-2">
          <Field
            label="Senha"
            type="password"
            autoComplete="new-password"
            value={form.password}
            onChange={set('password')}
            error={errors.password}
            hint="Mínimo de 10 caracteres, com letras e números."
          />
          {form.password && <PasswordStrength score={passwordStrength(form.password)} />}
        </div>
        <Field label="Confirme a senha" type="password" autoComplete="new-password" value={form.confirm} onChange={set('confirm')} error={errors.confirm} />
        <p className="text-xs text-muted">
          Ao continuar você concorda com os <Link to="/termos" className="underline">Termos de uso</Link> e o{' '}
          <Link to="/privacidade" className="underline">Aviso de privacidade</Link>.
        </p>
        <Button type="submit" loading={loading}>
          {inviteToken ? 'Criar minha conta' : 'Solicitar acesso'}
        </Button>
      </form>
    </AuthShell>
  )
}

// ------------------------------------------------------------------ Verificação de e-mail
export function VerifyEmailPage() {
  const [state, setState] = useState<{ ok: boolean; message: string } | null>(null)
  const started = useRef(false)
  useEffect(() => {
    if (started.current) return
    started.current = true
    const token = takeHashParam('token')
    if (!token) {
      setState({ ok: false, message: 'Link incompleto. Abra novamente o link recebido por e-mail.' })
      return
    }
    api<{ message: string }>('/auth/verify-email', { method: 'POST', body: { token } })
      .then((r) => setState({ ok: true, message: r.message }))
      .catch((e) => setState({ ok: false, message: messageFor(e) }))
  }, [])
  if (!state) return <FullPageSpinner />
  return (
    <AuthShell title={state.ok ? 'E-mail confirmado' : 'Não foi possível confirmar'}>
      <Alert kind={state.ok ? 'success' : 'error'}>{state.message}</Alert>
      <Link to="/entrar" className="mt-5 inline-block text-sm font-semibold underline">
        Ir para a tela de entrada
      </Link>
    </AuthShell>
  )
}

// ------------------------------------------------------------------ Esqueci a senha
export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [fieldError, setFieldError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const v = validateEmail(email)
    setFieldError(v)
    if (v) return
    setLoading(true)
    setError(null)
    try {
      const r = await api<{ message: string }>('/auth/forgot-password', { method: 'POST', body: { email: email.trim() } })
      setDone(r.message)
    } catch (err) {
      setError(messageFor(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell title="Recuperar senha" subtitle="Enviaremos um link de redefinição para o seu e-mail." footer={<Link to="/entrar" className="font-semibold text-ink underline">Voltar para entrar</Link>}>
      {done ? (
        <Alert kind="success">{done}</Alert>
      ) : (
        <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
          {error && <Alert kind="error">{error}</Alert>}
          <Field label="E-mail" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} error={fieldError} />
          <Button type="submit" loading={loading}>
            Enviar link
          </Button>
        </form>
      )}
    </AuthShell>
  )
}

// ------------------------------------------------------------------ Redefinir senha
export function ResetPasswordPage() {
  const [token] = useState(() => takeHashParam('token'))
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [errors, setErrors] = useState<Record<string, string | null>>({})
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const v = { password: validatePassword(password), confirm: password !== confirm ? 'As senhas não conferem.' : null }
    setErrors(v)
    if (v.password || v.confirm) return
    setLoading(true)
    setError(null)
    try {
      const r = await api<{ message: string }>('/auth/reset-password', { method: 'POST', body: { token, password } })
      setDone(r.message)
    } catch (err) {
      setError(messageFor(err))
    } finally {
      setLoading(false)
    }
  }

  if (!token) {
    return (
      <AuthShell title="Link inválido">
        <Alert kind="error">Este link está incompleto ou já foi usado.</Alert>
        <Link to="/esqueci-senha" className="mt-5 inline-block text-sm font-semibold underline">
          Pedir um novo link
        </Link>
      </AuthShell>
    )
  }

  return (
    <AuthShell title="Nova senha" subtitle="Escolha uma senha que você não usa em outros sites.">
      {done ? (
        <>
          <Alert kind="success">{done}</Alert>
          <Link to="/entrar" className="mt-5 inline-block text-sm font-semibold underline">
            Entrar
          </Link>
        </>
      ) : (
        <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
          {error && <Alert kind="error">{error}</Alert>}
          <div className="flex flex-col gap-2">
            <Field label="Nova senha" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} error={errors.password} />
            {password && <PasswordStrength score={passwordStrength(password)} />}
          </div>
          <Field label="Confirme a nova senha" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} error={errors.confirm} />
          <Button type="submit" loading={loading}>
            Salvar nova senha
          </Button>
        </form>
      )}
    </AuthShell>
  )
}
