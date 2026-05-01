"""
Buy Signal Score per company + Analyst Reliability Score.
  score = buy_count + tp_up_count + firm_count + avg_upside_score
          - hold_sell_count - tp_down_count

avg_upside_score is capped at 10 (i.e., 100 % upside maps to 10 pts).
"""
import re
import pandas as pd


def calculate_buy_signal_score(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    rows = []
    for company, grp in df.groupby("company"):
        if not company:
            continue

        buy_count     = int((grp["rating_normalized"] == "BUY").sum())
        positive_cnt  = int((grp["rating_normalized"] == "POSITIVE").sum())
        neutral_cnt   = int((grp["rating_normalized"] == "NEUTRAL").sum())
        hold_cnt      = int((grp["rating_normalized"] == "HOLD").sum())
        neg_cnt       = int(grp["rating_normalized"].isin(["NEGATIVE", "SELL"]).sum())
        hold_sell     = hold_cnt + neg_cnt  # kept for output column compatibility
        firm_count    = int(grp["securities_firm"].nunique())

        upside_vals = grp["upside"].dropna()
        avg_upside = float(upside_vals.mean()) if not upside_vals.empty else 0.0
        upside_score = min(avg_upside / 10.0, 10.0) if avg_upside > 0 else 0.0

        # Target-price trend (requires at least 2 dated reports)
        tp_up = tp_down = 0
        dated = grp.dropna(subset=["report_date", "target_price"]).sort_values("report_date")
        if len(dated) > 1:
            diff = dated["target_price"].diff().dropna()
            tp_up = int((diff > 0).sum())
            tp_down = int((diff < 0).sum())

        score = (buy_count
                 + positive_cnt * 0.6
                 + neutral_cnt * 0.2
                 - hold_cnt * 0.1
                 - neg_cnt
                 + tp_up
                 + firm_count
                 + upside_score
                 - tp_down)

        rows.append(
            {
                "company": company,
                "score": round(score, 2),
                "buy_count": buy_count,
                "hold_sell_count": hold_sell,
                "firm_count": firm_count,
                "avg_upside": round(avg_upside, 1),
                "tp_up": tp_up,
                "tp_down": tp_down,
                "latest_report": grp["report_date"].max(),
            }
        )

    return (
        pd.DataFrame(rows)
        .sort_values("score", ascending=False)
        .reset_index(drop=True)
    )


def get_analyst_scores(df: pd.DataFrame) -> pd.DataFrame:
    """
    애널리스트/증권사 신뢰도 점수.
    metrics:
    - coverage     : 다루는 종목 수
    - consistency  : 같은 종목 반복 커버 비율 (%)
    - bullish_ratio: Buy 비율 % (80%+ 페널티)
    - avg_upside   : 평균 상승여력 (50%+ 페널티)
    - reliability_score: 종합 점수 (0-100)
    Returns: analyst | firm | coverage | consistency |
             bullish_ratio | avg_upside | reliability_score
    """
    if df.empty:
        return pd.DataFrame()

    # Filter out boilerplate strings that end up in the analyst field
    _NOISE = re.compile(r"^(외이사의|책임|대리|관계자|당사는|주요주주|임원|이사회)$")
    work = df[
        df["analyst"].notna()
        & (df["analyst"].str.strip() != "")
        & (df["analyst"].str.len() >= 2)
        & (df["analyst"].str.len() <= 10)
        & ~df["analyst"].str.match(_NOISE).fillna(False)
    ].copy()
    if work.empty:
        return pd.DataFrame()

    rows = []
    for (analyst, firm), grp in work.groupby(["analyst", "securities_firm"], dropna=False):
        if len(grp) < 2:
            continue

        companies = grp["company"].dropna()
        coverage  = int(companies.nunique())
        if coverage == 0:
            continue

        company_counts = companies.value_counts()
        consistency = round(float((company_counts > 1).sum()) / coverage * 100, 1)

        rated_mask = grp["rating_normalized"].isin(["BUY", "HOLD", "SELL"])
        buy_n      = int((grp.loc[rated_mask, "rating_normalized"] == "BUY").sum())
        rated_n    = int(rated_mask.sum())
        bullish_ratio = round(buy_n / rated_n * 100, 1) if rated_n > 0 else 0.0

        upside_vals = grp["upside"].dropna()
        avg_upside  = round(float(upside_vals.mean()), 1) if not upside_vals.empty else 0.0

        score = 50.0
        score += min(coverage * 2.0, 20.0)       # breadth bonus (capped at +20)
        score += min(consistency * 0.15, 15.0)   # repeat-coverage bonus (capped at +15)
        if bullish_ratio > 80:
            score -= (bullish_ratio - 80) * 0.5  # over-bullish penalty
        if avg_upside > 50:
            score -= (avg_upside - 50) * 0.3     # unrealistic-target penalty
        score = round(max(0.0, min(100.0, score)), 1)

        rows.append({
            "analyst":           analyst,
            "firm":              str(firm) if firm else "",
            "coverage":          coverage,
            "consistency":       consistency,
            "bullish_ratio":     bullish_ratio,
            "avg_upside":        avg_upside,
            "reliability_score": score,
        })

    if not rows:
        return pd.DataFrame()

    return (
        pd.DataFrame(rows)
        .sort_values("reliability_score", ascending=False)
        .reset_index(drop=True)
    )
