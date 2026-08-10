import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from src.cross_reference import (
    merge_mortality_and_prescribing,
    correlation_by_year,
    overall_correlation,
)


def make_fixtures():
    years = list(range(2015, 2020))
    counties = ["00001", "00002", "00003", "00004", "00005"]
    mortality_rows, prescribing_rows = [], []
    rng = np.random.default_rng(0)
    for year in years:
        for i, fips in enumerate(counties):
            rx_rate = 5 + i * 2  # deterministic spread so correlation is well-defined
            mortality_rate = 8 + rx_rate * 0.8 + rng.normal(0, 0.01)
            mortality_rows.append(dict(county_fips=fips, county=f"County {i}", state="AA",
                                        year=year, crude_rate=mortality_rate))
            prescribing_rows.append(dict(county_fips=fips, state="AA", county=f"County {i}",
                                          year=year, opioid_prescribing_rate=rx_rate))
    return pd.DataFrame(mortality_rows), pd.DataFrame(prescribing_rows)


def test_merge_produces_lagged_column():
    m, p = make_fixtures()
    merged = merge_mortality_and_prescribing(m, p)
    assert "opioid_prescribing_rate_lag1" in merged.columns
    assert len(merged) == len(m)  # inner join on matching county-years


def test_overall_correlation_detects_strong_positive_relationship():
    m, p = make_fixtures()
    merged = merge_mortality_and_prescribing(m, p)
    result = overall_correlation(merged)
    assert result["pearson_r"] > 0.95
    assert result["p_value"] < 0.01


def test_correlation_by_year_returns_one_row_per_year():
    m, p = make_fixtures()
    merged = merge_mortality_and_prescribing(m, p)
    by_year = correlation_by_year(merged)
    assert len(by_year) == m["year"].nunique()
    assert (by_year["pearson_r"] > 0.9).all()
