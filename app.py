#!/usr/bin/env python3
"""
종목 분석 웹 앱.
티커를 입력하면 실시간으로 주가·PER·실적 차트를 보여준다.

실행: python app.py
접속: http://localhost:5000
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
        ks = raw + ".KS"
        try:
            stock = yf.Ticker(ks)
            hist = stock.history(period="5d")
            if not hist.empty:
                return ks
        except Exception:
            pass
        return raw + ".KQ"

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
<title>📊 종목 분석기</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3"></script>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:-apple-system,'Nanum Gothic',sans-serif; background:linear-gradient(135deg,#0f0c29,#302b63,#24243e); min-height:100vh; color:#E0E0E0; }

.top-bar { background:rgba(0,0,0,0.3); backdrop-filter:blur(10px); padding:16px 24px; position:sticky; top:0; z-index:100; border-bottom:1px solid rgba(255,255,255,0.1); }
.top-bar h1 { font-size:22px; color:#fff; display:inline; }
.search-box { display:flex; gap:8px; margin-top:12px; max-width:500px; }
.search-box input { flex:1; padding:10px 16px; border-radius:24px; border:1px solid rgba(255,255,255,0.2); background:rgba(255,255,255,0.1); color:#fff; font-size:16px; outline:none; }
.search-box input::placeholder { color:#888; }
.search-box input:focus { border-color:#1976D2; box-shadow:0 0 0 3px rgba(25,118,210,0.3); }
.search-box button { padding:10px 24px; border-radius:24px; border:none; background:linear-gradient(135deg,#1976D2,#1565C0); color:#fff; font-size:15px; font-weight:bold; cursor:pointer; }
.search-box button:hover { background:linear-gradient(135deg,#1E88E5,#1976D2); }
.search-box button:disabled { opacity:0.5; cursor:not-allowed; }

.quick-tags { margin-top:10px; display:flex; flex-wrap:wrap; gap:6px; }
.quick-tag { padding:4px 12px; border-radius:16px; border:1px solid rgba(255,255,255,0.15); background:rgba(255,255,255,0.05); color:#aaa; font-size:12px; cursor:pointer; transition:all 0.2s; }
.quick-tag:hover { background:rgba(25,118,210,0.3); border-color:#1976D2; color:#fff; }
.tab-btn { padding:6px 16px; border-radius:20px; border:1px solid rgba(255,255,255,0.2); background:rgba(255,255,255,0.05); color:#aaa; font-size:13px; cursor:pointer; }
.tab-btn.active { background:rgba(25,118,210,0.3); border-color:#1976D2; color:#fff; }

.container { max-width:1200px; margin:0 auto; padding:20px; }

.loading { text-align:center; padding:60px; }
.loading .spinner { width:48px; height:48px; border:4px solid rgba(255,255,255,0.1); border-top-color:#1976D2; border-radius:50%; animation:spin 0.8s linear infinite; margin:0 auto 16px; }
@keyframes spin { to { transform:rotate(360deg); } }

.error-msg { text-align:center; padding:40px; color:#F44336; font-size:16px; }

.stock-card { background:rgba(255,255,255,0.05); backdrop-filter:blur(10px); border:1px solid rgba(255,255,255,0.1); border-radius:16px; padding:24px; margin-bottom:24px; animation:fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity:0; transform:translateY(20px); } to { opacity:1; transform:translateY(0); } }

.card-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:20px; flex-wrap:wrap; gap:12px; }
.card-header h2 { color:#fff; font-size:24px; }
.ticker-badge { background:#1976D2; color:#fff; padding:2px 10px; border-radius:12px; font-size:13px; font-weight:bold; margin-right:8px; }
.sector { color:#888; font-size:13px; }
.price-area { text-align:right; }
.big-price { display:block; font-size:36px; font-weight:bold; color:#fff; }
.price-change { font-size:14px; padding:3px 10px; border-radius:12px; font-weight:bold; }
.price-up { background:rgba(76,175,80,0.2); color:#4CAF50; }
.price-down { background:rgba(244,67,54,0.2); color:#F44336; }
.mcap { color:#888; font-size:14px; margin-top:4px; }

.metrics-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:16px; margin-bottom:20px; }
.metric-card { background:rgba(255,255,255,0.05); border-radius:12px; padding:16px; }
.metric-title { font-size:14px; font-weight:bold; color:#90CAF9; margin-bottom:10px; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:8px; }
.metric-row { display:flex; justify-content:space-between; padding:5px 0; border-bottom:1px solid rgba(255,255,255,0.03); }
.metric-label { color:#999; font-size:13px; }
.metric-val { font-weight:bold; font-size:13px; }

.score-banner { display:flex; align-items:center; gap:20px; padding:16px 20px; border-radius:12px; margin-bottom:20px; }
.score-banner.A { background:rgba(76,175,80,0.15); border:1px solid rgba(76,175,80,0.3); }
.score-banner.B { background:rgba(33,150,243,0.15); border:1px solid rgba(33,150,243,0.3); }
.score-banner.C { background:rgba(255,193,7,0.15); border:1px solid rgba(255,193,7,0.3); }
.score-banner.D { background:rgba(255,152,0,0.15); border:1px solid rgba(255,152,0,0.3); }
.score-banner.F { background:rgba(244,67,54,0.15); border:1px solid rgba(244,67,54,0.3); }
.score-num { font-size:48px; font-weight:bold; }
.score-banner.A .score-num { color:#4CAF50; } .score-banner.B .score-num { color:#2196F3; }
.score-banner.C .score-num { color:#FFC107; } .score-banner.D .score-num { color:#FF9800; }
.score-banner.F .score-num { color:#F44336; }
.score-detail { flex:1; }
.score-grade { font-size:20px; font-weight:bold; color:#fff; }
.score-items { margin-top:6px; font-size:13px; color:#bbb; line-height:1.7; }

.w52 { margin:16px 0; padding:12px 16px; background:rgba(255,255,255,0.03); border-radius:8px; }
.w52-labels { display:flex; justify-content:space-between; font-size:12px; color:#888; margin-bottom:6px; }
.w52-track { position:relative; height:8px; background:rgba(255,255,255,0.1); border-radius:4px; }
.w52-fill { height:100%; background:linear-gradient(90deg,#4CAF50,#FFC107,#F44336); border-radius:4px; }
.w52-dot { position:absolute; top:-4px; width:16px; height:16px; background:#fff; border:3px solid #1976D2; border-radius:50%; transform:translateX(-50%); }

.charts-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:16px; }
.chart-wrap { background:rgba(255,255,255,0.03); border-radius:12px; padding:16px; }
@media(max-width:768px) { .charts-grid{grid-template-columns:1fr;} .card-header{flex-direction:column;} }
</style>
</head>
<body>
<div class="top-bar">
  <h1>📊 종목 분석기</h1>
  <div class="search-box">
    <input id="tickerInput" placeholder="티커 입력 (예: PLTR, 005930, 삼성전자)" autofocus />
    <button id="searchBtn" onclick="analyze()">분석</button>
  </div>
  <div style="margin-top:10px;display:flex;gap:8px;">
    <button class="tab-btn active" onclick="showTab('us',this)">🇺🇸 미국</button>
    <button class="tab-btn" onclick="showTab('kr',this)">🇰🇷 한국</button>
  </div>
  <div class="quick-tags" id="usTags"></div>
  <div class="quick-tags" id="krTags" style="display:none"></div>
</div>
<div class="container" id="results"></div>

<script>
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
  div.innerHTML = `
    <div class="card-header">
      <div>
        <h2>${s.name}</h2>
        <span class="ticker-badge">${s.ticker}</span>
        <span class="sector">${s.sector || ''} ${s.industry ? '· '+s.industry : ''}</span>
      </div>
      <div class="price-area">
        <span class="big-price">${fmtPrice(s.current_price)}</span>
        <span class="price-change ${changeClass}">${changeText}</span>
        <div class="mcap">${fmtCap(s.market_cap, curr)}</div>
      </div>
    </div>
    <div class="score-banner ${grade}">
      <div class="score-num">${s.score}</div>
      <div class="score-detail">
        <div class="score-grade">${gradeEmoji} 등급 ${grade}</div>
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
    <div class="charts-grid">
      <div class="chart-wrap"><canvas id="price_${idx}"></canvas></div>
      <div class="chart-wrap"><canvas id="per_${idx}"></canvas></div>
    </div>
    <div class="charts-grid">
      <div class="chart-wrap"><canvas id="rev_${idx}"></canvas></div>
      <div class="chart-wrap"><canvas id="margin_${idx}"></canvas></div>
    </div>`;
  c.appendChild(div);

  new Chart(document.getElementById('price_'+idx), {
    type:'line',
    data:{datasets:[{label:'주가 ('+sym+')',data:s.price_history,borderColor:'#1976D2',backgroundColor:'rgba(25,118,210,0.1)',fill:true,tension:0.3,pointRadius:0}]},
    options:{responsive:true,plugins:{title:{display:true,text:'주가 추이 (1년)',font:{size:14}}},scales:{x:{type:'time',time:{unit:'month'}}}}
  });
  new Chart(document.getElementById('per_'+idx), {
    type:'line',
    data:{datasets:[{label:'PER',data:s.per_history,borderColor:'#F44336',backgroundColor:'rgba(244,67,54,0.1)',fill:true,tension:0.3,pointRadius:0}]},
    options:{responsive:true,plugins:{title:{display:true,text:'PER 추이 (1년)',font:{size:14}}},scales:{x:{type:'time',time:{unit:'month'}}}}
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
}
</script>
</body>
</html>"""


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

        return {
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
