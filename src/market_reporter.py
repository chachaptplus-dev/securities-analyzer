"""
Weekly market report generator — LLM-backed (Claude Haiku) with keyword fallback.
Called on-demand from the dashboard; never auto-executed.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


_MODEL = "claude-haiku-4-5-20251001"
_REPORTS_PATH = Path(__file__).resolve().parents[1] / "data" / "weekly_reports.json"

_PROMPT_TEMPLATE = """\
당신은 한국 주식시장 전문 애널리스트입니다.
아래 이번 주 증권사 리포트 데이터를 분석해서 JSON으로만 응답하세요.
다른 텍스트나 마크다운 없이 순수 JSON만 출력하세요.

{{
  "hot_themes": ["이번 주 가장 주목받은 테마 TOP 5 (한국어)"],
  "why_hot": {{
    "테마명": "왜 주목받았는지 2문장 설명"
  }},
  "rotation": "어떤 테마에서 어떤 테마로 관심이 이동했는지 (예: A → B)",
  "consensus_variables": ["증권사들이 공통으로 언급한 핵심 변수 TOP 5"],
  "market_phase": "현재 시장 국면 한 줄 요약",
  "next_watch": ["다음 주에 주목할 지표/이벤트 3가지"],
  "theme_lineage": "테마 연결 흐름 설명 (예: AI → 전력인프라 → 조선)",
  "logic_shift": "이번 주 투자 로직 변화 (예: 실적 중심 → 밸류에이션 재평가)"
}}

{context}"""


def save_weekly_report(report: dict) -> None:
    """Append report to data/weekly_reports.json, keeping the last 10."""
    reports: list = []
    if _REPORTS_PATH.exists():
        try:
            reports = json.loads(_REPORTS_PATH.read_text(encoding="utf-8"))
        except Exception:
            reports = []
    reports.append(report)
    reports = reports[-10:]
    _REPORTS_PATH.write_text(
        json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_latest_report(force: bool = False) -> dict | None:
    """Return the most recent saved report if within 24h, else None.
    If force=True, skip the file entirely (used by force-regenerate button).
    """
    if force:
        return None
    if not _REPORTS_PATH.exists():
        return None
    try:
        reports = json.loads(_REPORTS_PATH.read_text(encoding="utf-8"))
        if not reports:
            return None
        latest = reports[-1]
        generated_at = latest.get("generated_at")
        if not generated_at:
            return None
        dt = datetime.strptime(generated_at, "%Y-%m-%d %H:%M")
        if datetime.now() - dt <= timedelta(hours=24):
            return latest
        return None
    except Exception:
        return None


def _build_weekly_context(df: pd.DataFrame) -> str:
    cutoff = (pd.Timestamp.now() - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
    recent = df[df["report_date"].astype(str) >= cutoff]
    if recent.empty:
        recent = df.tail(50)

    sector_counts = recent["sector"].value_counts().head(10).to_dict()

    buy_df = (
        recent[recent["rating_normalized"] == "BUY"][
            ["company", "sector", "upside", "securities_firm"]
        ]
        .dropna(subset=["company"])
        .head(20)
    )
    buy_str = buy_df.to_string(index=False) if not buy_df.empty else "(없음)"

    theses = [
        f"- {t[:150]}"
        for t in recent["thesis"].dropna().head(15).tolist()
    ]
    thesis_str = "\n".join(theses) if theses else "(없음)"

    return (
        f"=== 이번 주 증권사 리포트 분석 ({datetime.now().strftime('%Y-%m-%d')} 기준) ===\n\n"
        f"[섹터별 리포트 수 (상위 10)]\n"
        f"{json.dumps(sector_counts, ensure_ascii=False, indent=2)}\n\n"
        f"[주요 BUY 추천 종목]\n{buy_str}\n\n"
        f"[대표 투자근거 샘플]\n{thesis_str}\n"
    )


def _compute_report_stats(df: pd.DataFrame) -> dict:
    """
    LLM 없이 df에서 직접 계산하는 통계.
    Returns: sector_changes, consensus_stocks, top_upside, new_coverage
    """
    empty = {"sector_changes": [], "consensus_stocks": [], "top_upside": [], "new_coverage": []}
    if df.empty:
        return empty

    work = df.copy()
    work["report_date"] = pd.to_datetime(work["report_date"], errors="coerce")
    work = work.dropna(subset=["report_date"])
    if work.empty:
        return empty

    max_date = work["report_date"].max()
    this_week_cut = max_date - pd.Timedelta(days=7)
    last_week_cut = max_date - pd.Timedelta(days=14)

    this_week = work[work["report_date"] > this_week_cut]
    last_week = work[(work["report_date"] > last_week_cut) & (work["report_date"] <= this_week_cut)]

    # --- sector changes ---
    this_s = this_week["sector"].value_counts()
    last_s = last_week["sector"].value_counts()
    all_sectors = set(this_s.index) | set(last_s.index)
    sector_changes = []
    for s in all_sectors:
        if not s or (isinstance(s, float) and pd.isna(s)):
            continue
        tw = int(this_s.get(s, 0))
        lw = int(last_s.get(s, 0))
        delta = tw - lw
        sector_changes.append({
            "sector": s,
            "this_week": tw,
            "last_week": lw,
            "change": f"+{delta}" if delta > 0 else str(delta),
        })
    sector_changes.sort(key=lambda x: abs(int(x["change"].replace("+", ""))), reverse=True)
    sector_changes = sector_changes[:10]

    # --- consensus stocks (3+ firms same week) ---
    consensus_stocks = []
    if not this_week.empty:
        for company, grp in this_week.dropna(subset=["company"]).groupby("company"):
            if not company:
                continue
            firm_count = int(grp["securities_firm"].nunique())
            if firm_count < 3:
                continue
            buy_n = int((grp["rating_normalized"] == "BUY").sum())
            rating = "BUY" if buy_n >= len(grp) / 2 else "HOLD"
            upside_vals = grp["upside"].dropna()
            avg_upside = round(float(upside_vals.mean()), 1) if not upside_vals.empty else 0.0
            consensus_stocks.append({
                "company": company,
                "firm_count": firm_count,
                "avg_upside": avg_upside,
                "rating": rating,
            })
        consensus_stocks.sort(key=lambda x: x["firm_count"], reverse=True)
        consensus_stocks = consensus_stocks[:5]

    # --- top upside: BUY reports this week ---
    top_upside = []
    if not this_week.empty:
        buy_df = (
            this_week[
                (this_week["rating_normalized"] == "BUY") &
                this_week["upside"].notna()
            ]
            .sort_values("upside", ascending=False)
            .head(5)
        )
        for _, row in buy_df.iterrows():
            top_upside.append({
                "company":         row.get("company") or "",
                "upside":          round(float(row["upside"]), 1),
                "sector":          row.get("sector") or "",
                "securities_firm": row.get("securities_firm") or "",
            })

    # --- new coverage: first appearance in this_week ---
    new_coverage: list[str] = []
    if not this_week.empty:
        this_cos = set(this_week["company"].dropna().unique())
        prev_cos = set(work[work["report_date"] <= this_week_cut]["company"].dropna().unique())
        new_coverage = sorted(this_cos - prev_cos)[:10]

    return {
        "sector_changes":  sector_changes,
        "consensus_stocks": consensus_stocks,
        "top_upside":      top_upside,
        "new_coverage":    new_coverage,
    }


def generate_weekly_report(df: pd.DataFrame) -> dict:
    """
    최근 7일 리포트 기반 주간 시장 리포트 LLM 생성.

    Returns dict with keys:
      generated_at, hot_themes, why_hot, rotation,
      consensus_variables, market_phase, next_watch,
      theme_lineage, logic_shift,
      sector_changes, consensus_stocks, top_upside, new_coverage,
      fallback
    """
    stats = _compute_report_stats(df)

    if df.empty:
        result = _fallback_weekly_report(df)
        result.update(stats)
        return result

    context = _build_weekly_context(df)
    prompt  = _PROMPT_TEMPLATE.format(context=context)

    try:
        import anthropic
        client   = anthropic.Anthropic()
        response = client.messages.create(
            model=_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        result = json.loads(raw)
        result["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        result["fallback"] = False
        result.update(stats)
        return result
    except Exception as exc:
        print(f"[market_reporter] LLM error — using fallback: {exc}")
        result = _fallback_weekly_report(df)
        result.update(stats)
        return result


def _fallback_weekly_report(df: pd.DataFrame) -> dict:
    """Keyword-frequency fallback when LLM is unavailable."""
    from src.macro_analyzer import extract_macro_themes

    recent = df.tail(100)
    all_themes: list[str] = []
    for thesis in recent["thesis"].dropna():
        all_themes.extend(extract_macro_themes(thesis))

    hot = [t for t, _ in Counter(all_themes).most_common(5)]

    return {
        "hot_themes":          hot,
        "why_hot":             {t: "키워드 분석 기반 (LLM 미사용)" for t in hot},
        "rotation":            "-",
        "consensus_variables": [],
        "market_phase":        "분석 중 (LLM 미사용)",
        "next_watch":          [],
        "theme_lineage":       "-",
        "logic_shift":         "-",
        "generated_at":        datetime.now().strftime("%Y-%m-%d %H:%M"),
        "fallback":            True,
    }
