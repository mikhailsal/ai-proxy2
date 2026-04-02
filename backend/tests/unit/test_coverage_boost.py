"""Tests to boost backend coverage — targeting uncovered lines across modules."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ai_proxy.adapters.base import ProviderStreamResponse
from ai_proxy.api.ui import requests as requests_mod
from ai_proxy.config import loader
from ai_proxy.config.settings import AppConfig, ModificationRule
from ai_proxy.core import modification
from ai_proxy.logging import service
from ai_proxy.logging.masking import mask_sensitive_fields
from ai_proxy.logging.models import LogEntry
from ai_proxy.security import auth as auth_mod

# Chat repository and streaming tests are in test_coverage_boost_chats.py


def _make_record(**overrides):
    payload = {
        "id": uuid.uuid4(),
        "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "client_ip": "127.0.0.1",
        "client_api_key_hash": "hash",
        "method": "POST",
        "path": "/v1/chat/completions",
        "model_requested": "gpt-4o-mini",
        "model_resolved": "mapped-model",
        "response_status_code": 200,
        "latency_ms": 100.0,
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "cost": None,
        "cache_status": None,
        "error_message": None,
        "request_headers": {},
        "client_request_headers": {},
        "request_body": None,
        "client_request_body": None,
        "response_body": None,
        "client_response_body": None,
        "stream_chunks": None,
        "reasoning_tokens": None,
        "metadata_": None,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


# ── requests.py: _extract_cost — line 70 (cost in body root) ─────────


def test_extract_cost_from_response_body_root():
    record = _make_record(
        response_body={"cost": 0.05},
        client_response_body=None,
    )
    assert requests_mod._extract_cost(record) == 0.05


def test_extract_cost_fallback_to_client_response_body():
    record = _make_record(
        response_body=None,
        client_response_body={"usage": {"cost": 1.23}},
    )
    assert requests_mod._extract_cost(record) == 1.23


# ── requests.py: _extract_last_user_message — lines 80, 83, 86, 96 ──


def test_extract_last_user_message_skips_non_dict_messages():
    record = _make_record(
        request_body={"messages": ["string-message", {"role": "user", "content": "real"}]},
    )
    assert requests_mod._extract_last_user_message(record) == "real"


def test_extract_last_user_message_skips_assistant():
    record = _make_record(
        request_body={
            "messages": [
                {"role": "assistant", "content": "ignored"},
                {"role": "user", "content": "found"},
            ]
        },
    )
    assert requests_mod._extract_last_user_message(record) == "found"


def test_extract_last_user_message_returns_none_when_no_messages_key():
    record = _make_record(request_body={"no_messages": True})
    assert requests_mod._extract_last_user_message(record) is None


def test_extract_last_user_message_returns_none_when_all_exhausted():
    record = _make_record(
        request_body={"messages": [{"role": "assistant", "content": "only assistant"}]},
    )
    assert requests_mod._extract_last_user_message(record) is None


# ── requests.py: _extract_assistant_response — lines 105-129 ─────────


def test_extract_assistant_response_non_dict_choice():
    record = _make_record(response_body={"choices": ["not-a-dict"]})
    assert requests_mod._extract_assistant_response(record) is None


def test_extract_assistant_response_delta_fallback():
    record = _make_record(
        response_body={"choices": [{"delta": {"content": "via delta"}}]},
    )
    assert requests_mod._extract_assistant_response(record) == "via delta"


def test_extract_assistant_response_non_dict_message():
    record = _make_record(
        response_body={"choices": [{"message": "string-not-dict"}]},
    )
    assert requests_mod._extract_assistant_response(record) is None


def test_extract_assistant_response_tool_call_without_function():
    record = _make_record(
        response_body={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [{"id": "tc1"}],
                    },
                }
            ]
        },
    )
    assert requests_mod._extract_assistant_response(record) == "tool_call"


def test_extract_assistant_response_tool_call_non_dict_fn():
    record = _make_record(
        response_body={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [{"function": "not-dict"}],
                    },
                }
            ]
        },
    )
    assert requests_mod._extract_assistant_response(record) == "tool_call"


def test_extract_assistant_response_empty_content_with_no_tools():
    record = _make_record(
        response_body={"choices": [{"message": {"role": "assistant", "content": ""}}]},
    )
    assert requests_mod._extract_assistant_response(record) is None


def test_extract_assistant_response_non_dict_tool_call_skipped():
    record = _make_record(
        response_body={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": ["not-a-dict", {"function": {"name": "search"}}],
                    },
                }
            ]
        },
    )
    assert requests_mod._extract_assistant_response(record) == "search"


# ── requests.py: _summarize_tool_args & _compact_value lines 136-162 ─


def test_summarize_tool_args_non_dict_parsed():
    assert requests_mod._summarize_tool_args("[1,2,3]") == ""


def test_summarize_tool_args_non_string_non_dict():
    assert requests_mod._summarize_tool_args(42) == ""


def test_compact_value_bool():
    assert requests_mod._compact_value(True) == "true"
    assert requests_mod._compact_value(False) == "false"


def test_compact_value_int_float():
    assert requests_mod._compact_value(42) == "42"
    assert requests_mod._compact_value(3.14) == "3.14"


def test_compact_value_list_dict_none():
    assert requests_mod._compact_value([1, 2]) == "[2 items]"
    assert requests_mod._compact_value({"a": 1, "b": 2}) == "{2 keys}"
    assert requests_mod._compact_value(None) == "null"


def test_compact_value_other_type():
    assert requests_mod._compact_value(object()) != ""


# ── requests.py: _extract_cached_tokens — edge cases ─────────────────


def test_extract_cached_tokens_non_int_cached():
    record = _make_record(
        response_body={"usage": {"prompt_tokens_details": {"cached_tokens": "not-int"}}},
    )
    assert requests_mod._extract_cached_tokens(record) is None


def test_extract_cached_tokens_non_dict_details():
    record = _make_record(
        response_body={"usage": {"prompt_tokens_details": "not-dict"}},
    )
    assert requests_mod._extract_cached_tokens(record) is None


def test_extract_cached_tokens_non_dict_usage():
    record = _make_record(response_body={"usage": "not-dict"})
    assert requests_mod._extract_cached_tokens(record) is None


# ── core/modification.py: lines 19, 21 (match_model mismatch) ────────


def test_modification_skips_non_matching_provider(monkeypatch):
    config = AppConfig(
        modification_rules=[
            ModificationRule(action="add_header", key="X-Test", value="v", match_provider="other-*"),
        ],
    )
    monkeypatch.setattr(modification, "get_app_config", lambda: config)
    body, headers = modification.apply_modifications({}, {}, "primary", "gpt-4o")
    assert "X-Test" not in headers


def test_modification_skips_non_matching_model(monkeypatch):
    config = AppConfig(
        modification_rules=[
            ModificationRule(action="add_header", key="X-Test", value="v", match_provider="*", match_model="claude-*"),
        ],
    )
    monkeypatch.setattr(modification, "get_app_config", lambda: config)
    body, headers = modification.apply_modifications({}, {}, "primary", "gpt-4o")
    assert "X-Test" not in headers


# ── security/auth.py: lines 61-64 (no api_key, no configured keys) ───


def test_validate_proxy_no_key_no_configured_keys(monkeypatch):
    config = AppConfig(api_keys=[])
    monkeypatch.setattr(loader, "_app_config", config)
    settings = SimpleNamespace(get_api_keys=lambda: [], ui_api_key="")
    monkeypatch.setattr("ai_proxy.security.auth.get_settings", lambda: settings)

    ok, key_hash, is_known = auth_mod.validate_proxy_api_key(None, bypass_enabled=False)
    assert ok is True
    assert is_known is False
    assert key_hash == auth_mod.hash_api_key("anonymous")


def test_validate_proxy_no_key_with_configured_keys(monkeypatch):
    config = AppConfig(api_keys=["secret"])
    monkeypatch.setattr(loader, "_app_config", config)
    settings = SimpleNamespace(get_api_keys=lambda: [], ui_api_key="")
    monkeypatch.setattr("ai_proxy.security.auth.get_settings", lambda: settings)

    ok, key_hash, is_known = auth_mod.validate_proxy_api_key(None, bypass_enabled=False)
    assert ok is False


def test_validate_proxy_wrong_key_no_configured(monkeypatch):
    config = AppConfig(api_keys=[])
    monkeypatch.setattr(loader, "_app_config", config)
    settings = SimpleNamespace(get_api_keys=lambda: [], ui_api_key="")
    monkeypatch.setattr("ai_proxy.security.auth.get_settings", lambda: settings)

    ok, key_hash, is_known = auth_mod.validate_proxy_api_key("any-key")
    assert ok is True
    assert is_known is False


# ── config/loader.py: lines 46, 76, 80 (api_keys edge cases) ─────────


def test_loader_api_keys_string_format(tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text("providers: {}")
    secrets_path = tmp_path / "config.secrets.yml"
    secrets_path.write_text('api_keys: "key1, key2, key3"')

    config = loader.load_config(str(config_path), secrets_path=str(secrets_path))
    assert config.api_keys == ["key1", "key2", "key3"]


def test_loader_api_keys_non_list_non_string(tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text("providers: {}")
    secrets_path = tmp_path / "config.secrets.yml"
    secrets_path.write_text("api_keys: 12345")

    config = loader.load_config(str(config_path), secrets_path=str(secrets_path))
    assert config.api_keys == []


def test_loader_non_dict_mapping_skipped(tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text("providers: {}")
    secrets_path = tmp_path / "config.secrets.yml"
    secrets_path.write_text('key_mappings:\n  "client-key": "not-a-dict"')

    config = loader.load_config(str(config_path), secrets_path=str(secrets_path))
    assert config.key_mappings == {}


# ── logging/service.py: lines 61-69 (CancelledError flush) ───────────


@pytest.mark.asyncio
async def test_flush_loop_cancellation_flushes_remaining(monkeypatch):
    write_calls = []

    async def fake_write_batch(session_factory, entries):
        write_calls.append(len(entries))

    monkeypatch.setattr(service, "_write_batch", fake_write_batch)

    fake_engine = object()
    monkeypatch.setattr(service, "get_engine", lambda: fake_engine)
    monkeypatch.setattr(service, "async_sessionmaker", lambda engine, expire_on_commit: None)

    original_queue = service._queue
    service._queue = asyncio.Queue(maxsize=100)

    try:
        entry1 = LogEntry(provider_name="test1")
        entry2 = LogEntry(provider_name="test2")
        service._queue.put_nowait(entry1)
        service._queue.put_nowait(entry2)

        task = asyncio.create_task(service._flush_loop(batch_size=50, flush_interval=0.01))
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        total_written = sum(write_calls)
        assert total_written >= 2
    finally:
        service._queue = original_queue


# ── logging/service.py: line 129 (provider_config is None) ───────────


@pytest.mark.asyncio
async def test_resolve_provider_id_unknown_provider(monkeypatch):
    class FakeSession:
        async def execute(self, query):
            return SimpleNamespace(scalar_one_or_none=lambda: None)

    monkeypatch.setattr(
        service,
        "get_app_config",
        lambda: SimpleNamespace(providers={}),
    )
    result = await service._resolve_provider_id(FakeSession(), "nonexistent")
    assert result is None


# ── adapters/base.py: line 50 (error_body is None) ───────────────────


def test_provider_stream_response_parsed_error_body_none():
    stream = ProviderStreamResponse(status_code=200, headers={}, error_body=None)
    assert stream.parsed_error_body() is None


# ── logging/masking.py: line 42 (non-scalar data passthrough) ────────


def test_mask_sensitive_fields_numeric():
    assert mask_sensitive_fields(42) == 42
    assert mask_sensitive_fields(3.14) == 3.14
    assert mask_sensitive_fields(True) is True
