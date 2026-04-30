"""
Strip report-type prefixes from company names and null-out sentence/overlong values.
Usage:
  Dry-run (print only, no DB writes):
    py -3 scripts/clean_company_names.py --dry-run [--limit N]

  Apply updates:
    py -3 scripts/clean_company_names.py [--limit N]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import duckdb

from src.extractor import _clean_company
from src.database import update_report

DB_PATH = "data/securities.duckdb"


def main(dry_run: bool, limit: int) -> None:
    con = duckdb.connect(DB_PATH, read_only=True)
    rows = con.execute(
        "SELECT id, company FROM reports WHERE company IS NOT NULL ORDER BY id"
    ).fetchall()
    con.close()

    print(f"Rows with company: {len(rows)}")

    changes: list[tuple[int, str, str | None]] = []
    for row_id, company in rows:
        cleaned = _clean_company(company)
        if cleaned != company:
            changes.append((row_id, company, cleaned))

    print(f"Rows to update  : {len(changes)}")
    print()

    sample = changes[:limit] if limit else changes[:20]
    for row_id, old, new in sample:
        arrow = "→ None (nulled)" if new is None else f"→ {new!r}"
        print(f"  [{row_id:>4}]  {old!r}")
        print(f"          {arrow}")
        print()

    if len(changes) > len(sample):
        print(f"  ... ({len(changes) - len(sample)} more not shown)")
        print()

    print("─" * 60)
    nulled = sum(1 for _, _, n in changes if n is None)
    renamed = sum(1 for _, _, n in changes if n is not None)
    print(f"Prefix stripped : {renamed}")
    print(f"Nulled          : {nulled}")

    if dry_run:
        print("\n[DRY RUN — no DB writes]")
        return

    for row_id, _, new in changes:
        update_report(row_id, {"company": new})
    print(f"\nApplied {len(changes)} updates.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0,
                        help="Show only first N samples in preview (0 = 20)")
    args = parser.parse_args()
    main(dry_run=args.dry_run, limit=args.limit)
