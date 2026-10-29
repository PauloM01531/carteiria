/** Compras planejadas: avalia se uma compra futura cabe no orçamento, mês a mês. */
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Alert, Button, Card, ConfirmDialog, EmptyState, Field, Modal, SelectField, Spinner, TextareaField, cx } from '../../components/ui'
import { api, ApiError } from '../../lib/api'
import { longMonth } from '../../lib/cards'
import { addMonthsISO, installmentPreview, PLAN_STATUS, type PlanAnalysis, type PlanMonth, type PlannedPurchase, type PlanStatus } from '../../lib/planned'
import { todayISO } from '../../lib/dates'
import type { Category } from '../../lib/finance'
import { formatBRL } from '../../lib/format'
import { parseMoneyInput, toMoneyInput } from '../../lib/money'

const msg = (e: unknown) => (e instanceof ApiError ? e.message : 'Não foi possível concluir. Tente novamente.')

function StatusBadge({ status, large }: { status: PlanStatus; large?: boolean }) {
  const s = PLAN_STATUS[status]
  return (
    <span className={cx('inline-flex items-center gap-1 rounded-full font-semibold', large ? 'px-3 py-1 text-sm' : 'px-2.5 py-0.5 text-xs', s.cls)}>
      <span aria-hidden>{s.icon}</span>
      {s.label}
    </span>
  )
}

// ------------------------------------------------------------------ Formulário
function PlannedForm({ categories, initial, onDone }: { categories: Category[]; initial: PlannedPurchase | null; onDone: (m: string) => void }) {
  const expense = categories.filter((c) => c.kind === 'expense' && (c.active || c.id === initial?.category_id))
  const [name, setName] = useState(initial?.name ?? '')
  const [amount, setAmount] = useState(initial ? toMoneyInput(initial.total_amount) : '')
  const [count, setCount] = useState(String(initial?.installments_count ?? 1))
  const [first, setFirst] = useState(initial?.first_installment_date ?? todayISO())
  const [categoryId, setCategoryId] = useState(initial?.category_id ?? expense.find((c) => c.name === 'Compras')?.id ?? '')
  const [notes, setNotes] = useState(initial?.notes ?? '')
  const [errors, setErrors] = useState<Record<string, string | null>>({})
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [confirm, setConfirm] = useState(false)

  const parsed = parseMoneyInput(amount)
  const n = Number(count)
  const preview = parsed ? installmentPreview(parsed, n) : null
  const validDate = /^\d{4}-\d{2}-\d{2}$/.test(first)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const v = {
      name: name.trim() ? null : 'Informe o nome da compra.',
      amount: parsed ? null : 'Informe o valor total, por exemplo 2.600,00.',
      count: Number.isInteger(n) && n >= 1 && n <= 72 ? (parsed && !preview ? 'O valor é pequeno demais para esse número de parcelas.' : null) : 'Use de 1 a 72 parcelas.',
      first: validDate ? null : 'Informe a data da primeira parcela.',
      category: categoryId ? null : 'Escolha uma categoria.',
    }
    setErrors(v)
    if (Object.values(v).some(Boolean)) return
    setSaving(true)
    setError(null)
    const body = { name: name.trim(), total_amount: parsed, installments_count: n, first_installment_date: first, category_id: categoryId, notes: notes.trim() || null }
    try {
      await api(initial ? `/planned-purchases/${initial.id}` : '/planned-purchases', { method: initial ? 'PATCH' : 'POST', body })
      onDone(initial ? 'Compra planejada atualizada.' : 'Compra planejada adicionada. Veja a análise mês a mês.')
    } catch (err) {
      setError(msg(err))
    } finally {
      setSaving(false)
    }
  }

  async function remove() {
    if (!initial) return
    try {
      await api(`/planned-purchases/${initial.id}`, { method: 'DELETE' })
      onDone('Compra planejada excluída.')
    } catch (err) {
      setError(msg(err))
      setConfirm(false)
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {error && <Alert kind="error">{error}</Alert>}
      <Field label="Nome da compra" maxLength={200} value={name} onChange={(e) => setName(e.target.value)} error={errors.name} placeholder="Ex.: Tablet" />
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
        <Field label="Número de parcelas" type="number" min={1} max={72} value={count} onChange={(e) => setCount(e.target.value)} error={errors.count} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Data da primeira parcela" type="date" value={first} onChange={(e) => setFirst(e.target.value)} error={errors.first} />
        <SelectField label="Categoria" value={categoryId} onChange={(e) => setCategoryId(e.target.value)} error={errors.category}>
          <option value="">Selecione…</option>
          {expense.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </SelectField>
      </div>
      {preview && validDate && (
        <p className="tabular rounded-xl bg-surface-2 px-4 py-3 text-sm" aria-live="polite">
          <strong>
            {n === 1 ? `1x de ${formatBRL(preview.first)}` : preview.first === preview.last ? `${n}x de ${formatBRL(preview.first)}` : `${n - 1}x de ${formatBRL(preview.first)} + 1x de ${formatBRL(preview.last)}`}
          </strong>
          <span className="block text-muted">
            {n === 1 ? `Em ${longMonth(addMonthsISO(first, 0)).toLowerCase()}` : `De ${longMonth(addMonthsISO(first, 0)).toLowerCase()} a ${longMonth(addMonthsISO(first, n - 1)).toLowerCase()}`}
          </span>
        </p>
      )}
      <TextareaField label="Observações (opcional)" maxLength={500} value={notes} onChange={(e) => setNotes(e.target.value)} />
      <p className="text-xs text-muted">A compra planejada é só uma simulação: ela não entra em lançamentos, faturas nem relatórios.</p>
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
        {initial ? <Button type="button" variant="ghost" className="text-negative" onClick={() => setConfirm(true)}>Excluir</Button> : <span />}
        <Button type="submit" loading={saving}>{initial ? 'Salvar alterações' : 'Analisar e salvar'}</Button>
      </div>
      <ConfirmDialog open={confirm} title="Excluir compra planejada?" confirmLabel="Excluir" danger onConfirm={remove} onCancel={() => setConfirm(false)}>
        "{initial?.name}" deixará de ser considerada na análise das outras compras planejadas.
      </ConfirmDialog>
    </form>
  )
}

// ------------------------------------------------------------------ Análise de um mês
function MonthRow({ m, total }: { m: PlanMonth; total: number }) {
  const rows: [string, string | null, boolean?][] = [
    [m.income_source === 'media' ? 'Receita estimada (média dos últimos meses)' : 'Receitas lançadas', m.income],
    ['Despesas já lançadas', m.registered_expenses],
    ['Parcelas de cartão já cadastradas', m.card_installments],
    ['Assinaturas previstas no cartão', m.subscriptions_projected],
    ['Contas fixas previstas', m.bills_pending],
    ['Despesas habituais estimadas (média dos últimos meses, descontando o já lançado)', m.variable_estimate],
    ['Outras compras planejadas', m.other_planned],
    ['Total de compromissos', m.committed, true],
    ['Sobra antes desta compra', m.balance_before, true],
    [`Parcela ${m.number}/${total}`, m.installment],
  ]
  const after = m.balance_after
  return (
    <li className="rounded-2xl border border-line bg-surface">
      <details>
        <summary className="flex cursor-pointer list-none flex-col gap-2 p-4 sm:flex-row sm:items-center sm:justify-between">
          <span className="min-w-0">
            <span className="block font-semibold">{longMonth(m.month)}</span>
            <span className="block text-sm text-muted">Parcela {m.number}/{total} · {formatBRL(m.installment)}</span>
          </span>
          <span className="flex flex-wrap items-center gap-3">
            <span className={cx('tabular text-sm font-semibold', after !== null && Number(after) < 0 && 'text-negative')}>
              {after === null ? 'Sobra desconhecida' : Number(after) < 0 ? `Faltam ${formatBRL(String(-Number(after)))}` : `Sobram ${formatBRL(after)}`}
            </span>
            <StatusBadge status={m.status} />
          </span>
        </summary>
        <div className="grid gap-4 border-t border-line p-4 text-sm lg:grid-cols-2">
          <table className="tabular w-full">
            <caption className="sr-only">Composição do orçamento de {longMonth(m.month)}</caption>
            <tbody>
              {rows.map(([label, value, strong]) => (
                <tr key={label} className={cx('border-b border-line/60', strong && 'font-semibold')}>
                  <th scope="row" className="py-1.5 pr-3 text-left font-normal text-muted">{label}</th>
                  <td className="whitespace-nowrap py-1.5 pl-2 text-right align-top">{value === null ? 'sem dados' : formatBRL(value)}</td>
                </tr>
              ))}
              <tr className="font-semibold">
                <th scope="row" className="py-1.5 pr-3 text-left">Sobra após a parcela</th>
                <td className={cx('whitespace-nowrap py-1.5 pl-2 text-right align-top', after !== null && Number(after) < 0 && 'text-negative')}>{after === null ? 'sem dados' : formatBRL(after)}</td>
              </tr>
            </tbody>
          </table>
          <div className="flex flex-col gap-3">
            <div>
              <p className="font-semibold">Por que esta conclusão</p>
              <ul className="mt-1 list-disc pl-5 text-muted">
                {m.factors.map((f) => <li key={f}>{f}</li>)}
              </ul>
            </div>
            {m.notes.length > 0 && (
              <div>
                <p className="font-semibold">Sobre os dados</p>
                <ul className="mt-1 list-disc pl-5 text-muted">
                  {m.notes.map((n) => <li key={n}>{n}</li>)}
                </ul>
              </div>
            )}
          </div>
        </div>
      </details>
    </li>
  )
}

// ------------------------------------------------------------------ Análise completa
function AnalysisView({ p, version, onEdit }: { p: PlannedPurchase; version: number; onEdit: () => void }) {
  const [a, setA] = useState<PlanAnalysis | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    api<PlanAnalysis>(`/planned-purchases/${p.id}/analysis`)
      .then((r) => !cancelled && setA(r))
      .catch((e) => !cancelled && setError(msg(e)))
    return () => {
      cancelled = true
    }
  }, [p.id, version])

  if (error) return <Alert kind="error">{error}</Alert>
  if (!a) return <div className="flex justify-center py-10 text-muted"><Spinner className="h-7 w-7" /></div>

  const n = a.installments_count
  const parcel = n === 1 ? `1x de ${formatBRL(a.installment_amount)}` : a.installment_amount === a.last_installment_amount ? `${n}x de ${formatBRL(a.installment_amount)}` : `${n - 1}x de ${formatBRL(a.installment_amount)} + 1x de ${formatBRL(a.last_installment_amount)}`

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-display text-2xl font-semibold">{p.name}</h2>
            <p className="text-sm text-muted">{p.category_name}{p.notes ? ` · ${p.notes}` : ''}</p>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={a.overall_status} large />
            <Button variant="secondary" className="min-h-9 px-3" onClick={onEdit}>Editar</Button>
          </div>
        </div>
        <p className="font-semibold">{a.headline}</p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 2xl:grid-cols-4">
          <div className="rounded-xl bg-surface-2 p-3"><p className="text-xs text-muted">Valor total</p><p className="tabular font-display text-lg font-semibold">{formatBRL(a.total_amount)}</p></div>
          <div className="rounded-xl bg-surface-2 p-3"><p className="text-xs text-muted">Parcelas</p><p className="tabular font-semibold">{parcel}</p></div>
          <div className="rounded-xl bg-surface-2 p-3"><p className="text-xs text-muted">Período</p><p className="font-semibold">{n === 1 ? longMonth(a.first_month) : `${longMonth(a.first_month)} a ${longMonth(a.last_month)}`}</p></div>
          <div className="rounded-xl bg-surface-2 p-3">
            <p className="text-xs text-muted">Mês mais apertado</p>
            {a.worst_month && a.worst_balance_after !== null ? (
              <p className={cx('tabular font-semibold', Number(a.worst_balance_after) < 0 && 'text-negative')}>
                {longMonth(a.worst_month)}: {Number(a.worst_balance_after) < 0 ? `faltam ${formatBRL(String(-Number(a.worst_balance_after)))}` : `sobram ${formatBRL(a.worst_balance_after)}`}
              </p>
            ) : <p className="font-semibold">sem dados</p>}
          </div>
        </div>
        <ul className="flex flex-wrap gap-2 text-xs" aria-label="Resumo por situação">
          {(Object.keys(PLAN_STATUS) as PlanStatus[]).filter((k) => a.status_counts[k]).map((k) => (
            <li key={k} className={cx('rounded-full px-2.5 py-1 font-semibold', PLAN_STATUS[k].cls)}>{a.status_counts[k]} mês(es): {PLAN_STATUS[k].label}</li>
          ))}
          {a.average_balance_after !== null && <li className="rounded-full bg-surface-2 px-2.5 py-1 font-semibold">Sobra média após a parcela: {formatBRL(a.average_balance_after)}</li>}
        </ul>
        {a.confidence_notes.length > 0 && (
          <Alert kind="info">
            <strong>Dados limitados:</strong> {a.confidence_notes.join(' ')}{' '}
            <Link to="/lancamentos" className="font-semibold underline">Lançar receitas e despesas</Link>
          </Alert>
        )}
      </Card>
      <ul className="flex flex-col gap-3" aria-label="Análise mês a mês">
        {a.months.map((m) => <MonthRow key={m.month} m={m} total={n} />)}
      </ul>
    </div>
  )
}

// ------------------------------------------------------------------ Página
export default function PlannedPurchasesPage() {
  const [items, setItems] = useState<PlannedPurchase[] | null>(null)
  const [categories, setCategories] = useState<Category[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [modal, setModal] = useState<PlannedPurchase | 'new' | null>(null)
  const [version, setVersion] = useState(0)

  const load = useCallback(async () => {
    try {
      const list = await api<PlannedPurchase[]>('/planned-purchases')
      setItems(list)
      setSelected((s) => (s && list.some((p) => p.id === s) ? s : list[0]?.id ?? null))
      setVersion((v) => v + 1)
      setError(null)
    } catch (e) {
      setError(msg(e))
    }
  }, [])

  useEffect(() => {
    load()
    api<Category[]>('/categories?include_inactive=true').then(setCategories).catch(() => undefined)
  }, [load])

  // A análise usa dados vivos: ao voltar para a aba (após mudar receitas, despesas ou contas), recalcula.
  useEffect(() => {
    const onVisible = () => document.visibilityState === 'visible' && load()
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('focus', onVisible)
    return () => {
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('focus', onVisible)
    }
  }, [load])

  const close = useCallback(() => setModal(null), [])
  function done(m: string) {
    setModal(null)
    setNotice(m)
    setTimeout(() => setNotice(null), 4000)
    load()
  }

  const current = items?.find((p) => p.id === selected) ?? null

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">Compras planejadas</h1>
          <p className="mt-1 text-sm text-muted">Veja, mês a mês, se uma compra futura cabe no seu orçamento.</p>
        </div>
        <Button onClick={() => setModal('new')}>+ Nova compra planejada</Button>
      </header>

      <details className="rounded-2xl border border-line bg-surface p-4 text-sm">
        <summary className="cursor-pointer font-semibold">Como a análise funciona</summary>
        <ul className="mt-3 list-disc space-y-1.5 pl-5 text-muted">
          <li><strong className="text-ink">Receita do mês:</strong> as receitas lançadas no mês. Se ainda não houver, usamos a média dos últimos 3 meses completos (quando há receitas em pelo menos 2 deles). Sem isso, o mês fica como "Dados insuficientes".</li>
          <li><strong className="text-ink">Compromissos:</strong> despesas já lançadas, parcelas de cartão já cadastradas (pelo mês da fatura), assinaturas no cartão, contas fixas ainda não pagas, despesas habituais estimadas pela média dos últimos 3 meses (descontando o que já foi lançado no mês) e as outras compras planejadas.</li>
          <li><strong className="text-ink">Sem contar duas vezes:</strong> contas fixas pagas já são lançamentos; cobranças de assinatura já geradas já são parcelas de cartão; a compra planejada não vira despesa de verdade.</li>
          <li><strong className="text-ink">Limite do cartão não é dinheiro:</strong> o limite disponível nunca é somado como sobra.</li>
          <li><strong className="text-ink">Conclusão:</strong> "Acima do orçamento" quando a sobra fica negativa; "Cabe com atenção" quando sobra menos de 10% da receita, quando a parcela consome mais da metade da sobra ou quando estoura o orçamento da categoria; "Cabe no orçamento" nos demais casos.</li>
          <li>É uma estimativa feita com os dados que você registrou, não uma garantia financeira. Gastos não lançados e mudanças de renda não aparecem na conta.</li>
        </ul>
      </details>

      {notice && <Alert kind="success">{notice}</Alert>}
      {error && <Alert kind="error">{error}</Alert>}

      {items === null ? (
        !error && <div className="flex justify-center py-10 text-muted"><Spinner className="h-7 w-7" /></div>
      ) : items.length === 0 ? (
        <EmptyState title="Nenhuma compra planejada" action={<Button onClick={() => setModal('new')}>Planejar uma compra</Button>}>
          Cadastre uma compra que você está pensando em fazer, como um tablet de R$ 2.600,00 em 12 vezes, e veja se a parcela cabe nas suas receitas e compromissos de cada mês.
        </EmptyState>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[17rem_1fr]">
          <ul className="grid gap-2 sm:grid-cols-2 xl:flex xl:flex-col" aria-label="Compras planejadas">
            {items.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  onClick={() => setSelected(p.id)}
                  aria-pressed={p.id === selected}
                  className={cx('flex w-full flex-col gap-1.5 rounded-2xl border p-4 text-left transition', p.id === selected ? 'border-accent bg-accent-soft' : 'border-line bg-surface hover:bg-surface-2')}
                >
                  <span className="font-semibold">{p.name}</span>
                  <span className="tabular text-sm text-muted">
                    {formatBRL(p.total_amount)} · {p.installments_count}x de {formatBRL(p.installment_amount)}
                  </span>
                  <span className="text-xs text-muted">{p.installments_count === 1 ? longMonth(p.first_month) : `${longMonth(p.first_month)} a ${longMonth(p.last_month)}`}</span>
                  <StatusBadge status={p.overall_status} />
                </button>
              </li>
            ))}
          </ul>
          {current && <AnalysisView p={current} version={version} onEdit={() => setModal(current)} />}
        </div>
      )}

      <Modal open={modal !== null} title={modal === 'new' ? 'Nova compra planejada' : 'Editar compra planejada'} onClose={close}>
        {modal !== null && <PlannedForm categories={categories} initial={modal === 'new' ? null : modal} onDone={done} />}
      </Modal>
    </div>
  )
}
