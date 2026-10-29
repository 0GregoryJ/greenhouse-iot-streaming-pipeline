
import json
from unittest.mock import Mock

import pytest
import redis

from fastapi.testclient import TestClient

from api import main as api
from consumers.live import consumer as live


@pytest.fixture
def client(monkeypatch, redis_client):
    """Use isolated test Redis for all API calls."""

    monkeypatch.setattr(
        api,
        "redis_client",
        redis_client,
    )

    # Avoid entering the lifespan context here;
    # Redis availability is explicitly tested below.
    return TestClient(api.app)


def test_health_success(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok"
    }


def test_health_redis_unavailable(client, monkeypatch):
    broken_redis = Mock()

    broken_redis.ping.side_effect = (
        redis.ConnectionError("Connection refused")
    )

    monkeypatch.setattr(
        api,
        "redis_client",
        broken_redis,
    )

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Redis is unavailable"
    }


def test_latest_empty(client):
    response = client.get(
        "/api/v1/sensors/latest"
    )

    assert response.status_code == 200
    assert response.json() == {
        "count": 0,
        "readings": [],
    }


def test_latest_returns_real_redis_data(
    client,
    redis_client,
    sensor_event,
):
    # Use the real consumer writer to seed Redis.
    event, timestamp_ms = live.parse_event(
        json.dumps(sensor_event)
    )

    key, updated = live.write_latest(
        redis_client,
        event,
        timestamp_ms,
    )

    assert updated is True
    assert redis_client.exists(key) == 1

    response = client.get(
        "/api/v1/sensors/latest"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["count"] == 1
    assert body["readings"] == [
        {
            "gateway_id": "pi-001",
            "sensor_id": "bme280-001",
            "measurement_type": "air_temperature",
            "value": 23.4,
            "unit": "celsius",
            "timestamp": "2026-10-28T18:00:00Z",
            "event_id": sensor_event["event_id"],
        }
    ]


def test_latest_returns_sorted_readings(
    client,
    redis_client,
    sensor_event,
):
    for measurement_type, value, unit in [
        ("relative_humidity", 55.0, "percent"),
        ("air_temperature", 23.4, "celsius"),
        ("atmospheric_pressure", 1013.2, "hpa"),
    ]:
        event = dict(sensor_event)
        event["measurement_type"] = measurement_type
        event["value"] = value
        event["unit"] = unit

        parsed, timestamp_ms = live.parse_event(
            json.dumps(event)
        )
        live.write_latest(
            redis_client,
            parsed,
            timestamp_ms,
        )

    response = client.get(
        "/api/v1/sensors/latest"
    )

    assert response.status_code == 200

    body = response.json()
    assert body["count"] == 3

    measurement_types = [
        item["measurement_type"]
        for item in body["readings"]
    ]

    assert measurement_types == [
        "air_temperature",
        "atmospheric_pressure",
        "relative_humidity",
    ]


def test_latest_redis_unavailable(
    client, monkeypatch
):
    broken_redis = Mock()

    broken_redis.scan.side_effect = (
        redis.ConnectionError("Connection refused")
    )

    monkeypatch.setattr(
        api,
        "redis_client",
        broken_redis,
    )

    response = client.get(
        "/api/v1/sensors/latest"
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": (
            "Sensor readings are temporarily unavailable"
        )
    }


def test_latest_invalid_stored_value(
    client, redis_client
):
    # Redis has an existing key, but its numeric
    # measurement value has become corrupted.
    redis_client.hset(
        "greenhouse:latest:pi-001:soil-001:soil_moisture",
        mapping={
            "gateway_id": "pi-001",
            "sensor_id": "soil-001",
            "measurement_type": "soil_moisture",
            "value": "not-a-number",
            "unit": "raw_capacitance",
            "timestamp": "2026-10-28T18:00:00Z",
            "event_id": "test-event",
        },
    )

    response = client.get(
        "/api/v1/sensors/latest"
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Sensor readings are temporarily unavailable"
    )
