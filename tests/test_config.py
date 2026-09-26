from jpmarket.config import Settings


def test_load_real_config() -> None:
    s = Settings()
    keys = [q.key for q in s.quotes]
    assert "nikkei225" in keys and "topix" in keys
    assert len(keys) == len(set(keys))
    assert len(s.sector17_etfs) == 17
    assert len(s.themes) >= 15
    theme_keys = [t.key for t in s.themes]
    assert len(theme_keys) == len(set(theme_keys))
    for t in s.themes:
        assert all(isinstance(c, str) and len(c) == 4 for c in t.members), t.key
    assert s.feeds and s.news_max_items > 0
