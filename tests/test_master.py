import datetime as dt
from pathlib import Path

import httpx
import pytest

from jpmarket.sources.master import load_master, parse_topixweight

FIX = Path(__file__).parent / "fixtures" / "topixweight_sample.csv"


def test_parse() -> None:
    m = parse_topixweight(FIX.read_bytes())
    assert m.as_of == dt.date(2026, 7, 31)
    first = m.constituents[0]
    assert (first.code, first.name, first.sector33) == ("1301", "極洋", "水産・農林業")
    assert first.topix_weight_pct == pytest.approx(0.0048)
    assert "1332" in m.by_code()


def _client(content: bytes, status: int = 200) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(status, content=content)))


def test_load_downloads_and_caches(tmp_path: Path) -> None:
    m = load_master(tmp_path, today=dt.date(2026, 9, 25), client=_client(FIX.read_bytes()))
    assert len(m.constituents) > 10
    assert (tmp_path / "master" / "topixweight_j.csv").exists()
    # second call uses the fresh cache even if the network fails
    m2 = load_master(tmp_path, today=dt.date(2026, 9, 25), client=_client(b"", 500))
    assert m2 == m


def test_load_falls_back_to_stale_cache(tmp_path: Path) -> None:
    load_master(tmp_path, today=dt.date(2026, 9, 25), client=_client(FIX.read_bytes()))
    m = load_master(tmp_path, today=dt.date(2027, 9, 25), client=_client(b"", 500))
    assert m.as_of == dt.date(2026, 7, 31)


def test_load_raises_without_cache(tmp_path: Path) -> None:
    with pytest.raises(httpx.HTTPError):
        load_master(tmp_path, today=dt.date(2026, 9, 25), client=_client(b"", 500))
