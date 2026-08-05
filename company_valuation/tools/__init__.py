from company_valuation.tools.fundamentals import get_company_fundamentals
from company_valuation.tools.resolve import resolve_company
from company_valuation.tools.valuation import get_company_valuation

__all__ = [
    "resolve_company",
    "get_company_valuation",
    "get_company_fundamentals",
]


# OpenAI / Anthropic-style tool schemas for agent function calling
TOOL_SCHEMAS = [
    {
        "name": "resolve_company",
        "description": "Resolve a company name or ticker to US/KR listed identity.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Company name or ticker (e.g. Apple, AAPL, 삼성전자, 005930)",
                },
                "market": {
                    "type": "string",
                    "enum": ["US", "KR"],
                    "description": "Optional market hint",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_company_valuation",
        "description": (
            "Get market cap, enterprise value, price and multiples "
            "for a US or Korean listed company."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "query": {"type": "string"},
                "market": {"type": "string", "enum": ["US", "KR"]},
            },
        },
    },
    {
        "name": "get_company_fundamentals",
        "description": "Get income/balance fundamentals for a US or Korean listed company.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "query": {"type": "string"},
                "market": {"type": "string", "enum": ["US", "KR"]},
                "period": {"type": "string", "enum": ["annual", "quarter"]},
                "year": {"type": "integer"},
            },
        },
    },
]