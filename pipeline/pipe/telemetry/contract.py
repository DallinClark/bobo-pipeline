"""Telemetry envelope and serialization helpers."""

from __future__ import annotations

import json
from typing import Any, Final, Mapping

from .registry import SCHEMA_VERSION, STATUS_ERROR, get_event_definition

REQUIRED_ENVELOPE_KEYS: Final[tuple[str, ...]] = (
    "schema_version",
    "event_id",
    "event_type",
    "occurred_at_utc",
    "status",
    "payload",
)

REQUIRED_ERROR_KEYS: Final[tuple[str, ...]] = ("code", "message")


def compact_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy without ``None`` values."""

    return {key: value for key, value in data.items() if value is not None}


def validate_envelope(event: Mapping[str, Any]) -> None:
    """Validate required top-level envelope keys and schema version."""

    missing = [key for key in REQUIRED_ENVELOPE_KEYS if key not in event]
    if missing:
        raise ValueError(f"Event envelope missing required fields: {missing}")

    if event["schema_version"] != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported schema version {event['schema_version']!r}; "
            f"expected {SCHEMA_VERSION!r}"
        )

    event_type = event["event_type"]
    status = event["status"]
    definition = get_event_definition(event_type)
    if status not in definition.status_values:
        raise ValueError(
            f"Status '{status}' not allowed for event '{event_type}'. "
            f"Allowed: {definition.status_values}"
        )

    if status == STATUS_ERROR:
        error = event.get("error")
        if not isinstance(error, Mapping):
            raise ValueError(
                f"Event '{event_type}' status='error' requires error object"
            )
        missing_error_keys = [key for key in REQUIRED_ERROR_KEYS if key not in error]
        if missing_error_keys:
            raise ValueError(
                f"Event '{event_type}' error object missing required fields: "
                f"{missing_error_keys}"
            )
        error_code = str(error.get("code"))
        if definition.error_codes and error_code not in definition.error_codes:
            raise ValueError(
                f"Event '{event_type}' uses unsupported error code '{error_code}'. "
                f"Allowed: {definition.error_codes}"
            )


def normalize_error(
    error: Mapping[str, Any], *, include_stacktrace: bool = False
) -> dict[str, Any]:
    """Return a normalized error payload with stable keys."""

    normalized: dict[str, Any] = compact_mapping(
        {
            "code": error.get("code"),
            "message": error.get("message"),
            "exception_type": error.get("exception_type"),
            "stacktrace": error.get("stacktrace") if include_stacktrace else None,
        }
    )
    missing = [key for key in REQUIRED_ERROR_KEYS if key not in normalized]
    if missing:
        raise ValueError(f"Error payload missing required keys: {missing}")
    return normalized


def serialize_event(event: Mapping[str, Any]) -> str:
    """Serialize event deterministically for disk/appended transport."""

    return json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def event_size_bytes(event: Mapping[str, Any]) -> int:
    """Return serialized event size in bytes."""

    return len(serialize_event(event).encode("utf-8"))


def enforce_max_event_size(event: Mapping[str, Any], max_event_bytes: int) -> None:
    """Raise if serialized event exceeds configured maximum size."""

    size = event_size_bytes(event)
    if size > max_event_bytes:
        raise ValueError(
            f"Event size {size} exceeds PIPE_TELEMETRY_MAX_EVENT_BYTES={max_event_bytes}"
        )


__all__ = [
    "REQUIRED_ENVELOPE_KEYS",
    "REQUIRED_ERROR_KEYS",
    "compact_mapping",
    "validate_envelope",
    "normalize_error",
    "serialize_event",
    "event_size_bytes",
    "enforce_max_event_size",
]
