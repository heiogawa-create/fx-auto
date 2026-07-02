import numpy as np
import pytest

from fxauto.strategy import create_strategy
from fxauto.strategy.base import LONG, SHORT
from fxauto.strategy.ema_rsi import EmaRsiStrategy
from tests.conftest import make_ohlcv


def test_invalid_params_rejected():
    with pytest.raises(ValueError):
        EmaRsiStrategy(fast_ema=50, slow_ema=20)


def test_factory():
    s = create_strategy("ema_rsi", {"fast_ema": 10, "slow_ema": 30})
    assert isinstance(s, EmaRsiStrategy)
    with pytest.raises(ValueError):
        create_strategy("unknown", {})


def test_signals_on_trend_reversal(trend_df):
    s = EmaRsiStrategy(fast_ema=10, slow_ema=30)
    out = s.generate_signals(trend_df)
    assert set(out["signal"].unique()) <= {-1, 0, 1}
    assert (out["signal"] == LONG).sum() >= 1
    assert (out["signal"] == SHORT).sum() >= 1


def test_no_signal_during_warmup(trend_df):
    s = EmaRsiStrategy(fast_ema=10, slow_ema=30)
    out = s.generate_signals(trend_df)
    assert (out["signal"].iloc[:30] == 0).all()


def test_rsi_filter_blocks_overheated_entries():
    # 一貫した急騰の後にクロスが起きるとRSIが高く、ロングが抑制される
    prices = np.concatenate([np.linspace(110, 100, 60), np.linspace(100, 130, 60)])
    df = make_ohlcv(prices)
    strict = EmaRsiStrategy(fast_ema=5, slow_ema=20, rsi_long_max=50.0)
    loose = EmaRsiStrategy(fast_ema=5, slow_ema=20, rsi_long_max=100.0)
    n_strict = (strict.generate_signals(df)["signal"] == LONG).sum()
    n_loose = (loose.generate_signals(df)["signal"] == LONG).sum()
    assert n_strict <= n_loose


def test_signals_do_not_mutate_input(trend_df):
    before = trend_df.copy()
    EmaRsiStrategy().generate_signals(trend_df)
    assert trend_df.equals(before)


def test_trend_ema_must_exceed_slow_ema():
    with pytest.raises(ValueError, match="trend_ema"):
        EmaRsiStrategy(fast_ema=10, slow_ema=30, trend_ema=30)


def test_trend_filter_blocks_counter_trend_entries():
    # 長い下落の後の小反発: フィルタなしならゴールデンクロスでロングするが、
    # 価格はトレンドEMAの下にあるため、フィルタありではロングしない
    prices = np.concatenate([np.linspace(150, 100, 250), np.linspace(100, 108, 50)])
    df = make_ohlcv(prices)
    no_filter = EmaRsiStrategy(fast_ema=5, slow_ema=20)
    with_filter = EmaRsiStrategy(fast_ema=5, slow_ema=20, trend_ema=200)
    longs_without = (no_filter.generate_signals(df)["signal"] == LONG).sum()
    longs_with = (with_filter.generate_signals(df)["signal"] == LONG).sum()
    assert longs_without >= 1
    assert longs_with == 0


def test_trend_filter_allows_with_trend_entries():
    # 押し目を作りながら上昇し続ける相場: 押し目後の再クロスは
    # トレンドEMAの上で起きるため、フィルタがあってもロングが出る
    n = 900
    base = np.linspace(100, 160, n)
    pullbacks = -3 * (np.arange(n) % 100 < 20)  # 100本ごとに20本の押し目
    df = make_ohlcv(base + pullbacks)
    # RSI条件は無効化(rsi_long_max=100)してトレンドフィルタの挙動だけを見る
    s = EmaRsiStrategy(fast_ema=10, slow_ema=30, trend_ema=100, rsi_long_max=100.0)
    out = s.generate_signals(df)
    assert (out["signal"] == LONG).sum() >= 1
