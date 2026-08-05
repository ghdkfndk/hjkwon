#!/usr/bin/env python3
"""
2단계 증시 분석 자동화 스크립트.

1단계: 여러 뉴스 소스에서 증시 뉴스를 수집하고 언급된 종목을 추출
2단계: Motley Fool에서 해당 종목의 투자 분석/의견을 조회

결과를 마크다운 리포트로 생성하여 GitHub Issue에 게시.

사용법:
    python scripts/stock_news.py

환경 변수:
    GH_TOKEN (선택): GitHub Issue 생성 시 사용. 미설정 시 콘솔 출력만.
    GH_REPO  (선택): GitHub Issue를 생성할 저장소 (예: owner/repo).
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import quote
from xml.etree import ElementTree

KST = timezone(timedelta(hours=9))

STOCK_TICKERS = {
    "NVDA": "엔비디아", "AAPL": "애플", "MSFT": "마이크로소프트",
    "GOOGL": "구글(알파벳)", "AMZN": "아마존", "META": "메타",
    "TSLA": "테슬라", "AMD": "AMD", "INTC": "인텔",
    "AVGO": "브로드컴", "MU": "마이크론", "PLTR": "팔란티어",
    "ARM": "ARM", "MRVL": "마벨", "QCOM": "퀄컴",
    "CRM": "세일즈포스", "NFLX": "넷플릭스", "UBER": "우버",
    "SHOP": "쇼피파이", "COIN": "코인베이스",
    "ANET": "아리스타 네트웍스", "SNDK": "샌디스크",
    "CAT": "캐터필러", "BA": "보잉", "JPM": "JP모건",
    "V": "비자", "WMT": "월마트", "DIS": "디즈니",
    "SPCX": "스페이스X", "RIVN": "리비안", "LLY": "일라이 릴리",
    "SMCI": "슈퍼마이크로", "ORCL": "오라클", "SKHY": "SK하이닉스",
    "ABNB": "에어비앤비", "SOFI": "소파이",
}

COMPANY_TO_TICKER = {}
for _t, _n in STOCK_TICKERS.items():
    COMPANY_TO_TICKER[_n] = _t
    COMPANY_TO_TICKER[_t] = _t

COMPANY_ALIASES = {
    "nvidia": "NVDA", "엔비디아": "NVDA",
    "apple": "AAPL", "애플": "AAPL",
    "microsoft": "MSFT", "마이크로소프트": "MSFT",
    "google": "GOOGL", "alphabet": "GOOGL", "구글": "GOOGL", "알파벳": "GOOGL",
    "amazon": "AMZN", "아마존": "AMZN",
    "meta": "META", "메타": "META", "facebook": "META",
    "tesla": "TSLA", "테슬라": "TSLA",
    "amd": "AMD",
    "intel": "INTC", "인텔": "INTC",
    "broadcom": "AVGO", "브로드컴": "AVGO",
    "micron": "MU", "마이크론": "MU",
    "palantir": "PLTR", "팔란티어": "PLTR",
    "arm": "ARM",
    "marvell": "MRVL", "마벨": "MRVL",
    "qualcomm": "QCOM", "퀄컴": "QCOM",
    "salesforce": "CRM", "세일즈포스": "CRM",
    "netflix": "NFLX", "넷플릭스": "NFLX",
    "uber": "UBER", "우버": "UBER",
    "shopify": "SHOP", "쇼피파이": "SHOP",
    "coinbase": "COIN", "코인베이스": "COIN",
    "arista": "ANET", "아리스타": "ANET",
    "sandisk": "SNDK", "샌디스크": "SNDK",
    "caterpillar": "CAT", "캐터필러": "CAT",
    "boeing": "BA", "보잉": "BA",
    "spacex": "SPCX", "스페이스x": "SPCX",
    "rivian": "RIVN", "리비안": "RIVN",
    "eli lilly": "LLY", "일라이 릴리": "LLY",
    "super micro": "SMCI", "supermicro": "SMCI", "슈퍼마이크로": "SMCI",
    "oracle": "ORCL", "오라클": "ORCL",
    "sk hynix": "SKHY", "sk하이닉스": "SKHY", "하이닉스": "SKHY",
    "disney": "DIS", "디즈니": "DIS",
    "airbnb": "ABNB", "에어비앤비": "ABNB",
    "sofi": "SOFI", "소파이": "SOFI",
}


# ---------------------------------------------------------------------------
# HTML 파싱 유틸리티
# ---------------------------------------------------------------------------

class TextExtractor(HTMLParser):
    """HTML에서 텍스트만 추출하는 간단한 파서."""
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts).strip()


def html_to_text(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html)
    return parser.get_text()


def clean_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


# ---------------------------------------------------------------------------
# 번역
# ---------------------------------------------------------------------------

_translate_cache: dict[str, str] = {}


def is_korean(text: str) -> bool:
    """텍스트에 한글이 포함되어 있는지 확인."""
    return bool(re.search(r"[가-힣]", text))


def translate_to_korean(text: str) -> str:
    """Google Translate 무료 엔드포인트로 영어→한국어 번역."""
    if is_korean(text):
        return text
    if text in _translate_cache:
        return _translate_cache[text]

    try:
        encoded = quote(text)
        url = (
            "https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl=en&tl=ko&dt=t&q={encoded}"
        )
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            translated = "".join(part[0] for part in data[0] if part[0])
            _translate_cache[text] = translated
            time.sleep(0.3)
            return translated
    except Exception as exc:
        print(f"[WARN] 번역 실패: {exc}", file=sys.stderr)
        return text


def translate_item(item: dict) -> dict:
    """뉴스 항목의 제목과 설명을 한국어로 번역."""
    translated = dict(item)
    if not is_korean(item["title"]):
        kr_title = translate_to_korean(item["title"])
        translated["title_kr"] = kr_title
        translated["title_original"] = item["title"]
    else:
        translated["title_kr"] = item["title"]
        translated["title_original"] = item["title"]

    if item.get("description") and not is_korean(item["description"]):
        translated["description_kr"] = translate_to_korean(item["description"][:300])
    else:
        translated["description_kr"] = item.get("description", "")

    return translated


# ---------------------------------------------------------------------------
# 1단계: 뉴스 수집
# ---------------------------------------------------------------------------

def fetch_rss(url: str, limit: int = 10) -> list[dict]:
    req = Request(url, headers={"User-Agent": "StockNewsBot/1.0"})
    try:
        with urlopen(req, timeout=15) as resp:
            tree = ElementTree.parse(resp)
    except (URLError, ElementTree.ParseError) as exc:
        print(f"[WARN] RSS 가져오기 실패: {url} -> {exc}", file=sys.stderr)
        return []

    items = []
    for item in tree.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        if title:
            items.append({
                "title": title, "link": link,
                "description": clean_html(desc), "pubDate": pub_date,
            })
        if len(items) >= limit:
            break
    return items


def collect_news() -> list[dict]:
    feeds = [
        ("연합뉴스 경제", "https://www.yonhapnewstv.co.kr/category/news/economy/feed/"),
        ("매일경제", "https://www.mk.co.kr/rss/30100041/"),
        ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
        ("CNBC Economy", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258"),
        ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ]
    all_items = []
    for name, url in feeds:
        items = fetch_rss(url, limit=8)
        for item in items:
            item["source"] = name
        all_items.extend(items)
        print(f"[INFO] {name}: {len(items)}건 수집")
    return all_items


def filter_stock_news(items: list[dict]) -> list[dict]:
    keywords = [
        "증시", "주식", "코스피", "코스닥", "나스닥", "다우", "S&P",
        "stock", "market", "Wall Street", "Nasdaq", "Dow", "S&P 500",
        "rally", "earnings", "Fed", "금리", "환율", "유가", "반도체",
        "AI", "테슬라", "엔비디아", "애플", "삼성", "semiconductor",
        "Tesla", "Nvidia", "Apple", "oil", "bond", "yield", "inflation",
    ]
    pattern = re.compile("|".join(re.escape(k) for k in keywords), re.IGNORECASE)
    filtered = [
        item for item in items
        if pattern.search(item["title"]) or pattern.search(item["description"])
    ]
    return filtered if filtered else items[:10]


# ---------------------------------------------------------------------------
# 종목 추출
# ---------------------------------------------------------------------------

def extract_tickers(items: list[dict]) -> dict[str, list[str]]:
    """뉴스 항목에서 종목 티커와 관련 헤드라인을 추출한다."""
    ticker_headlines: dict[str, list[str]] = {}

    for item in items:
        text = f"{item['title']} {item['description']}".lower()
        found: set[str] = set()

        for alias, ticker in COMPANY_ALIASES.items():
            if alias.lower() in text:
                found.add(ticker)

        for ticker in STOCK_TICKERS:
            if re.search(rf"\b{re.escape(ticker)}\b", item["title"], re.IGNORECASE):
                found.add(ticker)

        for ticker in found:
            ticker_headlines.setdefault(ticker, [])
            if item["title"] not in ticker_headlines[ticker]:
                ticker_headlines[ticker].append(item["title"])

    return ticker_headlines


# ---------------------------------------------------------------------------
# 감성 분석
# ---------------------------------------------------------------------------

POSITIVE_WORDS_EN = {
    "surge", "surges", "surged", "surging", "soar", "soars", "soared", "soaring",
    "rally", "rallies", "rallied", "gain", "gains", "gained", "rise", "rises",
    "rose", "rising", "jump", "jumps", "jumped", "record high", "all-time high",
    "beat", "beats", "topped", "outperform", "upgrade", "upgrades", "upgraded",
    "bullish", "boom", "booming", "growth", "strong", "robust", "optimism",
    "positive", "profit", "profitable", "breakthrough", "accelerate", "upside",
    "buy", "outperform", "overweight", "best", "boost", "boosted",
    "fantastic", "magnificent", "brilliant", "better", "recover", "recovery",
}
NEGATIVE_WORDS_EN = {
    "fall", "falls", "fell", "falling", "drop", "drops", "dropped", "dropping",
    "decline", "declines", "declined", "declining", "plunge", "plunges", "plunged",
    "crash", "crashes", "crashed", "crashing", "sink", "sinks", "sank", "sinking",
    "loss", "losses", "lost", "losing", "sell", "selloff", "sell-off",
    "bearish", "recession", "slowdown", "slowing", "weak", "weaker",
    "downgrade", "downgrades", "downgraded", "underperform", "underweight",
    "risk", "risky", "warning", "warns", "warned", "fear", "fears",
    "concern", "concerns", "worried", "worries", "worst", "crisis",
    "inflation", "debt", "layoff", "layoffs", "cut", "cuts", "slash",
    "dump", "dumped", "crushed", "trouble", "pain", "struggling",
}
POSITIVE_WORDS_KR = {
    "급등", "상승", "강세", "호실적", "최고치", "경신", "돌파", "호재",
    "성장", "개선", "회복", "반등", "매수", "상향", "흑자", "호조",
    "낙관", "긍정", "기대", "활황", "호황", "돌풍",
}
NEGATIVE_WORDS_KR = {
    "급락", "하락", "약세", "부진", "폭락", "최저", "악재", "손실",
    "감소", "둔화", "침체", "매도", "하향", "적자", "부정", "우려",
    "위험", "위기", "불안", "리스크", "경고", "충격", "하방",
}


def analyze_sentiment(text: str) -> tuple[str, float]:
    """텍스트의 감성을 분석하여 (판정, 점수)를 반환한다.
    점수: -1.0(매우 부정) ~ +1.0(매우 긍정), 0 근처는 중립.
    """
    text_lower = text.lower()
    words = set(re.findall(r"[a-z\-]+", text_lower))
    kr_chars = text_lower

    pos_count = len(words & POSITIVE_WORDS_EN)
    neg_count = len(words & NEGATIVE_WORDS_EN)

    for phrase in ("record high", "all-time high", "sell-off", "sell off"):
        if phrase in text_lower:
            if phrase in ("record high", "all-time high"):
                pos_count += 1
            else:
                neg_count += 1

    for w in POSITIVE_WORDS_KR:
        if w in kr_chars:
            pos_count += 1
    for w in NEGATIVE_WORDS_KR:
        if w in kr_chars:
            neg_count += 1

    total = pos_count + neg_count
    if total == 0:
        return "중립 ⚪", 0.0

    score = (pos_count - neg_count) / total
    if score > 0.2:
        return "긍정 🟢", round(score, 2)
    elif score < -0.2:
        return "부정 🔴", round(score, 2)
    else:
        return "중립 ⚪", round(score, 2)


def build_sentiment_table(
    ticker_headlines: dict[str, list[str]],
    all_items: list[dict],
) -> list[dict]:
    """종목별 감성 분석 결과 테이블 데이터를 생성한다."""
    results = []

    item_map: dict[str, dict] = {}
    for item in all_items:
        item_map[item["title"]] = item

    for ticker, headlines in sorted(ticker_headlines.items()):
        name = STOCK_TICKERS.get(ticker, ticker)
        sentiments = []
        for headline in headlines:
            item = item_map.get(headline, {})
            full_text = f"{headline} {item.get('description', '')}"
            sentiment, score = analyze_sentiment(full_text)
            sentiments.append({
                "ticker": ticker,
                "name": name,
                "headline": headline,
                "sentiment": sentiment,
                "score": score,
            })

        if sentiments:
            avg_score = sum(s["score"] for s in sentiments) / len(sentiments)
            if avg_score > 0.2:
                overall = "긍정 🟢"
            elif avg_score < -0.2:
                overall = "부정 🔴"
            else:
                overall = "중립 ⚪"

            results.append({
                "ticker": ticker,
                "name": name,
                "news_count": len(sentiments),
                "overall": overall,
                "avg_score": round(avg_score, 2),
                "details": sentiments,
            })

    results.sort(key=lambda x: x["news_count"], reverse=True)
    return results


# ---------------------------------------------------------------------------
# 2단계: Motley Fool 분석 조회
# ---------------------------------------------------------------------------

def fetch_url(url: str) -> str:
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; StockNewsBot/1.0)",
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        with urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (URLError, HTTPError) as exc:
        print(f"[WARN] 페이지 가져오기 실패: {url} -> {exc}", file=sys.stderr)
        return ""


def fetch_fool_articles_for_ticker(ticker: str) -> list[dict]:
    """Motley Fool에서 특정 종목 관련 최신 기사를 가져온다."""
    urls = [
        f"https://www.fool.com/quote/{ticker}/",
        f"https://www.fool.com/quote/NYSE/{ticker}/",
        f"https://www.fool.com/quote/NASDAQ/{ticker}/",
    ]
    html = ""
    for u in urls:
        html = fetch_url(u)
        if html:
            break
    if not html:
        return []

    articles = []

    title_pattern = re.compile(
        r'<a[^>]*href="(/investing/\d{4}/\d{2}/\d{2}/[^"]*)"[^>]*>\s*(.*?)\s*</a>',
        re.DOTALL,
    )

    for match in title_pattern.finditer(html):
        link = "https://www.fool.com" + match.group(1)
        raw_title = match.group(2)
        title = html_to_text(raw_title)
        if title and len(title) > 15:
            articles.append({"title": title, "link": link})
        if len(articles) >= 5:
            break

    if not articles:
        search_url = f"https://www.fool.com/search/solr.aspx?q={ticker}"
        html = fetch_url(search_url)
        if html:
            for match in title_pattern.finditer(html):
                link = "https://www.fool.com" + match.group(1)
                raw_title = match.group(2)
                title = html_to_text(raw_title)
                if title and len(title) > 15:
                    articles.append({"title": title, "link": link})
                if len(articles) >= 3:
                    break

    return articles


def fetch_fool_investing_news() -> list[dict]:
    """Motley Fool 투자 뉴스 메인 페이지에서 최신 기사 목록을 가져온다."""
    url = "https://www.fool.com/investing-news/"
    html = fetch_url(url)
    if not html:
        return []

    articles = []
    pattern = re.compile(
        r'<a[^>]*href="(/investing/\d{4}/\d{2}/\d{2}/[^"]*)"[^>]*>\s*(.*?)\s*</a>',
        re.DOTALL,
    )
    for match in pattern.finditer(html):
        link = "https://www.fool.com" + match.group(1)
        raw_title = match.group(2)
        title = html_to_text(raw_title)
        if title and len(title) > 20:
            articles.append({"title": title, "link": link})
        if len(articles) >= 20:
            break

    return articles


def match_fool_to_tickers(
    fool_articles: list[dict], tickers: set[str]
) -> dict[str, list[dict]]:
    """Fool 기사를 티커별로 매칭한다."""
    result: dict[str, list[dict]] = {}
    for article in fool_articles:
        text = article["title"].lower()
        for alias, ticker in COMPANY_ALIASES.items():
            if ticker in tickers and alias.lower() in text:
                result.setdefault(ticker, [])
                if article not in result[ticker]:
                    result[ticker].append(article)

        for ticker in tickers:
            if re.search(rf"\b{re.escape(ticker)}\b", article["title"], re.IGNORECASE):
                result.setdefault(ticker, [])
                if article not in result[ticker]:
                    result[ticker].append(article)

    return result


# ---------------------------------------------------------------------------
# 리포트 생성
# ---------------------------------------------------------------------------

def build_report(
    news_items: list[dict],
    ticker_headlines: dict[str, list[str]],
    sentiment_data: list[dict],
    chart_results: list[dict],
    fool_analysis: dict[str, list[dict]],
    fool_general: list[dict],
    gh_repo: str = "",
) -> str:
    now = datetime.now(KST)
    date_str = now.strftime("%Y년 %m월 %d일 %H:%M KST")

    lines = [
        "# 📊 일일 증시 분석 리포트",
        "",
        f"> 생성 시각: {date_str}",
        "",
    ]

    # --- 결론 먼저 ---
    if chart_results:
        grade_emoji = {"A": "🟢", "B": "🔵", "C": "🟡", "D": "🟠", "F": "🔴"}
        sorted_by_score = sorted(chart_results, key=lambda x: x.get("score", 0), reverse=True)

        lines.append("## 🏆 오늘의 결론")
        lines.append("")
        lines.append("| 종목 | 스코어 | 등급 | 핵심 근거 |")
        lines.append("|---|---|---|---|")
        for cr in sorted_by_score:
            emoji = grade_emoji.get(cr.get("grade", "C"), "⚪")
            details = cr.get("score_details", [])
            reason = " / ".join(details[:2]) if details else "-"
            lines.append(
                f"| **{cr['name']}** ({cr['ticker']}) "
                f"| **{cr.get('score', '-')}**/100 "
                f"| {emoji} {cr.get('grade', '-')} "
                f"| {reason} |"
            )
        lines.append("")

        best = sorted_by_score[0]
        worst = sorted_by_score[-1]
        best_emoji = grade_emoji.get(best.get("grade", "C"), "⚪")
        worst_emoji = grade_emoji.get(worst.get("grade", "C"), "⚪")
        lines.append(
            f"> {best_emoji} **가장 유망**: {best['name']}({best['ticker']}) "
            f"— 스코어 {best.get('score', '-')}점"
        )
        if len(sorted_by_score) > 1:
            lines.append(
                f"> {worst_emoji} **가장 주의**: {worst['name']}({worst['ticker']}) "
                f"— 스코어 {worst.get('score', '-')}점"
            )
        lines.append("")

    # --- 감성 분석 요약도 상단에 ---
    if sentiment_data:
        lines.append("### 📰 뉴스 감성 요약")
        lines.append("")
        for s in sentiment_data:
            lines.append(f"- **{s['name']}**({s['ticker']}): {s['overall']} (점수 {s['avg_score']:+.2f})")
        lines.append("")

    lines.append("---")
    lines.append("")

    # --- 1단계: 주요 뉴스 ---
    lines.append("## 📰 1단계: 주요 증시 뉴스")
    lines.append("")

    seen_titles: set[str] = set()
    count = 0
    for item in news_items:
        title_kr = item.get("title_kr", item["title"])
        title_original = item.get("title_original", item["title"])
        if title_original in seen_titles:
            continue
        seen_titles.add(title_original)
        count += 1

        source = item.get("source", "")
        link = item.get("link", "")
        desc = item.get("description_kr", item.get("description", ""))
        if len(desc) > 250:
            desc = desc[:250] + "..."

        lines.append(f"**{count}.** {title_kr}")
        if title_kr != title_original:
            lines.append(f"  - *원문: {title_original}*")
        parts = []
        if source:
            parts.append(f"출처: {source}")
        if link:
            parts.append(f"[링크]({link})")
        if parts:
            lines.append(f"  - {' | '.join(parts)}")
        if desc:
            lines.append(f"  - {desc}")
        lines.append("")

        if count >= 12:
            break

    # --- 언급 종목 요약 ---
    lines.append("---")
    lines.append("")
    lines.append("## 🏷️ 뉴스에서 언급된 주요 종목")
    lines.append("")

    if ticker_headlines:
        lines.append("| 종목 | 티커 | 관련 뉴스 수 |")
        lines.append("|---|---|---|")
        sorted_tickers = sorted(
            ticker_headlines.items(), key=lambda x: len(x[1]), reverse=True
        )
        for ticker, headlines in sorted_tickers:
            name = STOCK_TICKERS.get(ticker, ticker)
            lines.append(f"| {name} | {ticker} | {len(headlines)}건 |")
        lines.append("")
    else:
        lines.append("언급된 종목이 없습니다.")
        lines.append("")

    # --- 감성 분석 ---
    lines.append("---")
    lines.append("")
    lines.append("## 📊 종목별 뉴스 감성 분석")
    lines.append("")

    if sentiment_data:
        lines.append("| 종목 | 티커 | 뉴스 수 | 감성 판정 | 점수 |")
        lines.append("|---|---|---|---|---|")
        for s in sentiment_data:
            lines.append(
                f"| {s['name']} | {s['ticker']} | {s['news_count']}건 "
                f"| {s['overall']} | {s['avg_score']:+.2f} |"
            )
        lines.append("")
        lines.append("> 점수 범위: -1.00(매우 부정) ~ +1.00(매우 긍정)")
        lines.append("")

        lines.append("<details>")
        lines.append("<summary>📋 뉴스별 상세 감성 분석 (클릭하여 펼치기)</summary>")
        lines.append("")
        for s in sentiment_data:
            lines.append(f"**{s['name']} ({s['ticker']})**")
            lines.append("")
            lines.append("| 뉴스 제목 | 감성 |")
            lines.append("|---|---|")
            for d in s["details"]:
                title_short = d["headline"][:60] + "..." if len(d["headline"]) > 60 else d["headline"]
                lines.append(f"| {title_short} | {d['sentiment']} |")
            lines.append("")
        lines.append("</details>")
        lines.append("")
    else:
        lines.append("감성 분석할 종목이 없습니다.")
        lines.append("")

    # --- 종목 차트 + 스코어 ---
    if chart_results:
        lines.append("---")
        lines.append("")
        lines.append("## 📈 종목별 투자 스코어 & 차트")
        lines.append("")

        grade_emoji = {"A": "🟢", "B": "🔵", "C": "🟡", "D": "🟠", "F": "🔴"}

        lines.append("### 스코어 요약")
        lines.append("")
        lines.append("| 종목 | 현재가 | 시총 | PER | PBR | 스코어 | 등급 |")
        lines.append("|---|---|---|---|---|---|---|")
        for cr in sorted(chart_results, key=lambda x: x.get("score", 0), reverse=True):
            price_str = f"${cr['current_price']:.2f}" if cr.get("current_price") else "N/A"
            emoji = grade_emoji.get(cr.get("grade", "C"), "⚪")

            pe_val = cr.get("pe_ratio", "N/A")
            if pe_val != "N/A":
                pe_f = float(pe_val)
                if pe_f < 0:
                    pe_label = f"{pe_val} (적자)"
                elif pe_f < 15:
                    pe_label = f"{pe_val} (저평가)"
                elif pe_f < 25:
                    pe_label = f"{pe_val} (적정)"
                elif pe_f < 40:
                    pe_label = f"{pe_val} (고평가)"
                else:
                    pe_label = f"{pe_val} (매우 고평가)"
            else:
                pe_label = "N/A"

            pb_val = cr.get("pb_ratio", "N/A")
            if pb_val != "N/A":
                pb_f = float(pb_val)
                if pb_f < 1:
                    pb_label = f"{pb_val} (저평가)"
                elif pb_f < 3:
                    pb_label = f"{pb_val} (적정)"
                elif pb_f < 10:
                    pb_label = f"{pb_val} (고평가)"
                else:
                    pb_label = f"{pb_val} (매우 고평가)"
            else:
                pb_label = "N/A"

            lines.append(
                f"| {cr['name']} ({cr['ticker']}) | {price_str} "
                f"| {cr['market_cap']} | {pe_label} | {pb_label} "
                f"| **{cr.get('score', 'N/A')}**/100 | {emoji} {cr.get('grade', '-')} |"
            )
        lines.append("")
        lines.append("> 스코어 = 모멘텀(25) + 밸류에이션(25) + 안정성(25) + 52주 위치(25)")
        lines.append("> 등급: A(80+) 🟢 | B(65+) 🔵 | C(50+) 🟡 | D(35+) 🟠 | F(<35) 🔴")
        lines.append("")
        lines.append("<details>")
        lines.append("<summary>📖 PER·PBR 보는 법 (클릭하여 펼치기)</summary>")
        lines.append("")
        lines.append("**PER (주가수익비율)** = 주가 ÷ 주당순이익(EPS)")
        lines.append("- 이 회사의 1년 이익 대비 주가가 몇 배인지를 보는 지표")
        lines.append("- PER 15 = \"이 회사가 현재 속도로 15년 벌면 시가총액만큼 번다\"는 의미")
        lines.append("- **낮을수록** 이익 대비 주가가 저렴 (단, 업종별 평균이 다름)")
        lines.append("- 일반적 기준: ~15 저평가 | 15~25 적정 | 25~40 고평가 | 40+ 매우 고평가")
        lines.append("- 적자 기업은 PER이 마이너스(-)이므로 의미 없음")
        lines.append("")
        lines.append("**PBR (주가순자산비율)** = 주가 ÷ 주당순자산(BPS)")
        lines.append("- 회사의 순자산(자산-부채) 대비 주가가 몇 배인지를 보는 지표")
        lines.append("- PBR 1 = \"회사를 청산하면 투자금만큼 돌려받을 수 있다\"는 의미")
        lines.append("- **1 미만**이면 자산가치보다 싸게 거래 중 (저평가 가능성)")
        lines.append("- 기술주는 PBR이 높은 게 보통 (무형자산·성장성 반영)")
        lines.append("- 일반적 기준: ~1 저평가 | 1~3 적정 | 3~10 고평가 | 10+ 매우 고평가")
        lines.append("")
        lines.append("**스코어에서 활용하는 방법**")
        lines.append("- PER이 적정 범위(15~25)에 있으면 밸류에이션 점수 높음")
        lines.append("- PER이 너무 높으면(80+) 과열 신호로 점수 낮음")
        lines.append("- PBR은 핵심 지표 테이블에서 참고용으로 제공")
        lines.append("")
        lines.append("</details>")
        lines.append("")

        for cr in chart_results:
            lines.append(f"### {cr['name']} ({cr['ticker']}) — {grade_emoji.get(cr.get('grade', 'C'), '')} 등급 {cr.get('grade', '-')} ({cr.get('score', 'N/A')}점)")
            lines.append("")

            if cr.get("score_details"):
                for detail in cr["score_details"]:
                    lines.append(f"- {detail}")
                lines.append("")

            if gh_repo and cr.get("chart_path"):
                filename = os.path.basename(cr["chart_path"])
                img_url = f"https://raw.githubusercontent.com/{gh_repo}/main/charts/{filename}"
                lines.append(f"![{cr['name']} 차트]({img_url})")
                lines.append("")
            elif cr.get("chart_path"):
                lines.append(f"*(차트: {cr['chart_path']})*")
                lines.append("")

    # --- 2단계: Motley Fool 분석 ---
    lines.append("---")
    lines.append("")
    lines.append("## 🔍 2단계: Motley Fool 투자 분석")
    lines.append("")

    if fool_analysis:
        for ticker, articles in fool_analysis.items():
            name = STOCK_TICKERS.get(ticker, ticker)
            lines.append(f"### {name} ({ticker})")
            lines.append("")
            for art in articles[:3]:
                title_kr = art.get("title_kr", art["title"])
                lines.append(f"- [{title_kr}]({art['link']})")
                if title_kr != art["title"]:
                    lines.append(f"  - *원문: {art['title']}*")
            lines.append("")
    else:
        lines.append("해당 종목에 대한 Motley Fool 분석이 없습니다.")
        lines.append("")

    # --- Fool 일반 투자 뉴스 ---
    if fool_general:
        lines.append("---")
        lines.append("")
        lines.append("## 📋 Motley Fool 오늘의 추천 기사")
        lines.append("")
        for art in fool_general[:8]:
            title_kr = art.get("title_kr", art["title"])
            lines.append(f"- [{title_kr}]({art['link']})")
            if title_kr != art["title"]:
                lines.append(f"  - *원문: {art['title']}*")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "*이 리포트는 자동 생성되었습니다. "
        "투자 결정은 본인의 판단에 따라 신중하게 해주세요.*"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# GitHub Issue 생성
# ---------------------------------------------------------------------------

def create_github_issue(title: str, body: str) -> None:
    repo = os.environ.get("GH_REPO", "")
    if not repo:
        print("[INFO] GH_REPO가 설정되지 않아 Issue 생성을 건너뜁니다.")
        return

    cmd = [
        "gh", "issue", "create",
        "--repo", repo,
        "--title", title,
        "--body", body,
        "--label", "stock-news",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"[INFO] Issue 생성 완료: {result.stdout.strip()}")
        else:
            print(f"[WARN] Issue 생성 실패 (라벨 없이 재시도): {result.stderr.strip()}", file=sys.stderr)
            cmd_no_label = [c for c in cmd if c not in ("--label", "stock-news")]
            result2 = subprocess.run(cmd_no_label, capture_output=True, text=True, timeout=30)
            if result2.returncode == 0:
                print(f"[INFO] Issue 생성 완료: {result2.stdout.strip()}")
            else:
                print(f"[ERROR] Issue 생성 최종 실패: {result2.stderr.strip()}", file=sys.stderr)
    except FileNotFoundError:
        print("[ERROR] gh CLI가 설치되어 있지 않습니다.", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("[ERROR] Issue 생성 시간 초과", file=sys.stderr)


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("  📊 2단계 증시 분석 리포트 생성")
    print("=" * 60)

    # --- 1단계 ---
    print("\n[1단계] 뉴스 수집 중...")
    all_news = collect_news()
    print(f"[INFO] 전체 {len(all_news)}건 수집")

    filtered = filter_stock_news(all_news)
    print(f"[INFO] 증시 관련 {len(filtered)}건 필터링")

    ticker_headlines = extract_tickers(filtered)
    tickers_found = set(ticker_headlines.keys())
    print(f"[INFO] 언급 종목 {len(tickers_found)}개: {', '.join(sorted(tickers_found))}")

    # --- 감성 분석 ---
    print("\n[감성분석] 종목별 뉴스 감성 분석 중...")
    sentiment_data = build_sentiment_table(ticker_headlines, filtered)
    for s in sentiment_data:
        print(f"[INFO] {s['name']}({s['ticker']}): {s['overall']} (점수: {s['avg_score']:+.2f})")

    # --- 번역 ---
    print("\n[번역] 영어 기사 한국어 번역 중...")
    filtered = [translate_item(item) for item in filtered]
    en_count = sum(1 for item in filtered if item.get("title_kr") != item.get("title_original"))
    print(f"[INFO] {en_count}건 번역 완료")

    # --- 2단계 ---
    print("\n[2단계] Motley Fool 분석 조회 중...")

    fool_general = fetch_fool_investing_news()
    print(f"[INFO] Fool 일반 기사 {len(fool_general)}건 수집")

    fool_matched = match_fool_to_tickers(fool_general, tickers_found)

    for ticker in tickers_found:
        if ticker not in fool_matched:
            arts = fetch_fool_articles_for_ticker(ticker)
            if arts:
                fool_matched[ticker] = arts
                print(f"[INFO] {ticker}: Fool 개별 페이지에서 {len(arts)}건 조회")

    matched_count = sum(len(v) for v in fool_matched.values())
    print(f"[INFO] Fool 매칭 완료: {len(fool_matched)}개 종목, 총 {matched_count}건")

    # Fool 기사 번역
    print("\n[번역] Motley Fool 기사 번역 중...")
    for ticker, articles in fool_matched.items():
        for art in articles:
            kr = translate_to_korean(art["title"])
            art["title_kr"] = kr
    for art in fool_general:
        kr = translate_to_korean(art["title"])
        art["title_kr"] = kr
    print("[INFO] Fool 기사 번역 완료")

    # --- 차트 생성 ---
    chart_results = []
    try:
        from scripts.stock_charts import generate_charts_for_tickers
        print("\n[차트] 종목별 1개월 차트 생성 중...")
        chart_results = generate_charts_for_tickers(
            list(tickers_found), STOCK_TICKERS, "charts"
        )
        print(f"[INFO] {len(chart_results)}개 종목 차트 생성 완료")
    except ImportError:
        try:
            from stock_charts import generate_charts_for_tickers
            print("\n[차트] 종목별 1개월 차트 생성 중...")
            chart_results = generate_charts_for_tickers(
                list(tickers_found), STOCK_TICKERS, "charts"
            )
            print(f"[INFO] {len(chart_results)}개 종목 차트 생성 완료")
        except ImportError:
            print("\n[WARN] stock_charts 모듈을 찾을 수 없습니다. 차트 생성을 건너뜁니다.")

    # --- 차트를 GitHub에 업로드 ---
    gh_repo = os.environ.get("GH_REPO", "")
    if gh_repo and chart_results:
        print("\n[업로드] 차트 이미지를 GitHub에 커밋 중...")
        try:
            subprocess.run(["git", "add", "charts/"], capture_output=True, timeout=10)
            subprocess.run(
                ["git", "commit", "-m", "Update stock charts"],
                capture_output=True, timeout=10,
            )
            subprocess.run(
                ["git", "push"], capture_output=True, timeout=30,
            )
            print("[INFO] 차트 업로드 완료")
        except Exception as exc:
            print(f"[WARN] 차트 업로드 실패: {exc}", file=sys.stderr)

    # --- 리포트 ---
    print("\n[리포트] 생성 중...")
    report = build_report(
        filtered, ticker_headlines, sentiment_data, chart_results,
        fool_matched, fool_general, gh_repo,
    )

    print("\n" + report + "\n")

    now = datetime.now(KST)
    issue_title = f"📊 일일 증시 분석 리포트 - {now.strftime('%Y-%m-%d')}"
    create_github_issue(issue_title, report)

    print("[INFO] 완료!")


if __name__ == "__main__":
    main()
