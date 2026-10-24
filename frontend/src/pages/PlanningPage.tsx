/** Orçamentos mensais por categoria e metas financeiras. */
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { BudgetBars, type BudgetRow } from '../components/charts'
import { Alert, Button, Card, ConfirmDialog, EmptyState, Field, Modal, Segmented, SelectField, Spinner, TextareaField, cx } from '../components/ui'
import { api, ApiError } from '../lib/api'
import { currentMonth, monthLabel, shiftMonth, todayISO, type YearMonth } from '../lib/dates'
import type { Category } from '../lib/finance'
import { formatBRL, formatDate } from '../lib/format'
import { parseMoneyInput, toMoneyInput } from '../lib/money'

const msg = (e: unknown) => (e instanceof ApiError ? e.message : 'Não foi possível concluir.')
const iso = (m: YearMonth) => `${m.year}-${String(m.month).padStart(2, '0')}-01`

interface Budget extends BudgetRow {
  category_id: string
  month: string
  previous_months: { month: string; spent: string }[]
  previous_average: string
}

interface Goal {
  id: string
  name: string
  target_amount: string
  deadline: string | null
  notes: string | null
  saved: string
  remaining: string
  percent: string
  status: 'achieved' | 'late' | 'in_progress'
  months_left: number | null
  monthly_needed: string | null
  contributions: { id: string; amount: string; contributed_on: string; notes: string | null }[]
}

// ------------------------------------------------------------------ Orçamentos
function Budgets() {
  const [month, setMonth] = useState<YearMonth>(currentMonth())
  const [items, setItems] = useState<Budget[] | null>(null)
  const [categories, setCategories] = useState<Category[]>([])
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [editing, setEditing] = useState<Budget | 'new' | null>(null)

  const load = useCallback(() => {
    setItems(null)
    api<Budget[]>(`/budgets?month=${iso(month)}`).then(setItems).catch((e) => setError(msg(e)))
  }, [month])
  useEffect(() => { load() }, [load])
  useEffect(() => { api<Category[]>('/categories?kind=expense').then(setCategories).catch(() => undefined) }, [])

  async function copyPrevious() {
    try {
      const r = await api<{ message: string }>('/budgets/copy', { method: 'POST', body: { source_month: iso(shiftMonth(month, -1)), target_month: iso(month) } })
      setNotice(r.message)
      load()
    } catch (e) {
      setError(msg(e))
    }
  }
  const close = useCallback(() => setEditing(null), [])

  const warnings = (items ?? []).filter((b) => b.status !== 'ok')

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1">
          <button type="button" aria-label="Mês anterior" onClick={() => setMonth(shiftMonth(month, -1))} className="grid h-10 w-10 place-items-center rounded-xl hover:bg-surface-2">‹</button>
          <p className="min-w-44 text-center font-display text-lg font-semibold">{monthLabel(month)}</p>
          <button type="button" aria-label="Próximo mês" onClick={() => setMonth(shiftMonth(month, 1))} className="grid h-10 w-10 place-items-center rounded-xl hover:bg-surface-2">›</button>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={copyPrevious}>Copiar do mês anterior</Button>
          <Button onClick={() => setEditing('new')}>+ Orçamento</Button>
        </div>
      </div>
      {notice && <Alert kind="success">{notice}</Alert>}
      {error && <Alert kind="error">{error}</Alert>}
      {warnings.length > 0 && (
        <Alert kind="error">
          <strong>Atenção:</strong> {warnings.map((w) => `${w.category_name} (${w.percent.replace('.', ',')}%)`).join(', ')} {warnings.length === 1 ? 'está' : 'estão'} perto ou acima do limite.
        </Alert>
      )}
      {items === null ? (
        <Spinner />
      ) : items.length === 0 ? (
        <EmptyState title="Nenhum orçamento neste mês" action={<Button onClick={() => setEditing('new')}>Definir um limite</Button>}>
          Defina quanto quer gastar por categoria, por exemplo R$ 500,00 em Alimentação. Compras no cartão contam pelo mês da fatura.
        </EmptyState>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
          <Card>
            <BudgetBars data={items} onSelect={(b) => setEditing(b as Budget)} />
          </Card>
          <Card>
            <h3 className="font-display text-lg font-semibold">Comparação com meses anteriores</h3>
            <div className="mt-3 overflow-x-auto">
              <table className="tabular w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-line text-muted">
                    <th className="py-1.5 pr-3 font-semibold">Categoria</th>
                    <th className="py-1.5 pr-3 font-semibold">Este mês</th>
                    <th className="py-1.5 font-semibold">Média 3 meses</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((b) => (
                    <tr key={b.id} className="border-b border-line/60">
                      <td className="py-1.5 pr-3">{b.category_name}</td>
                      <td className="py-1.5 pr-3">{formatBRL(b.spent)}</td>
                      <td className="py-1.5">{formatBRL(b.previous_average)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
      <Modal open={editing !== null} title={editing === 'new' ? 'Novo orçamento' : 'Editar orçamento'} onClose={close}>
        {editing !== null && (
          <BudgetForm
            month={month}
            categories={categories.filter((c) => editing !== 'new' || !(items ?? []).some((b) => b.category_id === c.id))}
            initial={editing === 'new' ? null : editing}
            onDone={(m) => { setEditing(null); setNotice(m); load() }}
          />
        )}
      </Modal>
    </div>
  )
}

function BudgetForm({ month, categories, initial, onDone }: { month: YearMonth; categories: Category[]; initial: Budget | null; onDone: (m: string) => void }) {
  const [categoryId, setCategoryId] = useState(initial?.category_id ?? '')
  const [limit, setLimit] = useState(initial ? toMoneyInput(initial.limit_amount) : '')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [confirm, setConfirm] = useState(false)
  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const parsed = parseMoneyInput(limit)
    if (!initial && !categoryId) return setError('Escolha a categoria.')
    if (!parsed) return setError('Informe um limite válido.')
    setSaving(true)
    setError(null)
    try {
      if (initial) await api(`/budgets/${initial.id}`, { method: 'PATCH', body: { limit_amount: parsed } })
      else await api('/budgets', { method: 'POST', body: { category_id: categoryId, month: iso(month), limit_amount: parsed } })
      onDone('Orçamento salvo.')
    } catch (err) {
      setError(msg(err))
    } finally {
      setSaving(false)
    }
  }
  async function remove() {
    if (!initial) return
    try {
      await api(`/budgets/${initial.id}`, { method: 'DELETE' })
      onDone('Orçamento excluído.')
    } catch (err) {
      setError(msg(err))
    }
  }
  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {error && <Alert kind="error">{error}</Alert>}
      {initial ? (
        <p className="font-semibold">{initial.category_name} · {monthLabel(month)}</p>
      ) : (
        <SelectField label="Categoria" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
          <option value="">Selecione…</option>
          {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </SelectField>
      )}
      <Field label="Limite do mês (R$)" inputMode="decimal" value={limit} onChange={(e) => setLimit(e.target.value)} placeholder="500,00" />
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
        {initial ? <Button type="button" variant="ghost" className="text-negative" onClick={() => setConfirm(true)}>Excluir</Button> : <span />}
        <Button type="submit" loading={saving}>Salvar</Button>
      </div>
      <ConfirmDialog open={confirm} title="Excluir orçamento?" confirmLabel="Excluir" danger onConfirm={remove} onCancel={() => setConfirm(false)}>
        O limite deste mês será removido. Seus lançamentos não são afetados.
      </ConfirmDialog>
    </form>
  )
}

// ------------------------------------------------------------------ Metas
const GOAL_STATUS = {
  achieved: { label: 'Meta atingida', cls: 'bg-positive/15 text-positive' },
  late: { label: 'Prazo vencido', cls: 'bg-negative/15 text-negative' },
  in_progress: { label: 'Em andamento', cls: 'bg-surface-2 text-ink' },
}

function Goals() {
  const [items, setItems] = useState<Goal[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [modal, setModal] = useState<null | { type: 'goal'; goal: Goal | null } | { type: 'move'; goal: Goal }>(null)
  const load = useCallback(() => { api<Goal[]>('/goals').then(setItems).catch((e) => setError(msg(e))) }, [])
  useEffect(() => { load() }, [load])
  const close = useCallback(() => setModal(null), [])
  const done = () => { setModal(null); load() }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end"><Button onClick={() => setModal({ type: 'goal', goal: null })}>+ Nova meta</Button></div>
      {error && <Alert kind="error">{error}</Alert>}
      {items === null ? (
        <Spinner />
      ) : items.length === 0 ? (
        <EmptyState title="Nenhuma meta ainda" action={<Button onClick={() => setModal({ type: 'goal', goal: null })}>Criar meta</Button>}>
          Defina um valor e um prazo, como uma reserva de emergência, e registre os aportes para acompanhar o progresso.
        </EmptyState>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {items.map((g) => (
            <Card key={g.id}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h3 className="font-display text-xl font-semibold">{g.name}</h3>
                  <p className="text-sm text-muted">{g.deadline ? `Prazo: ${formatDate(g.deadline)}` : 'Sem prazo'}</p>
                </div>
                <span className={cx('rounded-full px-2.5 py-1 text-xs font-semibold', GOAL_STATUS[g.status].cls)}>{GOAL_STATUS[g.status].label}</span>
              </div>
              <div className="mt-4 h-3 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-valuenow={Number(g.percent)} aria-valuemin={0} aria-valuemax={100} aria-label={`Progresso de ${g.name}`}>
                <div className="h-full rounded-full bg-positive" style={{ width: `${Math.min(100, Number(g.percent))}%` }} />
              </div>
              <p className="tabular mt-2 text-sm">
                <strong>{formatBRL(g.saved)}</strong> de {formatBRL(g.target_amount)} · {g.percent.replace('.', ',')}%
              </p>
              {g.monthly_needed && g.status !== 'achieved' && (
                <p className="tabular mt-1 text-xs text-muted">Para chegar no prazo: cerca de {formatBRL(g.monthly_needed)} por mês{g.months_left ? ` (${g.months_left} meses)` : ''}.</p>
              )}
              <div className="mt-4 flex gap-2">
                <Button className="min-h-9 px-3" onClick={() => setModal({ type: 'move', goal: g })}>Aporte / retirada</Button>
                <Button variant="ghost" className="min-h-9 px-3" onClick={() => setModal({ type: 'goal', goal: g })}>Editar</Button>
              </div>
              {g.contributions.length > 0 && (
                <details className="mt-3 text-sm">
                  <summary className="cursor-pointer text-muted">Histórico ({g.contributions.length})</summary>
                  <ul className="mt-2 divide-y divide-line">
                    {[...g.contributions].reverse().map((c) => (
                      <li key={c.id} className="flex items-center justify-between gap-2 py-1.5">
                        <span>{formatDate(c.contributed_on)}{c.notes ? ` · ${c.notes}` : ''}</span>
                        <span className="flex items-center gap-2">
                          <span className={cx('tabular font-semibold', Number(c.amount) < 0 && 'text-negative')}>{formatBRL(c.amount)}</span>
                          <button type="button" className="text-xs text-muted underline" onClick={() => api(`/goals/${g.id}/contributions/${c.id}`, { method: 'DELETE' }).then(load).catch((e) => setError(msg(e)))}>remover</button>
                        </span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </Card>
          ))}
        </div>
      )}
      <Modal open={modal?.type === 'goal'} title={modal?.type === 'goal' && modal.goal ? 'Editar meta' : 'Nova meta'} onClose={close}>
        {modal?.type === 'goal' && <GoalForm initial={modal.goal} onDone={done} />}
      </Modal>
      <Modal open={modal?.type === 'move'} title="Aporte ou retirada" onClose={close}>
        {modal?.type === 'move' && <MoveForm goal={modal.goal} onDone={done} />}
      </Modal>
    </div>
  )
}

function GoalForm({ initial, onDone }: { initial: Goal | null; onDone: () => void }) {
  const [name, setName] = useState(initial?.name ?? '')
  const [target, setTarget] = useState(initial ? toMoneyInput(initial.target_amount) : '')
  const [deadline, setDeadline] = useState(initial?.deadline ?? '')
  const [notes, setNotes] = useState(initial?.notes ?? '')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [confirm, setConfirm] = useState(false)
  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const parsed = parseMoneyInput(target)
    if (!name.trim()) return setError('Informe o nome da meta.')
    if (!parsed) return setError('Informe o valor desejado.')
    setSaving(true)
    setError(null)
    const body = { name: name.trim(), target_amount: parsed, deadline: deadline || null, notes: notes.trim() || null }
    try {
      await api(initial ? `/goals/${initial.id}` : '/goals', { method: initial ? 'PATCH' : 'POST', body })
      onDone()
    } catch (err) {
      setError(msg(err))
    } finally {
      setSaving(false)
    }
  }
  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {error && <Alert kind="error">{error}</Alert>}
      <Field label="Nome" maxLength={100} value={name} onChange={(e) => setName(e.target.value)} placeholder="Ex.: Reserva de emergência" />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Valor desejado (R$)" inputMode="decimal" value={target} onChange={(e) => setTarget(e.target.value)} />
        <Field label="Prazo (opcional)" type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
      </div>
      <TextareaField label="Observações (opcional)" maxLength={500} value={notes} onChange={(e) => setNotes(e.target.value)} />
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
        {initial ? <Button type="button" variant="ghost" className="text-negative" onClick={() => setConfirm(true)}>Excluir meta</Button> : <span />}
        <Button type="submit" loading={saving}>Salvar</Button>
      </div>
      <ConfirmDialog open={confirm} title="Excluir meta?" confirmLabel="Excluir" danger onConfirm={() => initial && api(`/goals/${initial.id}`, { method: 'DELETE' }).then(onDone).catch((e) => setError(msg(e)))} onCancel={() => setConfirm(false)}>
        A meta e o histórico de aportes serão removidos.
      </ConfirmDialog>
    </form>
  )
}

function MoveForm({ goal, onDone }: { goal: Goal; onDone: () => void }) {
  const [type, setType] = useState<'in' | 'out'>('in')
  const [amount, setAmount] = useState('')
  const [date, setDate] = useState(todayISO())
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const parsed = parseMoneyInput(amount)
    if (!parsed) return setError('Informe um valor válido.')
    setSaving(true)
    setError(null)
    try {
      await api(`/goals/${goal.id}/contributions`, { method: 'POST', body: { amount: type === 'in' ? parsed : `-${parsed}`, contributed_on: date, notes: notes.trim() || null } })
      onDone()
    } catch (err) {
      setError(msg(err))
    } finally {
      setSaving(false)
    }
  }
  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {error && <Alert kind="error">{error}</Alert>}
      <p className="text-sm text-muted">{goal.name} · guardado {formatBRL(goal.saved)}</p>
      <Segmented label="Tipo" value={type} onChange={setType} options={[{ value: 'in', label: 'Aporte' }, { value: 'out', label: 'Retirada' }]} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Valor (R$)" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
        <Field label="Data" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </div>
      <Field label="Observação (opcional)" maxLength={200} value={notes} onChange={(e) => setNotes(e.target.value)} />
      <Button type="submit" loading={saving}>Registrar</Button>
    </form>
  )
}

export default function PlanningPage() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('aba') === 'metas' ? 'metas' : 'orcamentos'
  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="font-display text-3xl font-semibold tracking-tight">Planejamento</h1>
        <p className="mt-1 text-sm text-muted">Limites mensais por categoria e metas de economia.</p>
      </header>
      <Segmented label="Seção" value={tab} onChange={(v) => setParams(v === 'metas' ? { aba: 'metas' } : {})} options={[{ value: 'orcamentos', label: 'Orçamentos' }, { value: 'metas', label: 'Metas' }]} />
      {tab === 'orcamentos' ? <Budgets /> : <Goals />}
    </div>
  )
}
