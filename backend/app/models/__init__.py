"""Modelos do banco. Importar este pacote registra todas as tabelas no metadata."""
from app.models.base import Base
from app.models.identity import AuthToken, User, UserSession
from app.models.admin import AppSetting, AuditLog, Invite
from app.models.preferences import UserPreferences
from app.models.finance import Category, Transaction
from app.models.cards import (
    BillOccurrence,
    Card,
    CardPurchase,
    CardStatement,
    CardSubscription,
    Installment,
    RecurringBill,
    StatementPayment,
)
from app.models.planning import Budget, Goal, GoalContribution, PlannedPurchase

__all__ = [
    "Base",
    "User",
    "UserSession",
    "AuthToken",
    "Invite",
    "AppSetting",
    "AuditLog",
    "UserPreferences",
    "Category",
    "Transaction",
    "Card",
    "CardStatement",
    "CardPurchase",
    "CardSubscription",
    "Installment",
    "StatementPayment",
    "RecurringBill",
    "BillOccurrence",
    "Budget",
    "Goal",
    "GoalContribution",
    "PlannedPurchase",
]
