import hmac
import os
from typing import Annotated

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

TOKEN_ENV = "BILINOTE_AGENT_TOKEN"
bearer_scheme = HTTPBearer(auto_error=False)


def validate_agent_authorization(authorization: str | None) -> None:
    expected = os.getenv(TOKEN_ENV, "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Agent API is disabled; configure {TOKEN_ENV}",
        )

    scheme, separator, supplied = (authorization or "").partition(" ")
    if (
        separator != " "
        or scheme.lower() != "bearer"
        or not hmac.compare_digest(supplied, expected)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_agent_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(bearer_scheme),
    ] = None,
) -> None:
    authorization = None
    if credentials is not None:
        authorization = f"{credentials.scheme} {credentials.credentials}"
    validate_agent_authorization(authorization)


class AgentTokenMiddleware:
    """Small ASGI auth boundary that does not buffer MCP streaming responses."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        try:
            validate_agent_authorization(headers.get("authorization"))
        except HTTPException as exc:
            import json

            body = json.dumps({"detail": exc.detail}).encode("utf-8")
            response_headers = [(b"content-type", b"application/json")]
            if exc.headers:
                response_headers.extend(
                    (key.encode("latin-1"), value.encode("latin-1"))
                    for key, value in exc.headers.items()
                )
            await send(
                {
                    "type": "http.response.start",
                    "status": exc.status_code,
                    "headers": response_headers,
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)
