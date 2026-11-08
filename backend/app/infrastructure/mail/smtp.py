"""Mailer implementations: SMTP (Mailpit in development) and a no-op that only logs.

smtplib is blocking (like PHP's mail()), so it runs in a worker thread with
asyncio.to_thread: the event loop keeps serving other requests meanwhile.
"""

import asyncio
import smtplib
from email.message import EmailMessage as MimeMessage

import structlog

from app.core.config import Settings
from app.shared.mail import EmailMessage, Mailer

logger = structlog.get_logger(__name__)

SMTP_TIMEOUT_SECONDS = 10


class SmtpMailer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        sender: str,
        username: str | None = None,
        password: str | None = None,
        starttls: bool = False,
    ) -> None:
        self._host = host
        self._port = port
        self._sender = sender
        self._username = username
        self._password = password
        self._starttls = starttls

    async def send(self, message: EmailMessage) -> None:
        await asyncio.to_thread(self._send_blocking, message)

    def _send_blocking(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = self._sender
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text)
        with smtplib.SMTP(self._host, self._port, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
            if self._starttls:
                smtp.starttls()
            if self._username and self._password:
                smtp.login(self._username, self._password)
            smtp.send_message(mime)


class LoggingMailer:
    """Used when no SMTP server is configured: nothing is sent.

    Logs only who and what subject. Never the body: it may contain an invitation link.
    """

    async def send(self, message: EmailMessage) -> None:
        logger.info(
            "email_not_sent", reason="smtp_not_configured", to=message.to, subject=message.subject
        )


def build_mailer(settings: Settings) -> Mailer:
    if settings.smtp_host is None:
        return LoggingMailer()
    return SmtpMailer(
        host=settings.smtp_host,
        port=settings.smtp_port,
        sender=settings.mail_from,
        username=settings.smtp_username,
        password=settings.smtp_password.get_secret_value() if settings.smtp_password else None,
        starttls=settings.smtp_starttls,
    )
