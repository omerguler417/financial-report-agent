# Checks that GET /health returns HTTP 200 and {"ok": true}; needs no API key or network access.
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
