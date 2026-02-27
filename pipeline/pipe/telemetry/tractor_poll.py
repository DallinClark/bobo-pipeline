"""Tractor farm pressure collector.

This collector emits ``tractor.farm.snapshot`` as a periodic, aggregated
time-series event for queue pressure and farm utilization.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence
from urllib.parse import urlparse

from . import events
from .context import extract_scope
from .contract import serialize_event
from .emit import emit
from .registry import ERROR_TRACTOR_SNAPSHOT_FAILED, STATUS_ERROR, STATUS_INFO

DEFAULT_POLL_INTERVAL_SECONDS = 300
DEFAULT_ENGINE_PORT = 80
DEFAULT_MIN_MATCHED_FIELDS = 4

_WAITING_PATH_CANDIDATES: tuple[tuple[str, ...], ...] = (
    ("jobs", "waiting"),
    ("jobs", "queued"),
    ("queue", "waiting"),
    ("queue", "queued"),
    ("waiting_jobs",),
)
_WAITING_KEY_CANDIDATES: tuple[str, ...] = (
    "waiting_jobs",
    "jobs_waiting",
    "waiting",
    "queued_jobs",
    "jobs_queued",
    "queued",
)

_RUNNING_PATH_CANDIDATES: tuple[tuple[str, ...], ...] = (
    ("jobs", "running"),
    ("jobs", "active"),
    ("queue", "running"),
    ("running_jobs",),
)
_RUNNING_KEY_CANDIDATES: tuple[str, ...] = (
    "running_jobs",
    "jobs_running",
    "running",
    "active_jobs",
    "jobs_active",
    "active",
)

_BUSY_SLOTS_PATH_CANDIDATES: tuple[tuple[str, ...], ...] = (
    ("slots", "busy"),
    ("slots", "in_use"),
    ("slots", "inuse"),
    ("busy_slots",),
)
_BUSY_SLOTS_KEY_CANDIDATES: tuple[str, ...] = (
    "busy_slots",
    "slots_busy",
    "in_use_slots",
    "slots_in_use",
    "slots_inuse",
    "busy",
)

_TOTAL_SLOTS_PATH_CANDIDATES: tuple[tuple[str, ...], ...] = (
    ("slots", "total"),
    ("slots", "capacity"),
    ("total_slots",),
)
_TOTAL_SLOTS_KEY_CANDIDATES: tuple[str, ...] = (
    "total_slots",
    "slots_total",
    "slots_capacity",
    "capacity_slots",
    "capacity",
)

_ACTIVE_BLADES_PATH_CANDIDATES: tuple[tuple[str, ...], ...] = (
    ("blades", "active"),
    ("blades", "up"),
    ("active_blades",),
)
_ACTIVE_BLADES_KEY_CANDIDATES: tuple[str, ...] = (
    "active_blades",
    "blades_active",
    "blades_up",
    "active",
    "up",
    "online_blades",
)

_TOTAL_BLADES_PATH_CANDIDATES: tuple[tuple[str, ...], ...] = (
    ("blades", "total"),
    ("blades", "count"),
    ("total_blades",),
)
_TOTAL_BLADES_KEY_CANDIDATES: tuple[str, ...] = (
    "total_blades",
    "blades_total",
    "blades_count",
    "blade_count",
    "count",
)


@dataclass(frozen=True)
class TractorEndpoint:
    """Resolved Tractor endpoint for polling."""

    engine_url: str
    hostname: str
    port: int


def _normalize_key(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _resolve_mapping_key(mapping: Mapping[str, Any], segment: str) -> Optional[str]:
    if segment in mapping:
        return segment
    target = _normalize_key(segment)
    for key in mapping.keys():
        if _normalize_key(str(key)) == target:
            return str(key)
    return None


def _lookup_path(data: Any, path: Sequence[str]) -> Any:
    current = data
    for segment in path:
        if isinstance(current, Mapping):
            key = _resolve_mapping_key(current, segment)
            if key is None:
                return None
            current = current[key]
            continue

        if isinstance(current, (list, tuple)):
            try:
                index = int(segment)
            except Exception:
                return None
            if index < 0 or index >= len(current):
                return None
            current = current[index]
            continue

        return None
    return current


def _find_first_key(data: Any, candidate_keys: set[str], seen: set[int]) -> Any:
    data_id = id(data)
    if data_id in seen:
        return None
    seen.add(data_id)

    if isinstance(data, Mapping):
        for raw_key, value in data.items():
            if _normalize_key(str(raw_key)) in candidate_keys:
                return value
        for value in data.values():
            found = _find_first_key(value, candidate_keys, seen)
            if found is not None:
                return found
        return None

    if isinstance(data, (list, tuple)):
        for value in data:
            found = _find_first_key(value, candidate_keys, seen)
            if found is not None:
                return found
    return None


def _parse_non_negative_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, str):
        normalized = value.strip().replace(",", "")
        if not normalized:
            return None
        try:
            if "." in normalized:
                return max(0, int(float(normalized)))
            return max(0, int(normalized))
        except ValueError:
            return None
    return None


def _extract_count(
    queue_stats: Any,
    *,
    path_candidates: Sequence[Sequence[str]],
    key_candidates: Sequence[str],
) -> tuple[int, bool]:
    for path in path_candidates:
        candidate = _lookup_path(queue_stats, path)
        parsed = _parse_non_negative_int(candidate)
        if parsed is not None:
            return parsed, True

    fallback_candidate = _find_first_key(
        queue_stats,
        candidate_keys={_normalize_key(candidate) for candidate in key_candidates},
        seen=set(),
    )
    fallback_parsed = _parse_non_negative_int(fallback_candidate)
    if fallback_parsed is not None:
        return fallback_parsed, True
    return 0, False


def _empty_snapshot_payload(engine_url: str) -> dict[str, Any]:
    return {
        "engine_url": engine_url,
        "waiting_jobs": 0,
        "running_jobs": 0,
        "busy_slots": 0,
        "total_slots": 0,
        "active_blades": 0,
        "total_blades": 0,
    }


def resolve_tractor_endpoint(
    engine_url: str, engine_port: Optional[int] = None
) -> TractorEndpoint:
    """Resolve Tractor endpoint from engine URL/host and optional port."""

    cleaned = str(engine_url).strip()
    if not cleaned:
        raise ValueError("engine_url must be a non-empty string")

    parsed = (
        urlparse(cleaned)
        if "://" in cleaned
        else urlparse(f"//{cleaned}", scheme="tractor")
    )
    hostname = parsed.hostname or cleaned
    if not hostname:
        raise ValueError(f"unable to resolve hostname from engine_url={engine_url!r}")

    port = engine_port if engine_port is not None else parsed.port
    if port is None:
        port = DEFAULT_ENGINE_PORT
    if port < 1:
        raise ValueError(f"engine_port must be >= 1, got {port}")

    return TractorEndpoint(engine_url=cleaned, hostname=hostname, port=port)


def fetch_tractor_queue_stats(endpoint: TractorEndpoint) -> Any:
    """Fetch queue stats payload from Tractor Engine API."""

    try:
        import tractor.api.author as tractor_author
        import tractor.base.EngineClient as tractor_engine_client
    except Exception as exc:
        raise RuntimeError("Failed to import Tractor Python API") from exc

    tractor_author.setEngineClientParam(hostname=endpoint.hostname, port=endpoint.port)
    try:
        queue_stats = tractor_engine_client.TheEngineClient.queueStats()
    finally:
        try:
            tractor_author.closeEngineClient()
        except Exception:
            pass

    if queue_stats is None:
        raise RuntimeError("Tractor queueStats() returned no data")
    return queue_stats


def build_snapshot_payload(
    queue_stats: Any, *, engine_url: str
) -> tuple[dict[str, Any], int]:
    """Build contract-compliant snapshot payload and count matched fields."""

    waiting_jobs, waiting_matched = _extract_count(
        queue_stats,
        path_candidates=_WAITING_PATH_CANDIDATES,
        key_candidates=_WAITING_KEY_CANDIDATES,
    )
    running_jobs, running_matched = _extract_count(
        queue_stats,
        path_candidates=_RUNNING_PATH_CANDIDATES,
        key_candidates=_RUNNING_KEY_CANDIDATES,
    )
    busy_slots, busy_slots_matched = _extract_count(
        queue_stats,
        path_candidates=_BUSY_SLOTS_PATH_CANDIDATES,
        key_candidates=_BUSY_SLOTS_KEY_CANDIDATES,
    )
    total_slots, total_slots_matched = _extract_count(
        queue_stats,
        path_candidates=_TOTAL_SLOTS_PATH_CANDIDATES,
        key_candidates=_TOTAL_SLOTS_KEY_CANDIDATES,
    )
    active_blades, active_blades_matched = _extract_count(
        queue_stats,
        path_candidates=_ACTIVE_BLADES_PATH_CANDIDATES,
        key_candidates=_ACTIVE_BLADES_KEY_CANDIDATES,
    )
    total_blades, total_blades_matched = _extract_count(
        queue_stats,
        path_candidates=_TOTAL_BLADES_PATH_CANDIDATES,
        key_candidates=_TOTAL_BLADES_KEY_CANDIDATES,
    )

    matched_fields = sum(
        (
            waiting_matched,
            running_matched,
            busy_slots_matched,
            total_slots_matched,
            active_blades_matched,
            total_blades_matched,
        )
    )

    payload = {
        "engine_url": engine_url,
        "waiting_jobs": waiting_jobs,
        "running_jobs": running_jobs,
        "busy_slots": busy_slots,
        "total_slots": total_slots,
        "active_blades": active_blades,
        "total_blades": total_blades,
    }
    return payload, matched_fields


def poll_tractor_farm_snapshot(
    *,
    engine_url: str,
    engine_port: Optional[int] = None,
    scope: Optional[Mapping[str, Any]] = None,
    action_id: Optional[str] = None,
    min_matched_fields: int = DEFAULT_MIN_MATCHED_FIELDS,
) -> Optional[dict[str, Any]]:
    """Poll Tractor farm stats and emit one ``tractor.farm.snapshot`` event."""

    payload = _empty_snapshot_payload(str(engine_url).strip() or "unknown")
    try:
        endpoint = resolve_tractor_endpoint(engine_url, engine_port)
        payload["engine_url"] = endpoint.engine_url
        queue_stats = fetch_tractor_queue_stats(endpoint)
        payload, matched_fields = build_snapshot_payload(
            queue_stats, engine_url=endpoint.engine_url
        )
        if matched_fields < min_matched_fields:
            raise ValueError(
                f"Unable to resolve enough queue fields from queueStats payload "
                f"(matched={matched_fields}, required={min_matched_fields})"
            )
        return emit(
            events.EVENT_TRACTOR_FARM_SNAPSHOT,
            status=STATUS_INFO,
            payload=payload,
            scope=scope,
            action_id=action_id,
        )
    except Exception as exc:
        return emit(
            events.EVENT_TRACTOR_FARM_SNAPSHOT,
            status=STATUS_ERROR,
            payload=payload,
            scope=scope,
            action_id=action_id,
            error={
                "code": ERROR_TRACTOR_SNAPSHOT_FAILED,
                "message": str(exc) or "Failed to poll Tractor farm snapshot",
                "exception_type": type(exc).__name__,
            },
        )


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


def run_tractor_poll_loop(
    *,
    engine_url: str,
    engine_port: Optional[int] = None,
    interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    max_samples: Optional[int] = None,
    stop_on_error: bool = False,
    scope: Optional[Mapping[str, Any]] = None,
    print_events: bool = False,
) -> int:
    """Run periodic Tractor polling loop and return number of samples emitted."""

    if interval_seconds < 1:
        raise ValueError("interval_seconds must be >= 1")
    if max_samples is not None and max_samples < 1:
        raise ValueError("max_samples must be >= 1 when provided")

    sample_count = 0
    while True:
        event = poll_tractor_farm_snapshot(
            engine_url=engine_url,
            engine_port=engine_port,
            scope=scope,
        )
        sample_count += 1

        if print_events and event is not None:
            print(serialize_event(event))

        if stop_on_error and isinstance(event, Mapping):
            if str(event.get("status")) == STATUS_ERROR:
                break

        if max_samples is not None and sample_count >= max_samples:
            break

        if not _sleep_until_next_sample(interval_seconds):
            break

    return sample_count


def _scope_from_args(args: argparse.Namespace) -> dict[str, str]:
    return extract_scope(vars(args))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Poll Tractor queue pressure and emit tractor.farm.snapshot events."
    )
    parser.add_argument(
        "--engine-url", required=True, help="Tractor engine host or URL"
    )
    parser.add_argument(
        "--engine-port",
        type=int,
        help=f"Tractor engine port (default: URL port or {DEFAULT_ENGINE_PORT})",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help=f"Polling cadence in seconds (default: {DEFAULT_POLL_INTERVAL_SECONDS})",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Emit exactly one snapshot and exit.",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        help="Optional max number of snapshots before exiting.",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop polling after first error status event.",
    )
    parser.add_argument(
        "--print-events",
        action="store_true",
        help="Print each emitted event JSON to stdout.",
    )
    parser.add_argument("--show")
    parser.add_argument("--sequence")
    parser.add_argument("--shot")
    parser.add_argument("--asset")
    parser.add_argument("--department")
    parser.add_argument("--task")
    args = parser.parse_args(argv)

    scope = _scope_from_args(args)
    max_samples = 1 if args.once else args.max_samples

    try:
        emitted_samples = run_tractor_poll_loop(
            engine_url=args.engine_url,
            engine_port=args.engine_port,
            interval_seconds=args.interval_seconds,
            max_samples=max_samples,
            stop_on_error=args.stop_on_error,
            scope=scope,
            print_events=args.print_events,
        )
    except ValueError as exc:
        print(f"Invalid tractor poll arguments: {exc}", file=sys.stderr)
        return 2

    if not args.print_events:
        print(
            "samples={samples} engine_url={engine_url} interval_seconds={interval}".format(
                samples=emitted_samples,
                engine_url=args.engine_url,
                interval=args.interval_seconds,
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
