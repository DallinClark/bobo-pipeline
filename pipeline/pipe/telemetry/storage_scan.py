"""Storage scan collector for aggregated telemetry buckets."""

from __future__ import annotations

import argparse
import hashlib
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Sequence

from . import events
from .contract import serialize_event
from .emit import emit
from .registry import STATUS_INFO, STATUS_SUCCESS

ScopeType = str
Category = str

_FX_SUFFIXES = {".vdb", ".bgeo", ".bgeo.sc", ".sim"}
_TEXTURE_SUFFIXES = {
    ".tex",
    ".tx",
    ".rat",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".exr",
}
_PLAYBLAST_SUFFIXES = {".mov", ".mp4"}


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def _normalize_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def classify_path(path: Path) -> Category:
    """Classify a production file path into a storage category."""

    lowered_parts = {part.lower() for part in path.parts}
    suffix = path.suffix.lower()

    if "render" in lowered_parts or "renders" in lowered_parts:
        return "render"
    if "fx" in lowered_parts or suffix in _FX_SUFFIXES:
        return "fx_cache"
    if (
        "tex" in lowered_parts
        or "textures" in lowered_parts
        or suffix in _TEXTURE_SUFFIXES
    ):
        return "texture"
    if "publish" in lowered_parts:
        return "publish"
    if "playblast" in lowered_parts or suffix in _PLAYBLAST_SUFFIXES:
        return "playblast"
    return "other"


def _bucket_path(root: Path, file_path: Path) -> Path:
    try:
        relative = file_path.relative_to(root)
    except ValueError:
        return root
    if not relative.parts:
        return root
    return root / relative.parts[0]


def _bucket_id(scope_type: str, scope_code: str, category: str, path: str) -> str:
    raw = f"{scope_type}|{scope_code}|{category}|{path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class BucketKey:
    scope_type: ScopeType
    scope_code: str
    category: Category
    path: str


@dataclass
class BucketMetrics:
    size_bytes: int = 0
    file_count: int = 0
    dirs: set[str] = field(default_factory=set)

    @property
    def dir_count(self) -> int:
        return len(self.dirs)

    def add_file(self, directory: str, size_bytes: int) -> None:
        self.size_bytes += size_bytes
        self.file_count += 1
        self.dirs.add(directory)


@dataclass
class StorageScanResult:
    scan_id: str
    scan_window_start_utc: str
    scan_window_end_utc: str
    roots_scanned_count: int
    buckets: dict[BucketKey, BucketMetrics]
    skipped_files: int
    scan_duration_ms: int

    @property
    def buckets_emitted_count(self) -> int:
        return len(self.buckets)

    @property
    def size_bytes_total(self) -> int:
        return sum(item.size_bytes for item in self.buckets.values())

    @property
    def file_count_total(self) -> int:
        return sum(item.file_count for item in self.buckets.values())

    @property
    def dir_count_total(self) -> int:
        return sum(item.dir_count for item in self.buckets.values())


def scan_storage(
    roots: Iterable[Path], *, scope_type: str, scope_code: str
) -> StorageScanResult:
    """Scan roots and return aggregated usage buckets."""

    scan_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    window_start = started_at.isoformat(timespec="seconds").replace("+00:00", "Z")
    buckets: dict[BucketKey, BucketMetrics] = {}
    skipped_files = 0
    roots_scanned_count = 0

    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        roots_scanned_count += 1
        for dirpath, _, filenames in os.walk(root):
            dir_path = Path(dirpath)
            dir_str = _normalize_path(dir_path)
            for filename in filenames:
                file_path = dir_path / filename
                try:
                    stat = file_path.stat()
                except OSError:
                    skipped_files += 1
                    continue

                category = classify_path(file_path)
                bucket_path = _normalize_path(_bucket_path(root, file_path))
                key = BucketKey(
                    scope_type=scope_type,
                    scope_code=scope_code,
                    category=category,
                    path=bucket_path,
                )
                metric = buckets.setdefault(key, BucketMetrics())
                metric.add_file(dir_str, stat.st_size)

    ended_at = datetime.now(timezone.utc)
    duration_ms = int((ended_at - started_at).total_seconds() * 1000)

    return StorageScanResult(
        scan_id=scan_id,
        scan_window_start_utc=window_start,
        scan_window_end_utc=ended_at.isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        ),
        roots_scanned_count=roots_scanned_count,
        buckets=buckets,
        skipped_files=skipped_files,
        scan_duration_ms=duration_ms,
    )


def build_storage_events(
    result: StorageScanResult,
    *,
    scope: Optional[dict[str, str]] = None,
    action_id: Optional[str] = None,
) -> list[dict[str, object]]:
    """Build `storage.scan.summary` and `storage.scan.bucket` events."""

    scope_data = scope or {}
    events_out: list[dict[str, object]] = []

    for key in sorted(
        result.buckets.keys(),
        key=lambda item: (item.scope_type, item.scope_code, item.category, item.path),
    ):
        metric = result.buckets[key]
        payload = {
            "bucket_id": _bucket_id(
                key.scope_type, key.scope_code, key.category, key.path
            ),
            "scope_type": key.scope_type,
            "scope_code": key.scope_code,
            "category": key.category,
            "path": key.path,
            "scan_window_start_utc": result.scan_window_start_utc,
            "scan_window_end_utc": result.scan_window_end_utc,
        }
        bucket_event = emit(
            events.EVENT_STORAGE_SCAN_BUCKET,
            status=STATUS_INFO,
            payload=payload,
            metrics={
                "size_bytes": metric.size_bytes,
                "file_count": metric.file_count,
                "dir_count": metric.dir_count,
            },
            scope=scope_data,
            action_id=action_id,
        )
        events_out.append(bucket_event)

    summary_event = emit(
        events.EVENT_STORAGE_SCAN_SUMMARY,
        status=STATUS_SUCCESS,
        payload={
            "scan_id": result.scan_id,
            "scan_window_start_utc": result.scan_window_start_utc,
            "scan_window_end_utc": result.scan_window_end_utc,
            "roots_scanned_count": result.roots_scanned_count,
            "buckets_emitted_count": result.buckets_emitted_count,
            "scan_duration_ms": result.scan_duration_ms,
        },
        metrics={
            "size_bytes_total": result.size_bytes_total,
            "file_count_total": result.file_count_total,
            "dir_count_total": result.dir_count_total,
        },
        scope=scope_data,
        action_id=action_id,
    )
    events_out.insert(0, summary_event)
    return events_out


def _scope_from_args(args: argparse.Namespace) -> dict[str, str]:
    scope: dict[str, str] = {}
    for field_name in ("show", "sequence", "shot", "asset", "department"):
        value = getattr(args, field_name)
        if value:
            scope[field_name] = value
    return scope


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan storage roots and emit aggregated telemetry events."
    )
    parser.add_argument("roots", nargs="+", help="Root directories to scan")
    parser.add_argument(
        "--scope-type",
        default="show",
        choices=("show", "sequence", "shot", "asset", "department"),
        help="Bucket scope dimension type",
    )
    parser.add_argument(
        "--scope-code",
        required=True,
        help="Bucket scope dimension code (for example show code).",
    )
    parser.add_argument("--show")
    parser.add_argument("--sequence")
    parser.add_argument("--shot")
    parser.add_argument("--asset")
    parser.add_argument("--department")
    parser.add_argument(
        "--print-events",
        action="store_true",
        help="Print each JSON event to stdout.",
    )
    parser.add_argument(
        "--jsonl-out",
        type=Path,
        help="Optional output path for JSONL event output.",
    )
    args = parser.parse_args(argv)

    roots = [Path(root).expanduser() for root in args.roots]
    result = scan_storage(roots, scope_type=args.scope_type, scope_code=args.scope_code)
    events_out = build_storage_events(result, scope=_scope_from_args(args))

    if args.jsonl_out is not None:
        args.jsonl_out.parent.mkdir(parents=True, exist_ok=True)
        with args.jsonl_out.open("w", encoding="utf-8") as handle:
            for event in events_out:
                handle.write(serialize_event(event))
                handle.write("\n")

    if args.print_events:
        for event in events_out:
            print(serialize_event(event))
    else:
        print(
            "scan_id={scan_id} roots={roots} buckets={buckets} size_bytes_total={size}".format(
                scan_id=result.scan_id,
                roots=result.roots_scanned_count,
                buckets=result.buckets_emitted_count,
                size=result.size_bytes_total,
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
