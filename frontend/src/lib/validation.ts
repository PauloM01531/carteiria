/** Validações no navegador (o backend valida de novo — esta camada só ajuda o usuário). */

export function validateEmail(email: string): string | null {
  if (!email.trim()) return 'Informe seu e-mail.'
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email.trim())) return 'E-mail inválido.'
  return null
}

export function validatePassword(password: string, email?: string): string | null {
  if (password.length < 10) return 'A senha deve ter pelo menos 10 caracteres.'
  if (password.length > 128) return 'A senha deve ter no máximo 128 caracteres.'
  if (!/[A-Za-zÀ-ÿ]/.test(password) || !/\d/.test(password)) return 'Use letras e números.'
  if (email && password.trim().toLowerCase() === email.trim().toLowerCase()) return 'A senha não pode ser igual ao e-mail.'
  return null
}

export function validateName(name: string): string | null {
  const v = name.trim()
  if (v.length < 2) return 'Informe um nome com pelo menos 2 caracteres.'
  if (v.length > 80) return 'Use no máximo 80 caracteres.'
  if (/[<>]/.test(v)) return 'O nome contém caracteres não permitidos.'
  return null
}

/** Força aproximada da senha (0–4) para o indicador visual. */
export function passwordStrength(password: string): number {
  let score = 0
  if (password.length >= 10) score++
  if (password.length >= 14) score++
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score++
  if (/\d/.test(password) && /[^A-Za-z0-9]/.test(password)) score++
  return Math.min(score, 4)
}
