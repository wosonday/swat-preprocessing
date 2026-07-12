"""ManifestWriter: produce manifest.json and qa_report.md after build().

manifest.json — machine-readable record of the output package:
  project, created_at, domains, output_dir, files, qa_summary

qa_report.md — human-readable QA results, one table per domain.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..qa import QACheck


def write_manifest(
    output_dir: Path,
    project_name: str,
    domains: list[str],
    all_qa: list[QACheck],
) -> tuple[Path, Path]:
    """Write manifest.json and qa_report.md; return both paths."""
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = _write_manifest_json(output_dir, project_name, domains, all_qa)
    report_path = _write_qa_report(output_dir, project_name, all_qa)

    return manifest_path, report_path


# ---------------------------------------------------------------------------
# manifest.json
# ---------------------------------------------------------------------------


def _write_manifest_json(
    output_dir: Path,
    project_name: str,
    domains: list[str],
    all_qa: list[QACheck],
) -> Path:
    # Inventory output files by sub-directory
    files: dict[str, list[str]] = {}
    for subdir in sorted(output_dir.iterdir()):
        if subdir.is_dir() and subdir.name not in ("__pycache__",):
            files[subdir.name] = sorted(p.name for p in subdir.iterdir() if p.is_file())

    qa_summary = {
        "pass": sum(1 for c in all_qa if c.status == "pass"),
        "warn": sum(1 for c in all_qa if c.status == "warn"),
        "fail": sum(1 for c in all_qa if c.status == "fail"),
    }

    manifest = {
        "schema_version": "1.0",
        "project": project_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "domains_processed": domains,
        "output_dir": str(output_dir),
        "files": files,
        "qa_summary": qa_summary,
    }

    path = output_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# qa_report.md
# ---------------------------------------------------------------------------


def _write_qa_report(
    output_dir: Path,
    project_name: str,
    all_qa: list[QACheck],
) -> Path:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [
        f"# QA Report — {project_name}",
        f"",
        f"Generated: {now}  ",
        f"Total checks: {len(all_qa)} "
        f"({sum(1 for c in all_qa if c.status=='pass')} pass, "
        f"{sum(1 for c in all_qa if c.status=='warn')} warn, "
        f"{sum(1 for c in all_qa if c.status=='fail')} fail)",
        "",
        "| Status | Check | Message |",
        "|--------|-------|---------|",
    ]

    _ICON = {"pass": "✅", "warn": "⚠️", "fail": "❌"}
    for c in all_qa:
        icon = _ICON.get(c.status, "?")
        # Escape pipe chars in message
        msg = c.message.replace("|", "\\|")
        lines.append(f"| {icon} {c.status} | `{c.name}` | {msg} |")

    path = output_dir / "qa_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
