# Telemetry Implementation Spec (Pipeline-Side)
Date: February 26, 2026  
Audience: Pipeline engineering team (Sandwich production)  
Status: Implementation-ready design

## 1) Purpose and Scope

This document specifies how to add lightweight, self-documenting telemetry to this pipeline codebase, with minimal risk to artist workflows and minimal operational overhead.

This spec focuses on code and behavior that lives **inside this repository**:

- Structured event emission
- Event contract and schema governance
- Non-intrusive instrumentation points in existing tools
- Local durability and fail-open behavior

This spec intentionally does **not** define dashboard implementation details. Downstream parsing, warehousing, and visualization remain in your separate analytics tool.

---

## 2) Design Priorities (in order)

1. **Non-intrusive first**
- Why: Artist throughput is the core product. Telemetry must never block publishing, rendering, opening files, or launching DCCs.

2. **Self-documenting and readable**
- Why: This pipeline will be maintained by rotating contributors over the show lifecycle. Event meaning must be discoverable from code, not tribal knowledge.

3. **Lightweight and local**
- Why: Cross-platform (Windows + Linux) and mixed lab/studio conditions require robust behavior under flaky network and variable permissions.

4. **Flexible over complete**
- Why: Overcollecting noisy fields now creates maintenance debt. Start with high-signal events and evolve with explicit schema versioning.

5. **Stable contracts**
- Why: Your external analytics tool should not break when internal implementation details change.

---

## 3) Non-Goals

- Building dashboards in this repo
- Building a distributed metrics system (Prometheus, etc.) in this repo
- Capturing every log line or every frame-level detail on day one
- Enforcing strict runtime validation that can interrupt artist actions

---

## 4) Telemetry Architecture (Pipeline Side)

## 4.1 Data flow

1. Code path calls `telemetry.emit(...)`.
2. Event is normalized and minimally validated.
3. Event is queued in-memory.
4. Background writer appends JSON lines to local spool files.
5. Failures are logged; operation continues (fail-open).

This repo stops here. Any central upload or aggregation can be done by a separate shipper/job.

## 4.2 Why this shape

- Queue + writer thread reduces latency on artist actions.
- Append-only JSONL is simple, inspectable, and resilient.
- Local spool avoids hard dependency on network path availability.
- Event model supports both current and future analytics consumers.

---

## 5) Proposed Module Layout

Create a new package:

`pipeline/pipe/telemetry/`

- `__init__.py`  
  Public API (`emit`, `new_action_id`, `configure_session_context`)

- `config.py`  
  Env-driven config, defaults, and parsing

- `contract.py`  
  Event envelope model, validation helpers, schema version constants

- `registry.py`  
  Event type registry (description + required payload fields + owner module)

- `context.py`  
  Context resolvers (shot/asset/department from SG entities, Maya/Houdini context)

- `spool.py`  
  Queue + background writer + file rotation + retention

- `emit.py`  
  Main emit implementation and convenience helpers (`timed_block`, `emit_exception`)

- `storage_scan.py`  
  Optional CLI scanner to emit storage summary events

- `docs.py` (optional)
  CLI helper to print/dump the live contract from registry for documentation

Why this layout:
- Keeps concerns isolated and readable.
- Makes event catalog explicit and reviewable.
- Avoids coupling telemetry internals to DCC-specific modules.

---

## 6) Event Contract (v1)

## 6.1 Envelope requirements

Every event is a JSON object with these top-level keys:

- `schema_version` (string, required)  
  Example: `"1.0"`

- `event_id` (string UUID4, required)

- `event_type` (string, required)  
  Must exist in `registry.py`.

- `occurred_at_utc` (string ISO-8601 UTC, required)

- `status` (string enum, required)  
  One of: `success`, `error`, `warning`, `info`

- `pipeline` (object, required)
- `host` (object, required)
- `session` (object, required)
- `scope` (object, optional but strongly recommended)
- `metrics` (object, optional)
- `error` (object, optional, required when `status=error`)
- `payload` (object, required; can be empty `{}`)

## 6.2 Canonical envelope shape

```json
{
  "schema_version": "1.0",
  "event_id": "1f64b8ec-8bc4-4f35-a111-6c1b95af57c9",
  "event_type": "publish.asset.usd",
  "occurred_at_utc": "2026-02-26T21:18:03Z",
  "status": "success",
  "pipeline": {
    "name": "sandwich-pipeline",
    "version": "0.1.0",
    "dcc": "maya",
    "module": "pipe.m.publish.asset",
    "function": "_postpublish"
  },
  "host": {
    "hostname": "ws-anim-17",
    "os": "Windows",
    "os_release": "11",
    "user": "artist_login",
    "pid": 32444
  },
  "session": {
    "session_id": "f93a4ab2-31cb-4d89-9e2a-f674f914f741",
    "action_id": "e4ba5d73-95b2-4c70-80d4-58ed926563ba"
  },
  "scope": {
    "show": "sandwich",
    "sequence": "A",
    "shot": "A_010",
    "asset": "hero_sandwich",
    "department": "lighting",
    "task": null
  },
  "metrics": {
    "duration_ms": 2412
  },
  "payload": {
    "publish_path": "/groups/.../asset/hero_sandwich/publish/_src/main.usd",
    "selection_count": 12
  }
}
```

## 6.3 Why this envelope

- `session_id` and `action_id` allow end-to-end tracing across nested calls.
- `scope` separates production identity from tool-specific payload.
- `metrics` is reserved for numeric values, improving downstream query consistency.
- `error` is structured, so analytics can group failures by stable code.

## 6.4 Error object shape

When `status=error`, include:

- `error.code` (required, stable string enum)
- `error.message` (required, truncated to max bytes)
- `error.exception_type` (optional)
- `error.stacktrace` (optional, truncated)

Example:

```json
"error": {
  "code": "USD_EXPORT_FAILED",
  "message": "mayaUSDExport raised RuntimeError",
  "exception_type": "RuntimeError"
}
```

## 6.5 Field constraints

- Max serialized event size: `64 KB` (hard cap, truncate payload/error fields first)
- Strings in `payload` should be bounded; truncate to configured max lengths
- No binary blobs in events
- No unrestricted environment dumps or raw secrets

---

## 7) Event Naming and Registry

## 7.1 Naming convention

`<domain>.<subject>.<action>`

Examples:

- `publish.asset.usd`
- `publish.anim.usd`
- `build.houdini.component`
- `texture.convert.tex`
- `tractor.job.spool`
- `storage.scan.summary`

Why:
- Predictable grouping in queries and dashboards.
- Easy to discover related events by prefix.

## 7.2 Registry requirements

Every event type must be declared in `registry.py` with:

- `event_type`
- `description`
- `required_payload_fields`
- `owner_module`
- `status_values`
- `sample_rate` (default `1.0`)

Why:
- Keeps the system self-documenting.
- Lets CI verify unknown or malformed event usage.

---

## 8) MVP Event Set (High Signal, Low Volume)

Implement these first:

1. `dcc.launch`
2. `publish.asset.usd`
3. `publish.anim.usd`
4. `publish.camera.usd`
5. `build.houdini.component`
6. `texture.export.substance`
7. `texture.convert.tex`
8. `file.open`
9. `file.create`
10. `shot.setup`
11. `playblast.create`
12. `tractor.job.spool`
13. `storage.scan.summary`
14. `storage.scan.bucket`

Why this set:
- Covers your top needs now: storage usage, publish health, render/farm context, and core artist-facing operations.

---

## 9) Integration Points in Existing Code

This section maps each event to concrete files already in this repo.

## 9.1 DCC launch

File:
- `pipeline/software/baseclass.py`

Emit:
- `dcc.launch` on attempted launch (success/info)
- `dcc.launch` with `status=error` on launch exception

Payload:
- `command_basename`
- `arg_count`
- `is_python_shell` (if available from caller)
- `env_keys_set` (list of changed keys only, not values)

Why:
- Tracks adoption and startup failure rates by DCC/host.

## 9.2 Maya publish core

File:
- `pipeline/pipe/m/publish/publisher.py`

Emit:
- one terminal event per publish call (`success` or `error`)

Payload:
- `publish_type` (`asset|anim|camera|customanim|previs_asset`)
- `publish_path`
- `selection_count`
- `is_windows_workaround_used`
- `mayausd_kwargs_keys` (keys only)

Metrics:
- `duration_ms`

Error codes:
- `PUBLISH_PRECHECK_FAILED`
- `USD_EXPORT_FAILED`
- `WINDOWS_MOVE_FAILED`

Why:
- Centralizing here minimizes code churn and avoids duplicated instrumentation in subclasses.

## 9.3 Houdini component build from Maya publish

Files:
- `pipeline/pipe/m/publish/asset.py`
- `pipeline/pipe/h/assetbuilder.py`

Emit:
- `build.houdini.component`

Payload:
- `mode` (`create|update`)
- `hip_path`
- `usd_path`
- `export_dir`
- `variant`
- `changed_usd_reference`
- `export_performed`
- `warnings_count`
- `errors_count`

Metrics:
- `duration_ms`

Why:
- You already produce structured result JSON; this is immediate high-value telemetry with almost no extra parsing.

## 9.4 Substance texture export and conversion

Files:
- `pipeline/pipe/sp/export.py`
- `pipeline/pipe/texconverter.py`

Emit:
- `texture.export.substance`
- `texture.convert.tex`

Payload (export):
- `asset`
- `geo_variant`
- `material_variant`
- `renderman_variant`
- `texture_set_count`
- `udim_set_count`

Payload (convert):
- `source_count`
- `converted_tex_count`
- `converted_preview_count`
- `batch_size`

Why:
- Texture and cache footprint are frequent disk pressure drivers.

## 9.5 File open/create/setup

Files:
- `pipeline/pipe/util/filemanager.py`
- `pipeline/pipe/m/assetfile.py`
- `pipeline/pipe/h/hipfile/filemanager.py`
- `pipeline/pipe/h/hipfile/shot.py`
- `pipeline/pipe/m/shotfile/shotfile_manager.py`

Emit:
- `file.open`
- `file.create`
- `shot.setup`

Payload:
- `entity_type`
- `entity_code`
- `path`
- `versioned` (bool)
- `opened_backup` (bool when known)
- `department` (for shot setup)

Why:
- Gives immediate visibility into file churn and setup error hotspots.

## 9.6 Playblasts

Files:
- `pipeline/pipe/util/playblaster.py`
- `pipeline/pipe/m/playblast/playblaster.py`
- `pipeline/pipe/h/playblast/playblaster.py`

Emit:
- `playblast.create`

Payload:
- `preset`
- `output_count`
- `frame_start`
- `frame_end`
- `fps`
- `tail_in`
- `tail_out`
- `camera` (when available)

Metrics:
- `duration_ms`
- `output_size_bytes` (per output or total)

Why:
- Useful for editorial throughput and troubleshooting encoding/runtime issues.

## 9.7 Tractor job submission (Houdini/Tractor LOPs)

Files:
- `pipeline/lib/tractor-lops/.../tractor_submit.../PythonModule`
- `pipeline/lib/tractor-lops/.../tractor_configure.../PythonModule`
- `pipeline/lib/tractor-lops/.../tractor_denoise.../PythonModule`

Emit:
- `tractor.job.spool`

Payload:
- `job_title`
- `engine_url`
- `priority`
- `service`
- `frame_start`
- `frame_end`
- `frame_step`
- `tile_count`
- `output_directory`
- `renderer`
- `denoise_enabled`

Why:
- Captures render context at submission time (most reliable join point before farm fan-out).

---

## 10) Storage Scan Event Spec (Optional but Recommended)

Implement `python -m pipe.telemetry.storage_scan` as a lightweight scanner that emits:

- `storage.scan.summary` (one per run)
- `storage.scan.bucket` (many per run; aggregated buckets)

## 10.1 Bucket dimensions

- `scope_type` (`show|sequence|shot|asset|department`)
- `scope_code`
- `category` (`render|fx_cache|texture|publish|playblast|other`)
- `path`

Metrics:
- `size_bytes`
- `file_count`
- `dir_count`

Why aggregated buckets:
- Much lower data volume than file-level events.
- Still enough to answer "what is taking space and where?"

## 10.2 Classification strategy

Use config-driven regex/path rules:

- `.../render/...` -> `render`
- `.../fx/...`, extensions `.vdb`, `.bgeo`, `.sim` -> `fx_cache`
- `.../tex/...`, extensions `.tex`, `.tx`, `.rat`, `.png`, `.exr` -> `texture`
- `.../publish/...` -> `publish`
- `.../playblast/...`, `.mov`, `.mp4` -> `playblast`
- else -> `other`

Keep rules in one readable config file. No hardcoded sprawl.

---

## 11) Runtime Behavior and Reliability

## 11.1 Fail-open policy

Telemetry must never raise exceptions to the caller for:

- queue full
- write failures
- serialization failures
- validation failures

Instead:
- drop event (count it)
- emit local log at debug/warning level
- continue operation

Why:
- Zero artist disruption is non-negotiable.

## 11.2 Queue and writer defaults

- In-memory queue max: `5000` events
- Flush interval: `1000 ms`
- Batch size: `100` events/write
- File rotate size: `8 MB`
- Local retention: `7 days`

These defaults are intentionally conservative and easy to reason about.

## 11.3 Local spool directory

Default priority:

1. `PIPE_TELEMETRY_SPOOL_DIR` if set
2. Linux: `${XDG_STATE_HOME:-~/.local/state}/sandwich-pipeline/telemetry`
3. Windows: `%LOCALAPPDATA%/sandwich-pipeline/telemetry`
4. Fallback: `${TMPDIR|TEMP}/sandwich-pipeline-telemetry`

Why:
- Avoids fragile shared-lock writes to network storage.
- Keeps telemetry durable across DCC sessions.

---

## 12) Configuration Contract

Environment variables to support:

- `PIPE_TELEMETRY_ENABLED` (`0|1`, default `1`)
- `PIPE_TELEMETRY_LEVEL` (`minimal|standard|verbose`, default `standard`)
- `PIPE_TELEMETRY_SPOOL_DIR` (optional path override)
- `PIPE_TELEMETRY_QUEUE_MAX` (default `5000`)
- `PIPE_TELEMETRY_FLUSH_MS` (default `1000`)
- `PIPE_TELEMETRY_MAX_EVENT_BYTES` (default `65536`)
- `PIPE_TELEMETRY_ROTATE_MB` (default `8`)
- `PIPE_TELEMETRY_RETENTION_DAYS` (default `7`)
- `PIPE_TELEMETRY_INCLUDE_STACKTRACE` (`0|1`, default `0`)

Why levels:
- `minimal` can be used on heavy render nodes to reduce event volume.
- `verbose` helps temporary investigations.

---

## 13) Self-Documentation Requirements

## 13.1 Registry as source of truth

`registry.py` must be the canonical contract for all event types.

## 13.2 Auto-generated contract artifact

Add command:

`python -m pipe.telemetry.docs > docs/telemetry/EVENT_CONTRACT.md`

The generated doc should include:
- event type
- description
- required payload fields
- status values
- owner module
- example payload

Why:
- Keeps docs synchronized with code.
- Makes reviews and onboarding faster.

## 13.3 Inline code comments

Add short comments only where behavior is non-obvious:
- why certain fields are omitted for privacy
- why truncation or sampling is done
- why event emitted at that layer instead of deeper layers

---

## 14) Schema Evolution Rules

1. `schema_version` starts at `1.0`.
2. Additive fields are allowed in minor upgrades (`1.1`).
3. Removing or changing semantics requires major bump (`2.0`).
4. Event type renames are discouraged; prefer deprecating old types after overlap period.
5. Unknown extra payload fields must be tolerated by consumers.

Why:
- Prevents brittle coupling with downstream tooling.

---

## 15) Security and Privacy Guardrails

- Never include:
  - ShotGrid credentials
  - Full environment variable values
  - Raw command lines containing secrets
- Whitelist only safe env keys when needed
- Truncate exception text and stack traces to configured limits
- Normalize paths to avoid leaking user home specifics when unnecessary

Why:
- Telemetry stores broad operational context; it should remain safe to share with production leadership and engineering.

---

## 16) Performance Budget

Target overhead per emit call:

- Fast path (queue push): `< 1 ms` on average
- P95 end-to-end emit API latency: `< 3 ms`

Writer thread handles disk I/O out-of-band.

Why:
- Keeps telemetry impact well below artist perception and typical UI operations.

---

## 17) Testing Plan

## 17.1 Unit tests

- Contract validation:
  - required envelope fields
  - required payload fields per event type
  - unknown event type behavior
- Truncation behavior for oversized events
- Queue overflow handling (drops counted, no exceptions)
- File rotation and retention

## 17.2 Integration tests

- Simulate publish call and verify JSONL contains event
- Simulate error paths and verify structured `error.code`
- Simulate process exit and verify flush-on-exit

## 17.3 CI guardrails

- Fail if emitted event type not in registry
- Fail if registry docs are stale (if auto-generated artifact committed)

---

## 18) Rollout Plan (Pipeline-Only)

## Phase 1 (1 week): Foundation

- Add telemetry package (`pipe.telemetry`)
- Add registry + envelope contract
- Add local spool writer
- Integrate `dcc.launch`, publish terminal events, and component build events

Success criteria:
- No user-facing behavior changes
- Events reliably written locally in both Windows and Linux sessions

## Phase 2 (1 week): Storage and texture visibility

- Add texture export/convert events
- Add `storage_scan.py` and storage bucket events
- Add file open/create/setup events

Success criteria:
- You can answer: "What categories consume most space?" from emitted events

## Phase 3 (1 week): Render submission context

- Instrument Tractor LOP submission events
- Add playblast events
- Stabilize error code taxonomy

Success criteria:
- You can correlate job submissions with render outcomes in downstream analytics

---

## 19) Suggested Error Code Taxonomy (Initial)

- `DCC_LAUNCH_FAILED`
- `PUBLISH_PRECHECK_FAILED`
- `USD_EXPORT_FAILED`
- `PUBLISH_COPY_FAILED`
- `HOUDINI_BUILD_FAILED`
- `HOUDINI_BUILD_RESULT_PARSE_FAILED`
- `TEXTURE_EXPORT_FAILED`
- `TEXTURE_CONVERSION_FAILED`
- `FILE_OPEN_FAILED`
- `FILE_CREATE_FAILED`
- `SHOT_SETUP_FAILED`
- `PLAYBLAST_FAILED`
- `TRACTOR_SPOOL_FAILED`
- `STORAGE_SCAN_FAILED`

Why fixed codes:
- Analytics needs stable grouping keys; exception strings are too variable.

---

## 20) Minimal API Sketch

```python
# pipe/telemetry/__init__.py
from .emit import emit, emit_exception, new_action_id, timed_block
```

```python
# usage example
from pipe.telemetry import emit, new_action_id

action_id = new_action_id()
emit(
    "publish.asset.usd",
    status="success",
    action_id=action_id,
    scope={"asset": asset.name, "department": "model"},
    metrics={"duration_ms": duration_ms},
    payload={"publish_path": str(path), "variant": variant},
)
```

Guidelines:
- Prefer one terminal event per operation with `duration_ms`.
- Use start events only where operation lasts long enough to need progress tracing.

---

## 21) Implementation Checklist

- [ ] Add `pipe.telemetry` package and wiring
- [ ] Add registry + contract validation
- [ ] Add local spool writer + retention
- [ ] Instrument:
  - [ ] `software/baseclass.py`
  - [ ] `pipe/m/publish/publisher.py`
  - [ ] `pipe/m/publish/asset.py`
  - [ ] `pipe/h/assetbuilder.py`
  - [ ] `pipe/sp/export.py`
  - [ ] `pipe/texconverter.py`
  - [ ] `pipe/util/filemanager.py`
  - [ ] `pipe/h/hipfile/shot.py`
  - [ ] `pipe/util/playblaster.py`
  - [ ] Tractor LOP PythonModules
- [ ] Add `storage_scan.py`
- [ ] Add tests and CI checks
- [ ] Generate contract docs

---

## 22) What makes this the lightest useful version

This spec is intentionally minimal in these ways:

- Uses JSONL files instead of service dependencies
- Emits only terminal high-signal events first
- Keeps event schema stable and human-readable
- Leverages existing structured outputs (asset builder JSON, existing SG context)
- Defers centralized ingestion and dashboards to your separate tool

It is still future-safe because:

- contract versioning is explicit
- event namespace is extensible
- registry-driven documentation keeps entropy low
- correlation IDs and scope fields support richer analytics later

