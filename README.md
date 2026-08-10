# CDC WONDER Opioid Mortality Hotspot Analysis

Geographic and temporal patterns in opioid-related mortality across US
counties — where it got worse, when, and how that tracks against Medicare
Part D opioid prescribing rates. Built as a portfolio "nice to have" project:
lower technical ceiling than the other pieces in the series, higher
general-audience impact.

**Live demo:** run locally with `streamlit run app/dashboard.py` — see
[Quick start](#quick-start) below. Works out of the box on bundled synthetic
data; swap in real CDC/CMS exports with zero code changes.

## What it does

- **Where** — county- and state-level choropleth maps of opioid mortality
  rate (deaths per 100,000), year by year.
- **When** — national trend line with trend/residual decomposition (STL for
  monthly data, polynomial fallback for annual data).
- **Hotspots** — a leaderboard of counties whose mortality trend is
  *accelerating* fastest relative to their own recent history, z-scored
  across all tracked counties.
- **Why (maybe)** — cross-references county mortality against CMS Medicare
  Part D opioid prescribing rates (the dataset behind "Project 2" in this
  portfolio series), with year-by-year Pearson correlation, so the
  relationship between prescribing and mortality can be read as it shifts
  over time rather than collapsed into a single number.

## Data sources

| Dataset | Source | Access |
|---|---|---|
| Opioid-related mortality (county x year) | [CDC WONDER — Multiple Cause of Death](https://wonder.cdc.gov/mcd-icd10-expanded.html) | Public, manual export (no signup) |
| Opioid prescribing rate (county x year) | [CMS — Medicare Part D Opioid Prescribing Rates by Geography](https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-medicaid-opioid-prescribing-rates/medicare-part-d-opioid-prescribing-rates-by-geography) | Public, manual export (no signup) |
| County boundaries | [Plotly public US-counties GeoJSON](https://github.com/plotly/datasets) | Public, fetched automatically at runtime |

Full step-by-step download instructions (exact ICD-10 codes, query filters,
where to save the files): **[`docs/data_acquisition_guide.md`](docs/data_acquisition_guide.md)**.

Neither dataset requires an account. Both are pulled through a short manual
export rather than a live API because CDC WONDER's restricted mortality
cuts and CMS's dataset pages don't expose a stable public API for this exact
shape of data — see the guide for why, and for the (truly public,
scriptable but coarser) state-level alternative if you'd rather automate
data pulls end-to-end.

## Quick start

```bash
git clone <your-repo-url>
cd opioid-mortality-hotspot-analysis
python -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt

# runs immediately on bundled synthetic sample data:
streamlit run app/dashboard.py
```

To use real data instead: follow `docs/data_acquisition_guide.md`, drop the
downloaded CSVs into `data/raw/`, and re-run — the app detects real files
automatically and swaps out the sample data (a banner in the dashboard tells
you which one is active).

### Running tests

```bash
pytest -v
```

### Regenerating the synthetic sample data

```bash
python scripts/generate_sample_data.py
```

### Exploring in a notebook

`notebooks/01_exploratory_analysis.ipynb` walks through the same `src/`
modules the dashboard uses. Needs Jupyter, which is intentionally left out
of `requirements.txt` to keep the dashboard's dependency footprint small:

```bash
pip install jupyter
jupyter notebook notebooks/01_exploratory_analysis.ipynb
```

## Project structure

```
├── app/
│   └── dashboard.py            # Streamlit app (entry point)
├── src/
│   ├── data_processing.py      # CDC WONDER / CMS export loading & cleaning
│   ├── geospatial.py           # choropleth builders, FIPS/state aggregation
│   ├── time_series.py          # trend decomposition, hotspot scoring
│   └── cross_reference.py      # mortality x prescribing merge & correlation
├── scripts/
│   └── generate_sample_data.py # synthetic data generator
├── sample_data/                # bundled synthetic CSVs (CDC/CMS-shaped)
├── data/raw/                   # put your real downloaded exports here (gitignored)
├── data/processed/             # cached derived data, e.g. geojson (gitignored)
├── tests/                      # pytest suite
├── docs/
│   └── data_acquisition_guide.md
└── .github/workflows/ci.yml    # tests + dashboard smoke test on push/PR
```

## Techniques demonstrated

- Geospatial visualization (county- and state-level choropleths, FIPS
  joins against a public boundary file)
- Time-series decomposition (STL / polynomial trend-residual split) and
  rate-of-change hotspot detection
- Cross-dataset correlation analysis across a multi-project narrative
  thread (mortality x CMS prescribing data)
- Defensive data-cleaning for real-world government exports: privacy
  suppression handling, footnote stripping, column-alias tolerance across
  export vintages

## Known limitations

- **CDC suppression**: county-years with fewer than 10 deaths are
  suppressed by CDC (privacy rule), not reported as zero. Small/rural
  counties are systematically undercounted as a result — the pipeline flags
  these (`is_suppressed`) rather than hiding it.
- **Ecological correlation caveat**: the mortality-vs-prescribing
  correlation is at the *county* level, not the individual level — it
  cannot show that people who overdosed were the same people who were
  prescribed opioids (ecological fallacy). Framed as a population-level
  pattern, not a causal or individual claim.
- **Sample data is synthetic**: the bundled `sample_data/` encodes a
  plausible, deliberately-engineered story (prescribing peak ~2016-2017,
  mortality accelerating post-2018) for demo purposes. It is not real
  epidemiological data — replace it with real CDC/CMS exports before
  drawing any actual conclusions.

## License

MIT — see [`LICENSE`](LICENSE).
