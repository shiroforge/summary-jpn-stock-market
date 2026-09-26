import datetime as dt

from jpmarket.models import DailySummary
from jpmarket.render.builder import heat_level, jst, nice_max, num, pct, render_daily, spark_path, tone


def test_formatters() -> None:
    assert pct(1.234) == "+1.23%"
    assert pct(-0.001) == "0.00%"
    assert pct(None) == "—"
    assert num(65432.1) == "65,432"
    assert num(4128.59) == "4,128.59"
    assert tone(0.0) == "flat" and tone(0.5) == "up" and tone(-0.5) == "down"
    assert heat_level(0.1) == "z" and heat_level(-2.5) == "dn3" and heat_level(0.5) == "up1"
    assert nice_max([0.3, -0.8]) == 1.0
    assert nice_max([4.06, -0.79]) == 5.0
    assert jst(dt.datetime(2026, 9, 25, 6, 30, tzinfo=dt.UTC), "%H:%M") == "15:30"


def test_spark_path_bounds() -> None:
    p = spark_path([1, 3, 2], w=100, h=20, pad=2)
    assert str(p["line"]).startswith("M2.0,")
    assert p["x"] == 98.0


def test_render_standalone(sample: DailySummary) -> None:
    html = render_daily(sample)
    assert html.lstrip().startswith("<!doctype html>")
    assert 'name="robots" content="noindex' in html
    for sec in sample.sectors:
        assert sec.name in html
    assert "推計値" in html


def test_render_fragment(sample: DailySummary) -> None:
    html = render_daily(sample, standalone=False)
    assert "<html" not in html and "<body" not in html
    assert "<title>" in html


def test_bp_and_shares() -> None:
    from jpmarket.render.builder import bp, shares

    assert bp(0.021) == "+2.1bp" and bp(-0.1) == "-10.0bp" and bp(0.0) == "0.0bp" and bp(None) == "—"
    assert shares(12_345_678) == "1,235万株" and shares(250_000_000) == "2.50億株"


def test_render_rates_and_surge(sample: DailySummary) -> None:
    html = render_daily(sample)
    assert 'id="rates"' in html and "bp</td>" in html
    assert "出来高急増" in html and "万株" in html
