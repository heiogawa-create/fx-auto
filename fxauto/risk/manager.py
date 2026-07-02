"""リスク管理層。戦略から完全に独立しており、全ての発注はここを通る。

ルール:
1. 1トレードのリスクは口座残高の risk_per_trade(既定1%)まで。ロットは自動計算。
2. SL(逆指値)のない注文は組み立て自体を拒否する。
3. 日次損失が max_daily_loss に達したらその日は新規エントリー停止。
4. 同時ポジション数は max_positions まで。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

logger = logging.getLogger(__name__)


@dataclass
class OrderPlan:
    """リスクチェックを通過した発注計画。"""
    instrument: str
    direction: int          # 1=long, -1=short
    units: int              # 符号付き(ショートは負)
    entry_price_hint: float
    sl_price: float
    tp_price: float | None
    risk_amount: float      # このトレードで許容する損失額(口座通貨)


class RiskRejection(Exception):
    """リスクルールにより発注が拒否された。"""


class RiskManager:
    def __init__(
        self,
        risk_per_trade: float = 0.01,
        max_daily_loss: float = 0.03,
        max_positions: int = 1,
        min_units: int = 1,
        max_units: int = 100_000,
    ):
        if not 0 < risk_per_trade <= 0.02:
            raise ValueError("risk_per_trade は0より大きく2%以下にすること")
        self.risk_per_trade = risk_per_trade
        self.max_daily_loss = max_daily_loss
        self.max_positions = max_positions
        self.min_units = min_units
        self.max_units = max_units
        self._daily_pnl = 0.0
        self._daily_start_balance: float | None = None
        self._current_day: date | None = None

    # ------------------------------------------------------------------
    # 日次損失トラッキング
    # ------------------------------------------------------------------
    def start_day_if_needed(self, today: date, balance: float) -> None:
        if self._current_day != today:
            self._current_day = today
            self._daily_pnl = 0.0
            self._daily_start_balance = balance
            logger.info("日次リセット: %s 開始残高=%.0f", today, balance)

    def record_realized_pnl(self, pnl: float) -> None:
        self._daily_pnl += pnl

    def daily_loss_reached(self) -> bool:
        if self._daily_start_balance is None:
            return False
        return self._daily_pnl <= -self._daily_start_balance * self.max_daily_loss

    # ------------------------------------------------------------------
    # 発注計画の組み立て(全チェックを通過しないと OrderPlan は作れない)
    # ------------------------------------------------------------------
    def build_order(
        self,
        instrument: str,
        direction: int,
        balance: float,
        entry_price: float,
        sl_price: float,
        tp_price: float | None,
        open_positions: int,
        today: date,
        quote_to_account_rate: float = 1.0,
    ) -> OrderPlan:
        """リスクルールを満たす注文だけを組み立てる。

        quote_to_account_rate: クオート通貨→口座通貨の換算レート。
        口座通貨=クオート通貨(JPY口座でUSD_JPY等)なら1.0のままで良い。
        """
        self.start_day_if_needed(today, balance)

        if direction not in (1, -1):
            raise RiskRejection(f"不正な方向: {direction}")
        if self.daily_loss_reached():
            raise RiskRejection(
                f"日次損失上限({self.max_daily_loss:.0%})に到達済み。本日の新規エントリーは停止中"
            )
        if open_positions >= self.max_positions:
            raise RiskRejection(f"同時ポジション数上限({self.max_positions})に到達")

        # SL必須チェック: 方向と整合しないSLも拒否
        sl_distance = (entry_price - sl_price) * direction
        if sl_price <= 0 or sl_distance <= 0:
            raise RiskRejection(
                f"SLが無効です(entry={entry_price}, sl={sl_price}, dir={direction})。"
                "SLなしのエントリーは許可されません"
            )

        risk_amount = balance * self.risk_per_trade
        units = int(risk_amount / (sl_distance * quote_to_account_rate))
        if units < self.min_units:
            raise RiskRejection(
                f"計算ロット({units})が最小単位({self.min_units})未満。エントリー見送り"
            )
        units = min(units, self.max_units)

        return OrderPlan(
            instrument=instrument,
            direction=direction,
            units=units * direction,
            entry_price_hint=entry_price,
            sl_price=sl_price,
            tp_price=tp_price,
            risk_amount=risk_amount,
        )
