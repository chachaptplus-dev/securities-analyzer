"""
Dry-run: show date / scanned logic across a sample of all rows.
Prints: filename | fn_date | pdf_date | final_date | rating | notes
No DB writes.
Usage:
  py -3 scripts/dry_run_date_scanned.py [--limit N] [--offset N]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import duckdb

from src.pdf_parser import extract_text_from_pdf
from src.extractor import (
    _date_from_filename, _extract_date, _first_match,
    _RATING_PATTERNS,
)

DB_PATH = "data/securities.duckdb"
UPLOAD_DIR = Path("data/uploads")


def _pdf_date_raw(header: str, full_text: str) -> str | None:
    return _extract_date(header) or _extract_date(full_text)


def main(limit: int, offset: int) -> None:
    con = duckdb.connect(DB_PATH, read_only=True)
    rows = con.execute(
        f"SELECT id, filename, report_date, rating_normalized FROM reports ORDER BY id LIMIT {limit} OFFSET {offset}"
    ).fetchall()
    con.close()

    print(f"{'ID':>5}  {'filename':<40}  {'fn_date':<12}  {'pdf_date':<12}  {'final':<12}  {'rating':<10}  notes")
    print("─" * 120)

    for row_id, filename, db_date, db_rating in rows:
        pdf_path = UPLOAD_DIR / filename
        if not pdf_path.exists():
            print(f"{row_id:>5}  {filename:<40}  {'':12}  {'':12}  {'':12}  {'':10}  NO PDF")
            continue

        try:
            pdf_data = extract_text_from_pdf(str(pdf_path))
        except Exception as e:
            print(f"{row_id:>5}  {filename:<40}  {'':12}  {'':12}  {'':12}  {'':10}  ERROR: {e}")
            continue

        fn_date = _date_from_filename(filename)
        full_text = pdf_data["full_text"]
        pages = pdf_data["pages"]
        header = pages[0]["text"] if pages else ""
        if len(pages) > 1:
            header += "\n" + pages[1]["text"]

        raw_pdf = _pdf_date_raw(header, full_text)
        pdf_date = raw_pdf
        pdf_note = ""
        if pdf_date:
            y = int(pdf_date[:4])
            if y < 2020 or y > 2027:
                pdf_note = f"[{y} out-of-range, discarded]"
                pdf_date = None

        final = fn_date or pdf_date

        # scanned flag
        notes = []
        if pdf_data["scanned"]:
            notes.append("SCANNED")
        if raw_pdf and int(raw_pdf[:4]) not in range(2020, 2028):
            notes.append(pdf_note)
        if final != str(db_date) if db_date else final is not None:
            if db_date and final and str(final) != str(db_date):
                notes.append(f"DB={db_date}")

        # rating from PDF
        rating_raw = _first_match(header, _RATING_PATTERNS, group=1)
        rating_str = rating_raw or ("SCANNED" if pdf_data["scanned"] else db_rating or "?")

        print(
            f"{row_id:>5}  {filename[:40]:<40}  "
            f"{(fn_date or ''):12}  {(raw_pdf or ''):12}  "
            f"{(final or ''):12}  {str(rating_str)[:10]:<10}  "
            + "  ".join(notes)
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()
    main(limit=args.limit, offset=args.offset)
