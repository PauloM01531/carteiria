/** Tipos e rótulos compartilhados das telas financeiras. */
export type Kind = 'income' | 'expense'

export interface Category {
  id: string
  name: string
  kind: Kind
  active: boolean
  is_system: boolean
}

export interface Transaction {
  id: string
  kind: Kind
  description: string
  amount: string
  occurred_on: string
  category_id: string
  category_name: string
  payment_method: string
  status: 'settled' | 'pending'
  notes: string | null
}

export interface Totals {
  income: string
  expense: string
  balance: string
  count: number
}

export interface TransactionPage {
  items: Transaction[]
  total: number
  page: number
  page_size: number
  totals: Totals
}

export const PAYMENT_METHODS: Record<string, string> = {
  pix: 'Pix',
  dinheiro: 'Dinheiro',
  debito: 'Cartão de débito',
  credito: 'Cartão de crédito',
  boleto: 'Boleto',
  transferencia: 'Transferência',
  outro: 'Outro',
}

export function statusLabel(kind: Kind, status: string): string {
  if (status === 'pending') return 'Pendente'
  return kind === 'income' ? 'Recebido' : 'Pago'
}
