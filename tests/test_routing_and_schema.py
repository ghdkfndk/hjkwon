from __future__ import annotations

from company_valuation.routing import detect_market, normalize_kr_ticker
from company_valuation.schema import CompanyIdentity, CompanyValuation, Market, Multiples
from company_valuation.tools.valuation import _parse_kr_amount


def test_normalize_kr_ticker():
    assert normalize_kr_ticker("5930") == "005930"
    assert normalize_kr_ticker("005930") == "005930"


def test_detect_market():
    assert detect_market("삼성전자") == "KR"
    assert detect_market("005930") == "KR"
    assert detect_market("AAPL") == "US"
    assert detect_market("BRK.B") == "US"
    assert detect_market("something vague") is None


def test_schema_roundtrip():
    identity = CompanyIdentity(
        market=Market.US,
        ticker="AAPL",
        name="Apple Inc.",
        currency="USD",
        exchange="NASDAQ",
    )
    assert identity.model_dump()["ticker"] == "AAPL"

    valuation = CompanyValuation(
        market=Market.KR,
        ticker="005930",
        name="삼성전자",
        currency="KRW",
        market_cap=400_000_000_000_000,
        multiples=Multiples(pe=12.5, pb=1.2),
        source=["pykrx"],
    )
    payload = valuation.model_dump(mode="json")
    assert payload["market"] == "KR"
    assert payload["multiples"]["pe"] == 12.5


def test_parse_kr_amount():
    assert _parse_kr_amount("1,234,567") == 1234567.0
    assert _parse_kr_amount("-") is None
    assert _parse_kr_amount(None) is None
    assert _parse_kr_amount(10) == 10.0