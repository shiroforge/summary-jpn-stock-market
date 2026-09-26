import datetime as dt
from pathlib import Path

import httpx
import pytest

from jpmarket.sources.rates import load_fred, load_jgb_yields, parse_fred_csv, parse_mof_csv, parse_wareki

FIX = Path(__file__).parent / "fixtures"


def test_wareki() -> None:
    assert parse_wareki("R8.9.24") == dt.date(2026, 9, 24)
    assert parse_wareki("H31.4.26") == dt.date(2019, 4, 26)
    assert parse_wareki("S49.9.24") == dt.date(1974, 9, 24)
    assert parse_wareki("基準日") is None


def test_parse_mof() -> None:
    df = parse_mof_csv((FIX / "jgbcm_sample.csv").read_bytes())
    assert df.index[0] == dt.date(2026, 9, 1)
    assert df.at[dt.date(2026, 9, 24), "10年"] == pytest.approx(3.073)
    old = parse_mof_csv((FIX / "jgbcm_all_sample.csv").read_bytes())
    assert "40年" not in old.loc[dt.date(1974, 9, 24)].dropna().index  # "-" skipped


def test_load_jgb_combines_history_and_current(tmp_path: Path) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        name = "jgbcm_all_sample.csv" if "jgbcm_all" in str(req.url) else "jgbcm_sample.csv"
        return httpx.Response(200, content=(FIX / name).read_bytes())

    df = load_jgb_yields(
        tmp_path, today=dt.date(2026, 9, 25), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    assert df.index.is_monotonic_increasing and not df.index.duplicated().any()
    assert df.index.min() <= dt.date(2026, 8, 31) and df.index.max() == dt.date(2026, 9, 24)
    assert (tmp_path / "rates" / "jgbcm_all.csv").exists()


def test_fred() -> None:
    s = parse_fred_csv((FIX / "fred_dgs2.csv").read_text())
    assert list(s.index) == [dt.date(2026, 9, 22), dt.date(2026, 9, 24)]  # "." skipped
    failing = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    assert load_fred("DGS2", client=failing).empty
