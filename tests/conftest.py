import copy
import os

import pytest
import redis


@pytest.fixture
def sensor_event():
    """A valid greenhouse schema v2 event."""
    return {
        "schema_version": 2,
        "event_id": "550e8400-e29b-41d4-a716-446655440000",
        "sensor_id": "bme280-001",
        "gateway_id": "pi-001",
        "timestamp": "2026-10-28T18:00:00Z",
        "measurement_type": "air_temperature",
        "value": 23.4,
        "unit": "celsius",
    }


@pytest.fixture
def valid_event(sensor_event):
    """Alias for ``sensor_event``, used by the schema and gateway tests."""
    return copy.deepcopy(sensor_event)


@pytest.fixture
def redis_client():
    """Isolated Redis database for integration tests."""
    url = os.getenv(
        "TEST_REDIS_URL",
        "redis://localhost:6379/15",
    )

    client = redis.Redis.from_url(
        url,
        decode_responses=True,
    )

    client.ping()
    client.flushdb()

    yield client

    client.flushdb()
    client.close()
