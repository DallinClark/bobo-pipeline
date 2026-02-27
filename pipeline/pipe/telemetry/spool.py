"""Telemetry spool writer interfaces and default implementations."""

from __future__ import annotations

import os
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol

from .contract import serialize_event


class SpoolWriter(Protocol):
    """Minimal writer protocol used by ``emit``."""

    def write_event(self, event: Mapping[str, Any]) -> None: ...

    def flush(self) -> None: ...

    def close(self) -> None: ...


class NullSpoolWriter:
    """No-op writer used by default until file spooling is wired."""

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
    """Simple append-only JSONL writer with per-process file naming."""

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
            stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            pid = str(os.getpid())
            self._path = (
                self._spool_dir / f"{self._filename_prefix}-{stamp}-{pid}.jsonl"
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


_ACTIVE_WRITER: SpoolWriter = NullSpoolWriter()


def configure_spool_writer(writer: Optional[SpoolWriter]) -> SpoolWriter:
    """Set the process-wide spool writer used by ``emit``."""

    global _ACTIVE_WRITER
    _ACTIVE_WRITER = writer if writer is not None else NullSpoolWriter()
    return _ACTIVE_WRITER


def get_spool_writer() -> SpoolWriter:
    """Return the process-wide spool writer."""

    return _ACTIVE_WRITER


__all__ = [
    "SpoolWriter",
    "NullSpoolWriter",
    "MemorySpoolWriter",
    "JsonlSpoolWriter",
    "configure_spool_writer",
    "get_spool_writer",
]
