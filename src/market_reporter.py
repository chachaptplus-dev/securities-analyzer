"""
Weekly market report generator — LLM-backed (Claude Haiku) with keyword fallback.
Called on-demand from the dashboard; never auto-executed.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime

import pandas as pd


_MODEL = "claude-haiku-4-5-20251001"

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
  "theme_lineage": "테마 연결 흐름 설명 (예: AI → 전력인프라 → 조선)"
}}

{context}"""


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


def generate_weekly_report(df: pd.DataFrame) -> dict:
    """
    최근 7일 리포트 기반 주간 시장 리포트 LLM 생성.

    Returns dict with keys:
      generated_at, hot_themes, why_hot, rotation,
      consensus_variables, market_phase, next_watch,
      theme_lineage, fallback
    """
    if df.empty:
        return _fallback_weekly_report(df)

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
        # Strip accidental markdown fences
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        result = json.loads(raw)
        result["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        result["fallback"] = False
        return result
    except Exception as exc:
        print(f"[market_reporter] LLM error — using fallback: {exc}")
        return _fallback_weekly_report(df)


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
        "generated_at":        datetime.now().strftime("%Y-%m-%d %H:%M"),
        "fallback":            True,
    }
