"""Telemetry context helpers for correlation and canonical scope extraction."""

from __future__ import annotations

import contextlib
import contextvars
import datetime
import getpass
import os
import platform
import uuid
from dataclasses import dataclass
from functools import lru_cache
from importlib import metadata
from typing import Any, Final, Iterator, Mapping, Optional

_PROJECT_NAME = "sandwich-pipeline"
_ACTION_UNSET: Final[object] = object()

SCOPE_FIELDS: Final[tuple[str, ...]] = (
    "show",
    "sequence",
    "shot",
    "asset",
    "department",
    "task",
)

_SCOPE_FIELD_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "show": ("show", "show_code", "project", "project_code"),
    "sequence": ("sequence", "sequence_code", "seq"),
    "shot": ("shot", "shot_code", "entity", "entity_code"),
    "asset": ("asset", "asset_code", "asset_name"),
    "department": ("department", "dept", "step"),
    "task": ("task", "task_name", "content"),
}


@dataclass(frozen=True)
class SessionContext:
    session_id: str
    action_id: Optional[str] = None


@dataclass(frozen=True)
class ScopeContext:
    show: Optional[str] = None
    sequence: Optional[str] = None
    shot: Optional[str] = None
    asset: Optional[str] = None
    department: Optional[str] = None
    task: Optional[str] = None

    def as_dict(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for field_name in SCOPE_FIELDS:
            value = getattr(self, field_name)
            if value is not None:
                result[field_name] = value
        return result


def new_session_id() -> str:
    """Return a new session identifier."""

    return str(uuid.uuid4())


def new_action_id() -> str:
    """Return a new operation/action identifier."""

    return str(uuid.uuid4())


def new_event_id() -> str:
    """Return a new event identifier."""

    return str(uuid.uuid4())


def utc_now_iso() -> str:
    """Return current UTC timestamp in stable ISO-8601 format."""

    return (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _normalize_identifier(field_name: str, value: Any) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


_SESSION_CONTEXT: contextvars.ContextVar[SessionContext] = contextvars.ContextVar(
    "pipe_telemetry_session_context",
    default=SessionContext(session_id=new_session_id()),
)


def configure_session_context(
    *, session_id: Optional[str] = None, action_id: object = _ACTION_UNSET
) -> SessionContext:
    """Set session-scoped context values for current execution context."""

    current = _SESSION_CONTEXT.get()
    resolved_session_id = (
        current.session_id
        if session_id is None
        else _normalize_identifier("session_id", session_id)
    )
    if action_id is _ACTION_UNSET:
        resolved_action_id = current.action_id
    elif action_id is None:
        resolved_action_id = None
    else:
        resolved_action_id = _normalize_identifier("action_id", action_id)

    updated = SessionContext(
        session_id=resolved_session_id,
        action_id=resolved_action_id,
    )
    _SESSION_CONTEXT.set(updated)
    return updated


def begin_action(action_id: Optional[str] = None) -> str:
    """Assign and return the current action id for this execution context."""

    resolved_action_id = (
        new_action_id()
        if action_id is None
        else _normalize_identifier("action_id", action_id)
    )
    configure_session_context(action_id=resolved_action_id)
    return resolved_action_id


def clear_action_context() -> SessionContext:
    """Clear the current action id while preserving session id."""

    return configure_session_context(action_id=None)


@contextlib.contextmanager
def action_context(action_id: Optional[str] = None) -> Iterator[str]:
    """Temporarily bind one action id for multiple emits in this context."""

    current = _SESSION_CONTEXT.get()
    resolved_action_id = (
        new_action_id()
        if action_id is None
        else _normalize_identifier("action_id", action_id)
    )
    token = _SESSION_CONTEXT.set(
        SessionContext(session_id=current.session_id, action_id=resolved_action_id)
    )
    try:
        yield resolved_action_id
    finally:
        _SESSION_CONTEXT.reset(token)


def get_session_context(
    *, action_id: Optional[str] = None, ensure_action_id: bool = True
) -> dict[str, str]:
    """Return current session context as telemetry payload."""

    current = _SESSION_CONTEXT.get()
    resolved_action_id = current.action_id
    if action_id is not None:
        resolved_action_id = _normalize_identifier("action_id", action_id)
    if ensure_action_id and not resolved_action_id:
        # A deterministic fallback keeps cross-event joins explicit.
        resolved_action_id = current.session_id

    result: dict[str, str] = {"session_id": current.session_id}
    if resolved_action_id:
        result["action_id"] = resolved_action_id
    return result


def _scope_source_value(source: Any, key: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(key)
    try:
        return getattr(source, key)
    except Exception:
        return None


def _normalize_scope_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, os.PathLike):
        normalized = os.fspath(value).strip()
        return normalized or None
    if isinstance(value, Mapping):
        for nested_key in ("code", "name", "display_name", "content", "id"):
            if nested_key in value:
                nested_value = _normalize_scope_value(value.get(nested_key))
                if nested_value is not None:
                    return nested_value
        return None

    for nested_attr in ("code", "name", "display_name", "content", "id"):
        try:
            nested_value = getattr(value, nested_attr)
        except Exception:
            continue
        normalized_nested = _normalize_scope_value(nested_value)
        if normalized_nested is not None:
            return normalized_nested
    return None


def _extract_scope_from_source(source: Any) -> dict[str, str]:
    if source is None:
        return {}
    if isinstance(source, ScopeContext):
        return source.as_dict()

    result: dict[str, str] = {}
    for field_name in SCOPE_FIELDS:
        for alias in _SCOPE_FIELD_ALIASES[field_name]:
            normalized = _normalize_scope_value(_scope_source_value(source, alias))
            if normalized is not None:
                result[field_name] = normalized
                break
    return result


def _scope_context_from_mapping(scope: Mapping[str, Any]) -> ScopeContext:
    return ScopeContext(
        show=scope.get("show"),
        sequence=scope.get("sequence"),
        shot=scope.get("shot"),
        asset=scope.get("asset"),
        department=scope.get("department"),
        task=scope.get("task"),
    )


_SCOPE_CONTEXT: contextvars.ContextVar[ScopeContext] = contextvars.ContextVar(
    "pipe_telemetry_scope_context",
    default=ScopeContext(),
)


def extract_scope(*sources: Any) -> dict[str, str]:
    """Extract canonical scope keys from mappings or entity-like objects."""

    resolved: dict[str, str] = {}
    for source in sources:
        resolved.update(_extract_scope_from_source(source))
    return resolved


def configure_scope_context(*sources: Any, merge: bool = True) -> ScopeContext:
    """Configure context-local default scope for subsequent emits."""

    base_scope = _SCOPE_CONTEXT.get().as_dict() if merge else {}
    resolved_scope = extract_scope(base_scope, *sources)
    updated = _scope_context_from_mapping(resolved_scope)
    _SCOPE_CONTEXT.set(updated)
    return updated


def clear_scope_context() -> ScopeContext:
    """Clear context-local default scope."""

    cleared = ScopeContext()
    _SCOPE_CONTEXT.set(cleared)
    return cleared


def get_scope_context(*sources: Any) -> dict[str, str]:
    """Return canonical scope merged with context-local defaults."""

    base_scope = _SCOPE_CONTEXT.get().as_dict()
    if not sources:
        return dict(base_scope)
    return extract_scope(base_scope, *sources)


@lru_cache(maxsize=1)
def _pipeline_version() -> Optional[str]:
    try:
        return metadata.version(_PROJECT_NAME)
    except Exception:
        return None


def get_pipeline_context(
    *,
    module: Optional[str] = None,
    function: Optional[str] = None,
    dcc: Optional[str] = None,
) -> dict[str, Any]:
    """Return pipeline identity context for an emitted event."""

    context: dict[str, Any] = {
        "name": _PROJECT_NAME,
        "version": _pipeline_version(),
        "dcc": dcc or os.getenv("DCC"),
        "module": module,
        "function": function,
    }
    return {key: value for key, value in context.items() if value is not None}


def get_host_context() -> dict[str, Any]:
    """Return host identity context for an emitted event."""

    user: Optional[str]
    try:
        user = getpass.getuser()
    except Exception:
        user = None

    context: dict[str, Any] = {
        "hostname": platform.node() or None,
        "os": platform.system() or None,
        "os_release": platform.release() or None,
        "user": user,
        "pid": os.getpid(),
    }
    return {key: value for key, value in context.items() if value is not None}


__all__ = [
    "SCOPE_FIELDS",
    "SessionContext",
    "ScopeContext",
    "new_session_id",
    "new_action_id",
    "new_event_id",
    "utc_now_iso",
    "configure_session_context",
    "begin_action",
    "clear_action_context",
    "action_context",
    "get_session_context",
    "extract_scope",
    "configure_scope_context",
    "clear_scope_context",
    "get_scope_context",
    "get_pipeline_context",
    "get_host_context",
]
