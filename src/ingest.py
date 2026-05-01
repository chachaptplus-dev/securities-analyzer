"""Process PDFs in data/uploads/ that are not yet in the database.

Run standalone: py -3 src/ingest.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import duckdb

from src.database import initialize_db, insert_report
from src.extractor import extract_report_data, _infer_sentiment
from src.pdf_parser import extract_text_from_pdf
from src.rating_normalizer import normalize_rating
from src.sector import infer_sector

UPLOAD_DIR = Path("data/uploads")
DB_PATH = Path("data/securities.duckdb")


def _known_filenames() -> set:
    if not DB_PATH.exists():
        return set()
    con = duckdb.connect(str(DB_PATH))
    rows = con.execute("SELECT filename FROM reports").fetchall()
    con.close()
    return {row[0] for row in rows}


def _process(pdf_path: Path) -> bool:
    try:
        pdf_data = extract_text_from_pdf(str(pdf_path))
        report = extract_report_data(pdf_data)
        report["rating_normalized"] = normalize_rating(report.get("rating_raw"))
        if report["rating_normalized"] == "UNKNOWN":
            report["rating_normalized"] = _infer_sentiment(report.get("thesis") or "")
        tp = report.get("target_price")
        cp = report.get("current_price")
        if tp and cp and cp > 0 and tp > cp * 3:
            report["current_price"] = None
            cp = None
        report["upside"] = round((tp - cp) / cp * 100, 1) if (tp and cp and cp > 0) else None
        report["report_date"] = report.pop("date", None)
        report["sector"] = infer_sector(report.get("thesis") or "", report.get("company") or "")
        insert_report(report)
        return True
    except Exception as exc:
        print(f"  ERROR {pdf_path.name}: {exc}", file=sys.stderr)
        return False


def ingest() -> int:
    """Return count of newly inserted reports."""
    initialize_db()
    known = _known_filenames()
    new_pdfs = sorted(p for p in UPLOAD_DIR.glob("*.pdf") if p.name not in known)

    if not new_pdfs:
        print("No new PDFs to process.")
        return 0

    print(f"Processing {len(new_pdfs)} new PDF(s)...")
    ok = sum(1 for p in new_pdfs if _process(p) and print(f"  + {p.name}") is None)
    print(f"\nDone. {ok}/{len(new_pdfs)} report(s) added to database.")
    return ok


if __name__ == "__main__":
    sys.exit(0 if ingest() >= 0 else 1)
