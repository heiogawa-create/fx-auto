from fxauto.strategy.base import Strategy
from fxauto.strategy.ema_rsi import EmaRsiStrategy

STRATEGIES: dict[str, type[Strategy]] = {
    "ema_rsi": EmaRsiStrategy,
}


def create_strategy(name: str, params: dict) -> Strategy:
    if name not in STRATEGIES:
        raise ValueError(f"未知の戦略: {name} (利用可能: {list(STRATEGIES)})")
    return STRATEGIES[name](**params)
