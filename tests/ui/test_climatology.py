import numpy as np
import pandas as pd
import pytest

from app.services.climatology import monthly_climatology, monthly_values


def july(values=1.0) -> pd.Series:
    return pd.Series(values, index=pd.date_range("2005-07-01", "2005-07-31"), dtype=float)


def one(daily, kind, estimated=None) -> pd.Series:
    table = monthly_values(daily, kind, estimated)
    assert len(table) == 1
    return table.iloc[0]


def test_full_month_sum_is_valid():
    row = one(july(2.0), "sum")
    assert row["valid"] and row["value"] == pytest.approx(62.0) and row["n_days"] == 31


def test_sum_with_one_missing_day_is_invalid():
    s = july(); s.iloc[10] = np.nan
    row = one(s, "sum")
    assert not row["valid"] and row["reason"] == "missing days" and np.isnan(row["value"])


@pytest.mark.parametrize("n_missing, valid", [(10, True), (11, False)])
def test_mean_allows_up_to_ten_scattered_missing_days(n_missing, valid):
    s = july(); s.iloc[0:2 * n_missing:2] = np.nan   # every other day: never 2 in a row
    row = one(s, "mean")
    assert bool(row["valid"]) is valid and row["n_missing"] == n_missing
    if not valid:
        assert row["reason"] == "11+ missing days"


@pytest.mark.parametrize("run, valid", [(4, True), (5, False)])
def test_mean_rejects_five_consecutive_missing_days(run, valid):
    s = july(); s.iloc[3:3 + run] = np.nan
    row = one(s, "mean")
    assert bool(row["valid"]) is valid and row["max_gap"] == run
    if not valid:
        assert row["reason"] == "5+ consecutive missing days"


@pytest.mark.parametrize("n_est, valid", [(10, True), (11, False)])
def test_at_most_ten_estimated_days(n_est, valid):
    est = pd.Series(False, index=july().index); est.iloc[0:2 * n_est:2] = True
    row = one(july(), "sum", est)
    assert bool(row["valid"]) is valid and row["n_estimated"] == n_est
    if not valid:
        assert row["reason"] == "more than 10 estimated days"


@pytest.mark.parametrize("run, valid", [(4, True), (5, False)])
def test_estimated_days_not_five_in_a_row(run, valid):
    est = pd.Series(False, index=july().index); est.iloc[0:run] = True
    row = one(july(), "sum", est)
    assert bool(row["valid"]) is valid and row["max_est_run"] == run


def test_days_outside_the_series_count_as_missing():
    s = pd.Series(1.0, index=pd.date_range("2005-07-15", "2005-08-31"))
    table = monthly_values(s, "sum")
    assert list(table["month"]) == [7, 8]
    assert table.iloc[0]["n_missing"] == 14 and not table.iloc[0]["valid"]
    assert table.iloc[1]["valid"]


def test_empty_series_gives_empty_table():
    assert monthly_values(pd.Series(dtype=float), "sum").empty


def five_julys(valid_years: int) -> pd.DataFrame:
    rows = [{"year": 2000 + i, "month": 7, "value": 10.0 * (i + 1), "valid": i < valid_years} for i in range(5)]
    return pd.DataFrame(rows)


@pytest.mark.parametrize("valid_years, ok", [(4, True), (3, False)])
def test_climatology_needs_eighty_percent_of_years(valid_years, ok):
    clim = monthly_climatology(five_julys(valid_years)).set_index("month")
    assert bool(clim.loc[7, "ok"]) is ok
    assert clim.loc[7, "n_valid"] == valid_years and clim.loc[7, "n_years"] == 5
    assert clim.loc[7, "mean"] == pytest.approx(np.mean([10.0 * (i + 1) for i in range(valid_years)]))


def test_climatology_has_twelve_months_even_without_data():
    clim = monthly_climatology(five_julys(5))
    assert list(clim["month"]) == list(range(1, 13))
    assert clim.set_index("month").loc[1, "n_years"] == 0 and not clim.set_index("month").loc[1, "ok"]
