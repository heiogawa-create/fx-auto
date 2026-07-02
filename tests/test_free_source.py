import pandas as pd

from fxauto.data.free_source import resample_ohlcv, to_yahoo_symbol


def test_usd_jpy_maps_to_jpy_x():
    assert to_yahoo_symbol("USD_JPY") == "JPY=X"


def test_eur_usd_maps_to_eurusd_x():
    assert to_yahoo_symbol("EUR_USD") == "EURUSD=X"


def test_gbp_usd_maps_to_gbpusd_x():
    assert to_yahoo_symbol("GBP_USD") == "GBPUSD=X"


def test_usd_chf_uses_override():
    assert to_yahoo_symbol("USD_CHF") == "CHF=X"


def test_resample_ohlcv_h1_to_h4():
    idx = pd.date_range("2024-01-01 00:00", periods=8, freq="1h", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [1, 2, 3, 4, 5, 6, 7, 8],
            "high": [11, 12, 13, 14, 15, 16, 17, 18],
            "low": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
            "close": [1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5],
            "volume": [10] * 8,
        },
        index=idx,
    )
    out = resample_ohlcv(df, "4h")
    assert len(out) == 2
    # 最初の4時間: open=先頭, high=最大, low=最小, close=末尾, volume=合計
    assert out["open"].iloc[0] == 1
    assert out["high"].iloc[0] == 14
    assert out["low"].iloc[0] == 0.1
    assert out["close"].iloc[0] == 4.5
    assert out["volume"].iloc[0] == 40
