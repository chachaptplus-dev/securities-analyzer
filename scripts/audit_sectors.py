"""
Automated sector mis-tagging audit.
Usage: py -3 scripts/audit_sectors.py
"""
from __future__ import annotations
import sys
import re
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

import duckdb

DB_PATH = "data/securities.duckdb"

# ── Sector conflict keywords for Rule 1 ──────────────────────────────────────
# (keyword_in_company_name → expected_sector)
NAME_CONFLICTS: list[tuple[str, str]] = [
    # Shipbuilding
    ("조선",        "Shipbuilding"),
    ("해운",        "Shipping"),
    ("shipping",    "Shipping"),
    # Healthcare
    ("바이오",      "Healthcare / Bio"),
    ("pharma",      "Healthcare / Bio"),
    ("제약",        "Healthcare / Bio"),
    ("메디",        "Healthcare / Bio"),
    ("헬스케어",    "Healthcare / Bio"),
    # Financials
    ("증권",        "Financials"),
    ("은행",        "Financials"),
    ("보험",        "Financials"),
    ("캐피탈",      "Financials"),
    ("자산운용",    "Financials"),
    ("금융",        "Financials"),
    # Construction
    ("건설",        "Construction"),
    ("엔지니어링",  "Construction"),
    # Energy / Utilities
    ("에너지",      "Energy"),
    ("오일",        "Energy"),
    ("oil",         "Energy"),
    ("가스",        "Energy"),
    ("전력",        "Utilities"),
    # Semiconductors
    ("반도체",      "Semiconductors"),
    ("웨이퍼",      "Semiconductors"),
    # Education
    ("교육",        "Education"),
    ("에듀",        "Education"),
    ("학원",        "Education"),
    # Airlines
    ("항공",        "Airlines"),
    ("에어",        "Airlines"),
    ("air",         "Airlines"),
    # Entertainment / Gaming
    ("엔터테인먼트","Entertainment"),
    ("게임",        "Gaming"),
    # Automotive
    ("자동차",      "Automotive"),
    ("모터",        "Automotive"),
    # Telecom
    ("통신",        "Telecom"),
    # Retail
    ("쇼핑",        "Retail"),
    ("마트",        "Retail"),
]

# ── Thesis keyword sets for Rule 2 ───────────────────────────────────────────
THESIS_KW: dict[str, list[str]] = {
    "Semiconductors":   ["반도체", "웨이퍼", "파운드리", "hbm", "낸드", "dram", "팹"],
    "Battery / EV":     ["배터리", "전기차", "2차전지", "양극재", "음극재", "셀"],
    "Healthcare / Bio": ["바이오", "제약", "임상", "신약", "의약품", "파이프라인", "cmo"],
    "Financials":       ["은행", "보험", "증권", "대출", "예금", "이자", "금리"],
    "Shipbuilding":     ["조선", "선박", "해양", "lng선", "드릴십"],
    "Defense":          ["방산", "무기", "탄약", "전차", "미사일", "군"],
    "Automotive":       ["자동차", "완성차", "내연기관", "하이브리드", "suv", "타이어"],
    "Construction":     ["건설", "수주", "공사", "시공", "아파트", "분양"],
    "Entertainment":    ["엔터", "음반", "앨범", "아이돌", "콘서트", "팬덤"],
    "Gaming":           ["게임", "mmo", "모바일게임", "매출", "유저"],
    "IT / Platform":    ["플랫폼", "이커머스", "온라인", "앱"],
    "Telecom":          ["통신", "5g", "네트워크", "기지국"],
    "Energy":           ["정유", "원유", "lng", "lpg", "에너지"],
    "Steel / Metals":   ["철강", "고로", "열연", "냉연", "스테인리스"],
}

SKIP_EXACT = {  # sectors where a strong keyword match is expected — skip false pos
    "Financials": {"Financials"},
}


def _norm(s: str) -> str:
    return re.sub(r"[\s\-·.]", "", (s or "")).lower()


def load_reports(con) -> list[dict]:
    rows = con.execute(
        "SELECT id, company, sector, thesis FROM reports WHERE sector IS NOT NULL"
    ).fetchall()
    return [{"id": r[0], "company": r[1] or "", "sector": r[2] or "", "thesis": r[3] or ""} for r in rows]


# ── Rule 1 ────────────────────────────────────────────────────────────────────
def rule1(reports: list[dict]) -> list[dict]:
    # Sectors that are compatible with each other (no flag needed)
    COMPATIBLE: dict[str, set[str]] = {
        "Energy":               {"Energy / Chemicals", "Utilities", "Renewables"},
        "Energy / Chemicals":   {"Energy", "Chemicals"},
        "Utilities":            {"Energy"},
        "Airlines":             {"Transportation", "Airlines"},
        "Healthcare / Bio":     {"Healthcare / Bio"},
        "Entertainment":        {"Media / Advertising"},
        "Semiconductors":       {"Electronics"},
        "Automotive":           {"Heavy Industry"},
    }

    hits: dict[tuple, dict] = {}
    for r in reports:
        cn = r["company"].lower()
        assigned = r["sector"]
        for kw, expected in NAME_CONFLICTS:
            if kw.lower() in cn and assigned != expected:
                # Skip if sectors are compatible
                compat = COMPATIBLE.get(assigned, set()) | COMPATIBLE.get(expected, set())
                if expected in compat or assigned in compat:
                    continue
                key = (r["company"], assigned, expected)
                if key not in hits:
                    hits[key] = {"company": r["company"], "assigned": assigned,
                                 "expected": expected, "count": 0}
                hits[key]["count"] += 1
    return sorted(hits.values(), key=lambda x: -x["count"])


# ── Rule 2 ────────────────────────────────────────────────────────────────────
def rule2(reports: list[dict], threshold: int = 3) -> list[dict]:
    COMPATIBLE_PAIRS: set[frozenset] = {
        frozenset({"Energy", "Energy / Chemicals"}),
        frozenset({"Energy", "Utilities"}),
        frozenset({"Semiconductors", "Electronics"}),
        frozenset({"Entertainment", "Gaming"}),
        frozenset({"Entertainment", "Media / Advertising"}),
        frozenset({"Automotive", "Heavy Industry"}),
        frozenset({"IT / Platform", "IT / Software"}),
        frozenset({"Financials", "IT / Platform"}),   # fintech
    }

    company_hits: dict[str, dict] = {}
    for r in reports:
        thesis_lower = r["thesis"].lower()
        assigned = r["sector"]
        company = r["company"]

        best_sector = None
        best_count = 0
        for sector, kws in THESIS_KW.items():
            if sector == assigned:
                continue
            cnt = sum(1 for kw in kws if kw in thesis_lower)
            if cnt > best_count:
                best_count = cnt
                best_sector = sector

        if best_sector and best_count >= threshold:
            pair = frozenset({assigned, best_sector})
            if pair in COMPATIBLE_PAIRS:
                continue
            key = (company, assigned, best_sector)
            if key not in company_hits:
                top_kws = [kw for kw in THESIS_KW[best_sector] if kw in thesis_lower]
                company_hits[key] = {
                    "company": company,
                    "assigned": assigned,
                    "suspected": best_sector,
                    "kw_count": best_count,
                    "keywords": top_kws,
                    "report_count": 0,
                }
            company_hits[key]["report_count"] += 1

    return sorted(company_hits.values(), key=lambda x: -x["kw_count"])


# ── Rule 3 ────────────────────────────────────────────────────────────────────
def rule3(con, min_count: int = 3) -> list[dict]:
    rows = con.execute("""
        SELECT sector, COUNT(*) n,
               STRING_AGG(DISTINCT company, ', ' ORDER BY company) companies
        FROM reports
        WHERE sector IS NOT NULL
        GROUP BY sector
        HAVING COUNT(*) < ?
        ORDER BY n
    """, [min_count]).fetchall()
    return [{"sector": r[0], "count": r[1], "companies": r[2]} for r in rows]


# ── Rule 4 ────────────────────────────────────────────────────────────────────
def rule4(con) -> list[dict]:
    rows = con.execute("""
        SELECT company,
               STRING_AGG(DISTINCT sector, ' / ' ORDER BY sector) sectors,
               COUNT(*) total,
               COUNT(DISTINCT sector) n_sectors
        FROM reports
        WHERE sector IS NOT NULL AND company IS NOT NULL AND company != ''
        GROUP BY company
        HAVING COUNT(DISTINCT sector) > 1
        ORDER BY n_sectors DESC, total DESC
    """).fetchall()
    return [{"company": r[0], "sectors": r[1], "total": r[2], "n_sectors": r[3]} for r in rows]


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    con = duckdb.connect(DB_PATH, read_only=True)
    reports = load_reports(con)

    total = con.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    tagged = len(reports)
    print(f"Loaded {tagged} tagged reports (of {total} total)\n")
    print("=" * 72)

    # Rule 1
    r1 = rule1(reports)
    print(f"\n[RULE 1 — Name/Sector Conflict]  ({len(r1)} flagged)")
    if r1:
        print(f"  {'Company':<32} {'Assigned':<22} {'Suspected':<22} {'#'}")
        print("  " + "-" * 68)
        for h in r1:
            print(f"  {h['company']:<32} {h['assigned']:<22} {h['expected']:<22} {h['count']}")
    else:
        print("  (none)")

    # Rule 2
    r2 = rule2(reports)
    print(f"\n[RULE 2 — Thesis/Sector Conflict]  ({len(r2)} flagged)")
    if r2:
        print(f"  {'Company':<30} {'Assigned':<22} {'Suspected':<22} {'KWs':<4} {'Matching keywords'}")
        print("  " + "-" * 100)
        for h in r2[:30]:
            kws = ", ".join(h["keywords"][:5])
            print(f"  {h['company']:<30} {h['assigned']:<22} {h['suspected']:<22} {h['kw_count']:<4} {kws}")
    else:
        print("  (none)")

    # Rule 3
    r3 = rule3(con)
    print(f"\n[RULE 3 — Tiny Sectors (< 3 reports)]  ({len(r3)} sectors)")
    if r3:
        for s in r3:
            companies_preview = (s["companies"] or "")[:80]
            print(f"  {s['sector']:<30} {s['count']}건  {companies_preview}")
    else:
        print("  (none)")

    # Rule 4
    r4 = rule4(con)
    print(f"\n[RULE 4 — Inconsistent Tagging]  ({len(r4)} companies)")
    if r4:
        print(f"  {'Company':<30} {'#Sec'} {'Total':<6} {'Sectors assigned'}")
        print("  " + "-" * 80)
        for h in r4:
            print(f"  {h['company']:<30} {h['n_sectors']:<5} {h['total']:<6} {h['sectors']}")
    else:
        print("  (none)")

    print("\n" + "=" * 72)
    con.close()


if __name__ == "__main__":
    main()
