"""同じ戦略・同じパラメータを複数の通貨ペアで一括バックテストする。

目的はサンプル数(取引回数)を増やして戦略の信頼性を測ること。
1つの通貨ペアに合わせてパラメータを調整し続けるとカーブフィッティングに
なるため、「調整していない他のペアでも通用するか」を見る。

使い方:
    python scripts/run_multi_backtest.py --days 3650
    python scripts/run_multi_backtest.py --instruments USD_JPY EUR_USD GBP_USD
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fxauto.backtest.engine import Backtester
from fxauto.backtest.metrics import combine_trade_stats, compute_metrics, periods_per_year_for
from fxauto.config import load_config
from fxauto.data.store import CandleStore
from fxauto.strategy import create_strategy

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")

DEFAULT_INSTRUMENTS = ["USD_JPY", "EUR_USD", "GBP_USD", "AUD_USD", "EUR_JPY"]


def main() -> None:
    parser = argparse.ArgumentParser(description="複数通貨ペア一括バックテスト")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--days", type=int, default=3650)
    parser.add_argument("--instruments", nargs="+", default=DEFAULT_INSTRUMENTS)
    args = parser.parse_args()

    cfg = load_config(args.config)
    store = CandleStore(client=None, cache_dir=cfg["data"]["cache_dir"])
    start = datetime.now(timezone.utc) - timedelta(days=args.days)
    bt_cfg = cfg["backtest"]
    strategy_params = cfg["strategy"]["params"].to_dict()

    results = []
    print(f"\n=== 複数通貨ペア一括バックテスト({cfg['granularity']}, "
          f"戦略パラメータは全ペア共通) ===")
    print(f"{'ペア':<10} {'取引':>4} {'PF':>6} {'勝率':>7} {'最大DD':>7} {'リターン':>8}")
    print("-" * 50)

    for instrument in args.instruments:
        try:
            df = store.fetch_free(instrument, cfg["granularity"], start=start)
        except Exception as e:  # noqa: BLE001 - 1ペアの失敗で全体を止めない
            print(f"{instrument:<10} 取得失敗: {e}")
            continue
        if df is None or len(df) < 300:
            print(f"{instrument:<10} データ不足({0 if df is None else len(df)}本)。スキップ")
            continue

        strategy = create_strategy(cfg["strategy"]["name"], strategy_params)
        result = Backtester(
            instrument=instrument,
            initial_balance=bt_cfg["initial_balance"],
            spread_pips=bt_cfg["spread_pips"],
            slippage_pips=bt_cfg["slippage_pips"],
            atr_period=bt_cfg["atr_period"],
            sl_atr_mult=bt_cfg["sl_atr_mult"],
            tp_atr_mult=bt_cfg["tp_atr_mult"],
            risk_per_trade=bt_cfg["risk_per_trade"],
        ).run(df, strategy)
        m = compute_metrics(result, periods_per_year=periods_per_year_for(cfg["granularity"]))
        results.append(result)
        print(f"{instrument:<10} {m.num_trades:>4} {m.profit_factor:>6.2f} "
              f"{m.win_rate:>6.1%} {m.max_drawdown:>6.1%} {m.total_return:>+7.1%}")

    if not results:
        raise SystemExit("有効な結果がありません。ネットワーク接続と通貨ペア表記を確認してください")

    combined = combine_trade_stats(results)
    print("\n=== 全ペア合算(R倍数ベース) ===")
    print(combined.summary())

    losing = sum(1 for r in results
                 if compute_metrics(r).profit_factor < 1.0 and len(r.trades) > 0)
    if losing > len(results) / 2:
        print(f"\n⚠ {losing}/{len(results)} ペアで負けています。"
              "この戦略はUSD_JPY固有の偶然に依存している可能性があります")
    if combined.num_trades < 30:
        print(f"\n⚠ 合算しても{combined.num_trades}回。まだ統計的な信頼には不足しています")


if __name__ == "__main__":
    main()
