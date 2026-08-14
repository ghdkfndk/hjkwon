#!/usr/bin/env python3
"""
종목 분석 웹 앱.
티커를 입력하면 실시간으로 주가·PER·실적 차트를 보여준다.

실행: python app.py
접속: http://localhost:5001
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify, render_template_string

try:
    import yfinance as yf
except ImportError:
    print("yfinance 필요: pip install yfinance")
    sys.exit(1)

app = Flask(__name__)
KST = timezone(timedelta(hours=9))

POPULAR_US = [
    ("NVDA", "엔비디아"), ("AAPL", "애플"), ("MSFT", "마이크로소프트"),
    ("GOOGL", "구글"), ("AMZN", "아마존"), ("META", "메타"),
    ("TSLA", "테슬라"), ("AMD", "AMD"), ("PLTR", "팔란티어"),
    ("AVGO", "브로드컴"), ("NFLX", "넷플릭스"), ("SPCX", "스페이스X"),
]

POPULAR_KR = [
    ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("035420", "네이버"),
    ("035720", "카카오"), ("005380", "현대차"), ("000270", "기아"),
    ("373220", "LG에너지솔루션"), ("068270", "셀트리온"), ("006400", "삼성SDI"),
    ("247540", "에코프로비엠"), ("086520", "에코프로"), ("293490", "카카오게임즈"),
]

KR_NAME_MAP = {code: name for code, name in POPULAR_KR}
KR_NAME_TO_CODE = {name: code for code, name in POPULAR_KR}

SEGMENT_DATA = {
    "PLTR": {
        "name": "Palantir",
        "segments": [
            {"name": "Commercial", "revenue": 945, "growth": "+110% YoY"},
            {"name": "Government", "revenue": 990, "growth": "+79% YoY"},
        ],
        "unit": "$M",
        "period": "Q2 2026",
    },
    "AMZN": {
        "name": "Amazon",
        "segments": [
            {"name": "Online Stores", "revenue": 75600, "growth": "+7% YoY"},
            {"name": "3rd Party Sellers", "revenue": 47500, "growth": "+9% YoY"},
            {"name": "AWS", "revenue": 28800, "growth": "+19% YoY"},
            {"name": "Advertising", "revenue": 17300, "growth": "+18% YoY"},
            {"name": "Subscription", "revenue": 11500, "growth": "+10% YoY"},
            {"name": "Physical Stores", "revenue": 5600, "growth": "+8% YoY"},
        ],
        "unit": "$M",
        "period": "Q4 2024",
    },
    "AAPL": {
        "name": "Apple",
        "segments": [
            {"name": "iPhone", "revenue": 69700, "growth": "+6% YoY"},
            {"name": "Services", "revenue": 26300, "growth": "+14% YoY"},
            {"name": "Mac", "revenue": 9000, "growth": "+15% YoY"},
            {"name": "iPad", "revenue": 8100, "growth": "+15% YoY"},
            {"name": "Wearables/Home", "revenue": 11700, "growth": "+2% YoY"},
        ],
        "unit": "$M",
        "period": "Q1 2025",
    },
    "GOOGL": {
        "name": "Alphabet",
        "segments": [
            {"name": "Search & Other", "revenue": 54700, "growth": "+12% YoY"},
            {"name": "YouTube Ads", "revenue": 10500, "growth": "+14% YoY"},
            {"name": "Google Cloud", "revenue": 12000, "growth": "+30% YoY"},
            {"name": "Network", "revenue": 8300, "growth": "+5% YoY"},
            {"name": "Other Bets", "revenue": 400, "growth": ""},
        ],
        "unit": "$M",
        "period": "Q4 2024",
    },
    "MSFT": {
        "name": "Microsoft",
        "segments": [
            {"name": "Intelligent Cloud (Azure)", "revenue": 25500, "growth": "+21% YoY"},
            {"name": "Productivity (Office/LinkedIn)", "revenue": 22400, "growth": "+14% YoY"},
            {"name": "Personal Computing (Windows/Xbox)", "revenue": 16900, "growth": "+17% YoY"},
        ],
        "unit": "$M",
        "period": "Q2 2025",
    },
    "META": {
        "name": "Meta",
        "segments": [
            {"name": "Family of Apps (광고)", "revenue": 46700, "growth": "+21% YoY"},
            {"name": "Reality Labs (VR/AR)", "revenue": 1100, "growth": "-12% YoY"},
        ],
        "unit": "$M",
        "period": "Q4 2024",
    },
    "NVDA": {
        "name": "NVIDIA",
        "segments": [
            {"name": "Data Center", "revenue": 35100, "growth": "+93% YoY"},
            {"name": "Gaming", "revenue": 3600, "growth": "+9% YoY"},
            {"name": "Automotive", "revenue": 570, "growth": "+55% YoY"},
            {"name": "Professional Visualization", "revenue": 490, "growth": "+10% YoY"},
        ],
        "unit": "$M",
        "period": "Q3 2025",
    },
    "TSLA": {
        "name": "Tesla",
        "segments": [
            {"name": "Automotive Sales", "revenue": 20000, "growth": "-6% YoY"},
            {"name": "Energy & Storage", "revenue": 2400, "growth": "+52% YoY"},
            {"name": "Services & Other", "revenue": 2800, "growth": "+13% YoY"},
        ],
        "unit": "$M",
        "period": "Q3 2024",
    },
}


def _search_yahoo(query: str, prefer_kr: bool = False) -> str | None:
    """Yahoo Finance autocomplete로 티커를 검색한다."""
    from urllib.request import urlopen, Request
    from urllib.parse import quote
    try:
        url = f"https://query1.finance.yahoo.com/v6/finance/autocomplete?query={quote(query)}&lang=en"
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
            results = data.get("ResultSet", {}).get("Result", [])
            if not results:
                return None
            if prefer_kr:
                for r in results:
                    sym = r["symbol"]
                    if sym.endswith((".KS", ".KQ")):
                        return sym
            return results[0]["symbol"]
    except Exception:
        pass
    return None


def _translate_to_english(text: str) -> str:
    """한글을 영어로 번역 (Yahoo 검색용)."""
    from urllib.request import urlopen, Request
    from urllib.parse import quote
    try:
        url = (
            "https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl=ko&tl=en&dt=t&q={quote(text)}"
        )
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return "".join(part[0] for part in data[0] if part[0]).strip()
    except Exception:
        return text


def _has_korean(text: str) -> bool:
    import re
    return bool(re.search(r"[가-힣]", text))


def resolve_ticker(raw: str) -> str:
    """입력값을 Yahoo Finance 티커로 변환한다.
    - 숫자 6자리 → 한국 주식 (.KS 시도 후 .KQ 폴백)
    - 한글 → 사전 매핑 → 영문 번역 → Yahoo 검색
    - 그 외 → Yahoo 검색 또는 그대로
    """
    raw = raw.strip()
    if raw.endswith((".KS", ".KQ")):
        return raw

    if raw.isdigit() and len(raw) == 6:
        for suffix in (".KS", ".KQ"):
            candidate = raw + suffix
            try:
                stock = yf.Ticker(candidate)
                info = stock.info or {}
                name = info.get("shortName", "")
                if name and "," not in name and len(name) < 50:
                    hist = stock.history(period="5d")
                    if not hist.empty:
                        return candidate
            except Exception:
                pass
        return raw + ".KS"

    if _has_korean(raw):
        if raw in KR_NAME_TO_CODE:
            code = KR_NAME_TO_CODE[raw]
            return resolve_ticker(code)

        en_name = _translate_to_english(raw)
        print(f"[INFO] '{raw}' → 영문 변환: '{en_name}'")
        result = _search_yahoo(en_name, prefer_kr=True)
        if result:
            print(f"[INFO] Yahoo 검색 결과: {result}")
            return result

        romanized = _transliterate_korean(raw)
        if romanized != en_name:
            print(f"[INFO] 로마자 변환 시도: '{romanized}'")
            result = _search_yahoo(romanized, prefer_kr=True)
            if result:
                print(f"[INFO] Yahoo 검색 결과: {result}")
                return result

        # 변형 검색 시도 (공백 제거, 소문자 등)
        variants = set()
        variants.add(en_name.replace(" ", ""))
        variants.add(en_name.lower().replace(" ", ""))
        variants.add(en_name.lower())
        # 단어 앞 3~4글자로 부분 검색
        first_word = en_name.split()[0] if en_name.split() else ""
        if len(first_word) >= 3:
            variants.add(first_word.lower())
        variants.discard(en_name)
        for variant in variants:
            result = _search_yahoo(variant, prefer_kr=True)
            if result:
                print(f"[INFO] Yahoo 검색 결과 (변형 '{variant}'): {result}")
                return result

    result = _search_yahoo(raw)
    if result:
        return result

    return raw


def _transliterate_korean(text: str) -> str:
    """한글을 로마자(발음)로 변환 (Google Translate 활용)."""
    from urllib.request import urlopen, Request
    from urllib.parse import quote
    try:
        url = (
            "https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl=ko&tl=en&dt=rm&q={quote(text)}"
        )
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            if len(data) > 3 and data[3]:
                return data[3]
    except Exception:
        pass
    return text


def get_display_name(ticker: str, info: dict) -> str:
    """한국 주식은 한글 이름을, 미국 주식은 영문 이름을 반환."""
    code = ticker.replace(".KS", "").replace(".KQ", "")
    if code in KR_NAME_MAP:
        return KR_NAME_MAP[code]
    return info.get("shortName", ticker)


def get_currency_symbol(currency: str) -> str:
    if currency == "KRW":
        return "₩"
    return "$"


def format_price(price, currency: str) -> str:
    if price is None:
        return "N/A"
    sym = get_currency_symbol(currency)
    if currency == "KRW":
        return f"{sym}{price:,.0f}"
    return f"{sym}{price:.2f}"

HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>종목 분석기</title>
<link rel="preconnect" href="https://cdn.jsdelivr.net"/>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css"/>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3"></script>
<style>
:root {
  --bg:#07080f; --text:#e8ecf4; --muted:#8b95a8; --faint:#64708a;
  --card:rgba(255,255,255,0.045); --card-2:rgba(255,255,255,0.06);
  --stroke:rgba(255,255,255,0.09); --stroke-2:rgba(255,255,255,0.14);
  --accent:#6ea8ff; --accent-2:#7dd3fc; --up:#34d399; --down:#f87171;
  --shadow:0 18px 50px rgba(0,0,0,0.35);
}
* { margin:0; padding:0; box-sizing:border-box; }
html { color-scheme: dark; }
body {
  font-family: Pretendard, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg); color: var(--text); min-height: 100vh; letter-spacing: -0.01em;
}
body::before {
  content:''; position:fixed; inset:0; pointer-events:none; z-index:0;
  background:
    radial-gradient(ellipse 70% 45% at 8% -8%, rgba(110,168,255,0.22), transparent 55%),
    radial-gradient(ellipse 50% 35% at 92% 0%, rgba(125,211,252,0.10), transparent 50%),
    radial-gradient(ellipse 55% 30% at 50% 110%, rgba(52,211,153,0.07), transparent 50%);
}
::selection { background: rgba(110,168,255,0.35); }
::-webkit-scrollbar { width:10px; height:10px; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.14); border-radius:99px; }
.page { position:relative; z-index:1; }

.top-bar {
  position:sticky; top:0; z-index:100; padding:16px 24px 14px;
  background: rgba(7,8,15,0.72); backdrop-filter: blur(18px) saturate(1.3);
  border-bottom: 1px solid var(--stroke);
}
.brand-row { display:flex; align-items:center; justify-content:space-between; gap:18px; flex-wrap:wrap; max-width:1120px; margin:0 auto; }
.brand { display:flex; align-items:center; gap:12px; }
.logo {
  width:42px; height:42px; border-radius:12px; display:grid; place-items:center; font-size:20px;
  background: linear-gradient(135deg, #4f8cff, #67e8f9); box-shadow: 0 8px 20px rgba(79,140,255,0.28);
}
.brand h1 { font-size:18px; font-weight:720; color:#fff; letter-spacing:-0.03em; }
.tagline { font-size:12px; color:var(--muted); margin-top:2px; }
.search-box { display:flex; gap:8px; flex:1; min-width:260px; max-width:520px; }
.search-box input {
  flex:1; padding:11px 16px; border-radius:14px; border:1px solid var(--stroke-2);
  background: rgba(255,255,255,0.06); color:#fff; font-size:15px; outline:none; font-family:inherit;
}
.search-box input::placeholder { color:var(--faint); }
.search-box input:focus { border-color: rgba(110,168,255,0.7); box-shadow: 0 0 0 4px rgba(110,168,255,0.16); }
.search-box button {
  padding:11px 20px; border-radius:14px; border:none; cursor:pointer; font-family:inherit;
  background: linear-gradient(135deg,#4f8cff,#3b6fe0); color:#fff; font-size:14px; font-weight:700;
  box-shadow: 0 8px 18px rgba(79,140,255,0.25); transition: transform .15s ease, filter .15s ease;
}
.search-box button:hover { filter:brightness(1.08); transform: translateY(-1px); }
.search-box button:disabled { opacity:0.5; cursor:not-allowed; transform:none; }

.market-row { max-width:1120px; margin:12px auto 0; display:flex; align-items:center; gap:8px; }
.tab-btn {
  padding:6px 14px; border-radius:999px; border:1px solid var(--stroke-2);
  background: rgba(255,255,255,0.04); color:var(--muted); font-size:13px; cursor:pointer; font-family:inherit;
  transition: all .15s ease;
}
.tab-btn:hover { color:#fff; border-color: rgba(110,168,255,0.4); }
.tab-btn.active { background: rgba(110,168,255,0.18); border-color: rgba(110,168,255,0.55); color:#fff; font-weight:650; }
.quick-tags { max-width:1120px; margin:10px auto 0; display:flex; flex-wrap:wrap; gap:6px; }
.quick-tag {
  padding:5px 11px; border-radius:999px; border:1px solid var(--stroke);
  background: rgba(255,255,255,0.04); color:#b7c0d0; font-size:12px; cursor:pointer; transition: all .15s ease;
}
.quick-tag:hover { background: rgba(110,168,255,0.18); border-color: rgba(110,168,255,0.5); color:#fff; transform: translateY(-1px); }

.container { max-width:1120px; margin:0 auto; padding:28px 20px 64px; }

.empty-state { text-align:center; padding:72px 16px 40px; }
.empty-icon {
  width:72px; height:72px; margin:0 auto 18px; border-radius:22px; display:grid; place-items:center; font-size:32px;
  background: linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.03));
  border:1px solid var(--stroke); box-shadow: var(--shadow);
}
.empty-state h2 { font-size:24px; color:#fff; font-weight:720; letter-spacing:-0.03em; }
.empty-state p { color:var(--muted); margin-top:8px; font-size:15px; }
.empty-hints { display:flex; justify-content:center; gap:8px; margin-top:22px; flex-wrap:wrap; }
.empty-hints span {
  padding:8px 14px; border-radius:12px; border:1px dashed var(--stroke-2); color:#c5cde0;
  background: rgba(255,255,255,0.03); font-size:13px; cursor:pointer;
}
.empty-hints span:hover { border-style:solid; border-color: var(--accent); color:#fff; }

.loading { text-align:center; padding:80px 16px; color:var(--muted); }
.loading .spinner {
  width:42px; height:42px; border:3px solid rgba(255,255,255,0.1); border-top-color: var(--accent);
  border-radius:50%; animation:spin .8s linear infinite; margin:0 auto 16px;
}
@keyframes spin { to { transform:rotate(360deg); } }
.error-msg { text-align:center; padding:48px 16px; color:#f87171; font-size:16px; background:rgba(248,113,113,0.08); border:1px solid rgba(248,113,113,0.2); border-radius:16px; }

.stock-card {
  background: var(--card); backdrop-filter: blur(16px);
  border:1px solid var(--stroke); border-radius:22px; padding:28px; margin-bottom:24px;
  box-shadow: var(--shadow); animation: fadeIn .45s ease;
}
@keyframes fadeIn { from { opacity:0; transform:translateY(16px); } to { opacity:1; transform:none; } }

.card-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:22px; flex-wrap:wrap; gap:16px; }
.name-row { display:flex; align-items:center; gap:14px; }
.ticker-avatar {
  width:50px; height:50px; border-radius:16px; display:grid; place-items:center;
  font-weight:800; font-size:18px; color:#fff; letter-spacing:-0.04em;
  background: linear-gradient(135deg, rgba(110,168,255,0.45), rgba(125,211,252,0.12));
  border:1px solid rgba(255,255,255,0.14);
}
.card-header h2 { color:#fff; font-size:24px; font-weight:750; letter-spacing:-0.03em; }
.ticker-badge {
  display:inline-block; background: rgba(110,168,255,0.2); color:#cfe0ff; padding:2px 9px;
  border-radius:8px; font-size:12px; font-weight:700; margin-right:8px; letter-spacing:.02em;
}
.sector { color:var(--muted); font-size:13px; }
.price-area { text-align:right; }
.big-price { display:block; font-size:34px; font-weight:760; color:#fff; font-variant-numeric: tabular-nums; letter-spacing:-0.04em; }
.price-change { display:inline-block; font-size:13px; padding:4px 10px; border-radius:999px; font-weight:700; margin-top:6px; }
.price-up { background:rgba(52,211,153,0.14); color:var(--up); }
.price-down { background:rgba(248,113,113,0.14); color:var(--down); }
.mcap { color:var(--muted); font-size:13px; margin-top:6px; }

.metrics-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px; margin-bottom:18px; }
.metric-card { background: var(--card-2); border:1px solid var(--stroke); border-radius:16px; padding:16px 18px; }
.metric-title { font-size:13px; font-weight:700; color:var(--accent-2); margin-bottom:10px; padding-bottom:8px; border-bottom:1px solid var(--stroke); }
.metric-row { display:flex; justify-content:space-between; padding:7px 0; border-bottom:1px solid rgba(255,255,255,0.04); }
.metric-row:last-child { border-bottom:none; }
.metric-label { color:var(--muted); font-size:13px; }
.metric-val { font-weight:700; font-size:13px; font-variant-numeric: tabular-nums; }

.score-banner { display:flex; align-items:center; gap:20px; padding:16px 18px; border-radius:18px; margin-bottom:20px; }
.score-banner.A { background:rgba(52,211,153,0.10); border:1px solid rgba(52,211,153,0.28); }
.score-banner.B { background:rgba(110,168,255,0.10); border:1px solid rgba(110,168,255,0.28); }
.score-banner.C { background:rgba(250,204,21,0.10); border:1px solid rgba(250,204,21,0.28); }
.score-banner.D { background:rgba(251,146,60,0.10); border:1px solid rgba(251,146,60,0.28); }
.score-banner.F { background:rgba(248,113,113,0.10); border:1px solid rgba(248,113,113,0.28); }
.score-ring {
  width:88px; height:88px; border-radius:50%; flex-shrink:0;
  background: conic-gradient(var(--ring) calc(var(--pct) * 1%), rgba(255,255,255,0.08) 0);
  display:grid; place-items:center;
}
.score-ring-inner {
  width:68px; height:68px; border-radius:50%; background: rgba(10,12,22,0.92);
  display:grid; place-items:center;
}
.score-num { font-size:22px; font-weight:800; letter-spacing:-0.04em; }
.score-banner.A .score-num, .score-banner.A { --ring:#34d399; } .score-banner.A .score-num { color:#34d399; }
.score-banner.B .score-num, .score-banner.B { --ring:#6ea8ff; } .score-banner.B .score-num { color:#6ea8ff; }
.score-banner.C .score-num, .score-banner.C { --ring:#facc15; } .score-banner.C .score-num { color:#facc15; }
.score-banner.D .score-num, .score-banner.D { --ring:#fb923c; } .score-banner.D .score-num { color:#fb923c; }
.score-banner.F .score-num, .score-banner.F { --ring:#f87171; } .score-banner.F .score-num { color:#f87171; }
.score-detail { flex:1; min-width:0; }
.score-grade { font-size:18px; font-weight:750; color:#fff; }
.score-items { margin-top:6px; font-size:13px; color:#b7c0d0; line-height:1.7; }

.w52 { margin:4px 0 18px; padding:14px 16px; background: rgba(255,255,255,0.03); border:1px solid var(--stroke); border-radius:14px; }
.w52-labels { display:flex; justify-content:space-between; font-size:12px; color:var(--muted); margin-bottom:8px; }
.w52-track { position:relative; height:8px; background:rgba(255,255,255,0.08); border-radius:99px; }
.w52-fill { height:100%; background:linear-gradient(90deg,#34d399,#facc15,#f87171); border-radius:99px; }
.w52-dot { position:absolute; top:-5px; width:18px; height:18px; background:#fff; border:3px solid #6ea8ff; border-radius:50%; transform:translateX(-50%); box-shadow:0 0 0 4px rgba(110,168,255,0.18); }

.charts-grid { display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-bottom:16px; }
.chart-wrap { background: rgba(255,255,255,0.03); border:1px solid var(--stroke); border-radius:16px; padding:16px; }
.section-label { color:var(--accent-2); font-size:13px; font-weight:700; margin-bottom:10px; }

.direction-box { background: rgba(255,255,255,0.035); border:1px solid var(--stroke); border-radius:16px; padding:18px; margin-bottom:16px; }
.direction-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; gap:10px; flex-wrap:wrap; }
.direction-title { font-size:14px; font-weight:700; color:var(--accent-2); }
.outlook-badge { padding:4px 12px; border-radius:999px; font-size:12px; font-weight:700; background: rgba(255,255,255,0.06); border:1px solid var(--stroke); }
.theme-tags { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:8px; }
.theme-tag { padding:4px 10px; border-radius:999px; font-size:12px; background:rgba(52,211,153,0.14); color:#6ee7b7; }
.risk-tag { padding:4px 10px; border-radius:999px; font-size:12px; background:rgba(248,113,113,0.14); color:#fca5a5; }
.subtle { color:var(--muted); font-size:12px; margin-bottom:6px; }

.news-list { margin-top:8px; }
.news-item { padding:12px 10px; border-radius:12px; border-bottom:1px solid rgba(255,255,255,0.05); transition: background .15s ease; }
.news-item:hover { background: rgba(255,255,255,0.04); }
.news-item:last-child { border-bottom:none; }
.news-title { color:#e8ecf4; font-size:14px; text-decoration:none; line-height:1.55; font-weight:550; }
.news-title:hover { color:#93c5fd; }
.news-meta { font-size:11px; color:var(--faint); margin-top:4px; }
.news-summary { font-size:12px; color:var(--muted); margin-top:4px; line-height:1.45; }

.stat-chips { display:flex; gap:10px; margin:12px 0; flex-wrap:wrap; }
.stat-chip { padding:10px 16px; background: rgba(255,255,255,0.04); border:1px solid var(--stroke); border-radius:14px; text-align:center; min-width:110px; }
.stat-chip span { display:block; color:var(--muted); font-size:11px; margin-bottom:4px; }
.stat-chip b { font-size:18px; font-weight:760; letter-spacing:-0.03em; }

.fin-table { width:100%; margin:8px 0 16px; border-collapse:separate; border-spacing:0; font-size:13px; overflow:hidden; border-radius:12px; }
.fin-table th { padding:10px 12px; text-align:left; color:var(--accent-2); font-weight:650; background: rgba(255,255,255,0.04); border-bottom:1px solid var(--stroke); }
.fin-table td { padding:9px 12px; border-bottom:1px solid rgba(255,255,255,0.05); font-variant-numeric: tabular-nums; }
.fin-table tr:hover td { background: rgba(255,255,255,0.03); }
.seg-row { display:flex; align-items:center; padding:6px 0; gap:8px; }
.seg-dot { width:10px; height:10px; border-radius:50%; flex-shrink:0; }

@media(max-width:768px) {
  .charts-grid { grid-template-columns:1fr; }
  .card-header { flex-direction:column; }
  .price-area { text-align:left; }
  .top-bar { padding:14px 16px 12px; }
  .stock-card { padding:18px; border-radius:18px; }
}
</style>
</head>
<body>
<div class="page">
<div class="top-bar">
  <div class="brand-row">
    <div class="brand">
      <div class="logo">📊</div>
      <div>
        <h1>종목 분석기</h1>
        <p class="tagline">실시간 주가 · 밸류에이션 · 실적 한눈에</p>
      </div>
    </div>
    <div class="search-box">
      <input id="tickerInput" placeholder="티커, 종목코드, 한글 이름 (예: PLTR, 삼성전자)" autofocus />
      <button id="searchBtn" onclick="analyze()">분석</button>
    </div>
  </div>
  <div class="market-row">
    <button class="tab-btn active" onclick="showTab('us',this)">🇺🇸 미국</button>
    <button class="tab-btn" onclick="showTab('kr',this)">🇰🇷 한국</button>
  </div>
  <div class="quick-tags" id="usTags"></div>
  <div class="quick-tags" id="krTags" style="display:none"></div>
</div>
<div class="container" id="results">
  <div class="empty-state" id="emptyState">
    <div class="empty-icon">📈</div>
    <h2>종목을 검색해 보세요</h2>
    <p>티커, 6자리 종목코드, 또는 한글 회사명으로 바로 분석합니다.</p>
    <div class="empty-hints">
      <span onclick="quickSearch('NVDA')">NVDA</span>
      <span onclick="quickSearch('PLTR')">PLTR</span>
      <span onclick="quickSearch('005930')">삼성전자</span>
      <span onclick="quickSearch('TSLA')">TSLA</span>
    </div>
  </div>
</div>
</div>

<script>
if (window.Chart) {
  Chart.defaults.color = '#94a3b8';
  Chart.defaults.borderColor = 'rgba(255,255,255,0.08)';
  Chart.defaults.font.family = "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif";
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.title.color = '#e2e8f0';
  Chart.defaults.plugins.title.font = { size: 14, weight: '600' };
  Chart.defaults.elements.line.borderWidth = 2.2;
  Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(8,10,18,0.92)';
  Chart.defaults.plugins.tooltip.padding = 12;
  Chart.defaults.plugins.tooltip.cornerRadius = 10;
}

const POPULAR_US = POPULAR_US_JSON;
const POPULAR_KR = POPULAR_KR_JSON;
const KR_NAME_MAP = Object.fromEntries(POPULAR_KR.map(([c,n])=>[n,c]));

document.getElementById('usTags').innerHTML = POPULAR_US.map(
  ([t,n]) => `<span class="quick-tag" onclick="quickSearch('${t}')">${t} ${n}</span>`
).join('');
document.getElementById('krTags').innerHTML = POPULAR_KR.map(
  ([t,n]) => `<span class="quick-tag" onclick="quickSearch('${t}')">${t} ${n}</span>`
).join('');

function showTab(tab, btn) {
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('usTags').style.display = tab==='us' ? 'flex' : 'none';
  document.getElementById('krTags').style.display = tab==='kr' ? 'flex' : 'none';
}

document.getElementById('tickerInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') analyze();
});

function quickSearch(t) {
  document.getElementById('tickerInput').value = t;
  analyze();
}

async function analyze() {
  const input = document.getElementById('tickerInput').value.trim().toUpperCase();
  if (!input) return;
  const tickers = input.split(/[\\s,]+/).map(t => KR_NAME_MAP[t] || t);
  const results = document.getElementById('results');
  const btn = document.getElementById('searchBtn');
  
  btn.disabled = true;
  btn.textContent = '분석 중...';
  results.innerHTML = '<div class="loading"><div class="spinner"></div><p>데이터를 가져오는 중...</p></div>';
  
  try {
    const resp = await fetch('/api/analyze?tickers=' + tickers.join(','));
    const data = await resp.json();
    if (data.error) {
      results.innerHTML = `<div class="error-msg">❌ ${data.error}</div>`;
      return;
    }
    results.innerHTML = '';
    data.stocks.forEach((s, i) => renderStock(s, i));
  } catch(e) {
    results.innerHTML = `<div class="error-msg">❌ 오류: ${e.message}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = '분석';
  }
}

function fmtCap(v, curr) {
  if (!v) return 'N/A';
  if (curr === 'KRW') {
    if (v >= 1e12) return (v/1e12).toFixed(1) + '조원';
    if (v >= 1e8) return (v/1e8).toFixed(0) + '억원';
    return v.toLocaleString() + '원';
  }
  if (v >= 1e12) return '$' + (v/1e12).toFixed(2) + 'T';
  if (v >= 1e9) return '$' + (v/1e9).toFixed(1) + 'B';
  return '$' + (v/1e6).toFixed(0) + 'M';
}

function peLabel(pe) {
  if (pe == null) return ['N/A','#999'];
  if (pe < 0) return [pe.toFixed(1)+' (적자)','#F44336'];
  if (pe < 15) return [pe.toFixed(1)+' (저평가)','#4CAF50'];
  if (pe < 25) return [pe.toFixed(1)+' (적정)','#2196F3'];
  if (pe < 40) return [pe.toFixed(1)+' (고평가)','#FF9800'];
  return [pe.toFixed(1)+' (매우 고평가)','#F44336'];
}

function renderDirection(s) {
  const d = s.direction;
  if (!d) return '';
  const themes = (d.themes||[]).map(t=>`<span class="theme-tag">📈 ${t}</span>`).join('');
  const risks = (d.risks||[]).map(r=>`<span class="risk-tag">⚠️ ${r}</span>`).join('');
  return `<div class="direction-box">
    <div class="direction-header">
      <span class="direction-title">🔭 기업 방향성 분석</span>
      <span class="outlook-badge" style="color:${d.outlook_color}">${d.outlook} · 뉴스 ${d.news_count}건</span>
    </div>
    ${themes ? '<div class="subtle">핵심 테마</div><div class="theme-tags">'+themes+'</div>' : ''}
    ${risks ? '<div class="subtle" style="margin-top:8px;">리스크 요인</div><div class="theme-tags">'+risks+'</div>' : ''}
  </div>`;
}

function renderNews(s) {
  const news = s.news;
  if (!news || !news.length) return '';
  const items = news.map(n => {
    const link = n.link ? `<a href="${n.link}" target="_blank" class="news-title">${n.title}</a>` : `<span class="news-title">${n.title}</span>`;
    const meta = [n.source, n.date ? new Date(n.date).toLocaleDateString('ko-KR') : ''].filter(Boolean).join(' · ');
    const summary = n.summary ? `<div class="news-summary">${n.summary}</div>` : '';
    return `<div class="news-item">${link}<div class="news-meta">${meta}</div>${summary}</div>`;
  }).join('');
  return `<div class="direction-box">
    <div class="direction-title" style="margin-bottom:12px;">📰 최근 뉴스</div>
    <div class="news-list">${items}</div>
  </div>`;
}

function renderSegmentDonut(s, idx) {
  const seg = s.segments;
  if (!seg) return '';
  
  const total = seg.segments.reduce((sum, s) => sum + s.revenue, 0);
  const unit = seg.unit || '$M';
  const isEstimated = seg.estimated;
  
  if (isEstimated) {
    // 뉴스 추정: 숫자 없이 키워드만
    return `<div style="margin-bottom:16px;">
      <div style="text-align:center;margin-bottom:12px;">
        <p style="color:#90CAF9;font-size:13px;font-weight:bold;">매출원 (뉴스 기반 추정)</p>
        <p style="color:#666;font-size:11px;">${seg.period}</p>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:8px;justify-content:center;">
        ${seg.segments.map((s,i) => {
          const colors = ['#1976D2','#4CAF50','#FF9800','#9C27B0','#F44336','#00BCD4'];
          return `<span style="padding:6px 14px;background:${colors[i%6]}33;border:1px solid ${colors[i%6]};border-radius:16px;color:${colors[i%6]};font-size:13px;">📊 ${s.name}</span>`;
        }).join('')}
      </div>
    </div>`;
  }
  
  return `<div style="margin-bottom:16px;">
    <div style="text-align:center;margin-bottom:12px;">
      <p style="color:#90CAF9;font-size:13px;font-weight:bold;">매출 발생 구조 (${seg.period})</p>
    </div>
    <div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap;">
      <div style="flex:1;min-width:200px;">
        <canvas id="seg_donut_${idx}"></canvas>
      </div>
      <div style="flex:1;min-width:200px;">
        ${seg.segments.map((s,i) => {
          const pct = total > 0 ? (s.revenue / total * 100).toFixed(0) : '?';
          const colors = ['#1976D2','#4CAF50','#FF9800','#9C27B0','#F44336','#00BCD4','#795548','#607D8B'];
          return `<div class="seg-row">
            <span class="seg-dot" style="background:${colors[i%8]}"></span>
            <span style="flex:1;color:#dbe3f0;font-size:13px;">${s.name}</span>
            <span style="color:#fff;font-weight:700;font-size:13px;margin-right:8px;">${s.revenue > 0 ? s.revenue.toLocaleString() + unit : ''}</span>
            <span style="color:#8b95a8;font-size:11px;width:35px;">${pct}%</span>
            <span style="color:${s.growth.includes('-')?'#f87171':'#34d399'};font-size:11px;font-weight:650;">${s.growth}</span>
          </div>`;
        }).join('')}
        ${total > 0 ? `<div style="border-top:1px solid rgba(255,255,255,0.1);margin-top:8px;padding-top:6px;display:flex;justify-content:space-between;">
          <span style="color:#90CAF9;font-size:12px;">합계</span>
          <span style="color:#fff;font-weight:bold;font-size:13px;">${total.toLocaleString()}${unit}</span>
        </div>` : ''}
      </div>
    </div>
  </div>`;
}

function renderRevenueStructure(s, idx) {
  const rs = s.revenue_structure;
  if (!rs || !rs.length) return '';
  const latest = rs[0];
  const unit = latest.unit || '$B';

  // 성장률 뱃지
  let growthHtml = '';
  if (rs.length >= 2) {
    const cur = rs[0], prev = rs[1];
    const revG = prev.revenue ? ((cur.revenue - prev.revenue) / prev.revenue * 100).toFixed(1) : 'N/A';
    const oiG = prev.operating_income && prev.operating_income > 0 ? ((cur.operating_income - prev.operating_income) / prev.operating_income * 100).toFixed(1) : 'N/A';
    const niG = prev.net_income && prev.net_income > 0 ? ((cur.net_income - prev.net_income) / prev.net_income * 100).toFixed(1) : 'N/A';
    const gc = (v) => parseFloat(v) > 0 ? '#34d399' : '#f87171';
    growthHtml = `<div class="stat-chips">
      <div class="stat-chip"><span>매출 YoY</span><b style="color:${gc(revG)}">${revG > 0?'+':''}${revG}%</b></div>
      <div class="stat-chip"><span>영업이익 YoY</span><b style="color:${gc(oiG)}">${oiG > 0?'+':''}${oiG}%</b></div>
      <div class="stat-chip"><span>순이익 YoY</span><b style="color:${gc(niG)}">${niG > 0?'+':''}${niG}%</b></div>
    </div>`;
  }

  // 연도별 테이블
  const fmtVal = (v) => v ? v.toFixed(1) + unit : 'N/A';
  let tableRows = rs.map(y => `
    <tr>
      <td style="color:#93c5fd;font-weight:700;">${y.year}</td>
      <td>${fmtVal(y.revenue)}</td>
      <td>${fmtVal(y.gross_profit)} <span style="color:#34d399;font-size:11px;">${y.gross_margin}%</span></td>
      <td>${fmtVal(y.operating_income)} <span style="color:#6ea8ff;font-size:11px;">${y.operating_margin}%</span></td>
      <td>${fmtVal(y.net_income)} <span style="color:#86efac;font-size:11px;">${y.net_margin}%</span></td>
    </tr>`).join('');

  return `<div class="direction-box">
    <div class="direction-title" style="margin-bottom:8px;">💰 수익 구조 (${latest.year})</div>
    ${growthHtml}
    ${renderSegmentDonut(s, idx)}
    <div class="charts-grid">
      <div class="chart-wrap" style="text-align:center;background:radial-gradient(circle at center, rgba(25,118,210,0.08) 0%, transparent 70%);">
        <p style="color:#90CAF9;font-size:14px;font-weight:bold;margin-bottom:12px;">💵 매출 구성</p>
        <canvas id="donut1_${idx}"></canvas>
      </div>
      <div class="chart-wrap" style="text-align:center;background:radial-gradient(circle at center, rgba(76,175,80,0.08) 0%, transparent 70%);">
        <p style="color:#90CAF9;font-size:14px;font-weight:bold;margin-bottom:12px;">✂️ 비용 & 이익</p>
        <canvas id="donut2_${idx}"></canvas>
      </div>
    </div>
    <table class="fin-table">
      <thead>
        <tr>
          <th>연도</th>
          <th>매출</th>
          <th>총이익 (마진)</th>
          <th>영업이익 (마진)</th>
          <th>순이익 (마진)</th>
        </tr>
      </thead>
      <tbody>${tableRows}</tbody>
    </table>
    <div class="charts-grid">
      <div class="chart-wrap"><canvas id="waterfall_${idx}"></canvas></div>
      <div class="chart-wrap"><canvas id="margin_trend_${idx}"></canvas></div>
    </div>
  </div>`;
}

function renderStock(s, idx) {
  const c = document.getElementById('results');
  const [peText,peColor] = peLabel(s.trailing_pe);
  const [fpeText,fpeColor] = peLabel(s.forward_pe);
  
  const changeClass = s.monthly_return >= 0 ? 'price-up' : 'price-down';
  const changeText = s.monthly_return != null ? (s.monthly_return >= 0 ? '+' : '') + s.monthly_return.toFixed(1) + '% (1개월)' : '';
  const curr = s.currency || 'USD';
  const sym = curr === 'KRW' ? '₩' : '$';
  const fmtPrice = (v) => v == null ? 'N/A' : curr === 'KRW' ? sym + v.toLocaleString('ko-KR',{maximumFractionDigits:0}) : sym + v.toFixed(2);
  
  const grade = s.score_grade || 'C';
  const gradeEmoji = {A:'🟢',B:'🔵',C:'🟡',D:'🟠',F:'🔴'}[grade] || '⚪';
  
  let metricsHtml = '';
  if (s.revenue_growth != null) {
    const rg = (s.revenue_growth*100);
    const rc = rg > 20 ? '#4CAF50' : rg > 0 ? '#FF9800' : '#F44336';
    metricsHtml += `<div class="metric-row"><span class="metric-label">매출 성장률</span><span class="metric-val" style="color:${rc}">${rg > 0 ? '+' : ''}${rg.toFixed(1)}%</span></div>`;
  }
  if (s.earnings_growth != null) {
    const eg = (s.earnings_growth*100);
    const ec = eg > 20 ? '#4CAF50' : eg > 0 ? '#FF9800' : '#F44336';
    metricsHtml += `<div class="metric-row"><span class="metric-label">이익 성장률</span><span class="metric-val" style="color:${ec}">${eg > 0 ? '+' : ''}${eg.toFixed(1)}%</span></div>`;
  }
  if (s.profit_margin != null) metricsHtml += `<div class="metric-row"><span class="metric-label">이익률</span><span class="metric-val">${(s.profit_margin*100).toFixed(1)}%</span></div>`;
  if (s.peg != null) {
    const pc = s.peg < 1 ? '#4CAF50' : s.peg < 1.5 ? '#2196F3' : s.peg < 3 ? '#FF9800' : '#F44336';
    metricsHtml += `<div class="metric-row"><span class="metric-label">PEG</span><span class="metric-val" style="color:${pc}">${s.peg.toFixed(2)}</span></div>`;
  }

  let w52Html = '';
  if (s.w52_high && s.w52_low && s.current_price) {
    const pos = ((s.current_price - s.w52_low) / (s.w52_high - s.w52_low) * 100).toFixed(0);
    w52Html = `<div class="w52"><div class="w52-labels"><span>${fmtPrice(s.w52_low)}</span><span>52주 범위 (현재 ${pos}%)</span><span>${fmtPrice(s.w52_high)}</span></div><div class="w52-track"><div class="w52-fill" style="width:${pos}%"></div><div class="w52-dot" style="left:${pos}%"></div></div></div>`;
  }

  const scoreItems = (s.score_details || []).map(d => d.replace(/\\n/g, '<br>')).join('<br>');

  const div = document.createElement('div');
  div.className = 'stock-card';
  const avatarLetter = (s.ticker || s.name || '?').split('.')[0].slice(0,2);
  div.innerHTML = `
    <div class="card-header">
      <div class="name-row">
        <div class="ticker-avatar">${avatarLetter}</div>
        <div>
          <h2>${s.name}</h2>
          <span class="ticker-badge">${s.ticker}</span>
          <span class="sector">${s.sector || ''} ${s.industry ? '· '+s.industry : ''}</span>
        </div>
      </div>
      <div class="price-area">
        <span class="big-price">${fmtPrice(s.current_price)}</span>
        <span class="price-change ${changeClass}">${changeText}</span>
        <div class="mcap">시가총액 ${fmtCap(s.market_cap, curr)}</div>
      </div>
    </div>
    <div class="score-banner ${grade}">
      <div class="score-ring" style="--pct:${s.score || 0}">
        <div class="score-ring-inner"><span class="score-num">${s.score}</span></div>
      </div>
      <div class="score-detail">
        <div class="score-grade">${gradeEmoji} 투자 등급 ${grade}</div>
        <div class="score-items">${scoreItems}</div>
      </div>
    </div>
    <div class="metrics-grid">
      <div class="metric-card">
        <div class="metric-title">밸류에이션</div>
        <div class="metric-row"><span class="metric-label">Trailing PER</span><span class="metric-val" style="color:${peColor}">${peText}</span></div>
        <div class="metric-row"><span class="metric-label">Forward PER</span><span class="metric-val" style="color:${fpeColor}">${fpeText}</span></div>
        <div class="metric-row"><span class="metric-label">PBR</span><span class="metric-val">${s.pb != null ? s.pb.toFixed(2) : 'N/A'}</span></div>
        <div class="metric-row"><span class="metric-label">EPS</span><span class="metric-val">${fmtPrice(s.eps)}</span></div>
        <div class="metric-row"><span class="metric-label">Forward EPS</span><span class="metric-val">${fmtPrice(s.forward_eps)}</span></div>
      </div>
      <div class="metric-card">
        <div class="metric-title">성장성</div>
        ${metricsHtml}
      </div>
    </div>
    ${w52Html}
    ${renderDirection(s)}
    ${renderNews(s)}
    <div class="charts-grid">
      <div class="chart-wrap"><canvas id="price_${idx}"></canvas></div>
      <div class="chart-wrap"><canvas id="per_${idx}"></canvas></div>
    </div>
    <div class="charts-grid">
      <div class="chart-wrap"><canvas id="rev_${idx}"></canvas></div>
      <div class="chart-wrap"><canvas id="margin_${idx}"></canvas></div>
    </div>
    ${renderRevenueStructure(s, idx)}`;
  c.appendChild(div);

  new Chart(document.getElementById('price_'+idx), {
    type:'line',
    data:{datasets:[{label:'주가 ('+sym+')',data:s.price_history,borderColor:'#6ea8ff',backgroundColor:'rgba(110,168,255,0.12)',fill:true,tension:0.35,pointRadius:0}]},
    options:{responsive:true,plugins:{title:{display:true,text:'주가 추이 (1년)'}},scales:{x:{type:'time',time:{unit:'month'}},y:{grid:{color:'rgba(255,255,255,0.06)'}}}}
  });
  new Chart(document.getElementById('per_'+idx), {
    type:'line',
    data:{datasets:[{label:'PER',data:s.per_history,borderColor:'#f87171',backgroundColor:'rgba(248,113,113,0.12)',fill:true,tension:0.35,pointRadius:0}]},
    options:{responsive:true,plugins:{title:{display:true,text:'PER 추이 (1년)'}},scales:{x:{type:'time',time:{unit:'month'}},y:{grid:{color:'rgba(255,255,255,0.06)'}}}}
  });
  if (s.quarters && s.quarters.length) {
    new Chart(document.getElementById('rev_'+idx), {
      type:'bar',
      data:{labels:s.quarters.map(q=>q.label),datasets:[{label:curr==='KRW'?'매출 (조원)':'매출 ($B)',data:s.quarters.map(q=>q.revenue),backgroundColor:'rgba(25,118,210,0.8)'},{label:curr==='KRW'?'순이익 (조원)':'순이익 ($B)',data:s.quarters.map(q=>q.net_income),backgroundColor:'rgba(76,175,80,0.8)'}]},
      options:{responsive:true,plugins:{title:{display:true,text:'분기별 매출 & 순이익',font:{size:14}}}}
    });
    new Chart(document.getElementById('margin_'+idx), {
      type:'bar',
      data:{labels:s.quarters.map(q=>q.label),datasets:[{label:'이익률 (%)',data:s.quarters.map(q=>q.margin),backgroundColor:s.quarters.map(q=>q.margin>40?'rgba(76,175,80,0.8)':q.margin>20?'rgba(255,193,7,0.8)':'rgba(244,67,54,0.8)')}]},
      options:{responsive:true,plugins:{title:{display:true,text:'분기별 이익률',font:{size:14}}},scales:{y:{beginAtZero:true}}}
    });
  }

  // 수익 구조 차트
  const rs = s.revenue_structure;
  if (rs && rs.length) {
    const latest = rs[0];
    const unit = latest.unit || '$B';
    const centerTextPlugin = {
      id: 'centerText',
      afterDraw(chart) {
        const { ctx, chartArea } = chart;
        const meta = chart.options.plugins.centerText;
        if (!meta) return;
        const cx = (chartArea.left + chartArea.right) / 2;
        const cy = (chartArea.top + chartArea.bottom) / 2;
        ctx.save();
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.font = 'bold 20px -apple-system, sans-serif';
        ctx.fillStyle = '#fff';
        ctx.fillText(meta.line1 || '', cx, cy - 10);
        ctx.font = '12px -apple-system, sans-serif';
        ctx.fillStyle = '#aaa';
        ctx.fillText(meta.line2 || '', cx, cy + 12);
        ctx.restore();
      }
    };

    // 세그먼트 도넛 차트
    const seg = s.segments;
    if (seg && !seg.estimated && document.getElementById('seg_donut_'+idx)) {
      const segColors = ['rgba(66,165,245,0.8)','rgba(102,187,106,0.75)','rgba(255,167,38,0.75)','rgba(171,71,188,0.7)','rgba(239,83,80,0.7)','rgba(38,198,218,0.7)','rgba(141,110,99,0.7)','rgba(120,144,156,0.65)'];
      const segTotal = seg.segments.reduce((a,b)=>a+b.revenue,0);
      new Chart(document.getElementById('seg_donut_'+idx), {
        type: 'doughnut',
        plugins: [centerTextPlugin],
        data: {
          labels: seg.segments.map(s => s.name),
          datasets: [{
            data: seg.segments.map(s => s.revenue),
            backgroundColor: segColors.slice(0, seg.segments.length),
            borderWidth: 0,
            hoverBorderColor: 'rgba(255,255,255,0.8)',
            hoverBorderWidth: 2,
            hoverOffset: 12,
            spacing: 2,
          }]
        },
        options: {
          responsive: true,
          cutout: '58%',
          animation: { animateRotate: true, duration: 1200 },
          plugins: {
            centerText: { line1: segTotal.toLocaleString(), line2: '합계 ('+seg.unit+')' },
            legend: { display: false },
            tooltip: {
              backgroundColor: 'rgba(0,0,0,0.85)', titleFont: { size: 14 }, bodyFont: { size: 13 }, padding: 12, cornerRadius: 8,
              callbacks: { label: (ctx) => ' ' + ctx.label + ': ' + ctx.parsed.toLocaleString() + seg.unit + ' (' + (ctx.parsed / segTotal * 100).toFixed(0) + '%)' }
            }
          }
        }
      });
    }

    // 도넛 1: 매출 = 매출원가 + 매출총이익
    // 도넛 중앙 텍스트 플러그인

    const donutStyle = {
      borderWidth: 0,
      hoverBorderColor: 'rgba(255,255,255,0.8)',
      hoverBorderWidth: 2,
      hoverOffset: 12,
      spacing: 2,
    };

    // 도넛 1: 매출 = 매출원가 + 매출총이익
    new Chart(document.getElementById('donut1_'+idx), {
      type: 'doughnut',
      plugins: [centerTextPlugin],
      data: {
        labels: ['매출원가 '+((latest.cost_of_revenue/latest.revenue)*100).toFixed(0)+'%', '매출총이익 '+latest.gross_margin+'%'],
        datasets: [{
          data: [latest.cost_of_revenue, latest.gross_profit],
          backgroundColor: ['rgba(239,83,80,0.75)', 'rgba(102,187,106,0.75)'],
          ...donutStyle,
        }]
      },
      options: {
        responsive: true,
        cutout: '62%',
        animation: { animateRotate: true, duration: 1200 },
        plugins: {
          centerText: { line1: latest.revenue.toFixed(1), line2: '매출 ('+unit+')' },
          legend: { position: 'bottom', labels: { font: { size: 13, weight: 'bold' }, padding: 14, usePointStyle: true, pointStyle: 'circle' } },
          tooltip: {
            backgroundColor: 'rgba(0,0,0,0.85)', titleFont: { size: 14 }, bodyFont: { size: 13 }, padding: 12, cornerRadius: 8,
            callbacks: { label: (ctx) => ' ' + ctx.label + ': ' + ctx.parsed.toFixed(1) + unit }
          }
        }
      }
    });

    // 도넛 2: 매출총이익 구성
    const smExp = latest.sga > latest.rnd ? latest.sga - latest.rnd : latest.sga;
    const otherExp = latest.operating_expense - latest.sga - latest.rnd;
    const donut2Data = [];
    const donut2Labels = [];
    const donut2Colors = [];

    if (latest.net_income > 0) { donut2Labels.push('순이익 '+latest.net_margin+'%'); donut2Data.push(latest.net_income); donut2Colors.push('rgba(66,165,245,0.8)'); }
    else if (latest.operating_income > 0) { donut2Labels.push('영업이익'); donut2Data.push(latest.operating_income); donut2Colors.push('rgba(66,165,245,0.8)'); }
    if (smExp > 0) { donut2Labels.push('판매&마케팅'); donut2Data.push(smExp); donut2Colors.push('rgba(255,167,38,0.7)'); }
    if (latest.rnd > 0) { donut2Labels.push('R&D'); donut2Data.push(latest.rnd); donut2Colors.push('rgba(171,71,188,0.7)'); }
    if (otherExp > 0) { donut2Labels.push('기타 비용'); donut2Data.push(otherExp); donut2Colors.push('rgba(120,144,156,0.6)'); }

    new Chart(document.getElementById('donut2_'+idx), {
      type: 'doughnut',
      plugins: [centerTextPlugin],
      data: {
        labels: donut2Labels,
        datasets: [{
          data: donut2Data,
          backgroundColor: donut2Colors,
          ...donutStyle,
        }]
      },
      options: {
        responsive: true,
        cutout: '62%',
        animation: { animateRotate: true, duration: 1200 },
        plugins: {
          centerText: { line1: latest.gross_profit.toFixed(1), line2: '매출총이익 ('+unit+')' },
          legend: { position: 'bottom', labels: { font: { size: 13, weight: 'bold' }, padding: 14, usePointStyle: true, pointStyle: 'circle' } },
          tooltip: {
            backgroundColor: 'rgba(0,0,0,0.85)', titleFont: { size: 14 }, bodyFont: { size: 13 }, padding: 12, cornerRadius: 8,
            callbacks: { label: (ctx) => ' ' + ctx.label + ': ' + ctx.parsed.toFixed(1) + unit }
          }
        }
      }
    });

    // 워터폴 차트
    const wfLabels2 = ['매출', '매출원가', '매출총이익', '판관비', 'R&D', '영업이익', '순이익'];
    const wfData2 = [latest.revenue, latest.cost_of_revenue, latest.gross_profit,
      latest.sga, latest.rnd, latest.operating_income, latest.net_income];
    const wfColors2 = ['#1976D2','#F44336','#4CAF50','#FF9800','#9C27B0','#2196F3','#66BB6A'];

    new Chart(document.getElementById('waterfall_'+idx), {
      type: 'bar',
      data: {
        labels: wfLabels2,
        datasets: [{
          label: unit,
          data: wfData2,
          backgroundColor: wfColors2,
          borderRadius: 4,
        }]
      },
      options: {
        responsive: true,
        plugins: {
          title: { display: true, text: '수익 구조 (' + latest.year + ')', font: { size: 14 } },
          tooltip: { callbacks: { label: (ctx) => ctx.parsed.y + unit + ' (' + (ctx.parsed.y/latest.revenue*100).toFixed(0) + '%)' } }
        }
      }
    });

    // 마진 트렌드
    const years = rs.map(y=>y.year).reverse();
    new Chart(document.getElementById('margin_trend_'+idx), {
      type: 'line',
      data: {
        labels: years,
        datasets: [
          { label: '매출총이익률 (%)', data: rs.map(y=>y.gross_margin).reverse(), borderColor: '#4CAF50', tension: 0.3 },
          { label: '영업이익률 (%)', data: rs.map(y=>y.operating_margin).reverse(), borderColor: '#2196F3', tension: 0.3 },
          { label: '순이익률 (%)', data: rs.map(y=>y.net_margin).reverse(), borderColor: '#FF9800', tension: 0.3 },
        ]
      },
      options: {
        responsive: true,
        plugins: { title: { display: true, text: '마진 추이 (연도별)', font: { size: 14 } } },
        scales: { y: { beginAtZero: true } }
      }
    });
  }
}
</script>
</body>
</html>"""


def _fetch_news(ticker: str, name: str) -> list[dict]:
    """종목 관련 최신 뉴스를 가져온다."""
    from urllib.request import urlopen, Request
    from urllib.parse import quote
    from xml.etree import ElementTree
    import re
    news = []

    is_kr = ticker.endswith((".KS", ".KQ"))
    search_name = name if _has_korean(name) else ticker.split(".")[0]

    if is_kr:
        url = f"https://news.google.com/rss/search?q={quote(search_name)}&hl=ko&gl=KR&ceid=KR:ko"
    else:
        url = f"https://news.google.com/rss/search?q={quote(search_name + ' stock earnings')}&hl=en&gl=US&ceid=US:en"

    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=10) as resp:
            tree = ElementTree.parse(resp)
        for item in list(tree.iter("item"))[:10]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            source = title.split(" - ")[-1] if " - " in title else ""
            headline = title.rsplit(" - ", 1)[0] if " - " in title else title
            if headline:
                news.append({"title": headline, "source": source, "link": link, "date": pub})
    except Exception as e:
        print(f"[WARN] Google News 실패: {e}")

    if not is_kr:
        try:
            stock = yf.Ticker(ticker)
            yf_news = stock.news or []
            for n in yf_news[:5]:
                content = n.get("content", n)
                title = content.get("title", "")
                summary = content.get("summary", "")
                provider = content.get("provider", {})
                source = provider.get("displayName", "") if isinstance(provider, dict) else ""
                link_data = content.get("canonicalUrl", content.get("clickThroughUrl", {}))
                link = link_data.get("url", "") if isinstance(link_data, dict) else ""
                pub = content.get("pubDate", "")
                if title and not any(n2["title"] == title for n2 in news):
                    news.append({"title": title, "source": source, "link": link,
                                 "date": pub, "summary": summary})
        except Exception as e:
            print(f"[WARN] Yahoo News 실패: {e}")

    return news


def _extract_segments_from_news(news: list[dict], name: str) -> dict | None:
    """뉴스 제목에서 매출 세그먼트 정보를 추출한다."""
    import re

    all_text = " ".join(n["title"] + " " + n.get("summary", "") for n in news)

    segment_patterns = {
        "en": [
            (r"(?:commercial|enterprise)\s+revenue[:\s]*\$?([\d,.]+)\s*(B|M|billion|million)", "Commercial"),
            (r"(?:government|federal)\s+revenue[:\s]*\$?([\d,.]+)\s*(B|M|billion|million)", "Government"),
            (r"(?:data\s*center|datacenter)\s+revenue[:\s]*\$?([\d,.]+)\s*(B|M|billion|million)", "Data Center"),
            (r"(?:cloud|aws|azure)\s+revenue[:\s]*\$?([\d,.]+)\s*(B|M|billion|million)", "Cloud"),
            (r"(?:gaming)\s+revenue[:\s]*\$?([\d,.]+)\s*(B|M|billion|million)", "Gaming"),
            (r"(?:advertising|ad)\s+revenue[:\s]*\$?([\d,.]+)\s*(B|M|billion|million)", "Advertising"),
            (r"(?:subscription|서브스크립션)\s+revenue[:\s]*\$?([\d,.]+)\s*(B|M|billion|million)", "Subscription"),
            (r"(?:automotive|자동차)\s+revenue[:\s]*\$?([\d,.]+)\s*(B|M|billion|million)", "Automotive"),
            (r"(?:services?)\s+revenue[:\s]*\$?([\d,.]+)\s*(B|M|billion|million)", "Services"),
        ],
        "kr": [
            (r"(IVI|차량용|자동차)\s*(?:칩|반도체)?\s*매출\s*([\d,.]+)\s*(억|조)", "차량용 반도체"),
            (r"(로봇|로보틱스)\s*(?:사업|부문)?\s*매출\s*([\d,.]+)\s*(억|조)", "로봇"),
            (r"(게이트웨이|통신)\s*(?:칩|사업)?\s*매출\s*([\d,.]+)\s*(억|조)", "네트워크 게이트웨이"),
            (r"(반도체|칩)\s*(?:사업|부문)?\s*매출\s*([\d,.]+)\s*(억|조)", "반도체"),
            (r"(서비스|SW)\s*(?:사업|부문)?\s*매출\s*([\d,.]+)\s*(억|조)", "서비스/SW"),
            (r"(광고)\s*(?:사업|부문)?\s*매출\s*([\d,.]+)\s*(억|조)", "광고"),
            (r"(구독|콘텐츠)\s*(?:사업|부문)?\s*매출\s*([\d,.]+)\s*(억|조)", "구독/콘텐츠"),
            (r"(플랫폼)\s*(?:사업|부문)?\s*매출\s*([\d,.]+)\s*(억|조)", "플랫폼"),
            (r"(커머스|쇼핑)\s*(?:사업|부문)?\s*매출\s*([\d,.]+)\s*(억|조)", "커머스"),
        ],
    }

    segments_found = []
    text_lower = all_text.lower()

    for pattern, seg_name in segment_patterns["en"]:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            val_str = match.group(1).replace(",", "")
            unit = match.group(2)
            val = float(val_str)
            if unit.lower() in ("b", "billion"):
                val *= 1000
            segments_found.append({"name": seg_name, "revenue": val, "growth": ""})

    for pattern, seg_name in segment_patterns["kr"]:
        match = re.search(pattern, all_text)
        if match:
            groups = match.groups()
            if len(groups) >= 3:
                val_str = groups[1].replace(",", "")
                unit = groups[2]
                val = float(val_str)
                if unit == "조":
                    val *= 10000
                segments_found.append({"name": seg_name, "revenue": val, "growth": ""})

    # 뉴스 제목에서 성장률도 추출
    growth_pattern = re.compile(r"(\w+)\s+revenue\s+(?:jumps?|soars?|grows?|up)\s+(\d+)%", re.IGNORECASE)
    for match in growth_pattern.finditer(all_text):
        seg = match.group(1).title()
        pct = match.group(2)
        for s in segments_found:
            if seg.lower() in s["name"].lower():
                s["growth"] = f"+{pct}% YoY"

    if not segments_found:
        # 키워드 기반 추정 (정확한 숫자 없이)
        biz_keywords = {
            "en": {
                "data center": "Data Center", "cloud": "Cloud", "gaming": "Gaming",
                "advertising": "Advertising", "automotive": "Automotive",
                "subscription": "Subscription", "enterprise": "Enterprise",
                "consumer": "Consumer", "hardware": "Hardware", "software": "Software",
            },
            "kr": {
                "자동차": "자동차", "반도체": "반도체", "로봇": "로봇", "AI": "AI",
                "클라우드": "클라우드", "광고": "광고", "게임": "게임",
                "배터리": "배터리", "디스플레이": "디스플레이", "바이오": "바이오",
                "플랫폼": "플랫폼", "커머스": "커머스", "핀테크": "핀테크",
                "콘텐츠": "콘텐츠", "물류": "물류",
            },
        }
        found_biz = []
        for kw, label in biz_keywords["en"].items():
            if kw in text_lower:
                found_biz.append(label)
        for kw, label in biz_keywords["kr"].items():
            if kw in all_text:
                found_biz.append(label)

        if found_biz:
            return {
                "name": name,
                "segments": [{"name": b, "revenue": 0, "growth": ""} for b in list(dict.fromkeys(found_biz))[:6]],
                "unit": "",
                "period": "뉴스 기반 추정",
                "estimated": True,
            }
        return None

    if segments_found:
        is_kr = any(s["name"] in ("차량용 반도체", "로봇", "네트워크 게이트웨이") for s in segments_found)
        return {
            "name": name,
            "segments": segments_found,
            "unit": "억원" if is_kr else "$M",
            "period": "최근 실적",
            "estimated": False,
        }

    return None


def _analyze_company_direction(news: list[dict], name: str) -> dict:
    """뉴스를 분석하여 기업 비전/방향성을 요약한다."""
    import re

    keywords_positive = {
        "성장": "성장", "확대": "사업 확대", "진출": "신규 진출", "수주": "수주",
        "흑자": "흑자 전환", "신제품": "신제품", "투자": "투자 확대",
        "AI": "AI/인공지능", "반도체": "반도체", "로봇": "로봇",
        "전기차": "전기차/EV", "배터리": "배터리", "자율주행": "자율주행",
        "클라우드": "클라우드", "데이터센터": "데이터센터",
        "growth": "성장", "expansion": "사업 확대", "launch": "신규 출시",
        "revenue": "매출", "profit": "수익", "partnership": "파트너십",
        "innovation": "혁신", "breakthrough": "기술 돌파",
    }

    keywords_risk = {
        "적자": "적자", "감소": "실적 감소", "하락": "주가 하락",
        "리스크": "리스크", "소송": "법적 리스크", "규제": "규제",
        "경쟁": "경쟁 심화", "둔화": "성장 둔화",
        "loss": "손실", "decline": "하락", "risk": "리스크",
        "lawsuit": "소송", "regulation": "규제",
    }

    themes = {}
    risks = {}
    all_text = " ".join(n["title"] + " " + n.get("summary", "") for n in news).lower()

    for keyword, theme in keywords_positive.items():
        if keyword.lower() in all_text:
            themes[theme] = themes.get(theme, 0) + 1

    for keyword, risk in keywords_risk.items():
        if keyword.lower() in all_text:
            risks[risk] = risks.get(risk, 0) + 1

    top_themes = sorted(themes.items(), key=lambda x: x[1], reverse=True)[:5]
    top_risks = sorted(risks.items(), key=lambda x: x[1], reverse=True)[:3]

    positive_count = sum(themes.values())
    negative_count = sum(risks.values())
    total = positive_count + negative_count

    if total == 0:
        outlook = "정보 부족"
        outlook_color = "#999"
    elif positive_count > negative_count * 2:
        outlook = "매우 긍정적"
        outlook_color = "#4CAF50"
    elif positive_count > negative_count:
        outlook = "긍정적"
        outlook_color = "#8BC34A"
    elif negative_count > positive_count:
        outlook = "부정적"
        outlook_color = "#F44336"
    else:
        outlook = "중립"
        outlook_color = "#FF9800"

    return {
        "outlook": outlook,
        "outlook_color": outlook_color,
        "themes": [t[0] for t in top_themes],
        "risks": [r[0] for r in top_risks],
        "news_count": len(news),
    }


def fetch_stock(raw_ticker: str) -> dict | None:
    try:
        ticker = resolve_ticker(raw_ticker)
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        hist = stock.history(period="1y")
        if hist.empty:
            return None

        currency = info.get("currency", "USD")
        is_kr = ticker.endswith((".KS", ".KQ"))

        shares = info.get("sharesOutstanding", 1)
        income = stock.quarterly_income_stmt
        quarters = []
        if income is not None and not income.empty:
            ni_row = income.loc["Net Income"] if "Net Income" in income.index else None
            rev_row = income.loc["Total Revenue"] if "Total Revenue" in income.index else None
            if ni_row is not None and rev_row is not None:
                for col in reversed(ni_row.index[:8]):
                    ni = float(ni_row[col])
                    rev = float(rev_row[col])
                    import math
                    margin = (ni / rev * 100) if rev else 0
                    if math.isnan(margin) or math.isinf(margin):
                        margin = 0
                    divisor = 1e12 if is_kr else 1e9
                    ni_val = round(ni / divisor, 3) if not math.isnan(ni) else 0
                    rev_val = round(rev / divisor, 3) if not math.isnan(rev) else 0
                    quarters.append({
                        "label": col.strftime("%y/%m"),
                        "revenue": rev_val,
                        "net_income": ni_val,
                        "margin": round(margin, 1),
                    })
        display_name = get_display_name(ticker, info)

        trailing_eps = info.get("trailingEps")
        trailing_pe = info.get("trailingPE")
        forward_pe = info.get("forwardPE")

        if (trailing_eps is None or trailing_pe is None) and income is not None and not income.empty:
            ni_row = income.loc["Net Income"] if "Net Income" in income.index else None
            if ni_row is not None and shares:
                recent_4q = list(ni_row.index)[:4]
                annual_ni = sum(float(ni_row[c]) for c in recent_4q)
                calc_eps = annual_ni / shares
                if calc_eps > 0:
                    if trailing_eps is None:
                        trailing_eps = calc_eps
                    current_price = info.get("currentPrice") or info.get("regularMarketPrice")
                    if trailing_pe is None and current_price and calc_eps > 0:
                        trailing_pe = current_price / calc_eps

        trailing_eps = trailing_eps or 1
        price_history = []
        per_history = []
        for i in range(0, len(hist), 3):
            row = hist.iloc[i]
            d = row.name.strftime("%Y-%m-%d")
            p = round(float(row["Close"]), 2)
            price_history.append({"x": d, "y": p})
            if trailing_eps > 0:
                per_history.append({"x": d, "y": round(p / trailing_eps, 1)})
        last = hist.iloc[-1]
        price_history.append({"x": last.name.strftime("%Y-%m-%d"), "y": round(float(last["Close"]), 2)})
        if trailing_eps > 0:
            per_history.append({"x": last.name.strftime("%Y-%m-%d"), "y": round(float(last["Close"]) / trailing_eps, 1)})

        monthly_return = None
        if len(hist) >= 20:
            s_price = float(hist["Close"].iloc[0])
            e_price = float(hist["Close"].iloc[-1])
            monthly_return = round(((e_price - s_price) / s_price) * 100, 1)

        # 스코어 계산
        from scripts.stock_charts import calculate_investment_score, fetch_stock_data
        full_data = fetch_stock_data(ticker)
        score_data = calculate_investment_score(full_data) if full_data else {"total": 50, "grade": "C", "details": [], "scores": {}}

        result = {
            "ticker": ticker,
            "name": display_name,
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "currency": currency,
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "market_cap": info.get("marketCap"),
            "trailing_pe": trailing_pe,
            "forward_pe": forward_pe,
            "peg": info.get("pegRatio"),
            "pb": info.get("priceToBook"),
            "eps": info.get("trailingEps"),
            "forward_eps": info.get("forwardEps"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "profit_margin": info.get("profitMargins"),
            "w52_high": info.get("fiftyTwoWeekHigh"),
            "w52_low": info.get("fiftyTwoWeekLow"),
            "monthly_return": monthly_return,
            "price_history": price_history,
            "per_history": per_history,
            "quarters": quarters,
            "score": score_data["total"],
            "score_grade": score_data["grade"],
            "score_details": score_data["details"],
        }

        # 수익 구조 분석
        import math as _math
        revenue_structure = None
        try:
            ann_income = stock.income_stmt
            if ann_income is not None and not ann_income.empty:
                years_data = []
                for col in ann_income.columns[:3]:
                    def _safe(key):
                        try:
                            v = float(ann_income.loc[key, col])
                            return v if not _math.isnan(v) else 0
                        except Exception:
                            return 0
                    rev = _safe("Total Revenue")
                    if rev == 0:
                        continue
                    div = 1e12 if is_kr else 1e9
                    unit = "조원" if is_kr else "$B"
                    cogs = _safe("Cost Of Revenue")
                    gross = _safe("Gross Profit")
                    opex = _safe("Operating Expense")
                    sga = _safe("Selling General And Administration")
                    rnd = _safe("Research And Development")
                    oi = _safe("Operating Income")
                    ni = _safe("Net Income")
                    ebitda = _safe("EBITDA")

                    years_data.append({
                        "year": col.strftime("%Y"),
                        "unit": unit,
                        "revenue": round(rev / div, 1),
                        "cost_of_revenue": round(cogs / div, 1),
                        "gross_profit": round(gross / div, 1),
                        "gross_margin": round(gross / rev * 100, 1) if rev else 0,
                        "operating_expense": round(opex / div, 1),
                        "sga": round(sga / div, 1),
                        "rnd": round(rnd / div, 1),
                        "operating_income": round(oi / div, 1),
                        "operating_margin": round(oi / rev * 100, 1) if rev else 0,
                        "net_income": round(ni / div, 1),
                        "net_margin": round(ni / rev * 100, 1) if rev else 0,
                        "ebitda": round(ebitda / div, 1),
                    })
                if years_data:
                    revenue_structure = years_data
        except Exception as e:
            print(f"[WARN] 수익 구조 분석 실패: {e}")

        result["revenue_structure"] = revenue_structure

        # 세그먼트별 매출
        base_ticker = ticker.split(".")[0].upper()
        result["segments"] = SEGMENT_DATA.get(base_ticker)

        print(f"[INFO] {display_name} 뉴스 수집 중...")
        news_list = _fetch_news(ticker, display_name)
        direction = _analyze_company_direction(news_list, display_name)
        result["news"] = news_list[:6]
        result["direction"] = direction
        print(f"[INFO] {display_name} 뉴스 {len(news_list)}건, 전망: {direction['outlook']}")

        # 사전 데이터 없으면 뉴스에서 세그먼트 추출 시도
        if not result["segments"] and news_list:
            extracted = _extract_segments_from_news(news_list, display_name)
            if extracted:
                result["segments"] = extracted
                print(f"[INFO] {display_name} 뉴스에서 세그먼트 {len(extracted['segments'])}개 추출")

        return result
    except Exception as e:
        print(f"[ERROR] {ticker}: {e}")
        return None


@app.route("/")
def index():
    html = HTML.replace("POPULAR_US_JSON", json.dumps(POPULAR_US, ensure_ascii=False))
    html = html.replace("POPULAR_KR_JSON", json.dumps(POPULAR_KR, ensure_ascii=False))
    return html


@app.route("/api/analyze")
def api_analyze():
    tickers_raw = request.args.get("tickers", "")
    tickers = [t.strip().upper() for t in tickers_raw.split(",") if t.strip()]
    if not tickers:
        return jsonify({"error": "티커를 입력해 주세요"})

    stocks = []
    for t in tickers[:5]:
        data = fetch_stock(t)
        if data:
            stocks.append(data)

    if not stocks:
        return jsonify({"error": f"'{tickers_raw}' 을(를) 찾을 수 없습니다. 종목 코드(예: 054450, 059120)로 다시 시도해 보세요."})

    import math

    def clean_nan(obj):
        if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
            return None
        if isinstance(obj, dict):
            return {k: clean_nan(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [clean_nan(v) for v in obj]
        return obj

    return jsonify({"stocks": clean_nan(stocks)})


if __name__ == "__main__":
    import webbrowser
    import threading

    port = int(os.environ.get("PORT", 5001))
    print("=" * 50)
    print("  📊 종목 분석기")
    print(f"  http://localhost:{port}")
    print("  종료: Ctrl+C")
    print("=" * 50)

    threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    app.run(host="0.0.0.0", port=port, debug=False)
