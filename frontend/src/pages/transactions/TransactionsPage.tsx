import { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, EmptyState, Field, Modal, Segmented, SelectField, Spinner, cx } from '../../components/ui'
import { api } from '../../lib/api'
import { currentMonth, monthLabel, monthRange, shiftMonth, type YearMonth } from '../../lib/dates'
import { PAYMENT_METHODS, statusLabel, type Category, type Kind, type Transaction, type TransactionPage } from '../../lib/finance'
import { formatBRL, formatDate } from '../../lib/format'
import { TransactionForm } from './TransactionForm'

type KindFilter = 'all' | Kind
const PAGE_SIZE = 50

function weekday(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  return new Intl.DateTimeFormat('pt-BR', { weekday: 'long', timeZone: 'UTC' }).format(new Date(Date.UTC(y, m - 1, d)))
}

export default function TransactionsPage() {
  const [month, setMonth] = useState<YearMonth>(currentMonth())
  const [custom, setCustom] = useState(false)
  const [start, setStart] = useState(monthRange(currentMonth()).start)
  const [end, setEnd] = useState(monthRange(currentMonth()).end)
  const [kind, setKind] = useState<KindFilter>('all')
  const [categoryId, setCategoryId] = useState('')
  const [method, setMethod] = useState('')
  const [status, setStatus] = useState('')
  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [showFilters, setShowFilters] = useState(false)

  const [categories, setCategories] = useState<Category[]>([])
  const [data, setData] = useState<TransactionPage | null>(null)
  const [items, setItems] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [editing, setEditing] = useState<Transaction | null | 'new'>(null)

  useEffect(() => {
    api<Category[]>('/categories?include_inactive=true').then(setCategories).catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q.trim()), 300)
    return () => clearTimeout(t)
  }, [q])

  const params = useMemo(() => {
    const p = new URLSearchParams()
    const range = custom ? { start, end } : monthRange(month)
    if (range.start) p.set('start', range.start)
    if (range.end) p.set('end', range.end)
    if (kind !== 'all') p.set('kind', kind)
    if (categoryId) p.set('category_id', categoryId)
    if (method) p.set('payment_method', method)
    if (status) p.set('status', status)
    if (debouncedQ) p.set('q', debouncedQ)
    p.set('page_size', String(PAGE_SIZE))
    return p
  }, [custom, start, end, month, kind, categoryId, method, status, debouncedQ])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const r = await api<TransactionPage>(`/transactions?${params}`)
      setData(r)
      setItems(r.items)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erro ao carregar.')
    } finally {
      setLoading(false)
    }
  }, [params])

  useEffect(() => {
    load()
  }, [load])

  async function loadMore() {
    if (!data) return
    setLoadingMore(true)
    try {
      const p = new URLSearchParams(params)
      p.set('page', String(data.page + 1))
      const r = await api<TransactionPage>(`/transactions?${p}`)
      setData(r)
      setItems((prev) => [...prev, ...r.items])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erro ao carregar.')
    } finally {
      setLoadingMore(false)
    }
  }

  const groups = useMemo(() => {
    const map = new Map<string, Transaction[]>()
    for (const t of items) map.set(t.occurred_on, [...(map.get(t.occurred_on) ?? []), t])
    return [...map.entries()]
  }, [items])

  const filterCats = categories.filter((c) => kind === 'all' || c.kind === kind)
  const activeFilters = [categoryId, method, status, debouncedQ].filter(Boolean).length
  const closeModal = useCallback(() => setEditing(null), [])

  function afterSave(msg: string) {
    setEditing(null)
    setNotice(msg)
    setTimeout(() => setNotice(null), 3500)
    load()
  }

  function clearFilters() {
    setCategoryId('')
    setMethod('')
    setStatus('')
    setQ('')
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">Lançamentos</h1>
          <p className="mt-1 text-sm text-muted">Receitas e despesas do período.</p>
        </div>
        <Button onClick={() => setEditing('new')} className="hidden sm:inline-flex">
          + Novo lançamento
        </Button>
      </header>

      {/* Período */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        {custom ? (
          <div className="grid grid-cols-2 gap-3 sm:flex sm:items-end">
            <Field label="De" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
            <Field label="Até" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
          </div>
        ) : (
          <div className="flex items-center gap-1">
            <button type="button" aria-label="Mês anterior" onClick={() => setMonth(shiftMonth(month, -1))} className="grid h-10 w-10 place-items-center rounded-xl hover:bg-surface-2">
              ‹
            </button>
            <p className="min-w-44 text-center font-display text-lg font-semibold">{monthLabel(month)}</p>
            <button type="button" aria-label="Próximo mês" onClick={() => setMonth(shiftMonth(month, 1))} className="grid h-10 w-10 place-items-center rounded-xl hover:bg-surface-2">
              ›
            </button>
          </div>
        )}
        <button type="button" onClick={() => setCustom(!custom)} className="self-start text-sm font-semibold text-muted underline hover:text-ink sm:self-auto">
          {custom ? 'Ver por mês' : 'Escolher período'}
        </button>
      </div>

      {/* Totais do filtro */}
      <div className="grid grid-cols-3 gap-2 sm:gap-4">
        {[
          { label: 'Receitas', value: data?.totals.income, cls: 'text-positive' },
          { label: 'Despesas', value: data?.totals.expense, cls: 'text-negative' },
          { label: 'Saldo', value: data?.totals.balance, cls: data && Number(data.totals.balance) < 0 ? 'text-negative' : '' },
        ].map((k) => (
          <Card key={k.label} className="p-3 sm:p-5">
            <p className="text-xs text-muted sm:text-sm">{k.label}</p>
            <p className={cx('tabular mt-1 truncate font-display text-base font-semibold sm:text-2xl', k.cls)}>{k.value !== undefined ? formatBRL(k.value) : '—'}</p>
          </Card>
        ))}
      </div>

      {/* Filtros */}
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Segmented
            label="Tipo"
            value={kind}
            onChange={(v) => {
              setKind(v)
              setCategoryId('')
            }}
            options={[
              { value: 'all', label: 'Todos' },
              { value: 'income', label: 'Receitas' },
              { value: 'expense', label: 'Despesas' },
            ]}
          />
          <Button variant="secondary" className="min-h-10" onClick={() => setShowFilters(!showFilters)} aria-expanded={showFilters}>
            Filtros{activeFilters ? ` (${activeFilters})` : ''}
          </Button>
          {activeFilters > 0 && (
            <button type="button" onClick={clearFilters} className="text-sm font-semibold text-muted underline">
              Limpar
            </button>
          )}
        </div>
        {showFilters && (
          <Card className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Descrição" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar…" />
            <SelectField label="Categoria" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
              <option value="">Todas</option>
              {filterCats.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </SelectField>
            <SelectField label="Forma de pagamento" value={method} onChange={(e) => setMethod(e.target.value)}>
              <option value="">Todas</option>
              {Object.entries(PAYMENT_METHODS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </SelectField>
            <SelectField label="Situação" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">Todas</option>
              <option value="settled">Pago / Recebido</option>
              <option value="pending">Pendente</option>
            </SelectField>
          </Card>
        )}
      </div>

      {notice && <Alert kind="success">{notice}</Alert>}
      {error && <Alert kind="error">{error}</Alert>}

      {/* Lista */}
      {loading ? (
        <div className="flex justify-center py-10 text-muted">
          <Spinner className="h-7 w-7" />
        </div>
      ) : items.length === 0 ? (
        activeFilters || kind !== 'all' ? (
          <EmptyState title="Nada encontrado">Nenhum lançamento corresponde aos filtros. Ajuste ou limpe os filtros.</EmptyState>
        ) : (
          <EmptyState title="Nenhum lançamento neste período" action={<Button onClick={() => setEditing('new')}>Adicionar o primeiro</Button>}>
            Registre suas receitas e despesas para acompanhar para onde vai o seu dinheiro.
          </EmptyState>
        )
      ) : (
        <div className="flex flex-col gap-5">
          {groups.map(([day, txs]) => (
            <section key={day}>
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">
                {formatDate(day)} · {weekday(day)}
              </h2>
              <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
                {txs.map((t) => (
                  <li key={t.id}>
                    <button type="button" onClick={() => setEditing(t)} className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-surface-2">
                      <span
                        aria-hidden
                        className={cx('grid h-10 w-10 shrink-0 place-items-center rounded-xl text-lg font-bold', t.kind === 'income' ? 'bg-positive/15 text-positive' : 'bg-negative/10 text-negative')}
                      >
                        {t.kind === 'income' ? '↑' : '↓'}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-semibold">{t.description}</span>
                        <span className="block truncate text-sm text-muted">
                          {t.category_name} · {PAYMENT_METHODS[t.payment_method]}
                          {t.status === 'pending' && <span className="ml-2 rounded-full bg-accent-soft px-2 py-0.5 text-xs font-semibold text-ink">{statusLabel(t.kind, t.status)}</span>}
                        </span>
                      </span>
                      <span className={cx('tabular shrink-0 font-semibold', t.kind === 'income' ? 'text-positive' : 'text-ink')}>
                        {t.kind === 'income' ? '+ ' : '− '}
                        {formatBRL(t.amount)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
          {data && items.length < data.total && (
            <Button variant="secondary" onClick={loadMore} loading={loadingMore} className="self-center">
              Carregar mais ({data.total - items.length} restantes)
            </Button>
          )}
        </div>
      )}

      {/* Botão flutuante (celular) */}
      <button
        type="button"
        onClick={() => setEditing('new')}
        aria-label="Novo lançamento"
        className="fixed bottom-24 right-4 z-10 grid h-14 w-14 place-items-center rounded-2xl bg-brand text-3xl text-brand-contrast shadow-lg sm:hidden"
      >
        +
      </button>

      <Modal open={editing !== null} title={editing === 'new' ? 'Novo lançamento' : 'Editar lançamento'} onClose={closeModal}>
        {editing !== null && (
          <TransactionForm
            categories={categories}
            initial={editing === 'new' ? null : editing}
            defaultKind={kind === 'income' ? 'income' : 'expense'}
            onSaved={() => afterSave(editing === 'new' ? 'Lançamento adicionado.' : 'Lançamento atualizado.')}
            onDeleted={() => afterSave('Lançamento excluído.')}
          />
        )}
      </Modal>
    </div>
  )
}
