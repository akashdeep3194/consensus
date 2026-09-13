"""Tests for authentication ports, adapters, and service."""

from uuid import uuid4

import httpx
import pytest

from adapters.auth.google import GoogleOAuthProvider
from adapters.auth.signer import ItsDangerousSessionSigner
from adapters.memory.user_repository import InMemoryUserRepository
from ports.auth import SessionToken, user_id_for
from services.auth import AuthService, ProviderNotConfigured
from tests.conftest import run  # one shared event loop, matching test_port_conformance.py

# ── UserRepository conformance ───────────────────────────────────────────────
# Both adapters must agree on more than method names: the earlier version of
# this pair disagreed on which side wins when ensure_user is called again with
# a new email (Postgres took the new one, memory kept the old) — exactly the
# kind of divergence a parametrized suite exists to catch.


@pytest.fixture(params=["memory", "postgres"])
def user_repo(request):
    if request.param == "memory":
        return InMemoryUserRepository()

    pool = request.getfixturevalue("pg_pool")
    from adapters.postgres import PostgresUserRepository

    run(pool.execute("TRUNCATE users CASCADE"))
    return PostgresUserRepository(pool)


def test_ensure_user_never_renames_on_repeat_login(user_repo):
    uid = uuid4()
    run(user_repo.ensure_user(uid, "sub-1", "google", handle="akash", email="a@x.com"))
    again = run(
        user_repo.ensure_user(uid, "sub-1", "google", handle="totally-different", email="a@x.com")
    )
    assert again.handle == "akash", "a repeat login must never rename an existing account"


def test_ensure_user_refreshes_email_to_the_latest_value(user_repo):
    uid = uuid4()
    run(user_repo.ensure_user(uid, "sub-2", "google", handle="akash", email="old@x.com"))
    again = run(user_repo.ensure_user(uid, "sub-2", "google", handle="akash", email="new@x.com"))
    assert again.email == "new@x.com", "the provider's latest email must win on repeat login"

    kept = run(user_repo.ensure_user(uid, "sub-2", "google", handle="akash", email=None))
    assert kept.email == "new@x.com", "a login with no email offered must not blank out the old one"


def test_ensure_user_avoids_handle_collision_across_accounts(user_repo):
    first = run(user_repo.ensure_user(uuid4(), "sub-a", "google", handle="akash"))
    second = run(user_repo.ensure_user(uuid4(), "sub-b", "google", handle="akash"))
    third = run(user_repo.ensure_user(uuid4(), "sub-c", "google", handle="AKASH"))

    handles = {first.handle.lower(), second.handle.lower(), third.handle.lower()}
    assert len(handles) == 3, "three different accounts must never end up sharing a handle"
    assert first.handle == "akash", "the first account to claim a handle keeps it exactly"


def test_get_handles_bulk_fetch(user_repo):
    a = run(user_repo.ensure_user(uuid4(), "sub-x", "google", handle="alice"))
    b = run(user_repo.ensure_user(uuid4(), "sub-y", "google", handle="bob"))
    handles = run(user_repo.get_handles([a.user_id, b.user_id]))
    assert handles == {a.user_id: "alice", b.user_id: "bob"}


def test_session_signer_round_trip():
    signer = ItsDangerousSessionSigner(secret_key="test-secret-key", default_max_age=3600)
    uid = uuid4()
    session = SessionToken(user_id=uid, handle="akash", provider="google")

    cookie = signer.sign(session)
    assert isinstance(cookie, str)
    assert cookie != ""

    recovered = signer.verify(cookie)
    assert recovered is not None
    assert recovered.user_id == uid
    assert recovered.handle == "akash"
    assert recovered.provider == "google"


def test_session_signer_rejects_tampering():
    signer = ItsDangerousSessionSigner(secret_key="test-secret-key")
    session = SessionToken(user_id=uuid4(), handle="alice", provider="dev")
    cookie = signer.sign(session)

    # Tamper with the cookie string
    tampered = cookie[:-4] + "xxxx"
    assert signer.verify(tampered) is None
    assert signer.verify("") is None
    assert signer.verify("garbage.not.a.valid.token") is None


def test_session_signer_respects_expiration():
    signer = ItsDangerousSessionSigner(secret_key="test-secret-key")
    session = SessionToken(user_id=uuid4(), handle="alice", provider="dev")
    cookie = signer.sign(session)

    # max_age = -1 forces expiration
    assert signer.verify(cookie, max_age=-1) is None


@pytest.mark.asyncio
async def test_user_repository_ensure_and_fetch():
    repo = InMemoryUserRepository()
    uid = uuid4()

    created = await repo.ensure_user(
        user_id=uid,
        external_id="10928374",
        provider="google",
        handle="akash",
        email="akash@example.com",
    )
    assert created.user_id == uid
    assert created.handle == "akash"
    assert created.email == "akash@example.com"

    by_id = await repo.get_by_id(uid)
    assert by_id == created

    by_ext = await repo.get_by_external("google", "10928374")
    assert by_ext == created

    # Calling ensure_user again preserves handle
    updated = await repo.ensure_user(
        user_id=uid,
        external_id="10928374",
        provider="google",
        handle="new_handle",
        email="akash@example.com",
    )
    assert updated.handle == "akash"

    handles = await repo.get_handles([uid])
    assert handles == {uid: "akash"}


def test_google_auth_url_construction():
    provider = GoogleOAuthProvider(client_id="dummy-client-id", client_secret="dummy-secret")
    url = provider.get_authorization_url(state="xyz123", redirect_uri="http://localhost:8099/callback")

    assert "https://accounts.google.com/o/oauth2/v2/auth?" in url
    assert "client_id=dummy-client-id" in url
    assert "state=xyz123" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8099%2Fcallback" in url
    assert "scope=openid+email+profile" in url or "scope=openid%20email%20profile" in url


@pytest.mark.asyncio
async def test_auth_service_full_oauth_flow():
    # Mock transport for Google OAuth HTTP calls
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == GoogleOAuthProvider.TOKEN_ENDPOINT:
            return httpx.Response(200, json={"access_token": "mock-token", "id_token": "mock-id"})
        if str(request.url) == GoogleOAuthProvider.USERINFO_ENDPOINT:
            return httpx.Response(
                200,
                json={
                    "sub": "google-user-12345",
                    "email": "player@example.com",
                    "name": "Super Player",
                },
            )
        return httpx.Response(404)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    google_provider = GoogleOAuthProvider(
        client_id="cid",
        client_secret="csecret",
        http_client=mock_client,
    )

    user_repo = InMemoryUserRepository()
    signer = ItsDangerousSessionSigner(secret_key="secret-key")
    auth_service = AuthService(user_repo=user_repo, signer=signer, providers=[google_provider])

    # 1. Start OAuth
    url, state = auth_service.start_oauth("google", "http://localhost:8099/callback")
    assert state
    assert "cid" in url

    # 2. Complete OAuth
    session, cookie = await auth_service.complete_oauth(
        provider_name="google",
        code="mock-code",
        redirect_uri="http://localhost:8099/callback",
    )
    assert session.provider == "google"
    assert session.handle == "SuperPlayer"
    expected_uid = user_id_for("google", "google-user-12345")
    assert session.user_id == expected_uid

    # 3. Verify session cookie
    verified = auth_service.verify_session(cookie)
    assert verified == session


@pytest.mark.asyncio
async def test_auth_service_dev_session():
    user_repo = InMemoryUserRepository()
    signer = ItsDangerousSessionSigner(secret_key="secret-key")
    auth_service = AuthService(user_repo=user_repo, signer=signer)

    session, cookie = await auth_service.create_dev_session(handle="alice")
    assert session.handle == "alice"
    assert session.provider == "dev"
    assert session.user_id == user_id_for("dev", "alice")

    verified = auth_service.verify_session(cookie)
    assert verified == session


def test_auth_service_unconfigured_provider():
    auth_service = AuthService(
        user_repo=InMemoryUserRepository(),
        signer=ItsDangerousSessionSigner(secret_key="secret"),
    )
    with pytest.raises(ProviderNotConfigured):
        auth_service.start_oauth("unsupported", "http://localhost/callback")


def test_api_auth_routes():
    from unittest.mock import MagicMock

    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    from api.auth import get_current_user_resolver, register_auth_routes

    app = FastAPI()
    mock_container = MagicMock()
    user_repo = InMemoryUserRepository()
    signer = ItsDangerousSessionSigner(secret_key="api-test-secret")
    mock_provider = GoogleOAuthProvider(client_id="cid", client_secret="csec")
    auth_service = AuthService(user_repo=user_repo, signer=signer, providers=[mock_provider])
    mock_container.auth = auth_service
    mock_container.users = user_repo
    mock_container.dev_login_enabled = True   # this test exercises dev sign-in

    register_auth_routes(app, lambda: mock_container)
    current_user = get_current_user_resolver(lambda: mock_container)

    @app.get("/protected")
    async def protected(uid=Depends(current_user)):  # noqa: B008
        return {"uid": str(uid)}


    client = TestClient(app)

    # 1. /api/me when logged out
    me_resp = client.get("/api/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["handle"] is None

    # 2. protected when logged out -> 401
    assert client.get("/protected").status_code == 401

    # 3. /api/session (dev sign in)
    signin_resp = client.post("/api/session", json={"handle": "testuser"})
    assert signin_resp.status_code == 200
    assert signin_resp.json()["handle"] == "testuser"
    assert "cx_session" in signin_resp.cookies

    # 4. /api/me when logged in with session cookie
    me_resp = client.get("/api/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["handle"] == "testuser"

    # 5. protected when logged in -> 200
    prot_resp = client.get("/protected")
    assert prot_resp.status_code == 200
    assert prot_resp.json()["uid"] == str(user_id_for("dev", "testuser"))

    # 6. /api/auth/google/login initiates redirect
    login_resp = client.get("/api/auth/google/login", follow_redirects=False)
    assert login_resp.status_code == 303
    assert "accounts.google.com" in login_resp.headers["location"]
    assert "cx_oauth_state" in login_resp.cookies

    # 7. /api/auth/google/callback requires matching state
    bad_cb = client.get("/api/auth/google/callback?code=abc&state=bad")
    assert bad_cb.status_code == 400

    # 8. /api/session delete clears cookies
    signout_resp = client.delete("/api/session")
    assert signout_resp.status_code == 200

