import { useEffect, useId, useRef, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from 'react'

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(' ')
}

export function Logo({ className = '' }: { className?: string }) {
  return (
    <span className={cx('inline-flex items-center gap-2 font-display text-xl font-semibold tracking-tight', className)}>
      <svg viewBox="0 0 64 64" className="h-8 w-8 shrink-0" aria-hidden>
        <rect width="64" height="64" rx="16" className="fill-[#0f2a2e] dark:fill-[#f2b544]" />
        <path d="M14 22a6 6 0 0 1 6-6h24a6 6 0 0 1 6 6v20a6 6 0 0 1-6 6H20a6 6 0 0 1-6-6z" fill="none" strokeWidth="4" className="stroke-[#f2b544] dark:stroke-[#0b1517]" />
        <path d="M36 30h14v8H36a4 4 0 0 1 0-8z" className="fill-[#f2b544] dark:fill-[#0b1517]" />
      </svg>
      <span>
        Carteir<span className="text-accent">IA</span>
      </span>
    </span>
  )
}

export function Spinner({ className = 'h-5 w-5' }: { className?: string }) {
  return (
    <svg className={cx('animate-spin', className)} viewBox="0 0 24 24" fill="none" role="status" aria-label="Carregando">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="4" />
      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
    </svg>
  )
}

export function FullPageSpinner() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center text-muted">
      <Spinner className="h-8 w-8" />
    </div>
  )
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost'
  loading?: boolean
}

export function Button({ variant = 'primary', loading, className, children, disabled, ...rest }: ButtonProps) {
  const styles = {
    primary: 'bg-brand text-brand-contrast hover:opacity-90',
    secondary: 'border border-line bg-surface text-ink hover:bg-surface-2',
    danger: 'bg-negative text-white hover:opacity-90',
    ghost: 'text-ink hover:bg-surface-2',
  }[variant]
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={cx(
        'inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60',
        styles,
        className,
      )}
    >
      {loading && <Spinner className="h-4 w-4" />}
      {children}
    </button>
  )
}

type FieldProps = InputHTMLAttributes<HTMLInputElement> & { label: string; error?: string | null; hint?: ReactNode }

export function Field({ label, error, hint, className, id, ...rest }: FieldProps) {
  const autoId = useId()
  const inputId = id ?? autoId
  const msgId = `${inputId}-msg`
  return (
    <div className={cx('flex flex-col gap-1.5', className)}>
      <label htmlFor={inputId} className="text-sm font-semibold">
        {label}
      </label>
      <input
        id={inputId}
        aria-invalid={!!error}
        aria-describedby={error || hint ? msgId : undefined}
        className={cx(
          'min-h-11 rounded-xl border bg-surface px-3.5 text-base outline-none transition placeholder:text-muted/70 focus:border-accent',
          error ? 'border-negative' : 'border-line',
        )}
        {...rest}
      />
      {error ? (
        <p id={msgId} className="text-sm text-negative">
          {error}
        </p>
      ) : hint ? (
        <p id={msgId} className="text-sm text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  )
}

export function Alert({ kind = 'info', children }: { kind?: 'info' | 'success' | 'error'; children: ReactNode }) {
  const styles = {
    info: 'border-line bg-surface-2 text-ink',
    success: 'border-positive/40 bg-positive/10 text-ink',
    error: 'border-negative/40 bg-negative/10 text-ink',
  }[kind]
  return (
    <div role={kind === 'error' ? 'alert' : 'status'} className={cx('rounded-xl border px-4 py-3 text-sm', styles)}>
      {children}
    </div>
  )
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={cx('rounded-2xl border border-line bg-surface p-5 sm:p-6', className)}>{children}</section>
}

export function EmptyState({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-line px-6 py-10 text-center">
      <div className="grid h-12 w-12 place-items-center rounded-full bg-accent-soft text-accent" aria-hidden>
        <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 5v14M5 12h14" strokeLinecap="round" />
        </svg>
      </div>
      <h3 className="font-display text-lg font-semibold">{title}</h3>
      <p className="max-w-md text-sm text-muted">{children}</p>
      {action}
    </div>
  )
}

/** Diálogo de confirmação acessível (usado antes de excluir registros). */
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel = 'Confirmar',
  danger,
  loading,
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  children: ReactNode
  confirmLabel?: string
  danger?: boolean
  loading?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    ref.current?.querySelector<HTMLButtonElement>('button')?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onCancel()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onCancel])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" onClick={onCancel}>
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md rounded-2xl border border-line bg-surface p-6 text-ink shadow-xl"
      >
        <h2 id="confirm-title" className="font-display text-xl font-semibold">
          {title}
        </h2>
        <div className="mt-3 text-sm text-muted">{children}</div>
        <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="secondary" onClick={onCancel} disabled={loading}>
            Cancelar
          </Button>
          <Button variant={danger ? 'danger' : 'primary'} onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}

export function PasswordStrength({ score }: { score: number }) {
  const labels = ['Muito fraca', 'Fraca', 'Razoável', 'Boa', 'Forte']
  return (
    <div className="flex items-center gap-2" aria-live="polite">
      <div className="flex flex-1 gap-1">
        {[0, 1, 2, 3].map((i) => (
          <span key={i} className={cx('h-1.5 flex-1 rounded-full', i < score ? (score >= 3 ? 'bg-positive' : 'bg-accent') : 'bg-surface-2')} />
        ))}
      </div>
      <span className="text-xs text-muted">{labels[score]}</span>
    </div>
  )
}

export function useAsync() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setLoading(true)
    setError(null)
    try {
      return await fn()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erro inesperado.')
      return undefined
    } finally {
      setLoading(false)
    }
  }
  return { loading, error, setError, run }
}
