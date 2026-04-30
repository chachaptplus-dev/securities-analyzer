"""Canonical sector inference from thesis text and company name."""
from __future__ import annotations

import re
from typing import Optional

# ── Authoritative company → sector mapping (~150 Korean stocks) ───────────────
# Keys are canonical company names; matching also handles space variants and
# dirty prefixes like "Issue Comment비에이치" via partial matching.
COMPANY_SECTOR: dict[str, str] = {
    # ── Semiconductors ────────────────────────────────────────────────────────
    "삼성전자":         "Semiconductors",
    "SK하이닉스":       "Semiconductors",
    "DB하이텍":         "Semiconductors",
    "원익IPS":          "Semiconductors",
    "솔브레인":         "Semiconductors",
    "리노공업":         "Semiconductors",
    "ISC":              "Semiconductors",
    "피에스케이":       "Semiconductors",
    "피에스케이홀딩스": "Semiconductors",
    "테스":             "Semiconductors",
    "유니셈":           "Semiconductors",
    "에스앤에스텍":     "Semiconductors",
    "엘티씨":           "Semiconductors",
    "넥스틴":           "Semiconductors",
    "에이디테크놀로지": "Semiconductors",
    "티에스아이":       "Semiconductors",
    "티엘비":           "Semiconductors",
    "심텍":             "Semiconductors",
    "덕산테코피아":     "Semiconductors",
    "RF머트리얼즈":     "Semiconductors",
    "고영":             "Semiconductors",
    "오이솔루션":       "Semiconductors",
    "노바텍":           "Semiconductors",
    "한화비전":         "Semiconductors",
    "지앤비에스 에코":  "Semiconductors",
    "비나텍":           "Semiconductors",
    "디케이티":         "Semiconductors",
    # ── Battery / EV ─────────────────────────────────────────────────────────
    "삼성SDI":          "Battery / EV",
    "LG에너지솔루션":   "Battery / EV",
    "SK이노베이션":     "Battery / EV",
    "에코프로비엠":     "Battery / EV",
    "에코프로":         "Battery / EV",
    "포스코퓨처엠":     "Battery / EV",
    "엘앤에프":         "Battery / EV",
    "코스모신소재":     "Battery / EV",
    "솔루스첨단소재":   "Battery / EV",
    "천보":             "Battery / EV",
    "성일하이텍":       "Battery / EV",
    "더블유씨피":       "Battery / EV",
    # ── Automotive ───────────────────────────────────────────────────────────
    "현대차":           "Automotive",
    "기아":             "Automotive",
    "현대모비스":       "Automotive",
    "현대위아":         "Automotive",
    "현대트랜시스":     "Automotive",
    "HL만도":           "Automotive",
    "금호타이어":       "Automotive",
    "DN오토모티브":     "Automotive",
    "에스엘":           "Automotive",
    "한국타이어앤테크놀로지": "Automotive",
    "넥센타이어":       "Automotive",
    "성우하이텍":       "Automotive",
    # ── Healthcare / Bio ─────────────────────────────────────────────────────
    "삼성바이오로직스": "Healthcare / Bio",
    "셀트리온":         "Healthcare / Bio",
    "셀트리온헬스케어": "Healthcare / Bio",
    "한미약품":         "Healthcare / Bio",
    "유한양행":         "Healthcare / Bio",
    "종근당":           "Healthcare / Bio",
    "대웅제약":         "Healthcare / Bio",
    "동아에스티":       "Healthcare / Bio",
    "동아쏘시오홀딩스": "Healthcare / Bio",
    "HK이노엔":         "Healthcare / Bio",
    "휴젤":             "Healthcare / Bio",
    "덴티움":           "Healthcare / Bio",
    "클래시스":         "Healthcare / Bio",
    "파마리서치":       "Healthcare / Bio",
    "에이비엘바이오":   "Healthcare / Bio",
    "한올바이오파마":   "Healthcare / Bio",
    "에스티팜":         "Healthcare / Bio",
    "레고켐바이오":     "Healthcare / Bio",
    "오스코텍":         "Healthcare / Bio",
    "SK바이오팜":       "Healthcare / Bio",
    "알지노믹스":       "Healthcare / Bio",
    "디오":             "Healthcare / Bio",
    "파미셀":           "Healthcare / Bio",
    # ── Financials ───────────────────────────────────────────────────────────
    "KB금융":           "Financials",
    "신한지주":         "Financials",
    "하나금융지주":     "Financials",
    "우리금융지주":     "Financials",
    "우리금융":         "Financials",
    "NH투자증권":       "Financials",
    "미래에셋증권":     "Financials",
    "삼성증권":         "Financials",
    "키움증권":         "Financials",
    "한국금융지주":     "Financials",
    "메리츠금융지주":   "Financials",
    "iM금융지주":       "Financials",
    "JB금융지주":       "Financials",
    "기업은행":         "Financials",
    "삼성생명":         "Financials",
    "삼성화재":         "Financials",
    "현대해상":         "Financials",
    "DB손해보험":       "Financials",
    "한화생명":         "Financials",
    "카카오뱅크":       "Financials",
    "케이뱅크":         "Financials",
    # ── IT / Platform ────────────────────────────────────────────────────────
    "카카오":           "IT / Platform",
    "NAVER":            "IT / Platform",
    "네이버":           "IT / Platform",
    "카카오페이":       "IT / Platform",
    "엔비티":           "IT / Platform",
    # ── IT / Software ────────────────────────────────────────────────────────
    "삼성에스디에스":   "IT / Software",
    "SK스퀘어":         "IT / Software",
    "더존비즈온":       "IT / Software",
    "쿠콘":             "IT / Software",
    "아이씨티케이":     "IT / Software",
    "ICTK":             "IT / Software",
    # ── Telecom ──────────────────────────────────────────────────────────────
    "SK텔레콤":         "Telecom",
    "KT":               "Telecom",
    "LG유플러스":       "Telecom",
    "우리넷":           "Telecom",
    "AP위성":           "Telecom",
    "KMW":              "Telecom",
    "쏠리드":           "Telecom",
    "유비쿼스":         "Telecom",
    # ── Electronics ──────────────────────────────────────────────────────────
    "LG전자":           "Electronics",
    "LG이노텍":         "Electronics",
    "삼성전기":         "Electronics",
    "파트론":           "Electronics",
    "비에이치":         "Electronics",
    "대덕전자":         "Electronics",
    "소룩스":           "Electronics",
    # ── Industrial Equipment ─────────────────────────────────────────────────
    "LS ELECTRIC":      "Industrial Equipment",
    "HD현대일렉트릭":   "Industrial Equipment",
    "효성중공업":       "Industrial Equipment",
    "산일전기":         "Industrial Equipment",
    "일진전기":         "Industrial Equipment",
    "제룡전기":         "Industrial Equipment",
    "대한전선":         "Industrial Equipment",
    # ── Display ──────────────────────────────────────────────────────────────
    "LG디스플레이":     "Display",
    "덕산네오룩스":     "Display",
    # ── Shipbuilding ─────────────────────────────────────────────────────────
    "HD현대중공업":     "Shipbuilding",
    "한화오션":         "Shipbuilding",
    "삼성중공업":       "Shipbuilding",
    "HD한국조선해양":   "Shipbuilding",
    "현대미포조선":     "Shipbuilding",
    "HJ중공업":         "Shipbuilding",
    "한화엔진":         "Shipbuilding",
    "HD현대마린솔루션": "Shipbuilding",
    # ── Defense ──────────────────────────────────────────────────────────────
    "한화에어로스페이스": "Defense",
    "한화시스템":       "Defense",
    "현대로템":         "Defense",
    "한국항공우주":     "Defense",
    "LIG넥스원":        "Defense",
    "RFHIC":            "Defense",
    "풍산":             "Defense",
    # ── Steel / Metals ───────────────────────────────────────────────────────
    "POSCO홀딩스":      "Steel / Metals",
    "포스코홀딩스":     "Steel / Metals",
    "현대제철":         "Steel / Metals",
    "동국제강":         "Steel / Metals",
    "세아제강":         "Steel / Metals",
    "세아베스틸지주":   "Steel / Metals",
    "세아베스틸":       "Steel / Metals",
    "태웅":             "Steel / Metals",
    "성광벤드":         "Steel / Metals",
    "동국홀딩스":       "Steel / Metals",
    # ── Construction ─────────────────────────────────────────────────────────
    "현대건설":         "Construction",
    "GS건설":           "Construction",
    "대우건설":         "Construction",
    "DL이앤씨":         "Construction",
    "삼성E&A":          "Construction",
    "IPARK현대산업개발":"Construction",
    "HDC현대산업개발":  "Construction",
    "자이에스앤디":     "Construction",
    "한미글로벌":       "Construction",
    "HDC":              "Construction",
    "HD건설기계":       "Construction",
    "SGC에너지":        "Construction",
    # ── Chemicals ────────────────────────────────────────────────────────────
    "LG화학":           "Chemicals",
    "롯데케미칼":       "Chemicals",
    "금호석유":         "Chemicals",
    # ── Renewables ───────────────────────────────────────────────────────────
    "한화솔루션":       "Renewables",
    "OCI홀딩스":        "Renewables",
    "LS에코에너지":     "Renewables",
    # ── Energy / Utilities ───────────────────────────────────────────────────
    "한국전력":         "Utilities",
    "한국가스공사":     "Utilities",
    "서부T&D":          "Utilities",
    "GS피앤엘":         "Energy",
    "포스코인터내셔널": "Energy",
    "SK가스":           "Energy",
    # ── Heavy Industry / Machinery ───────────────────────────────────────────
    "두산에너빌리티":   "Heavy Industry",
    "두산밥캣":         "Heavy Industry",
    "두산":             "Heavy Industry",
    "HD현대":           "Heavy Industry",
    # ── Retail ───────────────────────────────────────────────────────────────
    "이마트":           "Retail",
    "신세계":           "Retail",
    "GS리테일":         "Retail",
    "BGF리테일":        "Retail",
    "롯데하이마트":     "Retail",
    "케이카":           "Retail",
    "한샘":             "Retail",
    "현대백화점":       "Retail",
    "한국가구":         "Retail",
    # ── Food / Consumer ──────────────────────────────────────────────────────
    "농심":             "Food / Consumer",
    "오리온":           "Food / Consumer",
    "빙그레":           "Food / Consumer",
    "CJ제일제당":       "Food / Consumer",
    "CJ프레시웨이":     "Food / Consumer",
    "하이트진로":       "Food / Consumer",
    "삼양식품":         "Food / Consumer",
    # ── Beauty / Cosmetics ───────────────────────────────────────────────────
    "아모레퍼시픽":     "Beauty / Cosmetics",
    "LG생활건강":       "Beauty / Cosmetics",
    "코스맥스":         "Beauty / Cosmetics",
    "한국콜마":         "Beauty / Cosmetics",
    "에이피알":         "Beauty / Cosmetics",
    "실리콘투":         "Beauty / Cosmetics",
    # ── Fashion / Apparel ────────────────────────────────────────────────────
    "한섬":             "Fashion / Apparel",
    "신세계인터내셔날": "Fashion / Apparel",
    "감성코퍼레이션":   "Fashion / Apparel",
    "한세실업":         "Fashion / Apparel",
    "에이유브랜즈":     "Fashion / Apparel",
    # ── Entertainment ────────────────────────────────────────────────────────
    "하이브":           "Entertainment",
    "에스엠":           "Entertainment",
    "와이지엔터테인먼트": "Entertainment",
    "JYP Ent":          "Entertainment",
    "스튜디오드래곤":   "Entertainment",
    "CJ ENM":           "Entertainment",
    # ── Gaming ───────────────────────────────────────────────────────────────
    "엔씨소프트":       "Gaming",
    "크래프톤":         "Gaming",
    "펄어비스":         "Gaming",
    "더블유게임즈":     "Gaming",
    "넥슨게임즈":       "Gaming",
    "카카오게임즈":     "Gaming",
    # ── Media / Advertising ──────────────────────────────────────────────────
    "제일기획":         "Media / Advertising",
    # ── Hotels / Leisure ─────────────────────────────────────────────────────
    "호텔신라":         "Hotels / Leisure",
    "강원랜드":         "Hotels / Leisure",
    # ── Airlines ─────────────────────────────────────────────────────────────
    "대한항공":         "Airlines",
    "아시아나항공":     "Airlines",
    "제주항공":         "Airlines",
    "에어부산":         "Airlines",
    # ── Shipping ─────────────────────────────────────────────────────────────
    "HMM":              "Shipping",
    "팬오션":           "Shipping",
}

# ── Keyword → sector fallback (thesis + company name text scan) ───────────────
# Priority-ordered: specific terms before generic ones.
SECTOR_MAP: list[tuple[str, str]] = [
    # Sector keywords
    ("반도체",      "Semiconductors"),
    ("메모리",      "Semiconductors"),
    ("파운드리",    "Semiconductors"),
    ("hbm",         "Semiconductors"),
    ("낸드",        "Semiconductors"),
    ("dram",        "Semiconductors"),
    ("배터리",      "Battery / EV"),
    ("전기차",      "Battery / EV"),
    ("2차전지",     "Battery / EV"),
    ("양극재",      "Battery / EV"),
    ("음극재",      "Battery / EV"),
    ("바이오",      "Healthcare / Bio"),
    ("제약",        "Healthcare / Bio"),
    ("임상",        "Healthcare / Bio"),
    ("신약",        "Healthcare / Bio"),
    ("의약품",      "Healthcare / Bio"),
    ("은행",        "Financials"),
    ("금융투자",    "Financials"),
    ("보험",        "Financials"),
    ("증권",        "Financials"),
    ("조선",        "Shipbuilding"),
    ("선박",        "Shipbuilding"),
    ("방산",        "Defense"),
    ("무기체계",    "Defense"),
    ("인공지능",    "AI / Data"),
    ("클라우드",    "AI / Data"),
    ("데이터센터",  "AI / Data"),
    ("소프트웨어",  "IT / Software"),
    ("플랫폼",      "IT / Platform"),
    ("이커머스",    "IT / Platform"),
    ("인터넷",      "IT / Platform"),
    ("엔터테인먼트","Entertainment"),
    ("게임",        "Gaming"),
    ("항공",        "Airlines"),
    ("카지노",      "Hotels / Leisure"),
    ("리조트",      "Hotels / Leisure"),
    ("석유화학",    "Chemicals"),     # before "화학"
    ("화학",        "Chemicals"),
    ("정유",        "Energy / Chemicals"),
    ("철강",        "Steel / Metals"),
    ("알루미늄",    "Steel / Metals"),
    ("건설",        "Construction"),
    ("자동차",      "Automotive"),
    ("전기전자",    "Electronics"),   # before "전자"
    ("전자",        "Electronics"),
    ("디스플레이",  "Display"),
    ("oled",        "Display"),
    ("통신",        "Telecom"),
    ("유통",        "Retail"),
    ("식품",        "Food / Consumer"),
    ("금융",        "Financials"),    # broad fallback
    ("태양광",      "Renewables"),
    ("수소",        "Renewables"),
    ("에너지",      "Energy"),
]

_STRIP_RE = re.compile(r'[\s\-·.★☆♦◆●▶①②③]')


def _norm(s: str) -> str:
    return _STRIP_RE.sub("", s).lower()


def infer_sector(thesis: str, company: str = "") -> Optional[str]:
    """
    Return the first matching English sector label, or None.

    Priority:
      1. Exact company-map lookup (after normalization)
      2. Partial company-map lookup (map key contained in company name, key ≥ 3 chars)
      3. Keyword scan of company name + thesis text
    """
    company_norm = _norm(company)

    # 1. Exact match
    for key, sector in COMPANY_SECTOR.items():
        if _norm(key) == company_norm:
            return sector

    # 2. Partial match — handles "Issue Comment비에이치", space variants, etc.
    for key, sector in COMPANY_SECTOR.items():
        key_n = _norm(key)
        if len(key_n) >= 3 and key_n in company_norm:
            return sector

    # 3. Keyword scan on combined text
    text = f"{company} {thesis}".lower()
    for kw, sector in SECTOR_MAP:
        if kw.lower() in text:
            return sector

    return None
