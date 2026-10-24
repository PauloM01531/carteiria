export type Theme = 'system' | 'light' | 'dark'

export function applyTheme(theme: Theme) {
  const dark = theme === 'dark' || (theme === 'system' && window.matchMedia?.('(prefers-color-scheme: dark)').matches)
  document.documentElement.classList.toggle('dark', !!dark)
  try {
    localStorage.setItem('cw-theme', theme) // preferência visual apenas; nada sensível
  } catch {
    /* navegação privada */
  }
}

export function storedTheme(): Theme {
  try {
    const t = localStorage.getItem('cw-theme')
    if (t === 'light' || t === 'dark' || t === 'system') return t
  } catch {
    /* ignore */
  }
  return 'system'
}
