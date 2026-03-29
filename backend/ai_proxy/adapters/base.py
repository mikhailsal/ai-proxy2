"""Abstract base adapter."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator


class BaseAdapter(ABC):
    def __init__(self, provider_name: str, endpoint_url: str, api_key: str | None, headers: dict[str, str] | None = None, timeout: int = 120) -> None:
        self.provider_name = provider_name
        self.endpoint_url = endpoint_url.rstrip("/")
        self.api_key = api_key
        self.extra_headers = headers or {}
        self.timeout = timeout

    @abstractmethod
    async def chat_completions(self, request_body: dict, headers: dict[str, str]) -> dict:
        ...

    @abstractmethod
    async def stream_chat_completions(self, request_body: dict, headers: dict[str, str]) -> AsyncGenerator[bytes, None]:
        ...

    @abstractmethod
    async def list_models(self) -> list[dict]:
        ...
