"""DuckDB persistence layer for securities reports."""
from typing import Optional

import duckdb
import pandas as pd
from pathlib import Path

_DB_PATH = Path("data/securities.duckdb")

_DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS reports (
        id          INTEGER PRIMARY KEY,
        filename    VARCHAR UNIQUE,
        company     VARCHAR,
        rating_raw  VARCHAR,
        rating_normalized VARCHAR,
        target_price  INTEGER,
        current_price INTEGER,
        upside        DOUBLE,
        securities_firm VARCHAR,
        analyst       VARCHAR,
        report_date   DATE,
        thesis        TEXT,
        sector        VARCHAR,
        page_count    INTEGER,
        uploaded_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE SEQUENCE IF NOT EXISTS reports_id_seq START 1",
    # Migration: add sector column to existing tables created before this version
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS sector VARCHAR",
]


def _con() -> duckdb.DuckDBPyConnection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(_DB_PATH))


def initialize_db() -> None:
    con = _con()
    for stmt in _DDL_STATEMENTS:
        con.execute(stmt)
    con.close()


def insert_report(report: dict) -> Optional[int]:
    con = _con()
    existing = con.execute(
        "SELECT id FROM reports WHERE filename = ?", [report["filename"]]
    ).fetchone()
    if existing:
        con.close()
        return existing[0]

    result = con.execute(
        """
        INSERT INTO reports (
            id, filename, company, rating_raw, rating_normalized,
            target_price, current_price, upside,
            securities_firm, analyst, report_date, thesis, sector, page_count
        ) VALUES (
            nextval('reports_id_seq'), ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?, ?, ?
        ) RETURNING id
        """,
        [
            report.get("filename"),
            report.get("company"),
            report.get("rating_raw"),
            report.get("rating_normalized"),
            report.get("target_price"),
            report.get("current_price"),
            report.get("upside"),
            report.get("securities_firm"),
            report.get("analyst"),
            report.get("report_date"),
            report.get("thesis"),
            report.get("sector"),
            report.get("page_count"),
        ],
    ).fetchone()
    con.close()
    return result[0] if result else None


def get_all_reports() -> pd.DataFrame:
    con = _con()
    df = con.execute("SELECT * FROM reports ORDER BY uploaded_at DESC").df()
    con.close()
    return df


def get_company_detail(company: str) -> pd.DataFrame:
    con = _con()
    df = con.execute(
        "SELECT * FROM reports WHERE company = ? ORDER BY report_date DESC",
        [company],
    ).df()
    con.close()
    return df


_UPDATABLE_FIELDS: frozenset[str] = frozenset({
    "company", "rating_raw", "rating_normalized",
    "target_price", "current_price", "upside",
    "securities_firm", "analyst", "report_date",
    "thesis", "sector",
})


def update_report(report_id: int, fields: dict) -> None:
    """Update whitelisted fields for an existing row by primary key."""
    safe = {k: v for k, v in fields.items() if k in _UPDATABLE_FIELDS}
    if not safe:
        return
    con = _con()
    set_clause = ", ".join(f"{k} = ?" for k in safe)
    con.execute(
        f"UPDATE reports SET {set_clause} WHERE id = ?",
        list(safe.values()) + [report_id],
    )
    con.close()


def clear_all() -> None:
    con = _con()
    con.execute("DELETE FROM reports")
    con.close()


def backfill_sectors() -> tuple[int, int]:
    """
    Two-pass sector backfill.

    Pass 1 — company-map override: update ALL rows whose company name matches
              the authoritative COMPANY_SECTOR dict (fixes wrong keyword tags too).
    Pass 2 — keyword fill: update remaining NULL rows via thesis keyword scan.

    Returns (pass1_count, pass2_count).
    """
    from src.sector import infer_sector, map_company

    con = _con()
    all_rows = con.execute("SELECT id, company, thesis, sector FROM reports").fetchall()

    pass1 = pass2 = 0

    for row_id, company, thesis, current_sector in all_rows:
        # Pass 1: authoritative company-map lookup (uses Korean/Latin threshold fix)
        mapped = map_company(company or "")

        if mapped and mapped != current_sector:
            con.execute("UPDATE reports SET sector = ? WHERE id = ?", [mapped, row_id])
            pass1 += 1
            continue

        # Pass 2: keyword fill for still-NULL rows
        if current_sector is None and not mapped:
            kw_sector = infer_sector(thesis or "", company or "")
            if kw_sector:
                con.execute("UPDATE reports SET sector = ? WHERE id = ?", [kw_sector, row_id])
                pass2 += 1

    con.close()
    return pass1, pass2
