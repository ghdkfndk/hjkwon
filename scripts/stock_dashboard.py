#!/usr/bin/env python3
"""
종목 대시보드를 인터랙티브 HTML로 생성하는 스크립트.
차트는 Chart.js를 사용하여 브라우저에서 바로 볼 수 있는 단일 HTML 파일로 출력.

사용법:
    python scripts/stock_dashboard.py PLTR
    python scripts/stock_dashboard.py PLTR NVDA TSLA
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

try:
    import yfinance as yf
    HAS_YF = True
except ImportError:
    HAS_YF = False

KST = timezone(timedelta(hours=9))


def fetch_data(ticker: str) -> dict | None:
    stock = yf.Ticker(ticker)
    info = stock.info or {}
    hist = stock.history(period="1y")
    if hist.empty:
        return None

    income = stock.quarterly_income_stmt
    quarters = []
    shares = info.get("sharesOutstanding", 1)
    if income is not None and not income.empty:
        ni_row = income.loc["Net Income"] if "Net Income" in income.index else None
        rev_row = income.loc["Total Revenue"] if "Total Revenue" in income.index else None
        if ni_row is not None and rev_row is not None:
            for col in reversed(ni_row.index[:8]):
                ni = float(ni_row[col])
                rev = float(rev_row[col])
                quarters.append({
                    "label": col.strftime("%y/%m"),
                    "revenue": round(rev / 1e9, 3),
                    "net_income": round(ni / 1e9, 3),
                    "margin": round(ni / rev * 100, 1) if rev else 0,
                    "eps": round(ni / shares, 3) if shares else 0,
                })

    trailing_eps = info.get("trailingEps", 0) or 1
    price_data = []
    per_data = []
    for i in range(0, len(hist), 3):
        row = hist.iloc[i]
        d = row.name.strftime("%Y-%m-%d")
        p = round(float(row["Close"]), 2)
        price_data.append({"x": d, "y": p})
        if trailing_eps > 0:
            per_data.append({"x": d, "y": round(p / trailing_eps, 1)})
    last = hist.iloc[-1]
    d = last.name.strftime("%Y-%m-%d")
    price_data.append({"x": d, "y": round(float(last["Close"]), 2)})
    if trailing_eps > 0:
        per_data.append({"x": d, "y": round(float(last["Close"]) / trailing_eps, 1)})

    return {
        "ticker": ticker,
        "name": info.get("shortName", ticker),
        "sector": info.get("sector", ""),
        "industry": info.get("industry", ""),
        "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "market_cap": info.get("marketCap"),
        "trailing_pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "peg": info.get("pegRatio"),
        "pb": info.get("priceToBook"),
        "eps": info.get("trailingEps"),
        "forward_eps": info.get("forwardEps"),
        "revenue_growth": info.get("revenueGrowth"),
        "earnings_growth": info.get("earningsGrowth"),
        "profit_margin": info.get("profitMargins"),
        "w52_high": info.get("fiftyTwoWeekHigh"),
        "w52_low": info.get("fiftyTwoWeekLow"),
        "price_history": price_data,
        "per_history": per_data,
        "quarters": quarters,
    }


def _fmt_cap(val):
    if not val: return "N/A"
    if val >= 1e12: return f"${val/1e12:.2f}T"
    if val >= 1e9: return f"${val/1e9:.1f}B"
    return f"${val/1e6:.0f}M"


def _fmt_pct(val):
    if val is None: return "N/A"
    return f"{val*100:+.1f}%"


def _pe_label(pe):
    if pe is None: return "N/A", "#999"
    if pe < 0: return f"{pe:.1f} (적자)", "#F44336"
    if pe < 15: return f"{pe:.1f} (저평가)", "#4CAF50"
    if pe < 25: return f"{pe:.1f} (적정)", "#2196F3"
    if pe < 40: return f"{pe:.1f} (고평가)", "#FF9800"
    return f"{pe:.1f} (매우 고평가)", "#F44336"


def generate_html(stocks: list[dict]) -> str:
    now = datetime.now(KST).strftime("%Y년 %m월 %d일 %H:%M KST")

    cards_html = ""
    charts_js = ""

    for i, s in enumerate(stocks):
        pe_text, pe_color = _pe_label(s["trailing_pe"])
        fpe_text, fpe_color = _pe_label(s["forward_pe"])

        q_labels = json.dumps([q["label"] for q in s["quarters"]])
        q_rev = json.dumps([q["revenue"] for q in s["quarters"]])
        q_ni = json.dumps([q["net_income"] for q in s["quarters"]])
        q_margin = json.dumps([q["margin"] for q in s["quarters"]])
        price_json = json.dumps(s["price_history"])
        per_json = json.dumps(s["per_history"])

        growth_items = ""
        if s["revenue_growth"] is not None:
            rg = s["revenue_growth"] * 100
            rg_color = "#4CAF50" if rg > 20 else "#FF9800" if rg > 0 else "#F44336"
            growth_items += f'<div class="metric-item"><span class="metric-label">매출 성장률</span><span class="metric-value" style="color:{rg_color}">{rg:+.1f}%</span></div>'
        if s["earnings_growth"] is not None:
            eg = s["earnings_growth"] * 100
            eg_color = "#4CAF50" if eg > 20 else "#FF9800" if eg > 0 else "#F44336"
            growth_items += f'<div class="metric-item"><span class="metric-label">이익 성장률</span><span class="metric-value" style="color:{eg_color}">{eg:+.1f}%</span></div>'
        if s["profit_margin"] is not None:
            pm = s["profit_margin"] * 100
            growth_items += f'<div class="metric-item"><span class="metric-label">이익률</span><span class="metric-value">{pm:.1f}%</span></div>'
        if s["peg"] is not None:
            peg_color = "#4CAF50" if s["peg"] < 1 else "#2196F3" if s["peg"] < 1.5 else "#FF9800" if s["peg"] < 3 else "#F44336"
            growth_items += f'<div class="metric-item"><span class="metric-label">PEG</span><span class="metric-value" style="color:{peg_color}">{s["peg"]:.2f}</span></div>'

        w52_html = ""
        if s["w52_high"] and s["w52_low"] and s["current_price"]:
            pos = (s["current_price"] - s["w52_low"]) / (s["w52_high"] - s["w52_low"]) * 100
            w52_html = f"""
            <div class="w52-range">
                <div class="w52-label"><span>${s["w52_low"]:.0f}</span><span>52주 범위</span><span>${s["w52_high"]:.0f}</span></div>
                <div class="w52-bar"><div class="w52-fill" style="width:{pos:.0f}%"></div><div class="w52-dot" style="left:{pos:.0f}%"></div></div>
            </div>"""

        cards_html += f"""
        <div class="stock-card">
            <div class="card-header">
                <div>
                    <h2>{s["name"]}</h2>
                    <span class="ticker">{s["ticker"]}</span>
                    <span class="sector">{s["sector"]} · {s["industry"]}</span>
                </div>
                <div class="price-box">
                    <span class="current-price">${s["current_price"]:.2f}</span>
                    <span class="market-cap">{_fmt_cap(s["market_cap"])}</span>
                </div>
            </div>

            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-title">밸류에이션</div>
                    <div class="metric-item"><span class="metric-label">Trailing PER</span><span class="metric-value" style="color:{pe_color}">{pe_text}</span></div>
                    <div class="metric-item"><span class="metric-label">Forward PER</span><span class="metric-value" style="color:{fpe_color}">{fpe_text}</span></div>
                    <div class="metric-item"><span class="metric-label">PBR</span><span class="metric-value">{f'{s["pb"]:.2f}' if s["pb"] else "N/A"}</span></div>
                    <div class="metric-item"><span class="metric-label">EPS</span><span class="metric-value">{f'${s["eps"]:.2f}' if s["eps"] else "N/A"}</span></div>
                    <div class="metric-item"><span class="metric-label">Forward EPS</span><span class="metric-value">{f'${s["forward_eps"]:.2f}' if s["forward_eps"] else "N/A"}</span></div>
                </div>
                <div class="metric-card">
                    <div class="metric-title">성장성</div>
                    {growth_items}
                </div>
            </div>

            {w52_html}

            <div class="charts-row">
                <div class="chart-box"><canvas id="priceChart{i}"></canvas></div>
                <div class="chart-box"><canvas id="perChart{i}"></canvas></div>
            </div>
            <div class="charts-row">
                <div class="chart-box"><canvas id="revenueChart{i}"></canvas></div>
                <div class="chart-box"><canvas id="marginChart{i}"></canvas></div>
            </div>
        </div>
        """

        charts_js += f"""
        new Chart(document.getElementById('priceChart{i}'), {{
            type: 'line',
            data: {{ datasets: [{{ label: '주가 ($)', data: {price_json}, borderColor: '#1976D2', backgroundColor: 'rgba(25,118,210,0.1)', fill: true, tension: 0.3, pointRadius: 0 }}] }},
            options: {{ responsive: true, plugins: {{ title: {{ display: true, text: '주가 추이 (1년)', font: {{ size: 14 }} }} }}, scales: {{ x: {{ type: 'time', time: {{ unit: 'month' }} }} }} }}
        }});
        new Chart(document.getElementById('perChart{i}'), {{
            type: 'line',
            data: {{ datasets: [{{ label: 'PER', data: {per_json}, borderColor: '#F44336', backgroundColor: 'rgba(244,67,54,0.1)', fill: true, tension: 0.3, pointRadius: 0 }}] }},
            options: {{ responsive: true, plugins: {{ title: {{ display: true, text: 'PER 추이 (1년)', font: {{ size: 14 }} }}, annotation: {{ annotations: {{ line1: {{ type: 'line', yMin: 25, yMax: 25, borderColor: '#4CAF50', borderDash: [5,5], label: {{ content: 'S&P평균', display: true }} }} }} }} }}, scales: {{ x: {{ type: 'time', time: {{ unit: 'month' }} }} }} }}
        }});
        new Chart(document.getElementById('revenueChart{i}'), {{
            type: 'bar',
            data: {{ labels: {q_labels}, datasets: [{{ label: '매출 ($B)', data: {q_rev}, backgroundColor: 'rgba(25,118,210,0.8)' }}, {{ label: '순이익 ($B)', data: {q_ni}, backgroundColor: 'rgba(76,175,80,0.8)' }}] }},
            options: {{ responsive: true, plugins: {{ title: {{ display: true, text: '분기별 매출 & 순이익', font: {{ size: 14 }} }} }} }}
        }});
        new Chart(document.getElementById('marginChart{i}'), {{
            type: 'bar',
            data: {{ labels: {q_labels}, datasets: [{{ label: '이익률 (%)', data: {q_margin}, backgroundColor: {q_margin}.map(v => v > 40 ? 'rgba(76,175,80,0.8)' : v > 20 ? 'rgba(255,193,7,0.8)' : 'rgba(244,67,54,0.8)') }}] }},
            options: {{ responsive: true, plugins: {{ title: {{ display: true, text: '분기별 이익률', font: {{ size: 14 }} }} }}, scales: {{ y: {{ beginAtZero: true, max: 70 }} }} }}
        }});
        """

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>📊 종목 대시보드</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, 'Nanum Gothic', sans-serif; background: linear-gradient(135deg, #0f0c29, #302b63, #24243e); min-height: 100vh; color: #E0E0E0; padding: 20px; }}
h1 {{ text-align: center; color: #fff; font-size: 28px; margin-bottom: 8px; }}
.subtitle {{ text-align: center; color: #aaa; margin-bottom: 30px; font-size: 14px; }}
.stock-card {{ background: rgba(255,255,255,0.05); backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; padding: 24px; margin-bottom: 30px; }}
.card-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; flex-wrap: wrap; gap: 12px; }}
.card-header h2 {{ color: #fff; font-size: 24px; margin-bottom: 4px; }}
.ticker {{ background: #1976D2; color: #fff; padding: 2px 10px; border-radius: 12px; font-size: 13px; font-weight: bold; margin-right: 8px; }}
.sector {{ color: #aaa; font-size: 13px; }}
.price-box {{ text-align: right; }}
.current-price {{ display: block; font-size: 32px; font-weight: bold; color: #fff; }}
.market-cap {{ color: #aaa; font-size: 14px; }}
.metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 20px; }}
.metric-card {{ background: rgba(255,255,255,0.05); border-radius: 12px; padding: 16px; }}
.metric-title {{ font-size: 15px; font-weight: bold; color: #90CAF9; margin-bottom: 12px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 8px; }}
.metric-item {{ display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.03); }}
.metric-label {{ color: #aaa; font-size: 14px; }}
.metric-value {{ font-weight: bold; font-size: 14px; }}
.w52-range {{ margin: 16px 0; padding: 12px 16px; background: rgba(255,255,255,0.03); border-radius: 8px; }}
.w52-label {{ display: flex; justify-content: space-between; font-size: 12px; color: #aaa; margin-bottom: 6px; }}
.w52-bar {{ position: relative; height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; }}
.w52-fill {{ height: 100%; background: linear-gradient(90deg, #4CAF50, #FFC107, #F44336); border-radius: 4px; }}
.w52-dot {{ position: absolute; top: -4px; width: 16px; height: 16px; background: #fff; border: 3px solid #1976D2; border-radius: 50%; transform: translateX(-50%); }}
.charts-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }}
.chart-box {{ background: rgba(255,255,255,0.03); border-radius: 12px; padding: 16px; }}
canvas {{ max-height: 280px; }}
@media (max-width: 768px) {{ .charts-row {{ grid-template-columns: 1fr; }} .card-header {{ flex-direction: column; }} }}
</style>
</head>
<body>
<h1>📊 종목 대시보드</h1>
<p class="subtitle">{now}</p>
{cards_html}
<script>
Chart.defaults.color = '#aaa';
Chart.defaults.borderColor = 'rgba(255,255,255,0.06)';
{charts_js}
</script>
</body>
</html>"""


def main():
    if not HAS_YF:
        print("yfinance가 필요합니다: pip install yfinance")
        return

    tickers = sys.argv[1:] if len(sys.argv) > 1 else ["PLTR"]
    print(f"종목: {', '.join(tickers)}")

    stocks = []
    for t in tickers:
        print(f"[INFO] {t} 데이터 조회 중...")
        data = fetch_data(t)
        if data:
            stocks.append(data)

    if not stocks:
        print("[ERROR] 데이터를 가져올 수 없습니다.")
        return

    html = generate_html(stocks)
    out_path = "/workspace/dashboard.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n[INFO] 대시보드 생성 완료: {out_path}")
    print(f"[INFO] 브라우저에서 열어보세요!")


if __name__ == "__main__":
    main()
