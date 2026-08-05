from __future__ import annotations

from company_valuation.schema import Market
from company_valuation.tools.valuation import get_company_valuation


def test_kr_valuation_uses_krx_snapshot(monkeypatch):
    class FakeKRX:
        def market_snapshot(self, ticker: str):
            assert ticker == "005930"
            return {
                "ticker": "005930",
                "name": "삼성전자",
                "as_of": "2026-08-05",
                "price": 100000.0,
                "market_cap": 500_000_000_000_000.0,
                "shares_outstanding": 5_000_000_000.0,
                "pe": 12.0,
                "pb": 1.1,
                "source": "FinanceDataReader",
            }

    monkeypatch.setattr(
        "company_valuation.tools.valuation.KRXClient",
        FakeKRX,
    )
    monkeypatch.setattr(
        "company_valuation.tools.valuation._lookup_corp_code",
        lambda ticker: None,
    )

    result = get_company_valuation(query="005930", market="KR")
    assert result.market == Market.KR
    assert result.ticker == "005930"
    assert result.currency == "KRW"
    assert result.market_cap == 500_000_000_000_000.0
    assert result.multiples.pe == 12.0
    assert "FinanceDataReader" in result.source


def test_us_valuation_maps_fmp(monkeypatch):
    class FakeFMP:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def profile(self, symbol: str):
            return {
                "companyName": "Apple Inc.",
                "price": 190.0,
                "marketCap": 3_000_000_000_000,
                "sharesOutstanding": 15_000_000_000,
                "pe": 30.0,
            }

        def market_cap(self, symbol: str):
            return {"marketCap": 3_000_000_000_000, "date": "2026-08-05"}

        def enterprise_values(self, symbol: str, limit: int = 1):
            return [
                {
                    "date": "2026-08-05",
                    "enterpriseValue": 3_100_000_000_000,
                    "marketCapitalization": 3_000_000_000_000,
                }
            ]

        def ratios_ttm(self, symbol: str):
            return {
                "priceToEarningsRatioTTM": 30.0,
                "priceToBookRatioTTM": 45.0,
                "priceToSalesRatioTTM": 8.0,
                "enterpriseValueMultipleTTM": 22.0,
            }

        def key_metrics_ttm(self, symbol: str):
            return {}

        def balance_sheet(self, symbol: str, period: str = "annual", limit: int = 1):
            return [{"totalDebt": 100.0, "cashAndCashEquivalents": 50.0}]

    monkeypatch.setattr("company_valuation.tools.valuation.FMPClient", FakeFMP)
    result = get_company_valuation(query="AAPL", market="US")
    assert result.market == Market.US
    assert result.ticker == "AAPL"
    assert result.enterprise_value == 3_100_000_000_000
    assert result.multiples.pe == 30.0
    assert result.source == ["fmp"]
