import numpy as np
import pandas as pd

from fxauto.strategy.indicators import atr, ema, rsi
from tests.conftest import make_ohlcv


def test_ema_converges_to_constant():
    s = pd.Series([100.0] * 50)
    result = ema(s, 10)
    assert abs(result.iloc[-1] - 100.0) < 1e-9


def test_ema_warmup_is_nan():
    s = pd.Series(np.arange(20, dtype=float))
    assert ema(s, 10).iloc[:9].isna().all()


def test_rsi_range_and_direction():
    up = pd.Series(np.linspace(100, 120, 50))
    down = pd.Series(np.linspace(120, 100, 50))
    rsi_up = rsi(up, 14).iloc[-1]
    rsi_down = rsi(down, 14).iloc[-1]
    assert 50 < rsi_up <= 100
    assert 0 <= rsi_down < 50


def test_rsi_all_gains_is_100():
    s = pd.Series(np.arange(1, 40, dtype=float))
    assert rsi(s, 14).iloc[-1] == 100.0


def test_atr_positive_and_scales_with_volatility():
    calm = make_ohlcv(100 + np.sin(np.arange(100)) * 0.1)
    wild = make_ohlcv(100 + np.sin(np.arange(100)) * 3.0)
    atr_calm = atr(calm, 14).iloc[-1]
    atr_wild = atr(wild, 14).iloc[-1]
    assert atr_calm > 0
    assert atr_wild > atr_calm
