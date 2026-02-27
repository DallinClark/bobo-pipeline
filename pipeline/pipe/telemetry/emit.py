"""Telemetry emit API with greppability-focused conventions.

Design rule: keep instrumentation explicit and searchable. Callers should emit
exactly one terminal ``emit(...)`` per operation boundary.
"""

from __future__ import annotations

import datetime
import re
import uuid
from typing import Any, Mapping, Optional

from .config import load_config
from .context import get_host_context, get_pipeline_context, get_session_context
from .contract import (
    enforce_max_event_size,
    normalize_error,
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

_SNAKE_CASE_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


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
    include_stacktrace: bool = False,
) -> dict[str, Any]:
    """Build and validate a telemetry event envelope.

    This function confirms the following:
    - event type exists in the registry
    - status is allowed for the event type
    - required payload and metrics keys are present
    - payload keys are stable snake_case
    """

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
            f"Event '{event_type}' is missing required payload fields: "
            f"{missing_payload_fields}"
        )

    missing_metrics_fields = sorted(
        field
        for field in definition.required_metrics_fields
        if field not in metrics_data
    )
    if missing_metrics_fields:
        raise ValueError(
            f"Event '{event_type}' is missing required metrics fields: "
            f"{missing_metrics_fields}"
        )

    if status == STATUS_ERROR and not error_data:
        raise ValueError(
            f"Event '{event_type}' with status='error' must include error data"
        )

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

    if error_data:
        error_data = normalize_error(error_data, include_stacktrace=include_stacktrace)

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

    validate_envelope(event)

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
) -> dict[str, Any]:
    """Validate and build one telemetry event.

    Events are validated against the registry and written through the configured
    spool writer when telemetry is enabled.
    """

    config = load_config()
    event = build_event(
        event_type,
        status=status,
        payload=payload,
        metrics=metrics,
        scope=scope,
        error=error,
        action_id=action_id,
        include_stacktrace=config.include_stacktrace,
    )
    enforce_max_event_size(event, config.max_event_bytes)

    if config.enabled:
        writer = get_spool_writer()
        try:
            writer.write_event(event)
        except Exception:
            # Fail-open behavior: telemetry must not break production workflows.
            pass

    return event


__all__ = ["emit", "build_event", "is_snake_case_key"]
