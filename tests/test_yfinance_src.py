import datetime as dt

import numpy as np
import pandas as pd

from jpmarket.sources.yfinance_src import YFinanceSource, to_yf, wide_to_long

D = dt.date


def fake_wide(tickers: list[str], dates: list[dt.date]) -> pd.DataFrame:
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in dates])
    cols = pd.MultiIndex.from_product([tickers, ["Open", "High", "Low", "Close", "Adj Close", "Volume"]])
    data = np.arange(len(idx) * len(cols), dtype=float).reshape(len(idx), len(cols)) + 1
    return pd.DataFrame(data, index=idx, columns=cols)


def test_to_yf() -> None:
    assert to_yf("7203") == "7203.T"
    assert to_yf("285A") == "285A.T"
    assert to_yf("^N225") == "^N225"
    assert to_yf("USDJPY=X") == "USDJPY=X"


def test_wide_to_long_drops_empty() -> None:
    w = fake_wide(["7203.T", "6758.T"], [D(2026, 9, 24), D(2026, 9, 25)])
    w.loc[:, ("6758.T", "Close")] = np.nan
    out = wide_to_long(w, {"7203.T": "7203", "6758.T": "6758"})
    assert set(out["symbol"]) == {"7203"}
    assert list(out["date"]) == [D(2026, 9, 24), D(2026, 9, 25)]


class Recorder:
    def __init__(self, fail_first: set[str], rate_limit_calls: int = 0) -> None:
        self.calls: list[list[str]] = []
        self.fail_first = set(fail_first)
        self.rate_limit_calls = rate_limit_calls

    def __call__(self, tickers: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
        self.calls.append(list(tickers))
        if self.rate_limit_calls:
            self.rate_limit_calls -= 1
            raise RuntimeError("YFRateLimitError('Too Many Requests. Rate limited.')")
        ok = [t for t in tickers if t not in self.fail_first]
        self.fail_first -= set(tickers)  # succeed on retry
        return fake_wide(ok, [D(2026, 9, 25)]) if ok else pd.DataFrame()


def test_chunks_and_refetch_missing() -> None:
    rec = Recorder(fail_first={"0003.T"})
    src = YFinanceSource(chunk_size=2, pause_sec=0, downloader=rec, sleep=lambda s: None)
    out = src.daily_bars(["0001", "0002", "0003", "0001"], D(2026, 9, 25), D(2026, 9, 25))
    assert rec.calls == [["0001.T", "0002.T"], ["0003.T"], ["0003.T"]]
    assert sorted(out["symbol"]) == ["0001", "0002", "0003"]


def test_rate_limit_backoff() -> None:
    sleeps: list[float] = []
    rec = Recorder(fail_first=set(), rate_limit_calls=1)
    src = YFinanceSource(chunk_size=10, pause_sec=1, downloader=rec, sleep=sleeps.append)
    out = src.daily_bars(["0001"], D(2026, 9, 25), D(2026, 9, 25))
    assert list(out["symbol"]) == ["0001"]
    assert sleeps == [4]


def test_gives_up_after_retries() -> None:
    rec = Recorder(fail_first=set(), rate_limit_calls=99)
    src = YFinanceSource(max_retries=2, pause_sec=0, downloader=rec, sleep=lambda s: None)
    out = src.daily_bars(["0001"], D(2026, 9, 25), D(2026, 9, 25))
    assert out.empty and len(rec.calls) == 3
