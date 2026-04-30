"""
LLM-assisted re-extraction for rows with UNKNOWN rating or NULL company.

Uses Claude Haiku for cost efficiency (~$0.001 per row).

Usage:
  Dry-run (no API calls):  py -3 scripts/llm_reparse.py --dry-run
  Test first 10 rows:      py -3 scripts/llm_reparse.py --limit 10
  Full run:                py -3 scripts/llm_reparse.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

# Load .env from project root if present (fallback for when key isn't in shell env)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

import duckdb
import anthropic

from src.pdf_parser import extract_text_from_pdf
from src.database import update_report
from src.rating_normalizer import normalize_rating
from src.sector import infer_sector

DB_PATH = "data/securities.duckdb"
UPLOAD_DIR = Path("data/uploads")
MODEL = "claude-haiku-4-5-20251001"
MAX_TEXT_CHARS = 2000   # header chars sent to LLM
RATE_LIMIT_SLEEP = 0.5  # seconds between API calls


_SYSTEM = """\
You extract structured data from Korean securities research reports.
Return ONLY valid JSON with these exact keys — no explanation, no markdown fences:
{
  "company": "<Korean or English company/stock name, null if not found>",
  "rating": "<BUY | HOLD | SELL, null if not found>",
  "target_price": <integer Korean Won price, null if not found>,
  "current_price": <integer Korean Won price, null if not found>
}
Rules:
- company: the stock/company being analysed, NOT the securities firm writing the report
- rating: normalise all variants — 매수→BUY, 중립/보유→HOLD, 매도→SELL
- prices: integers only, no commas/units
"""

_USER_TMPL = """\
Extract the four fields from this Korean securities report excerpt.

--- REPORT TEXT ---
{text}
--- END ---
"""


def _get_header_text(filename: str) -> str:
    pdf_path = UPLOAD_DIR / filename
    if not pdf_path.exists():
        return ""
    try:
        data = extract_text_from_pdf(str(pdf_path))
        pages = data.get("pages", [])
        parts = []
        for p in pages[:2]:
            parts.append(p.get("text", ""))
        return "\n".join(parts)[:MAX_TEXT_CHARS]
    except Exception:
        return ""


def _call_llm(client: anthropic.Anthropic, text: str) -> dict:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=256,
        system=_SYSTEM,
        messages=[{"role": "user", "content": _USER_TMPL.format(text=text)}],
    )
    raw = resp.content[0].text.strip()
    # Strip markdown fences if model added them anyway
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


def _get_target_rows(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """
    Returns rows where we need LLM help:
      - rating_normalized = 'UNKNOWN'  OR  company IS NULL
    Prioritises rows that have at least some thesis text.
    """
    return con.execute("""
        SELECT id, filename, company, rating_normalized, target_price, current_price, thesis
        FROM reports
        WHERE rating_normalized = 'UNKNOWN' OR company IS NULL
        ORDER BY
            CASE WHEN thesis IS NOT NULL AND length(thesis) > 10 THEN 0 ELSE 1 END,
            id
    """).fetchall()


def run(dry_run: bool, limit: int | None) -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=api_key) if not dry_run else None
    con = duckdb.connect(DB_PATH, read_only=True)
    rows = _get_target_rows(con)
    con.close()

    if limit:
        rows = rows[:limit]

    print(f"Target rows: {len(rows)}")
    if dry_run:
        print("[DRY RUN — no API calls]\n")
        for row in rows[:20]:
            row_id, filename, company, rating, tp, cp, thesis = row
            text = _get_header_text(filename)
            print(
                f"  id={row_id:5d} | company={str(company)[:15]:15s} | "
                f"rating={rating:8s} | text_len={len(text):4d} | file={filename}"
            )
        if len(rows) > 20:
            print(f"  ... and {len(rows) - 20} more")
        return

    stats = {"updated": 0, "skipped_no_text": 0, "error": 0, "no_change": 0}
    input_tokens = output_tokens = 0

    for i, row in enumerate(rows):
        row_id, filename, company, rating_norm, tp, cp, thesis = row

        # Build text: prefer PDF header, fall back to thesis
        text = _get_header_text(filename)
        if not text and thesis:
            text = (thesis or "")[:MAX_TEXT_CHARS]

        if len(text.strip()) < 30:
            stats["skipped_no_text"] += 1
            print(f"  [{i+1}/{len(rows)}] id={row_id} SKIP (no text)")
            continue

        try:
            result = _call_llm(client, text)
            time.sleep(RATE_LIMIT_SLEEP)
        except Exception as exc:
            stats["error"] += 1
            print(f"  [{i+1}/{len(rows)}] id={row_id} ERROR: {exc}")
            continue

        # Build update dict — only fill gaps, don't overwrite good data
        updates: dict = {}

        llm_company = (result.get("company") or "").strip() or None
        if company is None and llm_company and len(llm_company) <= 20:
            updates["company"] = llm_company

        llm_rating = (result.get("rating") or "").upper().strip()
        if rating_norm == "UNKNOWN" and llm_rating in {"BUY", "HOLD", "SELL"}:
            updates["rating_normalized"] = llm_rating
            updates["rating_raw"] = llm_rating

        llm_tp = result.get("target_price")
        if tp is None and isinstance(llm_tp, int) and 1000 < llm_tp < 10_000_000:
            updates["target_price"] = llm_tp

        llm_cp = result.get("current_price")
        if cp is None and isinstance(llm_cp, int) and 1000 < llm_cp < 10_000_000:
            updates["current_price"] = llm_cp

        # Recompute upside if we now have both prices
        final_tp = updates.get("target_price", tp)
        final_cp = updates.get("current_price", cp)
        if final_tp and final_cp and final_cp > 0:
            updates["upside"] = round((final_tp - final_cp) / final_cp * 100, 1)

        # Infer sector if company was just recovered
        if "company" in updates and updates["company"]:
            sec = infer_sector(thesis or text, updates["company"])
            if sec:
                updates["sector"] = sec

        if updates:
            update_report(row_id, updates)
            stats["updated"] += 1
            print(
                f"  [{i+1}/{len(rows)}] id={row_id} UPDATED: {updates}"
            )
        else:
            stats["no_change"] += 1
            print(
                f"  [{i+1}/{len(rows)}] id={row_id} no_change "
                f"(llm={result})"
            )

    print()
    print("─" * 55)
    print(f"Updated          : {stats['updated']}")
    print(f"No change        : {stats['no_change']}")
    print(f"Skipped (no text): {stats['skipped_no_text']}")
    print(f"Errors           : {stats['error']}")
    print(f"Total processed  : {len(rows)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process at most N rows (for testing)")
    args = parser.parse_args()

    if not args.dry_run and not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    run(dry_run=args.dry_run, limit=args.limit)
