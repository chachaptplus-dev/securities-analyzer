"""
Securities Report Analyzer — Streamlit entry point.
Run: streamlit run app.py
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

# Bridge Streamlit Cloud secrets → environment variables
try:
    _secrets_key = st.secrets.get("ANTHROPIC_API_KEY")
    if _secrets_key and not os.environ.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = _secrets_key
except Exception:
    pass

from src.clustering import cluster_theses
from src.dashboard_components import (
    render_buy_stocks_tab,
    render_clusters_tab,
    render_company_tab,
    render_market_intelligence_tab,
    render_reports_tab,
    render_sector_trends_tab,
    render_upload_tab,
)
from src.macro_analyzer import detect_new_themes
from src.database import clear_all, get_all_reports, initialize_db, insert_report
from src.extractor import extract_report_data, _infer_sentiment
from src.pdf_parser import extract_text_from_pdf
from src.rating_normalizer import normalize_rating
from src.scoring import calculate_buy_signal_score
from src.sector import infer_sector

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_SAMPLE_PATH = Path("data/sample_reports.csv")


def _load_demo_data() -> bool:
    """Insert sample CSV into an empty DB for Streamlit Cloud demo. Returns True if loaded."""
    if not _SAMPLE_PATH.exists():
        return False
    try:
        df = pd.read_csv(_SAMPLE_PATH)
        for _, row in df.iterrows():
            insert_report(row.to_dict())
        return True
    except Exception:
        return False

_PERIOD_DAYS: dict[str, int | None] = {
    "전체": None, "3개월": 91, "2개월": 61, "1개월": 31, "2주": 14,
}
_PERIOD_KEY = "sidebar_date_period"


def _apply_date_filter(df: pd.DataFrame, period: str) -> pd.DataFrame:
    days = _PERIOD_DAYS.get(period)
    if days is None or df.empty:
        return df
    dates = pd.to_datetime(df["report_date"], errors="coerce")
    cutoff = dates.max() - pd.Timedelta(days=days)
    return df[dates >= cutoff].copy()


_LOG_PATHS = [Path("data/scraper.log"), Path("logs/scraper.log")]
_DB_PATH   = "data/securities.duckdb"


@st.cache_data(ttl=600)
def _get_emerging_themes(df: pd.DataFrame) -> list:
    return detect_new_themes(df)


@st.cache_data(ttl=300)
def _get_scraper_status() -> dict:
    """
    Returns {last_run: datetime|None, count: int, source: str}.
    Tries log file first; falls back to DB MAX(uploaded_at).
    """
    # 1. Log file — use mtime as timestamp, parse count from last lines
    for log_path in _LOG_PATHS:
        if log_path.exists():
            try:
                mtime = datetime.fromtimestamp(log_path.stat().st_mtime)
                count = 0
                text = log_path.read_text(encoding="utf-8", errors="ignore")
                for line in reversed(text.splitlines()[-30:]):
                    m = re.search(r"(\d+)\s+new\s+PDF", line, re.IGNORECASE)
                    if m:
                        count = int(m.group(1))
                        break
                return {"last_run": mtime, "count": count, "source": "log"}
            except Exception:
                pass

    # 2. DB fallback
    try:
        con = duckdb.connect(_DB_PATH, read_only=True)
        row = con.execute("SELECT MAX(uploaded_at) FROM reports").fetchone()
        last_run = row[0] if row and row[0] is not None else None
        count = 0
        if last_run is not None:
            # Strip timezone if present
            if hasattr(last_run, "tzinfo") and last_run.tzinfo is not None:
                last_run = last_run.replace(tzinfo=None)
            last_date = last_run.date()
            result = con.execute(
                "SELECT COUNT(*) FROM reports WHERE DATE(uploaded_at) = ?", [last_date]
            ).fetchone()
            count = result[0] if result else 0
        con.close()
        return {"last_run": last_run, "count": count, "source": "db"}
    except Exception:
        return {"last_run": None, "count": 0, "source": "error"}

st.set_page_config(
    page_title="증권사 리포트 분석기",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Upload & processing pipeline
# ---------------------------------------------------------------------------

def _process_files(uploaded_files: list) -> None:
    progress = st.progress(0.0)
    status = st.empty()
    success = 0

    for i, uf in enumerate(uploaded_files):
        status.text(f"처리 중 ({i + 1}/{len(uploaded_files)}): {uf.name}")
        save_path = UPLOAD_DIR / uf.name

        with open(save_path, "wb") as f:
            f.write(uf.read())

        try:
            pdf_data = extract_text_from_pdf(str(save_path))
            report = extract_report_data(pdf_data)

            report["rating_normalized"] = normalize_rating(report.get("rating_raw"))
            if report["rating_normalized"] == "UNKNOWN":
                report["rating_normalized"] = _infer_sentiment(report.get("thesis") or "")

            tp = report.get("target_price")
            cp = report.get("current_price")
            if tp and cp and cp > 0 and tp > cp * 3:
                report["current_price"] = None
                cp = None
            report["upside"] = round((tp - cp) / cp * 100, 1) if (tp and cp and cp > 0) else None

            report["report_date"] = report.pop("date", None)
            report["sector"] = infer_sector(
                report.get("thesis") or "", report.get("company") or ""
            )

            insert_report(report)
            success += 1
        except Exception as exc:
            st.error(f"오류 [{uf.name}]: {exc}")

        progress.progress((i + 1) / len(uploaded_files))

    progress.empty()
    status.empty()
    st.success(f"{success}/{len(uploaded_files)}개 리포트 처리 완료")
    st.rerun()


# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------

def main() -> None:
    initialize_db()

    all_reports = get_all_reports()

    # On Streamlit Cloud the DB starts empty — load sample data for demo
    demo_mode = False
    if all_reports.empty:
        demo_mode = _load_demo_data()
        if demo_mode:
            all_reports = get_all_reports()

    # Seed session_state default so filtered_reports is computable before sidebar renders
    if _PERIOD_KEY not in st.session_state:
        st.session_state[_PERIOD_KEY] = "전체"

    filtered_reports = _apply_date_filter(all_reports, st.session_state[_PERIOD_KEY])

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.title("📊 증권 리포트 분석기")
        if demo_mode:
            st.info("🎭 **데모 모드** — 샘플 데이터 50건 표시 중\nPDF를 업로드하면 실제 모드로 전환됩니다.")
        st.divider()

        # Metrics reflect the filtered window
        st.subheader("데이터 현황")
        st.metric("총 리포트", len(filtered_reports))
        if not filtered_reports.empty:
            st.metric("종목 수", int(filtered_reports["company"].nunique()))
            st.metric("증권사 수", int(filtered_reports["securities_firm"].nunique()))
            st.metric(
                "Buy 의견",
                int((filtered_reports["rating_normalized"] == "BUY").sum()),
            )

        # Date range filter
        st.divider()
        st.subheader("📅 기간 필터")
        st.radio(
            "기간",
            list(_PERIOD_DAYS.keys()),
            key=_PERIOD_KEY,
            horizontal=True,
            label_visibility="collapsed",
        )

        # Active range caption
        if not all_reports.empty:
            dates = pd.to_datetime(all_reports["report_date"], errors="coerce")
            max_d = dates.max()
            days = _PERIOD_DAYS[st.session_state[_PERIOD_KEY]]
            if days is not None:
                cutoff = max_d - pd.Timedelta(days=days)
                st.caption(f"{cutoff.date()} ~ {max_d.date()}")
            else:
                st.caption(f"{dates.min().date()} ~ {max_d.date()}")

        # Scraper status
        st.divider()
        st.subheader("🤖 스크래퍼 현황")
        scraper = _get_scraper_status()
        lr = scraper["last_run"]
        if lr is None:
            st.caption("마지막 수집: 정보 없음")
            st.caption("오늘 수집: 정보 없음")
            st.caption("상태: 🔴 미실행")
        else:
            hours_ago = (datetime.now() - lr).total_seconds() / 3600
            st.caption(f"마지막 수집: {lr.strftime('%Y-%m-%d %H:%M')}")
            st.caption(f"오늘 수집: +{scraper['count']:,}건")
            if hours_ago < 25:
                st.caption("상태: 🟢 정상")
            elif hours_ago < 48:
                st.caption("상태: 🟡 지연")
            else:
                st.caption("상태: 🔴 미실행")

        # Emerging themes
        st.divider()
        st.subheader("🆕 급부상 테마")
        emerging = _get_emerging_themes(all_reports)
        if not emerging:
            st.caption("감지된 급부상 테마 없음")
        else:
            for t in emerging[:3]:
                kw        = t["keywords"][0] if t["keywords"] else "?"
                ratio_str = f"{t['surge_ratio']}×" if t["surge_ratio"] else "신규"
                companies = ", ".join(t["sample_companies"][:2]) if t["sample_companies"] else "—"
                color     = "#D32F2F"
                st.markdown(
                    f'<span style="background:{color};color:#fff;padding:2px 8px;'
                    f'border-radius:10px;font-size:12px">{kw}</span>'
                    f' &nbsp; **{ratio_str}**',
                    unsafe_allow_html=True,
                )
                st.caption(f"관련: {companies}")

        st.divider()
        if not all_reports.empty:
            if st.button("🗑 데이터 전체 초기화", type="secondary", use_container_width=True):
                clear_all()
                st.rerun()

    # ── Tabs — all receive filtered_reports ──────────────────────────────────
    (tab_upload, tab_reports, tab_buy, tab_sectors,
     tab_clusters, tab_company, tab_intel) = st.tabs(
        ["📤 PDF Upload", "📋 Extracted Reports", "📈 Buy Stocks",
         "🌐 Sector Trends", "📊 테마 투자 동향", "🏢 Company Detail",
         "📡 시장 인텔리전스"]
    )

    with tab_upload:
        render_upload_tab(_process_files)

    with tab_reports:
        render_reports_tab(filtered_reports)

    with tab_buy:
        scores = calculate_buy_signal_score(filtered_reports) if not filtered_reports.empty else pd.DataFrame()
        render_buy_stocks_tab(filtered_reports, scores)

    with tab_sectors:
        render_sector_trends_tab(filtered_reports)

    with tab_clusters:
        theses_col = filtered_reports["thesis"] if not filtered_reports.empty else pd.Series([], dtype=str)
        valid_theses = theses_col.fillna("").tolist()
        non_empty = [t for t in valid_theses if t.strip()]

        if len(non_empty) >= 2:
            n_clusters = min(5, max(2, len(non_empty) // 3))
            labels, cluster_names, cluster_terms = cluster_theses(valid_theses, n_clusters=n_clusters)
            render_clusters_tab(filtered_reports, labels, cluster_names, cluster_terms)
        else:
            st.info("클러스터링에는 최소 2개 이상의 투자근거 텍스트가 필요합니다.")

    with tab_company:
        render_company_tab(filtered_reports)

    with tab_intel:
        render_market_intelligence_tab(filtered_reports)


if __name__ == "__main__":
    main()
