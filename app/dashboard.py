"""
CDC WONDER Opioid Mortality Hotspot Analysis — Streamlit dashboard.

Run:
    streamlit run app/dashboard.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.data_processing import load_mortality_data, load_prescribing_data, load_national_mortality_trend, data_source_status
from src.geospatial import county_choropleth, state_choropleth, aggregate_to_state
from src.time_series import national_trend, decompose_series, compute_hotspot_scores, yoy_change, forecast_mortality_rate, compare_forecast_methods
from src.cross_reference import merge_mortality_and_prescribing, correlation_by_year, overall_correlation

st.set_page_config(
    page_title="Opioid Mortality Hotspot Analysis",
    page_icon="🗺️",
    layout="wide",
)


@st.cache_data
def get_data():
    mortality = load_mortality_data()
    prescribing = load_prescribing_data()
    national = load_national_mortality_trend()
    return mortality, prescribing, national


mortality, prescribing, national_trend_real = get_data()
status = data_source_status()

st.title("🗺️ CDC WONDER Opioid Mortality Hotspot Analysis")
st.caption(
    "Geographic and temporal patterns in opioid-related mortality, "
    "cross-referenced with CMS Medicare Part D opioid prescribing rates."
)

if not status["mortality_is_real"] or not status["prescribing_is_real"]:
    st.info(
        "📊 Running on **synthetic sample data** (bundled in `sample_data/`). "
        "Drop your real CDC WONDER export in `data/raw/cdc_wonder_mortality.csv` "
        "and/or your CMS export in `data/raw/cms_opioid_prescribing_*.csv` to "
        "switch to real data automatically — see `docs/data_acquisition_guide.md`.",
        icon="ℹ️",
    )
elif not status["national_is_real"]:
    st.warning(
        "⚠️ No dedicated National-level CDC WONDER export found. The national "
        "trend/forecast below is being **derived from county-level data**, and "
        "~93% of counties are suppressed (<10 deaths, hidden for privacy) — so "
        "this derived rate is a significant undercount, not the true national "
        "rate. Add `data/raw/cdc_wonder_national.csv` (Group Results By: "
        "National + Year) for the accurate trend — see `docs/data_acquisition_guide.md`.",
        icon="⚠️",
    )

years = sorted(mortality["year"].dropna().unique().tolist())
states = sorted(mortality["state"].dropna().unique().tolist())

# ---------------------------------------------------------------- sidebar --
st.sidebar.header("Filters")
selected_year = st.sidebar.slider(
    "Map year", min_value=int(min(years)), max_value=int(max(years)), value=int(max(years))
)
map_level = st.sidebar.radio("Map level", ["County", "State"], index=0)
selected_states = st.sidebar.multiselect("Filter states (blank = all)", states, default=[])
min_pop = st.sidebar.number_input(
    "Minimum county population (filters noisy small counties)", min_value=0, value=0, step=10_000
)

filtered = mortality.copy()
if selected_states:
    filtered = filtered[filtered["state"].isin(selected_states)]
if min_pop:
    filtered = filtered[filtered["population"] >= min_pop]

# --------------------------------------------------------- headline stats --
if national_trend_real is not None:
    nat = national_trend_real.rename(columns={"crude_rate": "national_rate"})[["year", "national_rate"]]
else:
    nat = national_trend(mortality)  # approximate, undercounts due to county-level suppression
current = nat[nat["year"] == selected_year]["national_rate"]
prev = nat[nat["year"] == selected_year - 1]["national_rate"]
current_val = float(current.iloc[0]) if len(current) else float("nan")
yoy = (
    (current_val - float(prev.iloc[0])) / float(prev.iloc[0]) * 100
    if len(prev) and len(current)
    else float("nan")
)
hotspots = compute_hotspot_scores(filtered)
n_hotspots = int((hotspots["hotspot_zscore"] > 1.5).sum()) if not hotspots.empty else 0

c1, c2, c3 = st.columns(3)
c1.metric(f"National rate, {selected_year}", f"{current_val:.1f} / 100k" if pd.notna(current_val) else "n/a",
          f"{yoy:+.1f}% YoY" if pd.notna(yoy) else None, delta_color="inverse")
c2.metric("Counties tracked", f"{filtered['county_fips'].nunique():,}")
c3.metric("Accelerating hotspots (z > 1.5)", n_hotspots)

st.divider()

# --------------------------------------------------------------- geo map --
st.subheader("Where — geographic hotspots")
if map_level == "County":
    fig_map = county_choropleth(filtered, "crude_rate", selected_year,
                                 title=f"Opioid Mortality Rate by County — {selected_year}")
else:
    state_df = aggregate_to_state(filtered, "crude_rate")
    fig_map = state_choropleth(state_df, "crude_rate", selected_year,
                                title=f"Opioid Mortality Rate by State — {selected_year}")
st.plotly_chart(fig_map, use_container_width=True)
st.caption(
    "Rate = deaths per 100,000 residents. County-years with fewer than 10 deaths "
    "are suppressed by CDC and excluded from the map, not shown as zero."
)

st.divider()

# --------------------------------------------------------- time series ----
st.subheader("When — national trend & decomposition")
st.caption(
    "Source: dedicated National-level CDC WONDER export (accurate)." if national_trend_real is not None
    else "Source: derived from county-level rollup — approximate, undercounts due to suppression (see warning above)."
)
tcol1, tcol2 = st.columns([2, 1])

series = nat.set_index("year")["national_rate"]
decomp = decompose_series(series, period=12)

with tcol1:
    fig_trend = go.Figure()
    fig_trend.add_trace(go.Scatter(x=series.index, y=series.values, mode="lines+markers", name="Observed"))
    fig_trend.add_trace(go.Scatter(x=decomp.trend.index, y=decomp.trend.values, mode="lines",
                                    name=f"Trend ({decomp.method})", line=dict(dash="dash")))
    fig_trend.update_layout(
        title="National opioid mortality rate over time",
        xaxis_title="Year", yaxis_title="Deaths per 100,000",
        margin=dict(l=0, r=0, t=40, b=0),
    )
    st.plotly_chart(fig_trend, use_container_width=True)

with tcol2:
    fig_resid = go.Figure()
    fig_resid.add_trace(go.Bar(x=decomp.resid.index, y=decomp.resid.values, name="Residual"))
    fig_resid.update_layout(
        title="Residual (unexplained by trend)",
        margin=dict(l=0, r=0, t=40, b=0),
    )
    st.plotly_chart(fig_resid, use_container_width=True)

st.divider()

# ------------------------------------------------------------ forecast ----
st.subheader("Forecast — next-year projection")
exclude_latest = st.checkbox(
    "Treat most recent year as provisional and exclude it from the backtest "
    "(recommended — CDC's newest year is usually incomplete due to death-certificate processing lag)",
    value=True,
)

# Rank methods (naive / linear / polynomial / avg YoY change) by backtest
# accuracy on the years we trust; then use whichever wins for the actual
# forward-looking forecast, fit on all available data.
backtest_series = series.iloc[:-1] if (exclude_latest and len(series) >= 5) else series
comparison = compare_forecast_methods(backtest_series, forecast_years=1)
scored = [r for r in comparison if r.backtest_mae is not None]
best = min(scored, key=lambda r: r.backtest_mae) if scored else comparison[0]

full_comparison = compare_forecast_methods(series, forecast_years=1)
best_forward = next(r for r in full_comparison if r.method == best.method)

fcol1, fcol2 = st.columns([2, 1])
with fcol1:
    fig_fc = go.Figure()
    fig_fc.add_trace(go.Scatter(x=series.index, y=series.values, mode="lines+markers", name="Observed"))
    fig_fc.add_trace(go.Scatter(
        x=[series.index[-1]] + best_forward.future_years,
        y=[series.values[-1]] + best_forward.forecast_values,
        mode="lines+markers", name=f"Forecast ({best.method})", line=dict(dash="dot", color="orange"),
    ))
    fig_fc.update_layout(
        title=f"Best-backtested forecast: {best.method}",
        xaxis_title="Year", yaxis_title="Deaths per 100,000",
        margin=dict(l=0, r=0, t=40, b=0),
    )
    st.plotly_chart(fig_fc, use_container_width=True)

    st.caption("Backtest comparison across methods (lower error = better; winner used for the forecast above):")
    comp_df = pd.DataFrame([{
        "method": r.method,
        "predicted": round(r.backtest_predicted, 2) if r.backtest_predicted is not None else None,
        "actual": round(r.backtest_actual, 2) if r.backtest_actual is not None else None,
        "% error": round(r.backtest_pct_error, 1) if r.backtest_pct_error is not None else None,
    } for r in comparison]).sort_values("% error")
    st.dataframe(comp_df, use_container_width=True, hide_index=True)

with fcol2:
    if best.backtest_mae is not None:
        st.metric(
            f"Best method: {best.method} ({best.backtest_year})",
            f"±{best.backtest_mae:.2f} /100k",
            f"{best.backtest_pct_error:.1f}% error" if best.backtest_pct_error is not None else None,
            delta_color="inverse",
        )
        st.caption(
            f"Trained on all years *except* {best.backtest_year}, then used to predict it: "
            f"forecasted {best.backtest_predicted:.2f} vs. actual {best.backtest_actual:.2f}. "
            f"This is the honest accuracy check — the forward forecast on the chart has no "
            f"ground truth to validate against yet."
        )
    else:
        st.write("Not enough years of data to backtest forecast accuracy.")

st.divider()

# ------------------------------------------------------- hotspot leaders --
st.subheader("Hotspot leaderboard")
st.caption(
    f"Counties where the {min(3, len(years))}-year recent trend is accelerating fastest "
    "relative to their own earlier trend (z-scored across all counties)."
)
if not hotspots.empty:
    top_n = st.slider("Show top N", 5, min(30, len(hotspots)), 10)
    display_cols = ["county", "state", "latest_value", "early_slope", "recent_slope", "acceleration", "hotspot_zscore"]
    display_df = hotspots[display_cols].head(top_n).round({
        "latest_value": 1, "early_slope": 2, "recent_slope": 2,
        "acceleration": 2, "hotspot_zscore": 2,
    })
    st.dataframe(display_df, use_container_width=True)
else:
    st.write("Not enough data points to compute hotspot scores for the current filter.")

st.divider()

# ----------------------------------------------------- cross-reference ----
st.subheader("Cross-reference — mortality vs. CMS prescribing rate")
st.caption(
    "Optional multi-project thread: does county mortality track Medicare Part D "
    "opioid prescribing intensity, and how has that relationship shifted over time?"
)

merged = merge_mortality_and_prescribing(filtered, prescribing)
if merged.empty:
    st.write("No overlapping county-years between the mortality and prescribing datasets for the current filter.")
else:
    xcol1, xcol2 = st.columns([1, 1])

    with xcol1:
        overall = overall_correlation(merged)
        st.metric("Overall Pearson r (mortality vs. prescribing rate)",
                  f"{overall['pearson_r']:.2f}" if pd.notna(overall.get("pearson_r")) else "n/a",
                  f"p = {overall['p_value']:.3g}, n = {overall['n']}" if pd.notna(overall.get("p_value")) else None)
        fig_scatter = px.scatter(
            merged[merged["year"] == selected_year],
            x="opioid_prescribing_rate", y="crude_rate", color="state",
            hover_name="county",
            render_mode="svg",
            labels={"opioid_prescribing_rate": "Opioid prescribing rate (%)", "crude_rate": "Mortality rate /100k"},
            title=f"Mortality vs. prescribing rate — {selected_year}",
            trendline="ols" if merged["year"].eq(selected_year).sum() >= 3 else None,
        )
        fig_scatter.update_layout(margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(fig_scatter, use_container_width=True)

    with xcol2:
        corr_by_year = correlation_by_year(merged)
        if not corr_by_year.empty:
            fig_corr = px.line(
                corr_by_year, x="year", y="pearson_r", markers=True,
                title="Correlation strength by year",
                labels={"pearson_r": "Pearson r"},
            )
            fig_corr.update_layout(margin=dict(l=0, r=0, t=40, b=0))
            st.plotly_chart(fig_corr, use_container_width=True)
        else:
            st.write("Not enough overlapping counties per year to compute a yearly correlation.")

st.divider()
st.caption(
    "Sources: CDC WONDER Multiple Cause of Death (mortality) · "
    "CMS Medicare Part D Opioid Prescribing Rates by Geography (prescribing) · "
    "County boundaries: public Plotly US-counties GeoJSON. "
    "See docs/data_acquisition_guide.md for exact download steps."
)
