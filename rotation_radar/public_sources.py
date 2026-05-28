from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class SourceFetchError(RuntimeError):
    """Raised when a public market data source cannot be fetched."""


@dataclass(frozen=True)
class SourceEndpoint:
    name: str
    url: str


def fetch_public_text(url: str, timeout: int = 20) -> str:
    request = Request(
        url,
        headers={
            "Accept": "application/json,text/plain,*/*",
            "User-Agent": "Mozilla/5.0 AI_stock_rotation_radar/0.1",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8-sig")
    except OSError as exc:
        raise SourceFetchError(f"Failed to fetch {url}: {exc}") from exc


def fetch_public_json(url: str, timeout: int = 20) -> dict[str, Any]:
    payload = fetch_public_text(url, timeout=timeout)

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SourceFetchError(f"Source did not return JSON: {url}") from exc


def save_raw_snapshot(payload: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_raw_text(payload: str, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def build_twse_endpoints(trade_date: date) -> list[SourceEndpoint]:
    ymd = trade_date.strftime("%Y%m%d")
    return [
        SourceEndpoint(
            name="twse_prices",
            url=_url(
                "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX",
                date=ymd,
                type="ALLBUT0999",
                response="json",
            ),
        ),
        SourceEndpoint(
            name="twse_institutional",
            url=_url(
                "https://www.twse.com.tw/rwd/zh/fund/T86",
                date=ymd,
                selectType="ALLBUT0999",
                response="json",
            ),
        ),
        SourceEndpoint(
            name="twse_margin",
            url=_url(
                "https://www.twse.com.tw/exchangeReport/MI_MARGN",
                date=ymd,
                selectType="ALL",
                response="open_data",
            ),
        ),
    ]


def build_tpex_endpoints(trade_date: date) -> list[SourceEndpoint]:
    slash_date = trade_date.strftime("%Y/%m/%d")
    ymd = trade_date.strftime("%Y%m%d")
    return [
        SourceEndpoint(
            name="tpex_prices",
            url=_url(
                "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc",
                date=slash_date,
                type="EW",
                response="json",
            ),
        ),
        SourceEndpoint(
            name="tpex_institutional",
            url=_url(
                "https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade",
                date=slash_date,
                type="Daily",
                response="json",
            ),
        ),
        SourceEndpoint(
            name="tpex_margin",
            url=_url(
                "https://www.tpex.org.tw/www/zh-tw/margin/balance",
                date=ymd,
                response="json",
            ),
        ),
    ]


def fetch_raw_market_snapshots(trade_date: date, output_dir: str | Path) -> tuple[list[Path], list[str]]:
    saved: list[Path] = []
    errors: list[str] = []
    for endpoint in [*build_twse_endpoints(trade_date), *build_tpex_endpoints(trade_date)]:
        try:
            if endpoint.name == "twse_margin":
                payload_text = fetch_public_text(endpoint.url)
                if not _looks_like_twse_margin_csv(payload_text):
                    raise SourceFetchError(
                        "TWSE margin source did not return the stock-level CSV. "
                        "This can happen before the daily file is published or when the site returns a maintenance page."
                    )
                output_path = Path(output_dir) / trade_date.strftime("%Y%m%d") / f"{endpoint.name}.csv"
                save_raw_text(payload_text, output_path)
                saved.append(output_path)
                continue
            payload = fetch_public_json(endpoint.url)
        except SourceFetchError as exc:
            errors.append(f"{endpoint.name}: {exc}")
            continue
        output_path = Path(output_dir) / trade_date.strftime("%Y%m%d") / f"{endpoint.name}.json"
        save_raw_snapshot(payload, output_path)
        saved.append(output_path)
    return saved, errors


def fetch_raw_price_snapshots(trade_date: date, output_dir: str | Path, force: bool = False) -> tuple[list[Path], list[str]]:
    saved: list[Path] = []
    errors: list[str] = []
    for endpoint in [build_twse_endpoints(trade_date)[0], build_tpex_endpoints(trade_date)[0]]:
        output_path = Path(output_dir) / trade_date.strftime("%Y%m%d") / f"{endpoint.name}.json"
        if output_path.exists() and not force:
            saved.append(output_path)
            continue
        try:
            payload = fetch_public_json(endpoint.url)
        except SourceFetchError as exc:
            errors.append(f"{endpoint.name}: {exc}")
            continue
        save_raw_snapshot(payload, output_path)
        saved.append(output_path)
    return saved, errors


def recent_weekdays(end_date: date, count: int) -> list[date]:
    days: list[date] = []
    current = end_date
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current -= timedelta(days=1)
    return days


def parse_trade_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Trade date must use YYYY-MM-DD format.") from exc


def _url(base: str, **query: str) -> str:
    return f"{base}?{urlencode(query)}"


def _looks_like_twse_margin_csv(payload: str) -> bool:
    first_line = payload.lstrip("\ufeff\r\n ").splitlines()[0] if payload.strip() else ""
    return "股票代號" in first_line and "融資今日餘額" in first_line
