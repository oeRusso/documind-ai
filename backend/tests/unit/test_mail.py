"""Mailers: the SMTP conversation (with a fake smtplib) and the background sender."""

import smtplib
from email.message import EmailMessage as MimeMessage
from typing import Any, ClassVar

import pytest
from fastapi import BackgroundTasks

from app.core.config import Settings
from app.core.mail import BackgroundMail
from app.infrastructure.mail import smtp
from app.infrastructure.mail.smtp import LoggingMailer, SmtpMailer, build_mailer
from app.shared.mail import EmailMessage
from tests.fakes import FakeOutgoingMail

MESSAGE = EmailMessage(to="dana@example.com", subject="Hola", text="Link: https://x/#token=abc")


class FakeSmtp:
    """Stands in for smtplib.SMTP and records what the mailer did."""

    instances: ClassVar[list["FakeSmtp"]] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.address = (host, port, timeout)
        self.calls: list[str] = []
        self.sent: list[MimeMessage] = []
        FakeSmtp.instances.append(self)

    def __enter__(self) -> "FakeSmtp":
        return self

    def __exit__(self, *_: Any) -> None:
        self.calls.append("quit")

    def starttls(self) -> None:
        self.calls.append("starttls")

    def login(self, username: str, password: str) -> None:
        self.calls.append(f"login:{username}")

    def send_message(self, message: MimeMessage) -> None:
        self.calls.append("send")
        self.sent.append(message)


@pytest.fixture
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> list[FakeSmtp]:
    FakeSmtp.instances = []
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    return FakeSmtp.instances


async def test_smtp_mailer_sends_a_plain_text_message(fake_smtp: list[FakeSmtp]) -> None:
    mailer = SmtpMailer(host="mailpit", port=1025, sender="DocuMind <no-reply@x.test>")

    await mailer.send(MESSAGE)

    [server] = fake_smtp
    assert server.address == ("mailpit", 1025, smtp.SMTP_TIMEOUT_SECONDS)
    assert server.calls == ["send", "quit"]  # Mailpit: no TLS, no login
    [sent] = server.sent
    assert (sent["From"], sent["To"], sent["Subject"]) == (
        "DocuMind <no-reply@x.test>",
        "dana@example.com",
        "Hola",
    )
    assert "https://x/#token=abc" in sent.get_content()


async def test_smtp_mailer_uses_starttls_and_login_when_configured(
    fake_smtp: list[FakeSmtp],
) -> None:
    mailer = SmtpMailer(
        host="smtp.example",
        port=587,
        sender="x@x.test",
        username="user",
        password="pass",  # pragma: allowlist secret
        starttls=True,
    )

    await mailer.send(MESSAGE)

    assert fake_smtp[0].calls == ["starttls", "login:user", "send", "quit"]


def test_without_smtp_host_nothing_is_sent(offline_settings: Settings) -> None:
    assert isinstance(build_mailer(offline_settings), LoggingMailer)
    with_host = offline_settings.model_copy(update={"smtp_host": "mailpit"})
    assert isinstance(build_mailer(with_host), SmtpMailer)


async def test_background_mail_sends_after_the_response() -> None:
    tasks = BackgroundTasks()
    mailer = FakeOutgoingMail()

    BackgroundMail(tasks, mailer).queue(MESSAGE)
    assert mailer.sent == []  # nothing yet: it runs when FastAPI runs the background tasks
    await tasks()

    assert mailer.sent == [MESSAGE]


async def test_a_failing_email_is_logged_and_swallowed() -> None:
    class BrokenMailer:
        async def send(self, message: EmailMessage) -> None:
            raise ConnectionRefusedError

    tasks = BackgroundTasks()
    BackgroundMail(tasks, BrokenMailer()).queue(MESSAGE)

    await tasks()  # does not raise
