from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def normalize_raw_directory(raw_dir: str | Path, output_dir: str | Path) -> list[Path]:
    raw_path = Path(raw_dir)
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw input directory does not exist: {raw_path}")

    saved: list[Path] = []
    for csv_path in sorted(raw_path.glob("*.csv")):
        output_path = Path(output_dir) / csv_path.name
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(csv_path.read_text(encoding="utf-8-sig"), encoding="utf-8-sig")
        saved.append(output_path)
    for json_path in sorted(raw_path.glob("*.json")):
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        for index, table in enumerate(_extract_tables(payload), start=1):
            fields = _dedupe_fields([_clean_cell(field) for field in table.get("fields", [])])
            rows = table.get("data", [])
            if not fields or not rows:
                continue

            output_path = Path(output_dir) / f"{json_path.stem}_table{index}.csv"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(fields)
                for row in rows:
                    writer.writerow([_clean_cell(cell) for cell in row])
            saved.append(output_path)
    return saved


def _extract_tables(payload: dict[str, Any]) -> list[dict[str, Any]]:
    tables = payload.get("tables")
    if isinstance(tables, list):
        return [table for table in tables if isinstance(table, dict)]
    if isinstance(payload.get("fields"), list) and isinstance(payload.get("data"), list):
        return [payload]
    return []


def _clean_cell(value: Any) -> str:
    return str(value).replace(",", "").strip()


def _dedupe_fields(fields: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for field in fields:
        base = field or "column"
        seen[base] = seen.get(base, 0) + 1
        if seen[base] == 1:
            result.append(base)
        else:
            result.append(f"{base}_{seen[base]}")
    return result
