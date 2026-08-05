from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from company_valuation.routing import normalize_kr_ticker


def _recent_business_days(n: int = 10) -> list[str]:
    """Return recent calendar dates as YYYYMMDD (weekends skipped)."""
    days: list[str] = []
    cursor = datetime.now().date()
    while len(days) < n:
        if cursor.weekday() < 5:
            days.append(cursor.strftime("%Y%m%d"))
        cursor -= timedelta(days=1)
    return days


class KRXClient:
    """
    Korean exchange market data via pykrx / FinanceDataReader.

    OpenDART does not provide market cap; this client fills that gap.
    """

    def market_snapshot(self, ticker: str) -> dict[str, Any] | None:
        ticker = normalize_kr_ticker(ticker)
        # Prefer pykrx; fall back to FinanceDataReader listing snapshot.
        snap = self._from_pykrx(ticker)
        if snap:
            return snap
        return self._from_fdr(ticker)

    def _from_pykrx(self, ticker: str) -> dict[str, Any] | None:
        try:
            from pykrx import stock
        except ImportError:
            return None

        consecutive_failures = 0
        for day in _recent_business_days(10):
            try:
                df = stock.get_market_cap_by_ticker(day, market="ALL")
            except Exception:
                consecutive_failures += 1
                # Auth / blocked environments fail repeatedly — bail out to FDR.
                if consecutive_failures >= 2:
                    return None
                continue
            if df is None or df.empty:
                consecutive_failures += 1
                if consecutive_failures >= 2:
                    return None
                continue
            consecutive_failures = 0
            if ticker not in df.index:
                continue
            row = df.loc[ticker]
            name = None
            try:
                name = stock.get_market_ticker_name(ticker)
            except Exception:
                name = None

            pe = pb = None
            try:
                fund = stock.get_market_fundamental_by_ticker(day, market="ALL")
                if fund is not None and not fund.empty and ticker in fund.index:
                    frow = fund.loc[ticker]
                    pe = _safe_float(frow.get("PER"))
                    pb = _safe_float(frow.get("PBR"))
            except Exception:
                pass

            return {
                "ticker": ticker,
                "name": name,
                "as_of": f"{day[:4]}-{day[4:6]}-{day[6:]}",
                "price": _safe_float(row.get("종가")),
                "market_cap": _safe_float(row.get("시가총액")),
                "shares_outstanding": _safe_float(row.get("상장주식수")),
                "volume": _safe_float(row.get("거래량")),
                "pe": pe,
                "pb": pb,
                "source": "pykrx",
            }
        return None

    def _from_fdr(self, ticker: str) -> dict[str, Any] | None:
        try:
            import FinanceDataReader as fdr
        except ImportError:
            return None

        try:
            listing = fdr.StockListing("KRX")
        except Exception:
            return None
        if listing is None or listing.empty:
            return None

        # Column names vary slightly by FinanceDataReader version.
        code_col = next(
            (c for c in ("Code", "Symbol", "종목코드") if c in listing.columns),
            None,
        )
        if not code_col:
            return None

        match = listing[listing[code_col].astype(str).str.zfill(6) == ticker]
        if match.empty:
            return None
        row = match.iloc[0]
        name = row.get("Name") or row.get("종목명")
        close = row.get("Close") or row.get("ClosePrice") or row.get("종가")
        marcap = row.get("Marcap") or row.get("시가총액")
        shares = row.get("Stocks") or row.get("상장주식수")
        return {
            "ticker": ticker,
            "name": None if name is None else str(name),
            "as_of": datetime.now().strftime("%Y-%m-%d"),
            "price": _safe_float(close),
            "market_cap": _safe_float(marcap),
            "shares_outstanding": _safe_float(shares),
            "volume": _safe_float(row.get("Volume")),
            "pe": None,
            "pb": None,
            "source": "FinanceDataReader",
        }


def _safe_float(value: Any) -> float | None:
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