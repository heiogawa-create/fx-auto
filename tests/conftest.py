import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def make_ohlcv(prices: np.ndarray, start: str = "2024-01-01", freq: str = "1h") -> pd.DataFrame:
    """終値列からそれらしいOHLCVを合成するテストヘルパー。"""
    index = pd.date_range(start, periods=len(prices), freq=freq, tz="UTC", name="time")
    close = pd.Series(prices, index=index)
    open_ = close.shift(1).fillna(close.iloc[0])
    high = pd.concat([open_, close], axis=1).max(axis=1) + 0.02
    low = pd.concat([open_, close], axis=1).min(axis=1) - 0.02
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": 100}
    )


@pytest.fixture
def trend_df() -> pd.DataFrame:
    """上昇→下降→上昇のトレンドを持つ合成データ(取引が発生する)。"""
    rng = np.random.default_rng(42)
    up1 = np.linspace(100, 110, 300)
    down = np.linspace(110, 98, 300)
    up2 = np.linspace(98, 112, 300)
    prices = np.concatenate([up1, down, up2]) + rng.normal(0, 0.05, 900)
    return make_ohlcv(prices)


@pytest.fixture
def flat_df() -> pd.DataFrame:
    """完全に横ばいの合成データ(EMAクロスが発生しない)。"""
    return make_ohlcv(np.full(300, 100.0))
