import pytest
from app import deps
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Vide les limiteurs entre tests : l'IP TestClient est partagée, sinon les
    tentatives s'accumulent d'un test à l'autre."""
    from app.ratelimit import reset_all_limiters
    reset_all_limiters()
    yield
    reset_all_limiters()


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient avec une DB SQLite temporaire isolée par test."""
    monkeypatch.setenv("BENJI_DB_PATH", str(tmp_path / "test.db"))
    deps._default_db.cache_clear()
    yield TestClient(app)
    deps._default_db.cache_clear()


def _register_login(client, email, password="pw"):
    client.post("/v1/auth/register", json={"email": email, "password": password})
    r = client.post("/v1/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


@pytest.fixture
def token(client):
    return _register_login(client, "free@b.c")


@pytest.fixture
def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def pro_token(client):
    tok = _register_login(client, "pro@b.c")
    db = deps.get_db()
    db.set_plan(db.get_user_by_email("pro@b.c")["id"], "pro")
    return tok


@pytest.fixture
def pro_auth(pro_token):
    return {"Authorization": f"Bearer {pro_token}"}
