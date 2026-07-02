"""無料の外部データソース(Yahoo Finance)からFXデータを取得する。

OANDA証券のAPIはデモ口座でも本番口座への入金(25万円)が条件になっているため、
口座開設・入金なしでバックテストを試せるよう、無料で使えるYahoo Financeの
データを代替ソースとして用意する。

注意:
- Yahoo Financeのレートは終値ベースの参考値であり、OANDAのbid/ask中値と
  厳密には一致しない(スプレッドの実態も反映していない)。
  あくまで「戦略のロジックを試す」ためのバックテスト用データと割り切ること。
- 分足データはYahoo側の制限で取得できる期間が短い(概ね数十日〜2年)。
  長期間の検証をしたい場合は granularity を D(日足) にするのが無難。
"""

from __future__ import annotations

import logging

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# OANDA形式(USD_JPY)からYahoo Finance形式への変換の特例
# Yahooは「USD/XXX」を "XXX=X" と表記する(USDが分母側に来る通貨に限る)
_OVERRIDES = {
    "USD_JPY": "JPY=X",
    "USD_CHF": "CHF=X",
    "USD_CAD": "CAD=X",
    "USD_SEK": "SEK=X",
    "USD_NOK": "NOK=X",
    "USD_MXN": "MXN=X",
    "USD_ZAR": "ZAR=X",
}

_GRANULARITY_TO_INTERVAL = {
    "M5": "5m", "M15": "15m", "M30": "30m", "H1": "60m", "H4": "60m", "D": "1d",
}

COLUMNS = ["open", "high", "low", "close", "volume"]


def to_yahoo_symbol(instrument: str) -> str:
    """OANDA形式の通貨ペア表記(USD_JPY)をYahoo Finance形式(JPY=X)に変換する。"""
    if instrument in _OVERRIDES:
        return _OVERRIDES[instrument]
    base, _, quote = instrument.partition("_")
    if not quote:
        raise ValueError(f"不正な通貨ペア表記です: {instrument}")
    return f"{base}{quote}=X"


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """OHLCVをより大きな時間足に集約する(例: 1時間足 → 4時間足)。"""
    out = df.resample(rule).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    return out.dropna(subset=["open", "high", "low", "close"])


def fetch_free_candles(
    instrument: str,
    granularity: str,
    start,
    end=None,
) -> pd.DataFrame:
    """Yahoo FinanceからOHLCVを取得し、既存のcandle DataFrame形式に揃えて返す。

    H4はYahoo側に存在しないため、1時間足を取得して4時間足に集約する。
    """
    symbol = to_yahoo_symbol(instrument)
    interval = _GRANULARITY_TO_INTERVAL.get(granularity)
    if interval is None:
        raise ValueError(f"未対応の時間足です: {granularity}")

    df = yf.download(
        symbol, start=start, end=end, interval=interval,
        progress=False, auto_adjust=False,
    )
    if df is None or df.empty:
        logger.warning("Yahoo Financeからデータを取得できませんでした: %s %s", symbol, interval)
        return pd.DataFrame(columns=COLUMNS, index=pd.DatetimeIndex([], name="time", tz="UTC"))

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)
    df.index = pd.to_datetime(df.index, utc=True)
    df.index.name = "time"

    out = df[["open", "high", "low", "close"]].copy()
    out["volume"] = df["volume"].fillna(0).astype(int) if "volume" in df else 0
    out = out.dropna(subset=["open", "high", "low", "close"]).sort_index()
    if granularity == "H4":
        out = resample_ohlcv(out, "4h")
    return out
