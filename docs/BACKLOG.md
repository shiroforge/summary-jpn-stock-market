# BACKLOG

状態: `todo` → `doing` → `review`（ユーザーの承認待ち）→ `done`。ループでは **上から順に** `todo` を1件ずつ片付ける。
🔒 = 承認ゲート（`review` で止め、ユーザーに提示する）。💰 = 費用が発生する（事前承認が必須）。

## Phase 0: 設計を固める

| ID | 状態 | タスク | 受け入れ条件 |
|---|---|---|---|
| P0-1 | done | リポジトリの初期化（uv, ruff, mypy, pytest） | `ruff check` / `mypy src` / `pytest` が通る |
| P0-2 | done | yfinance・TOPIX・33業種の技術検証 | 結果を DECISIONS D-03〜D-06 に記録 |
| P0-3 | done | RSS の技術検証 | D-07 に記録、`config/news_feeds.yaml` を作成 |
| P0-4 | done | `models.py`（DailySummary v1）と Protocol（sources/news/notify） | ダミーJSONが往復で一致する |
| P0-5 | done | ダミーデータ生成とテンプレート（日次ページ） | `tests/fixtures/sample_summary.json` から HTML を生成できる |
| P0-6 | done | ドキュメント（CLAUDE.md, SPEC, DESIGN, BACKLOG, DECISIONS） | — |
| P0-7 | done | CI（GitHub Actions: lint・型・テスト） | `.github/workflows/ci.yml` |
| P0-8 | done 🔒 | **G1**: 仕様とモック画面の承認 | 「いったん進めて」で仮承認（D-10） |
| P0-9 | done | テーマ株の銘柄数の拡充（ユーザーの要望） | 19テーマ・257銘柄。全コードを確認済み |

## Phase 1: データとページ（ローカル）

| ID | 状態 | タスク | 受け入れ条件 |
|---|---|---|---|
| P1-1 | todo | `calendar.py` 営業日判定 | 祝日・年末年始・振替休日のテスト。前後の営業日を返す関数 |
| P1-2 | todo | `config.py`（pydantic-settings）と YAML の読み込み | 設定の型検証。themes の銘柄コードが重複しても動く |
| P1-3 | todo | `sources/master.py`: topixweight_j.csv の取得・パース・キャッシュ | CP932 の fixture でテスト。30日以内のキャッシュを再利用 |
| P1-4 | todo | `sources/yfinance_src.py`: 分割取得・再取得・429 のバックオフ | 取得部分をモックしてテスト（欠損・429）。出力は long 形式 |
| P1-5 | todo | `sources/yahoo_jp.py`: TOPIX の終値・前日比 | 保存した HTML の fixture でパースをテスト。失敗時は None |
| P1-6 | todo | 株価履歴のキャッシュ（`data/prices/`）への追記 | 同じ日付を何度追記しても重複しない。初回の自動構築（3か月分） |
| P1-7 | todo | `analytics/indices.py`: Quote の生成 | 固定値で騰落率・5日・20日の騰落率を検証 |
| P1-8 | todo | `analytics/sectors.py`: 加重騰落率・中央値・寄与度 | 手計算した値と一致する。カバー率の警告 |
| P1-9 | todo | `analytics/breadth.py` と `rankings.py` | 騰落レシオ・売買代金の足切り・年初来高安 |
| P1-10 | todo | `analytics/themes.py` | 欠けた銘柄を除外して平均。全員欠けていればテーマごと除外 |
| P1-11 | todo | `news/rss.py` とキーワードによるタグ付け | 保存した RSS の fixture でテスト。時間帯で絞り込み・重複を除く |
| P1-12 | todo | コメント生成（ルールベース） | 典型的な3パターン（全面高・まちまち・全面安）のテスト |
| P1-13 | todo | `pipeline.py` と `cli run --date --no-notify --force` | 1コマンドで JSON とサイトを出力。鮮度チェックで失敗したら終了コード 75 |
| P1-14 | todo | サイトビルダー: 日次・index のリダイレクト・アーカイブ・前後の営業日リンク | 複数日の fixture でリンクがつながる |
| P1-15 | todo | 見た目の確認（Playwright でデスクトップ・スマホのスクリーンショット） | `scripts/screenshot.py` を用意 |
| P1-16 | review 🔒 | **G2**: 実データで生成した日次ページの承認 | 直近の営業日で指数の値を公開値と照らし合わせたメモを添える |

## Phase 2: 自動化と通知

| ID | 状態 | タスク | 受け入れ条件 |
|---|---|---|---|
| P2-1 | todo | `notify/discord.py`（Embed・エラー通知・dry-run） | ペイロードのスナップショットテスト |
| P2-2 | todo | `.github/workflows/daily.yml`（cron、再試行、JSONのコミット、Pages へのデプロイ、通知） | 手動実行（workflow_dispatch）で成功する |
| P2-3 | todo | GitHub Actions 上で yfinance の429を確認する | 結果を DECISIONS に記録 |
| P2-4 | review 🔒 | **G3**: 通知の文面と、公開・cron の有効化の承認 | |

## Phase 3: 拡張（承認を得た順に進める）

| ID | 状態 | タスク |
|---|---|---|
| P3-1 | todo | トレンドページ（60日のヒートマップ、テーマの推移の折れ線） |
| P3-2 | todo 🔒💰 | LLM（Claude API）: ニュース要約・一言コメント・テーマ候補の提案 |
| P3-3 | todo 🔒 | TDnet の適時開示（上方修正・決算） |
| P3-4 | todo 🔒💰 | J-Quants への切り替え（公式の33業種・TOPIX） |
| P3-5 | todo 🔒 | Slack / LINE への通知 |
