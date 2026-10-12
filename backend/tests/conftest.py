"""
Test setup: a throwaway SQLite database, no background scheduler, and no
calls to real AI, speech, payment or telephony services.
Run from backend/:  venv/Scripts/python -m pytest -q
"""
import os
import sys
import tempfile
import uuid

import pytest

_DB = os.path.join(tempfile.mkdtemp(prefix="nimmi-test-"), "test.db")
os.environ.update({
    "SQLITE_PATH": _DB, "LOCAL_DEV": "true", "DISABLE_SCHEDULER": "true", "JWT_SECRET": "test-secret",
    "RAZORPAY_KEY_ID": "rzp_test_x", "RAZORPAY_KEY_SECRET": "test_secret", "RAZORPAY_WEBHOOK_SECRET": "hook_secret",
    "EXOTEL_WS_SECRET": "exo-secret", "ADMIN_API_KEY": "admin-key",
    "TWILIO_ACCOUNT_SID": "ACtest", "TWILIO_AUTH_TOKEN": "tw-token", "TWILIO_WS_SECRET": "tw-secret",
    "PUBLIC_BACKEND_URL": "https://example.test",
    "GROQ_API_KEY": "", "SUPABASE_SERVICE_ROLE_KEY": "",
    "RESEND_API_KEY": "", "SMTP_HOST": "", "SARVAM_API_KEY": "",
})

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def run(client):
    """Run a coroutine on the app's own event loop (shares the DB engine safely)."""
    def _run(coro_fn, *args, **kwargs):
        return client.portal.call(lambda: coro_fn(*args, **kwargs))
    return _run


class User:
    def __init__(self, client, name="Test User"):
        import auth
        auth._hits.clear()  # every test user signs up from the same address
        self.email = f"{uuid.uuid4().hex[:10]}@example.com"
        resp = client.post("/api/auth/signup", json={"email": self.email, "name": name, "password": "password123"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        self.id, self.token = data["user_id"], data["token"]
        self.client = client

    def h(self, workspace=None):
        headers = {"Authorization": f"Bearer {self.token}"}
        if workspace:
            headers["X-Workspace"] = workspace
        return headers

    def bot(self, name="Desk"):
        resp = self.client.post("/api/bots/create", json={"name": name}, headers=self.h())
        assert resp.status_code == 200, resp.text
        return resp.json()["id"]


@pytest.fixture
def make_user(client):
    return lambda name="Test User": User(client, name)
