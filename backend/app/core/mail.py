"""OutgoingMail for HTTP requests: messages are sent by FastAPI BackgroundTasks, which run
after the response is sent (and after get_session has committed)."""

from typing import Annotated

import structlog
from fastapi import BackgroundTasks, Depends, Request

from app.shared.mail import EmailMessage, Mailer

logger = structlog.get_logger(__name__)


class BackgroundMail:
    def __init__(self, background_tasks: BackgroundTasks, mailer: Mailer) -> None:
        self._background_tasks = background_tasks
        self._mailer = mailer

    def queue(self, message: EmailMessage) -> None:
        self._background_tasks.add_task(self._send, message)

    async def _send(self, message: EmailMessage) -> None:
        try:
            await self._mailer.send(message)
        except Exception as exc:
            logger.warning("email_send_failed", to=message.to, error=type(exc).__name__)


def get_outgoing_mail(request: Request, background_tasks: BackgroundTasks) -> BackgroundMail:
    return BackgroundMail(background_tasks, request.app.state.mailer)


OutgoingMailDep = Annotated[BackgroundMail, Depends(get_outgoing_mail)]
