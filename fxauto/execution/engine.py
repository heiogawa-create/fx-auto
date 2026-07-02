"""フォワードテスト実行エンジン(OANDAデモ口座専用)。

方針:
- 確定した最新バーのシグナルで成行エントリー(SL/TP付き)。同一バーで二重発注しない。
- 発注は必ず RiskManager を通す。SLなし・日次損失超過・ポジション上限超過は発注不可。
- API切断・例外ではプロセスを落とさず、ログと通知に残して次のループへ。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import pandas as pd

from fxauto.backtest.engine import pip_size
from fxauto.data.oanda_client import OandaClient, OandaError
from fxauto.data.store import candles_to_df
from fxauto.execution.trade_log import TradeLogger
from fxauto.notify.notifier import Notifier
from fxauto.risk.manager import RiskManager, RiskRejection
from fxauto.strategy.base import Strategy
from fxauto.strategy.indicators import atr

logger = logging.getLogger(__name__)


class ForwardTestEngine:
    def __init__(
        self,
        client: OandaClient,
        strategy: Strategy,
        risk_manager: RiskManager,
        trade_logger: TradeLogger,
        notifier: Notifier,
        instrument: str = "USD_JPY",
        granularity: str = "H1",
        atr_period: int = 14,
        sl_atr_mult: float = 1.5,
        tp_atr_mult: float = 3.0,
        poll_interval_sec: float = 60.0,
        candle_history: int = 300,
    ):
        self.client = client
        self.strategy = strategy
        self.risk = risk_manager
        self.trade_log = trade_logger
        self.notifier = notifier
        self.instrument = instrument
        self.granularity = granularity
        self.atr_period = atr_period
        self.sl_atr_mult = sl_atr_mult
        self.tp_atr_mult = tp_atr_mult
        self.poll_interval_sec = poll_interval_sec
        self.candle_history = candle_history
        self._last_signal_bar: pd.Timestamp | None = None
        self._known_trade_ids: set[str] = set()
        self._last_balance: float | None = None

    # ------------------------------------------------------------------
    def run_forever(self) -> None:
        logger.info("フォワードテスト開始: %s %s(デモ口座)", self.instrument, self.granularity)
        self.notifier.send(f"▶ フォワードテスト開始: {self.instrument} {self.granularity}")
        while True:
            try:
                self.step()
            except KeyboardInterrupt:
                logger.info("手動停止")
                self.notifier.send("⏹ フォワードテスト停止(手動)")
                break
            except OandaError as e:
                # リトライ済みでも失敗した場合。落とさず次のループで再試行する
                logger.error("APIエラー(継続): %s", e)
                self.trade_log.log_error(str(e))
                self.notifier.notify_error(str(e)[:300])
            except Exception as e:  # noqa: BLE001 - 想定外でもループは維持する
                logger.exception("想定外のエラー(継続)")
                self.trade_log.log_error(f"unexpected: {e}")
                self.notifier.notify_error(f"想定外: {e}")
            time.sleep(self.poll_interval_sec)

    # ------------------------------------------------------------------
    def step(self) -> None:
        """1回分の処理。テストしやすいように run_forever から分離。"""
        account = self.client.get_account_summary()
        balance = float(account["balance"])
        open_trades = self.client.get_open_trades()
        today = datetime.now(timezone.utc).date()
        self.risk.start_day_if_needed(today, balance)

        self._detect_closed_trades(open_trades, balance)
        self._last_balance = balance

        candles = self.client.get_candles(
            self.instrument, self.granularity, count=self.candle_history
        )
        df = candles_to_df(candles)
        if len(df) < self.atr_period + 5:
            logger.warning("ローソク足が不足(%d本)。スキップ", len(df))
            return

        data = self.strategy.generate_signals(df)
        data["atr"] = atr(data, self.atr_period)
        last = data.iloc[-1]
        bar_time = data.index[-1]

        # 同じバーで二度シグナル処理しない
        if self._last_signal_bar is not None and bar_time <= self._last_signal_bar:
            return
        self._last_signal_bar = bar_time

        signal = int(last["signal"])
        if signal == 0 or pd.isna(last["atr"]):
            return

        price = float(last["close"])
        pip = pip_size(self.instrument)
        sl_dist = float(last["atr"]) * self.sl_atr_mult
        sl_dist = max(sl_dist, pip)  # SL幅ゼロ防止
        sl_price = price - signal * sl_dist
        tp_price = price + signal * float(last["atr"]) * self.tp_atr_mult

        try:
            plan = self.risk.build_order(
                instrument=self.instrument,
                direction=signal,
                balance=balance,
                entry_price=price,
                sl_price=sl_price,
                tp_price=tp_price,
                open_positions=len(open_trades),
                today=today,
            )
        except RiskRejection as e:
            logger.info("エントリー見送り: %s", e)
            self.trade_log.log("risk_rejection", instrument=self.instrument,
                               direction=signal, reason=str(e))
            return

        resp = self.client.create_market_order(
            instrument=plan.instrument,
            units=plan.units,
            stop_loss_price=plan.sl_price,
            take_profit_price=plan.tp_price,
        )
        self.trade_log.log_entry(
            plan.instrument, plan.direction, plan.units, price, plan.sl_price, plan.tp_price
        )
        self.notifier.notify_entry(plan.instrument, plan.direction, plan.units, price, plan.sl_price)
        logger.info("発注完了: %s", resp.get("orderFillTransaction", {}).get("id", "?"))

    # ------------------------------------------------------------------
    def _detect_closed_trades(self, open_trades: list[dict], balance: float) -> None:
        """前回見えていたトレードが消えていたら決済とみなして記録する。"""
        current_ids = {t["id"] for t in open_trades}
        closed = self._known_trade_ids - current_ids
        if closed and self._last_balance is not None:
            realized = balance - self._last_balance
            self.risk.record_realized_pnl(realized)
            self.trade_log.log_exit(self.instrument, realized, f"closed trades: {sorted(closed)}")
            self.notifier.notify_exit(self.instrument, realized, "SL/TP到達または手動決済")
            if self.risk.daily_loss_reached():
                self.notifier.send("🛑 日次損失上限に到達。本日の新規エントリーを停止します")
        self._known_trade_ids = current_ids
