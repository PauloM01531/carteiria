import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { addMonthsISO, installmentPreview } from '../lib/planned'
import PlannedPurchasesPage from '../pages/planned/PlannedPurchasesPage'

afterEach(() => vi.unstubAllGlobals())

describe('prévia das parcelas', () => {
  it('tablet de R$ 2.600 em 12x: diferença de centavos na última', () => {
    expect(installmentPreview('2600.00', 12)).toEqual({ first: 216.66, last: 216.74 })
    expect(installmentPreview('1200.00', 12)).toEqual({ first: 100, last: 100 })
    expect(installmentPreview('0.05', 12)).toBeNull()
    expect(installmentPreview('100.00', 0)).toBeNull()
    expect(installmentPreview('100.00', 73)).toBeNull()
  })
  it('período em meses', () => {
    expect(addMonthsISO('2026-11-10', 0)).toBe('2026-11-01')
    expect(addMonthsISO('2026-11-10', 11)).toBe('2027-10-01')
  })
})

const cats = [{ id: 'c1', name: 'Compras', kind: 'expense', active: true, is_system: true }]

function mock(handler: (url: string, init?: RequestInit) => { status?: number; body: unknown }) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const { status = 200, body } = handler(url, init)
    return new Response(JSON.stringify(body), { status })
  })
  vi.stubGlobal('fetch', fn)
  return fn
}

const renderPage = () => render(<MemoryRouter><PlannedPurchasesPage /></MemoryRouter>)

describe('aba Compras planejadas', () => {
  it('mostra estado vazio e valida o formulário antes de enviar', async () => {
    const fetchMock = mock((url) => (url.includes('/categories') ? { body: cats } : { body: [] }))
    renderPage()
    expect(await screen.findByText('Nenhuma compra planejada')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '+ Nova compra planejada' }))
    await userEvent.clear(screen.getByLabelText('Número de parcelas'))
    await userEvent.type(screen.getByLabelText('Número de parcelas'), '80')
    await userEvent.click(screen.getByRole('button', { name: 'Analisar e salvar' }))
    expect(screen.getByText('Informe o nome da compra.')).toBeInTheDocument()
    expect(screen.getByText('Informe o valor total, por exemplo 2.600,00.')).toBeInTheDocument()
    expect(screen.getByText('Use de 1 a 72 parcelas.')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([, i]) => i?.method === 'POST')).toBe(false)
  })

  it('envia a compra com valor decimal e mostra a prévia da parcela', async () => {
    const fetchMock = mock((url, init) => {
      if (url.includes('/categories')) return { body: cats }
      if (init?.method === 'POST') return { status: 201, body: {} }
      return { body: [] }
    })
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: '+ Nova compra planejada' }))
    await userEvent.type(screen.getByLabelText('Nome da compra'), 'Tablet')
    await userEvent.type(screen.getByLabelText('Valor total (R$)'), '2.600,00')
    await userEvent.clear(screen.getByLabelText('Número de parcelas'))
    await userEvent.type(screen.getByLabelText('Número de parcelas'), '12')
    expect(screen.getByText('11x de R$ 216,66 + 1x de R$ 216,74')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Analisar e salvar' }))
    await waitFor(() => expect(fetchMock.mock.calls.some(([, i]) => i?.method === 'POST')).toBe(true))
    const post = fetchMock.mock.calls.find(([, i]) => i?.method === 'POST')!
    const body = JSON.parse(String(post[1]!.body))
    expect(body).toMatchObject({ name: 'Tablet', total_amount: '2600.00', installments_count: 12, category_id: 'c1' })
    expect(body).not.toHaveProperty('user_id')
  })

  it('exibe a conclusão de cada mês com texto (não só cor)', async () => {
    const p = {
      id: 'p1', name: 'Tablet', total_amount: '2600.00', installments_count: 2, first_installment_date: '2026-12-10', category_id: 'c1',
      category_name: 'Compras', notes: null, installment_amount: '1300.00', last_installment_amount: '1300.00', first_month: '2026-12-01',
      last_month: '2027-01-01', overall_status: 'over', headline: 'Acima do orçamento em 1 de 2 mês(es).',
    }
    const month = (m: string, status: string, after: string) => ({
      month: m, number: m === '2026-12-01' ? 1 : 2, installment: '1300.00', income: '5000.00', income_source: 'media', registered_expenses: '0.00',
      card_installments: '0.00', subscriptions_projected: '0.00', bills_pending: '0.00', variable_estimate: '3000.00', other_planned: '0.00',
      committed: '3000.00', balance_before: '2000.00', balance_after: after, status, factors: ['Fator de teste.'], notes: [],
    })
    mock((url) => {
      if (url.includes('/categories')) return { body: cats }
      if (url.includes('/analysis')) {
        return { body: { ...p, status_counts: { fits: 0, attention: 1, over: 1, insufficient: 0 }, worst_month: '2027-01-01', worst_balance_after: '-200.00',
          average_balance_after: '250.00', history_months: [], history_income_avg: '5000.00', history_variable_avg: '3000.00', confidence_notes: [],
          months: [month('2026-12-01', 'attention', '700.00'), month('2027-01-01', 'over', '-200.00')] } }
      }
      return { body: [p] }
    })
    renderPage()
    expect(await screen.findByText('Acima do orçamento em 1 de 2 mês(es).')).toBeInTheDocument()
    expect(screen.getByText('Sobram R$ 700,00')).toBeInTheDocument()
    expect(screen.getByText('Faltam R$ 200,00')).toBeInTheDocument()
    expect(screen.getAllByText('Cabe com atenção').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Acima do orçamento').length).toBeGreaterThan(0)
  })

  it('mostra mensagem de erro quando a API falha', async () => {
    mock((url) => (url.includes('/categories') ? { body: cats } : { status: 500, body: null }))
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent(/servidor|Não foi possível/)
  })
})
