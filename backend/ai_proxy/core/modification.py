"""Request enrichment/modification rules."""

import fnmatch

from ai_proxy.config.loader import get_app_config


def apply_modifications(
    request_body: dict,
    headers: dict[str, str],
    provider_name: str,
    model: str,
) -> tuple[dict, dict[str, str]]:
    config = get_app_config()

    for rule in config.modification_rules:
        if not fnmatch.fnmatch(provider_name, rule.match_provider):
            continue
        if not fnmatch.fnmatch(model, rule.match_model):
            continue

        if rule.action == "add_header":
            headers[rule.key] = rule.value or ""
        elif rule.action == "remove_header":
            headers.pop(rule.key, None)
        elif rule.action == "set_field":
            request_body[rule.key] = rule.value
        elif rule.action == "remove_field":
            request_body.pop(rule.key, None)

    return request_body, headers
