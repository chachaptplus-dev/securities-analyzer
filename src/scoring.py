"""
Buy Signal Score per company:
  score = buy_count + tp_up_count + firm_count + avg_upside_score
          - hold_sell_count - tp_down_count

avg_upside_score is capped at 10 (i.e., 100 % upside maps to 10 pts).
"""
import pandas as pd


def calculate_buy_signal_score(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    rows = []
    for company, grp in df.groupby("company"):
        if not company:
            continue

        buy_count = int((grp["rating_normalized"] == "BUY").sum())
        hold_sell = int(grp["rating_normalized"].isin(["HOLD", "SELL"]).sum())
        firm_count = int(grp["securities_firm"].nunique())

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

        score = buy_count + tp_up + firm_count + upside_score - hold_sell - tp_down

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
