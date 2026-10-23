"""Tests for StreamflowPreprocessor and ObservationWriter."""

from __future__ import annotations

import pandas as pd
import pytest

from swatprep.config import StreamflowConfig
from swatprep.core.streamflow import StreamflowPreprocessor
from swatprep.errors import InputValidationError
from swatprep.qa import failures


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cfg(path, **kwargs) -> StreamflowConfig:
    return StreamflowConfig(path=path, **kwargs)


# ---------------------------------------------------------------------------
# Loading and validation
# ---------------------------------------------------------------------------


def test_streamflow_loads(streamflow_csv):
    cfg = _make_cfg(streamflow_csv)
    result = StreamflowPreprocessor(cfg).run()
    assert result.units == "m3s"
    assert "ST001" in result.daily.columns


def test_daily_shape(streamflow_csv):
    cfg = _make_cfg(streamflow_csv)
    result = StreamflowPreprocessor(cfg).run()
    assert len(result.daily) == 10  # 10-day fixture


def test_no_failures_on_clean_data(streamflow_csv):
    cfg = _make_cfg(streamflow_csv)
    result = StreamflowPreprocessor(cfg).run()
    assert not failures(result.qa)


def test_missing_column_raises(tmp_dir):
    bad_csv = tmp_dir / "bad.csv"
    bad_csv.write_text("date,station_id\n2000-01-01,ST001\n", encoding="utf-8")
    cfg = _make_cfg(bad_csv)
    with pytest.raises(InputValidationError, match="missing columns"):
        StreamflowPreprocessor(cfg).run()


def test_custom_column_names(tmp_dir):
    csv = tmp_dir / "custom.csv"
    csv.write_text(
        "time,gauge,discharge\n2000-01-01,G1,5.5\n2000-01-02,G1,6.0\n",
        encoding="utf-8",
    )
    cfg = _make_cfg(csv, date_col="time", station_id_col="gauge", value_col="discharge")
    result = StreamflowPreprocessor(cfg).run()
    assert "G1" in result.daily.columns


def test_negative_value_produces_warn_qa(tmp_dir):
    csv = tmp_dir / "neg.csv"
    csv.write_text(
        "date,station_id,flow\n2000-01-01,ST001,-1.0\n2000-01-02,ST001,5.0\n",
        encoding="utf-8",
    )
    cfg = _make_cfg(csv)
    result = StreamflowPreprocessor(cfg).run()
    assert any(c.name == "streamflow_negative" for c in result.qa)


def test_missing_values_produce_warn_qa(tmp_dir):
    csv = tmp_dir / "miss.csv"
    csv.write_text(
        "date,station_id,flow\n2000-01-01,ST001,\n2000-01-02,ST001,5.0\n",
        encoding="utf-8",
    )
    cfg = _make_cfg(csv)
    result = StreamflowPreprocessor(cfg).run()
    assert any("missing:streamflow" in c.name for c in result.qa)
    # warn, not fail
    assert not failures(result.qa)


def test_units_mm_preserved(tmp_dir):
    csv = tmp_dir / "mm.csv"
    csv.write_text(
        "date,station_id,flow\n2000-01-01,ST001,10.0\n",
        encoding="utf-8",
    )
    cfg = _make_cfg(csv, units="mm")
    result = StreamflowPreprocessor(cfg).run()
    assert result.units == "mm"


# ---------------------------------------------------------------------------
# ObservationWriter
# ---------------------------------------------------------------------------


def test_observation_writer_creates_files(streamflow_csv, tmp_dir):
    from swatprep.writers.observations import ObservationWriter

    cfg = _make_cfg(streamflow_csv)
    result = StreamflowPreprocessor(cfg).run()
    written = ObservationWriter(result, tmp_dir / "obs").write()

    names = [p.name for p in written]
    assert "streamflow_ST001.csv" in names
    assert "streamflow_meta.csv" in names


def test_observation_csv_has_correct_columns(streamflow_csv, tmp_dir):
    from swatprep.writers.observations import ObservationWriter

    cfg = _make_cfg(streamflow_csv)
    result = StreamflowPreprocessor(cfg).run()
    out = tmp_dir / "obs"
    ObservationWriter(result, out).write()

    df = pd.read_csv(out / "streamflow_ST001.csv")
    assert "date" in df.columns
    assert "flow_m3s" in df.columns
    assert len(df) == 10


def test_meta_csv_has_station_info(streamflow_csv, tmp_dir):
    from swatprep.writers.observations import ObservationWriter

    cfg = _make_cfg(streamflow_csv)
    result = StreamflowPreprocessor(cfg).run()
    out = tmp_dir / "obs"
    ObservationWriter(result, out).write()

    meta = pd.read_csv(out / "streamflow_meta.csv")
    assert "station_id" in meta.columns
    assert "ST001" in meta["station_id"].values


# ---------------------------------------------------------------------------
# format: per_station (file = one station, columns date + discharge)
# ---------------------------------------------------------------------------


def test_per_station_single_file_uses_file_stem_as_station(tmp_path):
    f = tmp_path / "Q_HT_0006.csv"
    f.write_text('"date","discharge"\n1958-01-01,3\n1958-01-02,3.88\n1958-01-03,\n', encoding="utf-8")
    result = StreamflowPreprocessor(_make_cfg(f, format="per_station")).run()
    assert list(result.daily.columns) == ["Q_HT_0006"]
    assert result.daily["Q_HT_0006"].iloc[1] == 3.88 and len(result.daily) == 3
    assert not failures(result.qa)


def test_per_station_folder_reads_all_matching_files(tmp_path):
    for sid, v in (("Q_HT_0001", 1), ("Q_HT_0002", 2)):
        (tmp_path / f"{sid}.csv").write_text(f"date,discharge\n2000-01-01,{v}\n2000-01-02,{v}\n")
    (tmp_path / "other.csv").write_text("date,discharge\n2000-01-01,9\n")
    result = StreamflowPreprocessor(_make_cfg(tmp_path, format="per_station")).run()
    assert list(result.daily.columns) == ["Q_HT_0001", "Q_HT_0002"]


def test_long_format_error_hints_at_per_station(tmp_path):
    f = tmp_path / "Q_HT_0006.csv"
    f.write_text("date,discharge\n2000-01-01,1\n", encoding="utf-8")
    with pytest.raises(InputValidationError, match="format: per_station"):
        StreamflowPreprocessor(_make_cfg(f)).run()


def test_stations_filter_selects_files_and_reports_missing(tmp_path):
    for sid in ("Q_HT_0001", "Q_HT_0002", "Q_HT_0003"):
        (tmp_path / f"{sid}.csv").write_text("date,discharge\n2000-01-01,1\n2000-01-02,2\n")
    cfg = _make_cfg(tmp_path, format="per_station", stations=["Q_HT_0003", "Q_HT_0001"])
    assert list(StreamflowPreprocessor(cfg).run().daily.columns) == ["Q_HT_0001", "Q_HT_0003"]
    with pytest.raises(InputValidationError, match="Q_HT_0099"):
        StreamflowPreprocessor(_make_cfg(tmp_path, format="per_station", stations=["Q_HT_0099"])).run()


def test_stations_filter_long_format(streamflow_csv):
    with pytest.raises(InputValidationError, match="NOPE"):
        StreamflowPreprocessor(_make_cfg(streamflow_csv, stations=["NOPE"])).run()
    r = StreamflowPreprocessor(_make_cfg(streamflow_csv, stations=["ST001"])).run()
    assert list(r.daily.columns) == ["ST001"]
