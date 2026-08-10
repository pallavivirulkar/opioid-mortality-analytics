"""
Generates synthetic sample data shaped exactly like real CDC WONDER and CMS
exports, so the pipeline and dashboard run end-to-end before real data is
downloaded. Encodes a deliberate, plausible story: Appalachian/Rust Belt
counties show a Part D prescribing peak around 2015-2017 that declines after
policy tightening, while overdose mortality keeps climbing past 2018 as
illicit fentanyl replaces prescription opioids as the dominant driver -
mirroring the real national pattern. This gives the dashboard something
real to narrate without touching actual restricted data.

Run:
    python scripts/generate_sample_data.py
Writes:
    sample_data/sample_mortality.csv   (CDC WONDER shape)
    sample_data/sample_prescribing.csv (CMS shape)
"""

import csv
import random
from pathlib import Path

random.seed(42)

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "sample_data"
OUT_DIR.mkdir(exist_ok=True)

YEARS = list(range(2015, 2024))

STATE_ABBR = {
    "West Virginia": "WV", "Ohio": "OH", "Kentucky": "KY",
    "Pennsylvania": "PA", "Massachusetts": "MA", "Florida": "FL",
    "California": "CA", "New York": "NY", "Tennessee": "TN",
    "New Mexico": "NM", "Arizona": "AZ", "Illinois": "IL",
    "North Carolina": "NC", "Indiana": "IN", "Maryland": "MD",
    "Vermont": "VT", "New Hampshire": "NH", "Connecticut": "CT",
    "Michigan": "MI", "Missouri": "MO", "Colorado": "CO",
    "Washington": "WA", "Oregon": "OR", "Georgia": "GA",
}

# (State, State FIPS, County, County FIPS, base 2015 population, "hotspot" flag)
COUNTIES = [
    ("West Virginia", "54", "Cabell County", "54011", 96_000, True),
    ("West Virginia", "54", "Kanawha County", "54039", 187_000, True),
    ("Ohio", "39", "Scioto County", "39145", 76_000, True),
    ("Ohio", "39", "Montgomery County", "39113", 531_000, True),
    ("Ohio", "39", "Franklin County", "39049", 1_260_000, False),
    ("Kentucky", "21", "Fayette County", "21067", 320_000, False),
    ("Kentucky", "21", "Pike County", "21195", 61_000, True),
    ("Pennsylvania", "42", "Allegheny County", "42003", 1_225_000, False),
    ("Pennsylvania", "42", "Philadelphia County", "42101", 1_567_000, True),
    ("Massachusetts", "25", "Suffolk County", "25025", 803_000, False),
    ("Massachusetts", "25", "Essex County", "25009", 789_000, False),
    ("Florida", "12", "Miami-Dade County", "12086", 2_700_000, False),
    ("Florida", "12", "Palm Beach County", "12099", 1_450_000, False),
    ("California", "06", "Los Angeles County", "06037", 10_100_000, False),
    ("California", "06", "San Francisco County", "06075", 865_000, False),
    ("New York", "36", "New York County", "36061", 1_630_000, False),
    ("New York", "36", "Erie County", "36029", 919_000, False),
    ("Tennessee", "47", "Davidson County", "47037", 691_000, False),
    ("Tennessee", "47", "Knox County", "47093", 460_000, False),
    ("New Mexico", "35", "Bernalillo County", "35001", 679_000, True),
    ("New Mexico", "35", "Rio Arriba County", "35039", 39_000, True),
    ("Arizona", "04", "Maricopa County", "04013", 4_090_000, False),
    ("Arizona", "04", "Pima County", "04019", 1_010_000, False),
    ("Illinois", "17", "Cook County", "17031", 5_230_000, False),
    ("Illinois", "17", "Sangamon County", "17167", 197_000, False),
    ("North Carolina", "37", "Mecklenburg County", "37119", 1_035_000, False),
    ("North Carolina", "37", "Buncombe County", "37021", 253_000, False),
    ("Indiana", "18", "Marion County", "18097", 941_000, True),
    ("Indiana", "18", "Scott County", "18143", 24_000, True),
    ("Maryland", "24", "Baltimore city", "24510", 615_000, True),
    ("Maryland", "24", "Baltimore County", "24005", 828_000, True),
    ("Vermont", "50", "Chittenden County", "50007", 162_000, False),
    ("New Hampshire", "33", "Hillsborough County", "33011", 411_000, True),
    ("Connecticut", "09", "Hartford County", "09003", 894_000, False),
    ("Michigan", "26", "Wayne County", "26163", 1_749_000, True),
    ("Missouri", "29", "St. Louis city", "29510", 300_000, True),
    ("Colorado", "08", "Denver County", "08031", 704_000, False),
    ("Washington", "53", "King County", "53033", 2_150_000, False),
    ("Oregon", "41", "Multnomah County", "41051", 812_000, False),
    ("Georgia", "13", "Fulton County", "13121", 1_030_000, False),
]


def mortality_row(state, county, fips, year, pop):
    hotspot = next(c[5] for c in COUNTIES if c[3] == fips)
    year_idx = year - 2015
    base_rate = 12.0 if not hotspot else 14.0
    if hotspot:
        # accelerating post-2018 due to synthetic fentanyl wave
        trend = base_rate + year_idx * 1.9 + max(0, year - 2018) ** 1.4 * 1.1
    else:
        trend = base_rate + year_idx * 0.6
    noise = random.gauss(0, 1.1)
    crude_rate = max(0.5, trend + noise)
    deaths = round(crude_rate * pop / 100_000)
    suppressed = deaths < 10
    return {
        "County": f"{county}, {STATE_ABBR[state]}",
        "County Code": fips,
        "Year": year,
        "Year Code": year,
        "Deaths": "Suppressed" if suppressed else deaths,
        "Population": pop,
        "Crude Rate": "Suppressed" if suppressed else round(crude_rate, 1),
        "is_suppressed": suppressed,
    }


def prescribing_row(state, county, fips, year, hotspot):
    year_idx = year - 2015
    if hotspot:
        # peaks ~2016-2017 then declines after policy tightening
        peak_year = 2016.5
        rate = 9.0 + 6.0 * max(0, 1 - abs(year - peak_year) / 5.0)
        rate -= max(0, year - 2017) * 0.55  # tightening after peak
    else:
        rate = 4.5 + max(0, 2 - year_idx * 0.15)
    rate = max(0.8, rate + random.gauss(0, 0.4))
    total_claims = random.randint(15_000, 400_000)
    opioid_claims = round(total_claims * rate / 100)
    return {
        "State": state,
        "County": county,
        "County Code": fips,
        "Year": year,
        "Total Claims": total_claims,
        "Opioid Claims": opioid_claims,
        "Opioid Prescribing Rate": round(rate, 2),
    }


def main():
    mortality_path = OUT_DIR / "sample_mortality.csv"
    with open(mortality_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "County", "County Code", "Year", "Year Code",
                "Deaths", "Population", "Crude Rate", "is_suppressed",
            ],
        )
        writer.writeheader()
        for state, _sfips, county, fips, base_pop, hotspot in COUNTIES:
            for year in YEARS:
                pop = round(base_pop * (1 + 0.01 * (year - 2015)))
                writer.writerow(mortality_row(state, county, fips, year, pop))
        # CDC WONDER-style footer notes, stripped by the loader
        f.write('"---"\n')
        f.write('"Dataset: Synthetic sample data modeled on CDC WONDER Multiple Cause of Death output."\n')
        f.write('"Suppressed rows represent county-years with fewer than 10 deaths (per CDC privacy rules)."\n')

    prescribing_path = OUT_DIR / "sample_prescribing.csv"
    with open(prescribing_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "State", "County", "County Code", "Year",
                "Total Claims", "Opioid Claims", "Opioid Prescribing Rate",
            ],
        )
        writer.writeheader()
        for state, _sfips, county, fips, _base_pop, hotspot in COUNTIES:
            for year in YEARS:
                writer.writerow(prescribing_row(state, county, fips, year, hotspot))

    print(f"Wrote {mortality_path}")
    print(f"Wrote {prescribing_path}")


if __name__ == "__main__":
    main()
