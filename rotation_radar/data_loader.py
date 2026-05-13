from __future__ import annotations

import csv
from pathlib import Path

from .models import SectorMetrics, StockMetrics


class DataFormatError(ValueError):
    """Raised when an input data file is missing required fields."""


SECTOR_COLUMNS = {
    "name",
    "theme",
    "capital_inflow_rank",
    "turnover_share_change",
    "industry_trend",
    "overseas_signal",
    "pe_percentile",
    "risk_heat",
    "catalysts",
    "risks",
}

STOCK_COLUMNS = {
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
    "revenue_yoy",
    "revenue_mom",
    "technical_setup",
    "liquidity",
    "risk_heat",
    "thesis",
    "risk_reason",
}


def load_dataset(data_dir: str | Path) -> tuple[list[SectorMetrics], list[StockMetrics]]:
    base = Path(data_dir)
    sectors = load_sector_metrics(base / "sector_metrics.csv")
    stocks = load_stock_metrics(base / "stock_metrics.csv")
    _validate_stock_sectors(sectors, stocks)
    return sectors, stocks


def load_sector_metrics(path: str | Path) -> list[SectorMetrics]:
    rows = _read_dicts(path, SECTOR_COLUMNS)
    return [
        SectorMetrics(
            name=row["name"],
            theme=row["theme"],
            capital_inflow_rank=_to_float(row, "capital_inflow_rank"),
            turnover_share_change=_to_float(row, "turnover_share_change"),
            capital_share=_to_float_default(row, "capital_share", 0.0),
            capital_share_prev=_to_float_default(row, "capital_share_prev", 0.0),
            turnover_value=_to_float_default(row, "turnover_value", 0.0),
            turnover_value_prev=_to_float_default(row, "turnover_value_prev", 0.0),
            momentum_20d=_to_float(row, "momentum_20d"),
            strong_stock_ratio=_to_float(row, "strong_stock_ratio"),
            industry_trend=_to_float(row, "industry_trend"),
            overseas_signal=_to_float(row, "overseas_signal"),
            pe_percentile=_to_float(row, "pe_percentile"),
            risk_heat=_to_float(row, "risk_heat"),
            catalysts=_split_list(row["catalysts"]),
            risks=_split_list(row["risks"]),
        )
        for row in rows
    ]


def load_stock_metrics(path: str | Path) -> list[StockMetrics]:
    rows = _read_dicts(path, STOCK_COLUMNS)
    return [
        StockMetrics(
            symbol=row["symbol"],
            name=row["name"],
            sector=row["sector"],
            close=_to_float(row, "close"),
            pullback_quality=_to_float(row, "pullback_quality"),
            chip_cleanliness=_to_float(row, "chip_cleanliness"),
            foreign_5d=_to_float(row, "foreign_5d"),
            trust_5d=_to_float(row, "trust_5d"),
            margin_change_5d=_to_float(row, "margin_change_5d"),
            pe=_to_float(row, "pe"),
            sector_pe_low=_to_float(row, "sector_pe_low"),
            sector_pe_avg=_to_float(row, "sector_pe_avg"),
            sector_pe_high=_to_float(row, "sector_pe_high"),
            fair_value_low=_to_float_default(row, "fair_value_low", 0.0),
            fair_value_avg=_to_float_default(row, "fair_value_avg", 0.0),
            fair_value_high=_to_float_default(row, "fair_value_high", 0.0),
            revenue_yoy=_to_float(row, "revenue_yoy"),
            revenue_mom=_to_float(row, "revenue_mom"),
            technical_setup=_to_float(row, "technical_setup"),
            liquidity=_to_float(row, "liquidity"),
            risk_heat=_to_float(row, "risk_heat"),
            thesis=row["thesis"],
            risk_reason=row["risk_reason"],
        )
        for row in rows
    ]


def _read_dicts(path: str | Path, required_columns: set[str]) -> list[dict[str, str]]:
    csv_path = Path(path)
    if not csv_path.exists():
        raise DataFormatError(f"Missing data file: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = sorted(required_columns - fieldnames)
        if missing:
            raise DataFormatError(f"{csv_path} is missing columns: {', '.join(missing)}")
        return [dict(row) for row in reader]


def _to_float(row: dict[str, str], key: str) -> float:
    raw = row[key].strip()
    if raw == "":
        raise DataFormatError(f"Missing numeric value for {key}")
    try:
        return float(raw)
    except ValueError as exc:
        raise DataFormatError(f"Invalid numeric value for {key}: {raw}") from exc


def _to_float_default(row: dict[str, str], key: str, default: float) -> float:
    if key not in row or row[key].strip() == "":
        return default
    return _to_float(row, key)


def _split_list(raw: str) -> list[str]:
    return [item.strip() for item in raw.split("|") if item.strip()]


def _validate_stock_sectors(sectors: list[SectorMetrics], stocks: list[StockMetrics]) -> None:
    sector_names = {sector.name for sector in sectors}
    unknown = sorted({stock.sector for stock in stocks if stock.sector not in sector_names})
    if unknown:
        raise DataFormatError(f"Stocks reference unknown sectors: {', '.join(unknown)}")
