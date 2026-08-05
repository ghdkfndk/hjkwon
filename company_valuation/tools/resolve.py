from __future__ import annotations

from company_valuation.clients.fmp import FMPClient
from company_valuation.clients.opendart import OpenDartClient
from company_valuation.routing import detect_market, looks_like_ticker, normalize_kr_ticker
from company_valuation.schema import CompanyIdentity, Market


def resolve_company(query: str, market: str | None = None) -> list[CompanyIdentity]:
    """
    Resolve a company name or ticker to a normalized identity.

    Routing:
    - 6-digit numeric / Hangul name → KR
    - Latin ticker → US
    - ambiguous → try US then KR
    """
    q = query.strip()
    if not q:
        return []

    preferred = (market or detect_market(q) or "").upper() or None
    results: list[CompanyIdentity] = []

    if preferred == "KR":
        results = _resolve_kr(q)
        if not results and looks_like_ticker(q):
            results = _resolve_us(q)
    elif preferred == "US":
        results = _resolve_us(q)
        if not results:
            results = _resolve_kr(q)
    else:
        results = _resolve_us(q) or _resolve_kr(q)

    return results


def _resolve_us(query: str) -> list[CompanyIdentity]:
    try:
        client = FMPClient()
    except RuntimeError:
        return []

    with client:
        rows = client.search(query, limit=8)
        out: list[CompanyIdentity] = []
        for row in rows:
            symbol = (row.get("symbol") or "").upper()
            if not symbol:
                continue
            currency = (row.get("currency") or "USD").upper()
            if currency not in ("USD", "KRW"):
                currency = "USD"
            exchange = row.get("exchangeShortName") or row.get("stockExchange")
            # Prefer US exchanges when present
            out.append(
                CompanyIdentity(
                    market=Market.US,
                    ticker=symbol,
                    name=row.get("name") or symbol,
                    exchange=exchange,
                    currency=currency,  # type: ignore[arg-type]
                    extras={"fmp": row},
                )
            )
        # Stable preference: exact ticker match first
        q = query.strip().upper()
        out.sort(key=lambda c: (0 if c.ticker == q else 1, c.ticker))
        return out


def _resolve_kr(query: str) -> list[CompanyIdentity]:
    try:
        client = OpenDartClient()
    except RuntimeError:
        # Without OpenDART key, still allow ticker-only identity for KRX pricing.
        digits = "".join(ch for ch in query if ch.isdigit())
        if len(digits) in (5, 6):
            ticker = normalize_kr_ticker(digits)
            return [
                CompanyIdentity(
                    market=Market.KR,
                    ticker=ticker,
                    name=ticker,
                    exchange="KRX",
                    currency="KRW",
                )
            ]
        return []

    with client:
        rows = client.search(query, listed_only=True, limit=8)
        out: list[CompanyIdentity] = []
        for row in rows:
            stock_code = (row.get("stock_code") or "").strip()
            if not stock_code:
                continue
            ticker = normalize_kr_ticker(stock_code)
            out.append(
                CompanyIdentity(
                    market=Market.KR,
                    ticker=ticker,
                    name=row.get("corp_name") or ticker,
                    exchange="KRX",
                    currency="KRW",
                    corp_code=row.get("corp_code"),
                    extras={"opendart": row},
                )
            )
        return out