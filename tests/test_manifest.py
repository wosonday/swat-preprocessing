"""Tests for manifest.json and qa_report.md generation."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import date

import pytest

from swatprep.api import SWATPrepProject, PrepareResult
from swatprep.config import SWATPrepConfig
from swatprep.writers.manifest import write_manifest
from swatprep.qa import QACheck


# ---------------------------------------------------------------------------
# write_manifest unit tests
# ---------------------------------------------------------------------------


def test_manifest_json_created(tmp_dir):
    out = tmp_dir / "output"
    out.mkdir()
    (out / "weather").mkdir()
    (out / "weather" / "ST001.pcp").write_text("x")

    manifest_path, _ = write_manifest(out, "test_project", ["weather"], [])
    assert manifest_path.exists()
    assert manifest_path.name == "manifest.json"


def test_manifest_json_content(tmp_dir):
    out = tmp_dir / "output"
    out.mkdir()
    (out / "weather").mkdir()
    (out / "weather" / "ST001.pcp").write_text("x")

    qa = [
        QACheck(name="check_a", status="pass", message="ok"),
        QACheck(name="check_b", status="warn", message="hmm"),
        QACheck(name="check_c", status="fail", message="bad"),
    ]
    manifest_path, _ = write_manifest(out, "basin_test", ["weather"], qa)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert data["project"] == "basin_test"
    assert "weather" in data["domains_processed"]
    assert data["qa_summary"]["pass"] == 1
    assert data["qa_summary"]["warn"] == 1
    assert data["qa_summary"]["fail"] == 1
    assert "schema_version" in data
    assert "created_at" in data


def test_qa_report_md_created(tmp_dir):
    out = tmp_dir / "output"
    out.mkdir()
    qa = [QACheck(name="x", status="pass", message="all good")]
    _, report_path = write_manifest(out, "proj", ["weather"], qa)
    assert report_path.exists()
    assert report_path.name == "qa_report.md"
    content = report_path.read_text(encoding="utf-8")
    assert "pass" in content
    assert "all good" in content


def test_qa_report_contains_all_statuses(tmp_dir):
    out = tmp_dir / "output"
    out.mkdir()
    qa = [
        QACheck(name="p", status="pass", message="ok"),
        QACheck(name="w", status="warn", message="hmm"),
        QACheck(name="f", status="fail", message="bad"),
    ]
    _, report_path = write_manifest(out, "p", [], qa)
    content = report_path.read_text(encoding="utf-8")
    assert "✅" in content
    assert "⚠️" in content
    assert "❌" in content


# ---------------------------------------------------------------------------
# End-to-end: prepare() with weather + streamflow writes manifest
# ---------------------------------------------------------------------------


def test_prepare_writes_manifest_and_report(
    tmp_dir,
    weather_stations_csv,
    weather_data_dir,
    streamflow_csv,
):
    import yaml

    output_dir = tmp_dir / "output"
    config_path = tmp_dir / "config.yaml"
    config_path.write_text(
        yaml.dump({
            "project": {
                "name": "e2e_basin",
                "crs": "EPSG:32648",
                "output_dir": str(output_dir),
            },
            "weather": {
                "stations": str(weather_stations_csv),
                "data_dir": str(weather_data_dir),
                "start": "2000-01-01",
                "end": "2000-01-10",
            },
            "streamflow": {
                "path": str(streamflow_csv),
            },
        }),
        encoding="utf-8",
    )

    result = SWATPrepProject.from_config(config_path).prepare()

    assert result.success
    assert result.manifest_path is not None
    assert result.manifest_path.exists()
    assert (output_dir / "qa_report.md").exists()

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["project"] == "e2e_basin"
    assert "weather" in manifest["domains_processed"]
    assert "streamflow" in manifest["domains_processed"]
    assert manifest["qa_summary"]["fail"] == 0


def test_prepare_no_domains_no_manifest(tmp_dir):
    """No domains → nothing written, manifest_path is None."""
    output_dir = tmp_dir / "output"
    cfg = SWATPrepConfig.model_validate({
        "project": {
            "name": "empty",
            "crs": "EPSG:4326",
            "output_dir": str(output_dir),
        }
    })
    result = SWATPrepProject(cfg).prepare()
    assert result.manifest_path is None
    assert not output_dir.exists()
