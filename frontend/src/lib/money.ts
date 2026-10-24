/**
 * Valores digitados em reais ("1.234,56") -> texto decimal para a API ("1234.56").
 * Nada de float: a conversão é feita só com texto.
 */
export function parseMoneyInput(input: string): string | null {
  const s = input.replace(/\s|R\$/g, '')
  if (!s) return null
  let normalized: string
  if (s.includes(',')) {
    // Formato brasileiro: pontos são milhares, vírgula é decimal
    if (!/^\d{1,3}(\.\d{3})*(,\d{1,2})?$|^\d+(,\d{1,2})?$/.test(s)) return null
    normalized = s.replace(/\./g, '').replace(',', '.')
  } else {
    if (!/^\d{1,3}(\.\d{3})+$|^\d+(\.\d{1,2})?$/.test(s)) return null
    // "1.234" com grupo de 3 é milhar; "12.5" é decimal
    normalized = /^\d{1,3}(\.\d{3})+$/.test(s) ? s.replace(/\./g, '') : s
  }
  const [int, dec = ''] = normalized.split('.')
  const intClean = int.replace(/^0+(?=\d)/, '')
  const result = `${intClean}.${dec.padEnd(2, '0')}`
  if (result === '0.00') return null
  if (intClean.length > 10) return null
  return result
}

/** "1234.5" -> "1.234,50" (para preencher o campo ao editar). */
export function toMoneyInput(value: string): string {
  const [int, dec = '00'] = value.split('.')
  const withDots = int.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
  return `${withDots},${dec.padEnd(2, '0').slice(0, 2)}`
}
