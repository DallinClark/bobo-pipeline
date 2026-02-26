"""Telemetry package public exports.

Step 2 intentionally exposes only the frozen v1.0 registry contract.
Runtime emission and storage wiring are added in later steps.
"""

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
