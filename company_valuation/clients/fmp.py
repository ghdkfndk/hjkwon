from __future__ import annotations

from typing import Any

import httpx

from company_valuation.config import require_fmp_key

BASE_URL = "https://financialmodelingprep.com/stable"


class FMPClient:
    """Financial Modeling Prep client for US (and some global) listed equities."""

    def __init__(self, api_key: str | None = None, timeout: float = 30.0) -> None:
        self.api_key = api_key or require_fmp_key()
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> FMPClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = {"apikey": self.api_key}
        if params:
            query.update(params)
        response = self._client.get(f"{BASE_URL}{path}", params=query)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and data.get("Error Message"):
            raise RuntimeError(data["Error Message"])
        return data

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        data = self._get("/search-symbol", {"query": query, "limit": limit})
        if not data:
            data = self._get("/search-name", {"query": query, "limit": limit})
        return data if isinstance(data, list) else []

    def profile(self, symbol: str) -> dict[str, Any] | None:
        data = self._get("/profile", {"symbol": symbol.upper()})
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict) and data:
            return data
        return None

    def market_cap(self, symbol: str) -> dict[str, Any] | None:
        data = self._get("/market-capitalization", {"symbol": symbol.upper()})
        if isinstance(data, list) and data:
            return data[0]
        return None

    def enterprise_values(self, symbol: str, limit: int = 1) -> list[dict[str, Any]]:
        data = self._get(
            "/enterprise-values",
            {"symbol": symbol.upper(), "limit": limit},
        )
        return data if isinstance(data, list) else []

    def ratios_ttm(self, symbol: str) -> dict[str, Any] | None:
        data = self._get("/ratios-ttm", {"symbol": symbol.upper()})
        if isinstance(data, list) and data:
            return data[0]
        return None

    def key_metrics_ttm(self, symbol: str) -> dict[str, Any] | None:
        data = self._get("/key-metrics-ttm", {"symbol": symbol.upper()})
        if isinstance(data, list) and data:
            return data[0]
        return None

    def income_statement(
        self, symbol: str, period: str = "annual", limit: int = 1
    ) -> list[dict[str, Any]]:
        data = self._get(
            "/income-statement",
            {"symbol": symbol.upper(), "period": period, "limit": limit},
        )
        return data if isinstance(data, list) else []

    def balance_sheet(
        self, symbol: str, period: str = "annual", limit: int = 1
    ) -> list[dict[str, Any]]:
        data = self._get(
            "/balance-sheet-statement",
            {"symbol": symbol.upper(), "period": period, "limit": limit},
        )
        return data if isinstance(data, list) else []

    def cash_flow(
        self, symbol: str, period: str = "annual", limit: int = 1
    ) -> list[dict[str, Any]]:
        data = self._get(
            "/cash-flow-statement",
            {"symbol": symbol.upper(), "period": period, "limit": limit},
        )
        return data if isinstance(data, list) else []