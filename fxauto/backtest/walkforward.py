"""Walk-forward検証(In-Sample最適化 → Out-of-Sample評価)。

期間を n_splits 個のウィンドウに分け、各ウィンドウの前半(train_ratio)で
パラメータをグリッド最適化し、後半のOOSで評価する。
IS成績とOOS成績の乖離が大きければ過剰最適化として警告する。
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field

import pandas as pd

from fxauto.backtest.engine import Backtester
from fxauto.backtest.metrics import Metrics, compute_metrics

logger = logging.getLogger(__name__)

# OOSのPFがISの半分未満なら過剰最適化を疑う
OVERFIT_PF_DEGRADATION = 0.5


@dataclass
class WalkForwardWindow:
    fold: int
    best_params: dict
    is_metrics: Metrics
    oos_metrics: Metrics


@dataclass
class WalkForwardResult:
    windows: list[WalkForwardWindow]
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = []
        for w in self.windows:
            lines.append(
                f"[fold {w.fold}] params={w.best_params} | "
                f"IS: PF={w.is_metrics.profit_factor:.2f} n={w.is_metrics.num_trades} | "
                f"OOS: PF={w.oos_metrics.profit_factor:.2f} n={w.oos_metrics.num_trades} "
                f"DD={w.oos_metrics.max_drawdown:.1%}"
            )
        for warn in self.warnings:
            lines.append(f"⚠ {warn}")
        return "\n".join(lines)


def _score(m: Metrics) -> float:
    """IS最適化のスコア。取引が少なすぎる組合せは足切り。"""
    if m.num_trades < 5:
        return float("-inf")
    pf = min(m.profit_factor, 10.0)  # inf対策
    return pf


def walk_forward(
    df: pd.DataFrame,
    strategy_cls,
    param_grid: dict[str, list],
    backtester_kwargs: dict,
    n_splits: int = 4,
    train_ratio: float = 0.7,
) -> WalkForwardResult:
    if not 0.0 < train_ratio < 1.0:
        raise ValueError("train_ratio は0と1の間で指定してください")
    if len(df) < n_splits * 100:
        raise ValueError(f"データが不足しています({len(df)}本)。分割数を減らすか期間を延ばしてください")

    keys = list(param_grid.keys())
    combos = [dict(zip(keys, values)) for values in itertools.product(*param_grid.values())]

    window_size = len(df) // n_splits
    windows: list[WalkForwardWindow] = []

    for fold in range(n_splits):
        chunk = df.iloc[fold * window_size: (fold + 1) * window_size]
        split = int(len(chunk) * train_ratio)
        is_df, oos_df = chunk.iloc[:split], chunk.iloc[split:]

        best_params, best_metrics, best_score = None, None, float("-inf")
        for params in combos:
            try:
                strategy = strategy_cls(**params)
            except ValueError:
                continue  # 不正な組合せ(fast >= slow など)はスキップ
            result = Backtester(**backtester_kwargs).run(is_df, strategy)
            m = compute_metrics(result)
            if _score(m) > best_score:
                best_score, best_params, best_metrics = _score(m), params, m

        if best_params is None:
            logger.warning("fold %d: 有効なパラメータがありません", fold)
            continue

        oos_result = Backtester(**backtester_kwargs).run(oos_df, strategy_cls(**best_params))
        oos_metrics = compute_metrics(oos_result)
        windows.append(
            WalkForwardWindow(
                fold=fold,
                best_params=best_params,
                is_metrics=best_metrics,
                oos_metrics=oos_metrics,
            )
        )

    return WalkForwardResult(windows=windows, warnings=_wf_warnings(windows))


def _wf_warnings(windows: list[WalkForwardWindow]) -> list[str]:
    warnings = []
    degraded = 0
    for w in windows:
        is_pf = min(w.is_metrics.profit_factor, 10.0)
        oos_pf = min(w.oos_metrics.profit_factor, 10.0)
        if is_pf > 0 and oos_pf < is_pf * OVERFIT_PF_DEGRADATION:
            degraded += 1
    if windows and degraded >= max(1, len(windows) // 2):
        warnings.append(
            f"{degraded}/{len(windows)} のfoldでOOSのPFがISの半分未満に劣化しています。"
            "過剰最適化(カーブフィッティング)の可能性が高いです"
        )
    losing_oos = sum(1 for w in windows if w.oos_metrics.profit_factor < 1.0)
    if windows and losing_oos > len(windows) / 2:
        warnings.append(
            f"{losing_oos}/{len(windows)} のfoldでOOSが負けています。"
            "この戦略は未知データで機能していません"
        )
    return warnings
