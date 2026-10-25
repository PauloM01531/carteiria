import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { longMonth, shortMonth, type CreditCard } from '../lib/cards'
import type { Category } from '../lib/finance'
import { PurchaseForm } from '../pages/cards/forms'

afterEach(() => vi.unstubAllGlobals())

describe('rótulos de competência', () => {
  it('formata meses', () => {
    expect(shortMonth('2026-11-01')).toBe('nov/2026')
    expect(longMonth('2027-03-01')).toBe('Março de 2027')
  })
})

const card: CreditCard = {
  id: 'k1', nickname: 'Nubank', institution: null, closing_day: 10, due_day: 17, credit_limit: null,
  active: true, used_amount: '0.00', available_limit: null,
}
const cats: Category[] = [{ id: 'c1', name: 'Compras', kind: 'expense', active: true, is_system: true }]

describe('formulário de compra parcelada', () => {
  it('mostra a divisão das parcelas e usa a competência sugerida pelo servidor', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.includes('suggest-statement')) {
        return new Response(JSON.stringify({ reference_month: '2026-11-01', closing_date: '2026-11-10', due_date: '2026-11-17' }))
      }
      return new Response(JSON.stringify({ id: 'p1', ...JSON.parse(String(init?.body)) }), { status: 201 })
    })
    vi.stubGlobal('fetch', fetchMock)
    const onSaved = vi.fn()
    render(
      <MemoryRouter>
        <PurchaseForm cards={[card]} categories={cats} onSaved={onSaved} onDeleted={() => undefined} />
      </MemoryRouter>,
    )
    await userEvent.type(screen.getByLabelText('Descrição'), 'Notebook')
    await userEvent.type(screen.getByLabelText('Valor total (R$)'), '1.200,00')
    await userEvent.clear(screen.getByLabelText('Parcelas'))
    await userEvent.type(screen.getByLabelText('Parcelas'), '12')
    expect(screen.getByText('12x de R$ 100,00')).toBeInTheDocument()
    await userEvent.clear(screen.getByLabelText('Valor total (R$)'))
    await userEvent.type(screen.getByLabelText('Valor total (R$)'), '100,00')
    await userEvent.clear(screen.getByLabelText('Parcelas'))
    await userEvent.type(screen.getByLabelText('Parcelas'), '3')
    expect(screen.getByText('2x de R$ 33,33 + 1x de R$ 33,34')).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Categoria'), 'c1')
    await waitFor(() => expect((screen.getByLabelText('Primeira fatura (competência)') as HTMLInputElement).value).toBe('2026-11'))
    await userEvent.click(screen.getByRole('button', { name: 'Registrar compra' }))
    await waitFor(() => expect(onSaved).toHaveBeenCalled())
    const post = fetchMock.mock.calls.find(([u, i]) => String(u).endsWith('/card-purchases') && i?.method === 'POST')!
    expect(JSON.parse(String(post[1]!.body))).toMatchObject({
      card_id: 'k1', total_amount: '100.00', installments_count: 3, first_statement_month: '2026-11-01', category_id: 'c1',
    })
  })
})

import { SubscriptionForm } from '../pages/cards/SubscriptionForm'

describe('formulário de assinatura no cartão', () => {
  it('sugere a categoria Assinaturas e envia o valor mensal como decimal', async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => new Response(JSON.stringify({ id: 's1', ...JSON.parse(String(init?.body)) }), { status: 201 }))
    vi.stubGlobal('fetch', fetchMock)
    const onDone = vi.fn()
    const categories = [...cats, { id: 'c9', name: 'Assinaturas', kind: 'expense' as const, active: true, is_system: true }]
    render(<SubscriptionForm cards={[card]} categories={categories} onDone={onDone} />)
    expect((screen.getByLabelText('Categoria') as HTMLSelectElement).value).toBe('c9')
    await userEvent.type(screen.getByLabelText('Assinatura'), 'Streaming')
    await userEvent.type(screen.getByLabelText('Valor mensal (R$)'), '39,90')
    await userEvent.clear(screen.getByLabelText('Dia da cobrança'))
    await userEvent.type(screen.getByLabelText('Dia da cobrança'), '5')
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar assinatura' }))
    await waitFor(() => expect(onDone).toHaveBeenCalled())
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]!.body))
    expect(body).toMatchObject({ card_id: 'k1', description: 'Streaming', amount: '39.90', category_id: 'c9', charge_day: 5 })
    expect(body).not.toHaveProperty('user_id')
  })
})
