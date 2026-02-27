"""Telemetry context helpers (host, pipeline, and session)."""

from __future__ import annotations

import contextvars
import getpass
import os
import platform
import uuid
from dataclasses import dataclass
from functools import lru_cache
from importlib import metadata
from typing import Any, Optional

_PROJECT_NAME = "sandwich-pipeline"


@dataclass(frozen=True)
class SessionContext:
    session_id: str
    action_id: Optional[str] = None


def new_session_id() -> str:
    """Return a new session identifier."""

    return str(uuid.uuid4())


def new_action_id() -> str:
    """Return a new operation/action identifier."""

    return str(uuid.uuid4())


_SESSION_CONTEXT: contextvars.ContextVar[SessionContext] = contextvars.ContextVar(
    "pipe_telemetry_session_context",
    default=SessionContext(session_id=new_session_id()),
)


def configure_session_context(
    *, session_id: Optional[str] = None, action_id: Optional[str] = None
) -> SessionContext:
    """Set session-scoped context values for current execution context."""

    current = _SESSION_CONTEXT.get()
    updated = SessionContext(
        session_id=session_id or current.session_id,
        action_id=current.action_id if action_id is None else action_id,
    )
    _SESSION_CONTEXT.set(updated)
    return updated


def get_session_context(*, action_id: Optional[str] = None) -> dict[str, str]:
    """Return current session context as telemetry payload."""

    current = _SESSION_CONTEXT.get()
    resolved_action_id = current.action_id if action_id is None else action_id
    result: dict[str, str] = {"session_id": current.session_id}
    if resolved_action_id:
        result["action_id"] = resolved_action_id
    return result


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
    "SessionContext",
    "new_session_id",
    "new_action_id",
    "configure_session_context",
    "get_session_context",
    "get_pipeline_context",
    "get_host_context",
]
