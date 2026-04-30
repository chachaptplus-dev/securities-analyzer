"""
Re-parse PDFs for rows where company IS NULL OR rating_normalized = 'UNKNOWN'.
Usage:
  Dry-run (print only, no DB writes):
    py -3 scripts/reparse_unknown.py --dry-run [--limit N]

  Apply updates:
    py -3 scripts/reparse_unknown.py [--limit N]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import duckdb

from src.pdf_parser import extract_text_from_pdf
from src.extractor import extract_report_data, _infer_sentiment
from src.rating_normalizer import normalize_rating
from src.sector import infer_sector, map_company
from src.database import update_report

DB_PATH = "data/securities.duckdb"
UPLOAD_DIR = Path("data/uploads")

# ── helpers ──────────────────────────────────────────────────────────────────

def _compute_upside(tp, cp) -> float | None:
    if tp and cp and cp > 0:
        return round((tp - cp) / cp * 100, 1)
    return None


def _normalize(report: dict) -> str:
    """Derive rating_normalized from raw + sentiment fallback."""
    if report.get("_scanned"):
        return "SCANNED"
    raw = report.get("rating_raw")
    normalized = normalize_rating(raw)
    if normalized == "UNKNOWN":
        sentiment = _infer_sentiment(report.get("thesis") or "")
        if sentiment:
            return sentiment
    return normalized


# ── main ─────────────────────────────────────────────────────────────────────

def main(dry_run: bool, limit: int) -> None:
    con = duckdb.connect(DB_PATH, read_only=True)
    rows = con.execute("""
        SELECT id, filename, company, rating_normalized, report_date, thesis, sector
        FROM reports
        WHERE company IS NULL OR rating_normalized = 'UNKNOWN'
        ORDER BY id
    """).fetchall()
    con.close()

    print(f"Candidate rows: {len(rows)}")
    if limit:
        rows = rows[:limit]
        print(f"Sampling first {len(rows)}")
    print()

    stats = {"scanned": 0, "company_found": 0, "rating_improved": 0,
             "date_found": 0, "no_pdf": 0, "unchanged": 0}

    for row_id, filename, old_company, old_rating, old_date, old_thesis, old_sector in rows:
        pdf_path = UPLOAD_DIR / filename
        if not pdf_path.exists():
            stats["no_pdf"] += 1
            continue

        try:
            pdf_data = extract_text_from_pdf(str(pdf_path))
            report = extract_report_data(pdf_data)
        except Exception as exc:
            print(f"  [ERROR] {filename}: {exc}")
            continue

        new_rating = _normalize(report)
        new_company = report.get("company")
        new_date = report.get("date")
        new_thesis = report.get("thesis") or ""
        new_sector = (
            map_company(new_company) or infer_sector(new_thesis, new_company or "")
            if new_company
            else old_sector
        )
        new_upside = _compute_upside(report.get("target_price"), report.get("current_price"))

        # Collect fields that actually changed / improved
        updates: dict = {}

        if report.get("_scanned"):
            stats["scanned"] += 1
            updates["rating_normalized"] = "SCANNED"

        else:
            if new_company and not old_company:
                updates["company"] = new_company
                stats["company_found"] += 1

            if new_rating != old_rating and new_rating != "UNKNOWN":
                updates["rating_normalized"] = new_rating
                updates["rating_raw"] = report.get("rating_raw")
                stats["rating_improved"] += 1

            if new_date and not old_date:
                updates["report_date"] = new_date
                stats["date_found"] += 1

            if new_sector and new_sector != old_sector and new_company:
                updates["sector"] = new_sector

            if report.get("target_price"):
                updates["target_price"] = report["target_price"]
            if report.get("current_price"):
                updates["current_price"] = report["current_price"]
            if new_upside is not None:
                updates["upside"] = new_upside
            if report.get("securities_firm"):
                updates["securities_firm"] = report["securities_firm"]
            if report.get("analyst"):
                updates["analyst"] = report["analyst"]
            if new_thesis and (not old_thesis or len(new_thesis) > len(old_thesis or "")):
                updates["thesis"] = new_thesis

        if not updates:
            stats["unchanged"] += 1
            continue

        # ── Print result ──────────────────────────────────────────────────────
        print(f"  [{row_id}] {filename[:55]}")
        if new_company and not old_company:
            print(f"    company      : None → {new_company!r}")
        if "rating_normalized" in updates:
            print(f"    rating       : {old_rating!r} → {updates['rating_normalized']!r}")
        if "report_date" in updates:
            print(f"    date         : None → {new_date}")
        if "sector" in updates:
            print(f"    sector       : {old_sector!r} → {new_sector!r}")
        if report.get("target_price"):
            print(f"    target_price : {report['target_price']:,}")
        if new_upside is not None:
            print(f"    upside       : {new_upside}%")
        print()

        # ── Apply updates (unless dry-run) ────────────────────────────────────
        if not dry_run:
            update_report(row_id, updates)

    print("─" * 60)
    print(f"Scanned PDFs      : {stats['scanned']}")
    print(f"Company found     : {stats['company_found']}")
    print(f"Rating improved   : {stats['rating_improved']}")
    print(f"Date from filename: {stats['date_found']}")
    print(f"No PDF on disk    : {stats['no_pdf']}")
    print(f"No change         : {stats['unchanged']}")
    if dry_run:
        print("\n[DRY RUN — no DB writes]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0,
                        help="Process only the first N rows (0 = all)")
    args = parser.parse_args()
    main(dry_run=args.dry_run, limit=args.limit)
