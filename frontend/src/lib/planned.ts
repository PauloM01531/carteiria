/** Tipos e regras de exibição das compras planejadas. */

export type PlanStatus = 'fits' | 'attention' | 'over' | 'insufficient'

export const PLAN_STATUS: Record<PlanStatus, { label: string; icon: string; cls: string }> = {
  fits: { label: 'Cabe no orçamento', icon: '✓', cls: 'bg-positive/15 text-positive' },
  attention: { label: 'Cabe com atenção', icon: '!', cls: 'bg-accent-soft text-ink' },
  over: { label: 'Acima do orçamento', icon: '✕', cls: 'bg-negative/15 text-negative' },
  insufficient: { label: 'Dados insuficientes', icon: '?', cls: 'bg-surface-2 text-muted' },
}

export interface PlannedPurchase {
  id: string
  name: string
  total_amount: string
  installments_count: number
  first_installment_date: string
  category_id: string
  category_name: string
  notes: string | null
  installment_amount: string
  last_installment_amount: string
  first_month: string
  last_month: string
  overall_status: PlanStatus
  headline: string
}

export interface PlanMonth {
  month: string
  number: number
  installment: string
  income: string | null
  income_source: 'registrada' | 'media' | null
  registered_expenses: string
  card_installments: string
  subscriptions_projected: string
  bills_pending: string
  variable_estimate: string
  other_planned: string
  committed: string
  balance_before: string | null
  balance_after: string | null
  status: PlanStatus
  factors: string[]
  notes: string[]
}

export interface PlanAnalysis {
  name: string
  total_amount: string
  installments_count: number
  installment_amount: string
  last_installment_amount: string
  first_month: string
  last_month: string
  overall_status: PlanStatus
  headline: string
  status_counts: Record<PlanStatus, number>
  worst_month: string | null
  worst_balance_after: string | null
  average_balance_after: string | null
  history_months: string[]
  history_income_avg: string | null
  history_variable_avg: string | null
  confidence_notes: string[]
  months: PlanMonth[]
}

/**
 * Prévia das parcelas com a mesma regra do servidor (centavos inteiros; a diferença vai para a última).
 * `parsed` é o valor já normalizado ("2600.00").
 */
export function installmentPreview(parsed: string, count: number): { first: number; last: number } | null {
  if (!Number.isInteger(count) || count < 1 || count > 72) return null
  const cents = Number(parsed.replace('.', ''))
  const base = Math.floor(cents / count)
  if (base === 0) return null
  return { first: base / 100, last: (cents - base * (count - 1)) / 100 }
}

/** "2026-11-10" + n meses -> "2026-11-01" ... (primeiro dia do mês). */
export function addMonthsISO(isoDate: string, months: number): string {
  const [y, m] = isoDate.split('-').map(Number)
  const idx = y * 12 + (m - 1) + months
  return `${Math.floor(idx / 12)}-${String((idx % 12) + 1).padStart(2, '0')}-01`
}
