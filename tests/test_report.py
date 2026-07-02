import pandas as pd

from fxauto.backtest.engine import BacktestResult, Trade
from fxauto.backtest.metrics import compute_metrics
from fxauto.backtest.report import generate_html_report, write_report


def _sample_result() -> BacktestResult:
    index = pd.date_range("2024-01-01", periods=5, freq="1D", tz="UTC")
    curve = pd.Series([1_000_000, 1_010_000, 1_005_000, 1_020_000, 1_015_000], index=index)
    trades = [
        Trade(entry_time=index[0], exit_time=index[1], direction=1, entry_price=150.0,
             exit_price=150.5, units=1000.0, sl_price=149.5, tp_price=151.0,
             pnl=500.0, exit_reason="take_profit"),
        Trade(entry_time=index[2], exit_time=index[3], direction=-1, entry_price=151.0,
             exit_price=151.3, units=800.0, sl_price=151.5, tp_price=150.0,
             pnl=-240.0, exit_reason="stop_loss"),
    ]
    return BacktestResult(trades=trades, equity_curve=curve, initial_balance=1_000_000,
                          final_balance=1_015_000)


def test_generate_html_report_contains_key_sections():
    result = _sample_result()
    metrics = compute_metrics(result)
    html = generate_html_report(result, metrics, "USD_JPY", "D", "EmaRsiStrategy")
    assert "<html" in html
    assert "USD_JPY" in html
    assert "取引履歴" in html
    assert "take_profit" in html
    assert "stop_loss" in html
    # スクリプトタグにデータが埋め込まれている(ダッシュボードとして機能する)
    assert "equity-chart" in html
    assert "<script>" in html


def test_generate_html_report_escapes_untrusted_strategy_name():
    result = _sample_result()
    metrics = compute_metrics(result)
    html = generate_html_report(result, metrics, "USD_JPY", "D", "<script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_write_report_creates_file(tmp_path):
    result = _sample_result()
    metrics = compute_metrics(result)
    out = tmp_path / "sub" / "report.html"
    path = write_report(result, metrics, "USD_JPY", "D", "EmaRsiStrategy", out)
    assert path.exists()
    assert path.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_empty_trades_report_does_not_crash():
    index = pd.date_range("2024-01-01", periods=2, freq="1D", tz="UTC")
    result = BacktestResult(trades=[], equity_curve=pd.Series([1_000_000, 1_000_000], index=index),
                            initial_balance=1_000_000, final_balance=1_000_000)
    metrics = compute_metrics(result)
    html = generate_html_report(result, metrics, "USD_JPY", "D", "EmaRsiStrategy")
    assert "取引はありませんでした" in html
