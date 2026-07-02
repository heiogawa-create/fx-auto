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


def test_oanda_and_free_caches_are_separate_files(tmp_path):
    store = CandleStore(client=None, cache_dir=tmp_path)
    oanda_df = candles_to_df([_candle("2024-01-01T00:00:00.000000000Z", 150.0)])
    free_df = candles_to_df([_candle("2024-01-01T00:00:00.000000000Z", 999.0)])
    store.save_cache(oanda_df, "USD_JPY", "D", source="oanda")
    store.save_cache(free_df, "USD_JPY", "D", source="yf")

    assert store._cache_path("USD_JPY", "D", source="oanda") != store._cache_path(
        "USD_JPY", "D", source="yf"
    )
    assert store.load_cache("USD_JPY", "D", source="oanda")["open"].iloc[0] == 150.0
    assert store.load_cache("USD_JPY", "D", source="yf")["open"].iloc[0] == 999.0


def test_fetch_free_uses_free_source_and_caches(tmp_path, monkeypatch):
    import fxauto.data.free_source as free_source

    calls = []

    def fake_fetch(instrument, granularity, start, end):
        calls.append((instrument, granularity))
        idx = pd.date_range(start, periods=3, freq="1D", tz="UTC")
        return pd.DataFrame(
            {"open": [1.0, 2.0, 3.0], "high": [1.1, 2.1, 3.1], "low": [0.9, 1.9, 2.9],
             "close": [1.05, 2.05, 3.05], "volume": [0, 0, 0]},
            index=idx,
        )

    monkeypatch.setattr(free_source, "fetch_free_candles", fake_fetch)
    store = CandleStore(client=None, cache_dir=tmp_path)
    df = store.fetch_free("USD_JPY", "D", start=pd.Timestamp("2024-01-01", tz="UTC"))

    assert len(calls) == 1
    assert len(df) == 3
    cached = store.load_cache("USD_JPY", "D", source="yf")
    assert len(cached) == 3
