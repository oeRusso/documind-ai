"""FastAPI dependencies shared by every module's routers."""

import ipaddress
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.infrastructure.database.session import get_session

# scope="function": commit before the response is sent (see get_session).
SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def get_client_ip(request: Request) -> str | None:
    """IP of the client, for the audit log and rate limits.

    Behind Cloudflare (production) the TCP peer is Caddy, so the real IP comes in the header
    named by CLIENT_IP_HEADER ("CF-Connecting-IP"). Without that setting, proxy headers are NOT
    trusted (anyone can forge them) and the peer is used.
    """
    settings: Settings = request.app.state.settings
    candidates = []
    if settings.client_ip_header:
        candidates.append(request.headers.get(settings.client_ip_header))
    candidates.append(request.client.host if request.client else None)
    for value in candidates:
        if not value:
            continue
        try:
            return str(ipaddress.ip_address(value.strip()))
        except ValueError:  # e.g. "testclient", or a forged value
            continue
    return None


ClientIpDep = Annotated[str | None, Depends(get_client_ip)]
