import datetime as dt

import numpy as np
import pandas as pd
import pytest

from jpmarket.analytics.core import (
    breadth,
    build_quote,
    chain_levels,
    rankings,
    returns_pct,
    sector_history,
    sector_perf,
    stock_move,
    theme_history,
    theme_perf,
    topix_estimate,
)
from jpmarket.config import QuoteSpec, ThemeSpec
from jpmarket.models import QuoteCategory, StockMove
from jpmarket.sources.master import Constituent

D = dt.date
DATES = [D(2026, 9, 24), D(2026, 9, 25)]
T = DATES[-1]

MASTER = [
    Constituent("0001", "A銀行", "銀行業", 3.0, ""),
    Constituent("0002", "B銀行", "銀行業", 1.0, ""),
    Constituent("0003", "C電機", "電気機器", 2.0, ""),
    Constituent("0004", "D電機", "電気機器", 2.0, ""),
]


def frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    closes = pd.DataFrame(
        {"0001": [100, 110], "0002": [100, 90], "0003": [100, 101], "0004": [100, np.nan]},
        index=DATES,
        dtype=float,
    )
    vols = pd.DataFrame({c: [1e7, 1e7] for c in closes.columns}, index=DATES)
    return closes, returns_pct(closes), vols


def test_returns_use_previous_available_close() -> None:
    c = pd.DataFrame({"x": [100.0, np.nan, 110.0]}, index=[D(2026, 9, 1), D(2026, 9, 2), D(2026, 9, 3)])
    r = returns_pct(c)
    assert r.at[D(2026, 9, 3), "x"] == pytest.approx(10.0)
    assert pd.isna(r.at[D(2026, 9, 2), "x"])


def test_build_quote() -> None:
    idx = [D(2026, 9, 1) + dt.timedelta(days=i) for i in range(25)]
    s = pd.Series([100.0 + i for i in range(25)], index=idx)
    spec = QuoteSpec(key="k", name="N", ticker="^X", category=QuoteCategory.DOMESTIC)
    q = build_quote(spec, s, D(2026, 9, 25))
    assert q is not None
    assert q.close == 124 and q.change == 1 and q.change_pct == pytest.approx(0.81)
    assert q.change_5d_pct == pytest.approx((124 / 119 - 1) * 100, abs=0.01)
    assert q.change_20d_pct == pytest.approx((124 / 104 - 1) * 100, abs=0.01)
    assert len(q.spark) == 20 and q.as_of == D(2026, 9, 25)
    # overseas quote lagging the JP date
    q2 = build_quote(spec, s.iloc[:-1], D(2026, 9, 25))
    assert q2 is not None and q2.as_of == D(2026, 9, 24)
    assert build_quote(spec, s.iloc[:1], D(2026, 9, 25)) is None


def test_sector_perf_weighted() -> None:
    closes, rets, vols = frames()
    secs = {s.name: s for s in sector_perf(MASTER, closes, rets, vols, T)}
    bank = secs["銀行業"]
    assert bank.change_pct == pytest.approx((10 * 3 - 10 * 1) / 4)  # +5.0
    assert (bank.advancers, bank.decliners, bank.count) == (1, 1, 2)
    assert [m.code for m in bank.leaders] == ["0001"]
    assert [m.code for m in bank.laggards] == ["0002"]
    elec = secs["電気機器"]
    assert elec.count == 1 and elec.change_pct == pytest.approx(1.0)  # 0004 missing today
    assert bank.topix_weight_pct == pytest.approx(50.0)
    assert list(secs) == ["銀行業", "電気機器"]


def test_topix_estimate_and_chain() -> None:
    _, rets, _ = frames()
    est = topix_estimate(MASTER, rets)
    assert est[T] == pytest.approx((10 * 3 - 10 * 1 + 1 * 2) / 6)
    lv = chain_levels(4000.0, pd.Series([np.nan, 1.0, -2.0], index=[1, 2, 3]))
    assert lv.iloc[-1] == 4000.0
    assert lv.iloc[1] == pytest.approx(4000 / 0.98)
    assert lv.iloc[0] == pytest.approx(4000 / 0.98 / 1.01)


def test_breadth_and_rankings() -> None:
    closes, rets, _ = frames()
    b = breadth([c.code for c in MASTER], closes, rets, T)
    assert (b.advancers, b.decliners, b.unchanged, b.total) == (2, 1, 0, 3)
    assert b.adv_dec_ratio_25d is None and b.new_highs is None
    moves = [
        StockMove(code="1", name="a", close=1, change_pct=5, turnover=2e9),
        StockMove(code="2", name="b", close=1, change_pct=20, turnover=1e8),  # illiquid
        StockMove(code="3", name="c", close=1, change_pct=-3, turnover=5e9),
    ]
    rk = rankings(moves, min_turnover=1e9)
    assert [m.code for m in rk.gainers] == ["1", "3"]
    assert [m.code for m in rk.losers] == ["3", "1"]
    assert [m.code for m in rk.turnover] == ["3", "1", "2"]


def test_breadth_ytd_highs() -> None:
    idx = [D(2026, 1, 5), D(2026, 6, 1), D(2026, 9, 25)]
    c = pd.DataFrame({"a": [100.0, 120, 130], "b": [100.0, 80, 90], "c": [100.0, 90, 70]}, index=idx)
    b = breadth(["a", "b", "c"], c, returns_pct(c), idx[-1])
    assert (b.new_highs, b.new_lows) == (1, 1)


def test_stock_move_turnover() -> None:
    closes, rets, vols = frames()
    m = stock_move("0001", "A", "銀行業", closes, rets, vols, T)
    assert m is not None and m.turnover == 1.1e9 and m.change_pct == 10.0
    assert stock_move("0004", "D", None, closes, rets, vols, T) is None
    assert stock_move("9999", "Z", None, closes, rets, vols, T) is None


def test_themes() -> None:
    closes, rets, vols = frames()
    themes = [
        ThemeSpec(key="bank", name="銀行", members={"0001": "A", "0002": "B"}),
        ThemeSpec(key="elec", name="電機", members={"0003": "C", "0004": "D"}),
        ThemeSpec(key="none", name="なし", members={"9999": "Z"}),
    ]
    tp = theme_perf(themes, closes, rets, vols, T, {"0001": "銀行業"})
    assert [t.key for t in tp] == ["elec", "bank"]  # 1.0 > 0.0; "none" dropped
    assert tp[1].change_pct == 0.0 and tp[1].advancers_ratio == 0.5
    assert tp[0].count == 1
    th = theme_history(themes, rets, T)
    assert th.series["bank"][-1] == 0.0 and "none" not in th.series


def test_sector_history() -> None:
    _, rets, _ = frames()
    h = sector_history(MASTER, rets, T)
    assert h.dates == DATES
    assert h.series["銀行業"] == [None, 5.0]
