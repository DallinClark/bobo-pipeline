"""Telemetry package public exports.

Step 3 exposes the frozen v1.0 contract, registry-backed event constants,
and the explicit emit API used for greppable instrumentation.
"""

from . import events
from .emit import build_event, emit
from .registry import (
    ERROR_CODES,
    EVENT_DEFINITIONS,
    EVENT_TYPES,
    EVENTS_BY_TYPE,
    SCHEMA_VERSION,
    STATUS_ERROR,
    STATUS_INFO,
    STATUS_SUCCESS,
    STATUS_VALUES,
    STATUS_WARNING,
    TERMINAL_STATUS_VALUES,
    EventDefinition,
    get_event_definition,
    is_known_event_type,
    list_error_codes,
    list_event_definitions,
    list_event_types,
)

__all__ = [
    "events",
    "emit",
    "build_event",
    "SCHEMA_VERSION",
    "STATUS_SUCCESS",
    "STATUS_ERROR",
    "STATUS_WARNING",
    "STATUS_INFO",
    "STATUS_VALUES",
    "TERMINAL_STATUS_VALUES",
    "ERROR_CODES",
    "EventDefinition",
    "EVENT_DEFINITIONS",
    "EVENT_TYPES",
    "EVENTS_BY_TYPE",
    "list_event_definitions",
    "list_event_types",
    "list_error_codes",
    "get_event_definition",
    "is_known_event_type",
]
