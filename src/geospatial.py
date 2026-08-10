"""
Geospatial helpers: county-boundary GeoJSON loading (cached locally) and
choropleth figure builders for both the county and state level.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import requests

ROOT = Path(__file__).resolve().parent.parent
GEOJSON_URL = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"
GEOJSON_CACHE = ROOT / "data" / "processed" / "us_counties.geojson"


MIN_EXPECTED_COUNTIES = 3000  # the real US counties file has ~3200 features


def load_county_geojson() -> dict:
    """Fetch the public US counties GeoJSON (Plotly's standard demo file,
    keyed by 5-digit county FIPS in feature.id), caching it locally after
    the first download so re-runs don't need network access. A cached file
    with an implausibly low feature count (e.g. a partial/corrupt download)
    is treated as invalid and re-fetched."""
    if GEOJSON_CACHE.exists():
        try:
            cached = json.loads(GEOJSON_CACHE.read_text())
            if len(cached.get("features", [])) >= MIN_EXPECTED_COUNTIES:
                return cached
        except (json.JSONDecodeError, OSError):
            pass  # fall through to re-fetch

    resp = requests.get(GEOJSON_URL, timeout=30)
    resp.raise_for_status()
    geojson = resp.json()
    GEOJSON_CACHE.parent.mkdir(parents=True, exist_ok=True)
    GEOJSON_CACHE.write_text(json.dumps(geojson))
    return geojson


def aggregate_to_state(df: pd.DataFrame, value_col: str, weight_col: str = "population") -> pd.DataFrame:
    """Roll county-level rows up to state level using a population-weighted
    average of value_col (appropriate for rates; for raw counts, sum
    instead by passing weight_col=None)."""
    if weight_col and weight_col in df.columns:
        grouped = df.dropna(subset=[value_col, weight_col]).groupby(["state", "year"], as_index=False).apply(
            lambda g: pd.Series({
                value_col: (g[value_col] * g[weight_col]).sum() / g[weight_col].sum()
                if g[weight_col].sum() > 0 else g[value_col].mean()
            }),
            include_groups=False,
        )
        return grouped.reset_index(drop=True)
    return df.groupby(["state", "year"], as_index=False)[value_col].sum()


def county_choropleth(
    df: pd.DataFrame,
    value_col: str,
    year: int,
    title: str = "",
    color_scale: str = "OrRd",
    range_color: Optional[tuple] = None,
) -> go.Figure:
    """County-level choropleth for a single year. df must have
    county_fips, year, and value_col columns."""
    geojson = load_county_geojson()
    subset = df[df["year"] == year].dropna(subset=[value_col])

    fig = go.Figure(
        go.Choropleth(
            geojson=geojson,
            locations=subset["county_fips"],
            z=subset[value_col],
            colorscale=color_scale,
            zmin=range_color[0] if range_color else None,
            zmax=range_color[1] if range_color else None,
            marker_line_width=0.2,
            colorbar_title=value_col.replace("_", " ").title(),
            text=subset.get("county", subset["county_fips"]),
            hovertemplate="%{text}<br>%{z:.1f}<extra></extra>",
        )
    )
    fig.update_geos(scope="usa")
    fig.update_layout(
        title=title or f"{value_col.replace('_', ' ').title()} by County — {year}",
        margin=dict(l=0, r=0, t=40, b=0),
    )
    return fig


def state_choropleth(
    df: pd.DataFrame,
    value_col: str,
    year: int,
    title: str = "",
    color_scale: str = "OrRd",
) -> go.Figure:
    """State-level choropleth using Plotly's built-in USA-states location
    mode (requires a 2-letter 'state' abbreviation column)."""
    subset = df[df["year"] == year].dropna(subset=[value_col])
    fig = go.Figure(
        go.Choropleth(
            locations=subset["state"],
            z=subset[value_col],
            locationmode="USA-states",
            colorscale=color_scale,
            marker_line_width=0.5,
            colorbar_title=value_col.replace("_", " ").title(),
        )
    )
    fig.update_geos(scope="usa")
    fig.update_layout(
        title=title or f"{value_col.replace('_', ' ').title()} by State — {year}",
        margin=dict(l=0, r=0, t=40, b=0),
    )
    return fig
