import pytest
from fastapi.testclient import TestClient

from api import main as api


@pytest.fixture
def client(monkeypatch, redis_client):
    """Use isolated test Redis for all API calls."""

    monkeypatch.setattr(
        api,
        "redis_client",
        redis_client,
    )

    return TestClient(api.app)
