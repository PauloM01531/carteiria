import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Alert, Button, ConfirmDialog, Field, Segmented, SelectField, TextareaField } from '../../components/ui'
import { api, ApiError } from '../../lib/api'
import { todayISO } from '../../lib/dates'
import { PAYMENT_METHODS, type Category, type Kind, type Transaction } from '../../lib/finance'
import { parseMoneyInput, toMoneyInput } from '../../lib/money'

interface Props {
  categories: Category[]
  initial?: Transaction | null
  defaultKind?: Kind
  onSaved: (tx: Transaction) => void
  onDeleted: (id: string) => void
}

export function TransactionForm({ categories, initial, defaultKind = 'expense', onSaved, onDeleted }: Props) {
  const [kind, setKind] = useState<Kind>(initial?.kind ?? defaultKind)
  const [description, setDescription] = useState(initial?.description ?? '')
  const [amount, setAmount] = useState(initial ? toMoneyInput(initial.amount) : '')
  const [date, setDate] = useState(initial?.occurred_on ?? todayISO())
  const [categoryId, setCategoryId] = useState(initial?.category_id ?? '')
  const [method, setMethod] = useState(initial?.payment_method ?? 'pix')
  const [status, setStatus] = useState<'settled' | 'pending'>(initial?.status ?? 'settled')
  const [notes, setNotes] = useState(initial?.notes ?? '')
  const [errors, setErrors] = useState<Record<string, string | null>>({})
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const options = categories.filter((c) => c.kind === kind && (c.active || c.id === initial?.category_id))

  function changeKind(k: Kind) {
    setKind(k)
    if (!categories.some((c) => c.id === categoryId && c.kind === k)) setCategoryId('')
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const parsed = parseMoneyInput(amount)
    const v = {
      description: description.trim() ? (description.trim().length > 200 ? 'Use no máximo 200 caracteres.' : null) : 'Informe uma descrição.',
      amount: parsed ? null : 'Informe um valor válido, por exemplo 1.234,56.',
      date: /^\d{4}-\d{2}-\d{2}$/.test(date) ? null : 'Informe a data.',
      category: categoryId ? null : 'Escolha uma categoria.',
      notes: notes.length > 500 ? 'Use no máximo 500 caracteres.' : null,
    }
    setErrors(v)
    if (Object.values(v).some(Boolean)) return
    setSaving(true)
    setError(null)
    const body = {
      kind,
      description: description.trim(),
      amount: parsed,
      occurred_on: date,
      category_id: categoryId,
      payment_method: method,
      status,
      notes: notes.trim() || null,
    }
    try {
      const tx = initial
        ? await api<Transaction>(`/transactions/${initial.id}`, { method: 'PATCH', body })
        : await api<Transaction>('/transactions', { method: 'POST', body })
      onSaved(tx)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Não foi possível salvar.')
    } finally {
      setSaving(false)
    }
  }

  async function doDelete() {
    if (!initial) return
    setDeleting(true)
    try {
      await api(`/transactions/${initial.id}`, { method: 'DELETE' })
      onDeleted(initial.id)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Não foi possível excluir.')
      setConfirmDelete(false)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {error && <Alert kind="error">{error}</Alert>}
      <Segmented
        label="Tipo"
        value={kind}
        onChange={changeKind}
        options={[
          { value: 'expense', label: 'Despesa' },
          { value: 'income', label: 'Receita' },
        ]}
      />
      <Field label="Descrição" maxLength={200} value={description} onChange={(e) => setDescription(e.target.value)} error={errors.description} placeholder={kind === 'expense' ? 'Ex.: Mercado' : 'Ex.: Salário'} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Valor (R$)"
          inputMode="decimal"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          onBlur={() => {
            const p = parseMoneyInput(amount)
            if (p) setAmount(toMoneyInput(p))
          }}
          error={errors.amount}
          placeholder="0,00"
        />
        <Field label="Data" type="date" value={date} onChange={(e) => setDate(e.target.value)} error={errors.date} min="2000-01-01" max="2100-12-31" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <SelectField label="Categoria" value={categoryId} onChange={(e) => setCategoryId(e.target.value)} error={errors.category}>
          <option value="">Selecione…</option>
          {options.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
              {!c.active ? ' (desativada)' : ''}
            </option>
          ))}
        </SelectField>
        <SelectField label={kind === 'expense' ? 'Forma de pagamento' : 'Forma de recebimento'} value={method} onChange={(e) => setMethod(e.target.value)}>
          {Object.entries(PAYMENT_METHODS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </SelectField>
      </div>
      {kind === 'expense' && method === 'credito' && !initial && (
        <Alert kind="info">
          Compras no cartão de crédito ficam melhor em <Link to="/cartoes" className="font-semibold underline">Cartões › Nova compra</Link>:
          lá elas são parceladas e distribuídas nas faturas, sem contar duas vezes.
        </Alert>
      )}
      <div className="flex flex-col gap-1.5">
        <span className="text-sm font-semibold">Situação</span>
        <Segmented
          label="Situação"
          value={status}
          onChange={setStatus}
          options={[
            { value: 'settled', label: kind === 'expense' ? 'Pago' : 'Recebido' },
            { value: 'pending', label: 'Pendente' },
          ]}
        />
      </div>
      <TextareaField label="Observações (opcional)" maxLength={500} value={notes} onChange={(e) => setNotes(e.target.value)} error={errors.notes} />
      <div className="mt-2 flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
        {initial ? (
          <Button type="button" variant="ghost" className="text-negative" onClick={() => setConfirmDelete(true)}>
            Excluir lançamento
          </Button>
        ) : (
          <span />
        )}
        <Button type="submit" loading={saving}>
          {initial ? 'Salvar alterações' : 'Adicionar lançamento'}
        </Button>
      </div>
      <ConfirmDialog
        open={confirmDelete}
        title="Excluir lançamento?"
        confirmLabel="Excluir"
        danger
        loading={deleting}
        onConfirm={doDelete}
        onCancel={() => setConfirmDelete(false)}
      >
        "{initial?.description}" será removido definitivamente.
      </ConfirmDialog>
    </form>
  )
}
