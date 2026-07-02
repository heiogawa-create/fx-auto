import numpy as np
import pandas as pd

from fxauto.backtest.engine import Backtester, pip_size
from fxauto.backtest.metrics import compute_metrics
from fxauto.strategy.base import FLAT, LONG, Strategy
from fxauto.strategy.ema_rsi import EmaRsiStrategy
from tests.conftest import make_ohlcv


class OneLongStrategy(Strategy):
    """指定バーで1回だけロングする検証用戦略。"""

    def __init__(self, entry_bar: int = 50):
        self.entry_bar = entry_bar

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["signal"] = FLAT
        out.iloc[self.entry_bar, out.columns.get_loc("signal")] = LONG
        return out


def test_pip_size():
    assert pip_size("USD_JPY") == 0.01
    assert pip_size("EUR_USD") == 0.0001


def test_entry_fills_next_bar_open_with_costs(trend_df):
    bt = Backtester(instrument="USD_JPY", spread_pips=1.0, slippage_pips=0.2)
    result = bt.run(trend_df, OneLongStrategy(entry_bar=50))
    assert len(result.trades) == 1
    trade = result.trades[0]
    raw_open = trend_df["open"].iloc[51]  # シグナルの次バー始値
    expected = raw_open + (1.0 * 0.01 / 2) + (0.2 * 0.01)
    assert abs(trade.entry_price - expected) < 1e-9
    assert trade.entry_time == trend_df.index[51]


def test_costs_reduce_pnl(trend_df):
    # SL/TPを遠くに置き、成行(期間終了)決済にすることで往復コストが損益に出る
    strategy = OneLongStrategy(entry_bar=50)
    kwargs = dict(sl_atr_mult=1000.0, tp_atr_mult=1000.0)
    free = Backtester(spread_pips=0.0, slippage_pips=0.0, **kwargs).run(trend_df, strategy)
    costly = Backtester(spread_pips=2.0, slippage_pips=1.0, **kwargs).run(trend_df, strategy)
    assert len(free.trades) == len(costly.trades) == 1
    assert free.trades[0].exit_reason == costly.trades[0].exit_reason == "end_of_data"
    assert costly.trades[0].entry_price > free.trades[0].entry_price
    assert costly.trades[0].exit_price < free.trades[0].exit_price


def test_stop_loss_always_set(trend_df):
    result = Backtester().run(trend_df, EmaRsiStrategy(fast_ema=10, slow_ema=30))
    for t in result.trades:
        assert t.sl_price > 0
        # SLはエントリーの不利側にある
        assert (t.entry_price - t.sl_price) * t.direction > 0


def test_risk_per_trade_bounds_loss():
    # 上昇後に急落するデータ: ロングエントリー直後にSLを踏む
    prices = np.concatenate([np.linspace(100, 105, 60), np.linspace(105, 95, 40)])
    df = make_ohlcv(prices)
    initial = 1_000_000
    bt = Backtester(initial_balance=initial, risk_per_trade=0.01,
                    slippage_pips=0.0, spread_pips=0.0)
    result = bt.run(df, OneLongStrategy(entry_bar=58))
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "stop_loss"
    # SL到達時の損失はリスク上限(残高の1%)と一致する(コスト0なら誤差なし)
    assert trade.pnl < 0
    assert abs(abs(trade.pnl) - initial * 0.01) < 1.0


def test_open_position_closed_at_end(trend_df):
    result = Backtester().run(trend_df, OneLongStrategy(entry_bar=len(trend_df) - 3))
    if result.trades:
        assert result.trades[-1].exit_time is not None


def test_no_lookahead_truncation(trend_df):
    """過去部分のトレードは、未来データを足しても変わらない(先読みなしの検証)。"""
    strategy = EmaRsiStrategy(fast_ema=10, slow_ema=30)
    full = Backtester().run(trend_df, strategy)
    cutoff = trend_df.index[600]
    partial = Backtester().run(trend_df.iloc[:600], strategy)
    full_past = [t for t in full.trades if t.exit_time is not None and t.exit_time < cutoff]
    partial_past = [t for t in partial.trades
                    if t.exit_time is not None and t.exit_time < cutoff
                    and t.exit_reason != "end_of_data"]
    for a, b in zip(full_past, partial_past):
        assert a.entry_time == b.entry_time
        assert abs(a.entry_price - b.entry_price) < 1e-9


def test_metrics_and_equity_curve(trend_df):
    result = Backtester().run(trend_df, EmaRsiStrategy(fast_ema=10, slow_ema=30))
    m = compute_metrics(result)
    assert m.num_trades == len(result.trades)
    assert 0.0 <= m.win_rate <= 1.0
    assert m.max_drawdown >= 0.0
    assert len(result.equity_curve) > 0


def test_no_trades_on_flat_market(flat_df):
    result = Backtester().run(flat_df, EmaRsiStrategy(fast_ema=10, slow_ema=30))
    m = compute_metrics(result)
    assert m.num_trades == 0
    # 取引が少なすぎる場合は「統計的に信頼できない」警告が出ること
    assert any("少なく" in w for w in m.warnings)
