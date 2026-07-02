"""通知層(Discord webhook / LINE Notify)。

通知の失敗で取引ループを止めないこと。エラーはログに残して握りつぶす。
"""

from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

LINE_NOTIFY_URL = "https://notify-api.line.me/api/notify"


class Notifier:
    """channel: "discord" | "line" | "none"。トークン未設定なら自動的に無効化。"""

    def __init__(self, channel: str = "discord", enabled: bool = True, timeout_sec: float = 10.0):
        self.channel = channel
        self.timeout_sec = timeout_sec
        self.discord_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
        self.line_token = os.environ.get("LINE_NOTIFY_TOKEN", "")
        self.enabled = enabled and channel != "none"
        if self.enabled and channel == "discord" and not self.discord_url:
            logger.warning("DISCORD_WEBHOOK_URL未設定のため通知を無効化します")
            self.enabled = False
        if self.enabled and channel == "line" and not self.line_token:
            logger.warning("LINE_NOTIFY_TOKEN未設定のため通知を無効化します")
            self.enabled = False

    def send(self, message: str) -> bool:
        if not self.enabled:
            return False
        try:
            if self.channel == "discord":
                resp = requests.post(
                    self.discord_url, json={"content": message}, timeout=self.timeout_sec
                )
            else:
                resp = requests.post(
                    LINE_NOTIFY_URL,
                    headers={"Authorization": f"Bearer {self.line_token}"},
                    data={"message": message},
                    timeout=self.timeout_sec,
                )
            ok = resp.status_code < 300
            if not ok:
                logger.error("通知失敗: %d %s", resp.status_code, resp.text[:200])
            return ok
        except requests.RequestException as e:
            # 通知失敗で取引を止めない
            logger.error("通知の送信に失敗: %s", e)
            return False

    # 用途別ヘルパー
    def notify_entry(self, instrument: str, direction: int, units: int, price: float, sl: float) -> None:
        side = "ロング" if direction > 0 else "ショート"
        self.send(f"📈 エントリー: {instrument} {side} {abs(units)}units @ {price} (SL: {sl})")

    def notify_exit(self, instrument: str, pnl: float, reason: str) -> None:
        emoji = "✅" if pnl >= 0 else "❌"
        self.send(f"{emoji} 決済: {instrument} 損益 {pnl:+.0f} ({reason})")

    def notify_error(self, message: str) -> None:
        self.send(f"🚨 エラー: {message}")
