"""The attempt limits of each endpoint, as FastAPI dependencies.

Limits by IP live here (an HTTP concern). The limit by email on login lives in the Login use
case, because only it knows the normalized email.
"""

from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings
from app.core.dependencies import ClientIpDep, SettingsDep
from app.shared.rate_limit import RateLimit, RateLimiter


def get_rate_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter


RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]


def login_per_email(settings: Settings) -> RateLimit:
    return RateLimit(settings.login_limit_per_email_per_15_minutes, timedelta(minutes=15))


def accept_invitation_per_user(settings: Settings) -> RateLimit:
    return RateLimit(settings.accept_invitation_limit_per_user_per_minute, timedelta(minutes=1))


def _ip_key(ip: str | None) -> str:
    # Unknown IP: everyone without one shares a bucket (stricter, never looser).
    return ip or "unknown"


async def limit_login_by_ip(
    limiter: RateLimiterDep, settings: SettingsDep, ip: ClientIpDep
) -> None:
    rule = RateLimit(settings.login_limit_per_ip_per_minute, timedelta(minutes=1))
    await limiter.hit(f"login:ip:{_ip_key(ip)}", rule)


async def limit_register_by_ip(
    limiter: RateLimiterDep, settings: SettingsDep, ip: ClientIpDep
) -> None:
    rule = RateLimit(settings.register_limit_per_ip_per_hour, timedelta(hours=1))
    await limiter.hit(f"register:ip:{_ip_key(ip)}", rule)
