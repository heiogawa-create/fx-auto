"""デモ口座でのフォワードテストを開始する。

使い方:
    python scripts/run_forward.py

Ctrl+C で停止。全取引は logs/ にCSV+JSONで記録され、通知が設定されていれば
エントリー/決済/エラーがDiscord/LINEに送られる。
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fxauto.config import get_oanda_credentials, load_config
from fxauto.data.oanda_client import OandaClient
from fxauto.execution.engine import ForwardTestEngine
from fxauto.execution.trade_log import TradeLogger
from fxauto.notify.notifier import Notifier
from fxauto.risk.manager import RiskManager
from fxauto.strategy import create_strategy

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="フォワードテスト(デモ口座)")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    token, account_id = get_oanda_credentials()
    client = OandaClient(token, account_id)

    risk_cfg = cfg["risk"]
    bt_cfg = cfg["backtest"]
    engine = ForwardTestEngine(
        client=client,
        strategy=create_strategy(cfg["strategy"]["name"], cfg["strategy"]["params"].to_dict()),
        risk_manager=RiskManager(
            risk_per_trade=risk_cfg["risk_per_trade"],
            max_daily_loss=risk_cfg["max_daily_loss"],
            max_positions=risk_cfg["max_positions"],
            min_units=risk_cfg["min_units"],
            max_units=risk_cfg["max_units"],
        ),
        trade_logger=TradeLogger(cfg["execution"]["log_dir"]),
        notifier=Notifier(
            channel=cfg["notify"]["channel"], enabled=cfg["notify"]["enabled"]
        ),
        instrument=cfg["instrument"],
        granularity=cfg["granularity"],
        atr_period=bt_cfg["atr_period"],
        sl_atr_mult=bt_cfg["sl_atr_mult"],
        tp_atr_mult=bt_cfg["tp_atr_mult"],
        poll_interval_sec=cfg["execution"]["poll_interval_sec"],
    )
    engine.run_forever()


if __name__ == "__main__":
    main()
