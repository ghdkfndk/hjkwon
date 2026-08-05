from __future__ import annotations

from datetime import datetime
from typing import Any

from company_valuation.clients.fmp import FMPClient
from company_valuation.clients.opendart import REPORT_ANNUAL, OpenDartClient
from company_valuation.routing import normalize_kr_ticker
from company_valuation.schema import Fundamentals, Market
from company_valuation.tools.resolve import resolve_company
from company_valuation.tools.valuation import _parse_kr_amount, _pick_identity


def get_company_fundamentals(
    ticker: str | None = None,
    *,
    query: str | None = None,
    market: str | None = None,
    period: str = "annual",
    year: int | None = None,
) -> Fundamentals:
    """Fetch latest fundamentals for a US or KR listed company."""
    identity = _pick_identity(ticker=ticker, query=query, market=market)
    if identity.market == Market.US:
        return _fundamentals_us(identity.ticker, identity.name, period=period)
    return _fundamentals_kr(
        identity.ticker,
        name=identity.name,
        corp_code=identity.corp_code,
        year=year,
    )


def _fundamentals_us(ticker: str, name: str, period: str = "annual") -> Fundamentals:
    with FMPClient() as client:
        income = (client.income_statement(ticker, period=period, limit=1) or [None])[0] or {}
        balance = (client.balance_sheet(ticker, period=period, limit=1) or [None])[0] or {}

    return Fundamentals(
        market=Market.US,
        ticker=ticker.upper(),
        name=name,
        currency="USD",
        period=period,
        fiscal_year=str(income.get("calendarYear") or income.get("fillingDate") or "")[:4]
        or None,
        revenue=_num(income.get("revenue")),
        operating_income=_num(income.get("operatingIncome")),
        net_income=_num(income.get("netIncome")),
        total_assets=_num(balance.get("totalAssets")),
        total_liabilities=_num(balance.get("totalLiabilities")),
        total_equity=_num(balance.get("totalEquity") or balance.get("totalStockholdersEquity")),
        total_debt=_num(balance.get("totalDebt")),
        cash=_num(
            balance.get("cashAndCashEquivalents")
            or balance.get("cashAndShortTermInvestments")
        ),
        source=["fmp"],
    )


def _fundamentals_kr(
    ticker: str,
    name: str,
    corp_code: str | None,
    year: int | None,
) -> Fundamentals:
    ticker = normalize_kr_ticker(ticker)
    if not corp_code:
        matches = resolve_company(ticker, market="KR")
        corp_code = matches[0].corp_code if matches else None
        if matches:
            name = matches[0].name or name

    if not corp_code:
        raise RuntimeError(
            f"OpenDART corp_code not found for {ticker}. Set OPENDART_API_KEY and retry."
        )

    target_year = year or datetime.now().year
    with OpenDartClient() as client:
        rows: list[dict[str, Any]] = []
        used_year = None
        for y in range(target_year, target_year - 4, -1):
            rows = client.major_accounts(
                corp_code, bsns_year=str(y), reprt_code=REPORT_ANNUAL
            )
            if rows:
                used_year = y
                break

    if not rows:
        return Fundamentals(
            market=Market.KR,
            ticker=ticker,
            name=name,
            currency="KRW",
            source=["opendart"],
        )

    cfs = [r for r in rows if r.get("fs_div") == "CFS"]
    chosen = cfs or rows
    accounts = {
        (r.get("account_nm") or "").strip(): _parse_kr_amount(r.get("thstrm_amount"))
        for r in chosen
        if (r.get("account_nm") or "").strip()
    }
    # drop Nones
    accounts_f = {k: v for k, v in accounts.items() if v is not None}

    def pick(names: list[str]) -> float | None:
        for n in names:
            if n in accounts_f:
                return accounts_f[n]
        for key, value in accounts_f.items():
            for n in names:
                if n in key:
                    return value
        return None

    return Fundamentals(
        market=Market.KR,
        ticker=ticker,
        name=name,
        currency="KRW",
        period="annual",
        fiscal_year=str(used_year) if used_year else None,
        revenue=pick(["매출액", "수익(매출액)", "영업수익"]),
        operating_income=pick(["영업이익", "영업이익(손실)"]),
        net_income=pick(["당기순이익", "당기순이익(손실)", "당기순이익(손실)(순손실)"]),
        total_assets=pick(["자산총계"]),
        total_liabilities=pick(["부채총계"]),
        total_equity=pick(["자본총계", "자본금"]),
        total_debt=pick(["단기차입금", "장기차입금"]),
        cash=pick(["현금및현금성자산"]),
        source=["opendart"],
        raw_accounts=accounts_f,
    )


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