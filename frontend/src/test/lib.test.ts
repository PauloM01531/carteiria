import { describe, expect, it } from 'vitest'
import { formatBRL, formatDate, formatDateTime } from '../lib/format'
import { parseError } from '../lib/api'
import { passwordStrength, validateEmail, validateName, validatePassword } from '../lib/validation'

describe('formatação brasileira', () => {
  it('formata reais', () => {
    expect(formatBRL(1234.56)).toBe('R$ 1.234,56')
    expect(formatBRL('100.00')).toBe('R$ 100,00')
    expect(formatBRL(0)).toBe('R$ 0,00')
    expect(formatBRL(-50.5)).toBe('-R$ 50,50')
  })
  it('formata datas no fuso de Fortaleza (UTC-3)', () => {
    // 02:30 UTC do dia 1º ainda é dia 31 em Fortaleza
    expect(formatDate('2026-11-01T02:30:00Z')).toBe('31/10/2026')
    expect(formatDate('2026-10-23')).toBe('23/10/2026')
    expect(formatDateTime('2026-10-23T15:05:00Z')).toBe('23/10/2026 às 12:05')
  })
})

describe('validações', () => {
  it('e-mail', () => {
    expect(validateEmail('')).toBeTruthy()
    expect(validateEmail('ana@')).toBeTruthy()
    expect(validateEmail('ana@exemplo.com.br')).toBeNull()
  })
  it('senha', () => {
    expect(validatePassword('curta1')).toBeTruthy()
    expect(validatePassword('somenteletras')).toBeTruthy()
    expect(validatePassword('ana@ex.com12', 'ANA@ex.com12')).toBeTruthy()
    expect(validatePassword('SenhaForte123')).toBeNull()
    expect(passwordStrength('SenhaForte123!@#')).toBe(4)
  })
  it('nome', () => {
    expect(validateName('a')).toBeTruthy()
    expect(validateName('<script>')).toBeTruthy()
    expect(validateName('Ana')).toBeNull()
  })
})

describe('erros da API', () => {
  it('usa a mensagem do backend', () => {
    const e = parseError(403, { detail: { code: 'pending_approval', message: 'Aguarde.' } })
    expect(e.code).toBe('pending_approval')
    expect(e.message).toBe('Aguarde.')
  })
  it('mensagens padrão sem detalhes técnicos', () => {
    expect(parseError(500, null).message).toMatch(/servidor/)
    expect(parseError(429, null).code).toBe('rate_limited')
  })
})

import { formatPct } from '../lib/reports'

describe('percentuais', () => {
  it('formata variação e trata ausência de base', () => {
    expect(formatPct('12.5')).toBe('+12,5%')
    expect(formatPct('-3.0')).toBe('-3,0%')
    expect(formatPct(null)).toBe('sem base de comparação')
  })
})
