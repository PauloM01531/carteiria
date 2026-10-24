import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Alert, Button, Card, ConfirmDialog, EmptyState, Field, Modal, Segmented, SelectField, Spinner, TextareaField, cx } from '../../components/ui'
import { api, ApiError } from '../../lib/api'
import { FREQUENCIES, type Bill, type Occurrence, type OccurrenceList } from '../../lib/cards'
import { currentMonth, monthLabel, monthRange, shiftMonth, todayISO, type YearMonth } from '../../lib/dates'
import { PAYMENT_METHODS, type Category } from '../../lib/finance'
import { formatBRL, formatDate } from '../../lib/format'
import { parseMoneyInput, toMoneyInput } from '../../lib/money'

const msg = (e: unknown) => (e instanceof ApiError ? e.message : 'Não foi possível concluir.')

const STATE: Record<Occurrence['status'], { label: string; cls: string }> = {
  overdue: { label: 'Atrasada', cls: 'bg-negative/15 text-negative' },
  due_soon: { label: 'Vence em breve', cls: 'bg-accent-soft text-ink' },
  pending: { label: 'Prevista', cls: 'bg-surface-2 text-muted' },
  paid: { label: 'Paga', cls: 'bg-positive/15 text-positive' },
}

function BillForm({ categories, initial, onSaved, onDeleted }: { categories: Category[]; initial?: Bill | null; onSaved: () => void; onDeleted: () => void }) {
  const [name, setName] = useState(initial?.name ?? '')
  const [type, setType] = useState<'fixed' | 'variable'>(initial?.amount_type ?? 'fixed')
  const [amount, setAmount] = useState(initial?.expected_amount ? toMoneyInput(initial.expected_amount) : '')
  const [categoryId, setCategoryId] = useState(initial?.category_id ?? '')
  const [frequency, setFrequency] = useState(initial?.frequency ?? 'monthly')
  const [dueDay, setDueDay] = useState(String(initial?.due_day ?? ''))
  const [start, setStart] = useState(initial?.start_date ?? todayISO().slice(0, 8) + '01')
  const [end, setEnd] = useState(initial?.end_date ?? '')
  const [active, setActive] = useState(initial?.active ?? true)
  const [notes, setNotes] = useState(initial?.notes ?? '')
  const [errors, setErrors] = useState<Record<string, string | null>>({})
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [confirm, setConfirm] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const parsed = amount.trim() ? parseMoneyInput(amount) : null
    const v = {
      name: name.trim() ? null : 'Informe o nome.',
      amount: type === 'fixed' && !parsed ? 'Informe o valor.' : amount.trim() && !parsed ? 'Valor inválido.' : null,
      category: categoryId ? null : 'Escolha uma categoria.',
      dueDay: /^\d{1,2}$/.test(dueDay) && +dueDay >= 1 && +dueDay <= 31 ? null : 'Dia entre 1 e 31.',
      start: start ? null : 'Informe a data de início.',
      end: end && end < start ? 'Deve ser depois do início.' : null,
    }
    setErrors(v)
    if (Object.values(v).some(Boolean)) return
    setSaving(true)
    setError(null)
    const body = {
      name: name.trim(),
      amount_type: type,
      expected_amount: parsed,
      category_id: categoryId,
      frequency,
      due_day: Number(dueDay),
      start_date: start,
      end_date: end || null,
      notes: notes.trim() || null,
      ...(initial ? { active } : {}),
    }
    try {
      await api(initial ? `/bills/${initial.id}` : '/bills', { method: initial ? 'PATCH' : 'POST', body })
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
      await api(`/bills/${initial.id}`, { method: 'DELETE' })
      onDeleted()
    } catch (err) {
      setError(msg(err))
      setConfirm(false)
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {error && <Alert kind="error">{error}</Alert>}
      <Field label="Nome" maxLength={100} value={name} onChange={(e) => setName(e.target.value)} error={errors.name} placeholder="Ex.: Aluguel, Internet, Academia" />
      <div className="flex flex-col gap-1.5">
        <span className="text-sm font-semibold">Valor</span>
        <Segmented label="Tipo de valor" value={type} onChange={setType} options={[{ value: 'fixed', label: 'Fixo' }, { value: 'variable', label: 'Variável' }]} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={type === 'fixed' ? 'Valor (R$)' : 'Valor estimado (opcional)'} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} error={errors.amount} placeholder="0,00" />
        <SelectField label="Categoria" value={categoryId} onChange={(e) => setCategoryId(e.target.value)} error={errors.category}>
          <option value="">Selecione…</option>
          {categories.filter((c) => c.kind === 'expense' && (c.active || c.id === initial?.category_id)).map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </SelectField>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <SelectField label="Periodicidade" value={frequency} onChange={(e) => setFrequency(e.target.value)}>
          {Object.entries(FREQUENCIES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </SelectField>
        <Field label="Dia de vencimento" inputMode="numeric" value={dueDay} onChange={(e) => setDueDay(e.target.value)} error={errors.dueDay} />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Início" type="date" value={start} onChange={(e) => setStart(e.target.value)} error={errors.start} />
        <Field label="Fim (opcional)" type="date" value={end} onChange={(e) => setEnd(e.target.value)} error={errors.end} />
      </div>
      <TextareaField label="Observações (opcional)" maxLength={500} value={notes} onChange={(e) => setNotes(e.target.value)} />
      {initial && (
        <label className="flex items-center gap-2 text-sm font-semibold">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} className="h-4 w-4" />
          Conta ativa (desmarque para parar de gerar previsões)
        </label>
      )}
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
        {initial ? <Button type="button" variant="ghost" className="text-negative" onClick={() => setConfirm(true)}>Excluir conta</Button> : <span />}
        <Button type="submit" loading={saving}>{initial ? 'Salvar' : 'Adicionar conta'}</Button>
      </div>
      <ConfirmDialog open={confirm} title="Excluir conta recorrente?" confirmLabel="Excluir" danger onConfirm={doDelete} onCancel={() => setConfirm(false)}>
        As previsões serão removidas. Pagamentos já registrados continuam em Lançamentos.
      </ConfirmDialog>
    </form>
  )
}

function PayForm({ occ, onSaved }: { occ: Occurrence; onSaved: () => void }) {
  const [amount, setAmount] = useState(occ.amount ? toMoneyInput(occ.amount) : '')
  const [date, setDate] = useState(todayISO())
  const [method, setMethod] = useState('pix')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const parsed = parseMoneyInput(amount)
    if (!parsed) return setError('Informe o valor pago.')
    setSaving(true)
    setError(null)
    try {
      await api(`/bills/occurrences/${occ.id}/pay`, { method: 'POST', body: { paid_on: date, amount: parsed, payment_method: method } })
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
      <p className="text-sm text-muted">{occ.bill_name} · vencimento {formatDate(occ.due_date)}</p>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Valor pago (R$)" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
        <Field label="Data do pagamento" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </div>
      <SelectField label="Forma de pagamento" value={method} onChange={(e) => setMethod(e.target.value)}>
        {Object.entries(PAYMENT_METHODS).filter(([k]) => k !== 'credito').map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </SelectField>
      <p className="text-xs text-muted">Ao confirmar, o pagamento entra em Lançamentos como despesa paga.</p>
      <Button type="submit" loading={saving}>Confirmar pagamento</Button>
    </form>
  )
}

export default function BillsPage() {
  const [month, setMonth] = useState<YearMonth>(currentMonth())
  const [data, setData] = useState<OccurrenceList | null>(null)
  const [bills, setBills] = useState<Bill[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [modal, setModal] = useState<null | { type: 'bill'; bill: Bill | null } | { type: 'pay'; occ: Occurrence }>(null)
  const [undo, setUndo] = useState<Occurrence | null>(null)

  const load = useCallback(async () => {
    const { start, end } = monthRange(month)
    setData(null)
    try {
      const [occ, list] = await Promise.all([api<OccurrenceList>(`/bills/occurrences?start=${start}&end=${end}`), api<Bill[]>('/bills')])
      setData(occ)
      setBills(list)
    } catch (e) {
      setError(msg(e))
    }
  }, [month])

  useEffect(() => {
    load()
  }, [load])
  useEffect(() => {
    api<Category[]>('/categories?include_inactive=true').then(setCategories).catch(() => undefined)
  }, [])

  const close = useCallback(() => setModal(null), [])
  function done(m: string) {
    setModal(null)
    setNotice(m)
    setTimeout(() => setNotice(null), 3500)
    load()
  }
  async function doUndo() {
    if (!undo) return
    try {
      await api(`/bills/occurrences/${undo.id}/unpay`, { method: 'POST' })
      done('Pagamento desfeito; o lançamento foi removido.')
    } catch (e) {
      setError(msg(e))
    } finally {
      setUndo(null)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">Contas fixas</h1>
          <p className="mt-1 text-sm text-muted">Aluguel, energia, assinaturas e outras contas que se repetem.</p>
        </div>
        <Button onClick={() => setModal({ type: 'bill', bill: null })}>+ Nova conta</Button>
      </header>

      <div className="flex items-center gap-1">
        <button type="button" aria-label="Mês anterior" onClick={() => setMonth(shiftMonth(month, -1))} className="grid h-10 w-10 place-items-center rounded-xl hover:bg-surface-2">‹</button>
        <p className="min-w-44 text-center font-display text-lg font-semibold">{monthLabel(month)}</p>
        <button type="button" aria-label="Próximo mês" onClick={() => setMonth(shiftMonth(month, 1))} className="grid h-10 w-10 place-items-center rounded-xl hover:bg-surface-2">›</button>
      </div>

      {notice && <Alert kind="success">{notice}</Alert>}
      {error && <Alert kind="error">{error}</Alert>}

      {data === null ? (
        <Spinner />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:gap-4">
            <Card className="p-4 sm:p-5">
              <p className="text-sm text-muted">A pagar no mês</p>
              <p className="tabular mt-1 font-display text-xl font-semibold sm:text-2xl">{formatBRL(data.summary.pending_total)}</p>
              {data.summary.overdue_count > 0 && <p className="mt-1 text-xs font-semibold text-negative">{data.summary.overdue_count} atrasada(s)</p>}
            </Card>
            <Card className="p-4 sm:p-5">
              <p className="text-sm text-muted">Já pago</p>
              <p className="tabular mt-1 font-display text-xl font-semibold text-positive sm:text-2xl">{formatBRL(data.summary.paid_total)}</p>
            </Card>
          </div>
          <p className="-mt-3 text-xs text-muted">Contas previstas não entram como despesa até serem marcadas como pagas.</p>

          {data.items.length === 0 ? (
            <EmptyState title={bills.length ? 'Nenhuma conta neste mês' : 'Nenhuma conta cadastrada'} action={!bills.length ? <Button onClick={() => setModal({ type: 'bill', bill: null })}>Cadastrar conta</Button> : undefined}>
              {bills.length ? 'Nenhum vencimento previsto para este mês.' : 'Cadastre suas contas que se repetem para acompanhar o que está pago, pendente e próximo do vencimento.'}
            </EmptyState>
          ) : (
            <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
              {data.items.map((o) => (
                <li key={o.id} className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-2 font-semibold">
                      {o.bill_name}
                      <span className={cx('rounded-full px-2.5 py-0.5 text-xs font-semibold', STATE[o.status].cls)}>{STATE[o.status].label}</span>
                    </p>
                    <p className="text-sm text-muted">
                      Vence {formatDate(o.due_date)} · {o.category_name}
                      {o.paid_on && ` · paga em ${formatDate(o.paid_on)}`}
                    </p>
                  </div>
                  <div className="flex items-center justify-between gap-3 sm:justify-end">
                    <span className="tabular font-semibold">{o.amount ? formatBRL(o.amount) : 'Valor variável'}</span>
                    {o.status === 'paid' ? (
                      <Button variant="ghost" className="min-h-9 px-3" onClick={() => setUndo(o)}>Desfazer</Button>
                    ) : (
                      <Button className="min-h-9 px-3" onClick={() => setModal({ type: 'pay', occ: o })}>Marcar como paga</Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}

          {bills.length > 0 && (
            <Card>
              <h2 className="font-display text-xl font-semibold">Contas cadastradas</h2>
              <ul className="mt-3 divide-y divide-line">
                {bills.map((b) => (
                  <li key={b.id}>
                    <button type="button" onClick={() => setModal({ type: 'bill', bill: b })} className={cx('flex w-full items-center justify-between gap-3 py-3 text-left text-sm hover:bg-surface-2', !b.active && 'opacity-60')}>
                      <span className="min-w-0">
                        <span className="block truncate font-semibold">{b.name}{!b.active && ' (inativa)'}</span>
                        <span className="block text-muted">{FREQUENCIES[b.frequency]} · dia {b.due_day} · {b.category_name}</span>
                      </span>
                      <span className="tabular shrink-0">{b.expected_amount ? formatBRL(b.expected_amount) : 'variável'}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </>
      )}

      <Modal open={modal?.type === 'bill'} title={modal?.type === 'bill' && modal.bill ? 'Editar conta' : 'Nova conta recorrente'} onClose={close}>
        {modal?.type === 'bill' && <BillForm categories={categories} initial={modal.bill} onSaved={() => done('Conta salva.')} onDeleted={() => done('Conta excluída.')} />}
      </Modal>
      <Modal open={modal?.type === 'pay'} title="Marcar como paga" onClose={close}>
        {modal?.type === 'pay' && <PayForm occ={modal.occ} onSaved={() => done('Pagamento registrado em Lançamentos.')} />}
      </Modal>
      <ConfirmDialog open={!!undo} title="Desfazer pagamento?" confirmLabel="Desfazer" onConfirm={doUndo} onCancel={() => setUndo(null)}>
        A conta volta a ficar pendente e o lançamento de despesa criado no pagamento será excluído.
      </ConfirmDialog>
    </div>
  )
}
