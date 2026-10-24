import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { currentMonth, monthRange, shiftMonth, todayISO } from '../lib/dates'
import type { Category } from '../lib/finance'
import { parseMoneyInput, toMoneyInput } from '../lib/money'
import { TransactionForm } from '../pages/transactions/TransactionForm'

describe('valores em reais', () => {
  it('converte o que o usuário digita em decimal exato', () => {
    expect(parseMoneyInput('1.234,56')).toBe('1234.56')
    expect(parseMoneyInput('R$ 1.234,5')).toBe('1234.50')
    expect(parseMoneyInput('0,10')).toBe('0.10')
    expect(parseMoneyInput('100')).toBe('100.00')
    expect(parseMoneyInput('12.5')).toBe('12.50')
    expect(parseMoneyInput('1.200')).toBe('1200.00')
    expect(parseMoneyInput('1200,00')).toBe('1200.00')
  })
  it('recusa valores inválidos', () => {
    for (const v of ['', '0', '0,00', 'abc', '1,234', '-5', '1,2,3', '12345678901,00']) expect(parseMoneyInput(v)).toBeNull()
  })
  it('formata para edição', () => {
    expect(toMoneyInput('1234.56')).toBe('1.234,56')
    expect(toMoneyInput('1200000.00')).toBe('1.200.000,00')
  })
})

describe('datas no fuso de Fortaleza', () => {
  it('hoje considera UTC-3', () => {
    expect(todayISO(new Date('2026-11-01T02:00:00Z'))).toBe('2026-10-31')
    expect(currentMonth(new Date('2026-11-01T02:00:00Z'))).toEqual({ year: 2026, month: 10 })
  })
  it('intervalos de mês', () => {
    expect(monthRange({ year: 2026, month: 2 })).toEqual({ start: '2026-02-01', end: '2026-02-28' })
    expect(monthRange({ year: 2028, month: 2 }).end).toBe('2028-02-29')
    expect(shiftMonth({ year: 2026, month: 1 }, -1)).toEqual({ year: 2025, month: 12 })
    expect(shiftMonth({ year: 2026, month: 12 }, 1)).toEqual({ year: 2027, month: 1 })
  })
})

const cats: Category[] = [
  { id: 'c1', name: 'Alimentação', kind: 'expense', active: true, is_system: true },
  { id: 'c2', name: 'Salário', kind: 'income', active: true, is_system: true },
]

describe('formulário de lançamento', () => {
  it('valida e envia o valor como texto decimal, sem identidade do usuário', async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) =>
      new Response(JSON.stringify({ id: 't1', ...JSON.parse(String(init?.body)) }), { status: 201 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const onSaved = vi.fn()
    render(<TransactionForm categories={cats} onSaved={onSaved} onDeleted={() => undefined} />)

    await userEvent.click(screen.getByRole('button', { name: 'Adicionar lançamento' }))
    expect(screen.getByText('Informe uma descrição.')).toBeInTheDocument()
    expect(screen.getByText('Escolha uma categoria.')).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()

    await userEvent.type(screen.getByLabelText('Descrição'), 'Mercado')
    await userEvent.type(screen.getByLabelText('Valor (R$)'), '1.234,56')
    await userEvent.selectOptions(screen.getByLabelText('Categoria'), 'c1')
    // Só categorias de despesa aparecem para despesa
    expect(screen.queryByRole('option', { name: 'Salário' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar lançamento' }))

    await waitFor(() => expect(onSaved).toHaveBeenCalled())
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]!.body))
    expect(body).toMatchObject({ kind: 'expense', description: 'Mercado', amount: '1234.56', category_id: 'c1', payment_method: 'pix', status: 'settled' })
    expect(body).not.toHaveProperty('user_id')
    vi.unstubAllGlobals()
  })
})
