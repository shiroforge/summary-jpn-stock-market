# CLAUDE.md — 大引けノート（jpmarket）

東証の引け後サマリ（指数・33業種・テーマ・ランキング・ニュース）を静的サイトに生成し、Discord に要約とURLを送るツール。
**開発はループエンジニアリングで行う。Claude が自律的に実装し、ユーザーは機能とデザインの承認者。**

## 必ず読むもの
- `docs/BACKLOG.md` — 次にやるタスク（上から順に）
- `docs/SPEC.md` — 機能仕様
- `docs/DESIGN.md` — 画面設計・トークン
- `docs/DECISIONS.md` — これまでの設計判断。新しい判断をしたら追記する

## コマンド
```bash
uv sync                                   # 依存関係
uv run ruff check . && uv run ruff format --check .
uv run mypy src                           # strict
uv run pytest                             # ネットワークなし（-m network で実通信テスト）
uv run python tests/fixtures/make_sample.py   # ダミーデータの再生成
uv run jpmarket render tests/fixtures/sample_summary.json --out site/index.html
```

## 1ループの手順
1. BACKLOG の `todo` のうち一番上のタスクを `doing` にする
2. 実装し、テストを書く。外部通信は fixture（`tests/fixtures/`）とモックで置き換える
3. ruff / mypy / pytest がすべて通るまで直す
4. 画面を変えたら、fixture からサイトを生成し、スクリーンショット（デスクトップ 1280px・スマホ 390px、ライト・ダーク）を撮って確認する
5. ブランチ `loop/<タスクID>` にコミットし、BACKLOG の状態を `done` にする（🔒 のタスクは `review`）
6. 🔒 のタスクでは止まってユーザーに提示する。それ以外は次のタスクへ進む

## 完了の定義
- 受け入れ条件を満たす / テストがある / lint・型・テストがすべて通る
- 仕様や判断を変えたら SPEC / DECISIONS を更新する
- 画面を変えたら、スクリーンショットで崩れがないことを確認した

## 自分で判断しないこと（必ずユーザーに確認）
- 💰 費用が発生するもの（J-Quants 有料プラン、Claude API など）
- 公開範囲の変更、デプロイ・cron の有効化、Discord への実送信（テスト用チャンネルを除く）
- 画面デザインの大きな変更、`DailySummary` から項目を削除する変更
- 利用規約上グレーなデータ取得元の追加

## コーディング規約
- Python 3.13、型ヒント必須（mypy strict）。行の長さは110文字
- `DailySummary`（models.py）が生成側と消費側の唯一の契約。変更したら `SCHEMA_VERSION` と DECISIONS を更新する
- データ源・ニュース・通知は `*/base.py` の Protocol を実装する。他の層から具体的な実装を直接 import しない（組み立ては pipeline で行う）
- yfinance は 429 を前提にする（D-05）。テストで実際の API を叩かない
- ニュースは見出し・リンク・メタデータのみを扱い、本文は保存しない
- 表示文言は日本語。コードのコメントは英語でも日本語でもよい
- 秘密情報は環境変数から読み、コミットしない
