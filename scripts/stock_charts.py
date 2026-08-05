#!/usr/bin/env python3
"""
종목별 1개월 주가·시총·PER·PBR 차트를 생성하는 모듈.

yfinance로 데이터를 가져오고 matplotlib로 차트를 그린다.
GitHub Issue에 삽입할 수 있도록 이미지 파일로 저장.
"""

import os
import sys
from datetime import datetime, timedelta

try:
    import yfinance as yf
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    import matplotlib.dates as mdates
    import matplotlib.ticker as mticker
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


def _setup_korean_font() -> None:
    """한글 폰트를 설정한다."""
    korean_fonts = [f.name for f in fm.fontManager.ttflist if "Nanum" in f.name]
    if korean_fonts:
        plt.rcParams["font.family"] = korean_fonts[0]
    plt.rcParams["axes.unicode_minus"] = False


def fetch_stock_data(ticker: str, period: str = "1mo") -> dict | None:
    """yfinance에서 종목 데이터를 가져온다."""
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
        }
    except Exception as exc:
        print(f"[WARN] {ticker} 데이터 가져오기 실패: {exc}", file=sys.stderr)
        return None


def _format_large_number(num: float | None) -> str:
    """큰 숫자를 읽기 쉽게 포맷."""
    if num is None:
        return "N/A"
    if num >= 1e12:
        return f"${num / 1e12:.2f}T"
    if num >= 1e9:
        return f"${num / 1e9:.2f}B"
    if num >= 1e6:
        return f"${num / 1e6:.2f}M"
    return f"${num:,.0f}"


def _format_ratio(val: float | None) -> str:
    if val is None:
        return "N/A"
    return f"{val:.2f}"


def generate_stock_chart(
    data: dict,
    name_kr: str,
    output_dir: str,
) -> str | None:
    """개별 종목 차트를 생성하고 파일 경로를 반환한다."""
    if not HAS_DEPS:
        return None

    _setup_korean_font()

    ticker = data["ticker"]
    hist = data["history"]
    name_en = data["name"]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f"{name_kr} ({ticker}) - 1개월 분석", fontsize=16, fontweight="bold")

    # --- 1. 주가 차트 ---
    ax1 = axes[0][0]
    ax1.plot(hist.index, hist["Close"], color="#2196F3", linewidth=2)
    ax1.fill_between(hist.index, hist["Close"], alpha=0.1, color="#2196F3")
    ax1.set_title("주가 추이", fontsize=12)
    ax1.set_ylabel(f"가격 ({data['currency']})")
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))

    if len(hist) >= 2:
        start_price = hist["Close"].iloc[0]
        end_price = hist["Close"].iloc[-1]
        change_pct = ((end_price - start_price) / start_price) * 100
        color = "#4CAF50" if change_pct >= 0 else "#F44336"
        ax1.annotate(
            f"{change_pct:+.1f}%",
            xy=(hist.index[-1], end_price),
            fontsize=14, fontweight="bold", color=color,
            xytext=(10, 10), textcoords="offset points",
        )

    # --- 2. 거래량 차트 ---
    ax2 = axes[0][1]
    colors = ["#4CAF50" if hist["Close"].iloc[i] >= hist["Open"].iloc[i] else "#F44336"
              for i in range(len(hist))]
    ax2.bar(hist.index, hist["Volume"], color=colors, alpha=0.7)
    ax2.set_title("거래량", fontsize=12)
    ax2.set_ylabel("거래량")
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x/1e6:.1f}M"))

    # --- 3. 핵심 지표 테이블 ---
    ax3 = axes[1][0]
    ax3.axis("off")

    market_cap = _format_large_number(data["market_cap"])
    pe = _format_ratio(data["pe_ratio"])
    pb = _format_ratio(data["pb_ratio"])
    price = f"${data['current_price']:.2f}" if data["current_price"] else "N/A"

    if len(hist) >= 2:
        high_1m = f"${hist['High'].max():.2f}"
        low_1m = f"${hist['Low'].min():.2f}"
        avg_vol = f"{hist['Volume'].mean()/1e6:.1f}M"
    else:
        high_1m = low_1m = avg_vol = "N/A"

    table_data = [
        ["현재가", price],
        ["시가총액", market_cap],
        ["PER", pe],
        ["PBR", pb],
        ["1개월 최고", high_1m],
        ["1개월 최저", low_1m],
        ["평균 거래량", avg_vol],
        ["섹터", data["sector"] or "N/A"],
    ]

    table = ax3.table(
        cellText=table_data,
        colLabels=["지표", "값"],
        cellLoc="center",
        loc="center",
        colWidths=[0.4, 0.4],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1, 1.8)
    for key, cell in table.get_celld().items():
        if key[0] == 0:
            cell.set_facecolor("#1976D2")
            cell.set_text_props(color="white", fontweight="bold")
        elif key[0] % 2 == 0:
            cell.set_facecolor("#E3F2FD")
        cell.set_edgecolor("#BBDEFB")
    ax3.set_title("핵심 투자 지표", fontsize=12, pad=20)

    # --- 4. 일간 수익률 분포 ---
    ax4 = axes[1][1]
    if len(hist) >= 2:
        returns = hist["Close"].pct_change().dropna() * 100
        color_hist = "#4CAF50" if returns.mean() >= 0 else "#F44336"
        ax4.hist(returns, bins=15, color=color_hist, alpha=0.7, edgecolor="white")
        ax4.axvline(x=0, color="black", linewidth=1, linestyle="--")
        ax4.axvline(x=returns.mean(), color="#FF9800", linewidth=2, linestyle="-",
                    label=f"평균: {returns.mean():.2f}%")
        ax4.set_title("일간 수익률 분포", fontsize=12)
        ax4.set_xlabel("수익률 (%)")
        ax4.set_ylabel("빈도")
        ax4.legend()
    else:
        ax4.text(0.5, 0.5, "데이터 부족", ha="center", va="center", fontsize=14)
        ax4.set_title("일간 수익률 분포", fontsize=12)
    ax4.grid(True, alpha=0.3)

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
    """여러 종목의 차트를 생성하고 결과를 반환한다."""
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

        chart_path = generate_stock_chart(data, name_kr, output_dir)
        if chart_path:
            results.append({
                "ticker": ticker,
                "name": name_kr,
                "chart_path": chart_path,
                "market_cap": _format_large_number(data["market_cap"]),
                "pe_ratio": _format_ratio(data["pe_ratio"]),
                "pb_ratio": _format_ratio(data["pb_ratio"]),
                "current_price": data["current_price"],
            })

    return results


if __name__ == "__main__":
    test_tickers = ["NVDA", "AMD", "TSLA"]
    test_names = {"NVDA": "엔비디아", "AMD": "AMD", "TSLA": "테슬라"}
    results = generate_charts_for_tickers(test_tickers, test_names, "charts")
    for r in results:
        print(f"{r['name']}: {r['chart_path']}")
