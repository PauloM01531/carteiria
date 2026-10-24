"""Comandos administrativos executados NO SERVIDOR com o papel dono do banco.

Uso:
  python -m app.cli promote-admin seu@email.com
  python -m app.cli registration-mode approval|invite|closed

A promoção a ADMIN não existe na API: nenhum usuário consegue se promover
pela internet. O papel da aplicação nem tem permissão de alterar a coluna `role`.
"""
import argparse
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_owner_engine
from app.models import User
from app.services import audit
from app.services.settings_service import set_registration_mode


def promote_admin(email: str) -> int:
    with Session(get_owner_engine()) as db:
        user = db.scalar(select(User).where(User.email == email.lower()))
        if user is None:
            print("Conta não encontrada. Cadastre-se pelo site primeiro.")
            return 1
        if user.email_verified_at is None:
            print("O e-mail desta conta ainda não foi verificado. Confirme o e-mail antes de promover.")
            return 1
        confirm = input(f"Promover '{user.display_name}' <{user.email}> a ADMIN? Digite SIM: ")
        if confirm.strip().lstrip("﻿").upper() != "SIM":
            print("Cancelado.")
            return 1
        user.role = "ADMIN"
        user.status = "active"
        audit.record(db, "admin_promoted", "success", target_user_id=user.id,
                     details={"via": "cli"}, actor_email="cli-servidor")
        db.commit()
        print("Conta promovida a ADMIN.")
        return 0


def reset_mfa(email: str) -> int:
    """Recuperação: remove o MFA de uma conta (ex.: celular perdido) e encerra as sessões dela."""
    from sqlalchemy import update

    from app.models import UserSession
    from app.services.sessions import utcnow

    with Session(get_owner_engine()) as db:
        user = db.scalar(select(User).where(User.email == email.lower()))
        if user is None:
            print("Conta não encontrada.")
            return 1
        if input(f"Remover a verificação em duas etapas de <{user.email}>? Digite SIM: ").strip().lstrip("\ufeff").upper() != "SIM":
            print("Cancelado.")
            return 1
        user.mfa_enabled_at = None
        user.mfa_secret_enc = None
        user.mfa_last_step = None
        db.execute(update(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
        audit.record(db, "mfa_reset", "success", target_user_id=user.id, actor_email="cli-servidor")
        db.commit()
        print("MFA removido. A pessoa deve configurar novamente ao entrar.")
        return 0


def registration_mode(mode: str) -> int:
    with Session(get_owner_engine()) as db:
        set_registration_mode(db, mode)
        audit.record(db, "registration_mode_changed", "success", actor_email="cli-servidor", details={"to": mode})
        db.commit()
    print(f"Modo de cadastro: {mode}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("promote-admin")
    a.add_argument("email")
    r = sub.add_parser("reset-mfa")
    r.add_argument("email")
    m = sub.add_parser("registration-mode")
    m.add_argument("mode", choices=["closed", "approval", "invite"])
    args = p.parse_args(argv)
    if args.cmd == "promote-admin":
        return promote_admin(args.email)
    if args.cmd == "reset-mfa":
        return reset_mfa(args.email)
    return registration_mode(args.mode)


if __name__ == "__main__":
    sys.exit(main())
