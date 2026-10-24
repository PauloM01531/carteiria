import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { Alert, Card, EmptyState, Spinner, cx } from '../components/ui'
import { api } from '../lib/api'
import { currentMonth, monthLabel, monthRange } from '../lib/dates'
import type { TransactionPage } from '../lib/finance'
import { formatBRL, formatDate, TIME_ZONE } from '../lib/format'

function greeting(): string {
  const hour = Number(new Intl.DateTimeFormat('pt-BR', { hour: 'numeric', hourCycle: 'h23', timeZone: TIME_ZONE }).format(new Date()))
  if (hour < 12) return 'Bom dia'
  if (hour < 18) return 'Boa tarde'
  return 'Boa noite'
}

export default function Dashboard() {
  const { user } = useAuth()
  const month = currentMonth()
  const [data, setData] = useState<TransactionPage | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const { start, end } = monthRange(month)
    // Todos os números vêm dos lançamentos reais do usuário autenticado.
    api<TransactionPage>(`/transactions?start=${start}&end=${end}&page_size=6`)
      .then(setData)
      .catch((e) => setError(e.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const kpis = [
    { label: 'Receitas do mês', value: data?.totals.income, cls: 'text-positive' },
    { label: 'Despesas do mês', value: data?.totals.expense, cls: 'text-negative' },
    { label: 'Diferença', value: data?.totals.balance, cls: data && Number(data.totals.balance) < 0 ? 'text-negative' : '' },
  ]

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="text-sm font-semibold text-muted">{monthLabel(month)}</p>
        <h1 className="mt-1 font-display text-3xl font-semibold tracking-tight">
          {greeting()}, {user?.display_name.split(' ')[0]}.
        </h1>
      </header>
      {error && <Alert kind="error">{error}</Alert>}
      <div className="grid gap-4 sm:grid-cols-3">
        {kpis.map((k) => (
          <Card key={k.label} className="p-5">
            <p className="text-sm text-muted">{k.label}</p>
            <p className={cx('tabular mt-2 font-display text-2xl font-semibold', k.cls)}>
              {k.value !== undefined ? formatBRL(k.value) : <Spinner className="h-5 w-5" />}
            </p>
          </Card>
        ))}
      </div>
      <p className="-mt-3 text-xs text-muted">Inclui lançamentos pagos/recebidos e pendentes do mês. Gráficos e relatórios chegam na Etapa 4.</p>

      {data && data.items.length === 0 ? (
        <EmptyState
          title="Nenhum lançamento neste mês"
          action={
            <Link to="/lancamentos" className="inline-flex min-h-11 items-center rounded-xl bg-brand px-4 text-sm font-semibold text-brand-contrast">
              Registrar lançamento
            </Link>
          }
        >
          Registre suas primeiras receitas e despesas para ver os resumos aqui.
        </EmptyState>
      ) : data ? (
        <Card>
          <div className="flex items-center justify-between">
            <h2 className="font-display text-xl font-semibold">Transações recentes</h2>
            <Link to="/lancamentos" className="text-sm font-semibold text-muted underline hover:text-ink">
              Ver todas
            </Link>
          </div>
          <ul className="mt-3 divide-y divide-line">
            {data.items.map((t) => (
              <li key={t.id} className="flex items-center justify-between gap-3 py-3 text-sm">
                <div className="min-w-0">
                  <p className="truncate font-semibold">{t.description}</p>
                  <p className="text-muted">
                    {formatDate(t.occurred_on)} · {t.category_name}
                  </p>
                </div>
                <span className={cx('tabular shrink-0 font-semibold', t.kind === 'income' ? 'text-positive' : '')}>
                  {t.kind === 'income' ? '+ ' : '− '}
                  {formatBRL(t.amount)}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  )
}
