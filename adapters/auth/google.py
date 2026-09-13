"""Google OAuth 2.0 / OpenID Connect adapter."""

import urllib.parse
from typing import Any

import httpx

from ports.auth import AuthIdentity


class GoogleAuthError(RuntimeError):
    """Raised when communication with Google OAuth endpoints fails."""


class GoogleOAuthProvider:
    """Satisfies OAuthProvider for Google."""

    AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
    USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not client_id or not client_secret:
            raise ValueError("client_id and client_secret are required for GoogleOAuthProvider")
        self._client_id = client_id
        self._client_secret = client_secret
        self._http_client = http_client

    @property
    def name(self) -> str:
        return "google"

    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
        return f"{self.AUTHORIZATION_ENDPOINT}?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> AuthIdentity:
        payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }

        async def _do_exchange(client: httpx.AsyncClient) -> dict[str, Any]:
            token_resp = await client.post(
                self.TOKEN_ENDPOINT,
                data=payload,
                headers={"Accept": "application/json"},
                timeout=10.0,
            )
            if token_resp.status_code != 200:
                raise GoogleAuthError(
                    f"Google token exchange failed ({token_resp.status_code}): {token_resp.text}"
                )
            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            if not access_token:
                raise GoogleAuthError("No access_token returned by Google")

            userinfo_resp = await client.get(
                self.USERINFO_ENDPOINT,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10.0,
            )
            if userinfo_resp.status_code != 200:
                raise GoogleAuthError(
                    f"Failed to fetch userinfo from Google ({userinfo_resp.status_code})"
                )
            return userinfo_resp.json()

        if self._http_client:
            userinfo = await _do_exchange(self._http_client)
        else:
            async with httpx.AsyncClient() as client:
                userinfo = await _do_exchange(client)

        sub = userinfo.get("sub")
        if not sub:
            raise GoogleAuthError("Google userinfo missing 'sub' subject claim")

        return AuthIdentity(
            provider=self.name,
            external_id=str(sub),
            email=userinfo.get("email"),
            name=userinfo.get("name"),
            picture=userinfo.get("picture"),
        )
