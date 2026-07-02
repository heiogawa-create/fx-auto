"""バックテスト結果を単一のHTMLファイルとして出力する。

外部CDNに依存せず、生成したHTMLファイル単体をダブルクリックで開ける形にする。
配色・マーク仕様は社内datavizガイドラインの参照パレットに準拠。
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import pandas as pd

from fxauto.backtest.engine import BacktestResult
from fxauto.backtest.metrics import Metrics

_CHART_WIDTH = 880
_CHART_HEIGHT = 320
_PAD_LEFT = 56
_PAD_RIGHT = 16
_PAD_TOP = 16
_PAD_BOTTOM = 32


def _fmt_yen(v: float) -> str:
    return f"{v:,.0f}"


def _equity_svg_data(curve: pd.Series) -> dict:
    """SVG描画に必要な座標・軸ラベルをまとめる。"""
    if len(curve) < 2:
        return {"points": [], "path": "", "area_path": "", "y_ticks": [], "x_ticks": []}

    values = curve.to_numpy(dtype=float)
    times = curve.index

    y_min, y_max = float(values.min()), float(values.max())
    if y_min == y_max:
        y_min -= 1.0
        y_max += 1.0
    y_span = y_max - y_min

    plot_w = _CHART_WIDTH - _PAD_LEFT - _PAD_RIGHT
    plot_h = _CHART_HEIGHT - _PAD_TOP - _PAD_BOTTOM
    n = len(values)

    def x_of(i: int) -> float:
        return _PAD_LEFT + (i / (n - 1)) * plot_w

    def y_of(v: float) -> float:
        return _PAD_TOP + (1 - (v - y_min) / y_span) * plot_h

    points = [
        {"x": round(x_of(i), 2), "y": round(y_of(v), 2), "t": str(times[i]), "v": round(float(v), 2)}
        for i, v in enumerate(values)
    ]
    path = "M " + " L ".join(f"{p['x']},{p['y']}" for p in points)
    baseline_y = _PAD_TOP + plot_h
    area_path = path + f" L {points[-1]['x']},{baseline_y} L {points[0]['x']},{baseline_y} Z"

    # Y軸: 4分割の目盛り
    y_ticks = []
    for i in range(5):
        v = y_min + y_span * i / 4
        y_ticks.append({"y": round(y_of(v), 2), "label": _fmt_yen(v)})

    # X軸: 先頭・中央・末尾のみラベル
    x_ticks = []
    for i in (0, n // 2, n - 1):
        x_ticks.append({"x": round(x_of(i), 2), "label": str(times[i])[:10]})

    return {
        "points": points, "path": path, "area_path": area_path,
        "y_ticks": y_ticks, "x_ticks": x_ticks, "baseline_y": baseline_y,
    }


def _stat_tile(label: str, value: str, accent: bool = False) -> str:
    cls = "stat-tile stat-tile--accent" if accent else "stat-tile"
    return (
        f'<div class="{cls}"><div class="stat-label">{html.escape(label)}</div>'
        f'<div class="stat-value">{html.escape(value)}</div></div>'
    )


def _warnings_html(warnings: list[str]) -> str:
    if not warnings:
        return ""
    items = "".join(f"<li>{html.escape(w)}</li>" for w in warnings)
    return (
        '<div class="callout callout--warning">'
        '<span class="callout-icon" aria-hidden="true">&#9888;</span>'
        '<div><div class="callout-title">検証結果への注意</div>'
        f'<ul class="callout-list">{items}</ul></div></div>'
    )


def _trades_table_html(result: BacktestResult) -> str:
    if not result.trades:
        return '<p class="muted">取引はありませんでした。</p>'
    rows = []
    for t in result.trades:
        direction = "ロング" if t.direction > 0 else "ショート"
        pnl = t.pnl if t.pnl is not None else 0.0
        pnl_cls = "pnl-pos" if pnl >= 0 else "pnl-neg"
        exit_price_str = f"{t.exit_price:.3f}" if t.exit_price is not None else "-"
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(t.entry_time))}</td>"
            f"<td>{html.escape(str(t.exit_time) if t.exit_time is not None else '-')}</td>"
            f"<td>{direction}</td>"
            f"<td class=\"num\">{t.entry_price:.3f}</td>"
            f"<td class=\"num\">{exit_price_str}</td>"
            f"<td class=\"num\">{t.units:,.0f}</td>"
            f"<td class=\"num {pnl_cls}\">{pnl:+,.0f}</td>"
            f"<td>{html.escape(t.exit_reason)}</td>"
            "</tr>"
        )
    header = (
        "<tr><th>エントリー日時</th><th>決済日時</th><th>方向</th>"
        "<th class=\"num\">エントリー価格</th><th class=\"num\">決済価格</th>"
        "<th class=\"num\">数量</th><th class=\"num\">損益</th><th>決済理由</th></tr>"
    )
    return (
        '<div class="table-scroll"><table class="trades-table">'
        f"<thead>{header}</thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def generate_html_report(
    result: BacktestResult,
    metrics: Metrics,
    instrument: str,
    granularity: str,
    strategy_name: str,
) -> str:
    curve = result.equity_curve
    period_start = str(curve.index.min())[:10] if len(curve) else "-"
    period_end = str(curve.index.max())[:10] if len(curve) else "-"
    chart = _equity_svg_data(curve)

    stat_tiles = "".join([
        _stat_tile("取引回数", f"{metrics.num_trades}"),
        _stat_tile("プロフィットファクター", f"{metrics.profit_factor:.2f}"),
        _stat_tile("勝率", f"{metrics.win_rate:.1%}"),
        _stat_tile("最大ドローダウン", f"{metrics.max_drawdown:.1%}"),
        _stat_tile("シャープレシオ", f"{metrics.sharpe_ratio:.2f}"),
        _stat_tile("トータルリターン", f"{metrics.total_return:+.1%}", accent=True),
    ])

    points_json = json.dumps(chart["points"], ensure_ascii=False)
    y_ticks_html = "".join(
        f'<text class="axis-label" x="{_PAD_LEFT - 8}" y="{t["y"] + 4}" text-anchor="end">{html.escape(t["label"])}</text>'
        f'<line class="gridline" x1="{_PAD_LEFT}" y1="{t["y"]}" x2="{_CHART_WIDTH - _PAD_RIGHT}" y2="{t["y"]}" />'
        for t in chart["y_ticks"]
    )
    x_ticks_html = "".join(
        f'<text class="axis-label" x="{t["x"]}" y="{_CHART_HEIGHT - 10}" text-anchor="middle">{html.escape(t["label"])}</text>'
        for t in chart["x_ticks"]
    )

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>バックテストレポート: {html.escape(instrument)} {html.escape(granularity)}</title>
<style>
  .viz-root {{
    --surface-1: #fcfcfb; --page: #f9f9f7;
    --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #898781;
    --gridline: #e1e0d9; --baseline: #c3c2b7; --border: rgba(11,11,11,0.10);
    --series-1: #2a78d6; --series-1-wash: rgba(42,120,214,0.10);
    --good: #006300; --bad: #b3261e; --warning-bg: #fdf3df; --warning-ink: #7a4a00;
  }}
  @media (prefers-color-scheme: dark) {{
    .viz-root {{
      --surface-1: #1a1a19; --page: #0d0d0d;
      --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
      --gridline: #2c2c2a; --baseline: #383835; --border: rgba(255,255,255,0.10);
      --series-1: #3987e5; --series-1-wash: rgba(57,135,229,0.14);
      --good: #0ca30c; --bad: #e66767; --warning-bg: #2a230f; --warning-ink: #f0c26a;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 32px 16px;
    background: var(--page); color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  }}
  .container {{ max-width: 960px; margin: 0 auto; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .subtitle {{ color: var(--text-secondary); font-size: 14px; margin: 0 0 24px; }}
  .card {{
    background: var(--surface-1); border: 1px solid var(--border);
    border-radius: 8px; padding: 20px; margin-bottom: 20px;
  }}
  .card h2 {{ font-size: 14px; color: var(--text-secondary); margin: 0 0 16px; font-weight: 600; }}
  .stat-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; }}
  .stat-tile {{ padding: 12px 14px; border: 1px solid var(--border); border-radius: 6px; }}
  .stat-tile--accent {{ border-color: var(--series-1); }}
  .stat-label {{ font-size: 12px; color: var(--text-secondary); margin-bottom: 6px; }}
  .stat-value {{ font-size: 22px; font-weight: 600; color: var(--text-primary); }}
  .callout {{ display: flex; gap: 10px; padding: 14px 16px; border-radius: 6px;
    background: var(--warning-bg); color: var(--warning-ink); margin-bottom: 20px; }}
  .callout-icon {{ font-size: 18px; line-height: 1.4; }}
  .callout-title {{ font-weight: 600; margin-bottom: 4px; }}
  .callout-list {{ margin: 0; padding-left: 18px; }}
  .axis-label {{ font-size: 10px; fill: var(--text-muted); }}
  .gridline {{ stroke: var(--gridline); stroke-width: 1; }}
  .equity-line {{ fill: none; stroke: var(--series-1); stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }}
  .equity-area {{ fill: var(--series-1-wash); }}
  .crosshair {{ stroke: var(--baseline); stroke-width: 1; display: none; }}
  .hover-dot {{ fill: var(--series-1); stroke: var(--surface-1); stroke-width: 2; r: 4; display: none; }}
  .tooltip {{
    position: absolute; display: none; pointer-events: none;
    background: var(--surface-1); border: 1px solid var(--border); border-radius: 6px;
    padding: 8px 10px; font-size: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  }}
  .tooltip-value {{ font-weight: 600; font-size: 14px; color: var(--text-primary); }}
  .tooltip-date {{ color: var(--text-secondary); }}
  .chart-wrap {{ position: relative; }}
  table.trades-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  .table-scroll {{ overflow-x: auto; }}
  .trades-table th, .trades-table td {{
    padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--gridline);
    white-space: nowrap;
  }}
  .trades-table th {{ color: var(--text-secondary); font-weight: 600; font-size: 12px; }}
  .trades-table td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .pnl-pos {{ color: var(--good); }}
  .pnl-neg {{ color: var(--bad); }}
  .muted {{ color: var(--text-muted); }}
</style>
</head>
<body class="viz-root" data-palette="#2a78d6,#1baf7a,#eda100,#008300,#4a3aa7,#e34948,#e87ba4,#eb6834">
<div class="container">
  <h1>バックテストレポート</h1>
  <p class="subtitle">
    {html.escape(instrument)} / {html.escape(granularity)} / 戦略: {html.escape(strategy_name)}
    ({html.escape(period_start)} 〜 {html.escape(period_end)})
  </p>

  {_warnings_html(metrics.warnings)}

  <div class="card">
    <h2>成績サマリー</h2>
    <div class="stat-grid">{stat_tiles}</div>
  </div>

  <div class="card">
    <h2>資産推移(残高 + 含み損益)</h2>
    <div class="chart-wrap">
      <svg id="equity-chart" width="{_CHART_WIDTH}" height="{_CHART_HEIGHT}" viewBox="0 0 {_CHART_WIDTH} {_CHART_HEIGHT}">
        {y_ticks_html}
        <path class="equity-area" d="{chart['area_path']}"></path>
        <path class="equity-line" d="{chart['path']}"></path>
        {x_ticks_html}
        <line id="crosshair-line" class="crosshair" x1="0" y1="{_PAD_TOP}" x2="0" y2="{chart['baseline_y']}"></line>
        <circle id="hover-dot" class="hover-dot" cx="0" cy="0"></circle>
      </svg>
      <div id="tooltip" class="tooltip"></div>
    </div>
  </div>

  <div class="card">
    <h2>取引履歴</h2>
    {_trades_table_html(result)}
  </div>
</div>
<script>
(function() {{
  const points = {points_json};
  if (points.length === 0) return;
  const svg = document.getElementById('equity-chart');
  const crosshair = document.getElementById('crosshair-line');
  const dot = document.getElementById('hover-dot');
  const tooltip = document.getElementById('tooltip');
  const wrap = svg.parentElement;

  function nearest(px) {{
    let lo = 0, hi = points.length - 1;
    while (lo < hi) {{
      const mid = (lo + hi) >> 1;
      if (points[mid].x < px) lo = mid + 1; else hi = mid;
    }}
    return lo;
  }}

  function onMove(evt) {{
    const rect = svg.getBoundingClientRect();
    const scaleX = {_CHART_WIDTH} / rect.width;
    const px = (evt.clientX - rect.left) * scaleX;
    const i = nearest(px);
    const p = points[i];
    crosshair.setAttribute('x1', p.x);
    crosshair.setAttribute('x2', p.x);
    crosshair.style.display = 'block';
    dot.setAttribute('cx', p.x);
    dot.setAttribute('cy', p.y);
    dot.style.display = 'block';
    tooltip.innerHTML =
      '<div class="tooltip-date"></div><div class="tooltip-value"></div>';
    tooltip.querySelector('.tooltip-date').textContent = p.t;
    tooltip.querySelector('.tooltip-value').textContent =
      '¥' + Math.round(p.v).toLocaleString('ja-JP');
    const scale = rect.width / {_CHART_WIDTH};
    const left = Math.min(p.x * scale + 12, rect.width - 140);
    tooltip.style.left = left + 'px';
    tooltip.style.top = Math.max(p.y * scale - 40, 0) + 'px';
    tooltip.style.display = 'block';
  }}

  function onLeave() {{
    crosshair.style.display = 'none';
    dot.style.display = 'none';
    tooltip.style.display = 'none';
  }}

  svg.addEventListener('pointermove', onMove);
  svg.addEventListener('pointerleave', onLeave);
}})();
</script>
</body>
</html>
"""


def write_report(
    result: BacktestResult,
    metrics: Metrics,
    instrument: str,
    granularity: str,
    strategy_name: str,
    out_path: str | Path,
) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    html_str = generate_html_report(result, metrics, instrument, granularity, strategy_name)
    out_path.write_text(html_str, encoding="utf-8")
    return out_path
