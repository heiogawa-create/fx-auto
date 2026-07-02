import numpy as np
import pytest

from fxauto.backtest.walkforward import walk_forward
from fxauto.strategy.ema_rsi import EmaRsiStrategy
from tests.conftest import make_ohlcv

BT_KWARGS = dict(instrument="USD_JPY", initial_balance=1_000_000,
                 spread_pips=1.0, slippage_pips=0.2)

GRID = {"fast_ema": [5, 10], "slow_ema": [20], "rsi_period": [14],
        "rsi_long_max": [70.0], "rsi_short_min": [30.0]}


def _long_df(n=2000, n_segments=40):
    rng = np.random.default_rng(7)
    # トレンドの向きが頻繁に変わるデータ(各foldのIS期間内で十分な取引が出るように)
    segments = []
    level = 100.0
    for k in range(n_segments):
        target = level + (3 if k % 2 == 0 else -2.5)
        segments.append(np.linspace(level, target, n // n_segments))
        level = target
    prices = np.concatenate(segments) + rng.normal(0, 0.05, len(np.concatenate(segments)))
    return make_ohlcv(prices)


def test_walk_forward_runs_and_splits():
    df = _long_df()
    result = walk_forward(df, EmaRsiStrategy, GRID, BT_KWARGS,
                          n_splits=3, train_ratio=0.7)
    assert len(result.windows) == 3
    for w in result.windows:
        assert w.best_params in [
            {"fast_ema": f, "slow_ema": 20, "rsi_period": 14,
             "rsi_long_max": 70.0, "rsi_short_min": 30.0}
            for f in (5, 10)
        ]


def test_invalid_param_combos_skipped():
    df = _long_df()
    grid = {"fast_ema": [30], "slow_ema": [20, 60], "rsi_period": [14],
            "rsi_long_max": [70.0], "rsi_short_min": [30.0]}
    # fast=30/slow=20 は不正なのでスキップされ、fast=30/slow=60だけが使われる
    result = walk_forward(df, EmaRsiStrategy, grid, BT_KWARGS, n_splits=2)
    for w in result.windows:
        assert w.best_params["slow_ema"] == 60


def test_insufficient_data_raises():
    df = _long_df(300)
    with pytest.raises(ValueError, match="不足"):
        walk_forward(df, EmaRsiStrategy, GRID, BT_KWARGS, n_splits=4)


def test_bad_train_ratio_raises():
    with pytest.raises(ValueError):
        walk_forward(_long_df(), EmaRsiStrategy, GRID, BT_KWARGS, train_ratio=1.5)
