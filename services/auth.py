"""Authentication service.

Coordinates identity providers, user persistence, and session signing.
Adheres to:
- SRP: Authentication orchestration only; no HTTP or driver details.
- OCP: Pluggable OAuthProvider registry.
- DIP: Depends entirely on port protocols (UserRepository, OAuthProvider, SessionSigner).
"""

import secrets
from collections.abc import Sequence

from ports.auth import (
    OAuthProvider,
    SessionSigner,
    SessionToken,
    UserRepository,
    user_id_for,
)


class ProviderNotConfigured(LookupError):
    """Raised when an unknown or unconfigured OAuth provider is requested."""


class AuthService:
    """Application service for managing player authentication and sessions."""

    def __init__(
        self,
        user_repo: UserRepository,
        signer: SessionSigner,
        providers: Sequence[OAuthProvider] = (),
    ) -> None:
        self._user_repo = user_repo
        self._signer = signer
        self._providers: dict[str, OAuthProvider] = {p.name: p for p in providers}

    def register_provider(self, provider: OAuthProvider) -> None:
        self._providers[provider.name] = provider

    def is_provider_available(self, name: str) -> bool:
        return name in self._providers

    def start_oauth(self, provider_name: str, redirect_uri: str) -> tuple[str, str]:
        """Initiates an OAuth flow: returns (authorization_url, csrf_state)."""
        provider = self._providers.get(provider_name)
        if not provider:
            raise ProviderNotConfigured(f"OAuth provider '{provider_name}' is not configured")
        state = secrets.token_urlsafe(32)
        url = provider.get_authorization_url(state=state, redirect_uri=redirect_uri)
        return url, state

    async def complete_oauth(
        self,
        provider_name: str,
        code: str,
        redirect_uri: str,
        requested_handle: str | None = None,
    ) -> tuple[SessionToken, str]:
        """Completes code exchange, provisions user record, and mints a signed session."""
        provider = self._providers.get(provider_name)
        if not provider:
            raise ProviderNotConfigured(f"OAuth provider '{provider_name}' is not configured")

        identity = await provider.exchange_code(code=code, redirect_uri=redirect_uri)
        user_id = user_id_for(provider_name, identity.external_id)

        handle = (requested_handle or identity.default_handle).strip()[:32]
        if not handle:
            handle = f"player_{identity.external_id[:6]}"

        user_record = await self._user_repo.ensure_user(
            user_id=user_id,
            external_id=identity.external_id,
            provider=provider_name,
            handle=handle,
            email=identity.email,
        )

        session = SessionToken(
            user_id=user_record.user_id,
            handle=user_record.handle,
            provider=user_record.provider,
        )
        signed_cookie = self._signer.sign(session)
        return session, signed_cookie

    async def create_dev_session(self, handle: str) -> tuple[SessionToken, str]:
        """Creates an authenticated session for local dev and testing."""
        clean_handle = handle.strip()[:32]
        if not clean_handle:
            clean_handle = "guest"
        user_id = user_id_for("dev", clean_handle)

        user_record = await self._user_repo.ensure_user(
            user_id=user_id,
            external_id=clean_handle,
            provider="dev",
            handle=clean_handle,
        )
        session = SessionToken(
            user_id=user_record.user_id,
            handle=user_record.handle,
            provider="dev",
        )
        signed_cookie = self._signer.sign(session)
        return session, signed_cookie

    def verify_session(self, cookie_value: str | None) -> SessionToken | None:
        """Verifies a signed session cookie."""
        if not cookie_value:
            return None
        return self._signer.verify(cookie_value)
