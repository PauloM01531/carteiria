"""Exportação CSV dos dados do próprio usuário (portabilidade - LGPD).

- Separador ";" e decimal com vírgula (abre direto no Excel em português), UTF-8 com BOM.
- Proteção contra injeção de fórmulas: textos que começam com = + - @ (ou tab/CR) recebem um apóstrofo.
- Todas as consultas filtram pelo user_id da sessão; o RLS é a segunda camada.
"""
import csv
import io
import json
import uuid
import zipfile
from collections.abc import Callable, Iterable
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BillOccurrence,
    Budget,
    Card,
    CardPurchase,
    CardStatement,
    Category,
    Goal,
    GoalContribution,
    PlannedPurchase,
    Installment,
    RecurringBill,
    StatementPayment,
    Transaction,
    User,
    UserPreferences,
)

KIND = {"income": "Receita", "expense": "Despesa"}
TX_STATUS = {"settled": "Pago/Recebido", "pending": "Pendente"}
FORMULA_PREFIX = ("=", "+", "-", "@", "\t", "\r")


def cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Sim" if v else "Não"
    if isinstance(v, Decimal):
        return f"{v:.2f}".replace(".", ",")
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y %H:%M")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    s = str(v)
    if s.startswith(FORMULA_PREFIX):
        s = "'" + s
    return s


def to_csv(header: list[str], rows: Iterable[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    w.writerow(header)
    for r in rows:
        w.writerow([cell(v) for v in r])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def _transactions(db: Session, uid: uuid.UUID, start: date | None, end: date | None) -> bytes:
    stmt = select(Transaction, Category.name).join(Category, Category.id == Transaction.category_id).where(Transaction.user_id == uid)
    if start:
        stmt = stmt.where(Transaction.occurred_on >= start)
    if end:
        stmt = stmt.where(Transaction.occurred_on <= end)
    rows = db.execute(stmt.order_by(Transaction.occurred_on)).all()
    return to_csv(["Data", "Tipo", "Descrição", "Valor", "Categoria", "Forma", "Situação", "Observações"],
                  [[t.occurred_on, KIND[t.kind], t.description, t.amount, c, t.payment_method, TX_STATUS[t.status], t.notes] for t, c in rows])


def _purchases(db: Session, uid: uuid.UUID, start, end) -> bytes:
    stmt = select(CardPurchase).where(CardPurchase.user_id == uid)
    if start:
        stmt = stmt.where(CardPurchase.purchase_date >= start)
    if end:
        stmt = stmt.where(CardPurchase.purchase_date <= end)
    rows = db.scalars(stmt.order_by(CardPurchase.purchase_date)).unique().all()
    return to_csv(["Data da compra", "Cartão", "Descrição", "Valor total", "Parcelas", "Primeira fatura", "Categoria", "Observações"],
                  [[p.purchase_date, p.card.nickname, p.description, p.total_amount, p.installments_count,
                    p.first_statement_month.strftime("%m/%Y"), p.category.name, p.notes] for p in rows])


def _installments(db: Session, uid: uuid.UUID, *_: object) -> bytes:
    rows = db.execute(
        select(Installment, CardPurchase, CardStatement)
        .join(CardPurchase, CardPurchase.id == Installment.purchase_id)
        .join(CardStatement, CardStatement.id == Installment.statement_id)
        .where(Installment.user_id == uid).order_by(CardStatement.reference_month, CardPurchase.description)
    ).unique().all()
    return to_csv(["Competência", "Cartão", "Compra", "Parcela", "Valor", "Vencimento da fatura"],
                  [[s.reference_month.strftime("%m/%Y"), s.card.nickname, p.description, f"{i.number}/{p.installments_count}",
                    i.amount, s.due_date] for i, p, s in rows])


def _statement_payments(db: Session, uid: uuid.UUID, *_: object) -> bytes:
    rows = db.execute(select(StatementPayment, CardStatement).join(CardStatement, CardStatement.id == StatementPayment.statement_id)
                      .where(StatementPayment.user_id == uid).order_by(StatementPayment.paid_on)).unique().all()
    return to_csv(["Data do pagamento", "Cartão", "Competência", "Valor", "Observações"],
                  [[p.paid_on, s.card.nickname, s.reference_month.strftime("%m/%Y"), p.amount, p.notes] for p, s in rows])


def _cards(db: Session, uid: uuid.UUID, *_: object) -> bytes:
    rows = db.scalars(select(Card).where(Card.user_id == uid).order_by(Card.nickname)).all()
    return to_csv(["Apelido", "Instituição", "Fechamento", "Vencimento", "Limite", "Ativo"],
                  [[c.nickname, c.institution, c.closing_day, c.due_day, c.credit_limit, c.active] for c in rows])


def _bills(db: Session, uid: uuid.UUID, *_: object) -> bytes:
    rows = db.execute(select(BillOccurrence, RecurringBill).join(RecurringBill, RecurringBill.id == BillOccurrence.bill_id)
                      .where(BillOccurrence.user_id == uid).order_by(BillOccurrence.due_date)).unique().all()
    return to_csv(["Conta", "Vencimento", "Valor", "Situação", "Pago em", "Periodicidade"],
                  [[b.name, o.due_date, o.amount, "Paga" if o.status == "paid" else "Pendente", o.paid_on, b.frequency]
                   for o, b in rows])


def _budgets(db: Session, uid: uuid.UUID, *_: object) -> bytes:
    rows = db.scalars(select(Budget).where(Budget.user_id == uid).order_by(Budget.month)).all()
    return to_csv(["Mês", "Categoria", "Limite"], [[b.month.strftime("%m/%Y"), b.category.name, b.limit_amount] for b in rows])


def _goals(db: Session, uid: uuid.UUID, *_: object) -> bytes:
    rows = db.execute(select(GoalContribution, Goal).join(Goal, Goal.id == GoalContribution.goal_id)
                      .where(GoalContribution.user_id == uid).order_by(Goal.name, GoalContribution.contributed_on)).all()
    goals = db.scalars(select(Goal).where(Goal.user_id == uid).order_by(Goal.name)).unique().all()
    lines = [[g.name, "Meta", g.target_amount, g.deadline, g.notes] for g in goals]
    lines += [[g.name, "Aporte" if c.amount > 0 else "Retirada", c.amount, c.contributed_on, c.notes] for c, g in rows]
    return to_csv(["Meta", "Registro", "Valor", "Data/prazo", "Observações"], lines)


def _categories(db: Session, uid: uuid.UUID, *_: object) -> bytes:
    rows = db.scalars(select(Category).where(Category.user_id == uid).order_by(Category.kind, Category.name)).all()
    return to_csv(["Nome", "Tipo", "Ativa"], [[c.name, KIND[c.kind], c.active] for c in rows])


def _planned(db: Session, uid: uuid.UUID, *_: object) -> bytes:
    rows = db.scalars(select(PlannedPurchase).where(PlannedPurchase.user_id == uid).order_by(PlannedPurchase.first_installment_date)).unique().all()
    return to_csv(["Compra planejada", "Valor total", "Parcelas", "Primeira parcela", "Categoria", "Observações"],
                  [[p.name, p.total_amount, p.installments_count, p.first_installment_date, p.category.name, p.notes] for p in rows])


DATASETS: dict[str, tuple[str, Callable]] = {
    "lancamentos": ("lancamentos.csv", _transactions),
    "compras-cartao": ("compras_cartao.csv", _purchases),
    "parcelas": ("parcelas.csv", _installments),
    "pagamentos-fatura": ("pagamentos_fatura.csv", _statement_payments),
    "cartoes": ("cartoes.csv", _cards),
    "contas-recorrentes": ("contas_recorrentes.csv", _bills),
    "orcamentos": ("orcamentos.csv", _budgets),
    "metas": ("metas.csv", _goals),
    "categorias": ("categorias.csv", _categories),
    "compras-planejadas": ("compras_planejadas.csv", _planned),
}


def export_dataset(db: Session, uid: uuid.UUID, name: str, start: date | None = None, end: date | None = None) -> tuple[str, bytes]:
    filename, fn = DATASETS[name]
    return filename, fn(db, uid, start, end)


def export_all(db: Session, user: User) -> bytes:
    """ZIP com todos os dados do usuário (CSV) + perfil (JSON), sem hash de senha nem tokens."""
    prefs = db.scalar(select(UserPreferences).where(UserPreferences.user_id == user.id))
    profile = {
        "nome": user.display_name, "email": user.email, "papel": user.role, "situacao": user.status,
        "criado_em": user.created_at.isoformat(), "email_verificado": user.email_verified_at is not None,
        "preferencias": {"tema": prefs.theme if prefs else "system"},
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("perfil.json", json.dumps(profile, ensure_ascii=False, indent=2))
        for key in DATASETS:
            filename, content = export_dataset(db, user.id, key)
            z.writestr(filename, content)
        z.writestr("LEIA-ME.txt", "Exportação dos seus dados da CarteirIA.\r\nArquivos CSV separados por ';' e valores com vírgula decimal.\r\n")
    return buf.getvalue()
