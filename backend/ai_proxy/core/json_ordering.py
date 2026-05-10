"""Helpers for JSON text that preserves insertion order."""

import json
from typing import cast

from ai_proxy.types import JsonData


def parse_json_text(raw_text: str) -> JsonData:
    return cast("JsonData", json.loads(raw_text))


def serialize_json_value(value: JsonData) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
