"""
TF-IDF + KMeans thesis clustering.
Run standalone: py -3 src/clustering.py [n_clusters]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

# ── Keyword → theme name (sector terms first, then investment thesis patterns) ──
# Checked in order; first match wins. Add sector terms before generic patterns.
_THEME_MAP: list[tuple[str, str]] = [
    # ── Sector themes ──────────────────────────────────────────────────────────
    ("반도체",    "Semiconductors"),
    ("메모리",    "Semiconductors"),
    ("파운드리",  "Semiconductors"),
    ("hbm",       "Semiconductors"),
    ("낸드",      "Semiconductors"),
    ("dram",      "Semiconductors"),
    ("배터리",    "Battery / EV"),
    ("전기차",    "Battery / EV"),
    ("2차전지",   "Battery / EV"),
    ("양극재",    "Battery / EV"),
    ("음극재",    "Battery / EV"),
    ("바이오",    "Healthcare / Bio"),
    ("제약",      "Healthcare / Bio"),
    ("임상",      "Healthcare / Bio"),
    ("신약",      "Healthcare / Bio"),
    ("의약품",    "Healthcare / Bio"),
    ("은행",      "Financials"),
    ("금융투자",  "Financials"),
    ("보험",      "Financials"),
    ("대출",      "Financials"),
    ("appendix",  "Financials"),        # disclosure-heavy broker template
    ("조선",      "Shipbuilding"),
    ("선박",      "Shipbuilding"),
    ("방산",      "Defense"),
    ("무기체계",  "Defense"),
    ("인공지능",  "AI / Data"),
    ("클라우드",  "AI / Data"),
    ("데이터센터","AI / Data"),
    ("소프트웨어","IT / Software"),
    ("플랫폼",    "IT / Platform"),
    ("이커머스",  "IT / Platform"),
    ("화학",      "Chemicals"),
    ("석유화학",  "Chemicals"),
    ("정유",      "Energy / Chemicals"),
    ("철강",      "Steel / Metals"),
    ("알루미늄",  "Steel / Metals"),
    ("건설",      "Construction"),
    ("자동차",    "Automotive"),
    ("전기전자",  "Electronics"),
    ("전자",      "Electronics"),
    ("디스플레이","Display"),
    ("oled",      "Display"),
    ("통신",      "Telecom"),
    ("유통",      "Retail"),
    ("식품",      "Food / Consumer"),
    ("태양광",    "Renewables"),
    ("수소",      "Renewables"),
    ("에너지",    "Energy"),
    # ── Investment thesis / report-type patterns ───────────────────────────────
    ("컨센서스",  "Consensus Beat"),
    ("상회",      "Consensus Beat"),
    ("어닝",      "Earnings Surprise"),
    ("목표주가",  "Target Price Revision"),
    ("적용",      "Target Price Revision"),    # valuation multiple applied
    ("각각",      "Earnings Preview"),         # side-by-side multi-co results table
    ("배당",      "Dividend / Income"),
    ("yield",     "Dividend / Income"),
    ("margin",    "Dividend / Income"),
    ("자사주",    "Buyback / Returns"),
    ("턴어라운드","Turnaround"),
    ("흑자전환",  "Turnaround"),
    ("신규",      "New Coverage"),
    ("인수",      "M&A"),
    ("합병",      "M&A"),
    ("재무분석",  "Technical / Quant"),
    ("시장동향",  "Technical / Quant"),
    ("기술분석",  "Technical / Quant"),
    ("추천",      "Buy Recommendation"),
    ("report",    "Buy Recommendation"),
    ("수요",      "Demand Outlook"),
    ("핵심",      "Core Business Overview"),
    ("사업으로",  "Core Business Overview"),
    ("지주",      "Holding Co. / Small Cap"),
    ("small",     "Holding Co. / Small Cap"),
    ("당사는",    "Disclaimer / Research Note"),
    ("없습니다",  "Disclaimer / Research Note"),
]

# Sector label for the Sector column (sector terms only)
_SECTOR_MAP: list[tuple[str, str]] = [
    ("반도체",    "Semiconductors"),
    ("메모리",    "Semiconductors"),
    ("파운드리",  "Semiconductors"),
    ("hbm",       "Semiconductors"),
    ("낸드",      "Semiconductors"),
    ("dram",      "Semiconductors"),
    ("배터리",    "Battery / EV"),
    ("전기차",    "Battery / EV"),
    ("2차전지",   "Battery / EV"),
    ("양극재",    "Battery / EV"),
    ("음극재",    "Battery / EV"),
    ("바이오",    "Healthcare / Bio"),
    ("제약",      "Healthcare / Bio"),
    ("임상",      "Healthcare / Bio"),
    ("신약",      "Healthcare / Bio"),
    ("의약품",    "Healthcare / Bio"),
    ("은행",      "Financials"),
    ("금융",      "Financials"),
    ("금융투자",  "Financials"),
    ("보험",      "Financials"),
    ("appendix",  "Financials"),
    ("조선",      "Shipbuilding"),
    ("선박",      "Shipbuilding"),
    ("방산",      "Defense"),
    ("인공지능",  "AI / Data"),
    ("클라우드",  "AI / Data"),
    ("데이터센터","AI / Data"),
    ("소프트웨어","IT / Software"),
    ("플랫폼",    "IT / Platform"),
    ("화학",      "Chemicals"),
    ("석유화학",  "Chemicals"),
    ("정유",      "Energy / Chemicals"),
    ("철강",      "Steel / Metals"),
    ("건설",      "Construction"),
    ("자동차",    "Automotive"),
    ("전기전자",  "Electronics"),
    ("전자",      "Electronics"),
    ("디스플레이","Display"),
    ("oled",      "Display"),
    ("통신",      "Telecom"),
    ("유통",      "Retail"),
    ("식품",      "Food / Consumer"),
    ("태양광",    "Renewables"),
    ("수소",      "Renewables"),
    ("에너지",    "Energy"),
]

# ── Stopwords: universal terms that appear in nearly all reports ───────────────
# These dominate TF-IDF centroids and prevent sector differentiation.
_STOPS: frozenset[str] = frozenset({
    # Korean function words / particles
    "및", "등", "것으로", "이를", "통해", "대해", "위해", "있으며",
    "있다", "한다", "된다", "되며", "이며", "하며", "하여", "하는",
    "한편", "또한", "다만", "이후", "향후", "전년", "동기",
    "기준", "수준", "비율", "것이", "있을", "있는", "보인다",
    "판단된다", "전망된다", "예상된다", "것을", "있어", "이에",
    "따라", "따른", "위한", "대한", "중인", "중에", "이상",
    "이하", "이전", "이후", "최근", "현재", "향후", "올해",
    # Universal financial metrics (present in ALL reports — zero discriminatory value)
    "영업이익", "매출액", "순이익", "매출", "이익", "실적", "손익",
    "영업", "흑자", "적자", "증가", "감소", "개선", "악화",
    "분기", "연간", "상반기", "하반기",
    "목표주가", "투자의견", "매수", "주가", "상향", "하향", "유지",
    "예상", "전망", "추정", "판단", "주요",
    "기업", "회사", "부문", "사업부", "연결", "별도", "사업",
    "성장", "확대", "증가", "감소", "상승", "하락", "회복",
    # Common Latin abbreviations in all reports
    "yoy", "qoq", "eps", "ebitda", "per", "pbr", "roe", "roa",
    "cagr", "ipo", "spac", "nav", "nar", "ebit", "opex", "capex",
    "price", "rel",
})

# Strip emails, URLs, phone numbers, and pure-numeric tokens before vectorizing
_NOISE_RE = re.compile(
    r"\S+@\S+"            # emails
    r"|\bhttps?://\S+"    # URLs
    r"|\b\d[\d\-\.\(\) ]{3,}\d\b"  # phone numbers / date strings
    r"|\b\d+\b",          # standalone numbers
    re.IGNORECASE,
)


def _preprocess(text: str) -> str:
    text = _NOISE_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _match_theme(terms: list[str]) -> str:
    joined = " ".join(terms).lower()
    for kw, name in _THEME_MAP:
        if kw in joined:
            return name
    return ""


def _match_sector(terms: list[str]) -> str:
    joined = " ".join(terms).lower()
    for kw, sector in _SECTOR_MAP:
        if kw in joined:
            return sector
    return "Mixed"


def cluster_theses(
    theses: list[str],
    n_clusters: int = 12,
    top_terms: int = 10,
) -> tuple[list[int], list[str], dict[int, list[str]]]:
    """
    Parameters
    ----------
    theses      : one text string per report
    n_clusters  : target cluster count (10-15 recommended)
    top_terms   : keywords to extract per cluster

    Returns
    -------
    labels          : cluster index per thesis (same length as `theses`)
    cluster_names   : auto-generated English theme label per cluster
    cluster_terms   : {cluster_id: [top keyword, ...]}
    """
    clean = [_preprocess(t) if t else "" for t in theses]
    valid_idx = [i for i, t in enumerate(clean) if t and len(t) >= 20]
    valid = [clean[i] for i in valid_idx]

    if len(valid) < 2:
        return [0] * len(theses), ["Cluster 1: (insufficient data)"], {0: []}

    n_clusters = min(n_clusters, len(valid))

    vectorizer = TfidfVectorizer(
        max_features=2000,
        min_df=3,
        max_df=0.2,   # drop terms in >20% of docs (financial boilerplate + inflected forms)
        ngram_range=(1, 2),
        sublinear_tf=True,
        # 2+ char Korean words OR 4+ char Latin words only
        token_pattern=r"(?u)\b[가-힣]{2,}\b|\b[a-zA-Z]{4,}\b",
        stop_words=list(_STOPS),
    )
    X = vectorizer.fit_transform(valid)
    X_norm = normalize(X)

    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    valid_labels = km.fit_predict(X_norm).tolist()

    feature_names = vectorizer.get_feature_names_out()
    cluster_terms: dict[int, list[str]] = {}
    cluster_names: list[str] = []
    seen_names: dict[str, int] = {}

    for cid in range(n_clusters):
        top_idx = km.cluster_centers_[cid].argsort()[-top_terms:][::-1]
        terms = [feature_names[i] for i in top_idx]
        cluster_terms[cid] = terms

        # Match against top-5 terms only so the label always aligns with visible keywords
        theme = _match_theme(terms[:5])
        if not theme:
            theme = "Theme {}: {}".format(cid + 1, " · ".join(terms[:3]))
        count = seen_names.get(theme, 0) + 1
        seen_names[theme] = count
        name = theme if count == 1 else f"{theme} ({count})"
        cluster_names.append(name)

    label_map = dict(zip(valid_idx, valid_labels))
    labels = [label_map.get(i, 0) for i in range(len(theses))]

    return labels, cluster_names, cluster_terms


def run_clustering(n_clusters: int = 12) -> pd.DataFrame:
    """Read DB, cluster by thesis text, return summary DataFrame."""
    from src.database import get_all_reports
    from src.sector import infer_sector as _infer_sector_db

    df = get_all_reports()
    if df.empty:
        print("No reports in database.")
        return pd.DataFrame()

    print(f"Loaded {len(df)} reports. Running TF-IDF + KMeans (k={n_clusters})...")

    texts = df["thesis"].fillna("").tolist()
    labels, cluster_names, cluster_terms = cluster_theses(texts, n_clusters=n_clusters)

    df = df.copy()
    df["_cluster"] = labels

    rows = []
    for cid in range(n_clusters):
        subset = df[df["_cluster"] == cid]
        terms = cluster_terms.get(cid, [])
        avg_up = subset["upside"].dropna()
        rows.append({
            "Theme":        cluster_names[cid],
            "Top Keywords": " · ".join(terms[:6]),
            "Stocks":       int(subset["company"].nunique()),
            "Sector":       subset["sector"].dropna().mode().iloc[0] if not subset["sector"].dropna().empty else _match_sector(terms),
            "Avg Upside %": round(float(avg_up.mean()), 1) if len(avg_up) else None,
            "Reports":      len(subset),
        })

    return (
        pd.DataFrame(rows)
        .sort_values("Reports", ascending=False)
        .reset_index(drop=True)
    )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12

    summary = run_clustering(n_clusters=n)
    if summary.empty:
        sys.exit(1)

    pd.set_option("display.max_colwidth", 55)
    pd.set_option("display.width", 145)
    pd.set_option("display.max_rows", 20)

    bar = "─" * 135
    print(f"\n{bar}")
    print(f"  INVESTMENT THESIS CLUSTERS  (k={n})")
    print(bar)
    print(summary.to_string(index=True))
    print(bar)
    print(f"  Total reports: {summary['Reports'].sum()}  |  "
          f"Total stocks: {summary['Stocks'].sum()}  |  "
          f"Overall avg upside: "
          f"{round(summary['Avg Upside %'].dropna().mean(), 1)}%")
    print(bar)
