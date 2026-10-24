import type { BudgetRow, CategoryDiff, CategoryShare, MonthPoint } from '../components/charts'

export type Basis = 'competencia' | 'lancamento' | 'caixa'

export const BASIS_LABEL: Record<Basis, { label: string; help: string }> = {
  competencia: { label: 'Competência', help: 'Lançamentos pela data e compras no cartão pelo mês da fatura.' },
  lancamento: { label: 'Data da compra', help: 'Lançamentos e compras no cartão (valor total) pela data em que aconteceram.' },
  caixa: { label: 'Pagamentos realizados', help: 'Só o que saiu de fato: despesas pagas e pagamentos de fatura.' },
}

export interface Summary {
  start: string
  end: string
  basis: string
  income: string
  expense: string
  balance: string
  savings_rate: string | null
  largest_expense: { description: string; amount: string; day: string; category_name: string; source: string } | null
  top_category: CategoryShare | null
  count: number
}

export interface Commitments {
  reference_date: string
  open_statements: { id: string; card_nickname: string; reference_month: string; due_date: string; remaining: string }[]
  open_statements_total: string
  future_installments_total: string
  future_installments_by_month: { month: string; amount: string }[]
  upcoming_bills: { id: string; name: string; due_date: string; amount: string | null; overdue: boolean }[]
  upcoming_bills_total: string
  pending_expenses_total: string
  total: string
}

export interface Dashboard {
  month: string
  summary: Summary
  previous_summary: Summary
  expense_change_pct: string | null
  cash_balance: string
  balance_after_commitments: string
  month_statements_total: string
  commitments: Commitments
  monthly: MonthPoint[]
  categories: CategoryShare[]
  budgets: BudgetRow[]
  recent: { id: string; kind: 'income' | 'expense'; description: string; amount: string; occurred_on: string; category_name: string; status: string }[]
}

export interface Compare {
  month_a: string
  month_b: string
  basis: string
  income: { previous: string; current: string; diff: string; pct: string | null }
  expense: { previous: string; current: string; diff: string; pct: string | null }
  balance: { previous: string; current: string; diff: string; pct: string | null }
  categories: CategoryDiff[]
}

/** "12.5" -> "+12,5%"; null -> "sem base de comparação" */
export function formatPct(p: string | null, signed = true): string {
  if (p === null) return 'sem base de comparação'
  const n = Number(p)
  return `${signed && n > 0 ? '+' : ''}${p.replace('.', ',')}%`
}
