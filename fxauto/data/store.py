"""ローソク足の取得とparquetキャッシュ。

キャッシュは data/candles/{INSTRUMENT}_{GRANULARITY}.parquet に保存し、
再取得時は不足分だけAPIから取りに行く。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from fxauto.data.oanda_client import MAX_CANDLES_PER_REQUEST, OandaClient

logger = logging.getLogger(__name__)

COLUMNS = ["open", "high", "low", "close", "volume"]

_GRANULARITY_SECONDS = {
    "M1": 60, "M5": 300, "M15": 900, "M30": 1800,
    "H1": 3600, "H4": 14400, "D": 86400,
}


def candles_to_df(candles: list[dict]) -> pd.DataFrame:
    """OANDAのcandle JSONをOHLCVのDataFrameへ変換する(未確定足は除外)。"""
    rows = []
    for c in candles:
        if not c.get("complete", False):
            continue
        mid = c["mid"]
        rows.append(
            {
                "time": pd.Timestamp(c["time"]),
                "open": float(mid["o"]),
                "high": float(mid["h"]),
                "low": float(mid["l"]),
                "close": float(mid["c"]),
                "volume": int(c["volume"]),
            }
        )
    if not rows:
        return pd.DataFrame(columns=COLUMNS, index=pd.DatetimeIndex([], name="time", tz="UTC"))
    df = pd.DataFrame(rows).set_index("time").sort_index()
    return df[COLUMNS]


class CandleStore:
    def __init__(self, client: OandaClient | None, cache_dir: str | Path = "data/candles"):
        self.client = client
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, instrument: str, granularity: str, source: str = "oanda") -> Path:
        suffix = "" if source == "oanda" else f"_{source}"
        return self.cache_dir / f"{instrument}_{granularity}{suffix}.parquet"

    def load_cache(
        self, instrument: str, granularity: str, source: str = "oanda"
    ) -> pd.DataFrame | None:
        path = self._cache_path(instrument, granularity, source)
        if path.exists():
            return pd.read_parquet(path)
        return None

    def save_cache(
        self, df: pd.DataFrame, instrument: str, granularity: str, source: str = "oanda"
    ) -> Path:
        path = self._cache_path(instrument, granularity, source)
        df.to_parquet(path)
        return path

    def fetch(
        self,
        instrument: str,
        granularity: str,
        start: datetime,
        end: datetime | None = None,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """指定期間のローソク足を返す。キャッシュ済み分はAPIを呼ばない。"""
        end = end or datetime.now(timezone.utc)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        cached = self.load_cache(instrument, granularity) if use_cache else None
        fetch_from = start
        if cached is not None and not cached.empty:
            last_cached = cached.index.max()
            if last_cached >= pd.Timestamp(end):
                return cached.loc[pd.Timestamp(start): pd.Timestamp(end)]
            if last_cached >= pd.Timestamp(start):
                fetch_from = (last_cached + pd.Timedelta(seconds=1)).to_pydatetime()

        if self.client is None:
            if cached is not None:
                logger.warning("APIクライアント未設定のためキャッシュのみ返します")
                return cached.loc[pd.Timestamp(start): pd.Timestamp(end)]
            raise RuntimeError("キャッシュがなく、APIクライアントも未設定です")

        fetched = self._fetch_range(instrument, granularity, fetch_from, end)
        if cached is not None and not cached.empty:
            df = pd.concat([cached, fetched])
            df = df[~df.index.duplicated(keep="last")].sort_index()
        else:
            df = fetched
        if not df.empty:
            self.save_cache(df, instrument, granularity)
        return df.loc[pd.Timestamp(start): pd.Timestamp(end)]

    def _fetch_range(
        self, instrument: str, granularity: str, start: datetime, end: datetime
    ) -> pd.DataFrame:
        """5000本制限に合わせて期間を分割しながら取得する。"""
        step_sec = _GRANULARITY_SECONDS.get(granularity, 3600)
        chunk = timedelta(seconds=step_sec * MAX_CANDLES_PER_REQUEST)
        frames: list[pd.DataFrame] = []
        cursor = start
        while cursor < end:
            chunk_end = min(cursor + chunk, end)
            candles = self.client.get_candles(
                instrument,
                granularity,
                from_time=cursor.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
                to_time=chunk_end.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
            )
            df = candles_to_df(candles)
            if not df.empty:
                frames.append(df)
            logger.info(
                "%s %s: %s〜%s %d本取得",
                instrument, granularity, cursor.date(), chunk_end.date(), len(df),
            )
            cursor = chunk_end
        if not frames:
            return pd.DataFrame(
                columns=COLUMNS, index=pd.DatetimeIndex([], name="time", tz="UTC")
            )
        out = pd.concat(frames)
        return out[~out.index.duplicated(keep="last")].sort_index()

    def fetch_free(
        self,
        instrument: str,
        granularity: str,
        start: datetime,
        end: datetime | None = None,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """OANDA APIを使わず、Yahoo Financeの無料データでローソク足を取得する。

        口座開設・入金なしでバックテストを試したい場合に使う代替経路。
        OANDA由来のキャッシュ("_oanda"扱い)とはファイルを分けて保存する。
        """
        from fxauto.data.free_source import fetch_free_candles  # 遅延import(yfinance依存を分離)

        end = end or datetime.now(timezone.utc)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        cached = self.load_cache(instrument, granularity, source="yf") if use_cache else None
        if cached is not None and not cached.empty and cached.index.max() >= pd.Timestamp(end):
            return cached.loc[pd.Timestamp(start): pd.Timestamp(end)]

        fetched = fetch_free_candles(instrument, granularity, start, end)
        if cached is not None and not cached.empty:
            df = pd.concat([cached, fetched])
            df = df[~df.index.duplicated(keep="last")].sort_index()
        else:
            df = fetched
        if not df.empty:
            self.save_cache(df, instrument, granularity, source="yf")
        return df.loc[pd.Timestamp(start): pd.Timestamp(end)]
