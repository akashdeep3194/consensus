"""Authentication API endpoints.

Handles OAuth 2.0 redirection, callback validation, session minting, and dev
session compatibility. Every security-relevant flag it reads (whether dev
login is reachable at all, whether cookies require HTTPS) comes from the
container, resolved once at startup in api.deps — this module never reads an
environment variable for anything that decides who gets in.
"""

import logging
from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from api.deps import Container
from ports.auth import SessionToken

log = logging.getLogger("consensus.auth")
router = APIRouter()

#: How long a session cookie is trusted for, independent of the signature's
#: own embedded timestamp check (ItsDangerousSessionSigner.default_max_age).
SESSION_COOKIE_MAX_AGE = 86400 * 30
OAUTH_STATE_COOKIE_MAX_AGE = 600


class DevSignIn(BaseModel):
    handle: str = Field(min_length=1, max_length=32)


def _get_google_redirect_uri(request: Request) -> str:
    import os

    explicit = os.environ.get("GOOGLE_REDIRECT_URI")
    if explicit:
        return explicit
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.netloc)
    return f"{scheme}://{host}/api/auth/google/callback"


def get_current_user_resolver(get_container: Callable[[], Container]):
    """Factory creating the `current_user` FastAPI dependency.

    The only source of identity is a validly signed `cx_session` cookie —
    there is no secondary, unsigned fallback. Dev sign-in mints the same kind
    of signed cookie through the same signer (see create_dev_session below),
    so it needs no special case here at all.
    """

    async def current_user(cx_session: str | None = Cookie(None)) -> UUID:
        session = get_container().auth.verify_session(cx_session)
        if session is None:
            raise HTTPException(401, "sign in first")
        return session.user_id

    return current_user


def register_auth_routes(app_router: APIRouter, get_container: Callable[[], Container]) -> None:
    """Registers authentication endpoints onto the router."""

    def _set_session_cookie(response, signed_cookie: str, *, max_age: int) -> None:
        c = get_container()
        response.set_cookie(
            "cx_session",
            signed_cookie,
            httponly=True,
            samesite="lax",
            secure=not c.dev_login_enabled,
            max_age=max_age,
        )

    @app_router.get("/api/auth/google/login")
    async def google_login(request: Request):
        c = get_container()
        if not c.auth.is_provider_available("google"):
            raise HTTPException(
                501,
                "Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
            )

        redirect_uri = _get_google_redirect_uri(request)
        try:
            auth_url, state = c.auth.start_oauth("google", redirect_uri)
        except Exception:
            log.exception("failed to start Google OAuth")
            raise HTTPException(500, "Failed to initiate Google authentication") from None

        response = RedirectResponse(auth_url, status_code=303)
        response.set_cookie(
            "cx_oauth_state", state, httponly=True, samesite="lax",
            secure=not c.dev_login_enabled, max_age=OAUTH_STATE_COOKIE_MAX_AGE,
        )
        return response

    @app_router.get("/api/auth/google/callback")
    async def google_callback(
        request: Request,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
        cx_oauth_state: str | None = Cookie(None),
    ):
        if error:
            log.warning("Google returned an OAuth error: %s", error)
            raise HTTPException(400, "Google sign-in was cancelled or denied")

        if not code or not state:
            raise HTTPException(400, "missing authorization code or state parameter")

        if not cx_oauth_state or cx_oauth_state != state:
            log.warning("OAuth state mismatch: cookie=%s, param=%s", cx_oauth_state, state)
            raise HTTPException(400, "invalid OAuth state (CSRF protection)")

        c = get_container()
        redirect_uri = _get_google_redirect_uri(request)

        try:
            _session, signed_cookie = await c.auth.complete_oauth("google", code, redirect_uri)
        except Exception:
            # The detail (token endpoint response, provider error text) is
            # never the client's business — it can carry the auth code, tokens
            # or raw provider internals. Only the log gets it.
            log.exception("Google OAuth token exchange failed")
            raise HTTPException(401, "Google authentication failed") from None

        response = RedirectResponse("/", status_code=303)
        response.delete_cookie("cx_oauth_state")
        _set_session_cookie(response, signed_cookie, max_age=SESSION_COOKIE_MAX_AGE)
        return response

    @app_router.get("/api/me")
    async def me(cx_session: str | None = Cookie(None)):
        c = get_container()
        session: SessionToken | None = c.auth.verify_session(cx_session)

        base = {
            "dev_enabled": c.dev_login_enabled,
            "google_enabled": c.auth.is_provider_available("google"),
        }
        if session is None:
            return {"handle": None, "user_id": None, "provider": None, **base}
        return {
            "handle": session.handle,
            "user_id": str(session.user_id),
            "provider": session.provider,
            **base,
        }

    @app_router.post("/api/session")
    async def dev_sign_in(response: Response, body: DevSignIn):
        c = get_container()
        if not c.dev_login_enabled:
            raise HTTPException(403, "dev login is disabled — use Google sign-in")

        session, signed_cookie = await c.auth.create_dev_session(body.handle)
        _set_session_cookie(response, signed_cookie, max_age=SESSION_COOKIE_MAX_AGE)
        return {"handle": session.handle, "user_id": str(session.user_id)}

    @app_router.delete("/api/session")
    async def sign_out(response: Response):
        response.delete_cookie("cx_session")
        response.delete_cookie("cx_oauth_state")
        return {"ok": True}

    @app_router.get("/dev/login")
    async def dev_login(handle: str):
        """One-click sign-in for local demos and automated runs."""
        c = get_container()
        if not c.dev_login_enabled:
            raise HTTPException(404, "not found")

        session, signed_cookie = await c.auth.create_dev_session(handle)
        res = RedirectResponse("/", status_code=303)
        _set_session_cookie(res, signed_cookie, max_age=86400)
        return res
