"""バックテストエンジン。

前提と実装方針:
- シグナルはバー確定時に判定し、約定は「次バーの始値」。先読みを構造的に排除する。
- スプレッドとスリッページを必ずコストに含める(買いは高く、売りは安く約定)。
- SL/TPはATRベース。バー内でSLとTPの両方に触れた場合は不利な方(SL)を優先する保守的判定。
- サイジングは「1トレードのリスク = 残高の risk_per_trade」。
  損益計算は口座通貨=クオート通貨(例: JPY口座でUSD_JPY)を前提とした簡易モデル。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from fxauto.strategy.base import LONG, SHORT, Strategy
from fxauto.strategy.indicators import atr


def pip_size(instrument: str) -> float:
    """1pipの価格単位。JPYクオートは0.01、その他は0.0001。"""
    return 0.01 if instrument.endswith("_JPY") else 0.0001


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp | None
    direction: int          # 1=long, -1=short
    entry_price: float
    exit_price: float | None
    units: float
    sl_price: float
    tp_price: float
    pnl: float | None = None
    exit_reason: str = ""


@dataclass
class BacktestResult:
    trades: list[Trade]
    equity_curve: pd.Series
    initial_balance: float
    final_balance: float
    params: dict = field(default_factory=dict)

    def trades_df(self) -> pd.DataFrame:
        return pd.DataFrame([vars(t) for t in self.trades])


class Backtester:
    def __init__(
        self,
        instrument: str = "USD_JPY",
        initial_balance: float = 1_000_000,
        spread_pips: float = 1.0,
        slippage_pips: float = 0.2,
        atr_period: int = 14,
        sl_atr_mult: float = 1.5,
        tp_atr_mult: float = 3.0,
        risk_per_trade: float = 0.01,
    ):
        self.instrument = instrument
        self.initial_balance = initial_balance
        self.pip = pip_size(instrument)
        self.half_spread = spread_pips * self.pip / 2.0
        self.slippage = slippage_pips * self.pip
        self.atr_period = atr_period
        self.sl_atr_mult = sl_atr_mult
        self.tp_atr_mult = tp_atr_mult
        self.risk_per_trade = risk_per_trade

    def run(self, df: pd.DataFrame, strategy: Strategy) -> BacktestResult:
        data = strategy.generate_signals(df)
        data["atr"] = atr(data, self.atr_period)

        balance = self.initial_balance
        equity = []
        trades: list[Trade] = []
        position: Trade | None = None

        times = data.index
        opens = data["open"].to_numpy()
        highs = data["high"].to_numpy()
        lows = data["low"].to_numpy()
        closes = data["close"].to_numpy()
        signals = data["signal"].to_numpy()
        atrs = data["atr"].to_numpy()

        for i in range(1, len(data)):
            # --- 既存ポジションの決済判定(バーi内の値動きで判定) ---
            if position is not None:
                exit_price, reason = self._check_exit(
                    position, highs[i], lows[i], closes[i], signals[i - 1]
                )
                if exit_price is not None:
                    balance += self._close(position, times[i], exit_price, reason)
                    trades.append(position)
                    position = None

            # --- 新規エントリー(前バー確定シグナル → 当バー始値で約定) ---
            sig = signals[i - 1]
            if position is None and sig in (LONG, SHORT) and not np.isnan(atrs[i - 1]):
                position = self._open(
                    sig, times[i], opens[i], atrs[i - 1], balance
                )

            # 評価残高(含み損益込み)
            unrealized = 0.0
            if position is not None:
                unrealized = (closes[i] - position.entry_price) * position.direction * position.units
            equity.append((times[i], balance + unrealized))

        # 期間終了時に未決済ポジションがあれば最終バー終値で強制決済
        if position is not None:
            exit_price = closes[-1] - position.direction * (self.half_spread + self.slippage)
            balance += self._close(position, times[-1], exit_price, "end_of_data")
            trades.append(position)
            if equity:
                equity[-1] = (times[-1], balance)

        curve = (
            pd.Series(dict(equity), name="equity")
            if equity
            else pd.Series([self.initial_balance], name="equity")
        )
        return BacktestResult(
            trades=trades,
            equity_curve=curve,
            initial_balance=self.initial_balance,
            final_balance=balance,
            params=strategy.params(),
        )

    # ------------------------------------------------------------------
    def _open(
        self, direction: int, time: pd.Timestamp, raw_open: float, atr_value: float, balance: float
    ) -> Trade:
        # 買いは高く・売りは安く約定(半スプレッド+スリッページ)
        entry = raw_open + direction * (self.half_spread + self.slippage)
        sl_dist = atr_value * self.sl_atr_mult
        tp_dist = atr_value * self.tp_atr_mult
        sl = entry - direction * sl_dist
        tp = entry + direction * tp_dist
        # 口座通貨=クオート通貨前提: 1unitの損益 = 価格差 × units
        units = (balance * self.risk_per_trade) / sl_dist if sl_dist > 0 else 0.0
        return Trade(
            entry_time=time, exit_time=None, direction=direction,
            entry_price=entry, exit_price=None, units=units,
            sl_price=sl, tp_price=tp,
        )

    def _check_exit(
        self, pos: Trade, high: float, low: float, close: float, prev_signal: int
    ) -> tuple[float | None, str]:
        """SL→TP→ドテンの優先順で決済価格を返す(SL優先=保守的)。"""
        if pos.direction == LONG:
            if low <= pos.sl_price:
                return pos.sl_price - self.slippage, "stop_loss"
            if high >= pos.tp_price:
                return pos.tp_price, "take_profit"
        else:
            if high >= pos.sl_price:
                return pos.sl_price + self.slippage, "stop_loss"
            if low <= pos.tp_price:
                return pos.tp_price, "take_profit"
        # 反対シグナルが出ていたら成行で手仕舞い(コスト込み)
        if prev_signal == -pos.direction:
            return close - pos.direction * (self.half_spread + self.slippage), "reverse_signal"
        return None, ""

    def _close(self, pos: Trade, time: pd.Timestamp, price: float, reason: str) -> float:
        pos.exit_time = time
        pos.exit_price = price
        pos.exit_reason = reason
        pos.pnl = (price - pos.entry_price) * pos.direction * pos.units
        return pos.pnl
