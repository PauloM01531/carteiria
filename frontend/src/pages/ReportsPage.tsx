import { useEffect, useMemo, useState } from 'react'
import { CategoryChart, CompareChart, type CategoryShare } from '../components/charts'
import { Alert, Card, EmptyState, Field, Segmented, SelectField, Spinner, cx } from '../components/ui'
import { api } from '../lib/api'
import { longMonth, type CreditCard } from '../lib/cards'
import { currentMonth, monthRange, shiftMonth, todayISO } from '../lib/dates'
import type { Category } from '../lib/finance'
import { formatBRL, formatDate } from '../lib/format'
import { BASIS_LABEL, formatPct, type Basis, type Commitments, type Compare, type Summary } from '../lib/reports'

type Mode = 'month' | 'year' | 'range'

function Answer({ q, children, sub }: { q: string; children: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <Card className="p-4 sm:p-5">
      <p className="text-sm text-muted">{q}</p>
      <div className="tabular mt-1 font-display text-xl font-semibold sm:text-2xl">{children}</div>
      {sub && <p className="mt-1 text-xs text-muted">{sub}</p>}
    </Card>
  )
}

export default function ReportsPage() {
  const cm = currentMonth()
  const [mode, setMode] = useState<Mode>('month')
  const [monthStr, setMonthStr] = useState(`${cm.year}-${String(cm.month).padStart(2, '0')}`)
  const [year, setYear] = useState(cm.year)
  const [start, setStart] = useState(monthRange(cm).start)
  const [end, setEnd] = useState(todayISO())
  const [basis, setBasis] = useState<Basis>('competencia')
  const [categoryId, setCategoryId] = useState('')
  const [cardId, setCardId] = useState('')
  const [categories, setCategories] = useState<Category[]>([])
  const [cards, setCards] = useState<CreditCard[]>([])

  const [summary, setSummary] = useState<Summary | null>(null)
  const [cats, setCats] = useState<CategoryShare[]>([])
  const [cmp, setCmp] = useState<Compare | null>(null)
  const [com, setCom] = useState<Commitments | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [cmpA, setCmpA] = useState(() => { const p = shiftMonth(cm, -1); return `${p.year}-${String(p.month).padStart(2, '0')}` })
  const [cmpB, setCmpB] = useState(`${cm.year}-${String(cm.month).padStart(2, '0')}`)

  useEffect(() => {
    api<Category[]>('/categories?include_inactive=true').then(setCategories).catch(() => undefined)
    api<CreditCard[]>('/cards').then(setCards).catch(() => undefined)
    api<Commitments>('/reports/commitments').then(setCom).catch(() => undefined)
  }, [])

  const params = useMemo(() => {
    const p = new URLSearchParams({ basis })
    if (mode === 'month') p.set('month', `${monthStr}-01`)
    else if (mode === 'year') p.set('year', String(year))
    else { p.set('start', start); p.set('end', end) }
    if (categoryId) p.set('category_id', categoryId)
    if (cardId) p.set('card_id', cardId)
    return p
  }, [mode, monthStr, year, start, end, basis, categoryId, cardId])

  useEffect(() => {
    if (mode === 'range' && (!start || !end || start > end)) return
    setSummary(null)
    setError(null)
    Promise.all([api<Summary>(`/reports/summary?${params}`), api<CategoryShare[]>(`/reports/categories?${params}`)])
      .then(([s, c]) => { setSummary(s); setCats(c) })
      .catch((e) => setError(e.message))
  }, [params, mode, start, end])

  useEffect(() => {
    if (!cmpA || !cmpB) return
    const p = new URLSearchParams({ month_a: `${cmpA}-01`, month_b: `${cmpB}-01`, basis })
    if (categoryId) p.set('category_id', categoryId)
    if (cardId) p.set('card_id', cardId)
    api<Compare>(`/reports/compare?${p}`).then(setCmp).catch((e) => setError(e.message))
  }, [cmpA, cmpB, basis, categoryId, cardId])

  const exportUrl = summary ? `/api/v1/export/lancamentos.csv?start=${summary.start}&end=${summary.end}` : '#'
  const years = Array.from({ length: 8 }, (_, i) => cm.year - 6 + i)

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">Relatórios</h1>
          <p className="mt-1 text-sm text-muted">Respostas rápidas sobre o seu dinheiro.</p>
        </div>
        <a href={exportUrl} download className="inline-flex min-h-11 items-center justify-center rounded-xl border border-line bg-surface px-4 text-sm font-semibold hover:bg-surface-2">
          Exportar lançamentos (CSV)
        </a>
      </header>

      {/* Filtros: uma linha acima dos resultados */}
      <Card className="flex flex-col gap-4 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <Segmented label="Período" value={mode} onChange={setMode} options={[{ value: 'month', label: 'Mês' }, { value: 'year', label: 'Ano' }, { value: 'range', label: 'Intervalo' }]} />
          {mode === 'month' && <Field label="Mês" type="month" value={monthStr} onChange={(e) => setMonthStr(e.target.value)} />}
          {mode === 'year' && (
            <SelectField label="Ano" value={year} onChange={(e) => setYear(Number(e.target.value))}>
              {years.map((y) => <option key={y} value={y}>{y}</option>)}
            </SelectField>
          )}
          {mode === 'range' && (
            <>
              <Field label="De" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
              <Field label="Até" type="date" value={end} onChange={(e) => setEnd(e.target.value)} error={start > end ? 'Antes do início.' : null} />
            </>
          )}
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <SelectField label="Base de cálculo" value={basis} onChange={(e) => setBasis(e.target.value as Basis)}>
            {Object.entries(BASIS_LABEL).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </SelectField>
          <SelectField label="Categoria" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">Todas</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.name}{c.kind === 'income' ? ' (receita)' : ''}</option>)}
          </SelectField>
          <SelectField label="Cartão" value={cardId} onChange={(e) => setCardId(e.target.value)}>
            <option value="">Todos (inclui lançamentos)</option>
            {cards.map((c) => <option key={c.id} value={c.id}>{c.nickname}</option>)}
          </SelectField>
        </div>
        <p className="text-xs text-muted">{BASIS_LABEL[basis].help}</p>
      </Card>

      {error && <Alert kind="error">{error}</Alert>}

      {!summary ? (
        <div className="flex justify-center py-10 text-muted"><Spinner className="h-7 w-7" /></div>
      ) : summary.count === 0 ? (
        <EmptyState title="Sem registros no período">Não há receitas nem despesas para os filtros escolhidos. Os valores aparecem zerados.</EmptyState>
      ) : (
        <>
          <p className="text-sm text-muted">De {formatDate(summary.start)} a {formatDate(summary.end)}</p>
          <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3">
            <Answer q="Quanto gastei?">{formatBRL(summary.expense)}</Answer>
            <Answer q="Quanto recebi?"><span className="text-positive">{formatBRL(summary.income)}</span></Answer>
            <Answer q="Quanto consegui economizar?" sub={summary.savings_rate ? `${summary.savings_rate.replace('.', ',')}% da receita` : 'Sem receita no período'}>
              <span className={cx(Number(summary.balance) < 0 && 'text-negative')}>{formatBRL(summary.balance)}</span>
            </Answer>
            <Answer q="Qual foi minha maior despesa?" sub={summary.largest_expense ? `${summary.largest_expense.description} · ${formatDate(summary.largest_expense.day)}` : undefined}>
              {summary.largest_expense ? formatBRL(summary.largest_expense.amount) : '—'}
            </Answer>
            <Answer q="Qual categoria consumiu mais?" sub={summary.top_category ? `${formatBRL(summary.top_category.amount)} · ${summary.top_category.share.replace('.', ',')}% do total` : undefined}>
              {summary.top_category?.category_name ?? '—'}
            </Answer>
            <Answer q="Quanto tenho em parcelas futuras?" sub={com ? `Próximas faturas em aberto: ${formatBRL(com.open_statements_total)}` : undefined}>
              {com ? formatBRL(com.future_installments_total) : '—'}
            </Answer>
          </div>
          <Card>
            <h2 className="font-display text-xl font-semibold">Gastos por categoria</h2>
            <div className="mt-3">{cats.length ? <CategoryChart data={cats} /> : <p className="text-sm text-muted">Nenhum gasto no período.</p>}</div>
          </Card>
        </>
      )}

      <Card>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <h2 className="font-display text-xl font-semibold">Comparar meses</h2>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Mês anterior" type="month" value={cmpA} onChange={(e) => setCmpA(e.target.value)} />
            <Field label="Mês atual" type="month" value={cmpB} onChange={(e) => setCmpB(e.target.value)} />
          </div>
        </div>
        {cmp && (
          <>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              {(['expense', 'income', 'balance'] as const).map((k) => (
                <div key={k} className="rounded-xl bg-surface-2 p-3 text-sm">
                  <p className="text-muted">{k === 'expense' ? 'Despesas' : k === 'income' ? 'Receitas' : 'Resultado'}</p>
                  <p className="tabular font-semibold">{formatBRL(cmp[k].previous)} → {formatBRL(cmp[k].current)}</p>
                  <p className="tabular text-xs text-muted">Diferença {formatBRL(cmp[k].diff)} · {formatPct(cmp[k].pct)}</p>
                </div>
              ))}
            </div>
            <div className="mt-4">
              {cmp.categories.length ? (
                <CompareChart data={cmp.categories} previousLabel={longMonth(cmp.month_a)} currentLabel={longMonth(cmp.month_b)} />
              ) : (
                <p className="text-sm text-muted">Sem gastos nos dois meses.</p>
              )}
            </div>
          </>
        )}
      </Card>

      {com && Number(com.future_installments_total) > 0 && (
        <Card>
          <h2 className="font-display text-xl font-semibold">Parcelas futuras por fatura</h2>
          <ul className="mt-3 divide-y divide-line text-sm">
            {com.future_installments_by_month.map((m) => (
              <li key={m.month} className="flex justify-between py-2"><span>{longMonth(m.month)}</span><span className="tabular font-semibold">{formatBRL(m.amount)}</span></li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
