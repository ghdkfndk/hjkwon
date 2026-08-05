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
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
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
    fool_analysis: dict[str, list[dict]],
    fool_general: list[dict],
) -> str:
    now = datetime.now(KST)
    date_str = now.strftime("%Y년 %m월 %d일 %H:%M KST")

    lines = [
        "# 📊 일일 증시 분석 리포트",
        "",
        f"> 생성 시각: {date_str}",
        "",
    ]

    # --- 1단계: 주요 뉴스 ---
    lines.append("## 📰 1단계: 주요 증시 뉴스")
    lines.append("")

    seen_titles: set[str] = set()
    count = 0
    for item in news_items:
        title = item["title"]
        if title in seen_titles:
            continue
        seen_titles.add(title)
        count += 1

        source = item.get("source", "")
        link = item.get("link", "")
        desc = item.get("description", "")
        if len(desc) > 200:
            desc = desc[:200] + "..."

        lines.append(f"**{count}.** {title}")
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
                lines.append(f"- [{art['title']}]({art['link']})")
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
            lines.append(f"- [{art['title']}]({art['link']})")
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

    # --- 리포트 ---
    print("\n[리포트] 생성 중...")
    report = build_report(filtered, ticker_headlines, fool_matched, fool_general)

    print("\n" + report + "\n")

    now = datetime.now(KST)
    issue_title = f"📊 일일 증시 분석 리포트 - {now.strftime('%Y-%m-%d')}"
    create_github_issue(issue_title, report)

    print("[INFO] 완료!")


if __name__ == "__main__":
    main()
