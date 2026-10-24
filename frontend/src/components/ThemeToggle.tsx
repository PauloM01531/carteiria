import { useState } from 'react'
import { applyTheme, storedTheme, type Theme } from '../lib/theme'
import { api } from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { cx } from './ui'

const next: Record<Theme, Theme> = { system: 'light', light: 'dark', dark: 'system' }
const label: Record<Theme, string> = { system: 'Tema do sistema', light: 'Tema claro', dark: 'Tema escuro' }

export function ThemeToggle({ compact }: { compact?: boolean }) {
  const { user } = useAuth()
  const [theme, setTheme] = useState<Theme>(storedTheme())

  function toggle() {
    const t = next[theme]
    setTheme(t)
    applyTheme(t)
    if (user) api('/me/preferences', { method: 'PUT', body: { theme: t } }).catch(() => undefined)
  }

  const icon =
    theme === 'dark' ? (
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    ) : theme === 'light' ? (
      <path d="M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zm0-5v3m0 14v3M2 12h3m14 0h3M4.9 4.9l2.1 2.1m10 10 2.1 2.1M4.9 19.1 7 17m10-10 2.1-2.1" />
    ) : (
      <path d="M3 5h18v11H3zm5 15h8m-4-4v4" />
    )

  return (
    <button
      type="button"
      onClick={toggle}
      title={`${label[theme]} (clique para alternar)`}
      aria-label={`${label[theme]}. Alternar tema`}
      className={cx('inline-flex min-h-10 items-center gap-2 rounded-xl px-3 text-sm font-semibold text-muted hover:bg-surface-2 hover:text-ink')}
    >
      <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
        {icon}
      </svg>
      {!compact && label[theme]}
    </button>
  )
}
