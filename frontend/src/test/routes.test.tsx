import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../App'
import { AuthProvider } from '../auth/AuthContext'

type Handler = (url: string, init?: RequestInit) => { status: number; body: unknown }

function mockFetch(handler: Handler) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const { status, body } = handler(url, init)
    return new Response(body === undefined ? '' : JSON.stringify(body), { status })
  })
  vi.stubGlobal('fetch', fn)
  return fn
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

const unauthenticated: Handler = () => ({ status: 401, body: { detail: { code: 'not_authenticated', message: 'Sessão inválida' } } })
const user = { id: '1', email: 'ana@exemplo.com.br', display_name: 'Ana Teste', role: 'USER', status: 'active', created_at: '2026-10-01T12:00:00Z' }

beforeEach(() => {
  window.matchMedia = vi.fn().mockReturnValue({ matches: false }) as never
})
afterEach(() => vi.unstubAllGlobals())

describe('proteção de rotas', () => {
  it('redireciona visitante sem sessão do painel para a tela de entrar', async () => {
    mockFetch(unauthenticated)
    renderAt('/painel')
    expect(await screen.findByRole('heading', { name: 'Entrar' })).toBeInTheDocument()
  })

  it('usuário comum não vê o painel administrativo', async () => {
    mockFetch((url) => (url.endsWith('/auth/session') ? { status: 200, body: { user, csrf_token: 'abc' } } : { status: 200, body: {} }))
    renderAt('/admin')
    expect(await screen.findByRole('heading', { name: /Ana/ })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Administração' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Admin' })).not.toBeInTheDocument()
  })
})

describe('formulários', () => {
  it('cadastro valida antes de enviar e não chama a API com dados inválidos', async () => {
    const fetchMock = mockFetch(unauthenticated)
    renderAt('/cadastro')
    await screen.findByRole('heading', { name: 'Solicitar acesso' })
    await userEvent.type(screen.getByLabelText('E-mail'), 'invalido')
    await userEvent.type(screen.getByLabelText('Senha'), 'curta')
    await userEvent.click(screen.getByRole('button', { name: 'Solicitar acesso' }))
    expect(screen.getByText('E-mail inválido.')).toBeInTheDocument()
    expect(screen.getByText('A senha deve ter pelo menos 10 caracteres.')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/auth/register'))).toBe(false)
  })

  it('login mostra a mensagem do servidor e envia o CSRF nas chamadas seguintes', async () => {
    let logged = false
    const fetchMock = mockFetch((url) => {
      if (url.endsWith('/auth/login')) {
        logged = true
        return { status: 200, body: { user, csrf_token: 'token-csrf' } }
      }
      if (url.endsWith('/auth/session')) return logged ? { status: 200, body: { user, csrf_token: 'token-csrf' } } : unauthenticated(url)
      return { status: 200, body: { theme: 'system' } }
    })
    renderAt('/entrar')
    await screen.findByRole('heading', { name: 'Entrar' })
    await userEvent.type(screen.getByLabelText('E-mail'), 'ana@exemplo.com.br')
    await userEvent.type(screen.getByLabelText('Senha'), 'SenhaForte123')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByRole('heading', { name: /Ana/ })).toBeInTheDocument()

    // Alternar o tema dispara um PUT, que precisa levar o cabeçalho CSRF
    await userEvent.click(screen.getAllByRole('button', { name: /Alternar tema/ })[0])
    await waitFor(() => {
      const put = fetchMock.mock.calls.find(([u, i]) => String(u).includes('/me/preferences') && i?.method === 'PUT')
      expect(put).toBeTruthy()
      expect((put![1]!.headers as Record<string, string>)['X-CSRF-Token']).toBe('token-csrf')
    })
  })

  it('login com erro exibe a mensagem', async () => {
    mockFetch((url) =>
      url.endsWith('/auth/login')
        ? { status: 401, body: { detail: { code: 'invalid_credentials', message: 'E-mail ou senha incorretos.' } } }
        : unauthenticated(url),
    )
    renderAt('/entrar')
    await screen.findByRole('heading', { name: 'Entrar' })
    await userEvent.type(screen.getByLabelText('E-mail'), 'ana@exemplo.com.br')
    await userEvent.type(screen.getByLabelText('Senha'), 'errada')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('E-mail ou senha incorretos.')
  })
})
