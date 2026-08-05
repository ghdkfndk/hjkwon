from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import httpx

from company_valuation.config import get_settings, require_opendart_key

BASE_URL = "https://opendart.fss.or.kr/api"

# OpenDART report codes
REPORT_ANNUAL = "11011"
REPORT_HALF = "11012"
REPORT_Q1 = "11013"
REPORT_Q3 = "11014"


class OpenDartClient:
    """OpenDART client for Korean listed company filings and fundamentals."""

    def __init__(
        self,
        api_key: str | None = None,
        data_dir: str | Path | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key or require_opendart_key()
        settings = get_settings()
        self.data_dir = Path(data_dir or settings["data_dir"])
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._corp_index: list[dict[str, str]] | None = None
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OpenDartClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        query = {"crtfc_key": self.api_key, **params}
        response = self._client.get(f"{BASE_URL}{path}", params=query)
        response.raise_for_status()
        data = response.json()
        status = data.get("status")
        if status not in (None, "000"):
            # 013 = no data — return empty rather than crash
            if status == "013":
                return data
            raise RuntimeError(f"OpenDART error {status}: {data.get('message')}")
        return data

    def ensure_corp_codes(self, force: bool = False) -> Path:
        """Download and cache corpCode.xml from OpenDART."""
        cache_path = self.data_dir / "corpCode.xml"
        if cache_path.exists() and not force:
            return cache_path

        response = self._client.get(
            f"{BASE_URL}/corpCode.xml",
            params={"crtfc_key": self.api_key},
        )
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            name = zf.namelist()[0]
            cache_path.write_bytes(zf.read(name))
        self._corp_index = None
        return cache_path

    def load_corp_index(self, force: bool = False) -> list[dict[str, str]]:
        if self._corp_index is not None and not force:
            return self._corp_index

        path = self.ensure_corp_codes(force=force)
        root = ElementTree.parse(path).getroot()
        rows: list[dict[str, str]] = []
        for el in root.findall("list"):
            corp_code = (el.findtext("corp_code") or "").strip()
            corp_name = (el.findtext("corp_name") or "").strip()
            stock_code = (el.findtext("stock_code") or "").strip()
            modify_date = (el.findtext("modify_date") or "").strip()
            if not corp_code:
                continue
            rows.append(
                {
                    "corp_code": corp_code,
                    "corp_name": corp_name,
                    "stock_code": stock_code,
                    "modify_date": modify_date,
                }
            )
        self._corp_index = rows
        return rows

    def search(
        self, query: str, listed_only: bool = True, limit: int = 10
    ) -> list[dict[str, str]]:
        q = query.strip()
        digits = "".join(ch for ch in q if ch.isdigit())
        index = self.load_corp_index()
        matches: list[dict[str, str]] = []

        if len(digits) in (5, 6):
            ticker = digits.zfill(6)
            for row in index:
                if row["stock_code"] == ticker:
                    matches.append(row)
                    break
            return matches[:limit]

        q_lower = q.lower()
        for row in index:
            if listed_only and not row["stock_code"]:
                continue
            name = row["corp_name"]
            if q in name or q_lower in name.lower():
                matches.append(row)
            if len(matches) >= limit:
                break
        return matches

    def company(self, corp_code: str) -> dict[str, Any]:
        return self._get_json("/company.json", {"corp_code": corp_code})

    def major_accounts(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str = REPORT_ANNUAL,
    ) -> list[dict[str, Any]]:
        data = self._get_json(
            "/fnlttSinglAcnt.json",
            {
                "corp_code": corp_code,
                "bsns_year": bsns_year,
                "reprt_code": reprt_code,
            },
        )
        return data.get("list") or []

    def full_accounts(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str = REPORT_ANNUAL,
        fs_div: str = "CFS",
    ) -> list[dict[str, Any]]:
        data = self._get_json(
            "/fnlttSinglAcntAll.json",
            {
                "corp_code": corp_code,
                "bsns_year": bsns_year,
                "reprt_code": reprt_code,
                "fs_div": fs_div,
            },
        )
        rows = data.get("list") or []
        if not rows and fs_div == "CFS":
            return self.full_accounts(
                corp_code, bsns_year, reprt_code=reprt_code, fs_div="OFS"
            )
        return rows