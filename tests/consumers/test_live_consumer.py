
import copy
import json
from unittest.mock import Mock

import pytest
import redis

from consumers.live import consumer as live


# ----------------------------------
# 1. Event parsing
# ----------------------------------

def test_parse_valid_event(sensor_event):
    raw = json.dumps(sensor_event).encode("utf-8")

    event, timestamp_ms = live.parse_event(raw)

    assert event == sensor_event
    assert timestamp_ms == 1793210400000


def test_parse_v1_event(sensor_event):
    event = copy.deepcopy(sensor_event)
    event["schema_version"] = 1

    parsed, timestamp_ms = live.parse_event(
        json.dumps(event).encode("utf-8")
    )

    assert parsed == event
    assert isinstance(timestamp_ms, int)


def test_parse_invalid_json():
    with pytest.raises(json.JSONDecodeError):
        live.parse_event(b"{invalid-json")


def test_parse_missing_field(sensor_event):
    del sensor_event["sensor_id"]

    with pytest.raises(
        ValueError,
        match="Missing required field: sensor_id",
    ):
        live.parse_event(json.dumps(sensor_event))


def test_parse_non_numeric_value(sensor_event):
    sensor_event["value"] = "23.4"

    with pytest.raises(
        ValueError,
        match="Measurement value must be numeric",
    ):
        live.parse_event(json.dumps(sensor_event))


def test_parse_naive_timestamp(sensor_event):
    sensor_event["timestamp"] = "2026-10-28T18:00:00"

    with pytest.raises(
        ValueError,
        match="Timestamp must include a timezone",
    ):
        live.parse_event(json.dumps(sensor_event))


def test_parse_timezone_offset(sensor_event):
    sensor_event["timestamp"] = (
        "2026-10-28T11:00:00-07:00"
    )

    _, timestamp_ms = live.parse_event(
        json.dumps(sensor_event)
    )

    assert timestamp_ms == 1793210400000


# ----------------------------------
# 2. Redis Lua timestamp guard
# ----------------------------------

def test_new_event_is_stored(redis_client, sensor_event):
    event, timestamp_ms = live.parse_event(
        json.dumps(sensor_event)
    )

    key, updated = live.write_latest(
        redis_client, event, timestamp_ms
    )

    record = redis_client.hgetall(key)

    assert updated is True

    assert key == (
        "greenhouse:latest:"
        "pi-001:bme280-001:air_temperature"
    )

    assert record["value"] == "23.4"
    assert record["unit"] == "celsius"
    assert record["event_id"] == sensor_event["event_id"]
    assert record["timestamp"] == sensor_event["timestamp"]
    assert int(record["timestamp_ms"]) == timestamp_ms


def test_newer_event_overwrites_older(
    redis_client, sensor_event
):
    first = copy.deepcopy(sensor_event)

    second = copy.deepcopy(sensor_event)
    second["event_id"] = (
        "550e8400-e29b-41d4-a716-446655440001"
    )
    second["timestamp"] = "2026-10-28T18:00:05Z"
    second["value"] = 25.0

    for event in (first, second):
        parsed, timestamp_ms = live.parse_event(
            json.dumps(event)
        )
        key, updated = live.write_latest(
            redis_client, parsed, timestamp_ms
        )
        assert updated is True

    record = redis_client.hgetall(key)

    assert record["value"] == "25.0"
    assert record["event_id"] == second["event_id"]


def test_older_event_cannot_overwrite_newer(
    redis_client, sensor_event
):
    newer = copy.deepcopy(sensor_event)
    newer["timestamp"] = "2026-10-28T18:00:10Z"
    newer["value"] = 25.0

    older = copy.deepcopy(sensor_event)
    older["timestamp"] = "2026-10-28T18:00:05Z"
    older["value"] = 20.0
    older["event_id"] = (
        "550e8400-e29b-41d4-a716-446655440002"
    )

    parsed_new, ms_new = live.parse_event(
        json.dumps(newer)
    )
    key, updated = live.write_latest(
        redis_client, parsed_new, ms_new
    )
    assert updated is True

    parsed_old, ms_old = live.parse_event(
        json.dumps(older)
    )
    _, updated = live.write_latest(
        redis_client, parsed_old, ms_old
    )

    assert updated is False

    record = redis_client.hgetall(key)

    assert record["value"] == "25.0"
    assert record["timestamp"] == newer["timestamp"]
    assert record["event_id"] == newer["event_id"]


def test_different_measurements_use_different_keys(
    redis_client, sensor_event
):
    temperature = copy.deepcopy(sensor_event)

    humidity = copy.deepcopy(sensor_event)
    humidity["measurement_type"] = "relative_humidity"
    humidity["unit"] = "percent"
    humidity["value"] = 55.0

    temp_event, temp_ms = live.parse_event(
        json.dumps(temperature)
    )
    humidity_event, humidity_ms = live.parse_event(
        json.dumps(humidity)
    )

    temp_key, _ = live.write_latest(
        redis_client, temp_event, temp_ms
    )
    humidity_key, _ = live.write_latest(
        redis_client, humidity_event, humidity_ms
    )

    assert temp_key != humidity_key
    assert redis_client.hget(temp_key, "value") == "23.4"
    assert redis_client.hget(humidity_key, "value") == "55.0"


def test_redis_failure_propagates(sensor_event):
    client = Mock()
    client.eval.side_effect = redis.ConnectionError(
        "Redis unavailable"
    )

    event, timestamp_ms = live.parse_event(
        json.dumps(sensor_event)
    )

    with pytest.raises(redis.ConnectionError):
        live.write_latest(client, event, timestamp_ms)


# ----------------------------------
# 3. Kafka offset commit behavior
# ----------------------------------

def run_one_kafka_message(
    monkeypatch,
    sensor_event,
    redis_failure=False,
):
    """Run main() with one fake Kafka message."""

    message = Mock()
    message.error.return_value = None
    message.value.return_value = json.dumps(
        sensor_event
    ).encode("utf-8")

    kafka_client = Mock()
    redis_connection = Mock()

    polls = 0

    def fake_poll(timeout):
        nonlocal polls
        polls += 1

        if polls == 1:
            return message

        # Stop the main loop after the first event.
        monkeypatch.setattr(live, "running", False)
        return None

    kafka_client.poll.side_effect = fake_poll

    if redis_failure:
        redis_connection.eval.side_effect = (
            redis.ConnectionError("Simulated outage")
        )
    else:
        redis_connection.eval.return_value = 1

    monkeypatch.setattr(live, "running", True)
    monkeypatch.setattr(
        live, "Consumer",
        Mock(return_value=kafka_client),
    )
    monkeypatch.setattr(
        live.redis, "Redis",
        Mock(return_value=redis_connection),
    )

    for name, value in {
        "KAFKA_BOOTSTRAP_SERVERS": "test-kafka:9092",
        "KAFKA_TOPIC": "greenhouse.sensor-readings",
        "KAFKA_CONSUMER_GROUP": "greenhouse-test",
        "REDIS_HOST": "test-redis",
    }.items():
        monkeypatch.setenv(name, value)

    return kafka_client, redis_connection, message


def test_kafka_offset_committed_after_redis_write(
    monkeypatch, sensor_event
):
    kafka, redis_connection, message = (
        run_one_kafka_message(
            monkeypatch, sensor_event
        )
    )

    live.main()

    redis_connection.eval.assert_called_once()

    kafka.commit.assert_called_once_with(
        message=message,
        asynchronous=False,
    )

    kafka.close.assert_called_once()
    redis_connection.close.assert_called_once()


def test_kafka_offset_not_committed_on_redis_failure(
    monkeypatch, sensor_event
):
    kafka, _, _ = run_one_kafka_message(
        monkeypatch,
        sensor_event,
        redis_failure=True,
    )

    with pytest.raises(redis.ConnectionError):
        live.main()

    kafka.commit.assert_not_called()
    kafka.close.assert_called_once()
