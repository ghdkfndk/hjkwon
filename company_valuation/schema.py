from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Market(str, Enum):
    US = "US"
    KR = "KR"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CompanyIdentity(BaseModel):
    market: Market
    ticker: str
    name: str
    exchange: str | None = None
    currency: Literal["USD", "KRW"]
    corp_code: str | None = Field(
        default=None,
        description="OpenDART 8-digit corp_code (KR only)",
    )
    extras: dict[str, Any] = Field(default_factory=dict)


class Multiples(BaseModel):
    pe: float | None = None
    pb: float | None = None
    ps: float | None = None
    ev_ebitda: float | None = None
    peg: float | None = None


class Fundamentals(BaseModel):
    market: Market
    ticker: str
    name: str | None = None
    currency: Literal["USD", "KRW"]
    period: str | None = None
    fiscal_year: str | None = None
    revenue: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    total_assets: float | None = None
    total_liabilities: float | None = None
    total_equity: float | None = None
    total_debt: float | None = None
    cash: float | None = None
    source: list[str] = Field(default_factory=list)
    raw_accounts: dict[str, float] = Field(default_factory=dict)


class CompanyValuation(BaseModel):
    market: Market
    ticker: str
    name: str
    currency: Literal["USD", "KRW"]
    as_of: str | None = None
    market_cap: float | None = None
    enterprise_value: float | None = None
    price: float | None = None
    shares_outstanding: float | None = None
    multiples: Multiples = Field(default_factory=Multiples)
    fundamentals: Fundamentals | None = None
    source: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM
    notes: list[str] = Field(default_factory=list)