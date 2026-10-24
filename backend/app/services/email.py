"""Envio de e-mails. Em desenvolvimento o SMTP aponta para o Mailpit (caixa local);
nos testes, um remetente em memória substitui o SMTP."""
import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Protocol

from app.config import get_settings

log = logging.getLogger("carteiria.email")


@dataclass
class SentEmail:
    to: str
    subject: str
    body: str


class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class SmtpEmailSender:
    def send(self, to: str, subject: str, body: str) -> None:
        s = get_settings()
        msg = EmailMessage()
        msg["From"] = s.mail_from
        msg["To"] = to
        msg["Subject"] = subject
        msg["Message-ID"] = make_msgid(domain="carteiria")
        msg.set_content(body)
        try:
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
                if s.smtp_starttls:
                    smtp.starttls()
                if s.smtp_user:
                    smtp.login(s.smtp_user, s.smtp_password)
                smtp.send_message(msg)
        except (OSError, smtplib.SMTPException):
            # Não registra o conteúdo (contém links com tokens).
            log.error("Falha ao enviar e-mail (assunto: %s)", subject)


class MemoryEmailSender:
    def __init__(self) -> None:
        self.outbox: list[SentEmail] = []

    def send(self, to: str, subject: str, body: str) -> None:
        self.outbox.append(SentEmail(to, subject, body))


_sender: EmailSender = SmtpEmailSender()


def get_email_sender() -> EmailSender:
    return _sender


def set_email_sender(sender: EmailSender) -> None:
    global _sender
    _sender = sender
