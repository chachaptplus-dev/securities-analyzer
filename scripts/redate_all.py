"""
Re-normalize report_date for every row:
  1. filename date (YYYYMMDD prefix) always wins
  2. If no filename date: re-parse PDF, discard year < 2020 or > 2027

Usage:
  Dry-run:  py -3 scripts/redate_all.py --dry-run
  Apply:    py -3 scripts/redate_all.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import duckdb

from src.extractor import _date_from_filename, _extract_date
from src.database import update_report

DB_PATH = "data/securities.duckdb"
UPLOAD_DIR = Path("data/uploads")


def _validated_pdf_date(filename: str) -> str | None:
    """Open PDF, extract date, discard if year out of [2020, 2027]."""
    from src.pdf_parser import extract_text_from_pdf
    pdf_path = UPLOAD_DIR / filename
    if not pdf_path.exists():
        return None
    try:
        pdf_data = extract_text_from_pdf(str(pdf_path))
        pages = pdf_data["pages"]
        header = pages[0]["text"] if pages else ""
        if len(pages) > 1:
            header += "\n" + pages[1]["text"]
        d = _extract_date(header) or _extract_date(pdf_data["full_text"])
        if d and 2020 <= int(d[:4]) <= 2027:
            return d
    except Exception:
        pass
    return None


def main(dry_run: bool) -> None:
    con = duckdb.connect(DB_PATH, read_only=True)
    rows = con.execute(
        "SELECT id, filename, report_date FROM reports ORDER BY id"
    ).fetchall()
    con.close()

    print(f"Total rows: {len(rows)}")

    stats = {
        "fn_wins":       0,   # filename date replaced wrong PDF date
        "fn_fills":      0,   # filename date filled a NULL
        "pdf_corrected": 0,   # PDF date year fixed (out-of-range discarded)
        "unchanged":     0,
        "no_date":       0,
    }

    for row_id, filename, db_date in rows:
        fn_date = _date_from_filename(filename)

        if fn_date:
            new_date = fn_date
        else:
            new_date = _validated_pdf_date(filename)

        db_str = str(db_date) if db_date else None

        if new_date == db_str:
            stats["unchanged"] += 1
            continue

        if new_date is None:
            stats["no_date"] += 1
            continue

        # Categorise the change
        if db_str is None:
            stats["fn_fills"] += 1
        elif fn_date and db_str != fn_date:
            stats["fn_wins"] += 1
        else:
            stats["pdf_corrected"] += 1

        if not dry_run:
            update_report(row_id, {"report_date": new_date})

    print()
    print("─" * 50)
    print(f"Filename date filled NULL : {stats['fn_fills']}")
    print(f"Filename date replaced PDF: {stats['fn_wins']}")
    print(f"PDF date year-corrected   : {stats['pdf_corrected']}")
    print(f"No date available         : {stats['no_date']}")
    print(f"Unchanged                 : {stats['unchanged']}")
    total_updated = stats["fn_fills"] + stats["fn_wins"] + stats["pdf_corrected"]
    print(f"Total updated             : {total_updated}")
    if dry_run:
        print("\n[DRY RUN — no DB writes]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
