"""Authentication and identity contracts.

Follows SOLID principles:
- SRP: Distinct protocols for OAuth provider interaction, session signing, and persistence.
- OCP: Adding a new OAuth provider (e.g. Apple) only requires a new OAuthProvider implementation.
- LSP: Any OAuthProvider, SessionSigner, or UserRepository substitute adheres to these contracts.

- ISP: Protocols are minimal and purpose-bound.
- DIP: Higher-level layers (services, API) depend on these abstractions, not third-party SDKs.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID, uuid5

#: Namespace for deriving stable user ids from a provider subject.
USER_NAMESPACE = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

#: Friendly numeric variants tried (handle2, handle3, ...) before a brand-new
#: account falls back to a random suffix to claim a free handle (ensure_user).
MAX_HANDLE_SUFFIX_ATTEMPTS = 25


def user_id_for(provider: str, external_id: str) -> UUID:
    """Derives a deterministic, RFC 4122 v5 UUID for a provider subject."""
    return uuid5(USER_NAMESPACE, f"{provider}:{external_id}")



@dataclass(frozen=True, slots=True)
class AuthIdentity:
    """Identity verified by an external authentication provider."""

    provider: str
    external_id: str
    email: str | None = None
    name: str | None = None
    picture: str | None = None

    @property
    def default_handle(self) -> str:
        """Derives a clean, alphanumeric default handle from name or email."""
        if self.name:
            cleaned = "".join(c for c in self.name if c.isalnum() or c in ("-", "_")).strip()
            if cleaned:
                return cleaned[:32]
        if self.email:
            prefix = self.email.split("@")[0]
            cleaned = "".join(c for c in prefix if c.isalnum() or c in ("-", "_")).strip()
            if cleaned:
                return cleaned[:32]
        return self.external_id[:32]


@dataclass(frozen=True, slots=True)
class SessionToken:
    """Contents of a validated authenticated session."""

    user_id: UUID
    handle: str
    provider: str


@dataclass(frozen=True, slots=True)
class UserRecord:
    """User row as stored in the database."""

    user_id: UUID
    external_id: str
    provider: str
    handle: str
    email: str | None = None


@runtime_checkable
class OAuthProvider(Protocol):
    """Contract for an OAuth2 / OpenID Connect identity provider."""

    @property
    def name(self) -> str:
        """Provider identifier, e.g. 'google' or 'apple'."""
        ...

    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """Returns the authorization URL to redirect the player's browser to."""
        ...

    async def exchange_code(self, code: str, redirect_uri: str) -> AuthIdentity:
        """Exchanges an authorization code for verified identity information."""
        ...


@runtime_checkable
class SessionSigner(Protocol):
    """Contract for cryptographically signing and verifying session cookies."""

    def sign(self, session: SessionToken) -> str:
        """Serialises and cryptographically signs a session token into a cookie string."""
        ...

    def verify(self, cookie_value: str, max_age: int | None = None) -> SessionToken | None:
        """Verifies and decodes a cookie string. Returns None if invalid or expired."""
        ...


@runtime_checkable
class UserRepository(Protocol):
    """Contract for user persistence and profile queries."""

    async def get_by_id(self, user_id: UUID) -> UserRecord | None:
        """Looks up a user by canonical UUID."""
        ...

    async def get_by_external(self, provider: str, external_id: str) -> UserRecord | None:
        """Looks up a user by external provider subject."""
        ...

    async def ensure_user(
        self,
        user_id: UUID,
        external_id: str,
        provider: str,
        handle: str,
        email: str | None = None,
    ) -> UserRecord:
        """Idempotently records a user.

        An existing account (same provider + external_id) keeps its handle
        forever — a repeat login never renames anyone — and refreshes its
        email to the latest non-null value offered. A brand-new account
        claims `handle` outright, or the first free case-insensitive variant
        of it (up to MAX_HANDLE_SUFFIX_ATTEMPTS, then a random one): handles
        are shown as if each identifies exactly one player, so two accounts
        must never end up sharing one.
        """
        ...

    async def get_handles(self, user_ids: Sequence[UUID]) -> dict[UUID, str]:
        """Bulk-fetches display handles for a collection of user IDs."""
        ...
