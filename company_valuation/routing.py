from __future__ import annotations

import re


_KR_TICKER = re.compile(r"^\d{1,6}$")
_US_TICKER = re.compile(r"^[A-Za-z][A-Za-z.\-]{0,9}$")
_HAS_HANGUL = re.compile(r"[\uac00-\ud7a3]")


def normalize_kr_ticker(ticker: str) -> str:
    digits = re.sub(r"\D", "", ticker)
    if not digits:
        raise ValueError(f"Invalid KR ticker: {ticker}")
    return digits.zfill(6)


def detect_market(query: str) -> str | None:
    """Return 'US', 'KR', or None if ambiguous."""
    q = query.strip()
    if not q:
        return None
    if _HAS_HANGUL.search(q):
        return "KR"
    if _KR_TICKER.match(q):
        return "KR"
    if _US_TICKER.match(q) and not q.isdigit():
        return "US"
    return None


def looks_like_ticker(query: str) -> bool:
    q = query.strip()
    return bool(_KR_TICKER.match(q) or _US_TICKER.match(q))