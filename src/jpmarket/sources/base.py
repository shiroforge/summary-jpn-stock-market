"""Market data source interface. yfinance now, J-Quants later — analytics depend only on this."""

from __future__ import annotations

import datetime as dt
from typing import Protocol

import pandas as pd


class MarketDataSource(Protocol):
    name: str

    def daily_bars(self, symbols: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
        """Daily OHLCV in long format.

        Columns: symbol (str), date (datetime.date), open, high, low, close, volume (float).
        `symbols` use the source-neutral form: TSE code ("7203", "285A") or a source ticker for
        non-TSE instruments ("^N225", "USDJPY=X"). Missing symbols are omitted, never raised.
        """
        ...


class Constituent(Protocol):
    code: str
    name: str
    sector33: str
    topix_weight_pct: float
