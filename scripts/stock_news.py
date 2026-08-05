#!/usr/bin/env python3
"""
매일 미국 증시 주요 뉴스를 수집하여 GitHub Issue로 게시하는 스크립트.

사용법:
    python scripts/stock_news.py

환경 변수:
    GH_TOKEN (선택): GitHub Issue 생성 시 사용. 설정하지 않으면 콘솔 출력만 수행.
    GH_REPO  (선택): GitHub Issue를 생성할 저장소 (예: owner/repo).
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError
from xml.etree import ElementTree

KST = timezone(timedelta(hours=9))


def fetch_rss(url: str, limit: int = 10) -> list[dict]:
    """RSS 피드에서 뉴스 항목을 가져온다."""
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
            items.append(
                {"title": title, "link": link, "description": desc, "pubDate": pub_date}
            )
        if len(items) >= limit:
            break
    return items


def clean_html(text: str) -> str:
    """간단한 HTML 태그 제거."""
    return re.sub(r"<[^>]+>", "", text).strip()


def collect_news() -> list[dict]:
    """여러 소스에서 증시 관련 뉴스를 수집한다."""
    feeds = [
        ("연합뉴스 경제", "https://www.yonhapnewstv.co.kr/category/news/economy/feed/"),
        ("MarketWatch Top Stories", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
        ("CNBC Economy", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258"),
        ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ]

    all_items = []
    for name, url in feeds:
        items = fetch_rss(url, limit=8)
        for item in items:
            item["source"] = name
            item["description"] = clean_html(item["description"])
        all_items.extend(items)
        print(f"[INFO] {name}: {len(items)}건 수집")

    return all_items


def filter_stock_news(items: list[dict]) -> list[dict]:
    """증시/주식 관련 키워드로 필터링한다."""
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


def build_report(items: list[dict]) -> str:
    """마크다운 형식의 리포트를 생성한다."""
    now = datetime.now(KST)
    date_str = now.strftime("%Y년 %m월 %d일 %H:%M KST")

    lines = [
        f"# 📊 일일 증시 뉴스 요약",
        f"",
        f"> 생성 시각: {date_str}",
        f"",
        f"---",
        f"",
    ]

    if not items:
        lines.append("수집된 뉴스가 없습니다.")
        return "\n".join(lines)

    seen_titles = set()
    count = 0
    for item in items:
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

        lines.append(f"### {count}. {title}")
        if source:
            lines.append(f"**출처**: {source}")
        if link:
            lines.append(f"**링크**: {link}")
        if desc:
            lines.append(f"")
            lines.append(f"{desc}")
        lines.append("")
        lines.append("---")
        lines.append("")

        if count >= 15:
            break

    lines.append(f"*총 {count}건의 뉴스가 수집되었습니다.*")
    return "\n".join(lines)


def create_github_issue(title: str, body: str) -> None:
    """gh CLI를 사용하여 GitHub Issue를 생성한다."""
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
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            print(f"[INFO] Issue 생성 완료: {result.stdout.strip()}")
        else:
            print(f"[WARN] Issue 생성 실패: {result.stderr.strip()}", file=sys.stderr)
            print("[INFO] 라벨 없이 재시도합니다...")
            cmd_no_label = [c for c in cmd if c not in ("--label", "stock-news")]
            result2 = subprocess.run(
                cmd_no_label, capture_output=True, text=True, timeout=30
            )
            if result2.returncode == 0:
                print(f"[INFO] Issue 생성 완료: {result2.stdout.strip()}")
            else:
                print(f"[ERROR] Issue 생성 최종 실패: {result2.stderr.strip()}", file=sys.stderr)
    except FileNotFoundError:
        print("[ERROR] gh CLI가 설치되어 있지 않습니다.", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("[ERROR] Issue 생성 시간 초과", file=sys.stderr)


def main() -> None:
    print("=" * 50)
    print("일일 증시 뉴스 수집 시작")
    print("=" * 50)

    items = collect_news()
    print(f"\n[INFO] 전체 {len(items)}건 수집 완료")

    filtered = filter_stock_news(items)
    print(f"[INFO] 증시 관련 {len(filtered)}건 필터링 완료\n")

    report = build_report(filtered)

    print(report)
    print()

    now = datetime.now(KST)
    issue_title = f"📊 일일 증시 뉴스 요약 - {now.strftime('%Y-%m-%d')}"
    create_github_issue(issue_title, report)

    print("\n[INFO] 완료!")


if __name__ == "__main__":
    main()
