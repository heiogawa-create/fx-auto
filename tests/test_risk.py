from datetime import date

import pytest

from fxauto.risk.manager import RiskManager, RiskRejection

TODAY = date(2026, 7, 1)


def make_rm(**kwargs) -> RiskManager:
    defaults = dict(risk_per_trade=0.01, max_daily_loss=0.03, max_positions=1,
                    min_units=1, max_units=1_000_000)
    defaults.update(kwargs)
    return RiskManager(**defaults)


def test_position_size_is_one_percent_risk():
    rm = make_rm()
    plan = rm.build_order(
        instrument="USD_JPY", direction=1, balance=1_000_000,
        entry_price=150.0, sl_price=149.5, tp_price=151.0,
        open_positions=0, today=TODAY,
    )
    # リスク1% = 10,000円 / SL幅0.5円 → 20,000units
    assert plan.units == 20_000
    assert plan.risk_amount == 10_000


def test_short_units_are_negative():
    rm = make_rm()
    plan = rm.build_order(
        instrument="USD_JPY", direction=-1, balance=1_000_000,
        entry_price=150.0, sl_price=150.5, tp_price=149.0,
        open_positions=0, today=TODAY,
    )
    assert plan.units < 0


def test_missing_or_wrong_side_sl_rejected():
    rm = make_rm()
    with pytest.raises(RiskRejection, match="SL"):
        rm.build_order("USD_JPY", 1, 1_000_000, 150.0, sl_price=0.0,
                       tp_price=None, open_positions=0, today=TODAY)
    with pytest.raises(RiskRejection, match="SL"):
        # ロングなのにSLがエントリーより上
        rm.build_order("USD_JPY", 1, 1_000_000, 150.0, sl_price=151.0,
                       tp_price=None, open_positions=0, today=TODAY)


def test_max_positions_enforced():
    rm = make_rm(max_positions=1)
    with pytest.raises(RiskRejection, match="ポジション"):
        rm.build_order("USD_JPY", 1, 1_000_000, 150.0, sl_price=149.5,
                       tp_price=None, open_positions=1, today=TODAY)


def test_daily_loss_limit_stops_trading():
    rm = make_rm(max_daily_loss=0.03)
    rm.start_day_if_needed(TODAY, 1_000_000)
    rm.record_realized_pnl(-30_000)  # ちょうど3%
    assert rm.daily_loss_reached()
    with pytest.raises(RiskRejection, match="日次"):
        rm.build_order("USD_JPY", 1, 970_000, 150.0, sl_price=149.5,
                       tp_price=None, open_positions=0, today=TODAY)


def test_daily_loss_resets_next_day():
    rm = make_rm()
    rm.start_day_if_needed(TODAY, 1_000_000)
    rm.record_realized_pnl(-50_000)
    assert rm.daily_loss_reached()
    rm.start_day_if_needed(date(2026, 7, 2), 950_000)
    assert not rm.daily_loss_reached()


def test_units_capped_at_max():
    rm = make_rm(max_units=1000)
    plan = rm.build_order("USD_JPY", 1, 10_000_000, 150.0, sl_price=149.99,
                          tp_price=None, open_positions=0, today=TODAY)
    assert plan.units == 1000


def test_too_small_size_rejected():
    rm = make_rm(min_units=100)
    with pytest.raises(RiskRejection, match="最小単位"):
        rm.build_order("USD_JPY", 1, 1_000, 150.0, sl_price=100.0,
                       tp_price=None, open_positions=0, today=TODAY)


def test_excessive_risk_per_trade_rejected():
    with pytest.raises(ValueError):
        RiskManager(risk_per_trade=0.10)
