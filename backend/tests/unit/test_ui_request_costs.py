from __future__ import annotations

from ai_proxy.api.ui import requests
from tests.unit.test_ui_repositories_and_logging import make_request_record


def test_serialize_request_uses_byok_inference_cost() -> None:
    record = make_request_record(
        cost=0.002,
        response_body={
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "cost": "0.002",
                "is_byok": True,
                "upstream_inference_cost": 0.01,
            },
        },
    )

    assert requests._serialize_request(record)["cost"] == 0.012


def test_serialize_request_uses_nested_cost_details_and_market_cost() -> None:
    nested_cost_details = make_request_record(
        cost=0.000069125,
        response_body={
            "usage": {
                "prompt_tokens": 1709,
                "completion_tokens": 176,
                "total_tokens": 1885,
                "cost": 0.000069125,
                "is_byok": True,
                "cost_details": {"upstream_inference_cost": 0.0013825},
            },
        },
    )
    market_cost = make_request_record(
        cost=None,
        response_body={
            "choices": [{"message": {"role": "assistant", "content": "hi there"}}],
            "market_cost": "0.125",
        },
    )

    assert requests._serialize_request(nested_cost_details)["cost"] == 0.001451625
    assert requests._serialize_request(market_cost)["cost"] == 0.125


def test_serialize_request_does_not_double_count_non_byok_inference_cost() -> None:
    record = make_request_record(
        cost=0.0003039,
        response_body={
            "usage": {
                "cost": 0.0003039,
                "is_byok": False,
                "cost_details": {"upstream_inference_cost": 0.0003039},
            }
        },
    )

    assert requests._serialize_request(record)["cost"] == 0.0003039


def test_compute_tps_subtracts_ttft() -> None:
    record = make_request_record(output_tokens=100, latency_ms=2000, ttft_ms=500)
    tps = requests._compute_tps(record)
    assert tps is not None
    assert abs(tps - 100 / 1.5) < 0.01

    record_no_ttft = make_request_record(output_tokens=100, latency_ms=2000, ttft_ms=None)
    tps_fallback = requests._compute_tps(record_no_ttft)
    assert tps_fallback is not None
    assert abs(tps_fallback - 50.0) < 0.01

    assert requests._compute_tps(make_request_record(output_tokens=None, latency_ms=2000)) is None
    assert requests._compute_tps(make_request_record(output_tokens=0, latency_ms=2000)) is None
    assert requests._compute_tps(make_request_record(output_tokens=100, latency_ms=None)) is None
    assert requests._compute_tps(make_request_record(output_tokens=100, latency_ms=0)) is None
    assert requests._compute_tps(make_request_record(output_tokens=100, latency_ms=500, ttft_ms=500)) is None
    assert requests._compute_tps(make_request_record(output_tokens=100, latency_ms=500, ttft_ms=600)) is None


def test_serialize_request_includes_tps() -> None:
    record = make_request_record(output_tokens=100, latency_ms=2000, ttft_ms=500)
    result = requests._serialize_request(record)
    assert result["tps"] is not None
    assert abs(result["tps"] - 100 / 1.5) < 0.01

    record_no_tokens = make_request_record(output_tokens=None, latency_ms=2000)
    assert requests._serialize_request(record_no_tokens)["tps"] is None
