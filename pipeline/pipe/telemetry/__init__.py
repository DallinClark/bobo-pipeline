"""Telemetry package public exports.

Step 4 exposes a thin public API for telemetry configuration, context,
emission, and contract inspection.
"""

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
    configure_session_context,
    get_host_context,
    get_pipeline_context,
    get_session_context,
    new_action_id,
    new_session_id,
)
from .docs import render_contract_markdown
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
    JsonlSpoolWriter,
    MemorySpoolWriter,
    NullSpoolWriter,
    configure_spool_writer,
    get_spool_writer,
)
from .storage_scan import build_storage_events, classify_path, scan_storage

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
    "configure_session_context",
    "get_session_context",
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
