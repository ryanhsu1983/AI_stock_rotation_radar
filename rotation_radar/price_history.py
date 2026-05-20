from __future__ import annotations

import csv
from pathlib import Path


def build_price_history_from_processed(
    processed_root: str | Path,
    output_path: str | Path,
    symbols: set[str] | None = None,
    market_quotes_path: str | Path | None = None,
) -> Path:
    rows_by_symbol = _load_existing_history(output_path, symbols)
    root = Path(processed_root)
    if root.exists():
        for folder in sorted(path for path in root.iterdir() if path.is_dir()):
            trade_date = _display_date(folder.name)
            for path in folder.glob("*prices*.csv"):
                for row in _read_csv(path):
                    symbol = (row.get("證券代號") or row.get("代號") or "").strip()
                    if not symbol or (symbols and symbol not in symbols):
                        continue
                    item = _ohlc_row(symbol, trade_date, row)
                    if item:
                        rows_by_symbol.setdefault(symbol, []).append(item)

    if market_quotes_path:
        for item in _latest_quote_rows(market_quotes_path, symbols):
            rows_by_symbol.setdefault(str(item["symbol"]), []).append(item)

    output_rows: list[dict[str, float | str]] = []
    for symbol, rows in rows_by_symbol.items():
        deduped = {str(row["date"]): row for row in rows}
        ordered = [deduped[key] for key in sorted(deduped)]
        closes: list[float] = []
        for row in ordered:
            closes.append(float(row["close"]))
            row["ma5"] = _avg(closes[-5:])
            row["ma20"] = _avg(closes[-20:])
            row["ma60"] = _avg(closes[-60:])
        output_rows.extend(ordered)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "date", "open", "high", "low", "close", "ma5", "ma20", "ma60"])
        writer.writeheader()
        writer.writerows(output_rows)
    return path


def load_price_history(path: str | Path | None) -> dict[str, list[dict[str, float | str]]]:
    if not path:
        return {}
    csv_path = Path(path)
    if not csv_path.exists():
        return {}

    history: dict[str, list[dict[str, float | str]]] = {}
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol = row.get("symbol", "").strip()
            if not symbol:
                continue
            history.setdefault(symbol, []).append(
                {
                    "date": row.get("date", ""),
                    "open": _number(row.get("open")),
                    "high": _number(row.get("high")),
                    "low": _number(row.get("low")),
                    "close": _number(row.get("close")),
                    "ma5": _number(row.get("ma5")),
                    "ma20": _number(row.get("ma20")),
                    "ma60": _number(row.get("ma60")),
                }
            )

    return {symbol: rows[-23:] for symbol, rows in history.items()}


def _load_existing_history(path: str | Path, symbols: set[str] | None) -> dict[str, list[dict[str, float | str]]]:
    csv_path = Path(path)
    if not csv_path.exists():
        return {}
    rows_by_symbol: dict[str, list[dict[str, float | str]]] = {}
    for row in _read_csv(csv_path):
        symbol = row.get("symbol", "").strip()
        if not symbol or (symbols and symbol not in symbols):
            continue
        item = {
            "symbol": symbol,
            "date": row.get("date", ""),
            "open": _number(row.get("open")),
            "high": _number(row.get("high")),
            "low": _number(row.get("low")),
            "close": _number(row.get("close")),
            "ma5": _number(row.get("ma5")),
            "ma20": _number(row.get("ma20")),
            "ma60": _number(row.get("ma60")),
        }
        rows_by_symbol.setdefault(symbol, []).append(item)
    return rows_by_symbol


def _read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _ohlc_row(symbol: str, trade_date: str, row: dict[str, str]) -> dict[str, float | str] | None:
    open_ = _number_or_none(row.get("開盤價") or row.get("開盤"))
    high = _number_or_none(row.get("最高價") or row.get("最高"))
    low = _number_or_none(row.get("最低價") or row.get("最低"))
    close = _number_or_none(row.get("收盤價") or row.get("收盤"))
    if None in {open_, high, low, close}:
        return None
    return {
        "symbol": symbol,
        "date": trade_date,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "ma5": close,
        "ma20": close,
        "ma60": close,
    }


def _latest_quote_rows(path: str | Path, symbols: set[str] | None) -> list[dict[str, float | str]]:
    csv_path = Path(path)
    if not csv_path.exists():
        return []
    rows: list[dict[str, float | str]] = []
    for row in _read_csv(csv_path):
        symbol = row.get("symbol", "").strip()
        if not symbol or (symbols and symbol not in symbols):
            continue
        open_ = _number_or_none(row.get("open"))
        high = _number_or_none(row.get("high"))
        low = _number_or_none(row.get("low"))
        close = _number_or_none(row.get("price"))
        trade_date = _display_date(row.get("quote_date", ""))
        if None in {open_, high, low, close} or not trade_date:
            continue
        rows.append(
            {
                "symbol": symbol,
                "date": trade_date,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "ma5": close,
                "ma20": close,
                "ma60": close,
            }
        )
    return rows


def _display_date(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value


def _avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _number_or_none(value: str | None) -> float | None:
    if value is None:
        return None
    raw = value.replace(",", "").replace("--", "").strip()
    if raw in {"", "-", "X", "除權息"}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _number(value: str | None) -> float:
    if value is None or value.strip() == "":
        return 0.0
    return float(value.replace(",", ""))
