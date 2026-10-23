"""Mọi ví dụ YAML đầy đủ trong tài liệu và file mẫu phải đọc được bằng SWATPrepConfig."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from swatprep.config import SWATPrepConfig

ROOT = Path(__file__).resolve().parents[1]
DOCS = [ROOT / "docs" / "USER_GUIDE_VI.md", ROOT / "docs" / "WEATHER_MISSING_FILL_VI.md",
        ROOT / "README.md", ROOT / "README_VI.md"]


def _complete_blocks():
    out = []
    for md in DOCS:
        if not md.exists():
            continue
        text = md.read_text(encoding="utf-8")
        for i, m in enumerate(re.finditer(r"```yaml\n(.*?)```", text, re.S)):
            body = m.group(1)
            if re.search(r"^project:", body, re.M):
                out.append(pytest.param(body, id=f"{md.name}#{i}"))
    return out


@pytest.mark.parametrize("body", _complete_blocks())
def test_documented_yaml_is_valid(body):
    SWATPrepConfig.model_validate(yaml.safe_load(body))


@pytest.mark.parametrize("name", ["config_minimal.yaml", "config_full.yaml"])
def test_example_configs_load(name):
    cfg = SWATPrepConfig.from_yaml(ROOT / "examples" / name)
    assert cfg.project.crs == "EPSG:32648"


def test_full_example_declares_every_domain():
    cfg = SWATPrepConfig.from_yaml(ROOT / "examples" / "config_full.yaml")
    assert cfg.configured_domains() == ["dem", "landuse", "soil", "weather", "streamflow"]
    assert cfg.weather.fill.netcdf.search_radius == 1
