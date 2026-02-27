"""Render diagnostics harvester for ``render.stats.summary`` telemetry.

This module scans Tractor/Husk/RenderMan artifacts produced by Tractor LOP
submission and emits one aggregated summary per render job.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from . import events
from .config import load_config
from .context import extract_scope, new_action_id
from .contract import serialize_event
from .emit import emit
from .registry import ERROR_RENDER_STATS_HARVEST_FAILED, STATUS_ERROR, STATUS_SUCCESS

DEFAULT_POLL_INTERVAL_SECONDS = 900
DEFAULT_LOOKBACK_HOURS = 72
DEFAULT_SETTLE_SECONDS = 300
DEFAULT_LOG_TAIL_BYTES = 262_144

_STATE_DIRNAME = "state"
_STATE_FILENAME = "render_harvest_state.json"

_FRAME_TOKEN_PATTERN = re.compile(
    r"(?:^|[_\-])f(?P<frame>\d{1,8})(?:[_\-]|$)", re.IGNORECASE
)
_TILE_TOKEN_PATTERN = re.compile(
    r"(?:^|[_\-])t(?P<tile>\d{1,8})(?:[_\-]|$)", re.IGNORECASE
)

_FAILURE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Traceback \(most recent call last\):"),
    re.compile(r"\bfatal\b", re.IGNORECASE),
    re.compile(r"\bsegmentation fault\b", re.IGNORECASE),
    re.compile(r"\b(?:render|husk).{0,40}\b(?:failed|failure)\b", re.IGNORECASE),
    re.compile(r"\berror:\b", re.IGNORECASE),
    re.compile(r"\blicense.{0,40}\b(?:failed|error)\b", re.IGNORECASE),
    re.compile(r"\bcommand.+exited.+status\b", re.IGNORECASE),
)
_FAILURE_FALSE_POSITIVE = re.compile(r"\b0\s+errors?\b", re.IGNORECASE)

_LOG_FRAME_TIME_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:elapsed(?:\s+time)?|render(?:ing)?\s+time|time\s+to\s+render)"
        r"[^0-9]{0,32}(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>ms|msec|milliseconds|s|sec|secs|seconds|m|min|mins|minutes)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bframe\s+\d+\b.{0,80}\b(?:in|took)\b[^0-9]{0,12}"
        r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>ms|msec|milliseconds|s|sec|secs|seconds|m|min|mins|minutes)\b",
        re.IGNORECASE,
    ),
)

_LOG_MEMORY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:peak|max(?:imum)?)\s+(?:memory|rss|resident(?:\s+set)?)"
        r"[^0-9]{0,20}(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>kb|mb|gb|tb|bytes?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:memory|rss)\b.{0,32}\b(?:peak|max)\b[^0-9]{0,20}"
        r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>kb|mb|gb|tb|bytes?)\b",
        re.IGNORECASE,
    ),
)

_DIRECT_QUEUE_WAIT_KEYS: tuple[tuple[str, ...], ...] = (
    ("queue", "wait"),
    ("queuewait",),
    ("wait", "ms"),
)

_DIRECT_RETRY_KEYS: tuple[tuple[str, ...], ...] = (
    ("retry", "count"),
    ("retries",),
    ("attempt", "count"),
)

_DIRECT_FAILED_KEYS: tuple[tuple[str, ...], ...] = (
    ("failed", "frame"),
    ("failedframes",),
    ("frame", "failed"),
)

_SECONDS_HINTS = ("sec", "second", "seconds")
_MILLISECONDS_HINTS = ("ms", "msec", "millisecond", "milliseconds")
_MINUTES_HINTS = ("min", "mins", "minute", "minutes")


@dataclass(frozen=True)
class RenderJobCandidate:
    """Candidate render job discovered from Tractor submission telemetry."""

    submission_path: Path
    submission: dict[str, Any]
    job_directory: Path
    job_id: str
    renderer: str
    service: str
    priority: int
    frame_start: int
    frame_end: int
    frame_step: int
    tile_count: int
    expected_frames: int
    scope: dict[str, str]


@dataclass(frozen=True)
class RenderArtifacts:
    """Resolved artifact paths used for one render summary."""

    stats_files: tuple[Path, ...]
    stderr_logs: tuple[Path, ...]
    tractor_json_files: tuple[Path, ...]
    latest_mtime: float
    has_render_signal: bool


def _safe_text(value: Any, fallback: str = "unknown") -> str:
    if value is None:
        return fallback
    normalized = str(value).strip()
    return normalized or fallback


def _normalize_key(value: str) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def _to_int(value: Any, *, fallback: int = 0, minimum: int = 0) -> int:
    try:
        resolved = int(value)
    except Exception:
        resolved = int(fallback)
    return max(minimum, resolved)


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _parse_iso_or_epoch(value: Any) -> Optional[float]:
    numeric = _to_float(value)
    if numeric is not None:
        if numeric > 1_000_000_000_000:
            return numeric / 1000.0
        if numeric > 0:
            return numeric
        return None

    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None

    iso = raw
    if iso.endswith("Z"):
        iso = iso[:-1] + "+00:00"
    try:
        parsed = _dt.datetime.fromisoformat(iso)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.timestamp()


def _frame_count(start: int, end: int, step: int) -> int:
    resolved_step = max(1, int(step))
    a = int(start)
    b = int(end)
    if b < a:
        a, b = b, a
    return ((b - a) // resolved_step) + 1


def _percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(float(item) for item in values)
    if len(sorted_values) == 1:
        return sorted_values[0]

    rank = (len(sorted_values) - 1) * min(max(p, 0.0), 1.0)
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return sorted_values[low]
    weight = rank - low
    return sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight


def _iter_leaf_items(
    data: Any, path: tuple[str, ...] = ()
) -> Iterable[tuple[tuple[str, ...], Any]]:
    if isinstance(data, Mapping):
        for key, value in data.items():
            yield from _iter_leaf_items(value, path + (str(key),))
        return
    if isinstance(data, list):
        for index, value in enumerate(data):
            yield from _iter_leaf_items(value, path + (str(index),))
        return
    yield path, data


def _contains_tokens(normalized: str, tokens: Sequence[str]) -> bool:
    return all(token in normalized for token in tokens)


def _unit_scale_from_path(normalized_path: str, raw_value: float) -> float:
    if any(token in normalized_path for token in _MILLISECONDS_HINTS):
        return 1.0
    if any(token in normalized_path for token in _SECONDS_HINTS):
        return 1000.0
    if any(token in normalized_path for token in _MINUTES_HINTS):
        return 60_000.0
    # Unqualified frame timings are most often in seconds in renderer logs/stats.
    if raw_value <= 600.0:
        return 1000.0
    return 1.0


def _memory_scale_from_path(normalized_path: str, raw_value: float) -> float:
    if "tb" in normalized_path:
        return 1024.0
    if "gb" in normalized_path or "gib" in normalized_path:
        return 1.0
    if "mb" in normalized_path or "mib" in normalized_path:
        return 1.0 / 1024.0
    if "kb" in normalized_path or "kib" in normalized_path:
        return 1.0 / (1024.0 * 1024.0)
    if "byte" in normalized_path or normalized_path.endswith("b"):
        return 1.0 / (1024.0 * 1024.0 * 1024.0)
    if raw_value > 1_000_000_000.0:
        return 1.0 / (1024.0 * 1024.0 * 1024.0)
    if raw_value > 1024.0:
        return 1.0 / 1024.0
    return 1.0


def _extract_frame_time_ms_from_stats(data: Mapping[str, Any]) -> Optional[float]:
    best_score = -1
    best_value_ms: Optional[float] = None

    for path, value in _iter_leaf_items(data):
        numeric = _to_float(value)
        if numeric is None or numeric <= 0:
            continue

        normalized_path = "".join(_normalize_key(part) for part in path)
        score = 0
        if _contains_tokens(normalized_path, ("frame", "time")):
            score += 80
        elif _contains_tokens(normalized_path, ("render", "time")):
            score += 70
        elif "elapsed" in normalized_path or "duration" in normalized_path:
            score += 60
        elif "time" in normalized_path:
            score += 40
        else:
            continue

        if "cpu" in normalized_path and "frame" not in normalized_path:
            score -= 10
        if "memory" in normalized_path:
            score -= 30

        value_ms = numeric * _unit_scale_from_path(normalized_path, numeric)
        if value_ms <= 0 or value_ms > 86_400_000:
            continue

        if score > best_score:
            best_score = score
            best_value_ms = value_ms
        elif score == best_score and best_value_ms is not None:
            best_value_ms = max(best_value_ms, value_ms)

    return best_value_ms


def _extract_memory_peak_gb_from_stats(data: Mapping[str, Any]) -> Optional[float]:
    best_score = -1
    best_value_gb: Optional[float] = None

    for path, value in _iter_leaf_items(data):
        numeric = _to_float(value)
        if numeric is None or numeric <= 0:
            continue

        normalized_path = "".join(_normalize_key(part) for part in path)
        score = 0
        if "memory" in normalized_path:
            score += 70
        if "rss" in normalized_path or "resident" in normalized_path:
            score += 50
        if "peak" in normalized_path or "max" in normalized_path:
            score += 60
        if "frame" in normalized_path and "memory" not in normalized_path:
            score -= 20
        if score < 60:
            continue

        value_gb = numeric * _memory_scale_from_path(normalized_path, numeric)
        if value_gb <= 0 or value_gb > 16_384:
            continue

        if score > best_score:
            best_score = score
            best_value_gb = value_gb
        elif score == best_score and best_value_gb is not None:
            best_value_gb = max(best_value_gb, value_gb)

    return best_value_gb


def _parse_frame_id(path: Path) -> Optional[int]:
    normalized_name = path.stem
    match = _FRAME_TOKEN_PATTERN.search(normalized_name)
    if not match:
        return None
    return _to_int(match.group("frame"), fallback=0, minimum=0)


def _parse_tile_id(path: Path) -> Optional[int]:
    normalized_name = path.stem
    match = _TILE_TOKEN_PATTERN.search(normalized_name)
    if not match:
        return None
    return _to_int(match.group("tile"), fallback=0, minimum=0)


def _load_json_dict(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return raw


def _read_log_tail(path: Path, max_bytes: int = DEFAULT_LOG_TAIL_BYTES) -> str:
    size = path.stat().st_size
    if size <= 0:
        return ""
    with path.open("rb") as handle:
        if size > max_bytes:
            handle.seek(size - max_bytes)
        raw = handle.read()
    return raw.decode("utf-8", errors="replace")


def _duration_ms_from_unit(value: float, unit: str) -> float:
    normalized = _normalize_key(unit)
    if normalized in ("ms", "msec", "millisecond", "milliseconds"):
        return value
    if normalized in ("s", "sec", "secs", "second", "seconds"):
        return value * 1000.0
    if normalized in ("m", "min", "mins", "minute", "minutes"):
        return value * 60_000.0
    return value


def _memory_gb_from_unit(value: float, unit: str) -> float:
    normalized = _normalize_key(unit)
    if normalized in ("tb",):
        return value * 1024.0
    if normalized in ("gb",):
        return value
    if normalized in ("mb",):
        return value / 1024.0
    if normalized in ("kb",):
        return value / (1024.0 * 1024.0)
    if normalized in ("byte", "bytes", "b"):
        return value / (1024.0 * 1024.0 * 1024.0)
    return value


def _parse_log_metrics(text: str) -> tuple[list[float], Optional[float], bool]:
    frame_times_ms: list[float] = []
    memory_peak_gb: Optional[float] = None
    has_failure = False

    for line in text.splitlines():
        if _FAILURE_FALSE_POSITIVE.search(line):
            pass
        elif any(pattern.search(line) for pattern in _FAILURE_PATTERNS):
            has_failure = True

        for pattern in _LOG_FRAME_TIME_PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            value = _to_float(match.group("value"))
            if value is None or value <= 0:
                continue
            unit = match.group("unit")
            duration_ms = _duration_ms_from_unit(value, unit)
            if 0 < duration_ms <= 86_400_000:
                frame_times_ms.append(duration_ms)
            break

        for pattern in _LOG_MEMORY_PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            value = _to_float(match.group("value"))
            if value is None or value <= 0:
                continue
            unit = match.group("unit")
            value_gb = _memory_gb_from_unit(value, unit)
            if value_gb <= 0 or value_gb > 16_384:
                continue
            if memory_peak_gb is None:
                memory_peak_gb = value_gb
            else:
                memory_peak_gb = max(memory_peak_gb, value_gb)
            break

    return frame_times_ms, memory_peak_gb, has_failure


def _iter_recent_submission_files(
    roots: Iterable[Path],
    *,
    lookback_hours: int,
) -> Iterable[Path]:
    cutoff = time.time() - max(1, lookback_hours) * 3600.0
    for root in roots:
        resolved_root = root.expanduser()
        if not resolved_root.exists() or not resolved_root.is_dir():
            continue

        for dirpath, _, filenames in os.walk(resolved_root):
            directory = Path(dirpath)
            if directory.name != "tractor" or directory.parent.name != "telemetry":
                continue

            for filename in filenames:
                if not filename.endswith("_submission.json"):
                    continue
                submission_path = directory / filename
                try:
                    if submission_path.stat().st_mtime < cutoff:
                        continue
                except OSError:
                    continue
                yield submission_path


def _scope_from_env() -> dict[str, str]:
    return extract_scope(
        {
            "show": os.getenv("SHOW"),
            "sequence": os.getenv("SEQUENCE"),
            "shot": os.getenv("SHOT"),
            "asset": os.getenv("ASSET"),
            "department": os.getenv("DEPARTMENT"),
            "task": os.getenv("TASK"),
        }
    )


def _parse_candidate(
    submission_path: Path, base_scope: Mapping[str, Any]
) -> Optional[RenderJobCandidate]:
    submission = _load_json_dict(submission_path)
    if not submission:
        return None

    job_id = _safe_text(submission.get("jid"), fallback="")
    if not job_id:
        return None

    directories = submission.get("job_directories")
    job_directory: Optional[Path] = None
    if isinstance(directories, list):
        for directory in directories:
            raw_path = _safe_text(directory, fallback="").strip()
            if not raw_path:
                continue
            candidate = Path(raw_path).expanduser()
            if str(candidate).strip():
                job_directory = candidate
                break
    if job_directory is None:
        # .../<job_dir>/telemetry/tractor/<submission>.json
        job_directory = submission_path.parent.parent.parent

    render_intent = submission.get("render_intent")
    if not isinstance(render_intent, Mapping):
        render_intent = {}

    frame_start = _to_int(render_intent.get("frame_start"), fallback=1, minimum=0)
    frame_end = _to_int(render_intent.get("frame_end"), fallback=frame_start, minimum=0)
    frame_step = _to_int(render_intent.get("frame_step"), fallback=1, minimum=1)
    if frame_end < frame_start:
        frame_start, frame_end = frame_end, frame_start

    tile_count = _to_int(render_intent.get("tile_count"), fallback=1, minimum=1)
    expected_frames = _frame_count(frame_start, frame_end, frame_step)

    scope = extract_scope(_scope_from_env(), base_scope, submission, render_intent)

    return RenderJobCandidate(
        submission_path=submission_path,
        submission=submission,
        job_directory=job_directory,
        job_id=job_id,
        renderer=_safe_text(render_intent.get("renderer")),
        service=_safe_text(render_intent.get("service")),
        priority=_to_int(
            submission.get("job", {}).get("priority")
            if isinstance(submission.get("job"), Mapping)
            else submission.get("priority"),
            fallback=0,
            minimum=0,
        ),
        frame_start=frame_start,
        frame_end=frame_end,
        frame_step=frame_step,
        tile_count=tile_count,
        expected_frames=expected_frames,
        scope=scope,
    )


def _discover_render_manifest_files(job_directory: Path) -> tuple[Path, ...]:
    manifest_dir = job_directory / "telemetry" / "manifest"
    if not manifest_dir.is_dir():
        return ()
    manifests: list[Path] = []
    for path in sorted(manifest_dir.glob("*_render_task.json")):
        if path.is_file():
            manifests.append(path)
    return tuple(manifests)


def _extract_parent_directory(template: str) -> Optional[Path]:
    cleaned = _safe_text(template, fallback="").strip()
    if not cleaned:
        return None
    return Path(cleaned).expanduser().parent


def _discover_stats_files(candidate: RenderJobCandidate) -> tuple[Path, ...]:
    directories: set[Path] = set()
    fallback_dir = candidate.job_directory / "telemetry" / "renderman"
    if fallback_dir.is_dir():
        directories.add(fallback_dir)

    for manifest_path in _discover_render_manifest_files(candidate.job_directory):
        try:
            manifest = _load_json_dict(manifest_path)
        except Exception:
            continue
        rm_stats = manifest.get("renderman_stats")
        if not isinstance(rm_stats, Mapping):
            continue
        if not bool(rm_stats.get("enabled", False)):
            continue
        parent = _extract_parent_directory(
            _safe_text(rm_stats.get("json_template"), fallback="")
        )
        if parent is not None and parent.is_dir():
            directories.add(parent)

    stats_files: set[Path] = set()
    for directory in directories:
        for path in directory.rglob("*.stats.json"):
            if path.is_file():
                stats_files.add(path)

    return tuple(sorted(stats_files))


def _discover_stderr_logs(candidate: RenderJobCandidate) -> tuple[Path, ...]:
    directories: set[Path] = set()
    fallback_dir = candidate.job_directory / "telemetry" / "husk"
    if fallback_dir.is_dir():
        directories.add(fallback_dir)

    for manifest_path in _discover_render_manifest_files(candidate.job_directory):
        try:
            manifest = _load_json_dict(manifest_path)
        except Exception:
            continue
        husk_data = manifest.get("husk")
        if not isinstance(husk_data, Mapping):
            continue
        parent = _extract_parent_directory(
            _safe_text(husk_data.get("stderr_template"), fallback="")
        )
        if parent is not None and parent.is_dir():
            directories.add(parent)

    stderr_logs: set[Path] = set()
    for directory in directories:
        for path in directory.rglob("*.stderr.log"):
            if path.is_file():
                stderr_logs.add(path)
    return tuple(sorted(stderr_logs))


def _discover_tractor_json_files(candidate: RenderJobCandidate) -> tuple[Path, ...]:
    tractor_dir = candidate.submission_path.parent
    candidates: set[Path] = set()

    for key in ("job_details_file", "job_dump_file", "queue_stats_file"):
        value = candidate.submission.get(key)
        if not value:
            continue
        path = tractor_dir / _safe_text(value, fallback="")
        if path.is_file():
            candidates.add(path)

    prefix = candidate.submission_path.name.replace("_submission.json", "")
    for suffix in ("_job_details.json", "_job_dump.json", "_queue_stats.json"):
        path = tractor_dir / f"{prefix}{suffix}"
        if path.is_file():
            candidates.add(path)

    return tuple(sorted(candidates))


def _collect_artifacts(candidate: RenderJobCandidate) -> RenderArtifacts:
    stats_files = _discover_stats_files(candidate)
    stderr_logs = _discover_stderr_logs(candidate)
    tractor_json_files = _discover_tractor_json_files(candidate)

    latest_mtime = 0.0
    for path in (
        candidate.submission_path,
        *stats_files,
        *stderr_logs,
        *tractor_json_files,
    ):
        try:
            latest_mtime = max(latest_mtime, path.stat().st_mtime)
        except OSError:
            continue

    return RenderArtifacts(
        stats_files=stats_files,
        stderr_logs=stderr_logs,
        tractor_json_files=tractor_json_files,
        latest_mtime=latest_mtime,
        has_render_signal=bool(stats_files or stderr_logs),
    )


def _direct_numeric_lookup(
    data: Any, token_groups: Sequence[Sequence[str]]
) -> Optional[int]:
    for path, value in _iter_leaf_items(data):
        numeric = _to_float(value)
        if numeric is None:
            continue
        normalized_path = "".join(_normalize_key(part) for part in path)
        for tokens in token_groups:
            if _contains_tokens(normalized_path, tokens):
                return max(0, int(round(numeric)))
    return None


def _extract_queue_wait_ms(data: Any) -> int:
    direct = _direct_numeric_lookup(data, _DIRECT_QUEUE_WAIT_KEYS)
    if direct is not None:
        # If a key is explicitly in seconds, convert.
        for path, value in _iter_leaf_items(data):
            numeric = _to_float(value)
            if numeric is None:
                continue
            normalized_path = "".join(_normalize_key(part) for part in path)
            if "queuewait" in normalized_path and "sec" in normalized_path:
                return max(0, int(round(numeric * 1000.0)))
            if "queuewait" in normalized_path and "ms" in normalized_path:
                return max(0, int(round(numeric)))
        return direct

    queued_times: list[float] = []
    started_times: list[float] = []
    for path, value in _iter_leaf_items(data):
        normalized_path = "".join(_normalize_key(part) for part in path)
        ts = _parse_iso_or_epoch(value)
        if ts is None:
            continue
        if (
            ("queue" in normalized_path and "time" in normalized_path)
            or ("spool" in normalized_path and "time" in normalized_path)
            or ("submit" in normalized_path and "time" in normalized_path)
        ):
            queued_times.append(ts)
        elif ("start" in normalized_path and "time" in normalized_path) or (
            "run" in normalized_path and "time" in normalized_path
        ):
            started_times.append(ts)

    if not queued_times or not started_times:
        return 0
    queued_at = min(queued_times)
    started_at = min(started_times)
    if started_at <= queued_at:
        return 0
    return int(round((started_at - queued_at) * 1000.0))


def _extract_retry_count(data: Any) -> Optional[int]:
    best: Optional[int] = _direct_numeric_lookup(data, _DIRECT_RETRY_KEYS)
    if best is not None:
        return best

    retries = 0
    for path, value in _iter_leaf_items(data):
        numeric = _to_float(value)
        if numeric is None or numeric < 0:
            continue
        normalized_path = "".join(_normalize_key(part) for part in path)
        if "retry" not in normalized_path:
            continue
        if "retryrc" in normalized_path:
            continue
        retries = max(retries, int(round(numeric)))
    if retries > 0:
        return retries
    return None


def _extract_failed_frames(data: Any) -> Optional[int]:
    return _direct_numeric_lookup(data, _DIRECT_FAILED_KEYS)


def _build_payload_defaults(candidate: RenderJobCandidate) -> dict[str, Any]:
    return {
        "job_id": candidate.job_id,
        "renderer": candidate.renderer,
        "service": candidate.service,
        "priority": candidate.priority,
        "total_frames": max(0, candidate.expected_frames),
        "failed_frames": 0,
        "frame_time_p50_ms": 0.0,
        "frame_time_p90_ms": 0.0,
        "memory_peak_gb": 0.0,
        "retry_count_total": 0,
        "queue_wait_ms": 0,
    }


def _summarize_candidate(
    candidate: RenderJobCandidate, artifacts: RenderArtifacts
) -> dict[str, Any]:
    payload = _build_payload_defaults(candidate)

    stats_times_by_frame: dict[int, list[float]] = {}
    log_times_by_frame: dict[int, list[float]] = {}
    unscoped_time_samples: list[float] = []

    stats_attempts: dict[tuple[int, int], int] = {}
    log_attempts: dict[tuple[int, int], int] = {}

    memory_peak_gb = 0.0
    failed_frames: set[int] = set()
    unscoped_failures = 0

    for stats_file in artifacts.stats_files:
        try:
            stats_data = _load_json_dict(stats_file)
        except Exception:
            continue

        frame_id = _parse_frame_id(stats_file)
        tile_id = _parse_tile_id(stats_file) or 0

        frame_time_ms = _extract_frame_time_ms_from_stats(stats_data)
        if frame_time_ms is not None:
            if frame_id is not None:
                stats_times_by_frame.setdefault(frame_id, []).append(frame_time_ms)
            else:
                unscoped_time_samples.append(frame_time_ms)

        memory_candidate = _extract_memory_peak_gb_from_stats(stats_data)
        if memory_candidate is not None:
            memory_peak_gb = max(memory_peak_gb, memory_candidate)

        if frame_id is not None:
            key = (frame_id, tile_id)
            stats_attempts[key] = stats_attempts.get(key, 0) + 1

    for stderr_log in artifacts.stderr_logs:
        frame_id = _parse_frame_id(stderr_log)
        tile_id = _parse_tile_id(stderr_log) or 0
        try:
            text = _read_log_tail(stderr_log)
        except Exception:
            continue

        log_times, log_memory_peak, has_failure = _parse_log_metrics(text)
        if log_memory_peak is not None:
            memory_peak_gb = max(memory_peak_gb, log_memory_peak)

        for duration_ms in log_times:
            if frame_id is not None:
                log_times_by_frame.setdefault(frame_id, []).append(duration_ms)
            else:
                unscoped_time_samples.append(duration_ms)

        if frame_id is not None:
            key = (frame_id, tile_id)
            log_attempts[key] = log_attempts.get(key, 0) + 1

        if has_failure:
            if frame_id is not None:
                failed_frames.add(frame_id)
            else:
                unscoped_failures += 1

    # Queue wait / retries / failed frame hints from Tractor JSON snapshots when available.
    queue_wait_ms_candidates: list[int] = []
    retry_candidates: list[int] = []
    failed_frame_candidates: list[int] = []
    for tractor_json_file in artifacts.tractor_json_files:
        try:
            tractor_data = _load_json_dict(tractor_json_file)
        except Exception:
            continue

        queue_wait_ms_candidates.append(_extract_queue_wait_ms(tractor_data))
        retry_value = _extract_retry_count(tractor_data)
        if retry_value is not None:
            retry_candidates.append(retry_value)
        failed_value = _extract_failed_frames(tractor_data)
        if failed_value is not None:
            failed_frame_candidates.append(failed_value)

    # Derive per-frame times while keeping tile fan-out from over-counting.
    frame_time_samples_ms: list[float] = []
    all_frame_ids = set(stats_times_by_frame.keys()) | set(log_times_by_frame.keys())
    for frame_id in sorted(all_frame_ids):
        if frame_id in stats_times_by_frame and stats_times_by_frame[frame_id]:
            frame_time_samples_ms.append(max(stats_times_by_frame[frame_id]))
            continue
        if frame_id in log_times_by_frame and log_times_by_frame[frame_id]:
            frame_time_samples_ms.append(max(log_times_by_frame[frame_id]))

    if not frame_time_samples_ms and unscoped_time_samples:
        frame_time_samples_ms.extend(unscoped_time_samples)

    # Retry inference fallback:
    # one baseline attempt per (frame,tile). Extra attempts are retries.
    baseline_tile_count = max(1, candidate.tile_count)
    attempts_by_frame: dict[int, int] = {}
    for (frame_id, _tile_id), attempts in stats_attempts.items():
        attempts_by_frame[frame_id] = attempts_by_frame.get(frame_id, 0) + attempts
    if not attempts_by_frame:
        for (frame_id, _tile_id), attempts in log_attempts.items():
            attempts_by_frame[frame_id] = attempts_by_frame.get(frame_id, 0) + attempts

    inferred_retry_count = 0
    for attempts in attempts_by_frame.values():
        inferred_retry_count += max(0, attempts - baseline_tile_count)

    payload["total_frames"] = max(
        0,
        candidate.expected_frames
        if candidate.expected_frames > 0
        else len(all_frame_ids),
    )
    payload["frame_time_p50_ms"] = round(_percentile(frame_time_samples_ms, 0.5), 3)
    payload["frame_time_p90_ms"] = round(_percentile(frame_time_samples_ms, 0.9), 3)
    payload["memory_peak_gb"] = round(max(0.0, memory_peak_gb), 4)
    payload["queue_wait_ms"] = (
        max(queue_wait_ms_candidates) if queue_wait_ms_candidates else 0
    )
    payload["retry_count_total"] = (
        max(retry_candidates) if retry_candidates else inferred_retry_count
    )

    if failed_frame_candidates:
        payload["failed_frames"] = min(
            payload["total_frames"], max(failed_frame_candidates)
        )
    else:
        derived_failed = len(failed_frames)
        if derived_failed == 0 and unscoped_failures > 0:
            derived_failed = min(payload["total_frames"], max(1, unscoped_failures))
        payload["failed_frames"] = min(payload["total_frames"], derived_failed)

    return payload


def default_state_file() -> Path:
    """Return default local state file used for de-duplication."""

    config = load_config()
    return config.spool_dir / _STATE_DIRNAME / _STATE_FILENAME


def _load_state(path: Optional[Path]) -> dict[str, str]:
    if path is None:
        return {}
    if not path.exists() or not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    entries = raw.get("entries")
    if not isinstance(entries, dict):
        return {}
    state: dict[str, str] = {}
    for key, value in entries.items():
        key_text = _safe_text(key, fallback="")
        value_text = _safe_text(value, fallback="")
        if key_text and value_text:
            state[key_text] = value_text
    return state


def _save_state(path: Optional[Path], state: Mapping[str, str]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "entries": dict(sorted(state.items()))}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    tmp.replace(path)


def _candidate_key(candidate: RenderJobCandidate) -> str:
    return f"{candidate.job_id}|{candidate.submission_path}"


def _artifact_fingerprint(
    candidate: RenderJobCandidate, artifacts: RenderArtifacts
) -> str:
    total_size = 0
    latest_mtime_ns = 0
    tracked_paths = (
        candidate.submission_path,
        *artifacts.stats_files,
        *artifacts.stderr_logs,
        *artifacts.tractor_json_files,
    )
    for path in tracked_paths:
        try:
            stat = path.stat()
        except OSError:
            continue
        total_size += stat.st_size
        latest_mtime_ns = max(latest_mtime_ns, stat.st_mtime_ns)

    raw = (
        f"{candidate.job_id}|{candidate.submission_path}|"
        f"{len(artifacts.stats_files)}|{len(artifacts.stderr_logs)}|"
        f"{len(artifacts.tractor_json_files)}|{total_size}|{latest_mtime_ns}"
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def harvest_render_diagnostics(
    roots: Iterable[Path],
    *,
    scope: Optional[Mapping[str, Any]] = None,
    action_id: Optional[str] = None,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    settle_seconds: int = DEFAULT_SETTLE_SECONDS,
    max_jobs: Optional[int] = None,
    state_file: Optional[Path] = None,
    include_incomplete: bool = False,
) -> list[dict[str, Any]]:
    """Harvest render diagnostics artifacts and emit summary events.

    Returns emitted events (already validated/sanitized by ``emit``).
    """

    if lookback_hours < 1:
        raise ValueError("lookback_hours must be >= 1")
    if settle_seconds < 0:
        raise ValueError("settle_seconds must be >= 0")
    if max_jobs is not None and max_jobs < 1:
        raise ValueError("max_jobs must be >= 1 when provided")

    resolved_scope = extract_scope(scope or {})
    resolved_action_id = action_id or new_action_id()
    now = time.time()

    state = _load_state(state_file)
    updated_state = dict(state)
    emitted_events: list[dict[str, Any]] = []

    submission_files = sorted(
        _iter_recent_submission_files(roots, lookback_hours=lookback_hours),
        key=lambda path: path.stat().st_mtime if path.exists() else 0.0,
        reverse=True,
    )

    processed_jobs = 0
    for submission_path in submission_files:
        if max_jobs is not None and processed_jobs >= max_jobs:
            break
        try:
            candidate = _parse_candidate(submission_path, resolved_scope)
        except Exception:
            continue
        if candidate is None:
            continue

        artifacts = _collect_artifacts(candidate)
        if not artifacts.has_render_signal:
            continue
        if not include_incomplete and artifacts.latest_mtime > 0:
            if (now - artifacts.latest_mtime) < float(settle_seconds):
                continue

        fingerprint = _artifact_fingerprint(candidate, artifacts)
        key = _candidate_key(candidate)
        if state.get(key) == fingerprint:
            continue

        try:
            payload = _summarize_candidate(candidate, artifacts)
            event = emit(
                events.EVENT_RENDER_STATS_SUMMARY,
                status=STATUS_SUCCESS,
                payload=payload,
                scope=candidate.scope,
                action_id=resolved_action_id,
            )
        except Exception as exc:
            event = emit(
                events.EVENT_RENDER_STATS_SUMMARY,
                status=STATUS_ERROR,
                payload=_build_payload_defaults(candidate),
                scope=candidate.scope,
                action_id=resolved_action_id,
                error={
                    "code": ERROR_RENDER_STATS_HARVEST_FAILED,
                    "message": str(exc) or "Failed to harvest render diagnostics",
                    "exception_type": type(exc).__name__,
                },
            )

        if event is None:
            continue

        emitted_events.append(event)
        updated_state[key] = fingerprint
        processed_jobs += 1

    _save_state(state_file, updated_state)
    return emitted_events


def _sleep_until_next_sample(interval_seconds: int) -> bool:
    deadline = time.monotonic() + float(interval_seconds)
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return True
        try:
            time.sleep(min(1.0, remaining))
        except KeyboardInterrupt:
            return False


def run_render_harvest_loop(
    *,
    roots: Iterable[Path],
    interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    max_samples: Optional[int] = None,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    settle_seconds: int = DEFAULT_SETTLE_SECONDS,
    max_jobs_per_sample: Optional[int] = None,
    scope: Optional[Mapping[str, Any]] = None,
    print_events: bool = False,
    state_file: Optional[Path] = None,
    include_incomplete: bool = False,
) -> int:
    """Run periodic render diagnostics harvesting loop.

    Returns the number of emitted events across all samples.
    """

    if interval_seconds < 1:
        raise ValueError("interval_seconds must be >= 1")
    if max_samples is not None and max_samples < 1:
        raise ValueError("max_samples must be >= 1 when provided")
    if max_jobs_per_sample is not None and max_jobs_per_sample < 1:
        raise ValueError("max_jobs_per_sample must be >= 1 when provided")

    emitted_total = 0
    sample_count = 0
    while True:
        events_out = harvest_render_diagnostics(
            roots,
            scope=scope,
            lookback_hours=lookback_hours,
            settle_seconds=settle_seconds,
            max_jobs=max_jobs_per_sample,
            state_file=state_file,
            include_incomplete=include_incomplete,
        )
        emitted_total += len(events_out)
        sample_count += 1

        if print_events:
            for event in events_out:
                print(serialize_event(event))

        if max_samples is not None and sample_count >= max_samples:
            break
        if not _sleep_until_next_sample(interval_seconds):
            break

    return emitted_total


def _scope_from_args(args: argparse.Namespace) -> dict[str, str]:
    return extract_scope(vars(args))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Harvest Tractor/Husk/RenderMan diagnostics and emit render.stats.summary."
        )
    )
    parser.add_argument(
        "roots", nargs="+", help="Root directories to scan for telemetry artifacts"
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help=f"Harvest cadence in seconds (default: {DEFAULT_POLL_INTERVAL_SECONDS})",
    )
    parser.add_argument("--lookback-hours", type=int, default=DEFAULT_LOOKBACK_HOURS)
    parser.add_argument("--settle-seconds", type=int, default=DEFAULT_SETTLE_SECONDS)
    parser.add_argument("--max-jobs", type=int, help="Max jobs to process per sample")
    parser.add_argument("--once", action="store_true", help="Harvest once and exit")
    parser.add_argument("--max-samples", type=int, help="Optional max loop samples")
    parser.add_argument(
        "--state-file",
        type=Path,
        default=default_state_file(),
        help="State file for de-duplication (default: local telemetry state path)",
    )
    parser.add_argument(
        "--no-state",
        action="store_true",
        help="Disable state file and emit all eligible jobs each run",
    )
    parser.add_argument(
        "--include-incomplete",
        action="store_true",
        help="Include jobs whose artifacts are newer than settle_seconds.",
    )
    parser.add_argument("--show")
    parser.add_argument("--sequence")
    parser.add_argument("--shot")
    parser.add_argument("--asset")
    parser.add_argument("--department")
    parser.add_argument("--task")
    parser.add_argument(
        "--print-events",
        action="store_true",
        help="Print each emitted event JSON to stdout.",
    )
    parser.add_argument(
        "--jsonl-out",
        type=Path,
        help="Optional output path for JSONL event output.",
    )
    args = parser.parse_args(argv)

    roots = [Path(root).expanduser() for root in args.roots]
    scope = _scope_from_args(args)
    state_file = None if args.no_state else args.state_file

    try:
        if args.once:
            events_out = harvest_render_diagnostics(
                roots,
                scope=scope,
                lookback_hours=args.lookback_hours,
                settle_seconds=args.settle_seconds,
                max_jobs=args.max_jobs,
                state_file=state_file,
                include_incomplete=args.include_incomplete,
            )
            emitted = len(events_out)
            if args.print_events:
                for event in events_out:
                    print(serialize_event(event))
            if args.jsonl_out is not None:
                args.jsonl_out.parent.mkdir(parents=True, exist_ok=True)
                with args.jsonl_out.open("w", encoding="utf-8") as handle:
                    for event in events_out:
                        handle.write(serialize_event(event))
                        handle.write("\n")
        else:
            emitted = run_render_harvest_loop(
                roots=roots,
                interval_seconds=args.interval_seconds,
                max_samples=args.max_samples,
                lookback_hours=args.lookback_hours,
                settle_seconds=args.settle_seconds,
                max_jobs_per_sample=args.max_jobs,
                scope=scope,
                print_events=args.print_events,
                state_file=state_file,
                include_incomplete=args.include_incomplete,
            )
    except ValueError as exc:
        print(f"Invalid render_harvest arguments: {exc}", file=sys.stderr)
        return 2

    if not args.print_events:
        print(
            "events={events} roots={roots} interval_seconds={interval}".format(
                events=emitted,
                roots=len(roots),
                interval=args.interval_seconds,
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
