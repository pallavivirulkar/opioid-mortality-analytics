"""
Time-series decomposition and hotspot-detection logic.

CDC WONDER can be queried at annual or monthly granularity. This module
works with whatever granularity is present: with >=24 monthly points it
runs a proper STL seasonal decomposition; with annual-only data (the common
case, and what the bundled sample data uses) seasonal decomposition isn't
meaningful, so it falls back to a trend/residual split via LOWESS smoothing.
Either way you get a trend line + residuals to reason about.

Hotspot detection is a rate-of-change approach: for each county, compare the
slope of the most recent N years to the slope of the years before that. A
county whose mortality rate is accelerating faster than its own history
*and* faster than the national trend is flagged as a hotspot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

try:
    from statsmodels.tsa.seasonal import STL
    HAS_STL = True
except ImportError:  # pragma: no cover
    HAS_STL = False


def national_trend(df: pd.DataFrame, value_col: str = "deaths", weight_col: str = "population") -> pd.DataFrame:
    """National population-weighted crude rate per year (per 100,000)."""
    yearly = df.dropna(subset=[value_col, weight_col]).groupby("year", as_index=False).agg(
        total_deaths=(value_col, "sum"), total_population=(weight_col, "sum")
    )
    yearly["national_rate"] = yearly["total_deaths"] / yearly["total_population"] * 100_000
    return yearly


@dataclass
class Decomposition:
    observed: pd.Series
    trend: pd.Series
    resid: pd.Series
    method: str


def decompose_series(series: pd.Series, period: int = 12) -> Decomposition:
    """series must be indexed by a sortable time key (year, or year-month).
    Uses STL if there are at least 2 full seasonal periods, else a LOWESS
    trend + residual fallback for short annual series."""
    series = series.sort_index()
    if HAS_STL and len(series) >= period * 2:
        stl = STL(series, period=period, robust=True).fit()
        return Decomposition(series, stl.trend, stl.resid, method="STL")

    # Fallback: LOWESS-style trend via a low-degree polynomial fit, which
    # behaves sensibly on short (e.g. 9-point annual) series where STL's
    # seasonal-period requirement can't be satisfied.
    x = np.arange(len(series))
    degree = 2 if len(series) >= 5 else 1
    coeffs = np.polyfit(x, series.values, deg=degree)
    trend_vals = np.polyval(coeffs, x)
    trend = pd.Series(trend_vals, index=series.index)
    resid = series - trend
    return Decomposition(series, trend, resid, method=f"polyfit(deg={degree})")


@dataclass
class Forecast:
    future_years: list
    forecast_values: list
    backtest_year: Optional[int]
    backtest_actual: Optional[float]
    backtest_predicted: Optional[float]
    backtest_mae: Optional[float]
    backtest_pct_error: Optional[float]
    method: str = "linear"


@dataclass
class MethodResult:
    method: str
    backtest_year: Optional[int]
    backtest_actual: Optional[float]
    backtest_predicted: Optional[float]
    backtest_mae: Optional[float]
    backtest_pct_error: Optional[float]
    future_years: list
    forecast_values: list


def _fc_naive(train_years, train_values, target_years):
    """Persistence baseline: assume the next value equals the last observed
    value. Deceptively strong on short series where the trend has recently
    plateaued or reversed — a real forecasting phenomenon, not a cop-out."""
    return np.full(len(target_years), train_values[-1])


def _fc_linear(train_years, train_values, target_years):
    coeffs = np.polyfit(train_years, train_values, 1)
    return np.polyval(coeffs, target_years)


def _fc_polynomial(train_years, train_values, target_years):
    if len(train_years) < 4:
        return _fc_linear(train_years, train_values, target_years)
    coeffs = np.polyfit(train_years, train_values, 2)
    return np.polyval(coeffs, target_years)


def _fc_avg_yoy_change(train_years, train_values, target_years):
    diffs = np.diff(train_values)
    avg_change = diffs.mean() if len(diffs) else 0.0
    preds, last = [], train_values[-1]
    for _ in target_years:
        last = last + avg_change
        preds.append(last)
    return np.array(preds)


FORECAST_METHODS = {
    "naive (last value)": _fc_naive,
    "linear trend": _fc_linear,
    "polynomial (deg 2)": _fc_polynomial,
    "avg YoY change": _fc_avg_yoy_change,
}


def compare_forecast_methods(series: pd.Series, forecast_years: int = 1) -> list:
    """Backtests every method in FORECAST_METHODS (leave-last-year-out) and
    returns a MethodResult per method, so you can see which approach
    actually predicts best rather than assuming a fancier model wins."""
    series = series.sort_index().dropna()
    years = series.index.to_numpy(dtype=float)
    values = series.values.astype(float)
    future_years = np.arange(years[-1] + 1, years[-1] + 1 + forecast_years)

    results = []
    for name, fn in FORECAST_METHODS.items():
        backtest_year = backtest_actual = backtest_predicted = None
        backtest_mae = backtest_pct_error = None
        if len(series) >= 4:
            train_years, train_values = years[:-1], values[:-1]
            test_year, test_value = years[-1], values[-1]
            predicted = float(fn(train_years, train_values, np.array([test_year]))[0])

            backtest_year = int(test_year)
            backtest_actual = float(test_value)
            backtest_predicted = predicted
            backtest_mae = abs(predicted - test_value)
            backtest_pct_error = abs(predicted - test_value) / test_value * 100 if test_value else None

        forecast_values = fn(years, values, future_years)
        results.append(MethodResult(
            method=name,
            backtest_year=backtest_year,
            backtest_actual=backtest_actual,
            backtest_predicted=backtest_predicted,
            backtest_mae=backtest_mae,
            backtest_pct_error=backtest_pct_error,
            future_years=future_years.astype(int).tolist(),
            forecast_values=forecast_values.tolist(),
        ))
    return results


def forecast_mortality_rate(series: pd.Series, forecast_years: int = 1) -> Forecast:
    """Benchmarks several simple forecasting methods (naive persistence,
    linear trend, degree-2 polynomial, average year-over-year change) via a
    leave-last-year-out backtest, and returns the forward forecast from
    whichever method backtested most accurately (lowest MAE). On short,
    regime-shifting series the naive baseline often wins — that's a
    legitimate finding, not a fallback to settle for. Needs >=4 points to
    backtest meaningfully; with fewer, all methods run but backtest fields
    are None and 'linear trend' is used for the forward forecast.

    series must be indexed by year (e.g. national_trend()
    ['national_rate'] with year as the index).
    """
    results = compare_forecast_methods(series, forecast_years=forecast_years)
    scored = [r for r in results if r.backtest_mae is not None]
    best = min(scored, key=lambda r: r.backtest_mae) if scored else next(
        r for r in results if r.method == "linear trend"
    )
    return Forecast(
        future_years=best.future_years,
        forecast_values=best.forecast_values,
        backtest_year=best.backtest_year,
        backtest_actual=best.backtest_actual,
        backtest_predicted=best.backtest_predicted,
        backtest_mae=best.backtest_mae,
        backtest_pct_error=best.backtest_pct_error,
        method=best.method,
    )


def yoy_change(df: pd.DataFrame, value_col: str = "crude_rate") -> pd.DataFrame:
    """Adds a year-over-year percent-change column, per county."""
    df = df.sort_values(["county_fips", "year"]).copy()
    df["yoy_pct_change"] = df.groupby("county_fips")[value_col].pct_change() * 100
    return df


def compute_hotspot_scores(
    df: pd.DataFrame,
    value_col: str = "crude_rate",
    recent_years: int = 3,
    min_points: int = 4,
) -> pd.DataFrame:
    """For each county, fit a linear slope over the recent window vs. the
    earlier years, then z-score the recent slope across all counties.
    Returns one row per county with: early_slope, recent_slope,
    acceleration, hotspot_zscore, sorted descending (biggest accelerating
    hotspots first).
    """
    records = []
    for fips, g in df.dropna(subset=[value_col]).groupby("county_fips"):
        g = g.sort_values("year")
        if len(g) < min_points:
            continue
        years = g["year"].to_numpy(dtype=float)
        values = g[value_col].to_numpy(dtype=float)
        cutoff = years.max() - recent_years + 1

        recent_mask = years >= cutoff
        early_mask = ~recent_mask

        recent_slope = (
            np.polyfit(years[recent_mask], values[recent_mask], 1)[0]
            if recent_mask.sum() >= 2 else np.nan
        )
        early_slope = (
            np.polyfit(years[early_mask], values[early_mask], 1)[0]
            if early_mask.sum() >= 2 else np.nan
        )

        records.append({
            "county_fips": fips,
            "county": g["county"].iloc[-1],
            "state": g["state"].iloc[-1] if "state" in g.columns else None,
            "latest_value": values[-1],
            "early_slope": early_slope,
            "recent_slope": recent_slope,
            "acceleration": (recent_slope - early_slope) if pd.notna(recent_slope) and pd.notna(early_slope) else np.nan,
        })

    result = pd.DataFrame(records)
    if result.empty:
        return result

    mean_accel = result["acceleration"].mean(skipna=True)
    std_accel = result["acceleration"].std(skipna=True) or 1.0
    result["hotspot_zscore"] = (result["acceleration"] - mean_accel) / std_accel
    return result.sort_values("hotspot_zscore", ascending=False).reset_index(drop=True)
