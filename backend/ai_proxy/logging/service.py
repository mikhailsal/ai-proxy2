"""Async logging service — background task that writes to PostgreSQL."""

import asyncio
from contextlib import suppress
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_proxy.config.loader import get_app_config
from ai_proxy.db.engine import get_engine
from ai_proxy.db.models import Provider, ProxyRequest
from ai_proxy.logging.masking import mask_headers, mask_sensitive_fields
from ai_proxy.logging.models import LogEntry

logger = structlog.get_logger()

_queue: asyncio.Queue[LogEntry] = asyncio.Queue(maxsize=10000)
_flush_task: asyncio.Task[None] | None = None


async def enqueue_log(entry: LogEntry) -> None:
    try:
        _queue.put_nowait(entry)
    except asyncio.QueueFull:
        logger.warning("log_queue_full", dropping_request_id=str(entry.id))


async def _flush_loop(batch_size: int = 50, flush_interval: float = 5.0) -> None:
    engine = get_engine()
    if engine is None:
        logger.error("logging_service_no_engine")
        return

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    while True:
        entries: list[LogEntry] = []
        try:
            # Wait for first entry or timeout
            try:
                entry = await asyncio.wait_for(_queue.get(), timeout=flush_interval)
                entries.append(entry)
            except asyncio.TimeoutError:
                continue

            # Drain up to batch_size
            while len(entries) < batch_size:
                try:
                    entry = _queue.get_nowait()
                    entries.append(entry)
                except asyncio.QueueEmpty:
                    break

            # Write batch
            await _write_batch(session_factory, entries)
        except asyncio.CancelledError:
            # Flush remaining on shutdown
            while not _queue.empty():
                try:
                    entries.append(_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            if entries:
                try:
                    await _write_batch(session_factory, entries)
                except Exception:
                    logger.exception("shutdown_flush_failed")
            raise
        except Exception:
            logger.exception("flush_loop_error", batch_size=len(entries))


_provider_id_cache: dict[str, int | None] = {}


async def _write_batch(session_factory: async_sessionmaker[AsyncSession], entries: list[LogEntry]) -> None:
    async with session_factory() as session:
        needed_names = {e.provider_name for e in entries if e.provider_name is not None}
        uncached_names = needed_names - _provider_id_cache.keys()
        if uncached_names:
            await _warm_provider_cache(session, uncached_names)

        for entry in entries:
            provider_id = _provider_id_cache.get(entry.provider_name) if entry.provider_name else None
            if entry.provider_name and provider_id is None and entry.provider_name not in _provider_id_cache:
                provider_id = await _resolve_provider_id(session, entry.provider_name)

            db_request = ProxyRequest(
                id=entry.id,
                timestamp=entry.timestamp,
                client_ip=entry.client_ip,
                client_api_key_hash=entry.client_api_key_hash,
                method=entry.method,
                path=entry.path,
                request_headers=mask_headers(entry.request_headers) if entry.request_headers else None,
                client_request_headers=mask_headers(entry.client_request_headers)
                if entry.client_request_headers
                else None,
                request_body=mask_sensitive_fields(entry.request_body),
                client_request_body=mask_sensitive_fields(entry.client_request_body),
                response_status_code=entry.response_status_code,
                response_headers=mask_headers(entry.response_headers) if entry.response_headers else None,
                client_response_headers=mask_headers(entry.client_response_headers)
                if entry.client_response_headers
                else None,
                response_body=entry.response_body,
                client_response_body=entry.client_response_body,
                stream_chunks=entry.stream_chunks,
                model_requested=entry.model_requested,
                model_resolved=entry.model_resolved,
                provider_id=provider_id,
                latency_ms=entry.latency_ms,
                input_tokens=entry.input_tokens,
                output_tokens=entry.output_tokens,
                total_tokens=entry.total_tokens,
                cost=entry.cost,
                cache_status=entry.cache_status,
                reasoning_tokens=entry.reasoning_tokens,
                error_message=entry.error_message,
                metadata_=entry.metadata,
            )
            session.add(db_request)
        await session.commit()
        logger.debug("batch_written", count=len(entries))


async def _warm_provider_cache(session: AsyncSession, names: set[str]) -> None:
    """Batch-load provider IDs for all names in a single query."""
    result = await session.execute(select(Provider).where(Provider.name.in_(names)))
    for provider in result.scalars().all():
        _provider_id_cache[provider.name] = provider.id


async def _resolve_provider_id(session: AsyncSession, provider_name: str | None) -> int | None:
    if provider_name is None:
        return None

    cached = _provider_id_cache.get(provider_name)
    if cached is not None:
        return cached

    existing = await session.execute(select(Provider).where(Provider.name == provider_name))
    provider = existing.scalar_one_or_none()
    if provider is not None:
        _provider_id_cache[provider_name] = provider.id
        return provider.id

    provider_config = get_app_config().providers.get(provider_name)
    if provider_config is None:
        _provider_id_cache[provider_name] = None
        return None

    settings_json: dict[str, Any] = {
        "headers": provider_config.headers,
        "timeout": provider_config.timeout,
    }
    if provider_config.fallback_for:
        settings_json["fallback_for"] = provider_config.fallback_for

    provider = Provider(
        name=provider_name,
        endpoint_url=provider_config.endpoint,
        provider_type=provider_config.type,
        settings_json=settings_json,
    )
    session.add(provider)
    await session.flush()
    _provider_id_cache[provider_name] = provider.id
    return provider.id


def start_logging_service(batch_size: int = 50, flush_interval: float = 5.0) -> asyncio.Task[None]:
    global _flush_task
    _flush_task = asyncio.create_task(_flush_loop(batch_size, flush_interval))
    return _flush_task


async def stop_logging_service() -> None:
    global _flush_task
    if _flush_task:
        _flush_task.cancel()
        with suppress(asyncio.CancelledError):
            await _flush_task
        _flush_task = None
