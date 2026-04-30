"""
Securities Report Analyzer — Streamlit entry point.
Run: streamlit run app.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.clustering import cluster_theses
from src.dashboard_components import (
    render_buy_stocks_tab,
    render_clusters_tab,
    render_company_tab,
    render_reports_tab,
    render_sector_trends_tab,
    render_upload_tab,
)
from src.database import clear_all, get_all_reports, initialize_db, insert_report
from src.extractor import extract_report_data
from src.pdf_parser import extract_text_from_pdf
from src.rating_normalizer import normalize_rating
from src.scoring import calculate_buy_signal_score
from src.sector import infer_sector

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

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

            tp = report.get("target_price")
            cp = report.get("current_price")
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

    # Sidebar
    with st.sidebar:
        st.title("📊 증권 리포트 분석기")
        st.divider()
        st.subheader("데이터 현황")
        st.metric("총 리포트", len(all_reports))
        if not all_reports.empty:
            st.metric("종목 수", int(all_reports["company"].nunique()))
            st.metric("증권사 수", int(all_reports["securities_firm"].nunique()))
            st.metric(
                "Buy 의견",
                int((all_reports["rating_normalized"] == "BUY").sum()),
            )
        st.divider()
        if not all_reports.empty:
            if st.button("🗑 데이터 전체 초기화", type="secondary", use_container_width=True):
                clear_all()
                st.rerun()

    tab_upload, tab_reports, tab_buy, tab_sectors, tab_clusters, tab_company = st.tabs(
        ["📤 PDF Upload", "📋 Extracted Reports", "📈 Buy Stocks",
         "🌐 Sector Trends", "🔍 Thesis Clusters", "🏢 Company Detail"]
    )

    with tab_upload:
        render_upload_tab(_process_files)

    with tab_reports:
        render_reports_tab(all_reports)

    with tab_buy:
        scores = calculate_buy_signal_score(all_reports) if not all_reports.empty else pd.DataFrame()
        render_buy_stocks_tab(all_reports, scores)

    with tab_sectors:
        render_sector_trends_tab(all_reports)

    with tab_clusters:
        theses_col = all_reports["thesis"] if not all_reports.empty else pd.Series([], dtype=str)
        valid_theses = theses_col.fillna("").tolist()
        non_empty = [t for t in valid_theses if t.strip()]

        if len(non_empty) >= 2:
            n_clusters = min(5, max(2, len(non_empty) // 3))
            labels, cluster_names, cluster_terms = cluster_theses(valid_theses, n_clusters=n_clusters)
            render_clusters_tab(all_reports, labels, cluster_names, cluster_terms)
        else:
            st.info("클러스터링에는 최소 2개 이상의 투자근거 텍스트가 필요합니다.")

    with tab_company:
        render_company_tab(all_reports)


if __name__ == "__main__":
    main()
