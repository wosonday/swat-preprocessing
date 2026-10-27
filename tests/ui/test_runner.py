from app.services import runner


def test_validate_example_passes(example_project):
    result = runner.validate(example_project)
    assert result.ok
    assert result.count("fail") == 0
    assert result.count("pass") == 9


def test_validate_reports_missing_file(example_project):
    (example_project.parent / "data" / "dem_30m.tif").unlink()
    result = runner.validate(example_project)
    assert not result.ok
    failed = [c.name for c in result.checks if c.status == "fail"]
    assert failed == ["file_exists:dem.path"]


def test_schema_error_is_reported_not_raised(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("project:\n  name: X\n", encoding="utf-8")  # crs missing
    result = runner.validate(cfg)
    assert not result.ok
    assert "project.crs" in result.error


def test_unexpected_error_is_captured(example_project, monkeypatch):
    def boom(_path):
        raise RuntimeError("boom")

    monkeypatch.setattr(runner.SWATPrepProject, "from_config", boom)
    result = runner.validate(example_project)
    assert not result.ok
    assert "boom" in result.error
    assert result.traceback is not None


def test_build_example_end_to_end(example_project):
    result = runner.build(example_project)
    assert result.ok, result.error
    assert result.count("fail") == 0
    assert result.manifest_path is not None and result.manifest_path.is_file()
    assert result.output_dir == example_project.parent / "output"
