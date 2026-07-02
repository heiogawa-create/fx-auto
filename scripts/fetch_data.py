"""OANDAからローソク足を取得してparquetにキャッシュする。

使い方:
    python scripts/fetch_data.py --days 730
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
    args = parser.parse_args()

    cfg = load_config(args.config)
    token, account_id = get_oanda_credentials()
    client = OandaClient(token, account_id)
    store = CandleStore(client, cache_dir=cfg["data"]["cache_dir"])

    start = datetime.now(timezone.utc) - timedelta(days=args.days)
    df = store.fetch(cfg["instrument"], cfg["granularity"], start=start)
    print(f"{cfg['instrument']} {cfg['granularity']}: {len(df)}本 "
          f"({df.index.min()} 〜 {df.index.max()})")
    print(f"キャッシュ: {store._cache_path(cfg['instrument'], cfg['granularity'])}")


if __name__ == "__main__":
    main()
