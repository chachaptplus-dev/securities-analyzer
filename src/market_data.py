"""
Macro market data (yfinance) + individual stock price history (pykrx).

SSL fix: yfinance's curl_cffi backend fails when certifi's .pem path
contains non-ASCII chars (Korean username on Windows).  We copy it to
the project data/ dir at import time so CURL_CA_BUNDLE is an ASCII path.
"""
from __future__ import annotations

import os
from pathlib import Path

# --- SSL fix (must run before yfinance import) ---
_CERT_DEST = Path(__file__).resolve().parents[1] / "data" / "cacert.pem"
if not _CERT_DEST.exists():
    try:
        import shutil, certifi
        shutil.copy(certifi.where(), str(_CERT_DEST))
    except Exception:
        pass
if _CERT_DEST.exists():
    os.environ.setdefault("CURL_CA_BUNDLE", str(_CERT_DEST))
    os.environ.setdefault("SSL_CERT_FILE",  str(_CERT_DEST))

import pandas as pd

_MACRO_TICKERS: dict[str, str] = {
    "kospi":   "^KS11",
    "kosdaq":  "^KQ11",
    "usd_krw": "KRW=X",
    "us_10y":  "^TNX",
    "wti":     "CL=F",
    "dxy":     "DX-Y.NYB",
}

_STOCK_MASTER_PATH = Path(__file__).resolve().parents[1] / "data" / "stock_master.csv"
_stock_master_cache: pd.DataFrame | None = None


def _load_stock_master() -> pd.DataFrame:
    global _stock_master_cache
    if _stock_master_cache is not None:
        return _stock_master_cache
    if not _STOCK_MASTER_PATH.exists():
        _stock_master_cache = pd.DataFrame(columns=["code", "name", "market"])
        return _stock_master_cache
    df = pd.read_csv(_STOCK_MASTER_PATH, dtype={"code": str})
    df["code"] = df["code"].str.zfill(6)
    _stock_master_cache = df
    return _stock_master_cache


def _company_to_code(company: str) -> str | None:
    master = _load_stock_master()
    if master.empty:
        return None
    rows = master[master["name"] == company]
    if rows.empty:
        # fuzzy: partial match
        rows = master[master["name"].str.contains(company, na=False)]
    return str(rows.iloc[0]["code"]) if not rows.empty else None


def get_macro_data(period: str = "3mo") -> dict:
    """
    매크로 지표 수집 (yfinance).
    Always fetches 6mo internally so all change windows are available.

    Returns {
        "prices": DataFrame,   # date × ticker, sliced to `period` — for chart
        "changes": {           # multi-period pct changes — for metric cards
            "<col>": {
                "current": float,
                "d1": float | None,   # 1-day %
                "w1": float | None,   # 1-week %
                "m1": float | None,   # 1-month %
                "m3": float | None,   # 3-month %
            }, ...
        }
    }
    Returns {} on total failure.
    """
    try:
        import yfinance as yf
    except ImportError:
        return {}

    dfs: dict[str, pd.Series] = {}
    for name, ticker in _MACRO_TICKERS.items():
        try:
            raw = yf.download(ticker, period="6mo", progress=False)
            if raw.empty:
                continue
            close = raw["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            close.name = name
            dfs[name] = close
        except Exception as e:
            print(f"[market_data] {name} ({ticker}) 수집 실패: {e}")

    if not dfs:
        return {}

    full = pd.concat(dfs.values(), axis=1)
    full.index = pd.to_datetime(full.index)
    full = full.sort_index().ffill().dropna(how="all")

    # --- compute multi-period changes from full 6mo series ---
    _PERIOD_DAYS = {"d1": 1, "w1": 7, "m1": 30, "m3": 91}
    last_date = full.index[-1]
    changes: dict[str, dict] = {}
    for col in full.columns:
        series = full[col].dropna()
        if series.empty:
            continue
        cur = float(series.iloc[-1])
        entry: dict = {"current": cur}
        for key, days in _PERIOD_DAYS.items():
            cutoff = last_date - pd.Timedelta(days=days)
            older = series[series.index <= cutoff]
            if older.empty:
                entry[key] = None
            else:
                prev = float(older.iloc[-1])
                entry[key] = round((cur - prev) / prev * 100, 2) if prev else None
        changes[col] = entry

    # --- slice prices to the requested period for the chart ---
    _CHART_DAYS = {"1mo": 30, "3mo": 91, "6mo": 183}
    chart_days = _CHART_DAYS.get(period, 91)
    chart_cutoff = last_date - pd.Timedelta(days=chart_days)
    prices = full[full.index >= chart_cutoff]

    return {"prices": prices, "changes": changes}


def get_stock_price_history(
    company: str,
    start_date: str,
    end_date: str | None = None,
) -> pd.DataFrame:
    """
    종목 주가 기록 조회 (pykrx).
    Returns DataFrame: date(index) | open | high | low | close | volume
    """
    from datetime import date as _date, timedelta

    code = _company_to_code(company)
    if code is None:
        return pd.DataFrame()

    if end_date is None:
        end_date = _date.today().strftime("%Y%m%d")
    else:
        end_date = end_date.replace("-", "")
    start_fmt = start_date.replace("-", "")

    try:
        from pykrx import stock as krx
        df = krx.get_market_ohlcv_by_date(start_fmt, end_date, code)
        if df.empty:
            return pd.DataFrame()
        df.columns = ["open", "high", "low", "close", "volume", "change_pct"]
        df.index.name = "date"
        return df[["open", "high", "low", "close", "volume"]]
    except Exception as e:
        print(f"[market_data] {company}({code}) 주가 조회 실패: {e}")
        return pd.DataFrame()


def get_theme_performance(
    df: pd.DataFrame,
    theme: str,
    lookback_days: int = 30,
) -> dict:
    """
    특정 테마 관련 종목들의 최근 N일 주가 성과.
    Returns: theme, period, stocks, avg_return, beat_count, miss_count
    """
    from datetime import date as _date, timedelta
    from src.macro_analyzer import extract_macro_themes

    empty = {
        "theme": theme, "period": f"{lookback_days}일",
        "stocks": [], "avg_return": 0.0, "beat_count": 0, "miss_count": 0,
    }

    if df.empty:
        return empty

    work = df[df["thesis"].notna() & df["company"].notna()].copy()
    theme_companies = (
        work[work["thesis"].apply(lambda t: theme in extract_macro_themes(t))]
        ["company"]
        .dropna()
        .unique()
        .tolist()
    )
    if not theme_companies:
        return empty

    end_dt   = _date.today()
    start_dt = end_dt - timedelta(days=lookback_days)
    end_str   = end_dt.strftime("%Y%m%d")
    start_str = start_dt.strftime("%Y%m%d")

    stocks = []
    for company in theme_companies[:15]:
        code = _company_to_code(company)
        if not code:
            continue
        try:
            from pykrx import stock as krx
            price_df = krx.get_market_ohlcv_by_date(start_str, end_str, code)
            if price_df.empty or len(price_df) < 2:
                continue
            price_df.columns = ["open", "high", "low", "close", "volume", "change_pct"]
            first_close = float(price_df["close"].iloc[0])
            last_close  = float(price_df["close"].iloc[-1])
            if first_close <= 0:
                continue
            ret = round((last_close - first_close) / first_close * 100, 2)

            report_rows = work[work["company"] == company]
            report_date = str(report_rows["report_date"].max())[:10] if not report_rows.empty else None

            stocks.append({"company": company, "return_pct": ret, "report_date": report_date})
        except Exception:
            continue

    if not stocks:
        return empty

    returns   = [s["return_pct"] for s in stocks]
    avg_ret   = round(sum(returns) / len(returns), 2)
    beat      = sum(1 for r in returns if r > 0)
    miss      = sum(1 for r in returns if r <= 0)

    return {
        "theme":       theme,
        "period":      f"{lookback_days}일",
        "stocks":      sorted(stocks, key=lambda x: x["return_pct"], reverse=True),
        "avg_return":  avg_ret,
        "beat_count":  beat,
        "miss_count":  miss,
    }
