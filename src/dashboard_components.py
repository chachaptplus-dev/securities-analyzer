"""Reusable Streamlit UI components for each dashboard tab."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


# ---------------------------------------------------------------------------
# Tab 1 – PDF Upload
# ---------------------------------------------------------------------------

def render_upload_tab(on_upload) -> None:
    st.header("PDF 리포트 업로드")
    st.markdown("증권사 리포트 PDF를 여러 개 동시에 업로드하면 종목·투자의견·목표주가·투자근거를 자동 추출합니다.")

    files = st.file_uploader(
        "PDF 파일 선택",
        type=["pdf"],
        accept_multiple_files=True,
    )

    if files:
        col_info, col_btn = st.columns([4, 1])
        col_info.info(f"{len(files)}개 파일 선택됨")
        if col_btn.button("분석 시작", type="primary", use_container_width=True):
            on_upload(files)


# ---------------------------------------------------------------------------
# Tab 2 – Extracted Reports
# ---------------------------------------------------------------------------

def render_reports_tab(df: pd.DataFrame) -> None:
    st.header("추출된 리포트 목록")

    if df.empty:
        st.info("아직 업로드된 리포트가 없습니다. **PDF Upload** 탭에서 파일을 올려주세요.")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        rating_opts = ["BUY", "HOLD", "SELL", "UNKNOWN"]
        sel_ratings = st.multiselect("투자의견", rating_opts, default=rating_opts)
    with col2:
        companies = ["전체"] + sorted(df["company"].dropna().unique().tolist())
        sel_company = st.selectbox("종목", companies)
    with col3:
        firms = ["전체"] + sorted(df["securities_firm"].dropna().unique().tolist())
        sel_firm = st.selectbox("증권사", firms)

    filtered = df.copy()
    if sel_ratings:
        filtered = filtered[filtered["rating_normalized"].isin(sel_ratings)]
    if sel_company != "전체":
        filtered = filtered[filtered["company"] == sel_company]
    if sel_firm != "전체":
        filtered = filtered[filtered["securities_firm"] == sel_firm]

    _COLS = {
        "filename": "파일명",
        "company": "종목",
        "rating_normalized": "투자의견",
        "target_price": "목표주가(원)",
        "current_price": "현재주가(원)",
        "upside": "업사이드(%)",
        "securities_firm": "증권사",
        "report_date": "리포트일",
    }
    st.dataframe(
        filtered[list(_COLS)].rename(columns=_COLS),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(f"총 {len(filtered):,}건 표시 중")


# ---------------------------------------------------------------------------
# Tab 3 – Buy Stocks
# ---------------------------------------------------------------------------

def render_buy_stocks_tab(reports_df: pd.DataFrame, scores_df: pd.DataFrame) -> None:
    st.header("Buy 종목 랭킹")

    if scores_df.empty:
        st.info("분석 데이터가 없습니다.")
        return

    top_n = min(20, len(scores_df))
    fig = px.bar(
        scores_df.head(top_n),
        x="company",
        y="score",
        color="score",
        color_continuous_scale="Blues",
        title=f"Buy Signal Score 상위 {top_n}개 종목",
        labels={"company": "종목", "score": "점수"},
        text_auto=".1f",
    )
    fig.update_layout(coloraxis_showscale=False, xaxis_tickangle=-30)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("점수 구성 상세")
    display = scores_df.copy()
    display.insert(0, "순위", range(1, len(display) + 1))
    st.dataframe(
        display.rename(
            columns={
                "company": "종목",
                "score": "Buy Signal Score",
                "buy_count": "Buy 수",
                "hold_sell_count": "Hold/Sell 수",
                "firm_count": "증권사 수",
                "avg_upside": "평균 업사이드(%)",
                "tp_up": "목표주가 상향",
                "tp_down": "목표주가 하향",
                "latest_report": "최근 리포트",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    if not reports_df.empty:
        rc = reports_df["rating_normalized"].value_counts()
        fig2 = px.pie(
            values=rc.values,
            names=rc.index,
            title="전체 투자의견 분포",
            color_discrete_map={
                "BUY": "#1976D2",
                "HOLD": "#FF9800",
                "SELL": "#E53935",
                "UNKNOWN": "#9E9E9E",
            },
        )
        st.plotly_chart(fig2, use_container_width=True)


# ---------------------------------------------------------------------------
# Tab 4 – Thesis Clusters
# ---------------------------------------------------------------------------

def render_clusters_tab(
    df: pd.DataFrame,
    labels: list[int],
    cluster_names: list[str],
    cluster_terms: dict[int, list[str]],
) -> None:
    st.header("투자근거 클러스터링")

    if df.empty or not labels:
        st.info("클러스터링할 데이터가 없습니다.")
        return

    df_c = df.copy()
    df_c["cluster_id"] = labels
    df_c["cluster_name"] = [cluster_names[l] for l in labels]

    counts = df_c["cluster_id"].value_counts().sort_index()
    fig = px.bar(
        x=[cluster_names[i] for i in counts.index],
        y=counts.values,
        title="클러스터별 리포트 수",
        labels={"x": "클러스터", "y": "리포트 수"},
    )
    fig.update_xaxes(tickangle=-20)
    st.plotly_chart(fig, use_container_width=True)

    selected_id = st.selectbox(
        "클러스터 선택",
        range(len(cluster_names)),
        format_func=lambda i: cluster_names[i],
    )

    terms = cluster_terms.get(selected_id, [])
    if terms:
        st.markdown("**핵심 키워드:** " + " &nbsp;|&nbsp; ".join(f"`{t}`" for t in terms))

    cluster_df = df_c[df_c["cluster_id"] == selected_id]
    st.dataframe(
        cluster_df[["company", "rating_normalized", "securities_firm", "report_date", "thesis"]].rename(
            columns={
                "company": "종목",
                "rating_normalized": "투자의견",
                "securities_firm": "증권사",
                "report_date": "리포트일",
                "thesis": "투자근거",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )


# ---------------------------------------------------------------------------
# Tab 5 – Company Detail
# ---------------------------------------------------------------------------

def render_company_tab(df: pd.DataFrame) -> None:
    st.header("종목 상세")

    if df.empty:
        st.info("데이터가 없습니다.")
        return

    companies = sorted(df["company"].dropna().unique().tolist())
    if not companies:
        st.info("종목 데이터가 없습니다.")
        return

    selected = st.selectbox("종목 선택", companies)
    cdf = df[df["company"] == selected].sort_values("report_date")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("총 리포트", len(cdf))
    buy_pct = (cdf["rating_normalized"] == "BUY").mean() * 100
    m2.metric("Buy 비율", f"{buy_pct:.0f}%")
    avg_tp = cdf["target_price"].mean()
    m3.metric("평균 목표주가", f"{avg_tp:,.0f}원" if pd.notna(avg_tp) else "N/A")
    avg_up = cdf["upside"].mean()
    m4.metric("평균 업사이드", f"{avg_up:.1f}%" if pd.notna(avg_up) else "N/A")

    if cdf["target_price"].notna().any():
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=cdf["report_date"],
                y=cdf["target_price"],
                mode="lines+markers",
                name="목표주가",
                line=dict(color="#1976D2", width=2),
            )
        )
        if cdf["current_price"].notna().any():
            fig.add_trace(
                go.Scatter(
                    x=cdf["report_date"],
                    y=cdf["current_price"],
                    mode="lines+markers",
                    name="현재주가",
                    line=dict(color="#FF9800", width=2, dash="dash"),
                )
            )
        fig.update_layout(
            title=f"{selected} 목표주가 추이",
            xaxis_title="날짜",
            yaxis_title="주가(원)",
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

    # Per-firm rating breakdown
    if cdf["securities_firm"].notna().any():
        rc = (
            cdf.groupby(["securities_firm", "rating_normalized"])
            .size()
            .reset_index(name="count")
        )
        fig2 = px.bar(
            rc,
            x="securities_firm",
            y="count",
            color="rating_normalized",
            barmode="stack",
            title="증권사별 투자의견",
            labels={"securities_firm": "증권사", "count": "건수", "rating_normalized": "투자의견"},
            color_discrete_map={
                "BUY": "#1976D2",
                "HOLD": "#FF9800",
                "SELL": "#E53935",
                "UNKNOWN": "#9E9E9E",
            },
        )
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("전체 리포트")
    st.dataframe(
        cdf[
            ["report_date", "rating_normalized", "target_price", "current_price",
             "upside", "securities_firm", "analyst", "thesis"]
        ].rename(
            columns={
                "report_date": "리포트일",
                "rating_normalized": "투자의견",
                "target_price": "목표주가",
                "current_price": "현재주가",
                "upside": "업사이드(%)",
                "securities_firm": "증권사",
                "analyst": "애널리스트",
                "thesis": "투자근거",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
