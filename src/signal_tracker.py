"""
Overheat signal recorder and retrospective evaluator.
Persists to data/signal_tracker.duckdb (separate from main securities.duckdb).
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

_DB_PATH = str(Path(__file__).resolve().parents[1] / "data" / "signal_tracker.duckdb")

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS overheat_signals (
    signal_date         DATE,
    theme               VARCHAR,
    company             VARCHAR,
    sector              VARCHAR,
    price_at_signal     DOUBLE,
    target_price        DOUBLE,
    upside_at_signal    DOUBLE
)
"""


def _connect(read_only: bool = False):
    import duckdb
    return duckdb.connect(_DB_PATH, read_only=read_only)


def record_overheat_signal(df: pd.DataFrame) -> None:
    """
    과열 감지 시점의 관련 종목 주가를 DB에 기록.
    Skips companies already recorded today to avoid duplicates.
    """
    from src.macro_analyzer import get_theme_overheat, extract_macro_themes
    from src.market_data import _company_to_code

    if df.empty:
        return

    overheat = get_theme_overheat(df)
    if overheat.empty:
        return

    hot_themes = overheat[overheat["overheat"] == "🌡️과열"]["theme"].tolist()
    if not hot_themes:
        return

    today_str = date.today().strftime("%Y%m%d")
    today_iso = date.today().isoformat()

    con = _connect()
    con.execute(_CREATE_SQL)

    already = set(
        r[0]
        for r in con.execute(
            "SELECT company FROM overheat_signals WHERE signal_date = ?", [today_iso]
        ).fetchall()
    )

    work = df[df["thesis"].notna() & df["company"].notna()].copy()
    rows_inserted = 0

    for theme in hot_themes:
        theme_companies = (
            work[work["thesis"].apply(lambda t: theme in extract_macro_themes(t))]
            .dropna(subset=["company"])
            .drop_duplicates("company")
        )
        for _, row in theme_companies.iterrows():
            company = row["company"]
            if company in already:
                continue
            code = _company_to_code(company)
            if not code:
                continue
            try:
                from pykrx import stock as krx
                price_df = krx.get_market_ohlcv_by_date(today_str, today_str, code)
                if price_df.empty:
                    # fall back to previous trading day
                    prev_str = (date.today() - timedelta(days=3)).strftime("%Y%m%d")
                    price_df = krx.get_market_ohlcv_by_date(prev_str, today_str, code)
                if price_df.empty:
                    continue
                price_df.columns = ["open", "high", "low", "close", "volume", "change_pct"]
                current_price = float(price_df["close"].iloc[-1])
            except Exception:
                continue

            tp_val = row.get("target_price")
            target = float(tp_val) if pd.notna(tp_val) else None
            upside = row.get("upside")
            upside_val = float(upside) if pd.notna(upside) else None

            con.execute(
                "INSERT INTO overheat_signals VALUES (?, ?, ?, ?, ?, ?, ?)",
                [today_iso, theme, company, row.get("sector"),
                 current_price, target, upside_val],
            )
            already.add(company)
            rows_inserted += 1

    con.close()
    if rows_inserted:
        print(f"[signal_tracker] {rows_inserted} signals recorded for {today_iso}")


def evaluate_past_signals(lookback_days: int = 30) -> pd.DataFrame:
    """
    N일 전 기록된 과열 신호의 실제 수익률 평가.
    Returns: signal_date | theme | company | price_at_signal |
             current_price | actual_return | prediction_correct
    """
    from src.market_data import _company_to_code

    con = _connect()
    try:
        con.execute(_CREATE_SQL)
        cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
        rows = con.execute(
            "SELECT signal_date, theme, company, sector, price_at_signal, "
            "       target_price, upside_at_signal "
            "FROM overheat_signals WHERE signal_date >= ? ORDER BY signal_date DESC",
            [cutoff],
        ).fetchall()
    finally:
        con.close()

    if not rows:
        return pd.DataFrame()

    today_str = date.today().strftime("%Y%m%d")
    start_str = (date.today() - timedelta(days=lookback_days + 5)).strftime("%Y%m%d")

    results = []
    for signal_date, theme, company, sector, price_at_signal, target_price, upside_at_signal in rows:
        if not price_at_signal:
            continue
        code = _company_to_code(company)
        if not code:
            continue
        try:
            from pykrx import stock as krx
            price_df = krx.get_market_ohlcv_by_date(today_str, today_str, code)
            if price_df.empty:
                price_df = krx.get_market_ohlcv_by_date(start_str, today_str, code)
            if price_df.empty:
                continue
            price_df.columns = ["open", "high", "low", "close", "volume", "change_pct"]
            current_price = float(price_df["close"].iloc[-1])
        except Exception:
            continue

        actual_return = round((current_price - price_at_signal) / price_at_signal * 100, 2)
        # Overheat signal predicts correction → correct if price fell
        prediction_correct = actual_return < 0

        results.append({
            "signal_date":       str(signal_date)[:10],
            "theme":             theme,
            "company":           company,
            "price_at_signal":   price_at_signal,
            "current_price":     current_price,
            "actual_return":     actual_return,
            "prediction_correct": prediction_correct,
        })

    if not results:
        return pd.DataFrame()

    return pd.DataFrame(results).sort_values("signal_date", ascending=False).reset_index(drop=True)
