"""Telemetry emit API with fail-open validation and sanitization."""

from __future__ import annotations

import datetime
import logging
import re
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .config import load_config
from .context import get_host_context, get_pipeline_context, get_session_context
from .contract import (
    EventTooLargeError,
    sanitize_event,
    truncate_event_to_size,
    validate_envelope,
)
from .registry import (
    SCHEMA_VERSION,
    STATUS_ERROR,
    STATUS_VALUES,
    StatusValue,
    get_event_definition,
)
from .spool import get_spool_writer

_LOG = logging.getLogger(__name__)

_SNAKE_CASE_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_ENVIRONMENT_KEY_PATTERN = re.compile(
    r"^(env|environment|environ|env_vars|environment_vars|environment_variables)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EmitCounters:
    """In-process telemetry emit counters for auditing/diagnostics."""

    attempted: int
    emitted: int
    dropped_invalid: int
    dropped_oversize: int
    dropped_write_failure: int


_COUNTER_LOCK = threading.Lock()
_COUNTERS = {
    "attempted": 0,
    "emitted": 0,
    "dropped_invalid": 0,
    "dropped_oversize": 0,
    "dropped_write_failure": 0,
}


def _increment_counter(name: str) -> None:
    with _COUNTER_LOCK:
        _COUNTERS[name] += 1


def get_emit_counters() -> EmitCounters:
    """Return current in-process emit counters."""

    with _COUNTER_LOCK:
        return EmitCounters(
            attempted=_COUNTERS["attempted"],
            emitted=_COUNTERS["emitted"],
            dropped_invalid=_COUNTERS["dropped_invalid"],
            dropped_oversize=_COUNTERS["dropped_oversize"],
            dropped_write_failure=_COUNTERS["dropped_write_failure"],
        )


def reset_emit_counters() -> None:
    """Reset in-process emit counters."""

    with _COUNTER_LOCK:
        for key in _COUNTERS:
            _COUNTERS[key] = 0


def _utc_now_iso() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _coerce_mapping(name: str, value: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping, got {type(value).__name__}")
    return dict(value)


def is_snake_case_key(key: str) -> bool:
    """Return True when key is stable snake_case."""

    return bool(_SNAKE_CASE_KEY_PATTERN.match(key))


def _validate_snake_case_payload_keys(
    payload: Mapping[str, Any], context: str = "payload"
) -> None:
    for key, value in payload.items():
        if not is_snake_case_key(key):
            raise ValueError(f"{context} key '{key}' must be snake_case")
        if _ENVIRONMENT_KEY_PATTERN.match(key):
            continue
        if isinstance(value, Mapping):
            _validate_snake_case_payload_keys(value, f"{context}.{key}")


def build_event(
    event_type: str,
    *,
    status: StatusValue,
    payload: Optional[Mapping[str, Any]] = None,
    metrics: Optional[Mapping[str, Any]] = None,
    scope: Optional[Mapping[str, Any]] = None,
    error: Optional[Mapping[str, Any]] = None,
    action_id: Optional[str] = None,
    pipeline: Optional[Mapping[str, Any]] = None,
    host: Optional[Mapping[str, Any]] = None,
    session: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Build one event envelope with strict contract validation."""

    definition = get_event_definition(event_type)

    if status not in STATUS_VALUES:
        raise ValueError(
            f"Invalid status '{status}' for event '{event_type}'. "
            f"Expected one of: {STATUS_VALUES}"
        )

    if status not in definition.status_values:
        raise ValueError(
            f"Status '{status}' is not allowed for event '{event_type}'. "
            f"Allowed: {definition.status_values}"
        )

    payload_data = _coerce_mapping("payload", payload)
    metrics_data = _coerce_mapping("metrics", metrics)
    scope_data = _coerce_mapping("scope", scope)
    error_data = _coerce_mapping("error", error)

    _validate_snake_case_payload_keys(payload_data)

    missing_payload_fields = sorted(
        field
        for field in definition.required_payload_fields
        if field not in payload_data
    )
    if missing_payload_fields:
        raise ValueError(
            f"Event '{event_type}' is missing required payload fields: {missing_payload_fields}"
        )

    missing_metrics_fields = sorted(
        field
        for field in definition.required_metrics_fields
        if field not in metrics_data
    )
    if missing_metrics_fields:
        raise ValueError(
            f"Event '{event_type}' is missing required metrics fields: {missing_metrics_fields}"
        )

    if status == STATUS_ERROR and not error_data:
        raise ValueError(f"Event '{event_type}' with status='error' must include error")

    pipeline_data = _coerce_mapping("pipeline", pipeline)
    host_data = _coerce_mapping("host", host)
    session_data = _coerce_mapping("session", session)

    if not pipeline_data:
        pipeline_data = get_pipeline_context()
    if not host_data:
        host_data = get_host_context()
    if not session_data:
        session_data = get_session_context(action_id=action_id)
    elif action_id and "action_id" not in session_data:
        session_data["action_id"] = action_id

    event: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "occurred_at_utc": _utc_now_iso(),
        "status": status,
        "pipeline": pipeline_data,
        "host": host_data,
        "session": session_data,
        "payload": payload_data,
    }
    if metrics_data:
        event["metrics"] = metrics_data
    if scope_data:
        event["scope"] = scope_data
    if error_data:
        event["error"] = error_data
    return event


def emit(
    event_type: str,
    *,
    status: StatusValue,
    payload: Optional[Mapping[str, Any]] = None,
    metrics: Optional[Mapping[str, Any]] = None,
    scope: Optional[Mapping[str, Any]] = None,
    error: Optional[Mapping[str, Any]] = None,
    action_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Emit telemetry in fail-open mode.

    Invalid events are dropped/counted/logged. Exceptions are not raised.
    """

    _increment_counter("attempted")
    config = load_config()

    try:
        definition = get_event_definition(event_type)
        event = build_event(
            event_type,
            status=status,
            payload=payload,
            metrics=metrics,
            scope=scope,
            error=error,
            action_id=action_id,
        )

        sanitized_event = sanitize_event(
            event,
            include_stacktrace=config.include_stacktrace,
            max_string_chars=max(256, min(2048, config.max_event_bytes // 8)),
        )
        sized_event = truncate_event_to_size(
            sanitized_event,
            max_event_bytes=config.max_event_bytes,
            required_payload_fields=definition.required_payload_fields,
        )
        validate_envelope(sized_event)
    except EventTooLargeError as exc:
        _increment_counter("dropped_oversize")
        _LOG.warning("Dropped telemetry event '%s': %s", event_type, exc)
        _LOG.debug("Telemetry drop details", exc_info=True)
        return None
    except ValueError as exc:
        _increment_counter("dropped_invalid")
        _LOG.warning("Dropped telemetry event '%s': %s", event_type, exc)
        _LOG.debug("Telemetry drop details", exc_info=True)
        return None
    except Exception as exc:
        _increment_counter("dropped_invalid")
        _LOG.warning("Dropped telemetry event '%s': %s", event_type, exc)
        _LOG.debug("Telemetry drop details", exc_info=True)
        return None

    if config.enabled:
        writer = get_spool_writer()
        try:
            writer.write_event(sized_event)
        except Exception as exc:
            _increment_counter("dropped_write_failure")
            _LOG.warning("Telemetry writer failure for '%s': %s", event_type, exc)
            _LOG.debug("Telemetry writer failure details", exc_info=True)
            return sized_event

    _increment_counter("emitted")
    return sized_event


__all__ = [
    "EmitCounters",
    "emit",
    "build_event",
    "is_snake_case_key",
    "get_emit_counters",
    "reset_emit_counters",
]
