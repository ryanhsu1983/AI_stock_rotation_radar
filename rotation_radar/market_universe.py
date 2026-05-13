from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


TWSE_COMPANY_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TPEX_COMPANY_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"


def build_market_universe(
    rules_path: str | Path = "data/industry_sector_rules.csv",
    output_path: str | Path = "data/market_universe.generated.csv",
    sector_map_output_path: str | Path = "data/sector_map.generated.csv",
) -> tuple[Path, Path]:
    rules = _load_rules(rules_path)
    market_path = Path(output_path)
    sector_path = Path(sector_map_output_path)
    try:
        rows = [*_fetch_twse_companies(rules), *_fetch_tpex_companies(rules)]
    except OSError:
        if market_path.exists() and sector_path.exists():
            return market_path, sector_path
        raise
    rows.sort(key=lambda item: item["symbol"])

    market_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(
        market_path,
        ["market", "symbol", "name", "industry_code", "sector"],
        rows,
    )

    sector_rows = [
        {
            "sector": row["sector"],
            "symbol": row["symbol"],
            "name": row["name"],
            "role": row["sector"],
            "overseas_reference": "",
            "market": row["market"],
        }
        for row in rows
    ]
    _write_csv(
        sector_path,
        ["sector", "symbol", "name", "role", "overseas_reference", "market"],
        sector_rows,
    )
    return market_path, sector_path


def _fetch_twse_companies(rules: dict[tuple[str, str], str]) -> list[dict[str, str]]:
    payload = _fetch_json(TWSE_COMPANY_URL)
    rows: list[dict[str, str]] = []
    for item in payload:
        symbol = str(item.get("公司代號", "")).strip()
        industry_code = str(item.get("產業別", "")).strip().zfill(2)
        if not symbol.isdigit():
            continue
        rows.append(
            {
                "market": "TWSE",
                "symbol": symbol,
                "name": str(item.get("公司簡稱") or item.get("公司名稱") or "").strip(),
                "industry_code": industry_code,
                "sector": _sector_for("TWSE", industry_code, rules),
            }
        )
    return rows


def _fetch_tpex_companies(rules: dict[tuple[str, str], str]) -> list[dict[str, str]]:
    payload = _fetch_json(TPEX_COMPANY_URL)
    rows: list[dict[str, str]] = []
    for item in payload:
        symbol = str(item.get("SecuritiesCompanyCode", "")).strip()
        industry_code = str(item.get("SecuritiesIndustryCode", "")).strip().zfill(2)
        if not symbol.isdigit():
            continue
        rows.append(
            {
                "market": "TPEx",
                "symbol": symbol,
                "name": str(item.get("CompanyAbbreviation") or item.get("CompanyName") or "").strip(),
                "industry_code": industry_code,
                "sector": _sector_for("TPEx", industry_code, rules),
            }
        )
    return rows


def _load_rules(path: str | Path) -> dict[tuple[str, str], str]:
    rules: dict[tuple[str, str], str] = {}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            rules[(row["market"], row["industry_code"].zfill(2))] = row["sector"]
    return rules


def _sector_for(market: str, industry_code: str, rules: dict[tuple[str, str], str]) -> str:
    return rules.get((market, industry_code), "其他")


def _fetch_json(url: str) -> list[dict[str, Any]]:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 AI_stock_single/0.1"})
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
