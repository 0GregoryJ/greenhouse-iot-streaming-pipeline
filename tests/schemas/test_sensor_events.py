
import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "schemas"


def load_schema(version):
    path = SCHEMA_DIR / f"sensor_event.v{version}.schema.json"

    with open(path) as f:
        schema = json.load(f)

    Draft202012Validator.check_schema(schema)
    return schema


SCHEMAS = {
    1: load_schema(1),
    2: load_schema(2),
}


def validate(event):
    version = event["schema_version"]

    validator = Draft202012Validator(
        SCHEMAS[version],
        format_checker=FormatChecker(),
    )
    validator.validate(event)


def test_valid_v2_temperature(valid_event):
    validate(valid_event)


def test_valid_v1_temperature(valid_event):
    event = copy.deepcopy(valid_event)
    event["schema_version"] = 1

    validate(event)


def test_valid_v2_pressure(valid_event):
    event = copy.deepcopy(valid_event)
    event["measurement_type"] = "atmospheric_pressure"
    event["value"] = 1013.2
    event["unit"] = "hpa"

    validate(event)


def test_v1_rejects_pressure(valid_event):
    event = copy.deepcopy(valid_event)
    event["schema_version"] = 1
    event["measurement_type"] = "atmospheric_pressure"
    event["unit"] = "hpa"

    with pytest.raises(Exception):
        validate(event)


def test_rejects_missing_event_id(valid_event):
    event = copy.deepcopy(valid_event)
    del event["event_id"]

    with pytest.raises(Exception):
        validate(event)


def test_rejects_extra_field(valid_event):
    event = copy.deepcopy(valid_event)
    event["unknown_field"] = "unexpected"

    with pytest.raises(Exception):
        validate(event)


def test_rejects_wrong_unit(valid_event):
    event = copy.deepcopy(valid_event)
    event["measurement_type"] = "atmospheric_pressure"
    event["unit"] = "percent"

    with pytest.raises(Exception):
        validate(event)
