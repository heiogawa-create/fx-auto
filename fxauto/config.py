"""config.yaml と .env の読み込み。

秘密情報(APIトークン等)は環境変数/.env のみから読む。
config.yaml には戦略パラメータや通貨ペアなどの非秘密設定を置く。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path("config.yaml")


def load_dotenv(path: str | Path = ".env") -> None:
    """シンプルな .env ローダー(依存を増やさないため自前実装)。

    既に設定済みの環境変数は上書きしない。
    """
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


class Config:
    """dict をドット参照っぽく扱う薄いラッパー。"""

    def __init__(self, data: dict[str, Any]):
        self._data = data

    def __getitem__(self, key: str) -> Any:
        value = self._data[key]
        return Config(value) if isinstance(value, dict) else value

    def get(self, key: str, default: Any = None) -> Any:
        value = self._data.get(key, default)
        return Config(value) if isinstance(value, dict) else value

    def to_dict(self) -> dict[str, Any]:
        return self._data

    def __contains__(self, key: str) -> bool:
        return key in self._data


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> Config:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"設定ファイルが不正です: {path}")
    return Config(data)


def get_oanda_credentials() -> tuple[str, str]:
    """OANDAデモ口座の認証情報を環境変数から取得する。"""
    load_dotenv()
    token = os.environ.get("OANDA_API_TOKEN", "")
    account_id = os.environ.get("OANDA_ACCOUNT_ID", "")
    if not token or not account_id:
        raise RuntimeError(
            "OANDA_API_TOKEN / OANDA_ACCOUNT_ID が未設定です。"
            " .env.example を参考に .env を作成してください(デモ口座のみ)。"
        )
    return token, account_id
