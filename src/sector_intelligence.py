"""Sector trend analytics: weekly time-series, surge detection, co-occurrence."""
from __future__ import annotations

from itertools import combinations
from collections import defaultdict

import pandas as pd

# Ignore report dates more than 30 days in the future — extraction artefacts.
_MAX_FUTURE_DAYS = 30


def _sanitise_dates(df: pd.DataFrame) -> pd.DataFrame:
    ceiling = pd.Timestamp.now() + pd.Timedelta(days=_MAX_FUTURE_DAYS)
    df = df.copy()
    df["report_date"] = pd.to_datetime(df["report_date"])
    return df[df["report_date"] <= ceiling]


def weekly_sector_counts(df: pd.DataFrame) -> pd.DataFrame:
    """
    Wide pivot: index = week-start Monday, columns = sector, values = report count.
    Rows with missing report_date or sector are dropped.
    """
    work = df[df["sector"].notna() & df["report_date"].notna()].copy()
    if work.empty:
        return pd.DataFrame()

    work = _sanitise_dates(work)
    work["week"] = work["report_date"].dt.to_period("W").dt.start_time

    counts = work.groupby(["week", "sector"]).size().reset_index(name="n")
    pivot = (
        counts.pivot(index="week", columns="sector", values="n")
        .fillna(0)
        .astype(int)
        .sort_index()
    )
    return pivot


def detect_surges(
    df: pd.DataFrame,
    recent_weeks: int = 4,
    min_recent: int = 2,
    spike_ratio: float = 3.0,
    rising_ratio: float = 2.0,
    growing_ratio: float = 1.5,
) -> pd.DataFrame:
    """
    Compare the last `recent_weeks` weeks against the equal window before that.
    Only flags sectors with at least `min_recent` reports in the recent window.

    Returns columns: sector, recent, prior, ratio, tier (emoji label).
    """
    work = df[df["sector"].notna() & df["report_date"].notna()].copy()
    if work.empty:
        return pd.DataFrame()

    work = _sanitise_dates(work)
    max_date = work["report_date"].max()
    cut_mid   = max_date - pd.Timedelta(weeks=recent_weeks)
    cut_start = cut_mid  - pd.Timedelta(weeks=recent_weeks)

    recent = work[work["report_date"] >  cut_mid].groupby("sector").size()
    prior  = work[(work["report_date"] > cut_start) &
                  (work["report_date"] <= cut_mid)].groupby("sector").size()

    rows = []
    for s in recent.index:
        r = int(recent[s])
        p = int(prior.get(s, 0))
        if r < min_recent:
            continue
        ratio = r / p if p > 0 else float("inf")
        if ratio < growing_ratio:
            continue

        if ratio == float("inf"):
            tier = "🔴 Spike"
        elif ratio >= spike_ratio:
            tier = "🔴 Spike"
        elif ratio >= rising_ratio:
            tier = "🟠 Rising"
        else:
            tier = "🟡 Growing"

        rows.append({
            "sector": s,
            "recent_n": r,
            "prior_n": p,
            "ratio": round(ratio, 2) if ratio != float("inf") else None,
            "tier": tier,
        })

    result = pd.DataFrame(rows)
    if result.empty:
        return result
    return result.sort_values("recent_n", ascending=False).reset_index(drop=True)


def sector_cooccurrence(df: pd.DataFrame, min_days: int = 2) -> pd.DataFrame:
    """
    Count days on which each sector pair both appear.
    Returns a symmetric square DataFrame (matrix).
    Only pairs with co-occurrence >= `min_days` are retained; others are 0.
    """
    work = df[df["sector"].notna() & df["report_date"].notna()].copy()
    if work.empty:
        return pd.DataFrame()

    work = _sanitise_dates(work)
    work["report_date"] = work["report_date"].dt.normalize()
    day_sets = work.groupby("report_date")["sector"].apply(set)

    pair_counts: dict[tuple[str, str], int] = defaultdict(int)
    for sectors in day_sets:
        for a, b in combinations(sorted(sectors), 2):
            pair_counts[(a, b)] += 1

    if not pair_counts:
        return pd.DataFrame()

    all_sectors = sorted({s for pair in pair_counts for s in pair})
    matrix = pd.DataFrame(0, index=all_sectors, columns=all_sectors, dtype=int)
    for (a, b), cnt in pair_counts.items():
        if cnt >= min_days:
            matrix.loc[a, b] = cnt
            matrix.loc[b, a] = cnt

    active = matrix.sum(axis=1) > 0
    return matrix.loc[active, active]
