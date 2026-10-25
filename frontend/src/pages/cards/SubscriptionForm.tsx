import { useState, type FormEvent } from 'react'
import { Alert, Button, ConfirmDialog, Field, SelectField, TextareaField } from '../../components/ui'
import { api, ApiError } from '../../lib/api'
import type { CreditCard, Subscription } from '../../lib/cards'
import { todayISO } from '../../lib/dates'
import type { Category } from '../../lib/finance'
import { parseMoneyInput, toMoneyInput } from '../../lib/money'

const msg = (e: unknown) => (e instanceof ApiError ? e.message : 'Não foi possível concluir.')

export function SubscriptionForm({
  cards,
  categories,
  initial,
  defaultCardId,
  onDone,
}: {
  cards: CreditCard[]
  categories: Category[]
  initial?: Subscription | null
  defaultCardId?: string
  onDone: (message: string) => void
}) {
  const activeCards = cards.filter((c) => c.active || c.id === initial?.card_id)
  const assinaturas = categories.find((c) => c.kind === 'expense' && c.name === 'Assinaturas')
  const [cardId, setCardId] = useState(initial?.card_id ?? defaultCardId ?? activeCards[0]?.id ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [amount, setAmount] = useState(initial ? toMoneyInput(initial.amount) : '')
  const [categoryId, setCategoryId] = useState(initial?.category_id ?? assinaturas?.id ?? '')
  const [day, setDay] = useState(String(initial?.charge_day ?? Number(todayISO().slice(8, 10))))
  const [start, setStart] = useState(initial?.start_date ?? todayISO())
  const [end, setEnd] = useState(initial?.end_date ?? '')
  const [active, setActive] = useState(initial?.active ?? true)
  const [notes, setNotes] = useState(initial?.notes ?? '')
  const [errors, setErrors] = useState<Record<string, string | null>>({})
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [confirm, setConfirm] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const parsed = parseMoneyInput(amount)
    const v = {
      card: cardId ? null : 'Escolha o cartão.',
      description: description.trim() ? null : 'Informe o nome da assinatura.',
      amount: parsed ? null : 'Informe o valor mensal.',
      category: categoryId ? null : 'Escolha uma categoria.',
      day: /^\d{1,2}$/.test(day) && +day >= 1 && +day <= 31 ? null : 'Dia entre 1 e 31.',
      start: start ? null : 'Informe o início.',
      end: end && end < start ? 'Deve ser depois do início.' : null,
    }
    setErrors(v)
    if (Object.values(v).some(Boolean)) return
    setSaving(true)
    setError(null)
    const body = {
      card_id: cardId,
      description: description.trim(),
      amount: parsed,
      category_id: categoryId,
      charge_day: Number(day),
      start_date: start,
      end_date: end || null,
      notes: notes.trim() || null,
      ...(initial ? { active } : {}),
    }
    try {
      await api(initial ? `/card-subscriptions/${initial.id}` : '/card-subscriptions', { method: initial ? 'PATCH' : 'POST', body })
      onDone(initial ? 'Assinatura atualizada. As próximas cobranças usam os novos dados.' : 'Assinatura cadastrada: a cobrança entra sozinha em cada fatura.')
    } catch (err) {
      setError(msg(err))
    } finally {
      setSaving(false)
    }
  }

  async function cancel() {
    if (!initial) return
    try {
      await api(`/card-subscriptions/${initial.id}`, { method: 'DELETE' })
      onDone('Assinatura cancelada. As cobranças já feitas continuam nas faturas.')
    } catch (err) {
      setError(msg(err))
      setConfirm(false)
    }
  }

  if (!activeCards.length) return <Alert kind="info">Cadastre um cartão antes de registrar assinaturas.</Alert>

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {error && <Alert kind="error">{error}</Alert>}
      <SelectField label="Cartão" value={cardId} onChange={(e) => setCardId(e.target.value)} error={errors.card}>
        {activeCards.map((c) => <option key={c.id} value={c.id}>{c.nickname}</option>)}
      </SelectField>
      <Field label="Assinatura" maxLength={200} value={description} onChange={(e) => setDescription(e.target.value)} error={errors.description} placeholder="Ex.: Netflix, Spotify, academia" />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Valor mensal (R$)"
          inputMode="decimal"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          onBlur={() => { const p = parseMoneyInput(amount); if (p) setAmount(toMoneyInput(p)) }}
          error={errors.amount}
          placeholder="0,00"
        />
        <SelectField label="Categoria" value={categoryId} onChange={(e) => setCategoryId(e.target.value)} error={errors.category}>
          <option value="">Selecione…</option>
          {categories.filter((c) => c.kind === 'expense' && (c.active || c.id === initial?.category_id)).map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </SelectField>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Field label="Dia da cobrança" inputMode="numeric" value={day} onChange={(e) => setDay(e.target.value)} error={errors.day} />
        <Field label="Início" type="date" value={start} onChange={(e) => setStart(e.target.value)} error={errors.start} />
        <Field label="Fim (opcional)" type="date" value={end} onChange={(e) => setEnd(e.target.value)} error={errors.end} />
      </div>
      <p className="text-xs text-muted">
        Todo mês, no dia da cobrança, a CarteirIA registra a compra neste cartão e ela entra na fatura correspondente. Nada é cobrado de verdade: é só o registro.
      </p>
      <TextareaField label="Observações (opcional)" maxLength={500} value={notes} onChange={(e) => setNotes(e.target.value)} />
      {initial && (
        <label className="flex items-center gap-2 text-sm font-semibold">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} className="h-4 w-4" />
          Assinatura ativa (desmarque para pausar as próximas cobranças)
        </label>
      )}
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
        {initial ? <Button type="button" variant="ghost" className="text-negative" onClick={() => setConfirm(true)}>Cancelar assinatura</Button> : <span />}
        <Button type="submit" loading={saving}>{initial ? 'Salvar' : 'Adicionar assinatura'}</Button>
      </div>
      <ConfirmDialog open={confirm} title="Cancelar assinatura?" confirmLabel="Cancelar assinatura" danger onConfirm={cancel} onCancel={() => setConfirm(false)}>
        As cobranças futuras deixam de entrar nas faturas. As que já aconteceram continuam no histórico.
      </ConfirmDialog>
    </form>
  )
}
