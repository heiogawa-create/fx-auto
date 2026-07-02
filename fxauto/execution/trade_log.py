"""取引ログ(CSV + JSON Lines)。全取引イベントを両形式で記録する。"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CSV_FIELDS = [
    "timestamp", "event", "instrument", "direction", "units",
    "price", "sl_price", "tp_price", "pnl", "reason", "detail",
]


class TradeLogger:
    def __init__(self, log_dir: str | Path = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        self.csv_path = self.log_dir / f"trades_{day}.csv"
        self.json_path = self.log_dir / f"trades_{day}.jsonl"

    def log(self, event: str, **fields: Any) -> dict[str, Any]:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **fields,
        }
        self._write_json(record)
        self._write_csv(record)
        return record

    def _write_json(self, record: dict[str, Any]) -> None:
        with open(self.json_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def _write_csv(self, record: dict[str, Any]) -> None:
        row = {k: record.get(k, "") for k in CSV_FIELDS}
        extras = {k: v for k, v in record.items() if k not in CSV_FIELDS}
        if extras:
            row["detail"] = json.dumps(extras, ensure_ascii=False, default=str)
        new_file = not self.csv_path.exists()
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow(row)

    # 用途別ヘルパー
    def log_entry(self, instrument: str, direction: int, units: int, price: float,
                  sl_price: float, tp_price: float | None) -> None:
        self.log("entry", instrument=instrument, direction=direction, units=units,
                 price=price, sl_price=sl_price, tp_price=tp_price or "")

    def log_exit(self, instrument: str, pnl: float, reason: str) -> None:
        self.log("exit", instrument=instrument, pnl=pnl, reason=reason)

    def log_error(self, message: str) -> None:
        self.log("error", reason=message)
