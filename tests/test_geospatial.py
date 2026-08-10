import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src.geospatial import aggregate_to_state


def test_aggregate_to_state_population_weighted_average():
    df = pd.DataFrame([
        dict(state="AA", year=2020, crude_rate=10.0, population=100),
        dict(state="AA", year=2020, crude_rate=20.0, population=300),
        dict(state="BB", year=2020, crude_rate=5.0, population=50),
    ])
    result = aggregate_to_state(df, "crude_rate")
    aa_rate = result[result["state"] == "AA"]["crude_rate"].iloc[0]
    # weighted average: (10*100 + 20*300) / 400 = 17.5
    assert abs(aa_rate - 17.5) < 1e-9
    bb_rate = result[result["state"] == "BB"]["crude_rate"].iloc[0]
    assert abs(bb_rate - 5.0) < 1e-9
