import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import pytest

from src.time_series import (
    national_trend,
    decompose_series,
    yoy_change,
    compute_hotspot_scores,
    forecast_mortality_rate,
)


def make_fixture():
    # Two counties: one flat, one accelerating in the recent years.
    rows = []
    for year in range(2015, 2024):
        rows.append(dict(county_fips="00001", county="Flat County", state="AA",
                          year=year, deaths=100, population=1_000_000, crude_rate=10.0))
        accel_rate = 10.0 + max(0, year - 2019) ** 2 * 1.5
        rows.append(dict(county_fips="00002", county="Accelerating County", state="BB",
                          year=year, deaths=int(accel_rate * 10), population=1_000_000, crude_rate=accel_rate))
    return pd.DataFrame(rows)


def test_national_trend_weights_by_population():
    df = make_fixture()
    trend = national_trend(df)
    assert set(trend.columns) >= {"year", "national_rate"}
    assert len(trend) == 9
    assert (trend["national_rate"] > 0).all()


def test_decompose_series_short_annual_uses_fallback():
    s = pd.Series([10, 11, 12, 14, 18, 25], index=range(2018, 2024))
    result = decompose_series(s, period=12)
    assert result.method.startswith("polyfit")
    assert len(result.trend) == len(s)
    # residuals should sum close to zero for a polynomial fit
    assert abs(result.resid.sum()) < 1e-6 * len(s) + 1


def test_yoy_change_computes_percent_change_per_county():
    df = make_fixture()
    result = yoy_change(df)
    flat = result[result["county_fips"] == "00001"].sort_values("year")
    # flat county has constant crude_rate -> 0% change after first year
    assert flat["yoy_pct_change"].dropna().eq(0).all()


def test_compute_hotspot_scores_ranks_accelerating_county_first():
    df = make_fixture()
    scores = compute_hotspot_scores(df, recent_years=3)
    assert scores.iloc[0]["county_fips"] == "00002"
    assert scores.iloc[0]["hotspot_zscore"] > scores.iloc[-1]["hotspot_zscore"]


def test_compute_hotspot_scores_handles_empty_input():
    empty = pd.DataFrame(columns=["county_fips", "county", "state", "year", "crude_rate"])
    result = compute_hotspot_scores(empty)
    assert result.empty


def test_forecast_mortality_rate_perfect_line_has_near_zero_backtest_error():
    # Perfectly linear series -> a linear-trend model should backtest almost exactly.
    s = pd.Series([10.0 + 2 * i for i in range(8)], index=range(2016, 2024))
    fc = forecast_mortality_rate(s, forecast_years=2)
    assert fc.backtest_year == 2023
    assert fc.backtest_mae < 1e-6
    assert fc.backtest_pct_error < 1e-6
    assert fc.future_years == [2024, 2025]
    # forecast should continue the +2/year trend
    assert abs(fc.forecast_values[0] - 26.0) < 1e-6


def test_forecast_mortality_rate_short_series_skips_backtest():
    s = pd.Series([10.0, 12.0, 15.0], index=range(2021, 2024))
    fc = forecast_mortality_rate(s, forecast_years=1)
    assert fc.backtest_mae is None
    assert fc.backtest_year is None
    assert len(fc.forecast_values) == 1
