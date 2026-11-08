"""Outgoing email, as ports. Use cases depend on these Protocols, never on SMTP.

- `Mailer` sends one message now (SMTP in production code, a list in tests).
- `OutgoingMail` is what use cases receive: it *queues* a message to be sent after the
  response, once the transaction has been committed. If sending fails, the request has
  already succeeded: the email is a convenience, never the only way to get a link.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class EmailMessage:
    to: str
    subject: str
    text: str  # plain text: no HTML templates until there is a real need


class Mailer(Protocol):
    async def send(self, message: EmailMessage) -> None: ...


class OutgoingMail(Protocol):
    def queue(self, message: EmailMessage) -> None: ...
