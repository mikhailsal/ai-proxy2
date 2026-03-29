"""Model access control."""

import fnmatch

from ai_proxy.config.loader import get_app_config


def check_model_access(client_key_hash: str, model: str) -> tuple[bool, str]:
    config = get_app_config()
    rules = config.access_rules

    if not rules:
        return True, ""

    # Check rules for this specific client key hash
    if client_key_hash in rules:
        rule = rules[client_key_hash]
        if hasattr(rule, "block") and rule.block:
            for pattern in rule.block:
                if fnmatch.fnmatch(model, pattern):
                    return False, f"Model {model} is blocked for this API key"
        if hasattr(rule, "allow") and rule.allow:
            for pattern in rule.allow:
                if fnmatch.fnmatch(model, pattern):
                    return True, ""
            return False, f"Model {model} is not in the allowlist for this API key"

    return True, ""
