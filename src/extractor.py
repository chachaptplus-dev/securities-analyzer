"""
Structured field extractor for Korean securities PDF reports.
Replace `extract_report_data` with an LLM-backed version to upgrade accuracy.

Actual PDF formats observed (2026-04):
  Company   : "iM금융 (139130)"  /  "(009830)\n한화솔루션"  /  "삼성SDI 006400"
              "삼성SDI (006400/KS)"  /  word-wrapped "HD현대일렉트\n릭\n(267260)"
              "(028260. KS)\n삼성물산"  /  "082740 · 조선\n한화엔진"
              "은행\n기업은행 024110"
  Rating    : "BUY (유지)"  /  "매수 (유지)"  /  "투자의견\nBUY(유지)"
  TP        : "목표주가(12M)\n24,500원(상향)"  /  "TP 880,000 원"
              "6개월 목표주가\n1,500,000\n상향"  (no 원, three lines)
  CurPrice  : "현재주가(4.28)\n19,280원"  /  "현재가 (4/28)\n680,000원"
              "현재주가\n(26.04.28)\n1,238,000"  (three lines, no 원)
              "주가(4/28): 76,500원"  /  "종가(2026.04.28)\n167,100원"
"""
import re
from pathlib import Path
from typing import Optional, List

# ---------------------------------------------------------------------------
# Sentiment keywords (Fix E)
# ---------------------------------------------------------------------------

_POSITIVE_KW: frozenset[str] = frozenset({"성장", "호조", "개선", "확대", "수혜", "상승", "긍정", "기대"})
_NEGATIVE_KW: frozenset[str] = frozenset({"부진", "악화", "하락", "우려", "리스크", "감소", "위축"})

# ---------------------------------------------------------------------------
# Company name sanitisation — strip report-type prefixes, reject sentences
# ---------------------------------------------------------------------------

_COMPANY_PREFIX_RE = re.compile(
    r"^(?:Earnings\s*Preview|Issue\s+Comment|Results?\s*Comments?|"
    r"Company\s*Report|Initiation|Update)\s*",
    re.IGNORECASE,
)
_KO_COMPANY_PREFIX_RE = re.compile(r"^기업분석\s*")
_STAR_RE = re.compile(r"[★☆]+")
_SENTENCE_STARTERS = ("양호한", "견조한", "전망")


def _clean_company(name: Optional[str]) -> Optional[str]:
    """Strip known report-type prefixes; return None for sentences or names > 20 chars."""
    if not name:
        return None
    name = _COMPANY_PREFIX_RE.sub("", name)
    name = _KO_COMPANY_PREFIX_RE.sub("", name)
    name = _STAR_RE.sub("", name).strip()
    if not name:
        return None
    if len(name) > 20:
        return None
    if any(name.startswith(s) for s in _SENTENCE_STARTERS):
        return None
    return name

# ---------------------------------------------------------------------------
# Stock master — code → name lookup (Fix G)
# ---------------------------------------------------------------------------

_STOCK_MASTER: Optional[dict[str, str]] = None   # cache after first load
_MASTER_PATH = Path("data/stock_master.csv")


def _load_stock_master() -> dict[str, str]:
    """Load code→name dict from CSV, building cache on first call."""
    global _STOCK_MASTER
    if _STOCK_MASTER is not None:
        return _STOCK_MASTER
    if not _MASTER_PATH.exists():
        _STOCK_MASTER = {}
        return _STOCK_MASTER
    import csv
    mapping: dict[str, str] = {}
    with open(_MASTER_PATH, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = (row.get("code") or "").strip().zfill(6)
            name = (row.get("name") or "").strip()
            if code and name:
                mapping[code] = name
    _STOCK_MASTER = mapping
    return _STOCK_MASTER


def lookup_company_by_code(code: str) -> Optional[str]:
    """Return company name for a 6-digit KRX stock code, or None."""
    if not code or not re.fullmatch(r"\d{6}", code.strip()):
        return None
    return _load_stock_master().get(code.strip())


# Reverse index: normalised name → canonical name (built lazily from stock master)
_STOCK_MASTER_BY_NAME: Optional[dict[str, str]] = None

_NORM_NAME_RE = re.compile(r"[\s.·&]")


def _load_name_index() -> dict[str, str]:
    global _STOCK_MASTER_BY_NAME
    if _STOCK_MASTER_BY_NAME is not None:
        return _STOCK_MASTER_BY_NAME
    _STOCK_MASTER_BY_NAME = {
        _NORM_NAME_RE.sub("", name).lower(): name
        for name in _load_stock_master().values()
    }
    return _STOCK_MASTER_BY_NAME


def _reverse_lookup_name(name: str) -> Optional[str]:
    """Return canonical stock-master name if input normalises to a match, else None."""
    key = _NORM_NAME_RE.sub("", name).lower()
    return _load_name_index().get(key)


def _extract_company_from_thesis(thesis: str) -> Optional[str]:
    """
    Fix H — thesis-lead fallback.
    If thesis opens with 'CompanyName의 ...', return CompanyName.
    Rejects candidates that start with a digit (avoids '4Q25의', '1분기의').
    """
    m = re.match(r"^([가-힣A-Za-z0-9·&. ]{2,15}?)의\s", thesis.strip())
    if not m:
        return None
    candidate = m.group(1).strip()
    if len(candidate) < 2 or candidate[0].isdigit():
        return None
    if not (re.search(r"[가-힣]", candidate) or re.search(r"[A-Za-z]{2,}", candidate)):
        return None
    return candidate


def _extract_code_from_header(text: str) -> Optional[str]:
    """
    Pull the first plausible 6-digit KRX stock code from PDF header text.
    Checked in preference order: parens (most reliable) → bare line code.
    """
    # Code inside parentheses, with optional exchange suffix (/KS  .KS  .KQ etc.)
    m = re.search(
        r"\(\s*(\d{6})\s*(?:[./\-]\s*K[SQ])?\s*\)",
        text,
    )
    if m:
        return m.group(1)

    # Bare code at end of a line after a company-like name
    m = re.search(
        r"[가-힣A-Za-z][가-힣A-Za-z0-9 ·&]{1,18}\s+(\d{6})\s*$",
        text,
        re.MULTILINE,
    )
    if m:
        return m.group(1)

    # Layout 7 style: "082740 · 조선" — code at line start
    m = re.search(r"^\s*(\d{6})\s*[··•]\s*[가-힣]", text, re.MULTILINE)
    if m:
        return m.group(1)

    return None

# ---------------------------------------------------------------------------
# Rating patterns
# ---------------------------------------------------------------------------

_RATING_PATTERNS: List[str] = [
    # 투자의견 label followed by newline then rating
    r"투자의견\s*[\n:]\s*(강력매수|적극매수|매수|보유|중립|매도|BUY|Buy|HOLD|Hold|SELL|Sell|Outperform|Underperform|Overweight|Underweight)",
    # 투자의견 label inline
    r"투자의견[:\s]+(강력매수|적극매수|매수|보유|중립|매도|BUY|Buy|HOLD|Hold|SELL|Sell|Outperform|Underperform|Overweight|Underweight)",
    # "BUY (유지)" / "매수 (유지)" — rating as first token before parens
    r"^[ \t]*(강력매수|적극매수|매수|보유|중립|매도|BUY|HOLD|SELL|Buy|Hold|Sell)\s*[\(\（]",
    # plain keyword
    r"\b(강력매수|적극매수|매수|보유|중립|매도)\b",
    r"\b(BUY|HOLD|SELL)\b",
]

# ---------------------------------------------------------------------------
# Securities firm patterns  (Korean name preferred, email-domain fallback)
# ---------------------------------------------------------------------------

_FIRM_PATTERNS: List[str] = [
    r"([가-힣]{2,8}(?:증권|투자증권|금융투자|자산운용))",
]

# email domain → Korean firm name
_DOMAIN_FIRM_MAP = {
    "hana": "하나증권",
    "hanafn": "하나증권",
    "ibks": "IBK투자증권",
    "eugene": "유진투자증권",
    "eugenefn": "유진투자증권",
    "kyobo": "교보증권",
    "kiwoom": "키움증권",
    "shinhan": "신한투자증권",
    "kb": "KB증권",
    "mirae": "미래에셋증권",
    "samsung": "삼성증권",
    "nh": "NH투자증권",
    "sk": "SK증권",
    "daishin": "대신증권",
    "hi": "하이투자증권",
    "imeritz": "이베스트투자증권",
    "iprovest": "이베스트투자증권",
    "meritz": "메리츠증권",
    "hanwha": "한화투자증권",
    "hyundai": "현대차증권",
    "lotte": "롯데증권",
}

# ---------------------------------------------------------------------------
# Analyst patterns
# ---------------------------------------------------------------------------

_ANALYST_PATTERNS: List[str] = [
    r"Analyst\s+([가-힣]{2,4})",
    r"애널리스트[:\s]*([가-힣]{2,4})",
    r"분석가[:\s]*([가-힣]{2,4})",
    r"작성자[:\s]*([가-힣]{2,4})",
    r"([가-힣]{2,4})\s*(?:애널리스트|연구원|선임|수석|CFA)",
]

# ---------------------------------------------------------------------------
# Date patterns
# ---------------------------------------------------------------------------

_DATE_PATTERNS: List[str] = [
    r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})",
    r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일",
]

# ---------------------------------------------------------------------------
# Investment thesis section headers
# ---------------------------------------------------------------------------

_THESIS_HEADERS: List[str] = [
    r"투자\s*포인트[:\s\n]+([\s\S]{30,600}?)(?=\n\n|\Z)",
    r"투자\s*근거[:\s\n]+([\s\S]{30,600}?)(?=\n\n|\Z)",
    r"핵심\s*요약[:\s\n]+([\s\S]{30,600}?)(?=\n\n|\Z)",
    r"요\s*약[:\s\n]+([\s\S]{30,600}?)(?=\n\n|\Z)",
    r"Summary[:\s\n]+([\s\S]{30,600}?)(?=\n\n|\Z)",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_number(text: str) -> Optional[int]:
    cleaned = re.sub(r"[,\s원]", "", text)
    try:
        return int(cleaned)
    except (ValueError, TypeError):
        return None


def _first_match(text: str, patterns: List[str], group: int = 1,
                 flags: int = re.IGNORECASE | re.MULTILINE) -> Optional[str]:
    for pattern in patterns:
        m = re.search(pattern, text, flags)
        if m:
            try:
                val = m.group(group)
                if val:
                    return val.strip()
            except IndexError:
                pass
    return None


# ---------------------------------------------------------------------------
# Dedicated extractors for fields that need multi-line or special logic
# ---------------------------------------------------------------------------

def _extract_company(text: str) -> Optional[str]:
    """
    Regex-only fallback (used when code lookup fails).

    Layouts handled:
      1. "iM금융 (139130)"           name + code in parens on same line
      2. "삼성SDI (006400/KS)"       same, with exchange suffix in parens
      3. "삼성SDI 006400"            name + bare code, no parens
      4. "HD현대일렉트\\n릭\\n(267260)"  name word-wrapped before code-only line
      5/6. "(009830)\\n한화솔루션"    code-only line (± .KS suffix), name on next line
      7. "082740 · 조선\\n한화엔진"   code + separator + sector, company on next line
      8. "은행\\n기업은행 024110"     sector label line, company + code on next line
    """
    _CODE_IN_PARENS = r"\(\s*\d{6}(?:[/\-][A-Z]{1,3})?\s*\)"

    lines = text.split("\n")

    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue

        # Layouts 1 & 2: name immediately before "(NNNNNN)" or "(NNNNNN/KS)"
        m = re.search(
            r"([가-힣A-Za-z0-9][가-힣A-Za-z0-9 \t·&]{0,18}?)\s*" + _CODE_IN_PARENS,
            line,
        )
        if m:
            candidate = m.group(1).strip()
            if re.search(r"[가-힣]", candidate) or re.search(r"[A-Za-z]{2,}", candidate):
                return candidate

        # Layout 3: bare code at end of line, name before it (no parens)
        m = re.match(
            r"([가-힣A-Za-z][가-힣A-Za-z0-9 \t·]{0,18}?)\s+(\d{6})\s*$",
            line,
        )
        if m:
            candidate = m.group(1).strip()
            if re.search(r"[가-힣]", candidate) or re.search(r"[A-Za-z]{2,}", candidate):
                return candidate

        # Layout 4: this line is ONLY "(NNNNNN)" or "(NNNNNN/KS)" → name on preceding lines
        if re.fullmatch(r"\(\s*\d{6}(?:[/\-][A-Z]{1,3})?\s*\)", line):
            prev = [lines[j].strip() for j in range(max(0, i - 2), i) if lines[j].strip()]
            candidate = "".join(prev)
            if (
                candidate
                and len(candidate) <= 25
                and (re.search(r"[가-힣]", candidate) or re.search(r"[A-Za-z]{2,}", candidate))
                and not re.search(r"\d{4,}", candidate)
            ):
                return candidate

        # Layout 7: "082740 · 조선" on this line → company on next line
        if re.match(r"^\d{6}\s*[··•]\s*[가-힣A-Za-z0-9 ]{1,15}\s*$", line):
            if i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                if (nxt and len(nxt) <= 25
                        and (re.search(r"[가-힣]", nxt) or re.search(r"[A-Za-z]{2,}", nxt))
                        and not re.search(r"\d{4,}", nxt)):
                    return nxt

        # Layout 8: "은행" (sector label only) on this line → "기업은행 024110" on next line
        _SECTOR_LABEL_RE = re.compile(
            r"^(?:은행|보험|증권|건설|조선|제약|바이오|반도체|자동차|유통|통신"
            r"|에너지|철강|화학|식품|방산|게임|엔터|디스플레이|소프트웨어|미디어|항공)$"
        )
        if _SECTOR_LABEL_RE.match(line) and i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            m8 = re.match(r"([가-힣A-Za-z][가-힣A-Za-z0-9·& ]{0,20}?)\s+\d{6}\s*$", nxt)
            if m8:
                return m8.group(1).strip()

    # Layouts 5/6: "(009830)\nname"  or  "(028260. KS)\n삼성물산"
    m = re.search(
        r"\(\s*\d{6}(?:\s*[.\-/]\s*K[SQ])?\s*\)\s*\n\s*([가-힣A-Za-z0-9·& ]{2,25})",
        text,
    )
    if m:
        return m.group(1).strip().split("\n")[0].strip()

    return None


def _extract_price_after_label(text: str, label_pattern: str) -> Optional[int]:
    """
    Tries four layouts in order:

    Two-line with 원:   label[anything]\nprice원
    Same-line with 원:  label[gap]price원
    Three-line, 원?:   label[anything]\n[intermediate line]\nprice원?
                        e.g. "현재주가\n(26.04.28)\n1,238,000"
    Two-line, 원?:      label[anything]\nprice  (no 원, sidebar boxes)
                        e.g. "6개월 목표주가\n1,500,000\n상향"
    """
    # 1. Two-line with 원
    m = re.search(
        label_pattern + r"[^\n]{0,30}\n\s*([0-9,]{4,})\s*원",
        text, re.IGNORECASE | re.MULTILINE,
    )
    if m:
        return _parse_number(m.group(1))

    # 2. Same-line with 원
    m = re.search(
        label_pattern + r"[^\n\d]{0,10}([0-9,]{4,})\s*원",
        text, re.IGNORECASE,
    )
    if m:
        return _parse_number(m.group(1))

    # 3. Three-line (intermediate line between label and price, 원 optional)
    m = re.search(
        label_pattern + r"[^\n]{0,30}\n[^\n]{1,60}\n\s*([0-9,]{4,})\s*원?",
        text, re.IGNORECASE | re.MULTILINE,
    )
    if m:
        val = _parse_number(m.group(1))
        if val and val >= 1000:
            return val

    # 4. Two-line without 원 (sidebar-box format)
    m = re.search(
        label_pattern + r"[^\n]{0,30}\n\s*([0-9,]{5,})\s*\n",
        text, re.IGNORECASE | re.MULTILINE,
    )
    if m:
        val = _parse_number(m.group(1))
        if val and val >= 1000:
            return val

    return None


def _extract_target_price(text: str) -> Optional[int]:
    for label in (r"6개월\s*목표주가", r"목표\s*주가"):
        tp = _extract_price_after_label(text, label)
        if tp:
            return tp
    m = re.search(r"\bTP\s+([0-9,]{4,})\s*원?", text, re.IGNORECASE)
    if m:
        return _parse_number(m.group(1))
    return None


def _extract_current_price(text: str) -> Optional[int]:
    for label in (r"현재\s*(?:주가|가(?![가-힣]))", r"종가"):
        cp = _extract_price_after_label(text, label)
        if cp:
            return cp
    m = re.search(r"주가\s*\([0-9/]+\)\s*:\s*([0-9,]{4,})\s*원", text, re.IGNORECASE)
    if m:
        return _parse_number(m.group(1))
    return None


def _extract_securities_firm(text: str) -> Optional[str]:
    m = re.search(r"([가-힣]{2,8}(?:증권|투자증권|금융투자|자산운용))", text)
    if m:
        return m.group(1)
    m = re.search(r"@([\w]+)\.com", text, re.IGNORECASE)
    if m:
        domain = m.group(1).lower()
        if domain in _DOMAIN_FIRM_MAP:
            return _DOMAIN_FIRM_MAP[domain]
        for key in _DOMAIN_FIRM_MAP:
            if domain.startswith(key):
                return _DOMAIN_FIRM_MAP[key]
    return None


def _extract_date(text: str) -> Optional[str]:
    for pattern in _DATE_PATTERNS:
        m = re.search(pattern, text)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 2000 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31:
                return f"{y:04d}-{mo:02d}-{d:02d}"
    return None


def _extract_thesis(text: str) -> str:
    for pattern in _THESIS_HEADERS:
        m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            return re.sub(r"\s+", " ", raw)[:600]
    lines = [ln.strip() for ln in text.split("\n") if len(ln.strip()) > 30]
    return " ".join(lines[:6])[:400]


# ---------------------------------------------------------------------------
# Fix F: report_date fallback from filename
# ---------------------------------------------------------------------------

def _date_from_filename(filename: str) -> Optional[str]:
    """Return ISO date if filename starts with 8 digits (YYYYMMDD...)."""
    m = re.match(r"^(\d{4})(\d{2})(\d{2})", filename)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if 2000 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31:
        return f"{y:04d}-{mo:02d}-{d:02d}"
    return None


# ---------------------------------------------------------------------------
# Fix E: sentiment inference for UNKNOWN-rated reports
# ---------------------------------------------------------------------------

def _infer_sentiment(thesis: str) -> Optional[str]:
    """
    Return 'POSITIVE'/'NEGATIVE'/None based on keyword counts.
    Requires 3+ unique keyword hits for POSITIVE; 3+ for NEGATIVE.
    Winner-takes-all if both cross threshold; ties → None.
    """
    if not thesis:
        return None
    pos = sum(1 for kw in _POSITIVE_KW if kw in thesis)
    neg = sum(1 for kw in _NEGATIVE_KW if kw in thesis)
    if pos >= 3 and pos > neg:
        return "POSITIVE"
    if neg >= 3 and neg > pos:
        return "NEGATIVE"
    return None


# ---------------------------------------------------------------------------
# Public API  (swap this body for an LLM call; keep the return schema)
# ---------------------------------------------------------------------------

def extract_report_data(pdf_data: dict) -> dict:
    filename = pdf_data["filename"]

    # Fix A: scanned / image-only PDF (< 200 chars, no Korean)
    if pdf_data.get("scanned"):
        return {
            "filename": filename,
            "company": None,
            "rating_raw": None,
            "rating_normalized": "SCANNED",
            "target_price": None,
            "current_price": None,
            "securities_firm": None,
            "analyst": None,
            "date": _date_from_filename(filename),
            "thesis": "",
            "page_count": pdf_data["page_count"],
            "_scanned": True,
        }

    pages = pdf_data["pages"]
    full_text = pdf_data["full_text"]

    header = pages[0]["text"] if pages else ""
    if len(pages) > 1:
        header += "\n" + pages[1]["text"]

    thesis = _extract_thesis(full_text)

    # Fix G: company extraction priority
    #   1st) 6-digit code from header → stock_master lookup
    #   2nd) regex name extraction from header
    #   3rd) thesis-lead fallback: "CompanyName의 ..." (Fix H)
    code = _extract_code_from_header(header)
    company = lookup_company_by_code(code) if code else None
    if not company:
        company = _extract_company(header)
    company = _clean_company(company)
    if not company:
        lead = _extract_company_from_thesis(thesis)
        if lead:
            company = _clean_company(_reverse_lookup_name(lead) or lead)

    rating_raw = _first_match(header, _RATING_PATTERNS, group=1,
                               flags=re.IGNORECASE | re.MULTILINE)
    target_price = _extract_target_price(header)
    current_price = _extract_current_price(header)
    securities = _extract_securities_firm(header)
    analyst = _first_match(header, _ANALYST_PATTERNS, group=1)
    # Fix F: filename date wins; PDF-internal is fallback, discarded if year out of range
    fn_date = _date_from_filename(filename)
    pdf_date = _extract_date(header) or _extract_date(full_text)
    if pdf_date:
        y = int(pdf_date[:4])
        if y < 2020 or y > 2027:
            pdf_date = None
    date = fn_date or pdf_date

    return {
        "filename": filename,
        "company": company,
        "rating_raw": rating_raw,
        "target_price": target_price,
        "current_price": current_price,
        "securities_firm": securities,
        "analyst": analyst,
        "date": date,
        "thesis": thesis,
        "page_count": pdf_data["page_count"],
    }
