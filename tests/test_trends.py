import datetime as dt

import numpy as np
import pandas as pd
import pytest

from jpmarket.analytics.core import returns_pct
from jpmarket.analytics.trends import SERIES_LEN, build_trends, period_return, ytd_return
from jpmarket.calendar import trading_days_back
from jpmarket.config import ThemeSpec
from jpmarket.sources.master import Constituent

D = dt.date
T = D(2026, 9, 25)


def test_period_return_compounds() -> None:
    s = pd.Series([np.nan, 10.0, -10.0, 5.0])
    assert period_return(s, 2) == pytest.approx((0.9 * 1.05 - 1) * 100, abs=0.01)
    assert period_return(s, 3) == pytest.approx((1.1 * 0.9 * 1.05 - 1) * 100, abs=0.01)
    assert period_return(s, 4) is None


def test_ytd_requires_first_session() -> None:
    idx = [D(2025, 12, 30), D(2026, 1, 5), D(2026, 1, 6)]
    s = pd.Series([1.0, 2.0, 3.0], index=idx)
    assert ytd_return(s, D(2026, 1, 6)) == pytest.approx((1.02 * 1.03 - 1) * 100, abs=0.01)
    assert ytd_return(s.iloc[2:], D(2026, 1, 6)) is None  # history starts after the first session


def test_build_trends() -> None:
    days = trading_days_back(T, 200)
    closes = pd.DataFrame({"a": np.linspace(100, 150, 200), "b": np.linspace(100, 80, 200)}, index=days)
    rets = returns_pct(closes)
    master = [Constituent("a", "A", "銀行業", 1.0, ""), Constituent("b", "B", "鉱業", 1.0, "")]
    themes = [
        ThemeSpec(key="x", name="X", members={"a": "A", "b": "B"}),
        ThemeSpec(key="none", name="N", members={"zz": "Z"}),
    ]
    tr = build_trends(master, themes, rets, T)
    assert len(tr["dates"]) == min(SERIES_LEN, 200) and tr["dates"][-1] == "2026-09-25"
    bank = next(r for r in tr["sectors"] if r["name"] == "銀行業")
    assert bank["periods"]["d20"] == pytest.approx(
        (closes["a"].iloc[-1] / closes["a"].iloc[-21] - 1) * 100, abs=0.01
    )
    assert bank["periods"]["ytd"] is not None and bank["periods"]["ytd"] > 0
    assert len(bank["daily"]) == min(SERIES_LEN, 200)
    assert [r["id"] for r in tr["themes"]] == ["t:x"]
    assert [p["key"] for p in tr["periods"]] == ["d1", "d5", "d20", "d60", "d120", "ytd"]
