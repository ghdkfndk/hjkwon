from __future__ import annotations

from datetime import datetime
from typing import Any

from company_valuation.clients.fmp import FMPClient
from company_valuation.clients.krx import KRXClient
from company_valuation.clients.opendart import REPORT_ANNUAL, OpenDartClient
from company_valuation.routing import normalize_kr_ticker
from company_valuation.schema import (
    CompanyValuation,
    Confidence,
    Fundamentals,
    Market,
    Multiples,
)
from company_valuation.tools.resolve import resolve_company


def get_company_valuation(
    ticker: str | None = None,
    *,
    query: str | None = None,
    market: str | None = None,
) -> CompanyValuation:
    """
    Fetch market cap / EV / multiples for a US or KR listed company.
    """
    identity = _pick_identity(ticker=ticker, query=query, market=market)
    if identity.market == Market.US:
        return _valuation_us(identity.ticker, identity.name)
    return _valuation_kr(
        identity.ticker,
        name=identity.name,
        corp_code=identity.corp_code,
    )


def _pick_identity(
    ticker: str | None,
    query: str | None,
    market: str | None,
):
    text = (ticker or query or "").strip()
    if not text:
        raise ValueError("ticker or query is required")
    matches = resolve_company(text, market=market)
    if not matches:
        # Fall back to raw ticker routing
        m = (market or "").upper()
        if m == "KR" or text.isdigit():
            t = normalize_kr_ticker(text)
            from company_valuation.schema import CompanyIdentity

            return CompanyIdentity(
                market=Market.KR,
                ticker=t,
                name=t,
                exchange="KRX",
                currency="KRW",
            )
        from company_valuation.schema import CompanyIdentity

        return CompanyIdentity(
            market=Market.US,
            ticker=text.upper(),
            name=text.upper(),
            currency="USD",
        )
    return matches[0]


def _valuation_us(ticker: str, name: str) -> CompanyValuation:
    with FMPClient() as client:
        profile = client.profile(ticker) or {}
        mcap_row = client.market_cap(ticker) or {}
        ev_rows = client.enterprise_values(ticker, limit=1)
        ratios = client.ratios_ttm(ticker) or {}
        metrics = client.key_metrics_ttm(ticker) or {}
        balance = (client.balance_sheet(ticker, limit=1) or [None])[0] or {}

    ev = ev_rows[0] if ev_rows else {}
    market_cap = _num(
        mcap_row.get("marketCap")
        or profile.get("marketCap")
        or ev.get("marketCapitalization")
    )
    enterprise_value = _num(ev.get("enterpriseValue") or metrics.get("enterpriseValueTTM"))
    price = _num(profile.get("price"))
    shares = _num(
        profile.get("sharesOutstanding")
        or ev.get("numberOfShares")
        or metrics.get("sharesOutstandingTTM")
    )

    multiples = Multiples(
        pe=_num(ratios.get("priceToEarningsRatioTTM") or ratios.get("peRatioTTM") or profile.get("pe")),
        pb=_num(ratios.get("priceToBookRatioTTM") or ratios.get("pbRatioTTM")),
        ps=_num(ratios.get("priceToSalesRatioTTM") or ratios.get("priceToSalesRatioTTM")),
        ev_ebitda=_num(
            ratios.get("enterpriseValueMultipleTTM")
            or metrics.get("evToEBITDATTM")
            or metrics.get("enterpriseValueOverEBITDATTM")
        ),
        peg=_num(ratios.get("pegRatioTTM") or metrics.get("pegRatioTTM")),
    )

    fundamentals = Fundamentals(
        market=Market.US,
        ticker=ticker.upper(),
        name=profile.get("companyName") or name,
        currency="USD",
        total_debt=_num(balance.get("totalDebt") or ev.get("addTotalDebt")),
        cash=_num(
            balance.get("cashAndCashEquivalents")
            or balance.get("cashAndShortTermInvestments")
            or ev.get("minusCashAndCashEquivalents")
        ),
        source=["fmp"],
    )

    as_of = (
        str(mcap_row.get("date") or ev.get("date") or profile.get("ipoDate") or "")
        or datetime.utcnow().strftime("%Y-%m-%d")
    )

    sources = ["fmp"]
    confidence = Confidence.HIGH if market_cap else Confidence.LOW
    return CompanyValuation(
        market=Market.US,
        ticker=ticker.upper(),
        name=profile.get("companyName") or name,
        currency="USD",
        as_of=as_of[:10],
        market_cap=market_cap,
        enterprise_value=enterprise_value,
        price=price,
        shares_outstanding=shares,
        multiples=multiples,
        fundamentals=fundamentals,
        source=sources,
        confidence=confidence,
    )


def _valuation_kr(
    ticker: str,
    name: str,
    corp_code: str | None,
) -> CompanyValuation:
    ticker = normalize_kr_ticker(ticker)
    snap = KRXClient().market_snapshot(ticker) or {}
    display_name = snap.get("name") or name or ticker
    sources: list[str] = []
    notes: list[str] = []

    if snap.get("source"):
        sources.append(str(snap["source"]))

    market_cap = _num(snap.get("market_cap"))
    price = _num(snap.get("price"))
    shares = _num(snap.get("shares_outstanding"))
    pe = _num(snap.get("pe"))
    pb = _num(snap.get("pb"))

    total_debt = cash = None
    resolved_corp = corp_code
    if not resolved_corp:
        resolved_corp = _lookup_corp_code(ticker)

    if resolved_corp:
        try:
            debt_cash = _kr_debt_cash(resolved_corp)
            total_debt = debt_cash.get("total_debt")
            cash = debt_cash.get("cash")
            if debt_cash.get("source"):
                sources.append(debt_cash["source"])
            notes.extend(debt_cash.get("notes") or [])
        except RuntimeError as exc:
            notes.append(str(exc))
        except Exception as exc:  # noqa: BLE001
            notes.append(f"OpenDART fundamentals unavailable: {exc}")

    enterprise_value = None
    if market_cap is not None and (total_debt is not None or cash is not None):
        enterprise_value = market_cap + (total_debt or 0.0) - (cash or 0.0)
        notes.append("KR EV estimated as market_cap + total_debt - cash")

    fundamentals = Fundamentals(
        market=Market.KR,
        ticker=ticker,
        name=display_name,
        currency="KRW",
        total_debt=total_debt,
        cash=cash,
        source=[s for s in sources if s == "opendart"] or [],
    )

    confidence = Confidence.HIGH if market_cap and pe is not None else Confidence.MEDIUM
    if market_cap is None:
        confidence = Confidence.LOW

    return CompanyValuation(
        market=Market.KR,
        ticker=ticker,
        name=display_name,
        currency="KRW",
        as_of=snap.get("as_of"),
        market_cap=market_cap,
        enterprise_value=enterprise_value,
        price=price,
        shares_outstanding=shares,
        multiples=Multiples(pe=pe, pb=pb),
        fundamentals=fundamentals,
        source=list(dict.fromkeys(sources)),
        confidence=confidence,
        notes=notes,
    )


def _lookup_corp_code(ticker: str) -> str | None:
    try:
        with OpenDartClient() as client:
            rows = client.search(ticker, listed_only=True, limit=1)
    except RuntimeError:
        return None
    if not rows:
        return None
    return rows[0].get("corp_code")


def _kr_debt_cash(corp_code: str) -> dict[str, Any]:
    year = datetime.now().year
    notes: list[str] = []
    with OpenDartClient() as client:
        rows: list[dict[str, Any]] = []
        used_year = None
        for y in range(year, year - 4, -1):
            rows = client.major_accounts(
                corp_code, bsns_year=str(y), reprt_code=REPORT_ANNUAL
            )
            if rows:
                used_year = y
                break
        if not rows:
            return {"notes": ["No OpenDART major accounts found"], "source": "opendart"}

        # Prefer consolidated (CFS) accounts when present.
        cfs = [r for r in rows if r.get("fs_div") == "CFS"]
        chosen = cfs or rows
        accounts = _index_accounts(chosen)

        cash = _pick_account(
            accounts,
            [
                "현금및현금성자산",
                "현금및현금성자산 합계",
                "Cash and cash equivalents",
            ],
        )
        # Debt approximation from major accounts
        short_debt = _pick_account(accounts, ["단기차입금", "단기차입금 합계"])
        long_debt = _pick_account(
            accounts,
            ["장기차입금", "사채", "장기차입금및사채", "비유동부채"],
        )
        total_liab = _pick_account(accounts, ["부채총계", "부채총액"])

        total_debt = None
        if short_debt is not None or long_debt is not None:
            total_debt = (short_debt or 0.0) + (long_debt or 0.0)
            notes.append("KR debt approximated from short/long borrowings (major accounts)")
        elif total_liab is not None:
            total_debt = total_liab
            notes.append("KR debt fallback used total liabilities (less accurate)")

        notes.append(f"OpenDART major accounts year={used_year}")
        return {
            "cash": cash,
            "total_debt": total_debt,
            "source": "opendart",
            "notes": notes,
        }


def _index_accounts(rows: list[dict[str, Any]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in rows:
        name = (row.get("account_nm") or "").strip()
        amount = row.get("thstrm_amount")
        parsed = _parse_kr_amount(amount)
        if name and parsed is not None:
            out[name] = parsed
    return out


def _pick_account(accounts: dict[str, float], names: list[str]) -> float | None:
    for name in names:
        if name in accounts:
            return accounts[name]
    # partial contains match
    for key, value in accounts.items():
        for name in names:
            if name in key:
                return value
    return None


def _parse_kr_amount(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text or text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        import math

        num = float(value)
        if math.isnan(num) or math.isinf(num):
            return None
        return num
    except (TypeError, ValueError):
        return None