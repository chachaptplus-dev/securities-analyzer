"""
Macro theme keyword matching for Korean securities reports.
Keyword-only engine — no LLM calls.
Return schema of explain_buy_reason() is stable for future LLM swap.
"""
from __future__ import annotations

from typing import Optional

# ---------------------------------------------------------------------------
# Theme definitions
# ---------------------------------------------------------------------------

MACRO_THEMES: dict[str, dict] = {
    "AI·반도체": {
        "keywords": [
            "AI", "인공지능", "HBM", "데이터센터", "GPU", "엔비디아", "NPU",
            "파운드리", "온디바이스", "DRAM", "CoWoS", "가속기",
        ],
        "sectors": ["Semiconductors", "IT Hardware", "AI / Data"],
        "description": "AI 인프라 수요 및 반도체 업사이클",
    },
    "전력·인프라": {
        "keywords": [
            "전력망", "송전", "변압기", "전력 수요", "데이터센터 전력",
            "HVDC", "원전", "SMR", "초고압", "전력기기", "그리드",
        ],
        "sectors": ["Utilities", "Industrial Equipment"],
        "description": "AI 전력 수요 및 에너지 인프라 투자",
    },
    "로봇·자동화": {
        "keywords": [
            "로봇", "휴머노이드", "협동로봇", "스마트팩토리", "자동화",
            "무인화", "공장자동화", "AMR", "액추에이터",
        ],
        "sectors": ["Industrial Equipment", "Machinery"],
        "description": "제조 자동화 및 휴머노이드 로봇 도입",
    },
    "배터리·전기차": {
        "keywords": [
            "배터리", "전기차", "EV", "2차전지", "리튬", "양극재",
            "음극재", "ESS", "전고체", "LFP", "NCM", "전해질",
        ],
        "sectors": ["Batteries / EV", "Automotive", "Chemicals"],
        "description": "전기차 보급 및 에너지 저장 시스템 성장",
    },
    "바이오·헬스케어": {
        "keywords": [
            "바이오", "신약", "임상", "FDA", "ADC", "CDMO",
            "의료기기", "항체", "파이프라인", "허가", "GLP-1",
        ],
        "sectors": ["Healthcare / Bio", "Pharmaceuticals"],
        "description": "신약 개발 모멘텀 및 바이오 위탁생산 성장",
    },
    "방산·우주": {
        "keywords": [
            "방산", "국방", "K방산", "드론", "위성", "지정학",
            "NATO", "수출 방산", "유럽 재무장", "미사일", "군비",
            "방산 수주", "무기 수출", "수출 계약",
        ],
        "sectors": ["Defense"],
        "description": "글로벌 지정학 긴장 및 K-방산 수출 확대",
    },
    "조선·해운": {
        "keywords": [
            "조선", "LNG선", "컨테이너선", "운임", "선박 수주",
            "친환경 선박", "암모니아", "VLCC", "슈퍼사이클", "수주잔고",
        ],
        "sectors": ["Shipbuilding"],
        "description": "친환경 선박 교체 수요 및 LNG선 수주 확대",
    },
    "금리·금융": {
        "keywords": [
            "금리 인하", "기준금리", "연준", "Fed", "피벗",
            "유동성", "NIM", "금리", "통화정책", "FOMC",
        ],
        "sectors": ["Banking / Insurance", "Financials"],
        "description": "금리 사이클 전환에 따른 금융주 리레이팅",
    },
    "수출·환율": {
        "keywords": [
            "수출 증가", "달러 강세", "원달러", "환율", "미국향",
            "글로벌 수요", "수출 호조", "달러", "위안화",
        ],
        "sectors": ["Electronics", "Semiconductors", "Automotive"],
        "description": "원화 약세·달러 강세에 따른 수출 기업 수혜",
    },
    "소비·내수": {
        "keywords": [
            "소비 회복", "내수", "민간소비", "소비심리", "리오프닝",
            "명품", "소비", "여행", "레저", "외식",
        ],
        "sectors": ["Retail", "Food / Consumer", "Hotels / Leisure"],
        "description": "내수 소비 회복 및 리오프닝 수혜",
    },
    "중국·신흥국": {
        "keywords": [
            "중국 리오프닝", "중국 수요", "중국 부양", "인도",
            "신흥국", "중국", "인도네시아", "베트남", "수출 확대",
        ],
        "sectors": ["Beauty / Cosmetics", "Chemicals", "Automotive"],
        "description": "중국·신흥국 수요 회복 및 소비 확대",
    },
}

# Badge colours per theme (used by dashboard)
THEME_COLORS: dict[str, str] = {
    "AI·반도체":    "#1565C0",
    "전력·인프라":  "#E65100",
    "로봇·자동화":  "#6A1B9A",
    "배터리·전기차":"#2E7D32",
    "바이오·헬스케어":"#C62828",
    "방산·우주":    "#37474F",
    "조선·해운":    "#00695C",
    "금리·금융":    "#4E342E",
    "수출·환율":    "#00838F",
    "소비·내수":    "#AD1457",
    "중국·신흥국":  "#F57F17",
}

_DEFAULT_BADGE_COLOR = "#455A64"

REGIME_THEME_MAP: dict[str, dict] = {
    "위험선호 (Risk-On)": {
        "strong": ["AI·반도체", "배터리·전기차", "바이오·헬스케어", "로봇·자동화"],
        "weak":   ["금리·금융", "소비·내수"],
    },
    "위험회피 (Risk-Off)": {
        "strong": ["금리·금융", "방산·우주"],
        "weak":   ["AI·반도체", "배터리·전기차"],
    },
    "수출주 강세": {
        "strong": ["수출·환율", "조선·해운", "AI·반도체"],
        "weak":   ["소비·내수", "중국·신흥국"],
    },
    "경기회복": {
        "strong": ["조선·해운", "전력·인프라", "로봇·자동화"],
        "weak":   ["금리·금융"],
    },
    "스태그플레이션 우려": {
        "strong": ["방산·우주", "전력·인프라"],
        "weak":   ["소비·내수", "배터리·전기차"],
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_theme_trend(df: "pd.DataFrame") -> "pd.DataFrame":
    """
    Weekly theme report counts.
    Returns a wide DataFrame: index = week-start Monday, columns = theme names, values = count.
    Rows/columns with all-zero are dropped.
    """
    import pandas as pd

    work = df[df["thesis"].notna() & df["report_date"].notna()].copy()
    if work.empty:
        return pd.DataFrame()

    work["report_date"] = pd.to_datetime(work["report_date"], errors="coerce")
    ceiling = pd.Timestamp.now() + pd.Timedelta(days=30)
    work = work[work["report_date"] <= ceiling]
    if work.empty:
        return pd.DataFrame()

    work["week"] = work["report_date"].dt.to_period("W").dt.start_time

    rows = []
    for _, row in work.iterrows():
        themes = extract_macro_themes(row["thesis"])
        for t in themes:
            rows.append({"week": row["week"], "theme": t})

    if not rows:
        return pd.DataFrame()

    long = pd.DataFrame(rows)
    counts = long.groupby(["week", "theme"]).size().reset_index(name="n")
    pivot = (
        counts.pivot(index="week", columns="theme", values="n")
        .fillna(0)
        .astype(int)
        .sort_index()
    )
    return pivot


def get_theme_momentum(df: "pd.DataFrame") -> "pd.DataFrame":
    """
    테마별 모멘텀 점수.
    최근 2주 언급 수 / 이전 2주 언급 수 비율.
    Returns: theme | recent | prev | momentum_score | tier
    tier: 🔥급상승(>3×) | 📈상승(>1.5×) | ➡️유지 | 📉하락(<0.7×)
    """
    import pandas as pd

    work = df[df["thesis"].notna() & df["report_date"].notna()].copy()
    if work.empty:
        return pd.DataFrame()

    work["report_date"] = pd.to_datetime(work["report_date"], errors="coerce")
    ceiling = pd.Timestamp.now() + pd.Timedelta(days=30)
    work = work[work["report_date"] <= ceiling]
    if work.empty:
        return pd.DataFrame()

    max_date  = work["report_date"].max()
    cut_mid   = max_date - pd.Timedelta(days=14)
    cut_start = max_date - pd.Timedelta(days=28)

    recent_rows = work[work["report_date"] > cut_mid]
    prev_rows   = work[(work["report_date"] > cut_start) & (work["report_date"] <= cut_mid)]

    def _count(rows: "pd.DataFrame") -> dict:
        counts: dict = {}
        for t in rows["thesis"]:
            for theme in extract_macro_themes(t):
                counts[theme] = counts.get(theme, 0) + 1
        return counts

    recent_c = _count(recent_rows)
    prev_c   = _count(prev_rows)

    rows_out = []
    for theme in set(recent_c) | set(prev_c):
        r = recent_c.get(theme, 0)
        p = prev_c.get(theme, 0)
        momentum = (r / p) if p > 0 else float("inf")
        if momentum == float("inf") or momentum > 3:
            tier = "🔥급상승"
        elif momentum > 1.5:
            tier = "📈상승"
        elif momentum < 0.7:
            tier = "📉하락"
        else:
            tier = "➡️유지"
        rows_out.append({
            "theme": theme, "recent": r, "prev": p,
            "momentum_score": round(momentum, 2) if momentum != float("inf") else None,
            "tier": tier,
        })

    result = pd.DataFrame(rows_out)
    if result.empty:
        return result
    return result.sort_values("recent", ascending=False).reset_index(drop=True)


def get_theme_overheat(df: "pd.DataFrame") -> "pd.DataFrame":
    """
    테마 과열도 점수.
    최근 4주 평균 대비 현재 주 z-score.
    Returns: theme | avg_weekly | current_week | z_score | overheat
    overheat: 🌡️과열(z>2) | ⚠️주의(z>1) | ✅정상
    """
    import pandas as pd

    trend = get_theme_trend(df)
    if trend.empty or len(trend) < 2:
        return pd.DataFrame()

    rows_out = []
    for theme in trend.columns:
        series = trend[theme].astype(float)
        if series.sum() == 0:
            continue
        current = float(series.iloc[-1])
        history = series.iloc[:-1].tail(4)
        avg     = float(history.mean())
        std     = float(history.std(ddof=0))
        z       = (current - avg) / std if std > 0 else 0.0
        if z > 2:
            overheat = "🌡️과열"
        elif z > 1:
            overheat = "⚠️주의"
        else:
            overheat = "✅정상"
        rows_out.append({
            "theme": theme, "avg_weekly": round(avg, 1),
            "current_week": int(current), "z_score": round(z, 2),
            "overheat": overheat,
        })

    result = pd.DataFrame(rows_out)
    if result.empty:
        return result
    return result.sort_values("z_score", ascending=False).reset_index(drop=True)


def get_theme_network(df: "pd.DataFrame") -> dict:
    """
    테마 간 연관관계 네트워크.
    같은 thesis에서 함께 등장하는 테마 쌍 집계.
    Returns: {"nodes": [...], "edges": [...]}
    nodes: {id, count, momentum_score, tier}
    edges: {source, target, weight}
    """
    from collections import defaultdict

    work = df[df["thesis"].notna()].copy()
    if work.empty:
        return {"nodes": [], "edges": []}

    theme_counts: dict = defaultdict(int)
    pair_counts:  dict = defaultdict(int)
    for thesis in work["thesis"]:
        themes = extract_macro_themes(thesis or "")
        for t in themes:
            theme_counts[t] += 1
        for i, t1 in enumerate(themes):
            for t2 in themes[i + 1:]:
                pair_counts[tuple(sorted([t1, t2]))] += 1

    momentum_df = get_theme_momentum(df)
    m_score: dict = {}
    m_tier:  dict = {}
    if not momentum_df.empty:
        for _, row in momentum_df.iterrows():
            m_score[row["theme"]] = row["momentum_score"]
            m_tier[row["theme"]]  = row["tier"]

    nodes = [
        {"id": t, "count": cnt,
         "momentum_score": m_score.get(t), "tier": m_tier.get(t, "➡️유지")}
        for t, cnt in theme_counts.items()
    ]
    edges = [
        {"source": pair[0], "target": pair[1], "weight": w}
        for pair, w in pair_counts.items() if w >= 2
    ]
    return {"nodes": nodes, "edges": edges}


def detect_new_themes(df: "pd.DataFrame", lookback_days: int = 7) -> list:
    """
    신규 테마 감지.
    최근 lookback_days일 키워드 빈도 vs 이전 30일 비교.
    5× 이상 증가 + 3건 이상인 키워드.
    Returns: [{keywords, count, sample_companies, first_seen, surge_ratio}]
    """
    import pandas as pd

    work = df[df["thesis"].notna() & df["report_date"].notna()].copy()
    if work.empty:
        return []

    work["report_date"] = pd.to_datetime(work["report_date"], errors="coerce")
    ceiling = pd.Timestamp.now() + pd.Timedelta(days=30)
    work = work[work["report_date"] <= ceiling]
    if work.empty:
        return []

    max_date    = work["report_date"].max()
    cut_recent  = max_date - pd.Timedelta(days=lookback_days)
    cut_start   = max_date - pd.Timedelta(days=lookback_days + 30)

    recent_rows = work[work["report_date"] > cut_recent]
    prev_rows   = work[(work["report_date"] > cut_start) & (work["report_date"] <= cut_recent)]

    def _kw_counts(rows: "pd.DataFrame") -> dict:
        counts: dict = {}
        for _, row in rows.iterrows():
            text_lower = (row["thesis"] or "").lower()
            for meta in MACRO_THEMES.values():
                for kw in meta["keywords"]:
                    if kw.lower() in text_lower:
                        counts[kw] = counts.get(kw, 0) + 1
        return counts

    recent_kw = _kw_counts(recent_rows)
    prev_kw   = _kw_counts(prev_rows)

    results = []
    seen: set = set()
    for kw, count in sorted(recent_kw.items(), key=lambda x: -x[1]):
        if kw in seen or count < 3:
            continue
        prev_count  = prev_kw.get(kw, 0)
        surge_ratio = (count / prev_count) if prev_count > 0 else float("inf")
        if surge_ratio != float("inf") and surge_ratio < 5:
            continue

        sample_companies: list = []
        first_seen = None
        for _, row in recent_rows.iterrows():
            if kw.lower() in (row["thesis"] or "").lower():
                co = row.get("company")
                if co and co not in sample_companies:
                    sample_companies.append(co)
                dt = row["report_date"]
                if first_seen is None or dt < first_seen:
                    first_seen = dt

        results.append({
            "keywords":         [kw],
            "count":            count,
            "sample_companies": sample_companies[:5],
            "first_seen":       str(first_seen)[:10] if first_seen is not None else None,
            "surge_ratio":      round(surge_ratio, 1) if surge_ratio != float("inf") else None,
        })
        seen.add(kw)
        if len(results) >= 10:
            break

    return results


def extract_macro_themes(thesis: str) -> list[str]:
    """
    Match thesis text against MACRO_THEMES keywords (case-insensitive).
    Returns theme names sorted by match-count descending.
    """
    if not thesis:
        return []
    text_lower = thesis.lower()
    scores: dict[str, int] = {}
    for theme, meta in MACRO_THEMES.items():
        count = sum(1 for kw in meta["keywords"] if kw.lower() in text_lower)
        if count > 0:
            scores[theme] = count
    return sorted(scores, key=lambda t: scores[t], reverse=True)


def _rank_themes(themes: list[str], sector: Optional[str]) -> list[str]:
    """
    Promote themes whose sectors list contains the company's actual sector
    to the front, preserving keyword-count order within each group.
    Falls back to pure keyword-count order when no theme matches the sector.
    """
    if not sector or not themes:
        return themes
    matched = [t for t in themes if sector in MACRO_THEMES[t]["sectors"]]
    others  = [t for t in themes if sector not in MACRO_THEMES[t]["sectors"]]
    return matched + others


def explain_buy_reason(
    company: Optional[str],
    sector: Optional[str],
    thesis: str,
    rating: str = "BUY",
) -> dict:
    """
    Keyword-based macro chain explanation.

    Return schema (stable for LLM swap):
      chain      : "테마 → Sector → 종목"
      themes     : list[str]  — matched themes; sector-matching theme first,
                                then remaining by keyword-count
      keywords   : list[str]  — all matched keywords across themes
      summary    : str        — one-sentence reason
      confidence : "high" | "mid" | "low"
    """
    themes = extract_macro_themes(thesis or "")
    themes = _rank_themes(themes, sector)   # sector match overrides keyword count

    # Collect all matched keywords, preserving theme order, deduped
    seen: set[str] = set()
    keywords: list[str] = []
    text_lower = (thesis or "").lower()
    for theme in themes:
        for kw in MACRO_THEMES[theme]["keywords"]:
            if kw.lower() in text_lower and kw not in seen:
                keywords.append(kw)
                seen.add(kw)

    # Confidence
    if len(keywords) >= 3:
        confidence = "high"
    elif len(keywords) >= 1:
        confidence = "mid"
    else:
        confidence = "low"

    # Chain
    theme_part   = themes[0] if themes else "—"
    sector_part  = sector or "—"
    company_part = company or "—"
    chain = f"{theme_part} → {sector_part} → {company_part}"

    # Summary
    co  = company or "이 종목"
    sec = sector or "—"
    if confidence == "low":
        summary = f"{co}({sec}) {rating} 추천 (매크로 연결고리 불명확)"
    elif len(themes) == 1:
        summary = f"{themes[0]} 수혜로 {co}({sec}) {rating} 추천"
    else:
        summary = f"{', '.join(themes[:2])} 모멘텀으로 {co}({sec}) {rating} 추천"

    return {
        "chain":      chain,
        "themes":     themes,
        "keywords":   keywords,
        "summary":    summary,
        "confidence": confidence,
    }
