"""Walk-forward検証(IS最適化 → OOS評価)を実行する。

使い方:
    python scripts/run_walkforward.py
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fxauto.backtest.walkforward import walk_forward
from fxauto.config import load_config
from fxauto.data.store import CandleStore
from fxauto.strategy.ema_rsi import EmaRsiStrategy

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# IS期間で総当たりするパラメータ候補(意図的に粗くしてある。
# 細かくしすぎるとカーブフィッティングまっしぐらなので注意)
PARAM_GRID = {
    "fast_ema": [10, 20, 30],
    "slow_ema": [50, 100],
    "rsi_period": [14],
    "rsi_long_max": [60.0, 70.0],
    "rsi_short_min": [30.0, 40.0],
}


def main() -> None:
    parser = argparse.ArgumentParser(description="walk-forward検証")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    store = CandleStore(client=None, cache_dir=cfg["data"]["cache_dir"])
    df = store.load_cache(cfg["instrument"], cfg["granularity"])
    if df is None or df.empty:
        raise SystemExit("キャッシュがありません。先に scripts/fetch_data.py を実行してください")

    bt_cfg = cfg["backtest"]
    result = walk_forward(
        df,
        strategy_cls=EmaRsiStrategy,
        param_grid=PARAM_GRID,
        backtester_kwargs=dict(
            instrument=cfg["instrument"],
            initial_balance=bt_cfg["initial_balance"],
            spread_pips=bt_cfg["spread_pips"],
            slippage_pips=bt_cfg["slippage_pips"],
            atr_period=bt_cfg["atr_period"],
            sl_atr_mult=bt_cfg["sl_atr_mult"],
            tp_atr_mult=bt_cfg["tp_atr_mult"],
            risk_per_trade=bt_cfg["risk_per_trade"],
        ),
        n_splits=cfg["walkforward"]["n_splits"],
        train_ratio=cfg["walkforward"]["train_ratio"],
    )
    print("\n=== Walk-Forward 結果 ===")
    print(result.summary())


if __name__ == "__main__":
    main()
