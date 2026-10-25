import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Alert, Button, EmptyState, Modal, Spinner, cx } from '../../components/ui'
import { api } from '../../lib/api'
import { STATEMENT_STATUS, longMonth, type CreditCard, type Statement, type Subscription } from '../../lib/cards'
import type { Category } from '../../lib/finance'
import { formatBRL, formatDate } from '../../lib/format'
import { CardForm, PurchaseForm } from './forms'
import { SubscriptionForm } from './SubscriptionForm'

function LimitBar({ card }: { card: CreditCard }) {
  if (!card.credit_limit) return <p className="text-sm text-muted">Comprometido: {formatBRL(card.used_amount)}</p>
  const used = Number(card.used_amount)
  const limit = Number(card.credit_limit)
  const pct = Math.min(100, Math.round((used / limit) * 100))
  return (
    <div className="flex flex-col gap-1.5">
      <div className="h-2 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Limite usado">
        <div className={cx('h-full rounded-full', pct >= 90 ? 'bg-negative' : pct >= 70 ? 'bg-accent' : 'bg-positive')} style={{ width: `${pct}%` }} />
      </div>
      <p className="tabular text-xs text-muted">
        {formatBRL(card.used_amount)} usados de {formatBRL(card.credit_limit)} · disponível {formatBRL(card.available_limit ?? '0')}
      </p>
    </div>
  )
}

export default function CardsPage() {
  const [cards, setCards] = useState<CreditCard[] | null>(null)
  const [categories, setCategories] = useState<Category[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [statements, setStatements] = useState<Statement[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [subs, setSubs] = useState<Subscription[]>([])
  const [modal, setModal] = useState<null | { type: 'card'; card: CreditCard | null } | { type: 'purchase' } | { type: 'sub'; sub: Subscription | null }>(null)

  const loadCards = useCallback(async () => {
    try {
      const list = await api<CreditCard[]>('/cards')
      setCards(list)
      setSelected((s) => (s && list.some((c) => c.id === s) ? s : list[0]?.id ?? null))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erro ao carregar.')
    }
  }, [])

  const loadStatements = useCallback(async () => {
    if (!selected) return setStatements([])
    setStatements(null)
    try {
      const [st, ss] = await Promise.all([
        api<Statement[]>(`/statements?card_id=${selected}`),
        api<Subscription[]>(`/card-subscriptions?card_id=${selected}`),
      ])
      setStatements(st)
      setSubs(ss)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erro ao carregar.')
    }
  }, [selected])

  useEffect(() => {
    loadCards()
    api<Category[]>('/categories?include_inactive=true').then(setCategories).catch(() => undefined)
  }, [loadCards])
  useEffect(() => {
    loadStatements()
  }, [loadStatements])

  const close = useCallback(() => setModal(null), [])
  function done(message: string) {
    setModal(null)
    setNotice(message)
    setTimeout(() => setNotice(null), 3500)
    loadCards()
    loadStatements()
  }

  const card = cards?.find((c) => c.id === selected)
  const visible = (statements ?? []).filter((s) => s.status !== 'empty')
  const upcoming = visible.filter((s) => s.status !== 'paid')
  const paid = visible.filter((s) => s.status === 'paid').reverse()

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">Cartões</h1>
          <p className="mt-1 text-sm text-muted">Compras parceladas, faturas e pagamentos.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setModal({ type: 'card', card: null })}>
            Novo cartão
          </Button>
          {!!cards?.some((c) => c.active) && <Button onClick={() => setModal({ type: 'purchase' })}>+ Nova compra</Button>}
        </div>
      </header>

      {notice && <Alert kind="success">{notice}</Alert>}
      {error && <Alert kind="error">{error}</Alert>}

      {cards === null ? (
        <Spinner />
      ) : cards.length === 0 ? (
        <EmptyState title="Nenhum cartão cadastrado" action={<Button onClick={() => setModal({ type: 'card', card: null })}>Cadastrar cartão</Button>}>
          Cadastre seu cartão com os dias de fechamento e vencimento. As compras parceladas serão distribuídas automaticamente nas faturas.
        </EmptyState>
      ) : (
        <>
          <div className="-mx-4 flex snap-x gap-3 overflow-x-auto px-4 pb-2 sm:mx-0 sm:grid sm:grid-cols-2 sm:overflow-visible sm:px-0 lg:grid-cols-3">
            {cards.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => setSelected(c.id)}
                aria-pressed={c.id === selected}
                className={cx(
                  'flex min-w-[17rem] snap-start flex-col gap-4 rounded-2xl border p-5 text-left transition',
                  c.id === selected ? 'border-accent bg-brand text-brand-contrast' : 'border-line bg-surface hover:bg-surface-2',
                  !c.active && 'opacity-60',
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-display text-xl font-semibold">{c.nickname}</p>
                    <p className={cx('text-sm', c.id === selected ? 'opacity-80' : 'text-muted')}>
                      {c.institution || 'Cartão de crédito'}
                      {!c.active && ' · inativo'}
                    </p>
                  </div>
                  <span className={cx('rounded-full px-2.5 py-1 text-xs font-semibold', c.id === selected ? 'bg-white/15' : 'bg-surface-2')}>
                    fecha dia {c.closing_day} · vence dia {c.due_day}
                  </span>
                </div>
                <div className={c.id === selected ? '[&_p]:text-brand-contrast/80' : ''}>
                  <LimitBar card={c} />
                </div>
              </button>
            ))}
          </div>

          {card && (
            <div className="flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <h2 className="font-display text-xl font-semibold">Faturas · {card.nickname}</h2>
                <Button variant="ghost" className="min-h-9" onClick={() => setModal({ type: 'card', card })}>
                  Editar cartão
                </Button>
              </div>
              <section className="rounded-2xl border border-line bg-surface p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h3 className="font-display text-lg font-semibold">Assinaturas neste cartão</h3>
                    <p className="text-xs text-muted">Cobranças mensais que entram sozinhas em cada fatura.</p>
                  </div>
                  {card.active && (
                    <Button variant="secondary" className="min-h-9 px-3" onClick={() => setModal({ type: 'sub', sub: null })}>
                      + Assinatura
                    </Button>
                  )}
                </div>
                {subs.length === 0 ? (
                  <p className="mt-3 text-sm text-muted">Nenhuma assinatura. Cadastre streaming, apps ou academia para não precisar lançar todo mês.</p>
                ) : (
                  <ul className="mt-3 divide-y divide-line">
                    {subs.map((s) => (
                      <li key={s.id}>
                        <button type="button" onClick={() => setModal({ type: 'sub', sub: s })} className={cx('flex w-full items-center justify-between gap-3 py-2.5 text-left text-sm hover:bg-surface-2', !s.active && 'opacity-60')}>
                          <span className="min-w-0">
                            <span className="block truncate font-semibold">{s.description}{!s.active && ' (pausada)'}</span>
                            <span className="block text-muted">
                              Todo dia {s.charge_day} · {s.category_name}
                              {s.next_charge && ` · próxima cobrança ${formatDate(s.next_charge)}`}
                            </span>
                          </span>
                          <span className="tabular shrink-0 whitespace-nowrap font-semibold">{formatBRL(s.amount)}/mês</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
              {statements === null ? (
                <Spinner />
              ) : visible.length === 0 ? (
                <EmptyState title="Nenhuma fatura ainda">Registre uma compra neste cartão para gerar as faturas.</EmptyState>
              ) : (
                <>
                  <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {upcoming.map((s) => (
                      <li key={s.id}>
                        <Link to={`/cartoes/faturas/${s.id}`} className="flex flex-col gap-2 rounded-2xl border border-line bg-surface p-4 hover:bg-surface-2">
                          <div className="flex items-center justify-between gap-2">
                            <p className="font-semibold">{longMonth(s.reference_month)}</p>
                            <span className={cx('rounded-full px-2.5 py-0.5 text-xs font-semibold', STATEMENT_STATUS[s.status].cls)}>{STATEMENT_STATUS[s.status].label}</span>
                          </div>
                          <p className="tabular font-display text-2xl font-semibold">{formatBRL(s.total)}</p>
                          <p className="text-xs text-muted">
                            Vence em {formatDate(s.due_date)} · {s.items_count} {s.items_count === 1 ? 'item' : 'itens'}
                            {Number(s.paid) > 0 && ` · pago ${formatBRL(s.paid)}`}
                          </p>
                        </Link>
                      </li>
                    ))}
                  </ul>
                  {paid.length > 0 && (
                    <details className="rounded-2xl border border-line bg-surface p-4">
                      <summary className="cursor-pointer text-sm font-semibold">Faturas pagas ({paid.length})</summary>
                      <ul className="mt-3 divide-y divide-line">
                        {paid.map((s) => (
                          <li key={s.id}>
                            <Link to={`/cartoes/faturas/${s.id}`} className="flex justify-between py-2.5 text-sm hover:underline">
                              <span>{longMonth(s.reference_month)}</span>
                              <span className="tabular">{formatBRL(s.total)}</span>
                            </Link>
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                </>
              )}
            </div>
          )}
        </>
      )}

      <Modal open={modal?.type === 'card'} title={modal?.type === 'card' && modal.card ? 'Editar cartão' : 'Novo cartão'} onClose={close}>
        {modal?.type === 'card' && (
          <CardForm initial={modal.card} onSaved={() => done(modal.card ? 'Cartão atualizado.' : 'Cartão cadastrado.')} onDeleted={() => done('Cartão excluído.')} />
        )}
      </Modal>
      <Modal open={modal?.type === 'purchase'} title="Nova compra no cartão" onClose={close}>
        {modal?.type === 'purchase' && cards && (
          <PurchaseForm cards={cards} categories={categories} defaultCardId={card?.active ? card.id : undefined} onSaved={() => done('Compra registrada e distribuída nas faturas.')} onDeleted={() => done('Compra excluída.')} />
        )}
      </Modal>
      <Modal open={modal?.type === 'sub'} title={modal?.type === 'sub' && modal.sub ? 'Editar assinatura' : 'Nova assinatura no cartão'} onClose={close}>
        {modal?.type === 'sub' && cards && (
          <SubscriptionForm cards={cards} categories={categories} initial={modal.sub} defaultCardId={card?.active ? card.id : undefined} onDone={done} />
        )}
      </Modal>
    </div>
  )
}
