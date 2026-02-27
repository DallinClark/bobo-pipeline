"""Telemetry package public exports.

Step 4 exposes a thin public API for telemetry configuration, context,
emission, and contract inspection.
"""

from typing import Any

from . import events
from .config import (
    PlatformFlavor,
    TelemetryConfig,
    TelemetryLevel,
    default_spool_dir,
    detect_platform_flavor,
    load_config,
)
from .context import (
    SCOPE_FIELDS,
    ScopeContext,
    action_context,
    begin_action,
    clear_action_context,
    clear_scope_context,
    configure_scope_context,
    configure_session_context,
    extract_scope,
    get_host_context,
    get_pipeline_context,
    get_scope_context,
    get_session_context,
    new_action_id,
    new_event_id,
    new_session_id,
    utc_now_iso,
)
from .emit import (
    EmitCounters,
    build_event,
    emit,
    get_emit_counters,
    reset_emit_counters,
)
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
from .spool import (
    AsyncJsonlSpoolWriter,
    AsyncSpoolStats,
    JsonlSpoolWriter,
    MemorySpoolWriter,
    NullSpoolWriter,
    configure_spool_writer,
    get_spool_writer,
)


def render_contract_markdown() -> str:
    """Return telemetry contract markdown generated from the registry."""

    from .docs import render_contract_markdown as _render_contract_markdown

    return _render_contract_markdown()


def scan_storage(*args: Any, **kwargs: Any) -> Any:
    """Proxy to ``pipe.telemetry.storage_scan.scan_storage``."""

    from .storage_scan import scan_storage as _scan_storage

    return _scan_storage(*args, **kwargs)


def build_storage_events(*args: Any, **kwargs: Any) -> Any:
    """Proxy to ``pipe.telemetry.storage_scan.build_storage_events``."""

    from .storage_scan import build_storage_events as _build_storage_events

    return _build_storage_events(*args, **kwargs)


def classify_path(*args: Any, **kwargs: Any) -> Any:
    """Proxy to ``pipe.telemetry.storage_scan.classify_path``."""

    from .storage_scan import classify_path as _classify_path

    return _classify_path(*args, **kwargs)


__all__ = [
    "events",
    "TelemetryConfig",
    "TelemetryLevel",
    "PlatformFlavor",
    "detect_platform_flavor",
    "default_spool_dir",
    "load_config",
    "new_session_id",
    "new_action_id",
    "new_event_id",
    "utc_now_iso",
    "configure_session_context",
    "begin_action",
    "clear_action_context",
    "action_context",
    "get_session_context",
    "SCOPE_FIELDS",
    "ScopeContext",
    "extract_scope",
    "configure_scope_context",
    "clear_scope_context",
    "get_scope_context",
    "get_host_context",
    "get_pipeline_context",
    "emit",
    "build_event",
    "EmitCounters",
    "get_emit_counters",
    "reset_emit_counters",
    "NullSpoolWriter",
    "MemorySpoolWriter",
    "JsonlSpoolWriter",
    "AsyncSpoolStats",
    "AsyncJsonlSpoolWriter",
    "configure_spool_writer",
    "get_spool_writer",
    "render_contract_markdown",
    "scan_storage",
    "build_storage_events",
    "classify_path",
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
