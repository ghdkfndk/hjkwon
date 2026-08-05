from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@lru_cache(maxsize=1)
def get_settings() -> dict[str, str]:
    return {
        "fmp_api_key": os.getenv("FMP_API_KEY", "").strip(),
        "opendart_api_key": os.getenv("OPENDART_API_KEY", "").strip(),
        "data_dir": os.getenv("COMPANY_VALUATION_DATA_DIR", "data"),
    }


def require_fmp_key() -> str:
    key = get_settings()["fmp_api_key"]
    if not key:
        raise RuntimeError(
            "FMP_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return key


def require_opendart_key() -> str:
    key = get_settings()["opendart_api_key"]
    if not key:
        raise RuntimeError(
            "OPENDART_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return key