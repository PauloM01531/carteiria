import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Alert, Button, Card, ConfirmDialog, EmptyState, FullPageSpinner, Modal, cx } from '../../components/ui'
import { api } from '../../lib/api'
import { STATEMENT_STATUS, longMonth, type CreditCard, type Purchase, type StatementDetail } from '../../lib/cards'
import type { Category } from '../../lib/finance'
import { formatBRL, formatDate } from '../../lib/format'
import { PaymentForm, PurchaseForm } from './forms'

export default function StatementPage() {
  const { id } = useParams<{ id: string }>()
  const [st, setSt] = useState<StatementDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [paying, setPaying] = useState(false)
  const [editing, setEditing] = useState<Purchase | null>(null)
  const [cards, setCards] = useState<CreditCard[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [removing, setRemoving] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setSt(await api<StatementDetail>(`/statements/${id}`))
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erro ao carregar.')
    }
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  async function openPurchase(purchaseId: string) {
    try {
      const [p, c, cats] = await Promise.all([
        api<Purchase>(`/card-purchases/${purchaseId}`),
        api<CreditCard[]>('/cards'),
        api<Category[]>('/categories?include_inactive=true'),
      ])
      setCards(c)
      setCategories(cats)
      setEditing(p)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erro ao carregar.')
    }
  }

  async function removePayment() {
    if (!removing) return
    try {
      await api(`/statements/${id}/payments/${removing}`, { method: 'DELETE' })
      flash('Pagamento removido.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erro.')
    } finally {
      setRemoving(null)
    }
  }

  function flash(m: string) {
    setNotice(m)
    setTimeout(() => setNotice(null), 3500)
    load()
  }

  const closeEdit = useCallback(() => setEditing(null), [])
  const closePay = useCallback(() => setPaying(false), [])

  if (error && !st) {
    return (
      <div className="flex flex-col gap-4">
        <Alert kind="error">{error}</Alert>
        <Link to="/cartoes" className="font-semibold underline">Voltar para cartões</Link>
      </div>
    )
  }
  if (!st) return <FullPageSpinner />
  const status = STATEMENT_STATUS[st.status]

  return (
    <div className="flex flex-col gap-6">
      <Link to="/cartoes" className="text-sm font-semibold text-muted hover:text-ink">‹ Cartões</Link>
      <header className="flex flex-col gap-2">
        <p className="text-sm font-semibold text-muted">Fatura · {st.card_nickname}</p>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-display text-3xl font-semibold tracking-tight">{longMonth(st.reference_month)}</h1>
          <span className={cx('rounded-full px-3 py-1 text-xs font-semibold', status.cls)}>{status.label}</span>
        </div>
        <p className="text-sm text-muted">
          Fecha em {formatDate(st.closing_date)} · vence em {formatDate(st.due_date)}
        </p>
      </header>

      {notice && <Alert kind="success">{notice}</Alert>}
      {error && <Alert kind="error">{error}</Alert>}

      <div className="grid grid-cols-3 gap-2 sm:gap-4">
        {[
          { label: 'Total', value: st.total },
          { label: 'Pago', value: st.paid, cls: 'text-positive' },
          { label: 'Em aberto', value: st.remaining, cls: Number(st.remaining) > 0 ? 'text-negative' : '' },
        ].map((k) => (
          <Card key={k.label} className="p-3 sm:p-5">
            <p className="text-xs text-muted sm:text-sm">{k.label}</p>
            <p className={cx('tabular mt-1 truncate font-display text-base font-semibold sm:text-2xl', k.cls)}>{formatBRL(k.value)}</p>
          </Card>
        ))}
      </div>

      {Number(st.remaining) > 0 && (
        <Button onClick={() => setPaying(true)} className="self-start">
          Registrar pagamento
        </Button>
      )}

      <Card>
        <h2 className="font-display text-xl font-semibold">Compras e parcelas</h2>
        {st.items.length === 0 ? (
          <div className="mt-3"><EmptyState title="Fatura vazia">Nenhuma parcela nesta competência.</EmptyState></div>
        ) : (
          <ul className="mt-3 divide-y divide-line">
            {st.items.map((i) => (
              <li key={i.installment_id}>
                <button type="button" onClick={() => openPurchase(i.purchase_id)} className="flex w-full items-center justify-between gap-3 py-3 text-left text-sm hover:bg-surface-2">
                  <span className="min-w-0">
                    <span className="block truncate font-semibold">{i.description}</span>
                    <span className="block text-muted">
                      {formatDate(i.purchase_date)} · {i.category_name}
                      {i.installments_count > 1 && ` · parcela ${i.number}/${i.installments_count}`}
                      {i.is_subscription && <span className="ml-2 rounded-full bg-accent-soft px-2 py-0.5 text-xs font-semibold text-ink">assinatura</span>}
                    </span>
                  </span>
                  <span className="tabular shrink-0 font-semibold">{formatBRL(i.amount)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {st.payments.length > 0 && (
        <Card>
          <h2 className="font-display text-xl font-semibold">Pagamentos</h2>
          <ul className="mt-3 divide-y divide-line">
            {st.payments.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-3 py-3 text-sm">
                <span>Pago em {formatDate(p.paid_on)}</span>
                <span className="flex items-center gap-3">
                  <span className="tabular font-semibold text-positive">{formatBRL(p.amount)}</span>
                  <Button variant="ghost" className="min-h-8 px-2 text-negative" onClick={() => setRemoving(p.id)}>
                    Remover
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Modal open={paying} title="Pagamento da fatura" onClose={closePay}>
        {paying && <PaymentForm statementId={st.id} remaining={st.remaining} onSaved={() => { setPaying(false); flash('Pagamento registrado.') }} />}
      </Modal>
      <Modal open={!!editing} title="Editar compra" onClose={closeEdit}>
        {editing && (
          <PurchaseForm
            cards={cards}
            categories={categories}
            initial={editing}
            onSaved={() => { setEditing(null); flash('Compra atualizada.') }}
            onDeleted={() => { setEditing(null); flash('Compra excluída.') }}
          />
        )}
      </Modal>
      <ConfirmDialog open={!!removing} title="Remover pagamento?" confirmLabel="Remover" danger onConfirm={removePayment} onCancel={() => setRemoving(null)}>
        O valor volta a constar como em aberto nesta fatura.
      </ConfirmDialog>
    </div>
  )
}
