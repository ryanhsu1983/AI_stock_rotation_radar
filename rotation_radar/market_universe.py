from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


TWSE_COMPANY_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TPEX_COMPANY_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"


class MarketUniverseFetchError(RuntimeError):
    """Raised when the exchange company universe cannot be fetched or parsed."""


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
    except (OSError, MarketUniverseFetchError) as exc:
        if market_path.exists() and sector_path.exists():
            print(f"Warning: failed to refresh market universe; using existing generated files: {exc}")
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


def build_fallback_universe_from_theme_map(
    theme_map_path: str | Path,
    output_path: str | Path = "data/market_universe.generated.csv",
    sector_map_output_path: str | Path = "data/sector_map.generated.csv",
) -> tuple[Path, Path]:
    """Build a conservative universe from the curated theme map.

    This is intentionally smaller than the exchange universe, but it lets the
    scheduled report continue when TWSE/TPEx company-list endpoints return a
    transient non-JSON response.
    """

    rows_by_symbol: dict[str, dict[str, str]] = {}
    with Path(theme_map_path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol = str(row.get("symbol", "")).strip()
            theme = str(row.get("theme", "")).strip()
            name = str(row.get("name", "")).strip()
            primary = str(row.get("primary", "yes")).strip().lower()
            if not symbol or not symbol.isdigit() or not theme or primary in {"no", "false", "0"}:
                continue
            rows_by_symbol.setdefault(
                symbol,
                {
                    "market": "",
                    "symbol": symbol,
                    "name": name,
                    "industry_code": "",
                    "sector": theme,
                },
            )

    rows = sorted(rows_by_symbol.values(), key=lambda item: item["symbol"])
    if not rows:
        raise MarketUniverseFetchError(f"No fallback rows found in {theme_map_path}")

    market_path = Path(output_path)
    sector_path = Path(sector_map_output_path)
    market_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(
        market_path,
        ["market", "symbol", "name", "industry_code", "sector"],
        rows,
    )
    _write_csv(
        sector_path,
        ["sector", "symbol", "name", "role", "overseas_reference", "market"],
        [
            {
                "sector": row["sector"],
                "symbol": row["symbol"],
                "name": row["name"],
                "role": row["sector"],
                "overseas_reference": "",
                "market": row["market"],
            }
            for row in rows
        ],
    )
    print(f"Warning: using curated theme map fallback universe with {len(rows)} symbols.")
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
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 AI_stock_rotation_radar/0.1"})
    with urlopen(request, timeout=30) as response:
        raw = response.read()
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        snippet = raw[:200].decode("utf-8", errors="replace").replace("\n", " ")
        raise MarketUniverseFetchError(f"Expected JSON from {url}; got: {snippet}") from exc
    if not isinstance(payload, list):
        raise MarketUniverseFetchError(f"Expected a JSON list from {url}; got {type(payload).__name__}")
    return payload


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
