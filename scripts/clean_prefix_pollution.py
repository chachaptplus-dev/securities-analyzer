"""
Diagnose and clean company name prefix pollution in DuckDB.
Usage: py -3 scripts/clean_prefix_pollution.py [--dry-run]
"""
from __future__ import annotations
import argparse
import sys
sys.stdout.reconfigure(encoding="utf-8")

import duckdb

DB_PATH = "data/securities.duckdb"

PREFIXES = [
    "Issue & News",
    "Issue Comment",
    "Results Comment",
    "Trading Update",
    "(잠정실적)",
]


def show_affected(con: duckdb.DuckDBPyConnection) -> dict[str, list[tuple]]:
    result = {}
    for prefix in PREFIXES:
        rows = con.execute(
            "SELECT id, company FROM reports WHERE company LIKE ? ORDER BY id",
            [prefix + "%"],
        ).fetchall()
        result[prefix] = rows
    # Also catch plain leading "(" not covered above
    paren_rows = con.execute(
        "SELECT id, company FROM reports WHERE company LIKE '(%' AND company NOT LIKE '(잠정실적)%' ORDER BY id"
    ).fetchall()
    result["( (other)"] = paren_rows
    return result


def run(dry_run: bool) -> None:
    con = duckdb.connect(DB_PATH)

    print("=" * 60)
    print("STEP 1 — AFFECTED ROWS")
    print("=" * 60)
    affected = show_affected(con)
    total_before = 0
    for prefix, rows in affected.items():
        if rows:
            print(f"\n[{prefix}]  ({len(rows)} rows)")
            for row_id, company in rows:
                print(f"  id={row_id:5d}  {company!r}")
            total_before += len(rows)
    print(f"\nTotal affected: {total_before}")

    if dry_run:
        print("\n[DRY RUN — no writes]")
        con.close()
        return

    print("\n" + "=" * 60)
    print("STEP 2 — APPLY UPDATES")
    print("=" * 60)

    for prefix in PREFIXES:
        rows_before = con.execute(
            "SELECT COUNT(*) FROM reports WHERE company LIKE ?", [prefix + "%"]
        ).fetchone()[0]
        if rows_before == 0:
            print(f"  {prefix!r}: nothing to do")
            continue
        con.execute(
            "UPDATE reports SET company = TRIM(SUBSTR(company, ? + 1)) WHERE company LIKE ?",
            [len(prefix), prefix + "%"],
        )
        rows_after = con.execute(
            "SELECT COUNT(*) FROM reports WHERE company LIKE ?", [prefix + "%"]
        ).fetchone()[0]
        print(f"  {prefix!r}: {rows_before} rows fixed ({rows_after} remaining)")

    # Strip leading "(" for other cases (not 잠정실적)
    paren_rows = con.execute(
        "SELECT COUNT(*) FROM reports WHERE company LIKE '(%' AND company NOT LIKE '(잠정실적)%'"
    ).fetchone()[0]
    if paren_rows:
        # Just strip the leading "("
        con.execute(
            "UPDATE reports SET company = TRIM(SUBSTR(company, 2)) "
            "WHERE company LIKE '(%' AND company NOT LIKE '(잠정실적)%'"
        )
        print(f"  '(' prefix: {paren_rows} rows fixed")

    print("\n" + "=" * 60)
    print("STEP 3 — VERIFICATION")
    print("=" * 60)
    remaining = show_affected(con)
    any_remaining = False
    for prefix, rows in remaining.items():
        if rows:
            print(f"  STILL DIRTY [{prefix}]: {rows}")
            any_remaining = True
    if not any_remaining:
        print("  All patterns clean.")

    print("\n=== Suspicious names (length > 15) ===")
    suspicious = con.execute(
        "SELECT company, length(company) l FROM reports "
        "WHERE company IS NOT NULL AND length(company) > 15 "
        "GROUP BY company ORDER BY l DESC LIMIT 30"
    ).fetchall()
    for company, l in suspicious:
        print(f"  len={l:3d}  {company!r}")

    con.close()
    print("\nDone.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
