from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .data_loader import SECTOR_COLUMNS, STOCK_COLUMNS


@dataclass(frozen=True)
class DailyMarketRow:
    trade_date: str
    symbol: str
    close: float | None = None
    amount: float | None = None
    foreign_net: float | None = None
    trust_net: float | None = None
    margin_balance: float | None = None
    previous_margin_balance: float | None = None


def update_stock_metrics_from_processed(
    stock_metrics_path: str | Path,
    processed_root: str | Path,
    output_path: str | Path,
) -> Path:
    stocks = _read_stock_metric_rows(stock_metrics_path)
    market_rows = _load_processed_market_rows(processed_root)
    by_symbol: dict[str, list[DailyMarketRow]] = defaultdict(list)
    for row in market_rows:
        by_symbol[row.symbol].append(row)

    updated: list[dict[str, str]] = []
    for stock in stocks:
        symbol = stock["symbol"]
        symbol_rows = sorted(by_symbol.get(symbol, []), key=lambda item: item.trade_date)
        if symbol_rows:
            _apply_market_rows(stock, symbol_rows)
        else:
            _apply_fair_values(stock)
        updated.append(stock)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_stock_field_order()))
        writer.writeheader()
        writer.writerows(updated)
    return path


def update_sector_metrics_from_stocks(
    sector_metrics_path: str | Path,
    stock_metrics_path: str | Path,
    output_path: str | Path,
) -> Path:
    sectors = _read_sector_metric_rows(sector_metrics_path)
    stocks = _read_stock_metric_rows(stock_metrics_path)

    by_sector: dict[str, list[dict[str, str]]] = defaultdict(list)
    for stock in stocks:
        by_sector[stock["sector"]].append(stock)

    updated: list[dict[str, str]] = []
    for sector in sectors:
        sector_stocks = by_sector.get(sector["name"], [])
        if sector_stocks:
            _apply_stock_group_metrics(sector, sector_stocks)
        updated.append(sector)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_sector_field_order()))
        writer.writeheader()
        writer.writerows(updated)
    return path


def _read_stock_metric_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = sorted(STOCK_COLUMNS - fieldnames)
        if missing:
            raise ValueError(f"{path} is missing columns: {', '.join(missing)}")
        return [dict(row) for row in reader]


def _read_sector_metric_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = sorted(SECTOR_COLUMNS - fieldnames)
        if missing:
            raise ValueError(f"{path} is missing columns: {', '.join(missing)}")
        return [dict(row) for row in reader]


def _load_processed_market_rows(processed_root: str | Path) -> list[DailyMarketRow]:
    root = Path(processed_root)
    if not root.exists():
        raise FileNotFoundError(f"Processed data directory does not exist: {root}")

    rows: list[DailyMarketRow] = []
    for folder in sorted(path for path in root.iterdir() if path.is_dir()):
        trade_date = folder.name
        rows.extend(_load_price_rows(folder, trade_date))
        rows.extend(_load_institutional_rows(folder, trade_date))
        rows.extend(_load_margin_rows(folder, trade_date))
    return rows


def _load_price_rows(folder: Path, trade_date: str) -> list[DailyMarketRow]:
    rows: list[DailyMarketRow] = []
    for path in folder.glob("*prices*.csv"):
        for row in _read_csv(path):
            symbol = row.get("代號", "").strip()
            if not symbol:
                continue
            rows.append(
                DailyMarketRow(
                    trade_date=trade_date,
                    symbol=symbol,
                    close=_number(row.get("收盤") or row.get("收盤價")),
                    amount=_number(row.get("成交金額(元)") or row.get("成交金額")),
                )
            )
    return rows


def _load_institutional_rows(folder: Path, trade_date: str) -> list[DailyMarketRow]:
    rows: list[DailyMarketRow] = []
    for path in folder.glob("*institutional*.csv"):
        for row in _read_csv(path):
            symbol = row.get("代號", "").strip()
            if not symbol:
                continue
            rows.append(
                DailyMarketRow(
                    trade_date=trade_date,
                    symbol=symbol,
                    foreign_net=_shares_to_lots(_number(row.get("買賣超股數"))),
                    trust_net=_shares_to_lots(_number(row.get("買賣超股數_2"))),
                )
            )
    return rows


def _load_margin_rows(folder: Path, trade_date: str) -> list[DailyMarketRow]:
    rows: list[DailyMarketRow] = []
    for path in folder.glob("*margin*.csv"):
        for row in _read_csv(path):
            symbol = row.get("代號", "").strip()
            if not symbol:
                symbol = row.get("股票代號", "").strip()
            if not symbol:
                continue
            rows.append(
                DailyMarketRow(
                    trade_date=trade_date,
                    symbol=symbol,
                    margin_balance=_number(row.get("資餘額") or row.get("融資今日餘額") or row.get("今日餘額")),
                    previous_margin_balance=_number(
                        row.get("前資餘額(張)") or row.get("融資前日餘額") or row.get("前日餘額")
                    ),
                )
            )
    return rows


def _apply_market_rows(stock: dict[str, str], rows: list[DailyMarketRow]) -> None:
    latest_close = _latest_value(rows, "close")
    if latest_close is not None:
        stock["close"] = _format_number(latest_close)

    stock["foreign_5d"] = _format_number(_sum_recent(rows, "foreign_net", fallback=stock["foreign_5d"]))
    stock["trust_5d"] = _format_number(_sum_recent(rows, "trust_net", fallback=stock["trust_5d"]))

    margin_change = _margin_change_pct(rows)
    if margin_change is not None:
        stock["margin_change_5d"] = _format_number(margin_change)

    liquidity = _liquidity_score(rows)
    if liquidity is not None:
        stock["liquidity"] = _format_number(liquidity)

    stock["chip_cleanliness"] = _format_number(_chip_score(stock))
    stock["risk_heat"] = _format_number(_risk_heat(stock))
    _apply_fair_values(stock)


def _apply_stock_group_metrics(sector: dict[str, str], stocks: list[dict[str, str]]) -> None:
    liquidity_avg = _avg(_number(stock.get("liquidity")) for stock in stocks)
    technical_avg = _avg(_number(stock.get("technical_setup")) for stock in stocks)
    risk_avg = _avg(_number(stock.get("risk_heat")) for stock in stocks)
    pe_percentile_avg = _avg(_pe_percentile(stock) for stock in stocks)
    positive_chip_ratio = _avg(_positive_chip(stock) for stock in stocks) * 100

    capital_score = liquidity_avg * 0.45 + positive_chip_ratio * 0.35 + technical_avg * 0.20
    sector["capital_inflow_rank"] = _format_number(_clamp(capital_score))
    sector["turnover_share_change"] = _format_number(_clamp(liquidity_avg))
    sector["momentum_20d"] = _format_number(_clamp(technical_avg))
    sector["strong_stock_ratio"] = _format_number(_clamp(positive_chip_ratio))
    sector["pe_percentile"] = _format_number(_clamp(pe_percentile_avg))
    sector["risk_heat"] = _format_number(_clamp(risk_avg))
    sector["capital_share"] = sector.get("capital_share", "0") or "0"
    sector["capital_share_prev"] = sector.get("capital_share_prev", "0") or "0"
    sector["turnover_value"] = sector.get("turnover_value", "0") or "0"
    sector["turnover_value_prev"] = sector.get("turnover_value_prev", "0") or "0"


def _apply_fair_values(stock: dict[str, str]) -> None:
    close = _number(stock.get("close"))
    pe = _number(stock.get("pe"))
    low = _number(stock.get("sector_pe_low"))
    avg = _number(stock.get("sector_pe_avg"))
    high = _number(stock.get("sector_pe_high"))
    if close is None or pe in (None, 0) or low is None or avg is None or high is None:
        return
    eps = close / pe
    stock["fair_value_low"] = _format_number(eps * low)
    stock["fair_value_avg"] = _format_number(eps * avg)
    stock["fair_value_high"] = _format_number(eps * high)


def _margin_change_pct(rows: list[DailyMarketRow]) -> float | None:
    margin_rows = [row for row in rows if row.margin_balance is not None]
    if not margin_rows:
        return None

    first = margin_rows[0]
    latest = margin_rows[-1]
    base = first.previous_margin_balance if first.previous_margin_balance not in (None, 0) else first.margin_balance
    if base in (None, 0) or latest.margin_balance is None:
        return None
    return (latest.margin_balance - base) / base * 100


def _liquidity_score(rows: list[DailyMarketRow]) -> float | None:
    amounts = [row.amount for row in rows if row.amount is not None]
    if not amounts:
        return None
    avg_amount_million = sum(amounts) / len(amounts) / 1_000_000
    if avg_amount_million >= 1500:
        return 100.0
    if avg_amount_million >= 800:
        return 90.0
    if avg_amount_million >= 300:
        return 75.0
    if avg_amount_million >= 100:
        return 60.0
    if avg_amount_million >= 30:
        return 45.0
    return 25.0


def _chip_score(stock: dict[str, str]) -> float:
    foreign = _number(stock.get("foreign_5d")) or 0.0
    trust = _number(stock.get("trust_5d")) or 0.0
    margin = _number(stock.get("margin_change_5d")) or 0.0
    score = 55.0
    if foreign > 0:
        score += 8
    if trust > 0:
        score += 10
    if foreign > 0 and trust > 0:
        score += 6
    if margin < 0:
        score += 8
    elif margin <= 5:
        score += 4
    elif margin > 12:
        score -= 12
    return _clamp(score)


def _risk_heat(stock: dict[str, str]) -> float:
    risk = 45.0
    margin = _number(stock.get("margin_change_5d")) or 0.0
    technical = _number(stock.get("technical_setup")) or 50.0
    pe = _number(stock.get("pe")) or 0.0
    sector_pe_high = _number(stock.get("sector_pe_high")) or 0.0

    if margin > 12:
        risk += 14
    elif margin > 5:
        risk += 6
    if technical > 78:
        risk += 10
    if sector_pe_high and pe > sector_pe_high * 0.9:
        risk += 12
    return _clamp(risk)


def _pe_percentile(stock: dict[str, str]) -> float | None:
    pe = _number(stock.get("pe"))
    low = _number(stock.get("sector_pe_low"))
    high = _number(stock.get("sector_pe_high"))
    if pe is None or low is None or high is None or high <= low:
        return None
    return _clamp((pe - low) / (high - low) * 100)


def _positive_chip(stock: dict[str, str]) -> float:
    foreign = _number(stock.get("foreign_5d")) or 0.0
    trust = _number(stock.get("trust_5d")) or 0.0
    margin = _number(stock.get("margin_change_5d")) or 0.0
    if foreign > 0 and trust > 0 and margin <= 12:
        return 1.0
    if (foreign > 0 or trust > 0) and margin <= 8:
        return 0.7
    return 0.0


def _avg(values: object) -> float:
    clean = [value for value in values if isinstance(value, (int, float))]
    if not clean:
        return 50.0
    return sum(clean) / len(clean)


def _latest_value(rows: list[DailyMarketRow], attr: str) -> float | None:
    for row in reversed(rows):
        value = getattr(row, attr)
        if value is not None:
            return value
    return None


def _sum_recent(rows: list[DailyMarketRow], attr: str, fallback: str) -> float:
    values = [getattr(row, attr) for row in rows[-5:] if getattr(row, attr) is not None]
    if not values:
        return _number(fallback) or 0.0
    return sum(values)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _number(value: str | float | int | None) -> float | None:
    if value is None:
        return None
    raw = str(value).replace(",", "").strip()
    if raw in {"", "--", "-"}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _shares_to_lots(value: float | None) -> float | None:
    if value is None:
        return None
    return value / 1000


def _format_number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _stock_field_order() -> tuple[str, ...]:
    return (
        "symbol",
        "name",
        "sector",
        "close",
        "pullback_quality",
        "chip_cleanliness",
        "foreign_5d",
        "trust_5d",
        "margin_change_5d",
        "pe",
        "sector_pe_low",
        "sector_pe_avg",
        "sector_pe_high",
        "fair_value_low",
        "fair_value_avg",
        "fair_value_high",
        "revenue_yoy",
        "revenue_mom",
        "technical_setup",
        "liquidity",
        "risk_heat",
        "thesis",
        "risk_reason",
    )


def _sector_field_order() -> tuple[str, ...]:
    return (
        "name",
        "theme",
        "capital_inflow_rank",
        "turnover_share_change",
        "capital_share",
        "capital_share_prev",
        "turnover_value",
        "turnover_value_prev",
        "momentum_20d",
        "strong_stock_ratio",
        "industry_trend",
        "overseas_signal",
        "pe_percentile",
        "risk_heat",
        "catalysts",
        "risks",
    )
