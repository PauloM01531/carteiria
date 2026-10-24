/** Formulários de cartão, compra parcelada e pagamento de fatura. */
import { useEffect, useState, type FormEvent } from 'react'
import { Alert, Button, ConfirmDialog, Field, SelectField, TextareaField } from '../../components/ui'
import { api, ApiError } from '../../lib/api'
import { longMonth, type CreditCard, type Purchase } from '../../lib/cards'
import { todayISO } from '../../lib/dates'
import type { Category } from '../../lib/finance'
import { formatBRL, formatDate } from '../../lib/format'
import { parseMoneyInput, toMoneyInput } from '../../lib/money'

const msg = (e: unknown) => (e instanceof ApiError ? e.message : 'Não foi possível concluir.')

// ------------------------------------------------------------------ Cartão
export function CardForm({ initial, onSaved, onDeleted }: { initial?: CreditCard | null; onSaved: () => void; onDeleted: () => void }) {
  const [nickname, setNickname] = useState(initial?.nickname ?? '')
  const [institution, setInstitution] = useState(initial?.institution ?? '')
  const [closing, setClosing] = useState(String(initial?.closing_day ?? ''))
  const [due, setDue] = useState(String(initial?.due_day ?? ''))
  const [limit, setLimit] = useState(initial?.credit_limit ? toMoneyInput(initial.credit_limit) : '')
  const [active, setActive] = useState(initial?.active ?? true)
  const [errors, setErrors] = useState<Record<string, string | null>>({})
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [confirm, setConfirm] = useState(false)

  const day = (v: string) => (/^\d{1,2}$/.test(v) && +v >= 1 && +v <= 31 ? null : 'Informe um dia entre 1 e 31.')

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const parsedLimit = limit.trim() ? parseMoneyInput(limit) : null
    const v = {
      nickname: nickname.trim() ? null : 'Informe um apelido.',
      closing: day(closing),
      due: day(due),
      limit: limit.trim() && !parsedLimit ? 'Valor inválido.' : null,
    }
    setErrors(v)
    if (Object.values(v).some(Boolean)) return
    setSaving(true)
    setError(null)
    const body = {
      nickname: nickname.trim(),
      institution: institution.trim() || null,
      closing_day: Number(closing),
      due_day: Number(due),
      credit_limit: parsedLimit,
      ...(initial ? { active } : {}),
    }
    try {
      await api(initial ? `/cards/${initial.id}` : '/cards', { method: initial ? 'PATCH' : 'POST', body })
      onSaved()
    } catch (err) {
      setError(msg(err))
    } finally {
      setSaving(false)
    }
  }

  async function doDelete() {
    if (!initial) return
    try {
      await api(`/cards/${initial.id}`, { method: 'DELETE' })
      onDeleted()
    } catch (err) {
      setError(msg(err))
      setConfirm(false)
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {error && <Alert kind="error">{error}</Alert>}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Apelido" maxLength={60} value={nickname} onChange={(e) => setNickname(e.target.value)} error={errors.nickname} placeholder="Ex.: Cartão roxo" />
        <Field label="Banco ou instituição" maxLength={60} value={institution} onChange={(e) => setInstitution(e.target.value)} />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Dia de fechamento" inputMode="numeric" value={closing} onChange={(e) => setClosing(e.target.value)} error={errors.closing} />
        <Field label="Dia de vencimento" inputMode="numeric" value={due} onChange={(e) => setDue(e.target.value)} error={errors.due} />
      </div>
      <Field label="Limite (opcional)" inputMode="decimal" value={limit} onChange={(e) => setLimit(e.target.value)} error={errors.limit} placeholder="0,00" />
      {initial && (
        <label className="flex items-center gap-2 text-sm font-semibold">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} className="h-4 w-4 accent-[var(--accent)]" />
          Cartão ativo
        </label>
      )}
      <p className="text-xs text-muted">Mudanças nos dias valem para faturas novas. Faturas já criadas mantêm suas datas.</p>
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
        {initial ? (
          <Button type="button" variant="ghost" className="text-negative" onClick={() => setConfirm(true)}>
            Excluir cartão
          </Button>
        ) : (
          <span />
        )}
        <Button type="submit" loading={saving}>
          {initial ? 'Salvar' : 'Adicionar cartão'}
        </Button>
      </div>
      <ConfirmDialog open={confirm} title="Excluir cartão?" confirmLabel="Excluir" danger onConfirm={doDelete} onCancel={() => setConfirm(false)}>
        Só é possível excluir cartões sem compras. Para cartões com histórico, desmarque "Cartão ativo".
      </ConfirmDialog>
    </form>
  )
}

// ------------------------------------------------------------------ Compra parcelada
export function PurchaseForm({
  cards,
  categories,
  initial,
  defaultCardId,
  onSaved,
  onDeleted,
}: {
  cards: CreditCard[]
  categories: Category[]
  initial?: Purchase | null
  defaultCardId?: string
  onSaved: () => void
  onDeleted: () => void
}) {
  const activeCards = cards.filter((c) => c.active || c.id === initial?.card_id)
  const [cardId, setCardId] = useState(initial?.card_id ?? defaultCardId ?? activeCards[0]?.id ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [amount, setAmount] = useState(initial ? toMoneyInput(initial.total_amount) : '')
  const [date, setDate] = useState(initial?.purchase_date ?? todayISO())
  const [categoryId, setCategoryId] = useState(initial?.category_id ?? '')
  const [count, setCount] = useState(String(initial?.installments_count ?? 1))
  const [firstMonth, setFirstMonth] = useState(initial?.first_statement_month.slice(0, 7) ?? '')
  const [monthTouched, setMonthTouched] = useState(!!initial)
  const [notes, setNotes] = useState(initial?.notes ?? '')
  const [suggestion, setSuggestion] = useState<{ reference_month: string; due_date: string } | null>(null)
  const [errors, setErrors] = useState<Record<string, string | null>>({})
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [confirm, setConfirm] = useState(false)

  // Sugere a competência a partir do fechamento do cartão (o usuário pode alterar).
  useEffect(() => {
    if (!cardId || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return
    let cancelled = false
    api<{ reference_month: string; due_date: string }>(`/cards/${cardId}/suggest-statement?purchase_date=${date}`)
      .then((s) => {
        if (cancelled) return
        setSuggestion(s)
        if (!monthTouched) setFirstMonth(s.reference_month.slice(0, 7))
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [cardId, date, monthTouched])

  const parsed = parseMoneyInput(amount)
  const n = Number(count)
  const preview = (() => {
    if (!parsed || !Number.isInteger(n) || n < 1 || n > 72) return null
    const cents = Number(parsed.replace('.', '')) // centavos inteiros; o servidor refaz o cálculo com decimal exato
    const base = Math.floor(cents / n)
    const last = cents - base * (n - 1)
    return n === 1 ? `1x de ${formatBRL(cents / 100)}` : base === last ? `${n}x de ${formatBRL(base / 100)}` : `${n - 1}x de ${formatBRL(base / 100)} + 1x de ${formatBRL(last / 100)}`
  })()

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const v = {
      card: cardId ? null : 'Escolha o cartão.',
      description: description.trim() ? null : 'Informe a descrição.',
      amount: parsed ? null : 'Informe um valor válido.',
      date: date ? null : 'Informe a data.',
      category: categoryId ? null : 'Escolha uma categoria.',
      count: Number.isInteger(n) && n >= 1 && n <= 72 ? null : 'Entre 1 e 72 parcelas.',
      month: /^\d{4}-\d{2}$/.test(firstMonth) ? null : 'Informe o mês da primeira fatura.',
    }
    setErrors(v)
    if (Object.values(v).some(Boolean)) return
    setSaving(true)
    setError(null)
    const body = {
      card_id: cardId,
      description: description.trim(),
      total_amount: parsed,
      purchase_date: date,
      category_id: categoryId,
      installments_count: n,
      first_statement_month: `${firstMonth}-01`,
      notes: notes.trim() || null,
    }
    try {
      await api(initial ? `/card-purchases/${initial.id}` : '/card-purchases', { method: initial ? 'PATCH' : 'POST', body })
      onSaved()
    } catch (err) {
      setError(msg(err))
    } finally {
      setSaving(false)
    }
  }

  async function doDelete() {
    if (!initial) return
    try {
      await api(`/card-purchases/${initial.id}`, { method: 'DELETE' })
      onDeleted()
    } catch (err) {
      setError(msg(err))
      setConfirm(false)
    }
  }

  const expenseCats = categories.filter((c) => c.kind === 'expense' && (c.active || c.id === initial?.category_id))

  if (!activeCards.length) return <Alert kind="info">Cadastre um cartão antes de registrar compras.</Alert>

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {error && <Alert kind="error">{error}</Alert>}
      <SelectField label="Cartão" value={cardId} onChange={(e) => setCardId(e.target.value)} error={errors.card}>
        {activeCards.map((c) => (
          <option key={c.id} value={c.id}>
            {c.nickname}
          </option>
        ))}
      </SelectField>
      <Field label="Descrição" maxLength={200} value={description} onChange={(e) => setDescription(e.target.value)} error={errors.description} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Valor total (R$)"
          inputMode="decimal"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          onBlur={() => parsed && setAmount(toMoneyInput(parsed))}
          error={errors.amount}
          placeholder="0,00"
        />
        <Field label="Data da compra" type="date" value={date} onChange={(e) => setDate(e.target.value)} error={errors.date} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <SelectField label="Categoria" value={categoryId} onChange={(e) => setCategoryId(e.target.value)} error={errors.category}>
          <option value="">Selecione…</option>
          {expenseCats.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </SelectField>
        <Field label="Parcelas" type="number" min={1} max={72} value={count} onChange={(e) => setCount(e.target.value)} error={errors.count} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Field
          label="Primeira fatura (competência)"
          type="month"
          value={firstMonth}
          onChange={(e) => {
            setFirstMonth(e.target.value)
            setMonthTouched(true)
          }}
          error={errors.month}
        />
        {suggestion && (
          <p className="text-xs text-muted">
            Sugestão pelo fechamento do cartão: {longMonth(suggestion.reference_month)}, com vencimento em {formatDate(suggestion.due_date)}.
            {monthTouched && firstMonth !== suggestion.reference_month.slice(0, 7) && (
              <button type="button" className="ml-1 font-semibold underline" onClick={() => { setFirstMonth(suggestion.reference_month.slice(0, 7)); setMonthTouched(false) }}>
                Usar sugestão
              </button>
            )}
          </p>
        )}
      </div>
      {preview && <p className="tabular rounded-xl bg-surface-2 px-4 py-3 text-sm font-semibold">{preview}</p>}
      <TextareaField label="Observações (opcional)" maxLength={500} value={notes} onChange={(e) => setNotes(e.target.value)} />
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
        {initial ? (
          <Button type="button" variant="ghost" className="text-negative" onClick={() => setConfirm(true)}>
            Excluir compra
          </Button>
        ) : (
          <span />
        )}
        <Button type="submit" loading={saving}>
          {initial ? 'Salvar alterações' : 'Registrar compra'}
        </Button>
      </div>
      <ConfirmDialog open={confirm} title="Excluir compra?" confirmLabel="Excluir" danger onConfirm={doDelete} onCancel={() => setConfirm(false)}>
        A compra e todas as suas parcelas serão removidas das faturas.
      </ConfirmDialog>
    </form>
  )
}

// ------------------------------------------------------------------ Pagamento de fatura
export function PaymentForm({ statementId, remaining, onSaved }: { statementId: string; remaining: string; onSaved: () => void }) {
  const [amount, setAmount] = useState(toMoneyInput(remaining))
  const [date, setDate] = useState(todayISO())
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const parsed = parseMoneyInput(amount)
    if (!parsed) return setError('Informe um valor válido.')
    setSaving(true)
    setError(null)
    try {
      await api(`/statements/${statementId}/payments`, { method: 'POST', body: { amount: parsed, paid_on: date } })
      onSaved()
    } catch (err) {
      setError(msg(err))
    } finally {
      setSaving(false)
    }
  }
  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {error && <Alert kind="error">{error}</Alert>}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Valor pago (R$)" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
        <Field label="Data do pagamento" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </div>
      <p className="text-xs text-muted">Saldo em aberto: {formatBRL(remaining)}. Pagamentos parciais são permitidos.</p>
      <Button type="submit" loading={saving}>
        Registrar pagamento
      </Button>
    </form>
  )
}
