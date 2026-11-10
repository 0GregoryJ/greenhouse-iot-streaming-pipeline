from api.routes import history


def test_history_series(client, monkeypatch):
    expected = {
        "sensor_id": "bme280-001",
        "measurement_type": "air_temperature",
        "period": "7d",
        "resolution": "hour",
        "unit": "celsius",
        "count": 0,
        "points": [],
    }

    def fake_fetch_history(sensor_id, measurement_type, period):
        assert sensor_id == "bme280-001"
        assert measurement_type == "air_temperature"
        assert period == "7d"
        return expected

    monkeypatch.setattr(
        history,
        "fetch_history",
        fake_fetch_history,
    )

    response = client.get(
        "/api/v1/history/series",
        params={
            "sensor_id": "bme280-001",
            "measurement_type": "air_temperature",
            "period": "7d",
        },
    )

    assert response.status_code == 200
    assert response.json() == expected


def test_history_invalid_period(client):
    response = client.get(
        "/api/v1/history/series",
        params={
            "sensor_id": "bme280-001",
            "measurement_type": "air_temperature",
            "period": "invalid",
        },
    )

    assert response.status_code == 422
