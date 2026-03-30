"""Chat repository — conversation grouping and message reconstruction."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import desc, select

from ai_proxy.db.models import ProxyRequest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _isoformat(value: Any) -> str | None:
    return value.isoformat() if value else None


def _request_messages(request_body: Any) -> list[dict[str, Any]]:
    if not isinstance(request_body, dict):
        return []

    messages = request_body.get("messages")
    if not isinstance(messages, list):
        return []

    return [message for message in messages if isinstance(message, dict)]


def _content_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
                    continue
                part_type = item.get("type")
                if isinstance(part_type, str) and part_type:
                    parts.append(f"[{part_type}]")
                    continue
            parts.append(json.dumps(item, sort_keys=True, ensure_ascii=False))
        return "\n".join(part for part in parts if part).strip()
    if value is None:
        return ""
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _message_tool_names(message: dict[str, Any]) -> list[str]:
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list):
        return []

    names: list[str] = []
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        function = tool_call.get("function")
        if isinstance(function, dict) and isinstance(function.get("name"), str):
            names.append(function["name"])
            continue
        if isinstance(tool_call.get("name"), str):
            names.append(tool_call["name"])
    return names


def _message_meta_tags(message: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in message.items() if key not in {"role", "content", "tool_calls"}}


def _message_display_text(message: dict[str, Any]) -> str:
    content = _content_text(message.get("content"))
    if content:
        return content

    tool_names = _message_tool_names(message)
    if tool_names:
        return f"Tool call: {', '.join(tool_names)}"

    role = message.get("role")
    if role == "tool":
        tool_name = message.get("name") or message.get("tool_call_id")
        if isinstance(tool_name, str) and tool_name:
            return f"Tool result: {tool_name}"

    return "(empty message)"


def _message_signature(message: dict[str, Any]) -> str:
    return json.dumps(message, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _first_message_by_role(request_body: Any, role: str) -> dict[str, Any] | None:
    for message in _request_messages(request_body):
        if message.get("role") == role:
            return message
    return None


def _first_message_text(request_body: Any) -> str:
    messages = _request_messages(request_body)
    if not messages:
        return "unknown"

    return _message_display_text(messages[0]) or "unknown"


def _group_identity(request: ProxyRequest, group_by: str) -> tuple[str, str]:
    request_body = getattr(request, "request_body", None)

    if group_by == "client":
        value = getattr(request, "client_api_key_hash", None) or "unknown"
        return value, value

    if group_by == "model":
        value = getattr(request, "model_requested", None) or getattr(request, "model_resolved", None) or "unknown"
        return value, value

    system_message = _first_message_by_role(request_body, "system")
    first_user_message = _first_message_by_role(request_body, "user")
    system_text = _message_display_text(system_message) if system_message else ""
    user_text = _message_display_text(first_user_message) if first_user_message else ""

    if group_by == "system_prompt_first_user":
        group_key = json.dumps(
            {"system_prompt": system_text, "first_user_message": user_text},
            sort_keys=True,
            ensure_ascii=False,
        )
        if system_text and user_text:
            return group_key, f"System: {system_text}\nUser: {user_text}"
        if system_text:
            return group_key, f"System: {system_text}"
        if user_text:
            return group_key, f"User: {user_text}"
        return group_key, "unknown"

    if system_text:
        return system_text, system_text
    if user_text:
        return user_text, user_text
    fallback = _first_message_text(request_body)
    return fallback, fallback


def _assistant_response_message(response_body: Any) -> dict[str, Any] | None:
    if not isinstance(response_body, dict):
        return None

    choices = response_body.get("choices")
    if not isinstance(choices, list) or not choices:
        return None

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return None

    message = first_choice.get("message")
    if not isinstance(message, dict):
        return None

    return message


def _message_entry(
    *,
    message: dict[str, Any],
    request: ProxyRequest,
    ordinal: int,
    origin: str,
    source_message_index: int,
) -> dict[str, Any]:
    timestamp = _isoformat(getattr(request, "timestamp", None))
    return {
        "id": f"{request.id}:{origin}:{ordinal}",
        "origin": origin,
        "role": message.get("role") or "unknown",
        "content": _message_display_text(message),
        "raw_message": message,
        "tool_names": _message_tool_names(message),
        "meta_tags": _message_meta_tags(message),
        "source_request_id": str(request.id),
        "source_request_timestamp": timestamp,
        "source_message_index": source_message_index,
        "last_seen_at": timestamp,
        "repeat_count": 1,
        "model": getattr(request, "model_resolved", None) or getattr(request, "model_requested", None),
        "latency_ms": getattr(request, "latency_ms", None),
        "total_tokens": getattr(request, "total_tokens", None),
        "_signature": _message_signature(message),
        "_ordinal": ordinal,
    }


def build_conversation_messages(requests: list[ProxyRequest]) -> list[dict[str, Any]]:
    ordered_requests = sorted(
        requests,
        key=lambda request: (
            getattr(request, "timestamp", None) or "",
            str(getattr(request, "id", "")),
        ),
    )
    timeline: list[dict[str, Any]] = []

    for request in ordered_requests:
        position = 0
        request_messages = _request_messages(getattr(request, "request_body", None))
        for source_message_index, message in enumerate(request_messages):
            signature = _message_signature(message)
            if position < len(timeline) and timeline[position]["_signature"] == signature:
                timeline[position]["repeat_count"] += 1
                timeline[position]["last_seen_at"] = _isoformat(getattr(request, "timestamp", None))
                position += 1
                continue

            timeline.append(
                _message_entry(
                    message=message,
                    request=request,
                    ordinal=len(timeline),
                    origin="request",
                    source_message_index=source_message_index,
                )
            )
            position += 1

        assistant_message = _assistant_response_message(getattr(request, "response_body", None))
        if assistant_message:
            signature = _message_signature(assistant_message)
            if position < len(timeline) and timeline[position]["_signature"] == signature:
                timeline[position]["repeat_count"] += 1
                timeline[position]["last_seen_at"] = _isoformat(getattr(request, "timestamp", None))
                continue

            timeline.append(
                _message_entry(
                    message=assistant_message,
                    request=request,
                    ordinal=len(timeline),
                    origin="response",
                    source_message_index=len(request_messages),
                )
            )

    result: list[dict[str, Any]] = []
    for item in reversed(timeline):
        public_item = dict(item)
        public_item.pop("_signature", None)
        public_item.pop("_ordinal", None)
        result.append(public_item)
    return result


async def get_conversations(
    session: AsyncSession,
    *,
    group_by: str = "system_prompt",
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    query = select(ProxyRequest).order_by(desc(ProxyRequest.timestamp), desc(ProxyRequest.id))
    result = await session.execute(query)
    records = list(result.scalars().all())

    grouped: dict[str, dict[str, Any]] = {}
    for record in records:
        group_key, group_label = _group_identity(record, group_by)
        conversation = grouped.setdefault(
            group_key,
            {
                "group_key": group_key,
                "group_label": group_label,
                "_records": [],
                "_first": getattr(record, "timestamp", None),
                "_last": getattr(record, "timestamp", None),
                "models_used": [],
            },
        )
        conversation["_records"].append(record)

        timestamp = getattr(record, "timestamp", None)
        if conversation["_first"] is None or (timestamp and timestamp < conversation["_first"]):
            conversation["_first"] = timestamp
        if conversation["_last"] is None or (timestamp and timestamp > conversation["_last"]):
            conversation["_last"] = timestamp

        model = getattr(record, "model_requested", None) or getattr(record, "model_resolved", None)
        if model and model not in conversation["models_used"]:
            conversation["models_used"].append(model)

    conversations: list[dict[str, Any]] = []
    for conversation in grouped.values():
        requests_in_conversation = conversation.pop("_records")
        messages = build_conversation_messages(requests_in_conversation)
        conversations.append(
            {
                "group_key": conversation["group_key"],
                "group_label": conversation["group_label"],
                "message_count": len(messages),
                "request_count": len(requests_in_conversation),
                "first_message": _isoformat(conversation.pop("_first")),
                "last_message": _isoformat(conversation.pop("_last")),
                "models_used": conversation["models_used"],
            }
        )

    conversations.sort(key=lambda item: item["last_message"] or "", reverse=True)
    return conversations[offset : offset + limit]


async def get_conversation_messages(
    session: AsyncSession,
    group_key: str,
    group_by: str = "system_prompt",
) -> list[dict[str, Any]]:
    query = select(ProxyRequest).order_by(ProxyRequest.timestamp, ProxyRequest.id)
    result = await session.execute(query)
    requests = [request for request in result.scalars().all() if _group_identity(request, group_by)[0] == group_key]
    return build_conversation_messages(requests)
