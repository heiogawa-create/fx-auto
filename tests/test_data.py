import pandas as pd
import pytest

from fxauto.data.oanda_client import OandaClient
from fxauto.data.store import CandleStore, candles_to_df


def _candle(time: str, o: float, complete: bool = True) -> dict:
    return {
        "time": time,
        "complete": complete,
        "volume": 10,
        "mid": {"o": str(o), "h": str(o + 0.1), "l": str(o - 0.1), "c": str(o + 0.05)},
    }


def test_candles_to_df_excludes_incomplete():
    candles = [
        _candle("2024-01-01T00:00:00.000000000Z", 150.0),
        _candle("2024-01-01T01:00:00.000000000Z", 150.1),
        _candle("2024-01-01T02:00:00.000000000Z", 150.2, complete=False),
    ]
    df = candles_to_df(candles)
    assert len(df) == 2
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df["open"].iloc[0] == 150.0


def test_candles_to_df_empty():
    df = candles_to_df([])
    assert df.empty


def test_cache_roundtrip(tmp_path):
    store = CandleStore(client=None, cache_dir=tmp_path)
    df = candles_to_df([_candle("2024-01-01T00:00:00.000000000Z", 150.0)])
    store.save_cache(df, "USD_JPY", "H1")
    loaded = store.load_cache("USD_JPY", "H1")
    pd.testing.assert_frame_equal(df, loaded)


def test_fetch_without_client_or_cache_raises(tmp_path):
    store = CandleStore(client=None, cache_dir=tmp_path)
    with pytest.raises(RuntimeError):
        store.fetch("USD_JPY", "H1", start=pd.Timestamp("2024-01-01", tz="UTC"))


def test_order_without_sl_rejected_at_client_level():
    client = OandaClient("dummy-token", "dummy-account")
    with pytest.raises(ValueError, match="SL"):
        client.create_market_order("USD_JPY", 1000, stop_loss_price=0)


def test_practice_url_only():
    from fxauto.data import oanda_client
    assert "fxpractice" in oanda_client.PRACTICE_API_URL
    assert "fxtrade" not in oanda_client.PRACTICE_API_URL
