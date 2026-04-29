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
        page_count    INTEGER,
        uploaded_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE SEQUENCE IF NOT EXISTS reports_id_seq START 1",
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
            securities_firm, analyst, report_date, thesis, page_count
        ) VALUES (
            nextval('reports_id_seq'), ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?, ?
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


def clear_all() -> None:
    con = _con()
    con.execute("DELETE FROM reports")
    con.close()
