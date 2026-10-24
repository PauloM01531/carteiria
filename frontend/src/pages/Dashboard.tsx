import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { BalanceChart, BudgetBars, CategoryChart, IncomeExpenseChart } from '../components/charts'
import { Alert, Card, EmptyState, Spinner, cx } from '../components/ui'
import { api } from '../lib/api'
import { longMonth } from '../lib/cards'
import { currentMonth, monthLabel, shiftMonth, type YearMonth } from '../lib/dates'
import { formatBRL, formatDate, TIME_ZONE } from '../lib/format'
import { formatPct, type Dashboard as DashboardData } from '../lib/reports'

function greeting(): string {
  const hour = Number(new Intl.DateTimeFormat('pt-BR', { hour: 'numeric', hourCycle: 'h23', timeZone: TIME_ZONE }).format(new Date()))
  if (hour < 12) return 'Bom dia'
  if (hour < 18) return 'Boa tarde'
  return 'Boa noite'
}

const MONTHS = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']

function Kpi({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: 'pos' | 'neg' }) {
  return (
    <Card className="p-4 sm:p-5">
      <p className="text-sm text-muted">{label}</p>
      <p className={cx('tabular mt-1 font-display text-lg font-semibold sm:text-xl 2xl:text-2xl', tone === 'pos' && 'text-positive', tone === 'neg' && 'text-negative')}>{formatBRL(value)}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </Card>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  const [month, setMonth] = useState<YearMonth>(currentMonth())
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setData(null)
    const mm = String(month.month).padStart(2, '0')
    api<DashboardData>(`/dashboard?month=${month.year}-${mm}-01`)
      .then(setData)
      .catch((e) => setError(e.message))
  }, [month])

  const years = Array.from({ length: 6 }, (_, i) => currentMonth().year - 4 + i)
  const s = data?.summary
  const empty = data && s && s.count === 0 && data.commitments.total === '0.00' && data.recent.length === 0

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-muted">{monthLabel(month)}</p>
          <h1 className="mt-1 font-display text-3xl font-semibold tracking-tight">
            {greeting()}, {user?.display_name.split(' ')[0]}.
          </h1>
        </div>
        {/* Filtro de mês e ano */}
        <div className="flex items-center gap-2" role="group" aria-label="Período do painel">
          <button type="button" aria-label="Mês anterior" onClick={() => setMonth(shiftMonth(month, -1))} className="grid h-10 w-10 place-items-center rounded-xl border border-line bg-surface hover:bg-surface-2">‹</button>
          <select aria-label="Mês" value={month.month} onChange={(e) => setMonth({ ...month, month: Number(e.target.value) })} className="min-h-10 rounded-xl border border-line bg-surface px-2">
            {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </select>
          <select aria-label="Ano" value={month.year} onChange={(e) => setMonth({ ...month, year: Number(e.target.value) })} className="min-h-10 rounded-xl border border-line bg-surface px-2">
            {years.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
          <button type="button" aria-label="Próximo mês" onClick={() => setMonth(shiftMonth(month, 1))} className="grid h-10 w-10 place-items-center rounded-xl border border-line bg-surface hover:bg-surface-2">›</button>
        </div>
      </header>

      {error && <Alert kind="error">{error}</Alert>}
      {!data || !s ? (
        <div className="flex justify-center py-16 text-muted"><Spinner className="h-8 w-8" /></div>
      ) : empty ? (
        <>
          <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
            <Kpi label="Receitas" value="0.00" />
            <Kpi label="Despesas" value="0.00" />
            <Kpi label="Diferença" value="0.00" />
            <Kpi label="Saldo calculado" value="0.00" />
          </div>
          <EmptyState
            title="Comece pelo primeiro lançamento"
            action={
              <div className="flex flex-wrap justify-center gap-2">
                <Link to="/lancamentos" className="inline-flex min-h-11 items-center rounded-xl bg-brand px-4 text-sm font-semibold text-brand-contrast">Registrar receita ou despesa</Link>
                <Link to="/cartoes" className="inline-flex min-h-11 items-center rounded-xl border border-line px-4 text-sm font-semibold">Cadastrar cartão</Link>
                <Link to="/contas" className="inline-flex min-h-11 items-center rounded-xl border border-line px-4 text-sm font-semibold">Cadastrar conta fixa</Link>
              </div>
            }
          >
            Seus indicadores e gráficos são calculados só com os seus dados. Registre receitas, despesas, cartões ou contas fixas para vê-los aqui.
          </EmptyState>
        </>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
            <Kpi label="Receitas do mês" value={s.income} tone="pos" />
            <Kpi label="Despesas do mês" value={s.expense} hint={`${formatPct(data.expense_change_pct)} vs. mês anterior`} />
            <Kpi label="Diferença" value={s.balance} tone={Number(s.balance) < 0 ? 'neg' : undefined} hint={s.savings_rate ? `Economia de ${s.savings_rate.replace('.', ',')}% da receita` : undefined} />
            <Kpi label="Faturas deste mês" value={data.month_statements_total} hint="Total das faturas com competência no mês" />
          </div>

          <Card className="grid gap-4 sm:grid-cols-3">
            <div>
              <p className="text-sm text-muted">Saldo calculado</p>
              <p className={cx('tabular mt-1 font-display text-2xl font-semibold', Number(data.cash_balance) < 0 && 'text-negative')}>{formatBRL(data.cash_balance)}</p>
              <p className="mt-1 text-xs text-muted">Recebido − pago até agora, a partir dos lançamentos.</p>
            </div>
            <div>
              <p className="text-sm text-muted">Compromissos futuros</p>
              <p className="tabular mt-1 font-display text-2xl font-semibold">{formatBRL(data.commitments.total)}</p>
              <p className="mt-1 text-xs text-muted">Faturas em aberto, contas previstas (30 dias) e despesas pendentes.</p>
            </div>
            <div>
              <p className="text-sm text-muted">Saldo após compromissos</p>
              <p className={cx('tabular mt-1 font-display text-2xl font-semibold', Number(data.balance_after_commitments) < 0 ? 'text-negative' : 'text-positive')}>{formatBRL(data.balance_after_commitments)}</p>
              <p className="mt-1 text-xs text-muted">O saldo calculado não é dinheiro livre: este valor já desconta o que está comprometido.</p>
            </div>
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <h2 className="font-display text-xl font-semibold">Receitas e despesas por mês</h2>
              <p className="mb-3 text-xs text-muted">Últimos 12 meses, por competência.</p>
              <IncomeExpenseChart data={data.monthly} />
            </Card>
            <Card>
              <h2 className="font-display text-xl font-semibold">Gastos por categoria</h2>
              <p className="mb-3 text-xs text-muted">{longMonth(data.month)}</p>
              {data.categories.length ? <CategoryChart data={data.categories} /> : <p className="text-sm text-muted">Nenhum gasto neste mês.</p>}
            </Card>
            <Card>
              <h2 className="font-display text-xl font-semibold">Evolução do saldo</h2>
              <p className="mb-3 text-xs text-muted">Resultado acumulado nos últimos 12 meses.</p>
              <BalanceChart data={data.monthly} />
            </Card>
            <Card>
              <div className="flex items-center justify-between">
                <h2 className="font-display text-xl font-semibold">Orçamento x gasto</h2>
                <Link to="/orcamentos" className="text-sm font-semibold text-muted underline hover:text-ink">Gerenciar</Link>
              </div>
              <div className="mt-3">
                {data.budgets.length ? (
                  <BudgetBars data={data.budgets} />
                ) : (
                  <p className="text-sm text-muted">Nenhum orçamento para este mês. <Link to="/orcamentos" className="font-semibold underline">Definir limites</Link></p>
                )}
              </div>
            </Card>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <div className="flex items-center justify-between">
                <h2 className="font-display text-xl font-semibold">Transações recentes</h2>
                <Link to="/lancamentos" className="text-sm font-semibold text-muted underline hover:text-ink">Ver todas</Link>
              </div>
              {data.recent.length ? (
                <ul className="mt-3 divide-y divide-line">
                  {data.recent.map((t) => (
                    <li key={t.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                      <div className="min-w-0">
                        <p className="truncate font-semibold">{t.description}</p>
                        <p className="text-muted">{formatDate(t.occurred_on)} · {t.category_name}{t.status === 'pending' && ' · pendente'}</p>
                      </div>
                      <span className={cx('tabular shrink-0 whitespace-nowrap font-semibold', t.kind === 'income' && 'text-positive')}>
                        {t.kind === 'income' ? '+ ' : '− '}{formatBRL(t.amount)}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-3 text-sm text-muted">Nenhum lançamento ainda.</p>
              )}
            </Card>
            <Card>
              <h2 className="font-display text-xl font-semibold">Próximas contas e faturas</h2>
              <ul className="mt-3 divide-y divide-line text-sm">
                {data.commitments.upcoming_bills.map((b) => (
                  <li key={b.id} className="flex justify-between gap-3 py-2.5">
                    <span>
                      <span className="font-semibold">{b.name}</span>
                      <span className={cx('block', b.overdue ? 'font-semibold text-negative' : 'text-muted')}>{b.overdue ? 'Atrasada · ' : ''}vence {formatDate(b.due_date)}</span>
                    </span>
                    <span className="tabular whitespace-nowrap">{b.amount ? formatBRL(b.amount) : 'variável'}</span>
                  </li>
                ))}
                {data.commitments.open_statements.slice(0, 4).map((st) => (
                  <li key={st.id}>
                    <Link to={`/cartoes/faturas/${st.id}`} className="flex justify-between gap-3 py-2.5 hover:underline">
                      <span>
                        <span className="font-semibold">Fatura {st.card_nickname}</span>
                        <span className="block text-muted">{longMonth(st.reference_month)} · vence {formatDate(st.due_date)}</span>
                      </span>
                      <span className="tabular whitespace-nowrap">{formatBRL(st.remaining)}</span>
                    </Link>
                  </li>
                ))}
                {!data.commitments.upcoming_bills.length && !data.commitments.open_statements.length && <li className="py-2.5 text-muted">Nada a vencer nos próximos 30 dias.</li>}
              </ul>
              {Number(data.commitments.future_installments_total) > 0 && (
                <p className="mt-3 rounded-xl bg-surface-2 px-3 py-2 text-xs">
                  Parcelas de cartão já comprometidas em meses futuros: <strong className="tabular">{formatBRL(data.commitments.future_installments_total)}</strong>
                </p>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
