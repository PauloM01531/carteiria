import { useAuth } from '../auth/AuthContext'
import { Card, EmptyState } from '../components/ui'
import { formatBRL, TIME_ZONE } from '../lib/format'

function greeting(): string {
  const hour = Number(new Intl.DateTimeFormat('pt-BR', { hour: 'numeric', hourCycle: 'h23', timeZone: TIME_ZONE }).format(new Date()))
  if (hour < 12) return 'Bom dia'
  if (hour < 18) return 'Boa tarde'
  return 'Boa noite'
}

export default function Dashboard() {
  const { user } = useAuth()
  const rawMonth = new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric', timeZone: TIME_ZONE }).format(new Date())
  const month = rawMonth.charAt(0).toUpperCase() + rawMonth.slice(1)
  // Sem lançamentos ainda: os indicadores ficam zerados (nada de números simulados).
  const kpis = [
    { label: 'Receitas do mês', value: 0 },
    { label: 'Despesas do mês', value: 0 },
    { label: 'Diferença', value: 0 },
  ]
  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="text-sm font-semibold text-muted">{month}</p>
        <h1 className="mt-1 font-display text-3xl font-semibold tracking-tight">
          {greeting()}, {user?.display_name.split(' ')[0]}.
        </h1>
      </header>
      <div className="grid gap-4 sm:grid-cols-3">
        {kpis.map((k) => (
          <Card key={k.label} className="p-5">
            <p className="text-sm text-muted">{k.label}</p>
            <p className="tabular mt-2 font-display text-2xl font-semibold">{formatBRL(k.value)}</p>
          </Card>
        ))}
      </div>
      <EmptyState title="Nenhum lançamento ainda">
        O cadastro de receitas e despesas chega na próxima etapa. Quando você registrar seus primeiros lançamentos, os gráficos e
        resumos aparecem aqui.
      </EmptyState>
    </div>
  )
}
