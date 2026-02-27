"""Telemetry spool writer interfaces and async local JSONL implementation."""

from __future__ import annotations

import atexit
import logging
import os
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final, Mapping, Optional, Protocol

from .config import load_config
from .contract import serialize_event

_LOG = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE: Final[int] = 100
_CLOSE_TIMEOUT_SECONDS: Final[float] = 5.0
_RETENTION_SWEEP_INTERVAL_SECONDS: Final[float] = 300.0
_FILE_SUFFIX: Final[str] = ".jsonl"


class SpoolWriter(Protocol):
    """Minimal writer protocol used by ``emit``."""

    def write_event(self, event: Mapping[str, Any]) -> None: ...

    def flush(self) -> None: ...

    def close(self) -> None: ...


class NullSpoolWriter:
    """No-op writer used when telemetry writing is disabled/unavailable."""

    def write_event(self, event: Mapping[str, Any]) -> None:
        del event

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None


class MemorySpoolWriter:
    """Bounded in-memory writer useful for tests and local debugging."""

    def __init__(self, max_events: int = 5000) -> None:
        if max_events < 1:
            raise ValueError("max_events must be >= 1")
        self._buffer: deque[dict[str, Any]] = deque(maxlen=max_events)
        self._dropped_count = 0
        self._lock = threading.Lock()

    @property
    def dropped_count(self) -> int:
        return self._dropped_count

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._buffer)

    def write_event(self, event: Mapping[str, Any]) -> None:
        with self._lock:
            if len(self._buffer) == self._buffer.maxlen:
                self._dropped_count += 1
            self._buffer.append(dict(event))

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None


class JsonlSpoolWriter:
    """Synchronous append-only JSONL writer kept for local debugging/tests."""

    def __init__(self, spool_dir: Path, *, filename_prefix: str = "telemetry") -> None:
        self._spool_dir = spool_dir
        self._filename_prefix = filename_prefix
        self._lock = threading.Lock()
        self._handle: Optional[Any] = None
        self._path: Optional[Path] = None

    @property
    def path(self) -> Optional[Path]:
        return self._path

    def _ensure_handle(self) -> Any:
        if self._handle is None:
            self._spool_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            pid = str(os.getpid())
            self._path = (
                self._spool_dir / f"{self._filename_prefix}-{stamp}-{pid}{_FILE_SUFFIX}"
            )
            self._handle = self._path.open("a", encoding="utf-8")
        return self._handle

    def write_event(self, event: Mapping[str, Any]) -> None:
        line = serialize_event(event)
        with self._lock:
            handle = self._ensure_handle()
            handle.write(line)
            handle.write("\n")

    def flush(self) -> None:
        with self._lock:
            if self._handle is not None:
                self._handle.flush()

    def close(self) -> None:
        with self._lock:
            if self._handle is not None:
                self._handle.close()
                self._handle = None


@dataclass(frozen=True)
class AsyncSpoolStats:
    """In-process async writer diagnostics for operational visibility."""

    enqueued_count: int
    written_count: int
    dropped_queue_full: int
    dropped_serialize: int
    dropped_write_failure: int
    rotated_files: int
    retention_deletes: int
    queue_size: int
    is_closed: bool
    active_path: Optional[Path]


class AsyncJsonlSpoolWriter:
    """Queue-backed JSONL spool writer with rotation/retention and flush-on-close."""

    def __init__(
        self,
        spool_dir: Path,
        *,
        filename_prefix: str = "telemetry",
        queue_max: int = 5000,
        flush_ms: int = 1000,
        rotate_mb: int = 8,
        retention_days: int = 7,
        batch_size: int = _DEFAULT_BATCH_SIZE,
    ) -> None:
        if queue_max < 1:
            raise ValueError("queue_max must be >= 1")
        if flush_ms < 1:
            raise ValueError("flush_ms must be >= 1")
        if rotate_mb < 1:
            raise ValueError("rotate_mb must be >= 1")
        if retention_days < 1:
            raise ValueError("retention_days must be >= 1")
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")

        self._spool_dir = spool_dir
        self._filename_prefix = filename_prefix
        self._flush_seconds = flush_ms / 1000.0
        self._rotate_bytes = rotate_mb * 1024 * 1024
        self._retention_days = retention_days
        self._batch_size = batch_size

        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=queue_max)
        self._state_lock = threading.Lock()
        self._stats_lock = threading.Lock()
        self._stop_event = threading.Event()

        self._is_closed = False
        self._handle: Optional[Any] = None
        self._active_path: Optional[Path] = None
        self._active_size_bytes = 0
        self._file_index = 0
        self._last_retention_sweep = 0.0

        self._enqueued_count = 0
        self._written_count = 0
        self._dropped_queue_full = 0
        self._dropped_serialize = 0
        self._dropped_write_failure = 0
        self._rotated_files = 0
        self._retention_deletes = 0

        self._worker = threading.Thread(
            target=self._worker_loop,
            name="pipe-telemetry-spool-writer",
            daemon=True,
        )
        self._worker.start()

    @property
    def path(self) -> Optional[Path]:
        with self._state_lock:
            return self._active_path

    def stats(self) -> AsyncSpoolStats:
        with self._stats_lock:
            return AsyncSpoolStats(
                enqueued_count=self._enqueued_count,
                written_count=self._written_count,
                dropped_queue_full=self._dropped_queue_full,
                dropped_serialize=self._dropped_serialize,
                dropped_write_failure=self._dropped_write_failure,
                rotated_files=self._rotated_files,
                retention_deletes=self._retention_deletes,
                queue_size=self._queue.qsize(),
                is_closed=self._is_closed,
                active_path=self.path,
            )

    def _increment(self, name: str, amount: int = 1) -> int:
        with self._stats_lock:
            if name == "enqueued_count":
                self._enqueued_count += amount
                return self._enqueued_count
            elif name == "written_count":
                self._written_count += amount
                return self._written_count
            elif name == "dropped_queue_full":
                self._dropped_queue_full += amount
                return self._dropped_queue_full
            elif name == "dropped_serialize":
                self._dropped_serialize += amount
                return self._dropped_serialize
            elif name == "dropped_write_failure":
                self._dropped_write_failure += amount
                return self._dropped_write_failure
            elif name == "rotated_files":
                self._rotated_files += amount
                return self._rotated_files
            elif name == "retention_deletes":
                self._retention_deletes += amount
                return self._retention_deletes
            return 0

    def write_event(self, event: Mapping[str, Any]) -> None:
        if self._is_closed:
            self._increment("dropped_queue_full")
            _LOG.debug("Telemetry spool writer is closed; dropping event")
            return

        try:
            self._queue.put_nowait(dict(event))
            self._increment("enqueued_count")
        except queue.Full:
            dropped = self._increment("dropped_queue_full")
            if dropped == 1 or dropped % 100 == 0:
                _LOG.warning(
                    "Telemetry queue full; dropped %d events (queue_max=%d)",
                    dropped,
                    self._queue.maxsize,
                )
            _LOG.debug("Telemetry queue full details", exc_info=True)

    def flush(self) -> None:
        deadline = time.monotonic() + _CLOSE_TIMEOUT_SECONDS
        while self._queue.unfinished_tasks:
            if self._worker.is_alive():
                if time.monotonic() > deadline:
                    _LOG.warning(
                        "Telemetry flush timed out with %d pending events",
                        self._queue.unfinished_tasks,
                    )
                    break
                time.sleep(0.01)
                continue

            dropped = 0
            while True:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
                dropped += 1
                self._queue.task_done()
            if dropped:
                self._increment("dropped_write_failure", dropped)
                _LOG.warning(
                    "Telemetry spool worker offline; dropped %d queued events", dropped
                )
            break

        with self._state_lock:
            if self._handle is not None:
                self._handle.flush()

    def close(self) -> None:
        with self._state_lock:
            if self._is_closed:
                return
            self._is_closed = True

        self._stop_event.set()
        self.flush()
        self._worker.join(timeout=_CLOSE_TIMEOUT_SECONDS)
        if self._worker.is_alive():
            _LOG.warning(
                "Telemetry spool writer did not stop within %.1fs timeout",
                _CLOSE_TIMEOUT_SECONDS,
            )
        self._close_handle()

    def _worker_loop(self) -> None:
        try:
            self._spool_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self._increment("dropped_write_failure")
            _LOG.warning(
                "Failed to create telemetry spool dir '%s': %s", self._spool_dir, exc
            )
            _LOG.debug("Telemetry spool dir failure details", exc_info=True)
            return

        self._sweep_retention(force=True)

        while True:
            if self._stop_event.is_set() and self._queue.empty():
                break

            batch = self._dequeue_batch()
            if not batch:
                self._flush_handle()
                self._sweep_retention(force=False)
                continue

            serialized_lines: list[str] = []
            for event in batch:
                try:
                    serialized_lines.append(serialize_event(event))
                except Exception as exc:
                    self._increment("dropped_serialize")
                    _LOG.warning("Telemetry serialization failed: %s", exc)
                    _LOG.debug("Telemetry serialization failure details", exc_info=True)

            if serialized_lines:
                try:
                    self._append_lines(serialized_lines)
                    self._increment("written_count", len(serialized_lines))
                except Exception as exc:
                    self._increment("dropped_write_failure", len(serialized_lines))
                    _LOG.warning("Telemetry spool append failed: %s", exc)
                    _LOG.debug("Telemetry spool append failure details", exc_info=True)

            for _ in batch:
                self._queue.task_done()

        self._flush_handle()
        self._close_handle()

    def _dequeue_batch(self) -> list[dict[str, Any]]:
        try:
            first_item = self._queue.get(timeout=self._flush_seconds)
        except queue.Empty:
            return []

        batch = [first_item]
        while len(batch) < self._batch_size:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return batch

    def _append_lines(self, lines: list[str]) -> None:
        with self._state_lock:
            for line in lines:
                encoded = (line + "\n").encode("utf-8")
                self._rotate_if_needed(incoming_bytes=len(encoded))
                handle = self._ensure_handle()
                handle.write(line)
                handle.write("\n")
                self._active_size_bytes += len(encoded)
            if self._handle is not None:
                self._handle.flush()

    def _ensure_handle(self) -> Any:
        if self._handle is None:
            self._spool_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            self._file_index += 1
            path = self._spool_dir / (
                f"{self._filename_prefix}-{timestamp}-{os.getpid()}-{self._file_index:04d}"
                f"{_FILE_SUFFIX}"
            )
            self._handle = path.open("a", encoding="utf-8")
            self._active_path = path
            self._active_size_bytes = 0
        return self._handle

    def _flush_handle(self) -> None:
        with self._state_lock:
            if self._handle is not None:
                self._handle.flush()

    def _close_handle(self) -> None:
        with self._state_lock:
            if self._handle is not None:
                self._handle.close()
                self._handle = None

    def _rotate_if_needed(self, *, incoming_bytes: int) -> None:
        if self._handle is None:
            return
        if self._active_size_bytes + incoming_bytes <= self._rotate_bytes:
            return
        self._handle.close()
        self._handle = None
        self._active_size_bytes = 0
        self._increment("rotated_files")
        self._sweep_retention(force=False)

    def _sweep_retention(self, *, force: bool) -> None:
        now = time.monotonic()
        if (
            not force
            and (now - self._last_retention_sweep) < _RETENTION_SWEEP_INTERVAL_SECONDS
        ):
            return
        self._last_retention_sweep = now

        try:
            cutoff_epoch = time.time() - (self._retention_days * 86400)
            deleted = 0
            pattern = f"{self._filename_prefix}-*{_FILE_SUFFIX}"
            for candidate in self._spool_dir.glob(pattern):
                if not candidate.is_file():
                    continue
                try:
                    if candidate.stat().st_mtime < cutoff_epoch:
                        candidate.unlink()
                        deleted += 1
                except OSError:
                    continue
            if deleted:
                self._increment("retention_deletes", deleted)
        except Exception as exc:
            _LOG.debug("Telemetry retention sweep failed: %s", exc, exc_info=True)


_ACTIVE_WRITER: SpoolWriter = NullSpoolWriter()
_ACTIVE_WRITER_LOCK = threading.Lock()
_DEFAULT_WRITER_INITIALIZED = False


def _build_default_writer() -> SpoolWriter:
    config = load_config()
    if not config.enabled:
        return NullSpoolWriter()
    try:
        return AsyncJsonlSpoolWriter(
            config.spool_dir,
            queue_max=config.queue_max,
            flush_ms=config.flush_ms,
            rotate_mb=config.rotate_mb,
            retention_days=config.retention_days,
        )
    except Exception as exc:
        _LOG.warning("Failed to initialize async telemetry spool writer: %s", exc)
        _LOG.debug("Telemetry spool initialization failure details", exc_info=True)
        return NullSpoolWriter()


def _close_writer_quietly(writer: Optional[SpoolWriter]) -> None:
    if writer is None:
        return
    try:
        writer.close()
    except Exception as exc:
        _LOG.debug("Telemetry writer close failed: %s", exc, exc_info=True)


def configure_spool_writer(writer: Optional[SpoolWriter]) -> SpoolWriter:
    """Set the process-wide spool writer used by ``emit``."""

    global _ACTIVE_WRITER, _DEFAULT_WRITER_INITIALIZED

    previous: Optional[SpoolWriter]
    with _ACTIVE_WRITER_LOCK:
        previous = _ACTIVE_WRITER
        _ACTIVE_WRITER = writer if writer is not None else NullSpoolWriter()
        _DEFAULT_WRITER_INITIALIZED = True

    if previous is not _ACTIVE_WRITER:
        _close_writer_quietly(previous)
    return _ACTIVE_WRITER


def get_spool_writer() -> SpoolWriter:
    """Return the process-wide spool writer, lazily initializing defaults."""

    global _ACTIVE_WRITER, _DEFAULT_WRITER_INITIALIZED

    with _ACTIVE_WRITER_LOCK:
        if not _DEFAULT_WRITER_INITIALIZED:
            _ACTIVE_WRITER = _build_default_writer()
            _DEFAULT_WRITER_INITIALIZED = True
        return _ACTIVE_WRITER


def _close_active_writer_at_exit() -> None:
    global _ACTIVE_WRITER, _DEFAULT_WRITER_INITIALIZED

    with _ACTIVE_WRITER_LOCK:
        if not _DEFAULT_WRITER_INITIALIZED:
            return
        writer = _ACTIVE_WRITER
        _ACTIVE_WRITER = NullSpoolWriter()
        _DEFAULT_WRITER_INITIALIZED = True

    _close_writer_quietly(writer)


atexit.register(_close_active_writer_at_exit)


__all__ = [
    "SpoolWriter",
    "NullSpoolWriter",
    "MemorySpoolWriter",
    "JsonlSpoolWriter",
    "AsyncSpoolStats",
    "AsyncJsonlSpoolWriter",
    "configure_spool_writer",
    "get_spool_writer",
]
