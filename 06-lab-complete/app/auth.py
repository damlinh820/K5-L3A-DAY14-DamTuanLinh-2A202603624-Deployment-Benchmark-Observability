"""API key authentication for the agent endpoint."""

import hmac

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import settings


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(key: str | None = Security(api_key_header)) -> str:
    if not key or not settings.agent_api_key or not hmac.compare_digest(key, settings.agent_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return key
