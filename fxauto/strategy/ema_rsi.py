"""EMAクロス + RSIフィルタ戦略(初期実装のルールベース1本)。

ルール:
- 短期EMAが長期EMAを上抜け、かつ RSI < rsi_long_max のときロング
- 短期EMAが長期EMAを下抜け、かつ RSI > rsi_short_min のときショート
RSIフィルタは「伸び切ったところで飛び乗る」ことを防ぐのが目的。
"""

from __future__ import annotations

import pandas as pd

from fxauto.strategy.base import FLAT, LONG, SHORT, Strategy
from fxauto.strategy.indicators import ema, rsi


class EmaRsiStrategy(Strategy):
    def __init__(
        self,
        fast_ema: int = 20,
        slow_ema: int = 50,
        rsi_period: int = 14,
        rsi_long_max: float = 65.0,
        rsi_short_min: float = 35.0,
    ):
        if fast_ema >= slow_ema:
            raise ValueError("fast_ema は slow_ema より小さくすること")
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.rsi_period = rsi_period
        self.rsi_long_max = rsi_long_max
        self.rsi_short_min = rsi_short_min

    def params(self) -> dict:
        return {
            "fast_ema": self.fast_ema,
            "slow_ema": self.slow_ema,
            "rsi_period": self.rsi_period,
            "rsi_long_max": self.rsi_long_max,
            "rsi_short_min": self.rsi_short_min,
        }

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["ema_fast"] = ema(out["close"], self.fast_ema)
        out["ema_slow"] = ema(out["close"], self.slow_ema)
        out["rsi"] = rsi(out["close"], self.rsi_period)

        above = out["ema_fast"] > out["ema_slow"]
        cross_up = above & ~above.shift(1, fill_value=False)
        cross_down = ~above & above.shift(1, fill_value=True)
        # 指標が揃っていない先頭区間はシグナルを出さない
        valid = out["ema_slow"].notna() & out["rsi"].notna()

        out["signal"] = FLAT
        out.loc[valid & cross_up & (out["rsi"] < self.rsi_long_max), "signal"] = LONG
        out.loc[valid & cross_down & (out["rsi"] > self.rsi_short_min), "signal"] = SHORT
        return out
