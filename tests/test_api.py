"""Tests for swatprep.api orchestration behavior."""

from __future__ import annotations

import pytest

from swatprep import SWATPrepProject
from swatprep.config import SWATPrepConfig


def test_prepare_not_implemented_does_not_create_output_dir(tmp_dir):
    output_dir = tmp_dir / "output"
    cfg = SWATPrepConfig.model_validate({
        "project": {
            "name": "test_basin",
            "crs": "EPSG:32648",
            "output_dir": output_dir,
        }
    })

    project = SWATPrepProject(cfg)

    with pytest.raises(NotImplementedError):
        project.prepare()

    assert not output_dir.exists()
