"""Async logging service — background task that writes to PostgreSQL."""

import asyncio

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ai_proxy.db.engine import get_engine
from ai_proxy.db.models import ProxyRequest
from ai_proxy.logging.masking import mask_headers, mask_sensitive_fields
from ai_proxy.logging.models import LogEntry

logger = structlog.get_logger()

_queue: asyncio.Queue[LogEntry] = asyncio.Queue(maxsize=10000)
_flush_task: asyncio.Task | None = None


async def enqueue_log(entry: LogEntry) -> None:
    try:
        _queue.put_nowait(entry)
    except asyncio.QueueFull:
        logger.warning("log_queue_full", dropping_request_id=str(entry.id))


async def _flush_loop(batch_size: int = 50, flush_interval: float = 5.0) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

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


async def _write_batch(session_factory, entries: list[LogEntry]) -> None:  # noqa: ANN001
    async with session_factory() as session:
        session: AsyncSession
        for entry in entries:
            db_request = ProxyRequest(
                id=entry.id,
                timestamp=entry.timestamp,
                client_ip=entry.client_ip,
                client_api_key_hash=entry.client_api_key_hash,
                method=entry.method,
                path=entry.path,
                request_headers=mask_headers(entry.request_headers) if entry.request_headers else None,
                request_body=mask_sensitive_fields(entry.request_body),
                response_status_code=entry.response_status_code,
                response_headers=mask_headers(entry.response_headers) if entry.response_headers else None,
                response_body=entry.response_body,
                stream_chunks=entry.stream_chunks,
                model_requested=entry.model_requested,
                model_resolved=entry.model_resolved,
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


def start_logging_service(batch_size: int = 50, flush_interval: float = 5.0) -> asyncio.Task:
    global _flush_task  # noqa: PLW0603
    _flush_task = asyncio.create_task(_flush_loop(batch_size, flush_interval))
    return _flush_task


async def stop_logging_service() -> None:
    global _flush_task  # noqa: PLW0603
    if _flush_task:
        _flush_task.cancel()
        try:
            await _flush_task
        except asyncio.CancelledError:
            pass
        _flush_task = None
