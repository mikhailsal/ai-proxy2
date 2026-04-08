"""UI API — Model catalog endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ai_proxy.api.deps import require_ui_auth
from ai_proxy.services.model_catalog import get_proxy_model_catalog

if TYPE_CHECKING:
    from ai_proxy.types import JsonObject

router = APIRouter(dependencies=[Depends(require_ui_auth)])


@router.get("/ui/v1/models")
async def list_catalog_models() -> JSONResponse:
    catalog = await get_proxy_model_catalog()
    models: list[JsonObject] = []

    for entry in catalog.values():
        item: JsonObject = {
            "id": entry.client_model,
            "provider": entry.provider_name,
            "mapped_model": entry.mapped_model,
        }

        if entry.pinned_providers:
            item["pinned_providers"] = list(entry.pinned_providers)

        if entry.metadata:
            for key, value in entry.metadata.items():
                if key != "id":
                    item.setdefault(key, value)

        models.append(item)

    return JSONResponse({"object": "list", "data": models})
