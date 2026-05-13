from __future__ import annotations

from collections import defaultdict
from html import escape

from .models import Bucket, Report, StockResult


def render_report(report: Report) -> str:
    top_sectors = report.sector_results[:3]
    buckets = _group_stocks(report.stock_results)

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(report.title)}</title>
  <style>{_css()}</style>
</head>
<body>
  <header class="hero">
    <div>
      <p class="eyebrow">AI Stock Single</p>
      <h1>{escape(report.title)}</h1>
      <p class="market-view">{escape(report.market_view)}</p>
      <p class="stamp">產出時間：{escape(report.generated_at)}</p>
    </div>
  </header>

  <main>
    <section class="section">
      <div class="section-head">
        <h2>族群輪動排名</h2>
        <p>資金占比用該族群成交金額除以全市場成交金額計算，分數再納入活性、價格動能、海外行情、估值位置與過熱風險。</p>
      </div>
      <div class="sector-grid">
        {''.join(_sector_card(item, index + 1) for index, item in enumerate(top_sectors))}
      </div>
    </section>

    <section class="section">
      <div class="section-head">
        <h2>短線波段名單</h2>
        <p>策略偏好：拉回找買點，其次是低本益比與籌碼轉強；衝高過熱會提高風險分數。</p>
      </div>
      {_stock_section(Bucket.ACTIONABLE, buckets, report)}
      {_stock_section(Bucket.WATCH, buckets, report)}
      {_stock_section(Bucket.EXCLUDED, buckets, report)}
    </section>

    <section class="section methodology">
      <h2>欄位判讀</h2>
      <div class="method-grid">
        <div><strong>本益比位置</strong><span>橫軸越左代表個股本益比越接近族群低檔，越右代表越接近族群高檔；右側不是越好，而是估值越貴。</span></div>
        <div><strong>外資/投信 5 日</strong><span>單位是張，正數代表近五日累計買超，負數代表累計賣超。</span></div>
        <div><strong>融資 5 日</strong><span>代表融資餘額近五日變化率；上升太快通常代表籌碼變熱，會提高風險。</span></div>
        <div><strong>合理估值</strong><span>用個股 EPS 估算，EPS = 收盤價 / 個股本益比，再乘上族群低檔、平均、高檔本益比。</span></div>
      </div>
    </section>
  </main>
</body>
</html>"""


def _group_stocks(stocks: list[StockResult]) -> dict[Bucket, list[StockResult]]:
    grouped: dict[Bucket, list[StockResult]] = defaultdict(list)
    for item in stocks:
        grouped[item.bucket].append(item)
    return grouped


def _sector_card(item, rank: int) -> str:
    metrics = item.metrics
    notes = "".join(f"<li>{escape(note)}</li>" for note in item.score.notes)
    catalysts = "".join(f"<span>{escape(text)}</span>" for text in metrics.catalysts)
    risks = "".join(f"<span>{escape(text)}</span>" for text in metrics.risks)
    share_delta = metrics.capital_share - metrics.capital_share_prev
    turnover_delta = _pct_change(metrics.turnover_value, metrics.turnover_value_prev)
    turnover_text = "資料待補" if turnover_delta is None else f"{turnover_delta:+.1f}%"
    return f"""
      <article class="sector-card">
        <div class="card-top">
          <span class="card-label">輪動族群</span>
          <span class="rank-badge">第 {rank} 名</span>
        </div>
        <h3>{escape(metrics.name)}</h3>
        <p>{escape(metrics.theme)}</p>
        <div class="sector-stats">
          <div><span>資金占比</span><strong>{metrics.capital_share:.1f}%</strong><em>{share_delta:+.1f}ppt</em></div>
          <div><span>成交金額</span><strong>{metrics.turnover_value:,.0f}百萬</strong><em>{turnover_text}</em></div>
          <div><span>強勢股比例</span><strong>{metrics.strong_stock_ratio:.0f}/100</strong><em>越高越強</em></div>
          <div><span>過熱風險</span><strong>{metrics.risk_heat:.0f}/100</strong><em>越高越熱</em></div>
        </div>
        <ul>{notes}</ul>
        <div class="tag-row">{catalysts}</div>
        <div class="risk-row">{risks}</div>
      </article>
    """


def _stock_section(bucket: Bucket, buckets: dict[Bucket, list[StockResult]], report: Report) -> str:
    rows = buckets.get(bucket, [])
    if bucket is Bucket.WATCH:
        rows = rows[:5]
    elif bucket is Bucket.EXCLUDED:
        rows = rows[:5]
    if not rows:
        body = '<p class="empty">目前沒有符合條件的個股。</p>'
    else:
        body = '<div class="stock-list">' + "".join(_stock_card(item, report, index + 1) for index, item in enumerate(rows)) + "</div>"
    return f"""
      <div class="bucket">
        <h3>{bucket.value}</h3>
        {body}
      </div>
    """


def _stock_card(item: StockResult, report: Report, rank: int) -> str:
    m = item.metrics
    notes = "".join(f"<li>{escape(note)}</li>" for note in item.score.notes[:3])
    pe_position = _pe_position(m.pe, m.sector_pe_low, m.sector_pe_high)
    fair_low, fair_avg, fair_high = _fair_values(m)
    chart = _chart_svg(report.price_history.get(m.symbol, []))
    pe_text = _pe_text(m, pe_position)
    return f"""
      <article class="stock-card">
        <div class="stock-main">
          <div>
            <span class="sector-pill">{escape(m.sector)}</span>
            <h4>{escape(m.name)} <small>{escape(m.symbol)}</small></h4>
            <p>{escape(m.thesis)}</p>
          </div>
          <div class="rank-badge">第 {rank} 名</div>
        </div>
        <div class="metrics">
          <div><span>收盤價</span><strong>{m.close:.1f} 元</strong></div>
          <div><span>本益比</span><strong>{_pe_display(m.pe)}</strong></div>
          <div><span>族群本益比區間</span><strong>{_pe_range_display(m)}</strong></div>
          <div><span>族群平均本益比</span><strong>{_pe_display(m.sector_pe_avg)}</strong></div>
        </div>
        <div class="valuation-box">
          <span>合理估值推估</span>
          <strong>{_fair_display(fair_low, fair_avg, fair_high)}</strong>
          <em>低檔 / 平均 / 高檔本益比推估</em>
        </div>
        <div class="pe-track" title="{escape(pe_text)}" style="--pos:{pe_position:.1f}">
          <b>低估</b><i></i><b>高估</b>
        </div>
        <p class="hint">{escape(pe_text)}</p>
        <div class="chips">
          <span>外資近5日：{_net_text(m.foreign_5d)}</span>
          <span>投信近5日：{_net_text(m.trust_5d)}</span>
          <span>融資餘額近5日變化：{m.margin_change_5d:+.1f}%</span>
        </div>
        {chart}
        <ul>{notes}</ul>
        <p class="risk-text">風險：{escape(m.risk_reason)}</p>
      </article>
    """


def _chart_svg(rows: list[dict[str, float | str]]) -> str:
    if len(rows) < 5:
        return '<div class="chart-empty">近一月日 K 線資料待補；接上每日 OHLC 後會顯示 5/20/60 日均線。</div>'

    width, height = 360, 190
    left_pad, right_pad, top_pad, bottom_pad = 44, 14, 18, 34
    prices: list[float] = []
    for row in rows:
        prices.extend([float(row["high"]), float(row["low"]), float(row["ma5"]), float(row["ma20"]), float(row["ma60"])])
    low, high = min(prices), max(prices)
    padding = (high - low) * 0.08 or max(high * 0.03, 1)
    low -= padding
    high += padding
    span = high - low or 1

    def y(value: float) -> float:
        return top_pad + (high - value) / span * (height - top_pad - bottom_pad)

    chart_width = width - left_pad - right_pad
    chart_height = height - top_pad - bottom_pad
    step = chart_width / max(1, len(rows) - 1)
    candles = []
    ma5, ma20, ma60 = [], [], []
    for index, row in enumerate(rows):
        x = left_pad + index * step
        open_, close = float(row["open"]), float(row["close"])
        high_, low_ = float(row["high"]), float(row["low"])
        color = "#c0392b" if close >= open_ else "#177245"
        body_y = min(y(open_), y(close))
        body_h = max(2, abs(y(open_) - y(close)))
        candles.append(
            f'<line x1="{x:.1f}" y1="{y(high_):.1f}" x2="{x:.1f}" y2="{y(low_):.1f}" stroke="{color}" stroke-width="1"/>'
            f'<rect x="{x - 3:.1f}" y="{body_y:.1f}" width="6" height="{body_h:.1f}" fill="{color}"/>'
        )
        ma5.append(f"{x:.1f},{y(float(row['ma5'])):.1f}")
        ma20.append(f"{x:.1f},{y(float(row['ma20'])):.1f}")
        ma60.append(f"{x:.1f},{y(float(row['ma60'])):.1f}")

    y_ticks = [high - span * ratio for ratio in (0, 0.5, 1)]
    y_axis = "".join(
        f'<line x1="{left_pad}" y1="{y(value):.1f}" x2="{width - right_pad}" y2="{y(value):.1f}" stroke="#eef1f5"/>'
        f'<text x="{left_pad - 6}" y="{y(value) + 4:.1f}" text-anchor="end" font-size="10" fill="#667085">{value:.1f}</text>'
        for value in y_ticks
    )
    tick_indexes = sorted({0, len(rows) // 2, len(rows) - 1})
    x_axis = "".join(
        f'<text x="{left_pad + index * step:.1f}" y="{height - 10}" text-anchor="middle" font-size="10" fill="#667085">{_short_date(str(rows[index]["date"]))}</text>'
        for index in tick_indexes
    )
    first_close = float(rows[0]["close"])
    last_close = float(rows[-1]["close"])
    change = (last_close - first_close) / first_close * 100 if first_close else 0.0
    chart_title = "近一月日 K" if len(rows) >= 18 else f"近期日 K（{len(rows)}日）"

    return f"""
      <div class="chart">
        <div class="chart-head"><span>{chart_title} <small>{change:+.1f}%</small></span><em>MA5</em><em>MA20</em><em>MA60</em></div>
        <svg viewBox="0 0 {width} {height}" role="img" aria-label="{chart_title}與均線">
          {y_axis}
          <line x1="{left_pad}" y1="{height - bottom_pad}" x2="{width - right_pad}" y2="{height - bottom_pad}" stroke="#d9dee7"/>
          <line x1="{left_pad}" y1="{top_pad}" x2="{left_pad}" y2="{height - bottom_pad}" stroke="#d9dee7"/>
          {''.join(candles)}
          <polyline points="{' '.join(ma5)}" fill="none" stroke="#e0a100" stroke-width="1.6"/>
          <polyline points="{' '.join(ma20)}" fill="none" stroke="#2673c9" stroke-width="1.6"/>
          <polyline points="{' '.join(ma60)}" fill="none" stroke="#7a4cc2" stroke-width="1.6"/>
          {x_axis}
        </svg>
      </div>
    """


def _fair_values(m) -> tuple[float, float, float]:
    if m.fair_value_low and m.fair_value_avg and m.fair_value_high:
        return m.fair_value_low, m.fair_value_avg, m.fair_value_high
    if m.pe <= 0:
        return 0.0, 0.0, 0.0
    eps = m.close / m.pe
    return eps * m.sector_pe_low, eps * m.sector_pe_avg, eps * m.sector_pe_high


def _pe_text(m, pe_position: float) -> str:
    if m.pe <= 0 or m.sector_pe_high <= 0:
        return "本益比位置：資料待補；此股目前是全市場初篩候選，尚未接入完整估值資料。"
    return f"本益比位置：族群區間第 {pe_position:.0f} 百分位；越左代表越便宜，越右代表越接近高估。"


def _pe_display(value: float) -> str:
    if value <= 0:
        return "待補"
    return f"{value:.1f}x"


def _pe_range_display(m) -> str:
    if m.sector_pe_low <= 0 or m.sector_pe_high <= 0:
        return "待補"
    return f"{m.sector_pe_low:.1f}-{m.sector_pe_high:.1f}x"


def _fair_display(low: float, avg: float, high: float) -> str:
    if low <= 0 or avg <= 0 or high <= 0:
        return "估值資料待補"
    return f"{low:.1f} / {avg:.1f} / {high:.1f} 元"


def _net_text(value: float) -> str:
    if value > 0:
        return f"買超 {value:,.0f} 張"
    if value < 0:
        return f"賣超 {abs(value):,.0f} 張"
    return "0 張"


def _pe_position(pe: float, low: float, high: float) -> float:
    if high <= low:
        return 50.0
    return max(0.0, min(100.0, (pe - low) / (high - low) * 100))


def _pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return (current - previous) / previous * 100


def _short_date(value: str) -> str:
    parts = value.split("-")
    if len(parts) == 3:
        return f"{int(parts[1])}/{int(parts[2])}"
    return value[-5:]


def _css() -> str:
    return """
:root {
  --bg: #f6f7f9;
  --panel: #ffffff;
  --ink: #1e252e;
  --muted: #667085;
  --line: #d9dee7;
  --accent: #147c72;
  --accent-2: #c87420;
  --risk: #b42318;
  --ok-bg: #eaf6f3;
}
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans TC", sans-serif; color: var(--ink); background: var(--bg); line-height: 1.55; }
.hero { min-height: 42vh; display: flex; align-items: end; padding: 40px max(20px, 6vw); background: linear-gradient(90deg, rgba(12,31,42,.90), rgba(12,31,42,.68)), url("https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1800&q=80") center/cover; color: white; }
.hero > div { max-width: 980px; }
.eyebrow { text-transform: uppercase; letter-spacing: .08em; color: #9bd8d1; font-size: .82rem; font-weight: 700; }
h1 { margin: 8px 0 14px; font-size: clamp(2rem, 4.8vw, 3.9rem); line-height: 1.08; letter-spacing: 0; max-width: 1040px; }
.market-view { max-width: 860px; font-size: clamp(1rem, 2vw, 1.24rem); color: #e4ebf2; }
.stamp { color: #b8c7d5; font-size: .92rem; }
main { padding: 28px max(16px, 5vw) 56px; }
.section { max-width: 1180px; margin: 0 auto 34px; }
.section-head { display: flex; justify-content: space-between; gap: 20px; align-items: end; margin-bottom: 16px; }
h2 { margin: 0; font-size: 1.45rem; }
.section-head p, .hint { margin: 0; color: var(--muted); max-width: 680px; }
.sector-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.sector-card, .stock-card, .method-grid div { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; box-shadow: 0 8px 22px rgba(20, 31, 44, .05); }
.sector-card, .stock-card { padding: 16px; }
.card-top, .stock-main { display: flex; justify-content: space-between; gap: 16px; }
.card-label { font-weight: 750; color: var(--muted); font-size: .82rem; }
.rank-badge { align-self: start; white-space: nowrap; color: var(--accent); background: var(--ok-bg); border: 1px solid #cde9e4; border-radius: 999px; padding: 5px 10px; font-weight: 800; font-size: .9rem; }
h3, h4 { margin: 8px 0 6px; }
h4 { font-size: 1.15rem; }
small { color: var(--muted); font-size: .85rem; }
.sector-card p, .stock-card p { color: var(--muted); margin: 0 0 12px; }
.bar { height: 8px; background: #edf0f4; border-radius: 999px; overflow: hidden; position: relative; }
.bar i { display: block; height: 100%; background: var(--accent); }
.sector-stats, .metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin: 14px 0; }
.sector-stats div, .metrics div, .valuation-box { border: 1px solid var(--line); border-radius: 6px; padding: 8px; }
.sector-stats span, .metrics span, .valuation-box span { display: block; color: var(--muted); font-size: .78rem; }
.sector-stats strong, .metrics strong, .valuation-box strong { display: block; font-size: .98rem; }
.sector-stats em, .valuation-box em { display: block; color: var(--muted); font-size: .76rem; font-style: normal; }
ul { padding-left: 18px; margin: 12px 0; color: #394452; }
.tag-row, .risk-row, .chips { display: flex; flex-wrap: wrap; gap: 6px; }
.tag-row span, .chips span, .sector-pill { background: var(--ok-bg); color: #0f5f58; border-radius: 999px; padding: 4px 8px; font-size: .82rem; font-weight: 650; }
.risk-row { margin-top: 8px; }
.risk-row span { color: var(--risk); background: #fff0ee; border-radius: 999px; padding: 4px 8px; font-size: .82rem; }
.bucket { margin-top: 22px; }
.bucket > h3 { border-left: 5px solid var(--accent); padding-left: 10px; }
.stock-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.valuation-box { margin-bottom: 12px; background: #fbfcfd; }
.pe-track { height: 18px; position: relative; display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 8px; color: var(--muted); font-size: .76rem; }
.pe-track:before { content: ""; position: absolute; left: 34px; right: 34px; top: 8px; height: 6px; border-radius: 999px; background: linear-gradient(90deg, #2f9e72, #f2c94c, #d64545); }
.pe-track i { position: absolute; top: 2px; left: calc(34px + (100% - 68px) * var(--pos) / 100); width: 4px; height: 18px; background: #111827; border-radius: 2px; transform: translateX(-2px); }
.hint { font-size: .78rem; margin: 4px 0 10px; }
.chart, .chart-empty { margin-top: 12px; border: 1px solid var(--line); border-radius: 6px; padding: 8px; background: #fbfcfd; }
.chart svg { width: 100%; height: auto; display: block; }
.chart-head { display: flex; gap: 10px; align-items: center; font-size: .78rem; color: var(--muted); }
.chart-head span { font-weight: 700; color: var(--ink); margin-right: auto; }
.chart-head em { font-style: normal; }
.chart-head em:nth-child(2) { color: #e0a100; }
.chart-head em:nth-child(3) { color: #2673c9; }
.chart-head em:nth-child(4) { color: #7a4cc2; }
.chart-empty { color: var(--muted); font-size: .86rem; }
.risk-text { color: var(--risk) !important; font-weight: 650; }
.method-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.method-grid div { padding: 16px; }
.method-grid strong { display: block; margin-bottom: 6px; }
.method-grid span { color: var(--muted); }
.empty { color: var(--muted); }
@media (max-width: 980px) {
  .sector-grid, .stock-list, .method-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .section-head { display: block; }
  .section-head p { margin-top: 6px; }
}
@media (max-width: 620px) {
  .hero { min-height: 52vh; padding: 30px 18px; }
  main { padding: 22px 12px 42px; }
  .sector-grid, .stock-list, .method-grid { grid-template-columns: 1fr; }
  .stock-main { align-items: start; }
  .metrics, .sector-stats { grid-template-columns: 1fr 1fr; }
}
"""
