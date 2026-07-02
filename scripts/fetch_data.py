"""ローソク足を取得してparquetにキャッシュする。

config.yaml の data.source で取得元を切り替える:
  - yfinance: Yahoo Financeの無料データ(口座開設・入金不要。既定値)
  - oanda   : OANDA証券API(要:本番口座 + 25万円入金でAPI解禁)

使い方:
    python scripts/fetch_data.py --days 730
    python scripts/fetch_data.py --source oanda --days 730   # OANDA APIを使う場合
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fxauto.config import get_oanda_credentials, load_config
from fxauto.data.oanda_client import OandaClient
from fxauto.data.store import CandleStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="ローソク足の取得とキャッシュ")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--days", type=int, default=730, help="何日分さかのぼって取得するか")
    parser.add_argument("--source", choices=["yfinance", "oanda"], default=None,
                        help="取得元を上書きする(未指定ならconfig.yamlのdata.sourceに従う)")
    args = parser.parse_args()

    cfg = load_config(args.config)
    source = args.source or cfg["data"].get("source", "yfinance")
    store = CandleStore(client=None, cache_dir=cfg["data"]["cache_dir"])
    start = datetime.now(timezone.utc) - timedelta(days=args.days)

    if source == "oanda":
        token, account_id = get_oanda_credentials()
        store.client = OandaClient(token, account_id)
        df = store.fetch(cfg["instrument"], cfg["granularity"], start=start)
        cache_source = "oanda"
    else:
        df = store.fetch_free(cfg["instrument"], cfg["granularity"], start=start)
        cache_source = "yf"

    if df.empty:
        raise SystemExit(
            "データを取得できませんでした。通貨ペア・時間足・ネットワーク接続を確認してください"
        )
    print(f"[{source}] {cfg['instrument']} {cfg['granularity']}: {len(df)}本 "
          f"({df.index.min()} 〜 {df.index.max()})")
    print(f"キャッシュ: {store._cache_path(cfg['instrument'], cfg['granularity'], source=cache_source)}")


if __name__ == "__main__":
    main()
