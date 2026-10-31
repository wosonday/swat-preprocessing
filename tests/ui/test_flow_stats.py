import numpy as np
import pandas as pd
import pytest

from app.services.flow_stats import fdc, flow_quantile, summary


def test_weibull_quantiles_of_one_to_ninety_nine():
    s = pd.Series(np.arange(1, 100, dtype=float))
    assert flow_quantile(s, 50) == pytest.approx(50)
    assert flow_quantile(s, 5) == pytest.approx(95)
    assert flow_quantile(s, 95) == pytest.approx(5)


def test_fdc_is_sorted_and_skips_nan():
    curve = fdc(pd.Series([3.0, np.nan, 1.0, 2.0]))
    assert list(curve["flow"]) == [3.0, 2.0, 1.0]
    assert list(curve["exceedance_pct"]) == pytest.approx([25.0, 50.0, 75.0])


@pytest.mark.parametrize("values", [[], [4.0, 4.0, 4.0], [0.0, 0.0]])
def test_degenerate_series_do_not_fail(values):
    s = pd.Series(values, dtype=float)
    q = flow_quantile(s, 50)
    assert (np.isnan(q) if not values else q == values[0])


def test_summary_counts_missing_between_first_and_last_value():
    days = pd.date_range("2000-01-01", periods=6)
    wide = pd.DataFrame({"A": [np.nan, 1.0, np.nan, 3.0, 2.0, np.nan], "B": [np.nan] * 6}, index=days)
    table = summary(wide).set_index("station")
    assert table.loc["A", "pct_missing"] == 25.0       # 1 of the 4 days from Jan 2 to Jan 5
    assert table.loc["A", "max"] == 3.0 and str(table.loc["A", "start"]) == "2000-01-02"
    assert pd.isna(table.loc["B", "mean"])
