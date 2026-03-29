"""API key masking in log data."""

import re

from ai_proxy.types import JsonData, JsonObject

MASK_PATTERNS = re.compile(r"(key|token|secret|password|authorization)", re.IGNORECASE)


def mask_api_key(value: str) -> str:
    if not value or len(value) <= 8:
        return "***"
    return f"{value[:3]}***{value[-4:]}"


def mask_headers(headers: JsonObject) -> JsonObject:
    masked: JsonObject = {}
    for k, v in headers.items():
        if MASK_PATTERNS.search(k):
            masked[k] = mask_api_key(str(v)) if v else v
        else:
            masked[k] = v
    return masked


def mask_sensitive_fields(data: JsonData) -> JsonData:
    if data is None:
        return None
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        return [mask_sensitive_fields(item) for item in data]
    if isinstance(data, dict):
        result: JsonObject = {}
        for k, v in data.items():
            if MASK_PATTERNS.search(k) and isinstance(v, str):
                result[k] = mask_api_key(v)
            else:
                result[k] = mask_sensitive_fields(v)
        return result
    return data
