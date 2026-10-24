/** Formatação no padrão brasileiro, com fuso de referência America/Fortaleza. */
export const TIME_ZONE = 'America/Fortaleza'

const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })

/** Aceita número ou string decimal vinda da API ("1234.56"). */
export function formatBRL(value: number | string): string {
  const n = typeof value === 'string' ? Number(value) : value
  return brl.format(Number.isFinite(n) ? n : 0).replace(/ /g, ' ')
}

const dateFmt = new Intl.DateTimeFormat('pt-BR', { timeZone: TIME_ZONE, day: '2-digit', month: '2-digit', year: 'numeric' })
const dateTimeFmt = new Intl.DateTimeFormat('pt-BR', {
  timeZone: TIME_ZONE,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

/** Data/hora ISO (UTC) -> DD/MM/AAAA no fuso de Fortaleza. Datas puras (AAAA-MM-DD) não mudam de dia. */
export function formatDate(iso: string): string {
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
    const [y, m, d] = iso.split('-')
    return `${d}/${m}/${y}`
  }
  return dateFmt.format(new Date(iso))
}

export function formatDateTime(iso: string): string {
  return dateTimeFmt.format(new Date(iso)).replace(',', ' às')
}
