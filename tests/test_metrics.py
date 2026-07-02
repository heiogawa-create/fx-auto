import pandas as pd

from fxauto.backtest.engine import BacktestResult, Trade
from fxauto.backtest.metrics import combine_trade_stats, compute_metrics


def _trade(pnl: float) -> Trade:
    t = pd.Timestamp("2024-01-01", tz="UTC")
    return Trade(entry_time=t, exit_time=t, direction=1, entry_price=100.0,
                 exit_price=100.0, units=1.0, sl_price=99.0, tp_price=102.0, pnl=pnl)


def _result(pnls: list[float], initial: float = 1000.0) -> BacktestResult:
    curve_values = [initial]
    for p in pnls:
        curve_values.append(curve_values[-1] + p)
    index = pd.date_range("2024-01-01", periods=len(curve_values), freq="1h", tz="UTC")
    return BacktestResult(
        trades=[_trade(p) for p in pnls],
        equity_curve=pd.Series(curve_values, index=index),
        initial_balance=initial,
        final_balance=initial + sum(pnls),
    )


def test_profit_factor_and_win_rate():
    m = compute_metrics(_result([10, -5, 20, -5]))
    assert abs(m.profit_factor - 3.0) < 1e-9
    assert m.win_rate == 0.5
    assert m.num_trades == 4


def test_max_drawdown():
    m = compute_metrics(_result([100, -200, 50]))
    # ピーク1100から900へ: DD = 200/1100
    assert abs(m.max_drawdown - 200 / 1100) < 1e-9


def test_suspiciously_good_pf_warns():
    m = compute_metrics(_result([10] * 40 + [-1]))
    assert any("PF" in w and "良すぎ" in w for w in m.warnings)


def test_high_win_rate_warns():
    m = compute_metrics(_result([5] * 35 + [-5] * 2))
    assert any("勝率" in w for w in m.warnings)


def test_few_trades_warns():
    m = compute_metrics(_result([10, -5]))
    assert any("少なく" in w for w in m.warnings)


def test_normal_result_has_no_pf_warning():
    pnls = ([12, -10] * 25)  # PF=1.2, 勝率50%, 50取引
    m = compute_metrics(_result(pnls))
    assert not any("PF" in w for w in m.warnings)


def _trade_r(pnl: float, entry=100.0, sl=99.0, units=100.0, direction=1) -> Trade:
    # リスク = (entry - sl) * direction * units = 100 → pnl 100 で 1R
    t = pd.Timestamp("2024-01-01", tz="UTC")
    return Trade(entry_time=t, exit_time=t, direction=direction, entry_price=entry,
                 exit_price=entry, units=units, sl_price=sl, tp_price=102.0, pnl=pnl)


def test_combine_trade_stats_r_multiples():
    r1 = BacktestResult(trades=[_trade_r(200.0), _trade_r(-100.0)],
                        equity_curve=pd.Series([1.0]), initial_balance=1, final_balance=1)
    r2 = BacktestResult(trades=[_trade_r(-100.0), _trade_r(200.0)],
                        equity_curve=pd.Series([1.0]), initial_balance=1, final_balance=1)
    combined = combine_trade_stats([r1, r2])
    assert combined.num_trades == 4
    assert abs(combined.profit_factor - 2.0) < 1e-9  # +2R+2R vs -1R-1R
    assert combined.win_rate == 0.5
    assert abs(combined.total_r - 2.0) < 1e-9
    assert abs(combined.avg_r - 0.5) < 1e-9


def test_combine_trade_stats_empty():
    combined = combine_trade_stats([])
    assert combined.num_trades == 0
    assert combined.total_r == 0.0
