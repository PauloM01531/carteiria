/**
 * Gráficos (Recharts). Regras: um único eixo Y, marcas finas, grade discreta, tooltip em reais,
 * legenda quando há 2 séries e uma tabela alternativa para leitores de tela.
 */
import type { ReactNode } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipProps,
} from 'recharts'
import { shortMonth } from '../lib/cards'
import { formatBRL } from '../lib/format'

const S1 = 'var(--series-1)'
const S2 = 'var(--series-2)'
const AXIS = { fontSize: 12, fill: 'var(--muted)' }

function compactBRL(v: number): string {
  const abs = Math.abs(v)
  if (abs >= 1_000_000) return `R$ ${(v / 1_000_000).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} mi`
  if (abs >= 1_000) return `R$ ${(v / 1_000).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} mil`
  return `R$ ${v.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`
}

function MoneyTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-xl border border-line bg-surface px-3 py-2 text-sm text-ink shadow-lg">
      <p className="mb-1 font-semibold">{label}</p>
      {payload.map((p) => (
        <p key={String(p.dataKey)} className="tabular flex items-center gap-2">
          <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: p.color }} />
          <span className="text-muted">{p.name}:</span> {formatBRL(Number(p.value))}
        </p>
      ))}
    </div>
  )
}

/** Tabela equivalente ao gráfico (acessibilidade e leitura exata). */
export function ChartTable({ headers, rows }: { headers: string[]; rows: ReactNode[][] }) {
  return (
    <details className="mt-2 text-sm">
      <summary className="cursor-pointer text-muted hover:text-ink">Ver dados em tabela</summary>
      <div className="mt-2 overflow-x-auto">
        <table className="tabular w-full text-left">
          <thead>
            <tr className="border-b border-line text-muted">
              {headers.map((h) => (
                <th key={h} className="py-1.5 pr-4 font-semibold">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-b border-line/60">
                {r.map((c, j) => (
                  <td key={j} className="py-1.5 pr-4">{c}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}

export interface MonthPoint {
  month: string
  income: string
  expense: string
  balance: string
  cumulative: string
}

/** 1. Evolução mensal de receitas e despesas (barras agrupadas). */
export function IncomeExpenseChart({ data }: { data: MonthPoint[] }) {
  const rows = data.map((p) => ({ label: shortMonth(p.month), Receitas: Number(p.income), Despesas: Number(p.expense) }))
  return (
    <figure>
      <div className="h-64" role="img" aria-label="Gráfico de barras: receitas e despesas por mês">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} barGap={2} barCategoryGap="22%" margin={{ top: 8, right: 4, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--grid)" />
            <XAxis dataKey="label" tick={AXIS} axisLine={false} tickLine={false} interval="preserveStartEnd" />
            <YAxis tick={AXIS} axisLine={false} tickLine={false} tickFormatter={compactBRL} width={84} />
            <Tooltip content={<MoneyTooltip />} cursor={{ fill: 'var(--surface-2)' }} />
            <Legend iconType="square" wrapperStyle={{ fontSize: 12, color: 'var(--muted)' }} />
            <Bar dataKey="Receitas" fill={S1} radius={[4, 4, 0, 0]} maxBarSize={18} />
            <Bar dataKey="Despesas" fill={S2} radius={[4, 4, 0, 0]} maxBarSize={18} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ChartTable headers={['Mês', 'Receitas', 'Despesas', 'Resultado']} rows={data.map((p) => [shortMonth(p.month), formatBRL(p.income), formatBRL(p.expense), formatBRL(p.balance)])} />
    </figure>
  )
}

/** 5. Evolução do saldo (linha única, acumulado no período). */
export function BalanceChart({ data }: { data: MonthPoint[] }) {
  const rows = data.map((p) => ({ label: shortMonth(p.month), 'Saldo acumulado': Number(p.cumulative) }))
  return (
    <figure>
      <div className="h-56" role="img" aria-label="Gráfico de linha: saldo acumulado por mês">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--grid)" />
            <XAxis dataKey="label" tick={AXIS} axisLine={false} tickLine={false} interval="preserveStartEnd" />
            <YAxis tick={AXIS} axisLine={false} tickLine={false} tickFormatter={compactBRL} width={84} />
            <ReferenceLine y={0} stroke="var(--muted)" strokeDasharray="3 3" />
            <Tooltip content={<MoneyTooltip />} />
            <Line type="monotone" dataKey="Saldo acumulado" stroke={S1} strokeWidth={2} dot={{ r: 4, strokeWidth: 2, fill: 'var(--surface)' }} activeDot={{ r: 6 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <ChartTable headers={['Mês', 'Resultado do mês', 'Saldo acumulado']} rows={data.map((p) => [shortMonth(p.month), formatBRL(p.balance), formatBRL(p.cumulative)])} />
    </figure>
  )
}

export interface CategoryShare {
  category_name: string
  amount: string
  share: string
}

/** 2. Distribuição dos gastos por categoria (barras horizontais ordenadas; 8 maiores + "Outras"). */
export function CategoryChart({ data }: { data: CategoryShare[] }) {
  const top = data.slice(0, 8)
  const rest = data.slice(8)
  const rows = top.map((c) => ({ name: c.category_name, Valor: Number(c.amount), share: c.share }))
  if (rest.length) {
    const sum = rest.reduce((s, c) => s + Number(c.amount), 0)
    const share = rest.reduce((s, c) => s + Number(c.share), 0)
    rows.push({ name: 'Outras', Valor: sum, share: share.toFixed(1) })
  }
  return (
    <figure>
      <div style={{ height: Math.max(120, rows.length * 38) }} role="img" aria-label="Gráfico de barras: gastos por categoria">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 110, left: 0, bottom: 0 }} barCategoryGap={8}>
            <XAxis type="number" hide />
            <YAxis type="category" dataKey="name" tick={AXIS} axisLine={false} tickLine={false} width={104} />
            <Tooltip content={<MoneyTooltip />} cursor={{ fill: 'var(--surface-2)' }} />
            <Bar
              dataKey="Valor"
              fill={S1}
              radius={[0, 4, 4, 0]}
              maxBarSize={20}
              label={(props: { x?: number | string; y?: number | string; width?: number | string; height?: number | string; value?: number | string }) => (
                <text
                  x={Number(props.x) + Number(props.width) + 6}
                  y={Number(props.y) + Number(props.height) / 2}
                  dy={4}
                  fontSize={12}
                  fill="var(--text)"
                  style={{ fontVariantNumeric: 'tabular-nums' }}
                >
                  {formatBRL(Number(props.value))}
                </text>
              )}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ChartTable headers={['Categoria', 'Valor', 'Participação']} rows={data.map((c) => [c.category_name, formatBRL(c.amount), `${c.share.replace('.', ',')}%`])} />
    </figure>
  )
}

export interface CategoryDiff {
  category_name: string
  previous: string
  current: string
  diff: string
  pct: string | null
}

/** 3. Comparação entre meses por categoria (barras agrupadas: anterior x atual). */
export function CompareChart({ data, previousLabel, currentLabel }: { data: CategoryDiff[]; previousLabel: string; currentLabel: string }) {
  const rows = data.slice(0, 8).map((c) => ({ name: c.category_name, [previousLabel]: Number(c.previous), [currentLabel]: Number(c.current) }))
  return (
    <figure>
      <div style={{ height: Math.max(140, rows.length * 52) }} role="img" aria-label={`Gráfico de barras: ${previousLabel} comparado com ${currentLabel}`}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 16, left: 0, bottom: 0 }} barGap={2} barCategoryGap={10}>
            <CartesianGrid horizontal={false} stroke="var(--grid)" />
            <XAxis type="number" tick={AXIS} axisLine={false} tickLine={false} tickFormatter={compactBRL} />
            <YAxis type="category" dataKey="name" tick={AXIS} axisLine={false} tickLine={false} width={104} />
            <Tooltip content={<MoneyTooltip />} cursor={{ fill: 'var(--surface-2)' }} />
            <Legend iconType="square" wrapperStyle={{ fontSize: 12, color: 'var(--muted)' }} />
            <Bar dataKey={previousLabel} fill={S2} radius={[0, 4, 4, 0]} maxBarSize={14} />
            <Bar dataKey={currentLabel} fill={S1} radius={[0, 4, 4, 0]} maxBarSize={14} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ChartTable
        headers={['Categoria', previousLabel, currentLabel, 'Diferença', 'Variação']}
        rows={data.map((c) => [c.category_name, formatBRL(c.previous), formatBRL(c.current), formatBRL(c.diff), c.pct === null ? 'sem base' : `${c.pct.replace('.', ',')}%`])}
      />
    </figure>
  )
}

export interface BudgetRow {
  id: string
  category_name: string
  limit_amount: string
  spent: string
  remaining: string
  percent: string
  status: 'ok' | 'warning' | 'limit' | 'over'
  previous_average?: string
}

const BUDGET_STATUS = {
  ok: { label: 'Dentro do limite', bar: 'bg-positive', text: 'text-positive', icon: '✓' },
  warning: { label: 'Perto do limite', bar: 'bg-accent', text: 'text-accent', icon: '!' },
  limit: { label: 'Limite atingido', bar: 'bg-negative', text: 'text-negative', icon: '!' },
  over: { label: 'Limite ultrapassado', bar: 'bg-negative', text: 'text-negative', icon: '✕' },
}

/** 4. Orçamento previsto x valor gasto (barra de progresso com alerta textual, não só cor). */
export function BudgetBars({ data, onSelect }: { data: BudgetRow[]; onSelect?: (b: BudgetRow) => void }) {
  return (
    <ul className="flex flex-col gap-4">
      {data.map((b) => {
        const st = BUDGET_STATUS[b.status]
        const pct = Math.min(100, Number(b.percent))
        const Wrapper = onSelect ? 'button' : 'div'
        return (
          <li key={b.id}>
            <Wrapper type={onSelect ? 'button' : undefined} onClick={onSelect ? () => onSelect(b) : undefined} className="block w-full text-left">
              <div className="flex items-baseline justify-between gap-2 text-sm">
                <span className="font-semibold">{b.category_name}</span>
                <span className="tabular text-muted">
                  {formatBRL(b.spent)} de {formatBRL(b.limit_amount)}
                </span>
              </div>
              <div
                className="mt-1.5 h-2.5 overflow-hidden rounded-full bg-surface-2"
                role="progressbar"
                aria-valuenow={Number(b.percent)}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`${b.category_name}: ${b.percent.replace('.', ',')}% do orçamento`}
              >
                <div className={`h-full rounded-full ${st.bar}`} style={{ width: `${pct}%` }} />
              </div>
              <div className="mt-1 flex justify-between text-xs">
                <span className={`font-semibold ${st.text}`}>
                  <span aria-hidden>{st.icon} </span>
                  {st.label} · {b.percent.replace('.', ',')}%
                </span>
                <span className="tabular text-muted">
                  {Number(b.remaining) >= 0 ? `Restam ${formatBRL(b.remaining)}` : `Excedeu ${formatBRL(String(-Number(b.remaining)))}`}
                </span>
              </div>
            </Wrapper>
          </li>
        )
      })}
    </ul>
  )
}
