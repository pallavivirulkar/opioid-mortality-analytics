import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src.data_processing import (
    load_mortality_data,
    load_prescribing_data,
    load_national_mortality_trend,
    _standardize_fips,
    _strip_footer_notes,
    data_source_status,
)


def test_load_mortality_data_sample_defaults_work():
    df = load_mortality_data()
    expected_cols = {"county", "county_fips", "state", "year", "deaths", "population", "crude_rate", "is_suppressed"}
    assert expected_cols.issubset(df.columns)
    assert len(df) > 0
    assert df["county_fips"].str.len().eq(5).all()
    assert df["year"].notna().all()


def test_load_mortality_data_flags_suppressed_rows():
    df = load_mortality_data()
    suppressed = df[df["is_suppressed"]]
    assert suppressed["deaths"].isna().all()


def test_load_prescribing_data_sample_defaults_work():
    df = load_prescribing_data()
    expected_cols = {"state", "county", "county_fips", "year", "opioid_prescribing_rate"}
    assert expected_cols.issubset(df.columns)
    assert len(df) > 0
    assert df["county_fips"].str.len().eq(5).all()


def test_standardize_fips_zero_pads():
    s = pd.Series(["1", "54011", "6037", None])
    result = _standardize_fips(s)
    assert result.iloc[0] == "00001"
    assert result.iloc[1] == "54011"
    assert result.iloc[2] == "06037"


def test_strip_footer_notes_removes_cdc_wonder_citation_block():
    raw = 'County,Deaths\n"Cabell County, WV",13\n"---"\n"Dataset: something"\n'
    cleaned = _strip_footer_notes(raw)
    assert "---" not in cleaned
    assert "Dataset:" not in cleaned
    assert "Cabell County" in cleaned


def test_data_source_status_reports_sample_when_no_raw_files():
    status = data_source_status()
    assert "mortality_is_real" in status
    assert "prescribing_is_real" in status
    assert "national_is_real" in status


def test_load_national_mortality_trend_returns_none_when_missing(tmp_path):
    result = load_national_mortality_trend(tmp_path / "does_not_exist.csv")
    assert result is None


def test_load_national_mortality_trend_parses_real_export_format(tmp_path):
    # Mirrors the real CDC WONDER "Group Results By: National + Year" export
    # shape: a leading blank Notes column, and a footer "Total" row whose
    # Year cell is blank (must be dropped, not misread as a real year).
    content = (
        '"Notes"\t"Year"\t"Year Code"\tDeaths\tPopulation\tCrude Rate\n'
        '\t"2018"\t"2018"\t67367\t327167434\t20.6\n'
        '\t"2019"\t"2019"\t70630\t328239523\t21.5\n'
        '"Total"\t\t\t137997\t655406957\t21.1\n'
        '"---"\n'
        '"Dataset: Multiple Cause of Death, 2018-2024, Single Race"\n'
    )
    f = tmp_path / "cdc_wonder_national.csv"
    f.write_text(content)

    result = load_national_mortality_trend(f)
    assert result is not None
    assert list(result["year"]) == [2018, 2019]
    assert result.loc[result["year"] == 2018, "crude_rate"].iloc[0] == 20.6
    assert result.loc[result["year"] == 2019, "deaths"].iloc[0] == 70630
