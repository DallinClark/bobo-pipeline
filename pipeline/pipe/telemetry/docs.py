"""Generate telemetry contract documentation from the registry."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from .registry import ERROR_CODES, EVENT_DEFINITIONS, SCHEMA_VERSION

DEFAULT_OUTPUT_PATH = Path("docs/telemetry/EVENT_CONTRACT.md")


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


def write_contract_markdown(path: Path) -> None:
    """Write generated contract markdown to ``path``."""

    content = render_contract_markdown()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def is_contract_markdown_current(path: Path) -> bool:
    """Return ``True`` when ``path`` exactly matches generated contract content."""

    expected = render_contract_markdown()
    try:
        current = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False
    return current == expected


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate telemetry event contract markdown from the registry."
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output path. If omitted, writes to stdout.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero when output file does not match generated content.",
    )
    args = parser.parse_args(argv)

    if args.check:
        output_path = args.output or DEFAULT_OUTPUT_PATH
        if is_contract_markdown_current(output_path):
            return 0
        sys.stderr.write(
            "Telemetry event contract is stale. Regenerate with:\n"
            "  python -m pipe.telemetry.docs > docs/telemetry/EVENT_CONTRACT.md\n"
        )
        return 1

    if args.output is None:
        sys.stdout.write(render_contract_markdown())
        return 0

    write_contract_markdown(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
