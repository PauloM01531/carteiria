import { TIME_ZONE } from './format'

/** Data de hoje (AAAA-MM-DD) no fuso de Fortaleza. */
export function todayISO(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: TIME_ZONE, year: 'numeric', month: '2-digit', day: '2-digit' }).format(now)
  return parts // en-CA já formata como AAAA-MM-DD
}

export interface YearMonth {
  year: number
  month: number // 1-12
}

export function currentMonth(now: Date = new Date()): YearMonth {
  const [y, m] = todayISO(now).split('-').map(Number)
  return { year: y, month: m }
}

export function shiftMonth({ year, month }: YearMonth, delta: number): YearMonth {
  const idx = year * 12 + (month - 1) + delta
  return { year: Math.floor(idx / 12), month: (idx % 12) + 1 }
}

export function monthRange({ year, month }: YearMonth): { start: string; end: string } {
  const last = new Date(Date.UTC(year, month, 0)).getUTCDate()
  const mm = String(month).padStart(2, '0')
  return { start: `${year}-${mm}-01`, end: `${year}-${mm}-${String(last).padStart(2, '0')}` }
}

const MONTHS = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']

export function monthLabel({ year, month }: YearMonth): string {
  return `${MONTHS[month - 1]} de ${year}`
}
