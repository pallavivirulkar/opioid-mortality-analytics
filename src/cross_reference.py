"""
Merges mortality (this project) with CMS prescribing data (Project 2 in the
portfolio) for the multi-project narrative thread: does county-level
opioid-prescribing intensity correlate with mortality, and does that
relationship shift over time (e.g. prescribing falls after policy changes
while mortality keeps rising due to illicit fentanyl)?
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def merge_mortality_and_prescribing(mortality_df: pd.DataFrame, prescribing_df: pd.DataFrame) -> pd.DataFrame:
    """Inner join on (county_fips, year). Keeps both raw columns plus a
    same-year and a 1-year-lagged prescribing rate (prescribing today can
    plausibly affect mortality with a delay, e.g. dependency -> overdose)."""
    merged = mortality_df.merge(
        prescribing_df,
        on=["county_fips", "year"],
        how="inner",
        suffixes=("", "_rx"),
    )

    lagged = prescribing_df.copy()
    lagged["year"] = lagged["year"] + 1
    lagged = lagged.rename(columns={"opioid_prescribing_rate": "opioid_prescribing_rate_lag1"})[
        ["county_fips", "year", "opioid_prescribing_rate_lag1"]
    ]
    merged = merged.merge(lagged, on=["county_fips", "year"], how="left")
    return merged


def correlation_by_year(
    merged_df: pd.DataFrame,
    mortality_col: str = "crude_rate",
    prescribing_col: str = "opioid_prescribing_rate",
) -> pd.DataFrame:
    """Pearson correlation between mortality rate and prescribing rate,
    computed separately per year, so you can see the relationship strengthen
    or weaken over time rather than collapsing it into one number."""
    rows = []
    for year, g in merged_df.dropna(subset=[mortality_col, prescribing_col]).groupby("year"):
        if len(g) < 3:
            continue
        r, p = stats.pearsonr(g[mortality_col], g[prescribing_col])
        rows.append({"year": year, "n_counties": len(g), "pearson_r": r, "p_value": p})
    return pd.DataFrame(rows).sort_values("year").reset_index(drop=True)


def overall_correlation(
    merged_df: pd.DataFrame,
    mortality_col: str = "crude_rate",
    prescribing_col: str = "opioid_prescribing_rate",
) -> dict:
    """Single overall Pearson r + p-value + simple OLS slope/intercept across
    all county-years pooled, for a headline stat."""
    clean = merged_df.dropna(subset=[mortality_col, prescribing_col])
    if len(clean) < 3:
        return {"pearson_r": np.nan, "p_value": np.nan, "n": len(clean)}
    r, p = stats.pearsonr(clean[mortality_col], clean[prescribing_col])
    slope, intercept, *_ = stats.linregress(clean[prescribing_col], clean[mortality_col])
    return {
        "pearson_r": r,
        "p_value": p,
        "n": len(clean),
        "slope": slope,
        "intercept": intercept,
    }
