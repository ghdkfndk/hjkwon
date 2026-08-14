#!/usr/bin/env python3
"""
종목별 1개월 주가 차트 + 자동 투자 스코어를 생성하는 모듈.

yfinance로 데이터를 가져오고 matplotlib로 차트를 그린다.
"""
from __future__ import annotations

import os
import sys
import math
from datetime import datetime, timedelta

try:
    import yfinance as yf
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    import matplotlib.dates as mdates
    import matplotlib.patches as patches
    import numpy as np
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


def _setup_korean_font() -> None:
    korean_fonts = [f.name for f in fm.fontManager.ttflist if "Nanum" in f.name]
    if korean_fonts:
        plt.rcParams["font.family"] = korean_fonts[0]
    plt.rcParams["axes.unicode_minus"] = False


def fetch_stock_data(ticker: str, period: str = "1mo") -> dict | None:
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)
        if hist.empty:
            print(f"[WARN] {ticker}: 데이터 없음", file=sys.stderr)
            return None

        info = stock.info or {}

        return {
            "ticker": ticker,
            "history": hist,
            "name": info.get("shortName", ticker),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE") or info.get("forwardPE"),
            "pb_ratio": info.get("priceToBook"),
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "currency": info.get("currency", "USD"),
            "sector": info.get("sector", ""),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
            "dividend_yield": info.get("dividendYield"),
            "beta": info.get("beta"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "forward_pe": info.get("forwardPE"),
            "peg_ratio": info.get("pegRatio"),
            "profit_margin": info.get("profitMargins"),
            "industry": info.get("industry", ""),
        }
    except Exception as exc:
        print(f"[WARN] {ticker} 데이터 가져오기 실패: {exc}", file=sys.stderr)
        return None


def _format_large_number(num: float | None) -> str:
    if num is None:
        return "N/A"
    if num >= 1e12:
        return f"${num / 1e12:.2f}T"
    if num >= 1e9:
        return f"${num / 1e9:.1f}B"
    if num >= 1e6:
        return f"${num / 1e6:.1f}M"
    return f"${num:,.0f}"


def _format_ratio(val: float | None) -> str:
    if val is None:
        return "N/A"
    return f"{val:.2f}"


# ---------------------------------------------------------------------------
# 투자 스코어 계산
# ---------------------------------------------------------------------------

def _pe_base_score(pe: float) -> int:
    if pe < 0:
        return 0
    elif pe < 15:
        return 25
    elif pe < 25:
        return 20
    elif pe < 40:
        return 15
    elif pe < 80:
        return 10
    else:
        return 5


def _analyze_valuation_context(
    pe: float | None,
    rev_growth: float | None,
    earn_growth: float | None,
    peg: float | None,
    forward_pe: float | None,
) -> str:
    """PER과 성장률을 종합하여 한 줄 평가를 생성한다."""
    if pe is None:
        return "PER: N/A"

    parts = []

    if pe < 0:
        return f"PER: {pe:.1f} (적자 — 수익성 확보 필요)"
    elif pe < 15:
        label = "저평가"
    elif pe < 25:
        label = "적정"
    elif pe < 40:
        label = "고평가"
    else:
        label = "매우 고평가"

    parts.append(f"PER {pe:.1f}")

    if pe > 25 and rev_growth is not None and rev_growth > 0.2:
        growth_pct = rev_growth * 100
        if rev_growth > 0.5:
            parts.append(f"매출 +{growth_pct:.0f}% 고성장으로 프리미엄 정당화 가능")
            label = "고평가(성장 반영)"
        elif rev_growth > 0.3:
            parts.append(f"매출 +{growth_pct:.0f}% 성장 중 — 일부 프리미엄 합리적")
            label = "고평가(성장 반영)"
        else:
            parts.append(f"매출 +{growth_pct:.0f}% 성장 중")
    elif pe > 40 and (rev_growth is None or rev_growth < 0.1):
        parts.append("성장률 대비 높은 밸류에이션 주의")

    if peg is not None:
        if 0 < peg < 1:
            parts.append(f"PEG {peg:.2f} — 성장 대비 저평가")
        elif peg < 1.5:
            parts.append(f"PEG {peg:.2f} — 성장 대비 적정")
        elif peg < 3:
            parts.append(f"PEG {peg:.2f} — 성장 대비 고평가")
        elif peg > 3:
            parts.append(f"PEG {peg:.2f} — 성장 대비 과열")

    if forward_pe is not None and pe > 30:
        if forward_pe < pe * 0.7:
            parts.append(f"예상 PER {forward_pe:.1f} — 이익 개선 기대")
        elif forward_pe < pe * 0.9:
            parts.append(f"예상 PER {forward_pe:.1f}")

    if earn_growth is not None and earn_growth > 0.3:
        parts.append(f"이익 +{earn_growth*100:.0f}% 성장")

    return f"{label}: " + "\n  - ".join(parts)


def calculate_investment_score(data: dict) -> dict:
    """다양한 지표를 종합하여 0~100 투자 스코어를 산출한다."""
    scores = {}
    details = []

    hist = data["history"]
    if len(hist) < 2:
        return {"total": 50, "grade": "C", "details": ["데이터 부족"], "scores": {}}

    # 1. 모멘텀 점수 (1개월 수익률 기반, 25점)
    start_price = hist["Close"].iloc[0]
    end_price = hist["Close"].iloc[-1]
    monthly_return = ((end_price - start_price) / start_price) * 100

    if monthly_return > 15:
        momentum = 25
    elif monthly_return > 5:
        momentum = 20
    elif monthly_return > 0:
        momentum = 15
    elif monthly_return > -5:
        momentum = 10
    elif monthly_return > -15:
        momentum = 5
    else:
        momentum = 0
    scores["모멘텀"] = momentum
    details.append(f"1개월 수익률: {monthly_return:+.1f}%")

    # 2. 밸류에이션 점수 (PER + 성장률 종합, 25점)
    pe = data.get("pe_ratio")
    rev_growth = data.get("revenue_growth")
    earn_growth = data.get("earnings_growth")
    peg = data.get("peg_ratio")
    forward_pe = data.get("forward_pe")

    growth_context = _analyze_valuation_context(pe, rev_growth, earn_growth, peg, forward_pe)

    if pe is not None:
        base_val = _pe_base_score(pe)

        growth_bonus = 0
        if rev_growth is not None and rev_growth > 0.3:
            growth_bonus += 5
        if earn_growth is not None and earn_growth > 0.2:
            growth_bonus += 3
        if peg is not None and 0 < peg < 1.5:
            growth_bonus += 4
        if forward_pe is not None and pe > 40 and forward_pe < pe * 0.7:
            growth_bonus += 3

        valuation = min(25, base_val + growth_bonus)
        details.append(growth_context)
    else:
        valuation = 12
        details.append("PER: N/A")
    scores["밸류에이션"] = valuation

    # 3. 안정성 점수 (변동성 기반, 25점)
    returns = hist["Close"].pct_change().dropna()
    volatility = returns.std() * 100
    if volatility < 1.5:
        stability = 25
    elif volatility < 2.5:
        stability = 20
    elif volatility < 4.0:
        stability = 15
    elif volatility < 6.0:
        stability = 10
    else:
        stability = 5
    scores["안정성"] = stability
    details.append(f"일간 변동성: {volatility:.2f}%")

    # 4. 52주 위치 점수 (25점)
    high_52 = data.get("52w_high")
    low_52 = data.get("52w_low")
    current = data.get("current_price") or end_price
    if high_52 and low_52 and high_52 != low_52:
        position = (current - low_52) / (high_52 - low_52)
        if position > 0.9:
            pos_score = 10
            details.append(f"52주 위치: 상단 {position*100:.0f}%")
        elif position > 0.7:
            pos_score = 20
            details.append(f"52주 위치: 중상단 {position*100:.0f}%")
        elif position > 0.4:
            pos_score = 25
            details.append(f"52주 위치: 중간 {position*100:.0f}%")
        elif position > 0.2:
            pos_score = 20
            details.append(f"52주 위치: 중하단 {position*100:.0f}%")
        else:
            pos_score = 15
            details.append(f"52주 위치: 하단 {position*100:.0f}%")
    else:
        pos_score = 12
        details.append("52주 위치: N/A")
    scores["52주 위치"] = pos_score

    total = sum(scores.values())

    if total >= 80:
        grade = "A"
    elif total >= 65:
        grade = "B"
    elif total >= 50:
        grade = "C"
    elif total >= 35:
        grade = "D"
    else:
        grade = "F"

    return {
        "total": total,
        "grade": grade,
        "details": details,
        "scores": scores,
    }


def _draw_score_gauge(ax, score: int, grade: str) -> None:
    """반원형 게이지로 투자 스코어를 표시한다."""
    ax.set_xlim(-1.3, 1.3)
    ax.set_ylim(-0.3, 1.3)
    ax.set_aspect("equal")
    ax.axis("off")

    colors = ["#F44336", "#FF9800", "#FFC107", "#8BC34A", "#4CAF50"]
    boundaries = [0, 20, 40, 60, 80, 100]

    for i in range(5):
        start_angle = 180 - (boundaries[i] / 100 * 180)
        end_angle = 180 - (boundaries[i + 1] / 100 * 180)
        theta1 = math.radians(end_angle)
        theta2 = math.radians(start_angle)
        n_pts = 30
        angles = [theta1 + (theta2 - theta1) * j / n_pts for j in range(n_pts + 1)]
        outer_x = [1.0 * math.cos(a) for a in angles]
        outer_y = [1.0 * math.sin(a) for a in angles]
        inner_x = [0.65 * math.cos(a) for a in reversed(angles)]
        inner_y = [0.65 * math.sin(a) for a in reversed(angles)]
        xs = outer_x + inner_x
        ys = outer_y + inner_y
        ax.fill(xs, ys, color=colors[i], alpha=0.8)

    needle_angle = math.radians(180 - (score / 100 * 180))
    nx = 0.9 * math.cos(needle_angle)
    ny = 0.9 * math.sin(needle_angle)
    ax.annotate("", xy=(nx, ny), xytext=(0, 0),
                arrowprops=dict(arrowstyle="-|>", color="#333333", lw=2.5))
    ax.add_patch(plt.Circle((0, 0), 0.08, color="#333333", zorder=5))

    grade_colors = {"A": "#4CAF50", "B": "#8BC34A", "C": "#FFC107", "D": "#FF9800", "F": "#F44336"}
    ax.text(0, 0.45, f"{score}", ha="center", va="center",
            fontsize=36, fontweight="bold", color=grade_colors.get(grade, "#333"))
    ax.text(0, 0.2, f"등급: {grade}", ha="center", va="center",
            fontsize=16, fontweight="bold", color=grade_colors.get(grade, "#333"))

    ax.text(-1.1, -0.15, "0", ha="center", fontsize=10, color="#999")
    ax.text(1.1, -0.15, "100", ha="center", fontsize=10, color="#999")
    ax.text(0, 1.15, "50", ha="center", fontsize=10, color="#999")


def generate_stock_chart(
    data: dict,
    name_kr: str,
    score_data: dict,
    output_dir: str,
) -> str | None:
    if not HAS_DEPS:
        return None

    _setup_korean_font()

    ticker = data["ticker"]
    hist = data["history"]

    fig = plt.figure(figsize=(14, 6))
    gs = fig.add_gridspec(1, 3, width_ratios=[2, 1, 1], wspace=0.3)

    fig.suptitle(f"{name_kr} ({ticker})", fontsize=18, fontweight="bold", y=1.02)

    # --- 1. 주가 차트 (큰 패널) ---
    ax1 = fig.add_subplot(gs[0, 0])

    close_prices = hist["Close"]
    dates = hist.index

    if len(hist) >= 2:
        start_p = close_prices.iloc[0]
        end_p = close_prices.iloc[-1]
        change = ((end_p - start_p) / start_p) * 100
        line_color = "#4CAF50" if change >= 0 else "#F44336"
        fill_color = "#E8F5E9" if change >= 0 else "#FFEBEE"
    else:
        line_color = "#2196F3"
        fill_color = "#E3F2FD"
        change = 0

    ax1.plot(dates, close_prices, color=line_color, linewidth=2.5)
    ax1.fill_between(dates, close_prices, alpha=0.3, color=fill_color)

    if len(hist) >= 5:
        ma5 = close_prices.rolling(5).mean()
        ax1.plot(dates, ma5, color="#FF9800", linewidth=1, linestyle="--",
                 alpha=0.7, label="5일 이평선")
        ax1.legend(loc="upper left", fontsize=9)

    ax1.set_ylabel(f"주가 ({data['currency']})", fontsize=11)
    ax1.grid(True, alpha=0.2)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax1.tick_params(axis="x", rotation=45)

    change_str = f"{change:+.1f}%"
    ax1.set_title(f"1개월 주가 추이  ({change_str})", fontsize=13,
                  color=line_color, fontweight="bold")

    price_min = close_prices.min()
    price_max = close_prices.max()
    margin = (price_max - price_min) * 0.1 or 1
    ax1.set_ylim(price_min - margin, price_max + margin)

    # --- 2. 핵심 지표 테이블 ---
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.axis("off")

    market_cap = _format_large_number(data["market_cap"])
    price = f"${data['current_price']:.2f}" if data["current_price"] else "N/A"
    high_1m = f"${hist['High'].max():.2f}" if len(hist) >= 1 else "N/A"
    low_1m = f"${hist['Low'].min():.2f}" if len(hist) >= 1 else "N/A"

    pe = data.get("pe_ratio")
    if pe is not None:
        if pe < 0:
            pe_str = f"{pe:.1f} (적자)"
        elif pe < 15:
            pe_str = f"{pe:.1f} (저평가)"
        elif pe < 25:
            pe_str = f"{pe:.1f} (적정)"
        elif pe < 40:
            pe_str = f"{pe:.1f} (고평가)"
        else:
            pe_str = f"{pe:.1f} (매우 고평가)"
    else:
        pe_str = "N/A"

    pb = data.get("pb_ratio")
    if pb is not None:
        if pb < 1:
            pb_str = f"{pb:.2f} (저평가)"
        elif pb < 3:
            pb_str = f"{pb:.2f} (적정)"
        elif pb < 10:
            pb_str = f"{pb:.2f} (고평가)"
        else:
            pb_str = f"{pb:.2f} (매우 고평가)"
    else:
        pb_str = "N/A"

    table_data = [
        ["현재가", price],
        ["시가총액", market_cap],
        ["PER", pe_str],
        ["PBR", pb_str],
        ["1개월 최고", high_1m],
        ["1개월 최저", low_1m],
    ]

    table = ax2.table(
        cellText=table_data,
        colLabels=["지표", "값"],
        cellLoc="center",
        loc="center",
        colWidths=[0.45, 0.45],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1, 2.0)
    for key, cell in table.get_celld().items():
        if key[0] == 0:
            cell.set_facecolor("#1565C0")
            cell.set_text_props(color="white", fontweight="bold")
        elif key[0] % 2 == 0:
            cell.set_facecolor("#E3F2FD")
        else:
            cell.set_facecolor("#FFFFFF")
        cell.set_edgecolor("#BBDEFB")

    ax2.set_title("핵심 지표", fontsize=13, fontweight="bold", pad=15)

    # --- 3. 투자 스코어 게이지 ---
    ax3 = fig.add_subplot(gs[0, 2])
    _draw_score_gauge(ax3, score_data["total"], score_data["grade"])
    ax3.set_title("투자 스코어", fontsize=13, fontweight="bold", pad=15)

    # 스코어 상세 항목
    detail_y = -0.22
    for name, val in score_data["scores"].items():
        bar_width = val / 25 * 0.8
        ax3.barh(detail_y, bar_width, height=0.06, left=-0.4,
                 color="#1565C0", alpha=0.6)
        ax3.text(-0.45, detail_y, name, ha="right", va="center", fontsize=7)
        ax3.text(-0.4 + bar_width + 0.03, detail_y, f"{val}/25",
                 ha="left", va="center", fontsize=7, color="#666")
        detail_y -= 0.10

    plt.tight_layout()

    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"chart_{ticker}.png")
    fig.savefig(filepath, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    print(f"[INFO] 차트 생성: {filepath}")
    return filepath


def generate_charts_for_tickers(
    tickers: list[str],
    ticker_names: dict[str, str],
    output_dir: str = "charts",
) -> list[dict]:
    if not HAS_DEPS:
        print("[WARN] yfinance 또는 matplotlib가 설치되어 있지 않습니다.", file=sys.stderr)
        return []

    results = []
    for ticker in tickers:
        name_kr = ticker_names.get(ticker, ticker)
        print(f"[INFO] {name_kr}({ticker}) 데이터 조회 중...")

        data = fetch_stock_data(ticker)
        if data is None:
            continue

        score_data = calculate_investment_score(data)
        chart_path = generate_stock_chart(data, name_kr, score_data, output_dir)
        if chart_path:
            results.append({
                "ticker": ticker,
                "name": name_kr,
                "chart_path": chart_path,
                "market_cap": _format_large_number(data["market_cap"]),
                "pe_ratio": _format_ratio(data["pe_ratio"]),
                "pb_ratio": _format_ratio(data["pb_ratio"]),
                "current_price": data["current_price"],
                "score": score_data["total"],
                "grade": score_data["grade"],
                "score_details": score_data["details"],
                "score_breakdown": score_data["scores"],
                "revenue_growth": data.get("revenue_growth"),
                "earnings_growth": data.get("earnings_growth"),
                "peg_ratio": data.get("peg_ratio"),
                "forward_pe": data.get("forward_pe"),
            })

    return results


if __name__ == "__main__":
    test_tickers = ["NVDA", "AMD", "TSLA"]
    test_names = {"NVDA": "엔비디아", "AMD": "AMD", "TSLA": "테슬라"}
    results = generate_charts_for_tickers(test_tickers, test_names, "charts")
    for r in results:
        print(f"{r['name']}: 스코어 {r['score']}/100 (등급 {r['grade']})")
