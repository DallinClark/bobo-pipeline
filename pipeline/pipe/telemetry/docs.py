"""Generate telemetry contract documentation from the registry."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from .registry import ERROR_CODES, EVENT_DEFINITIONS, SCHEMA_VERSION


def render_contract_markdown() -> str:
    """Return a markdown document generated from the telemetry registry."""

    lines: list[str] = []
    lines.append(f"# Telemetry Event Contract (v{SCHEMA_VERSION})")
    lines.append("")
    lines.append("Generated from `pipe.telemetry.registry`.")
    lines.append("")
    lines.append("## Global")
    lines.append("")
    lines.append(f"- `schema_version`: `{SCHEMA_VERSION}`")
    lines.append(
        "- Event names, required fields, and status values are registry-driven."
    )
    lines.append("")
    lines.append("## Stable Error Codes")
    lines.append("")
    for code in ERROR_CODES:
        lines.append(f"- `{code}`")
    lines.append("")
    lines.append("## Event Types")
    lines.append("")

    for event in EVENT_DEFINITIONS:
        lines.append(f"### `{event.event_type}`")
        lines.append("")
        lines.append(f"- Description: {event.description}")
        lines.append(f"- Owner module: `{event.owner_module}`")
        lines.append(f"- Status values: `{', '.join(event.status_values)}`")
        if event.required_payload_fields:
            lines.append(
                "- Required payload fields: "
                + ", ".join(f"`{field}`" for field in event.required_payload_fields)
            )
        else:
            lines.append("- Required payload fields: (none)")
        if event.required_metrics_fields:
            lines.append(
                "- Required metrics fields: "
                + ", ".join(f"`{field}`" for field in event.required_metrics_fields)
            )
        else:
            lines.append("- Required metrics fields: (none)")
        if event.error_codes:
            lines.append(
                "- Allowed error codes: "
                + ", ".join(f"`{code}`" for code in event.error_codes)
            )
        else:
            lines.append("- Allowed error codes: (none)")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate telemetry event contract markdown from the registry."
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output path. If omitted, writes to stdout.",
    )
    args = parser.parse_args(argv)

    content = render_contract_markdown()
    if args.output is None:
        sys.stdout.write(content)
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
