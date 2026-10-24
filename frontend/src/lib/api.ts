/**
 * Cliente HTTP da API.
 * - A sessão fica num cookie HttpOnly (o JavaScript nunca vê o token).
 * - O token CSRF fica somente em memória (não vai para localStorage).
 */

export interface ApiErrorDetail {
  code: string
  message: string
  fields?: { field: string; message: string }[]
}

export class ApiError extends Error {
  status: number
  code: string
  fields: { field: string; message: string }[]

  constructor(status: number, detail: ApiErrorDetail) {
    super(detail.message)
    this.status = status
    this.code = detail.code
    this.fields = detail.fields ?? []
  }
}

let csrfToken: string | null = null
let onUnauthorized: (() => void) | null = null

export function setCsrfToken(token: string | null) {
  csrfToken = token
}

export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn
}

const BASE = '/api/v1'

export function parseError(status: number, body: unknown): ApiError {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (detail && typeof detail === 'object' && 'message' in detail) {
    return new ApiError(status, detail as ApiErrorDetail)
  }
  if (typeof detail === 'string') return new ApiError(status, { code: 'error', message: detail })
  if (status === 429) return new ApiError(status, { code: 'rate_limited', message: 'Muitas tentativas. Aguarde e tente novamente.' })
  if (status >= 500) return new ApiError(status, { code: 'server', message: 'O servidor encontrou um problema. Tente novamente.' })
  return new ApiError(status, { code: 'error', message: 'Não foi possível concluir a operação.' })
}

export async function api<T>(path: string, options: { method?: string; body?: unknown; skipAuthRedirect?: boolean } = {}): Promise<T> {
  const method = options.method ?? 'GET'
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (method !== 'GET' && csrfToken) headers['X-CSRF-Token'] = csrfToken

  let res: Response
  try {
    res = await fetch(BASE + path, {
      method,
      headers,
      credentials: 'same-origin',
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    })
  } catch {
    throw new ApiError(0, { code: 'network', message: 'Sem conexão com o servidor. Verifique sua internet.' })
  }

  const text = await res.text()
  let data: unknown = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = null
    }
  }
  if (!res.ok) {
    if (res.status === 401 && !options.skipAuthRedirect && onUnauthorized) onUnauthorized()
    throw parseError(res.status, data)
  }
  return data as T
}

/** Lê um token passado no fragmento da URL (#token=...) e limpa a barra de endereço. */
export function takeHashParam(name: string): string | null {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ''))
  const value = params.get(name)
  if (value) history.replaceState(null, '', window.location.pathname + window.location.search)
  return value
}
