"""戦略の抽象クラス。

戦略は「確定したローソク足から売買シグナルを計算する」ことだけに責任を持つ。
ロット計算・SL強制・損失制限などのリスク管理は risk 層が担い、戦略からは独立。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

# シグナル値
LONG = 1
SHORT = -1
FLAT = 0


class Strategy(ABC):
    """差し替え可能な戦略の基底クラス。"""

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """OHLCVのDataFrameを受け取り、'signal' 列を付けて返す。

        signal は各バーの「確定時点」で判断した値とすること
        (実際の約定は次バー始値になる。先読み禁止)。
          1: ロングエントリー / -1: ショートエントリー / 0: 何もしない
        """

    @property
    def name(self) -> str:
        return type(self).__name__

    def params(self) -> dict:
        """最適化・記録用のパラメータ辞書。サブクラスで上書きする。"""
        return {}
