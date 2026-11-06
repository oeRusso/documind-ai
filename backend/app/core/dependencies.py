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

    Stage 3 puts Cloudflare in front: the real IP will come in `CF-Connecting-IP`, and this is
    the one place to change. Until then, proxy headers are NOT trusted (anyone can forge them).
    """
    host = request.client.host if request.client else None
    if host is None:
        return None
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:  # e.g. "testclient"
        return None


ClientIpDep = Annotated[str | None, Depends(get_client_ip)]
