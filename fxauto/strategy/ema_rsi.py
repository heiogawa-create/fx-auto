"""EMAクロス + RSIフィルタ戦略(初期実装のルールベース1本)。

ルール:
- 短期EMAが長期EMAを上抜け、かつ RSI < rsi_long_max のときロング
- 短期EMAが長期EMAを下抜け、かつ RSI > rsi_short_min のときショート
- trend_ema を設定した場合はさらに長期トレンドフィルタを適用:
  終値がトレンドEMAより上のときだけロング、下のときだけショート。
  クロスがトレンドと逆行しているとき(=戻り売り/戻り買いのダマシが多い局面)の
  エントリーを構造的に排除するのが目的。
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
        trend_ema: int | None = None,
    ):
        if fast_ema >= slow_ema:
            raise ValueError("fast_ema は slow_ema より小さくすること")
        if trend_ema is not None and trend_ema <= slow_ema:
            raise ValueError("trend_ema は slow_ema より大きくすること(未使用なら null)")
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.rsi_period = rsi_period
        self.rsi_long_max = rsi_long_max
        self.rsi_short_min = rsi_short_min
        self.trend_ema = trend_ema

    def params(self) -> dict:
        return {
            "fast_ema": self.fast_ema,
            "slow_ema": self.slow_ema,
            "rsi_period": self.rsi_period,
            "rsi_long_max": self.rsi_long_max,
            "rsi_short_min": self.rsi_short_min,
            "trend_ema": self.trend_ema,
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

        if self.trend_ema is not None:
            out["ema_trend"] = ema(out["close"], self.trend_ema)
            # ema_trendがNaNの区間は比較がFalseになり自動的にシグナル停止となる
            valid_long = valid & (out["close"] > out["ema_trend"])
            valid_short = valid & (out["close"] < out["ema_trend"])
        else:
            valid_long = valid_short = valid

        out["signal"] = FLAT
        out.loc[valid_long & cross_up & (out["rsi"] < self.rsi_long_max), "signal"] = LONG
        out.loc[valid_short & cross_down & (out["rsi"] > self.rsi_short_min), "signal"] = SHORT
        return out
