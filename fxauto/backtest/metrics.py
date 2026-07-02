"""バックテスト成績指標と過剰最適化(カーブフィッティング)警告。"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from fxauto.backtest.engine import BacktestResult

# 「良すぎる結果はまずバグ/過剰最適化を疑う」ための閾値
SUSPICIOUS_PF = 3.0
SUSPICIOUS_WIN_RATE = 0.80
SUSPICIOUS_SHARPE = 3.0
MIN_TRADES_FOR_CONFIDENCE = 30

# シャープレシオの年率換算用: 時間足ごとの年間バー数の概算(平日のみ)
PERIODS_PER_YEAR = {
    "M5": 288 * 252, "M15": 96 * 252, "M30": 48 * 252,
    "H1": 24 * 260, "H4": 6 * 260, "D": 252,
}


def periods_per_year_for(granularity: str) -> int:
    return PERIODS_PER_YEAR.get(granularity, 252)


@dataclass
class Metrics:
    profit_factor: float
    max_drawdown: float          # 残高比率(0.15 = 15%)
    win_rate: float
    sharpe_ratio: float
    num_trades: int
    total_return: float          # 初期残高比のリターン
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"取引回数        : {self.num_trades}",
            f"PF              : {self.profit_factor:.2f}",
            f"勝率            : {self.win_rate:.1%}",
            f"最大DD          : {self.max_drawdown:.1%}",
            f"シャープレシオ  : {self.sharpe_ratio:.2f}",
            f"トータルリターン: {self.total_return:.1%}",
        ]
        for w in self.warnings:
            lines.append(f"⚠ {w}")
        return "\n".join(lines)


def compute_metrics(result: BacktestResult, periods_per_year: int = 6240) -> Metrics:
    """成績指標を計算する。periods_per_year はH1・平日24hの概算値。"""
    pnls = np.array([t.pnl for t in result.trades if t.pnl is not None])
    n = len(pnls)

    gross_profit = float(pnls[pnls > 0].sum()) if n else 0.0
    gross_loss = float(-pnls[pnls < 0].sum()) if n else 0.0
    if gross_loss > 0:
        pf = gross_profit / gross_loss
    else:
        pf = math.inf if gross_profit > 0 else 0.0

    win_rate = float((pnls > 0).mean()) if n else 0.0

    curve = result.equity_curve
    if len(curve) > 1:
        peak = curve.cummax()
        dd = ((peak - curve) / peak).max()
        returns = curve.pct_change().dropna()
        std = returns.std()
        sharpe = float(returns.mean() / std * np.sqrt(periods_per_year)) if std > 0 else 0.0
    else:
        dd, sharpe = 0.0, 0.0

    total_return = result.final_balance / result.initial_balance - 1.0

    m = Metrics(
        profit_factor=pf,
        max_drawdown=float(dd),
        win_rate=win_rate,
        sharpe_ratio=sharpe,
        num_trades=n,
        total_return=total_return,
    )
    m.warnings = _overfit_warnings(m)
    return m


def _overfit_warnings(m: Metrics) -> list[str]:
    """優秀すぎる結果・信頼できない結果への警告。"""
    warnings = []
    if m.num_trades < MIN_TRADES_FOR_CONFIDENCE:
        warnings.append(
            f"取引回数が{m.num_trades}回と少なく統計的に信頼できません"
            f"(目安: {MIN_TRADES_FOR_CONFIDENCE}回以上)"
        )
    if m.profit_factor > SUSPICIOUS_PF:
        warnings.append(
            f"PF {m.profit_factor:.2f} は良すぎます。バグ(先読み・コスト抜け)や"
            "カーブフィッティングを疑って検証してください"
        )
    if m.win_rate > SUSPICIOUS_WIN_RATE and m.num_trades >= 10:
        warnings.append(f"勝率 {m.win_rate:.0%} は高すぎます。ロジックの先読みを確認してください")
    if m.sharpe_ratio > SUSPICIOUS_SHARPE:
        warnings.append(
            f"シャープレシオ {m.sharpe_ratio:.2f} は個人のFX戦略として異常に高い値です"
        )
    return warnings
