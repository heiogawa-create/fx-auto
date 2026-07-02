# fx-auto

FX自動売買システム(OANDAデモ口座専用)。
「すぐ勝てるbot」ではなく、**戦略を安全に検証 → 改善 → 運用できる基盤**。

## 構成

```
fxauto/
├── config.py          # config.yaml / .env の読み込み
├── data/              # ① データ取得層
│   ├── oanda_client.py    # OANDA v20 REST(fxpractice固定・リトライ付き)
│   └── store.py           # ローソク足取得 + parquetキャッシュ
├── strategy/          # ② 戦略層(差し替え可能)
│   ├── base.py            # Strategy 抽象クラス
│   ├── indicators.py      # EMA / RSI / ATR
│   └── ema_rsi.py         # EMAクロス + RSIフィルタ(初期実装)
├── backtest/          # ③ バックテストエンジン
│   ├── engine.py          # スプレッド・スリッページ込み、次バー始値約定
│   ├── metrics.py         # PF / 最大DD / 勝率 / シャープ / 取引回数 + 過剰最適化警告
│   └── walkforward.py     # IS/OOS分割のwalk-forward検証
├── risk/              # ④ リスク管理層(戦略から独立)
│   └── manager.py         # 1%ルール・SL必須・日次損失停止・ポジション上限
├── execution/         # ⑤ 実行エンジン(デモ口座フォワードテスト)
│   ├── engine.py          # ポーリングループ(例外で落ちない)
│   └── trade_log.py       # 全取引をCSV + JSONLに記録
└── notify/            # ⑥ 通知(Discord webhook / LINE Notify)
    └── notifier.py
```

## セットアップ

```bash
pip install -r requirements.txt
cp .env.example .env   # OANDAデモ口座のトークンを記入
```

`.env` に設定するのは **fxpractice(デモ口座)のAPIトークンのみ**。
接続先URLはコード内で `api-fxpractice.oanda.com` に固定されており、
本番口座に接続するコードは存在しない。

## 使い方

```bash
# 1. データ取得(parquetにキャッシュ。2回目以降は差分のみ取得)
python scripts/fetch_data.py --days 730

# 2. バックテスト(スプレッド・スリッページ込み)
python scripts/run_backtest.py

# 3. walk-forward検証(In-Sample最適化 → Out-of-Sample評価)
python scripts/run_walkforward.py

# 4. デモ口座でフォワードテスト(Ctrl+Cで停止)
python scripts/run_forward.py

# テスト
python -m pytest tests/ -q
```

通貨ペア・時間足・戦略パラメータ・リスク設定はすべて `config.yaml` で変更する。

## リスク管理ルール(risk/manager.py で強制)

- 1トレードのリスクは口座残高の **1%** まで(SL幅からロットを自動計算)
- **SL(逆指値)のない注文は組み立て不可**(クライアント層でも二重にチェック)
- 日次損失が残高の3%に達したら **その日は新規エントリー停止**
- 同時ポジション数は上限まで(既定1)

## 過剰最適化への防衛

- バックテストが **PF > 3 / 勝率 > 80% / シャープ > 3** を出したら警告
  (まずバグ = 先読み・コスト抜けを疑う)
- 取引回数が30回未満なら「統計的に信頼できない」警告
- walk-forwardでOOSのPFがISの半分未満に劣化したら過剰最適化警告
- バックテストの約定は「シグナル確定の**次バー始値** + スプレッド + スリッページ」で
  先読みを構造的に排除(`tests/test_backtest.py::test_no_lookahead_truncation` で検証)

## 戦略の追加方法

1. `fxauto/strategy/` に `Strategy` を継承したクラスを作る
   (`generate_signals(df)` が `signal` 列 {-1, 0, 1} を返すだけ)
2. `fxauto/strategy/__init__.py` の `STRATEGIES` に登録
3. `config.yaml` の `strategy.name` を切り替える

ロット計算・SL・損失制限はリスク管理層が持つため、戦略側には書かない。
