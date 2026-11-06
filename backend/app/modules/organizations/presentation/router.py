"""HTTP endpoints for organizations.

The stage 1 endpoints (create and get, without authentication) were removed when Row Level
Security arrived: without a user there is no tenant context, so they could not work safely.
They come back behind authentication in stage 2, step 14.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/organizations", tags=["organizations"])
