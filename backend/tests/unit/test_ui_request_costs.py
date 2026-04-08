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
