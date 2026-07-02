import csv
import json

from fxauto.execution.trade_log import TradeLogger


def test_logs_written_as_csv_and_jsonl(tmp_path):
    tl = TradeLogger(tmp_path)
    tl.log_entry("USD_JPY", 1, 10000, 150.123, 149.5, 151.0)
    tl.log_exit("USD_JPY", -1234.5, "stop_loss")
    tl.log_error("connection lost")

    with open(tl.json_path, encoding="utf-8") as f:
        records = [json.loads(line) for line in f]
    assert len(records) == 3
    assert records[0]["event"] == "entry"
    assert records[0]["units"] == 10000
    assert records[1]["pnl"] == -1234.5
    assert records[2]["event"] == "error"

    with open(tl.csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3
    assert rows[0]["instrument"] == "USD_JPY"
    assert float(rows[1]["pnl"]) == -1234.5


def test_extra_fields_go_to_detail_column(tmp_path):
    tl = TradeLogger(tmp_path)
    tl.log("custom", instrument="EUR_USD", foo="bar")
    with open(tl.csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert "foo" in rows[0]["detail"]
