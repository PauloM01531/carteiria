/** Tipos e rótulos de cartões, faturas e contas recorrentes. */
export interface CreditCard {
  id: string
  nickname: string
  institution: string | null
  closing_day: number
  due_day: number
  credit_limit: string | null
  active: boolean
  used_amount: string
  available_limit: string | null
}

export type StatementStatus = 'open' | 'closed' | 'partial' | 'paid' | 'overdue' | 'empty'

export interface Statement {
  id: string
  card_id: string
  card_nickname: string
  reference_month: string
  closing_date: string
  due_date: string
  total: string
  paid: string
  remaining: string
  status: StatementStatus
  items_count: number
}

export interface StatementItem {
  installment_id: string
  purchase_id: string
  description: string
  purchase_date: string
  category_name: string
  number: number
  installments_count: number
  amount: string
  is_subscription?: boolean
}

export interface Payment {
  id: string
  amount: string
  paid_on: string
  notes: string | null
}

export interface StatementDetail extends Statement {
  items: StatementItem[]
  payments: Payment[]
}

export interface Purchase {
  id: string
  card_id: string
  card_nickname: string
  description: string
  total_amount: string
  purchase_date: string
  category_id: string
  category_name: string
  installments_count: number
  first_statement_month: string
  notes: string | null
  subscription_id?: string | null
  installments: { id: string; number: number; amount: string; statement_id: string; reference_month: string }[]
}

export interface Subscription {
  id: string
  card_id: string
  card_nickname: string
  description: string
  amount: string
  category_id: string
  category_name: string
  charge_day: number
  start_date: string
  end_date: string | null
  active: boolean
  notes: string | null
  next_charge: string | null
}

export const STATEMENT_STATUS: Record<StatementStatus, { label: string; cls: string }> = {
  open: { label: 'Aberta', cls: 'bg-surface-2 text-ink' },
  closed: { label: 'Fechada', cls: 'bg-accent-soft text-ink' },
  partial: { label: 'Paga em parte', cls: 'bg-accent-soft text-ink' },
  paid: { label: 'Paga', cls: 'bg-positive/15 text-positive' },
  overdue: { label: 'Vencida', cls: 'bg-negative/15 text-negative' },
  empty: { label: 'Sem lançamentos', cls: 'bg-surface-2 text-muted' },
}

export type OccurrenceStatus = 'pending' | 'due_soon' | 'overdue' | 'paid'

export interface Bill {
  id: string
  name: string
  amount_type: 'fixed' | 'variable'
  expected_amount: string | null
  category_id: string
  category_name: string
  frequency: string
  due_day: number
  start_date: string
  end_date: string | null
  active: boolean
  notes: string | null
}

export interface Occurrence {
  id: string
  bill_id: string
  bill_name: string
  category_name: string
  amount_type: string
  due_date: string
  amount: string | null
  status: OccurrenceStatus
  paid_on: string | null
  transaction_id: string | null
}

export interface OccurrenceList {
  items: Occurrence[]
  summary: { pending_total: string; paid_total: string; overdue_count: number }
}

export const FREQUENCIES: Record<string, string> = {
  monthly: 'Mensal',
  bimonthly: 'Bimestral',
  quarterly: 'Trimestral',
  semiannual: 'Semestral',
  yearly: 'Anual',
}

const MONTHS_SHORT = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']
const MONTHS = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']

/** "2026-11-01" -> "nov/2026" */
export function shortMonth(iso: string): string {
  const [y, m] = iso.split('-').map(Number)
  return `${MONTHS_SHORT[m - 1]}/${y}`
}

/** "2026-11-01" -> "Novembro de 2026" */
export function longMonth(iso: string): string {
  const [y, m] = iso.split('-').map(Number)
  const name = MONTHS[m - 1]
  return `${name.charAt(0).toUpperCase()}${name.slice(1)} de ${y}`
}
