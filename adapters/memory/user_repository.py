"""In-memory implementation of UserRepository."""

from collections.abc import Sequence
from uuid import UUID, uuid4

from ports.auth import MAX_HANDLE_SUFFIX_ATTEMPTS, UserRecord


class InMemoryUserRepository:
    """Reference in-memory implementation for tests."""

    def __init__(self) -> None:
        self._by_id: dict[UUID, UserRecord] = {}
        self._by_external: dict[tuple[str, str], UUID] = {}
        self._by_handle_lower: dict[str, UUID] = {}   # cross-account uniqueness

    async def get_by_id(self, user_id: UUID) -> UserRecord | None:
        return self._by_id.get(user_id)

    async def get_by_external(self, provider: str, external_id: str) -> UserRecord | None:
        uid = self._by_external.get((provider, external_id))
        return self._by_id.get(uid) if uid else None

    async def ensure_user(
        self,
        user_id: UUID,
        external_id: str,
        provider: str,
        handle: str,
        email: str | None = None,
    ) -> UserRecord:
        key = (provider, external_id)
        if key in self._by_external:
            # This account already exists: its handle is never touched again;
            # its email refreshes to whatever the provider offers now.
            existing = self._by_id[self._by_external[key]]
            updated = UserRecord(
                user_id=existing.user_id,
                external_id=existing.external_id,
                provider=existing.provider,
                handle=existing.handle,
                email=email if email is not None else existing.email,
            )
            self._by_id[existing.user_id] = updated
            return updated

        # Brand-new account: claim `handle`, or the first free variant of it.
        candidates = [handle, *(f"{handle}{n}" for n in range(2, MAX_HANDLE_SUFFIX_ATTEMPTS))]
        attempt = next((c for c in candidates if c.lower() not in self._by_handle_lower), None)
        if attempt is None:
            attempt = f"{handle}-{uuid4().hex[:6]}"    # last resort, ~guaranteed free

        record = UserRecord(
            user_id=user_id, external_id=external_id, provider=provider,
            handle=attempt, email=email,
        )
        self._by_id[user_id] = record
        self._by_external[key] = user_id
        self._by_handle_lower[attempt.lower()] = user_id
        return record

    async def get_handles(self, user_ids: Sequence[UUID]) -> dict[UUID, str]:
        return {uid: self._by_id[uid].handle for uid in user_ids if uid in self._by_id}
