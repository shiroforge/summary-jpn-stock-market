import json

import httpx

from jpmarket.models import DailySummary
from jpmarket.notify.discord import COLOR_DOWN, COLOR_UP, DiscordNotifier, build_payload, error_payload

URL = "https://example.github.io/repo/2026-09-25/"


def test_payload_shape_and_limits(sample: DailySummary) -> None:
    p = build_payload(sample, URL)
    e = p["embeds"][0]
    assert e["title"] == "2026/09/25(金) 大引け" and e["url"] == URL
    assert URL in e["description"]
    names = [f["name"] for f in e["fields"]]
    assert names[:4] == ["▲ 上位業種", "▼ 下位業種", "🔥 強いテーマ", "🧊 弱いテーマ"]
    assert "📰 ニュース" in names and "⚠️ 注意" in names
    assert all(len(f["value"]) <= 1024 for f in e["fields"]) and len(e["fields"]) <= 25
    total = (
        len(e["title"]) + len(e["description"]) + sum(len(f["name"]) + len(f["value"]) for f in e["fields"])
    )
    assert total <= 6000
    nk = sample.quote("nikkei225")
    assert nk is not None and e["color"] == (COLOR_UP if nk.change_pct > 0 else COLOR_DOWN)
    assert "日本 10年" in next(f["value"] for f in e["fields"] if f["name"] == "為替・金利・海外")
    json.dumps(p)  # serializable


def test_send_and_dry_run(sample: DailySummary) -> None:
    sent: list[dict[str, object]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        sent.append(json.loads(req.content))
        return httpx.Response(204)

    n = DiscordNotifier(
        "https://discord.test/hook", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    n.send(sample, URL, dry_run=True)
    assert sent == []
    n.send(sample, URL)
    n.send_error("boom", run_url="https://github.com/run/1")
    assert len(sent) == 2
    assert "run/1" in error_payload("boom", "https://github.com/run/1")["embeds"][0]["description"]
