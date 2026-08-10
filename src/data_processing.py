"""
Loading and cleaning for the two source datasets:

- CDC WONDER Multiple Cause of Death exports (county x year opioid mortality)
- CMS Medicare Part D Opioid Prescribing Rates by Geography exports

Real government exports are messy in predictable ways: CDC WONDER appends
footer/citation notes below the data table and uses the literal strings
"Suppressed" (< 10 deaths) and "Unreliable" (rate based on < 20 deaths)
instead of numbers; column headers vary slightly by export vintage and
CMS occasionally renames a column between yearly files. Every loader here
is alias-tolerant and falls back to the bundled synthetic sample_data/ when
no raw file is present, so the pipeline always runs.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
SAMPLE_DIR = ROOT / "sample_data"

# CDC uses these literal strings for privacy-suppressed / statistically
# unreliable cells instead of leaving them blank.
SUPPRESSED_TOKENS = {"Suppressed", "Unreliable", "Missing", "Not Applicable", ""}

# Column-name aliases seen across different CDC WONDER export configurations.
MORTALITY_COLUMN_ALIASES = {
    "county": ["County", "county"],
    "county_fips": ["County Code", "county_code", "County Code Code", "FIPS"],
    "year": ["Year", "year"],
    "deaths": ["Deaths", "deaths"],
    "population": ["Population", "population"],
    "crude_rate": ["Crude Rate", "crude_rate"],
}

# Column-name aliases across CMS export vintages. If your downloaded file
# uses different headers, add them here rather than renaming the CSV.
PRESCRIBING_COLUMN_ALIASES = {
    "state": ["State", "Geo_Desc", "state"],
    "county": ["County", "county"],
    "county_fips": ["County Code", "county_code", "FIPS"],
    "year": ["Year", "year"],
    "total_claims": ["Total Claims", "Tot_Clms", "total_claims"],
    "opioid_claims": ["Opioid Claims", "Tot_Opioid_Clms", "opioid_claims"],
    "opioid_prescribing_rate": [
        "Opioid Prescribing Rate", "Opioid_Prscrbng_Rate",
        "opioid_prescribing_rate",
    ],
}

# The real "Medicare Part D Opioid Prescribing Rates - by Geography" CMS
# download (data.cms.gov) bundles National/State/County/ZIP geography levels
# and several demographic "breakouts" into one file, keyed by
# Prscrbr_Geo_Lvl / Breakout_Type / Breakout, with the county name and state
# packed into a single "State:County" field. This is detected automatically
# and reshaped into our standard columns.
CMS_GEO_FORMAT_MARKER = "Prscrbr_Geo_Lvl"


def _rename_with_aliases(df: pd.DataFrame, alias_map: dict) -> pd.DataFrame:
    rename = {}
    for standard_name, aliases in alias_map.items():
        for alias in aliases:
            if alias in df.columns:
                rename[alias] = standard_name
                break
    return df.rename(columns=rename)


def _strip_footer_notes(raw_text: str) -> str:
    """CDC WONDER exports append citation/footnote lines below the data,
    usually starting with a quoted '---' separator line. Cut everything
    from that marker onward before parsing as a table."""
    lines = raw_text.splitlines()
    cutoff = len(lines)
    for i, line in enumerate(lines):
        stripped = line.strip().strip('"')
        if stripped == "---" or stripped.startswith("Dataset:") or stripped.startswith("Query Date:"):
            cutoff = i
            break
    return "\n".join(lines[:cutoff])


def _sniff_delimiter(sample_text: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample_text.splitlines()[0])
        return dialect.delimiter
    except Exception:
        return "," if sample_text.splitlines()[0].count(",") >= sample_text.splitlines()[0].count("\t") else "\t"


def _standardize_fips(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.extract(r"(\d+)", expand=False)
        .str.zfill(5)
    )


def load_mortality_data(path: Optional[Path] = None) -> pd.DataFrame:
    """Load CDC WONDER mortality export (or sample data if none provided).

    Returns columns: county, county_fips, state, year, deaths, population,
    crude_rate, is_suppressed
    """
    if path is None:
        candidates = sorted(RAW_DIR.glob("cdc_wonder_mortality*.csv")) + sorted(
            RAW_DIR.glob("cdc_wonder_mortality*.txt")
        )
        path = candidates[0] if candidates else SAMPLE_DIR / "sample_mortality.csv"

    raw_text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    cleaned_text = _strip_footer_notes(raw_text)
    delimiter = _sniff_delimiter(cleaned_text)

    df = pd.read_csv(io.StringIO(cleaned_text), sep=delimiter, dtype=str, engine="python")
    df = _rename_with_aliases(df, MORTALITY_COLUMN_ALIASES)

    required = {"county", "county_fips", "year", "deaths", "population", "crude_rate"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Mortality file {path} is missing expected columns {missing}. "
            "Check docs/data_acquisition_guide.md or add aliases to "
            "MORTALITY_COLUMN_ALIASES in src/data_processing.py."
        )

    # Split "County Name, ST" -> county name + state abbreviation
    split = df["county"].str.rsplit(",", n=1, expand=True)
    df["county"] = split[0].str.strip()
    df["state"] = split[1].str.strip() if split.shape[1] > 1 else None

    df["county_fips"] = _standardize_fips(df["county_fips"])
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")

    for col in ["deaths", "population", "crude_rate"]:
        is_suppressed = df[col].isin(SUPPRESSED_TOKENS)
        df[col] = pd.to_numeric(df[col], errors="coerce")
        if col == "deaths":
            df["is_suppressed"] = is_suppressed

    df = df.dropna(subset=["county_fips", "year"]).reset_index(drop=True)
    return df[["county", "county_fips", "state", "year", "deaths", "population", "crude_rate", "is_suppressed"]]


def load_national_mortality_trend(path: Optional[Path] = None) -> Optional[pd.DataFrame]:
    """Load a dedicated National-level CDC WONDER export (Group Results By:
    National + Year, no County grouping). Unlike the county-level file, this
    is essentially never suppressed (national annual totals are always well
    above the <10-deaths privacy threshold), so it's the trustworthy source
    for a true national trend/forecast — the county-level rollup undercounts
    heavily once most counties are suppressed.

    Returns None (not an empty DataFrame) if no such file exists, so callers
    can tell "not provided" apart from "provided but empty" and fall back to
    deriving an approximate trend from the county-level data instead.

    Returns columns: year, deaths, population, crude_rate
    """
    if path is None:
        candidates = sorted(RAW_DIR.glob("cdc_wonder_national*.csv")) + sorted(
            RAW_DIR.glob("cdc_wonder_national*.txt")
        )
        if not candidates:
            return None
        path = candidates[0]
    elif not Path(path).exists():
        return None

    raw_text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    cleaned_text = _strip_footer_notes(raw_text)
    delimiter = _sniff_delimiter(cleaned_text)

    df = pd.read_csv(io.StringIO(cleaned_text), sep=delimiter, dtype=str, engine="python")
    df = _rename_with_aliases(df, MORTALITY_COLUMN_ALIASES)

    required = {"year", "deaths", "population", "crude_rate"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"National mortality file {path} is missing expected columns {missing}."
        )

    # Drop the "Total" summary row (its Year cell is blank) and any
    # suppressed/unreliable cells (shouldn't occur at national scale, but
    # handled defensively the same way as the county-level loader).
    df["year"] = pd.to_numeric(df["year"].astype(str).str.strip(), errors="coerce")
    for col in ["deaths", "population", "crude_rate"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["year"]).reset_index(drop=True)
    df["year"] = df["year"].astype(int)
    return df[["year", "deaths", "population", "crude_rate"]]


def _load_cms_geo_format(f: Path) -> pd.DataFrame:
    """Reshape the real CMS 'by Geography' export: filter down to
    county-level, overall (non-demographic-breakout) rows, and split the
    packed 'State:County' description into separate fields."""
    df = pd.read_csv(f, dtype=str)
    df = df[
        (df["Prscrbr_Geo_Lvl"] == "County")
        & (df["Breakout_Type"] == "Totals")
        & (df["Breakout"] == "Overall")
    ].copy()

    split = df["Prscrbr_Geo_Desc"].str.split(":", n=1, expand=True)
    df["state"] = split[0].str.strip()
    df["county"] = split[1].str.strip() if split.shape[1] > 1 else None
    df["county_fips"] = df["Prscrbr_Geo_Cd"]
    df["year"] = df["Year"]
    df["total_claims"] = df["Tot_Clms"]
    df["opioid_claims"] = df["Tot_Opioid_Clms"]
    df["opioid_prescribing_rate"] = df["Opioid_Prscrbng_Rate"]
    return df[["state", "county", "county_fips", "year", "total_claims", "opioid_claims", "opioid_prescribing_rate"]]


def load_prescribing_data(path_or_dir: Optional[Path] = None) -> pd.DataFrame:
    """Load CMS Part D opioid prescribing export(s) (or sample data).

    Accepts a single file or a directory containing multiple yearly files
    (they'll be concatenated). Returns columns: state, county, county_fips,
    year, total_claims, opioid_claims, opioid_prescribing_rate
    """
    if path_or_dir is None:
        candidates = sorted(RAW_DIR.glob("cms_opioid_prescribing*.csv"))
        files = candidates if candidates else [SAMPLE_DIR / "sample_prescribing.csv"]
    else:
        p = Path(path_or_dir)
        files = sorted(p.glob("*.csv")) if p.is_dir() else [p]

    frames = []
    for f in files:
        header = pd.read_csv(f, nrows=0, dtype=str).columns
        if CMS_GEO_FORMAT_MARKER in header:
            df = _load_cms_geo_format(f)
        else:
            df = pd.read_csv(f, dtype=str)
            df = _rename_with_aliases(df, PRESCRIBING_COLUMN_ALIASES)
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)

    required = {"state", "county", "county_fips", "year", "opioid_prescribing_rate"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Prescribing file(s) missing expected columns {missing}. "
            "Check docs/data_acquisition_guide.md or add aliases to "
            "PRESCRIBING_COLUMN_ALIASES in src/data_processing.py."
        )

    df["county_fips"] = _standardize_fips(df["county_fips"])
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    for col in ["total_claims", "opioid_claims", "opioid_prescribing_rate"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["county_fips", "year"]).drop_duplicates(
        subset=["county_fips", "year"]
    ).reset_index(drop=True)
    keep = ["state", "county", "county_fips", "year", "total_claims", "opioid_claims", "opioid_prescribing_rate"]
    return df[[c for c in keep if c in df.columns]]


def data_source_status() -> dict:
    """Report whether real raw data or sample data is currently in use,
    for display in the dashboard."""
    mortality_real = bool(
        list(RAW_DIR.glob("cdc_wonder_mortality*.csv")) + list(RAW_DIR.glob("cdc_wonder_mortality*.txt"))
    )
    prescribing_real = bool(list(RAW_DIR.glob("cms_opioid_prescribing*.csv")))
    national_real = bool(
        list(RAW_DIR.glob("cdc_wonder_national*.csv")) + list(RAW_DIR.glob("cdc_wonder_national*.txt"))
    )
    return {
        "mortality_is_real": mortality_real,
        "prescribing_is_real": prescribing_real,
        "national_is_real": national_real,
    }
