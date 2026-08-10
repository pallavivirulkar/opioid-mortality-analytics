# Data Acquisition Guide

Both datasets below are fully public and require no signup. Neither has a
scriptable, stable public API for the exact cuts this project needs, so both
are pulled through a short manual export. Save the files with the exact
names below and everything downstream (`src/data_processing.py`, the
dashboard) will pick them up automatically.

---

## 1. CDC WONDER — Multiple Cause of Death (opioid mortality)

**Portal:** https://wonder.cdc.gov/mcd-icd10-expanded.html
(*Current Final Multiple Cause of Death, 2018–2024, county-level*. Use the
1999–2020 bridged-race portal at https://wonder.cdc.gov/mcd-icd10.html if you
need years before 2018.)

Steps:

1. Open the link above and click **"I Agree"** on the data-use terms (no
   account needed).
2. **Organize table layout** — set "Group Results By" to `County`, then
   `Year`. (Optionally add `State` as a third grouping if you want a
   state rollup for free.)
3. **Select Location** — leave as "All States" or pick a subset you care
   about. Fewer states = a much smaller/faster export.
4. **Select Demographics** — leave defaults (All) unless you want an
   age/sex breakdown.
5. **Select Cause of Death**:
   - Open "Underlying Cause of Death" and enter these ICD-10 codes in the
     code box: `X40-X44, X60-X64, X85, Y10-Y14` (drug poisoning deaths —
     unintentional, suicide, assault, and undetermined intent).
   - Optionally also restrict by **Multiple Cause of Death** drug-involved
     codes to isolate *opioid*-involved deaths specifically:
     `T40.0-T40.4, T40.6` (any opioid, heroin, natural/semisynthetic,
     methadone, synthetic opioids e.g. fentanyl).
6. **Other Options** — check "Export Results" (enables a clean CSV/TSV
   download instead of the HTML report). Leave "Show Suppressed Values"
   and "Show Zero Values" checked so you can see which county-years were
   suppressed rather than silently missing them.
7. Click **Send**, then **Export** to download the tab-delimited file.
8. Save it as:
   ```
   data/raw/cdc_wonder_mortality.csv
   ```

**Important caveat (baked into the pipeline):** CDC WONDER suppresses any
county-year cell with **fewer than 10 deaths** (displayed as `Suppressed`)
and marks rates **unreliable** when based on fewer than 20 deaths. This is a
privacy rule, not missing data. `src/data_processing.py` converts these to
`NaN` and flags them (`is_suppressed` column) rather than dropping them
silently, so the hotspot logic can account for undercounting in low-population
counties.

**This suppression is severe: in practice, ~93% of county-year rows end up
suppressed.** That's fine for the map (it only ever shows real, reported
numbers) and fine for hotspot detection (which compares reporting counties
to their own history, not to a national total). It is **not** fine for a
"national rate" — summing only the ~7% of counties that report real numbers
massively undercounts the true national total. For an accurate national
trend, get a second, separate export below.

### 1b. (Recommended) National-level export, for an accurate trend/forecast

Repeat the same query, but change step 2:

1. Section 1, **"Group Results By"** → select **Year** only (leave the
   location field as **None** — don't group by County or State this time).
   No location grouping = CDC WONDER returns the true national total,
   which is essentially never suppressed at that scale.
2. Same cause-of-death selection as above (Drug/Alcohol Induced Causes →
   the 4 overdose categories).
3. Export and save as:
   ```
   data/raw/cdc_wonder_national.csv
   ```

The dashboard automatically prefers this file for the trend chart and
forecast once it's present, and shows a warning banner if it's missing
(falling back to the approximate, undercounted county rollup instead).

---

## 2. CMS — Medicare Part D Opioid Prescribing Rates by Geography

**Portal:** https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-medicaid-opioid-prescribing-rates/medicare-part-d-opioid-prescribing-rates-by-geography

This is the CMS cross-reference dataset for the "does mortality correlate
with prescribing" narrative thread. State- and county-level, one row per
geography per year, with total claims, opioid claims, and the opioid
prescribing rate.

Steps:

1. Open the link above.
2. Use the **Download/Export** button on the page and choose **CSV**
   (the page also lists prior years separately — grab each year you want,
   CMS typically publishes one file per year from ~2013 onward).
3. If multiple yearly files are downloaded, just drop them all into
   `data/raw/` — the loader concatenates any file matching the pattern
   below.
4. Save (or rename) file(s) as:
   ```
   data/raw/cms_opioid_prescribing_<year>.csv
   ```
   e.g. `data/raw/cms_opioid_prescribing_2021.csv`. A single combined file
   named `data/raw/cms_opioid_prescribing.csv` also works.

---

## 3. County FIPS boundaries (for the map)

No download needed — `src/geospatial.py` pulls the standard public Plotly
US-counties GeoJSON directly from
`https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json`
at runtime (this is the same public boundary file used in Plotly's own
choropleth docs, no key required). If you're offline, download it once and
point `GEOJSON_PATH` in `src/geospatial.py` at the local copy.

---

## 4. Quick start without real data

You don't need either file to try the project. `sample_data/` contains
synthetic mortality and prescribing data shaped exactly like the real
exports, covering 2015–2023 across 12 states / ~40 counties, with a
deliberately engineered "hotspot" story (a cluster of counties trending up
faster than the national baseline, roughly tracking a synthetic prescribing
spike). Run the app as-is first, then swap in your real CDC/CMS exports —
same file paths, same columns, zero code changes required.
