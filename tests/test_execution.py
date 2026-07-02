"""ForwardTestEngine をフェイクOANDAクライアントで検証する。"""

import pandas as pd

from fxauto.execution.engine import ForwardTestEngine
from fxauto.execution.trade_log import TradeLogger
from fxauto.notify.notifier import Notifier
from fxauto.risk.manager import RiskManager
from fxauto.strategy.base import FLAT, LONG, Strategy


def _fake_candles(n=100, base=150.0):
    candles = []
    t = pd.Timestamp("2026-07-01", tz="UTC")
    for i in range(n):
        o = base + i * 0.01
        candles.append({
            "time": (t + pd.Timedelta(hours=i)).isoformat(),
            "complete": True,
            "volume": 10,
            "mid": {"o": str(o), "h": str(o + 0.1), "l": str(o - 0.1), "c": str(o + 0.05)},
        })
    return candles


class FakeClient:
    def __init__(self, balance=1_000_000.0):
        self.balance = balance
        self.orders = []
        self.open_trades_response = []
        self.candles = _fake_candles()

    def get_account_summary(self):
        return {"balance": str(self.balance)}

    def get_open_trades(self):
        return self.open_trades_response

    def get_candles(self, instrument, granularity, count=None, **kwargs):
        return self.candles

    def create_market_order(self, instrument, units, stop_loss_price, take_profit_price=None):
        assert stop_loss_price > 0, "SLなしの注文が発行された"
        self.orders.append({"instrument": instrument, "units": units,
                            "sl": stop_loss_price, "tp": take_profit_price})
        return {"orderFillTransaction": {"id": str(len(self.orders))}}


class AlwaysLongStrategy(Strategy):
    def generate_signals(self, df):
        out = df.copy()
        out["signal"] = FLAT
        out.iloc[-1, out.columns.get_loc("signal")] = LONG
        return out


class NeverStrategy(Strategy):
    def generate_signals(self, df):
        out = df.copy()
        out["signal"] = FLAT
        return out


def make_engine(client, strategy, tmp_path, **risk_kwargs):
    defaults = dict(risk_per_trade=0.01, max_daily_loss=0.03, max_positions=1)
    defaults.update(risk_kwargs)
    return ForwardTestEngine(
        client=client,
        strategy=strategy,
        risk_manager=RiskManager(**defaults),
        trade_logger=TradeLogger(tmp_path),
        notifier=Notifier(channel="none"),
        instrument="USD_JPY",
        granularity="H1",
    )


def test_entry_order_placed_with_sl(tmp_path):
    client = FakeClient()
    engine = make_engine(client, AlwaysLongStrategy(), tmp_path)
    engine.step()
    assert len(client.orders) == 1
    order = client.orders[0]
    assert order["units"] > 0
    assert 0 < order["sl"] < 152  # ロングのSLはエントリー付近より下
    assert order["tp"] > order["sl"]


def test_same_bar_not_traded_twice(tmp_path):
    client = FakeClient()
    engine = make_engine(client, AlwaysLongStrategy(), tmp_path)
    engine.step()
    engine.step()  # 新しいバーが来ていないので発注しないはず
    assert len(client.orders) == 1


def test_no_signal_no_order(tmp_path):
    client = FakeClient()
    engine = make_engine(client, NeverStrategy(), tmp_path)
    engine.step()
    assert client.orders == []


def test_max_positions_blocks_entry(tmp_path):
    client = FakeClient()
    client.open_trades_response = [{"id": "1"}]
    engine = make_engine(client, AlwaysLongStrategy(), tmp_path, max_positions=1)
    engine.step()
    assert client.orders == []


def test_closed_trade_updates_daily_pnl_and_can_stop_day(tmp_path):
    client = FakeClient(balance=1_000_000)
    engine = make_engine(client, NeverStrategy(), tmp_path)
    client.open_trades_response = [{"id": "1"}]
    engine.step()  # トレード1を認識

    # トレードが消え、残高が4%減 → 日次損失上限(3%)超え
    client.open_trades_response = []
    client.balance = 960_000
    engine.step()
    assert engine.risk.daily_loss_reached()

    # 以降はシグナルが出ても発注されない
    engine.strategy = AlwaysLongStrategy()
    engine._last_signal_bar = None
    engine.step()
    assert client.orders == []
