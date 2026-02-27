"""Telemetry runtime configuration.

This module centralizes all environment-driven telemetry settings so callsites
do not need to read environment variables directly.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, Mapping, Optional

TelemetryLevel = Literal["minimal", "standard", "verbose"]

_TRUE_VALUES: Final[set[str]] = {"1", "true", "yes", "on"}
_FALSE_VALUES: Final[set[str]] = {"0", "false", "no", "off"}
_LEVEL_VALUES: Final[tuple[TelemetryLevel, ...]] = ("minimal", "standard", "verbose")

_DEFAULT_ENABLED: Final[bool] = True
_DEFAULT_LEVEL: Final[TelemetryLevel] = "standard"
_DEFAULT_QUEUE_MAX: Final[int] = 5000
_DEFAULT_FLUSH_MS: Final[int] = 1000
_DEFAULT_MAX_EVENT_BYTES: Final[int] = 65536
_DEFAULT_ROTATE_MB: Final[int] = 8
_DEFAULT_RETENTION_DAYS: Final[int] = 7
_DEFAULT_INCLUDE_STACKTRACE: Final[bool] = False


def _parse_bool(name: str, raw_value: Optional[str], default: bool) -> bool:
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(
        f"Invalid boolean value for {name}: {raw_value!r}. "
        f"Expected one of {_TRUE_VALUES | _FALSE_VALUES}."
    )


def _parse_int(
    name: str, raw_value: Optional[str], default: int, *, minimum: int
) -> int:
    if raw_value is None:
        return default
    try:
        value = int(raw_value.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid integer value for {name}: {raw_value!r}") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")
    return value


def _parse_level(raw_value: Optional[str]) -> TelemetryLevel:
    if raw_value is None:
        return _DEFAULT_LEVEL
    normalized = raw_value.strip().lower()
    if normalized not in _LEVEL_VALUES:
        raise ValueError(
            f"Invalid PIPE_TELEMETRY_LEVEL value {raw_value!r}. "
            f"Expected one of {_LEVEL_VALUES}."
        )
    return normalized  # type: ignore[return-value]


def default_spool_dir(env: Optional[Mapping[str, str]] = None) -> Path:
    """Return the platform-specific default telemetry spool directory."""

    source_env = env if env is not None else os.environ

    override = source_env.get("PIPE_TELEMETRY_SPOOL_DIR")
    if override:
        return Path(override).expanduser()

    if os.name == "nt":
        local_app_data = source_env.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "sandwich-pipeline" / "telemetry"
    else:
        xdg_state_home = source_env.get("XDG_STATE_HOME")
        if xdg_state_home:
            base = Path(xdg_state_home).expanduser()
        else:
            base = Path.home() / ".local" / "state"
        return base / "sandwich-pipeline" / "telemetry"

    temp_root = (
        source_env.get("TMPDIR") or source_env.get("TEMP") or tempfile.gettempdir()
    )
    return Path(temp_root) / "sandwich-pipeline-telemetry"


@dataclass(frozen=True)
class TelemetryConfig:
    """Immutable telemetry settings resolved from environment variables."""

    enabled: bool
    level: TelemetryLevel
    spool_dir: Path
    queue_max: int
    flush_ms: int
    max_event_bytes: int
    rotate_mb: int
    retention_days: int
    include_stacktrace: bool

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "TelemetryConfig":
        source_env = env if env is not None else os.environ
        return cls(
            enabled=_parse_bool(
                "PIPE_TELEMETRY_ENABLED",
                source_env.get("PIPE_TELEMETRY_ENABLED"),
                _DEFAULT_ENABLED,
            ),
            level=_parse_level(source_env.get("PIPE_TELEMETRY_LEVEL")),
            spool_dir=default_spool_dir(source_env),
            queue_max=_parse_int(
                "PIPE_TELEMETRY_QUEUE_MAX",
                source_env.get("PIPE_TELEMETRY_QUEUE_MAX"),
                _DEFAULT_QUEUE_MAX,
                minimum=1,
            ),
            flush_ms=_parse_int(
                "PIPE_TELEMETRY_FLUSH_MS",
                source_env.get("PIPE_TELEMETRY_FLUSH_MS"),
                _DEFAULT_FLUSH_MS,
                minimum=1,
            ),
            max_event_bytes=_parse_int(
                "PIPE_TELEMETRY_MAX_EVENT_BYTES",
                source_env.get("PIPE_TELEMETRY_MAX_EVENT_BYTES"),
                _DEFAULT_MAX_EVENT_BYTES,
                minimum=1024,
            ),
            rotate_mb=_parse_int(
                "PIPE_TELEMETRY_ROTATE_MB",
                source_env.get("PIPE_TELEMETRY_ROTATE_MB"),
                _DEFAULT_ROTATE_MB,
                minimum=1,
            ),
            retention_days=_parse_int(
                "PIPE_TELEMETRY_RETENTION_DAYS",
                source_env.get("PIPE_TELEMETRY_RETENTION_DAYS"),
                _DEFAULT_RETENTION_DAYS,
                minimum=1,
            ),
            include_stacktrace=_parse_bool(
                "PIPE_TELEMETRY_INCLUDE_STACKTRACE",
                source_env.get("PIPE_TELEMETRY_INCLUDE_STACKTRACE"),
                _DEFAULT_INCLUDE_STACKTRACE,
            ),
        )


_CONFIG_CACHE: Optional[TelemetryConfig] = None


def load_config(
    *, force_reload: bool = False, env: Optional[Mapping[str, str]] = None
) -> TelemetryConfig:
    """Load telemetry config, using a process-local cache by default."""

    global _CONFIG_CACHE
    if env is not None:
        return TelemetryConfig.from_env(env)

    if _CONFIG_CACHE is None or force_reload:
        _CONFIG_CACHE = TelemetryConfig.from_env()
    return _CONFIG_CACHE


__all__ = ["TelemetryLevel", "TelemetryConfig", "default_spool_dir", "load_config"]
