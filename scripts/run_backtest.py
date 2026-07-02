"""キャッシュ済みデータでバックテストを実行し、結果をHTMLレポートに出力する。

使い方:
    python scripts/fetch_data.py --days 730   # 先にデータ取得
    python scripts/run_backtest.py
    python scripts/run_backtest.py --no-report   # HTML出力をスキップしてコンソール表示のみ
"""

from __future__ import annotations

import argparse
import logging
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fxauto.backtest.engine import Backtester
from fxauto.backtest.metrics import compute_metrics, periods_per_year_for
from fxauto.backtest.report import write_report
from fxauto.config import load_config
from fxauto.data.store import CandleStore
from fxauto.strategy import create_strategy

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="バックテスト実行")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--no-report", action="store_true", help="HTMLレポートを出力しない")
    parser.add_argument("--no-open", action="store_true", help="レポートを自動でブラウザ表示しない")
    parser.add_argument("--out", default="reports/backtest_report.html")
    args = parser.parse_args()

    cfg = load_config(args.config)
    source = cfg["data"].get("source", "yfinance")
    cache_source = "oanda" if source == "oanda" else "yf"

    store = CandleStore(client=None, cache_dir=cfg["data"]["cache_dir"])
    df = store.load_cache(cfg["instrument"], cfg["granularity"], source=cache_source)
    if df is None or df.empty:
        raise SystemExit("キャッシュがありません。先に scripts/fetch_data.py を実行してください")

    strategy = create_strategy(cfg["strategy"]["name"], cfg["strategy"]["params"].to_dict())
    bt_cfg = cfg["backtest"]
    backtester = Backtester(
        instrument=cfg["instrument"],
        initial_balance=bt_cfg["initial_balance"],
        spread_pips=bt_cfg["spread_pips"],
        slippage_pips=bt_cfg["slippage_pips"],
        atr_period=bt_cfg["atr_period"],
        sl_atr_mult=bt_cfg["sl_atr_mult"],
        tp_atr_mult=bt_cfg["tp_atr_mult"],
        risk_per_trade=bt_cfg["risk_per_trade"],
    )
    result = backtester.run(df, strategy)
    metrics = compute_metrics(result, periods_per_year=periods_per_year_for(cfg["granularity"]))

    print(f"\n=== バックテスト結果: {cfg['instrument']} {cfg['granularity']} "
          f"({df.index.min().date()} 〜 {df.index.max().date()}) ===")
    print(f"戦略: {strategy.name} {strategy.params()}")
    print(metrics.summary())
    print(f"最終残高: {result.final_balance:,.0f}(初期 {result.initial_balance:,.0f})")

    if not args.no_report:
        path = write_report(result, metrics, cfg["instrument"], cfg["granularity"],
                            strategy.name, args.out)
        print(f"\nHTMLレポート: {path.resolve()}")
        if not args.no_open:
            webbrowser.open(path.resolve().as_uri())


if __name__ == "__main__":
    main()
