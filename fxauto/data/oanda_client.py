"""OANDA v20 REST APIクライアント(デモ口座 fxpractice 専用)。

安全方針:
- 接続先は api-fxpractice.oanda.com に固定。本番(fxtrade)のURLは存在しない。
- ネットワーク/5xxエラーは指数バックオフでリトライし、プロセスを落とさない。
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

# デモ口座のみ。本番URLをここに書かないこと。
PRACTICE_API_URL = "https://api-fxpractice.oanda.com"

MAX_CANDLES_PER_REQUEST = 5000


class OandaError(Exception):
    """リトライしても回復しなかったAPIエラー。"""


class OandaClient:
    def __init__(
        self,
        token: str,
        account_id: str,
        max_retries: int = 4,
        backoff_base_sec: float = 2.0,
        timeout_sec: float = 30.0,
    ):
        self.account_id = account_id
        self.max_retries = max_retries
        self.backoff_base_sec = backoff_base_sec
        self.timeout_sec = timeout_sec
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        )

    # ------------------------------------------------------------------
    # 低レベルHTTP(リトライ付き)
    # ------------------------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = PRACTICE_API_URL + path
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._session.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    timeout=self.timeout_sec,
                )
                # 4xx はリトライしても無駄なので即エラー(429を除く)
                if 400 <= resp.status_code < 500 and resp.status_code != 429:
                    raise OandaError(
                        f"{method} {path} -> {resp.status_code}: {resp.text[:500]}"
                    )
                if resp.status_code >= 500 or resp.status_code == 429:
                    raise requests.HTTPError(f"status={resp.status_code}", response=resp)
                return resp.json()
            except OandaError:
                raise
            except (requests.RequestException, ValueError) as e:
                last_error = e
                if attempt < self.max_retries:
                    wait = self.backoff_base_sec * (2**attempt)
                    logger.warning(
                        "OANDA API失敗 (%s %s, %d回目): %s -> %.1f秒後にリトライ",
                        method, path, attempt + 1, e, wait,
                    )
                    time.sleep(wait)
        raise OandaError(f"{method} {path} がリトライ上限に達しました: {last_error}")

    # ------------------------------------------------------------------
    # ローソク足
    # ------------------------------------------------------------------
    def get_candles(
        self,
        instrument: str,
        granularity: str,
        from_time: str | None = None,
        to_time: str | None = None,
        count: int | None = None,
        price: str = "M",
    ) -> list[dict[str, Any]]:
        """ローソク足を取得する(1リクエスト最大5000本)。

        price="M" でmid、"BA"でbid/ask。時刻はRFC3339文字列。
        """
        params: dict[str, Any] = {"granularity": granularity, "price": price}
        if from_time:
            params["from"] = from_time
        if to_time:
            params["to"] = to_time
        if count:
            params["count"] = min(count, MAX_CANDLES_PER_REQUEST)
        data = self._request("GET", f"/v3/instruments/{instrument}/candles", params=params)
        return data.get("candles", [])

    # ------------------------------------------------------------------
    # 口座・注文(フォワードテスト用)
    # ------------------------------------------------------------------
    def get_account_summary(self) -> dict[str, Any]:
        data = self._request("GET", f"/v3/accounts/{self.account_id}/summary")
        return data["account"]

    def get_open_trades(self) -> list[dict[str, Any]]:
        data = self._request("GET", f"/v3/accounts/{self.account_id}/openTrades")
        return data.get("trades", [])

    def create_market_order(
        self,
        instrument: str,
        units: int,
        stop_loss_price: float,
        take_profit_price: float | None = None,
    ) -> dict[str, Any]:
        """逆指値(SL)必須の成行注文。SLなしの発注はこの層で拒否する。"""
        if stop_loss_price is None or stop_loss_price <= 0:
            raise ValueError("SL(stop_loss_price)なしの発注は許可されていません")
        order: dict[str, Any] = {
            "type": "MARKET",
            "instrument": instrument,
            "units": str(units),
            "timeInForce": "FOK",
            "positionFill": "DEFAULT",
            "stopLossOnFill": {"price": f"{stop_loss_price:.3f}"},
        }
        if take_profit_price:
            order["takeProfitOnFill"] = {"price": f"{take_profit_price:.3f}"}
        return self._request(
            "POST", f"/v3/accounts/{self.account_id}/orders", json_body={"order": order}
        )

    def close_trade(self, trade_id: str) -> dict[str, Any]:
        return self._request(
            "PUT", f"/v3/accounts/{self.account_id}/trades/{trade_id}/close"
        )

    def get_pricing(self, instruments: list[str]) -> list[dict[str, Any]]:
        data = self._request(
            "GET",
            f"/v3/accounts/{self.account_id}/pricing",
            params={"instruments": ",".join(instruments)},
        )
        return data.get("prices", [])
