"""Shared backend JSON-oriented type aliases."""

from typing import Any, TypeAlias

JsonObject: TypeAlias = dict[str, Any]
JsonArray: TypeAlias = list[Any]
JsonData: TypeAlias = JsonObject | JsonArray | str | int | float | bool | None
