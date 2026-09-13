"""Session signer implementation using itsdangerous."""

from uuid import UUID

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from ports.auth import SessionToken


class ItsDangerousSessionSigner:
    """Satisfies SessionSigner: cryptographically signs and verifies session cookies.

    Tampering with the cookie invalidates the signature. Sessions expire
    after `default_max_age` seconds unless overridden during verification.
    """

    def __init__(
        self,
        secret_key: str,
        salt: str = "consensus-session",
        default_max_age: int = 86400 * 30,
    ) -> None:
        if not secret_key:
            raise ValueError("secret_key cannot be empty")
        self._serializer = URLSafeTimedSerializer(secret_key, salt=salt)
        self._default_max_age = default_max_age

    def sign(self, session: SessionToken) -> str:
        payload = {
            "uid": str(session.user_id),
            "handle": session.handle,
            "provider": session.provider,
        }
        return self._serializer.dumps(payload)

    def verify(self, cookie_value: str, max_age: int | None = None) -> SessionToken | None:
        if not cookie_value:
            return None
        max_age_to_use = max_age if max_age is not None else self._default_max_age
        try:
            data = self._serializer.loads(cookie_value, max_age=max_age_to_use)
            if not isinstance(data, dict):
                return None
            return SessionToken(
                user_id=UUID(data["uid"]),
                handle=str(data["handle"]),
                provider=str(data["provider"]),
            )
        except (BadSignature, SignatureExpired, KeyError, ValueError):
            return None
