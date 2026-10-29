"""Compras planejadas: avalia se uma compra futura cabe no orçamento, mês a mês.

A compra planejada é uma SIMULAÇÃO: não vira despesa, compra de cartão nem entra em
relatórios. A análise é recalculada a cada consulta com os dados reais do usuário, então
muda sozinha quando receitas, despesas, contas fixas ou cartões mudam.

Para cada mês de parcela:
  receita do mês        = receitas registradas no mês; se não houver, média dos últimos 3 meses
                          completos (só se houver receita em pelo menos 2 deles)
  compromissos do mês   = despesas já lançadas no mês
                        + parcelas de cartão já cadastradas com fatura no mês (competência)
                        + assinaturas no cartão ainda não geradas para o mês
                        + contas fixas previstas (pendentes) do mês
                        + gastos do dia a dia estimados (média histórica, descontando o que já foi lançado)
                        + parcelas de OUTRAS compras planejadas no mês
  sobra antes           = receita − compromissos
  sobra depois          = sobra antes − parcela desta compra

Regras para não contar duas vezes:
  - contas fixas pagas já viraram lançamentos: só as pendentes entram como "previstas";
  - cobranças de assinatura já geradas já são parcelas de cartão: só as que faltam são projetadas;
  - o gasto do dia a dia estimado desconta o que já foi lançado no mês;
  - limite de cartão nunca é tratado como dinheiro disponível;
  - a própria compra planejada não é compra de cartão, então não aparece nas parcelas existentes.
"""
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    BillOccurrence,
    Budget,
    CardPurchase,
    CardStatement,
    CardSubscription,
    Installment,
    PlannedPurchase,
    RecurringBill,
    Transaction,
)
from app.services.bills import due_dates
from app.services.calendar import add_months, first_of_month, today
from app.services.cards import split_installments, suggest_reference_month
from app.services.reports import month_end, q
from app.services.subscriptions import charge_dates
from app.services.transactions import validate_category

ZERO = Decimal("0.00")
HISTORY_MONTHS = 3
MIN_INCOME_MONTHS = 2          # meses com receita necessários para estimar a receita futura
ATTENTION_MARGIN = Decimal("0.10")   # sobra final abaixo de 10% da receita = atenção
ATTENTION_SHARE = Decimal("0.50")    # parcela consumindo mais de 50% da sobra = atenção

STATUS_RANK = {"fits": 0, "insufficient": 1, "attention": 2, "over": 3}


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message})


def brl(v: Decimal) -> str:
    s = f"{v:,.2f}"
    return "R$ " + s.replace(",", "_").replace(".", ",").replace("_", ".")


def pct(part: Decimal, whole: Decimal) -> str:
    """Percentual com vírgula decimal (texto exibido ao usuário)."""
    v = (part / whole * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) if whole else Decimal("0.0")
    return f"{v}".replace(".", ",")


# --------------------------------------------------------------------------- cronograma

def schedule(total: Decimal, count: int, first_date: date) -> list[tuple[date, Decimal]]:
    """Parcelas (mês, valor). Mesma regra das compras no cartão: centavos na última parcela."""
    month = first_of_month(first_date)
    return [(add_months(month, i), v) for i, v in enumerate(split_installments(total, count))]


# --------------------------------------------------------------------------- dados reais

@dataclass
class History:
    months: list[date]
    income_months_with_data: int
    income_avg: Decimal | None
    variable_avg: Decimal | None   # gastos do dia a dia (lançamentos fora de contas fixas + compras à vista no cartão)


def _bill_tx_ids(db: Session, uid: uuid.UUID) -> set[uuid.UUID]:
    return set(db.scalars(select(BillOccurrence.transaction_id).where(
        BillOccurrence.user_id == uid, BillOccurrence.transaction_id.is_not(None))))


def _tx_month(db: Session, uid: uuid.UUID, m: date, bill_tx: set[uuid.UUID]) -> dict[str, Decimal]:
    """Lançamentos registrados no mês (pagos e pendentes)."""
    out = {"income": ZERO, "expense": ZERO, "variable": ZERO}
    rows = db.execute(select(Transaction.id, Transaction.kind, Transaction.amount).where(
        Transaction.user_id == uid, Transaction.occurred_on >= m, Transaction.occurred_on <= month_end(m))).all()
    for tid, kind, amount in rows:
        out[kind] += amount
        if kind == "expense" and tid not in bill_tx:
            out["variable"] += amount
    return out


def _card_month(db: Session, uid: uuid.UUID, m: date) -> dict[str, Decimal]:
    """Parcelas de cartão já cadastradas com fatura (competência) no mês."""
    rows = db.execute(
        select(Installment.amount, CardPurchase.installments_count, CardPurchase.subscription_id)
        .join(CardPurchase, CardPurchase.id == Installment.purchase_id)
        .join(CardStatement, CardStatement.id == Installment.statement_id)
        .where(Installment.user_id == uid, CardStatement.reference_month == m)
    ).all()
    total = sum((a for a, _, _ in rows), ZERO)
    one_off = sum((a for a, n, s in rows if n == 1 and s is None), ZERO)  # compras à vista comuns
    return {"total": total, "one_off": one_off}


def history(db: Session, uid: uuid.UUID, ref: date, bill_tx: set[uuid.UUID]) -> History:
    current = first_of_month(ref)
    months = [add_months(current, -i) for i in range(1, HISTORY_MONTHS + 1)]
    incomes, variables = [], []
    for m in months:
        tx = _tx_month(db, uid, m, bill_tx)
        incomes.append(tx["income"])
        variables.append(tx["variable"] + _card_month(db, uid, m)["one_off"])
    with_income = [v for v in incomes if v > 0]
    income_avg = q(sum(with_income, ZERO) / len(with_income)) if len(with_income) >= MIN_INCOME_MONTHS else None
    any_activity = any(v > 0 for v in variables) or bool(with_income)
    variable_avg = q(sum(variables, ZERO) / len(variables)) if any_activity else None
    return History(months, len(with_income), income_avg, variable_avg)


def _bills_month(db: Session, uid: uuid.UUID, m: date) -> tuple[Decimal, list[str]]:
    """Contas fixas previstas (ainda não pagas) com vencimento no mês. Retorna (total, contas sem valor)."""
    total, missing = ZERO, []
    bills = db.scalars(select(RecurringBill).where(RecurringBill.user_id == uid, RecurringBill.active.is_(True))).unique().all()
    occs = {(o.bill_id, o.due_date): o for o in db.scalars(select(BillOccurrence).where(
        BillOccurrence.user_id == uid, BillOccurrence.due_date >= m, BillOccurrence.due_date <= month_end(m)))}
    for b in bills:
        for d in due_dates(b, m, month_end(m)):
            occ = occs.get((b.id, d))
            if occ is not None and occ.status == "paid":
                continue  # já é um lançamento do mês
            value = (occ.amount if occ is not None else None) or b.expected_amount
            if value is None:
                last_paid = db.scalar(select(BillOccurrence.amount).where(
                    BillOccurrence.bill_id == b.id, BillOccurrence.status == "paid", BillOccurrence.amount.is_not(None))
                    .order_by(BillOccurrence.due_date.desc()).limit(1))
                if last_paid is None:
                    missing.append(b.name)
                    continue
                value = last_paid
            total += value
    return total, missing


def _subscriptions_projected(db: Session, uid: uuid.UUID, m: date) -> Decimal:
    """Assinaturas no cartão cuja cobrança cai na fatura do mês mas ainda não foi gerada."""
    total = ZERO
    subs = db.scalars(select(CardSubscription).where(
        CardSubscription.user_id == uid, CardSubscription.active.is_(True))).unique().all()
    for s in subs:
        if not s.card.active:
            continue
        generated = set(db.scalars(select(CardPurchase.purchase_date).where(
            CardPurchase.subscription_id == s.id, CardPurchase.user_id == uid)))
        for d in charge_dates(s, month_end(m)):
            if d >= add_months(m, -1) and d not in generated and suggest_reference_month(s.card.closing_day, d) == m:
                total += s.amount
    return total


# --------------------------------------------------------------------------- análise

@dataclass
class MonthResult:
    month: date
    installment: Decimal
    number: int
    income: Decimal | None
    income_source: str | None            # "registrada" | "media" | None
    registered_expenses: Decimal
    card_installments: Decimal
    subscriptions_projected: Decimal
    bills_pending: Decimal
    variable_estimate: Decimal
    other_planned: Decimal
    committed: Decimal
    balance_before: Decimal | None
    balance_after: Decimal | None
    status: str                          # fits | attention | over | insufficient
    factors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def analyze(db: Session, uid: uuid.UUID, name: str, total: Decimal, count: int, first_date: date,
            category_id: uuid.UUID | None, exclude_id: uuid.UUID | None = None, ref: date | None = None) -> dict:
    ref = ref or today()
    current = first_of_month(ref)
    bill_tx = _bill_tx_ids(db, uid)
    hist = history(db, uid, ref, bill_tx)
    plan = schedule(total, count, first_date)

    others = db.scalars(select(PlannedPurchase).where(PlannedPurchase.user_id == uid)).unique().all()
    other_by_month: dict[date, Decimal] = {}
    other_names: dict[date, list[str]] = {}
    for o in others:
        if o.id == exclude_id:
            continue
        for m, v in schedule(o.total_amount, o.installments_count, o.first_installment_date):
            other_by_month[m] = other_by_month.get(m, ZERO) + v
            other_names.setdefault(m, []).append(o.name)

    budgets = {}
    if category_id:
        budgets = {b.month: b for b in db.scalars(select(Budget).where(
            Budget.user_id == uid, Budget.category_id == category_id)).unique().all()}

    months: list[MonthResult] = []
    for i, (m, inst) in enumerate(plan):
        past = m < current
        tx = _tx_month(db, uid, m, bill_tx)
        card = _card_month(db, uid, m)
        subs = ZERO if past else _subscriptions_projected(db, uid, m)
        bills, missing_bills = (ZERO, []) if past else _bills_month(db, uid, m)
        notes: list[str] = []

        # Receita
        if tx["income"] > 0:
            income, source = tx["income"], "registrada"
        elif not past and hist.income_avg is not None:
            income, source = hist.income_avg, "media"
            notes.append(f"Receita estimada pela média dos últimos meses com receita ({brl(hist.income_avg)}), "
                         "pois não há receitas lançadas neste mês.")
        else:
            income, source = None, None
            notes.append("Não há receitas lançadas neste mês nem histórico suficiente (pelo menos 2 dos últimos "
                         "3 meses com receita) para estimar.")

        # Gastos do dia a dia ainda não lançados (estimativa pela média, sem contar duas vezes)
        variable_registered = tx["variable"] + card["one_off"]
        variable_estimate = ZERO
        if not past and hist.variable_avg is not None:
            variable_estimate = max(hist.variable_avg - variable_registered, ZERO)
        elif not past:
            notes.append("Sem histórico de despesas para estimar os gastos habituais que ainda não foram lançados.")
        if missing_bills:
            notes.append("Conta(s) fixa(s) de valor variável sem valor informado nem pagamento anterior: "
                         + ", ".join(missing_bills) + ". Elas não entraram no cálculo.")

        other = other_by_month.get(m, ZERO)
        committed = q(tx["expense"] + card["total"] + subs + bills + variable_estimate + other)
        before = q(income - committed) if income is not None else None
        after = q(before - inst) if before is not None else None

        # Classificação e fatores
        factors: list[str] = []
        if income is None:
            status = "insufficient"
            factors.append(f"Sem receita conhecida para o mês; os compromissos conhecidos somam {brl(committed)}.")
        else:
            factors.append(f"Receita {'lançada' if source == 'registrada' else 'estimada'}: {brl(income)}.")
            factors.append(f"Compromissos do mês: {brl(committed)} (sobra antes da compra: {brl(before)}).")
            if after < 0:
                status = "over"
                factors.append(f"Depois da parcela de {brl(inst)}, faltariam {brl(-after)} no mês.")
            else:
                status = "fits"
                margin = q(income * ATTENTION_MARGIN)
                if after < margin:
                    status = "attention"
                    factors.append(f"Sobram só {brl(after)} depois da parcela, menos de 10% da receita ({brl(margin)}).")
                if before > 0 and inst > before * ATTENTION_SHARE:
                    status = "attention"
                    factors.append(f"A parcela consome {pct(inst, before)}% do que sobraria no mês.")
                if status == "fits":
                    factors.append(f"Depois da parcela ainda sobram {brl(after)} ({pct(after, income)}% da receita).")
        if card["total"] > 0:
            factors.append(f"Inclui {brl(card['total'])} de parcelas de cartão já cadastradas para a fatura do mês.")
        if bills > 0:
            factors.append(f"Inclui {brl(bills)} de contas fixas previstas.")
        if other > 0:
            factors.append(f"Inclui {brl(other)} de outras compras planejadas: " + ", ".join(other_names.get(m, [])) + ".")
        b = budgets.get(m)
        if b is not None:
            spent = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == uid, Transaction.category_id == b.category_id, Transaction.kind == "expense",
                Transaction.occurred_on >= m, Transaction.occurred_on <= month_end(m)))
            spent = Decimal(spent) + db.scalar(select(func.coalesce(func.sum(Installment.amount), 0))
                                               .join(CardPurchase, CardPurchase.id == Installment.purchase_id)
                                               .join(CardStatement, CardStatement.id == Installment.statement_id)
                                               .where(Installment.user_id == uid, CardPurchase.category_id == b.category_id,
                                                      CardStatement.reference_month == m))
            if spent + inst > b.limit_amount:
                factors.append(f"Com a parcela, a categoria passaria do orçamento definido ({brl(b.limit_amount)}).")
                if status == "fits":
                    status = "attention"
        if past:
            notes.append("Mês já passado: considerados apenas os valores lançados.")

        months.append(MonthResult(m, inst, i + 1, income, source, q(tx["expense"]), q(card["total"]), q(subs), q(bills),
                                  q(variable_estimate), q(other), committed, before, after, status, factors, notes))

    # Resumo
    counts = {k: sum(1 for r in months if r.status == k) for k in STATUS_RANK}
    known = [r for r in months if r.balance_after is not None]
    worst = min(known, key=lambda r: r.balance_after) if known else None
    overall = max((r.status for r in months), key=lambda s: STATUS_RANK[s])
    if counts["over"]:
        headline = f"Acima do orçamento em {counts['over']} de {len(months)} mês(es)."
    elif counts["attention"]:
        headline = f"Cabe, mas com atenção em {counts['attention']} de {len(months)} mês(es)."
    elif counts["insufficient"]:
        headline = f"Cabe nos meses com dados, mas faltam dados em {counts['insufficient']} mês(es)."
    else:
        headline = "Cabe no orçamento em todos os meses analisados."

    confidence_notes = []
    if hist.income_avg is None:
        confidence_notes.append("Há menos de 2 meses com receitas nos últimos 3 meses: para meses futuros sem receitas "
                                "lançadas não é possível estimar a sobra.")
    if hist.variable_avg is None:
        confidence_notes.append("Não há histórico de despesas: o cálculo considera só compromissos já cadastrados.")
    return {
        "name": name,
        "total_amount": q(total),
        "installments_count": count,
        "installment_amount": plan[0][1],
        "last_installment_amount": plan[-1][1],
        "first_month": plan[0][0],
        "last_month": plan[-1][0],
        "overall_status": overall,
        "headline": headline,
        "status_counts": counts,
        "worst_month": worst.month if worst else None,
        "worst_balance_after": worst.balance_after if worst else None,
        "average_balance_after": q(sum((r.balance_after for r in known), ZERO) / len(known)) if known else None,
        "history_months": hist.months,
        "history_income_avg": hist.income_avg,
        "history_variable_avg": hist.variable_avg,
        "confidence_notes": confidence_notes,
        "months": [r.__dict__ for r in months],
    }


# --------------------------------------------------------------------------- CRUD com dono

def get(db: Session, uid: uuid.UUID, pid: uuid.UUID) -> PlannedPurchase:
    p = db.scalar(select(PlannedPurchase).where(PlannedPurchase.id == pid, PlannedPurchase.user_id == uid))
    if p is None:
        raise _err(404, "not_found", "Compra planejada não encontrada.")
    return p


def check_inputs(db: Session, uid: uuid.UUID, total: Decimal, count: int, category_id: uuid.UUID,
                 allow_inactive_id: uuid.UUID | None = None) -> None:
    validate_category(db, uid, category_id, "expense", allow_inactive_id=allow_inactive_id)
    split_installments(total, count)  # recusa valor pequeno demais para o número de parcelas


def analyze_saved(db: Session, uid: uuid.UUID, p: PlannedPurchase) -> dict:
    return analyze(db, uid, p.name, p.total_amount, p.installments_count, p.first_installment_date,
                   p.category_id, exclude_id=p.id)


