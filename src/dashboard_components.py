"""Reusable Streamlit UI components for each dashboard tab."""
from __future__ import annotations

import math
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.sector_intelligence import (
    detect_surges,
    sector_cooccurrence,
    weekly_sector_counts,
)
from src.macro_analyzer import (
    explain_buy_reason,
    extract_macro_themes,
    get_theme_trend,
    get_theme_momentum,
    get_theme_overheat,
    get_theme_network,
    detect_new_themes,
    MACRO_THEMES,
    THEME_COLORS,
    _DEFAULT_BADGE_COLOR,
)
from src.scoring import get_analyst_scores
from src.market_reporter import generate_weekly_report


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

    # ── Sector filter ─────────────────────────────────────────────────────────
    all_sectors = sorted(reports_df["sector"].dropna().unique().tolist()) if not reports_df.empty else []
    sel_sectors = st.multiselect("섹터 필터", options=all_sectors, default=[],
                                  placeholder="전체 섹터 (선택하면 필터)")

    if sel_sectors:
        sector_companies = (
            reports_df[reports_df["sector"].isin(sel_sectors)]["company"]
            .dropna().unique()
        )
        fscores  = scores_df[scores_df["company"].isin(sector_companies)].copy()
        freports = reports_df[reports_df["sector"].isin(sel_sectors)].copy()
    else:
        fscores  = scores_df
        freports = reports_df

    if fscores.empty:
        st.info("선택한 섹터에 Buy Signal 데이터가 없습니다.")
        return

    # ── Buy Signal Score bar chart ────────────────────────────────────────────
    top_n = min(20, len(fscores))
    fig = px.bar(
        fscores.head(top_n),
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

    # ── Score breakdown table ─────────────────────────────────────────────────
    st.subheader("점수 구성 상세")
    display = fscores.copy()
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

    if freports.empty:
        return

    col_pie, col_bar = st.columns(2)

    # ── Rating distribution pie ───────────────────────────────────────────────
    with col_pie:
        rc = freports["rating_normalized"].value_counts()
        fig2 = px.pie(
            values=rc.values,
            names=rc.index,
            title="투자의견 분포",
            color_discrete_map={
                "BUY": "#1976D2",
                "HOLD": "#FF9800",
                "SELL": "#E53935",
                "UNKNOWN": "#9E9E9E",
            },
        )
        st.plotly_chart(fig2, use_container_width=True)

    # ── Sector Buy-rate bar chart ─────────────────────────────────────────────
    with col_bar:
        if "sector" in freports.columns and freports["sector"].notna().any():
            sector_counts = freports.groupby("sector", observed=True).size()
            active_sectors = sector_counts[sector_counts >= 5].index
            sec_buy = (
                freports[freports["sector"].isin(active_sectors)]
                .groupby("sector", observed=True)
                .apply(lambda x: round((x["rating_normalized"] == "BUY").mean() * 100, 1))
                .reset_index(name="buy_pct")
                .sort_values("buy_pct", ascending=True)
            )
            fig3 = px.bar(
                sec_buy,
                x="buy_pct",
                y="sector",
                orientation="h",
                color="buy_pct",
                color_continuous_scale="Blues",
                title="섹터별 Buy 비율 (%)",
                labels={"buy_pct": "Buy 비율 (%)", "sector": ""},
                text_auto=".1f",
            )
            fig3.update_layout(coloraxis_showscale=False, margin=dict(l=160))
            st.plotly_chart(fig3, use_container_width=True)


# ---------------------------------------------------------------------------
# Tab 4 – Thesis Clusters (macro theme view)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _tag_themes(theses: tuple[str, ...]) -> list[list[str]]:
    """Cached: apply extract_macro_themes to each thesis string."""
    return [extract_macro_themes(t) for t in theses]


def render_clusters_tab(
    df: pd.DataFrame,
    labels: list[int],
    cluster_names: list[str],
    cluster_terms: dict[int, list[str]],
) -> None:
    st.header("📊 테마별 투자 동향")

    if df.empty:
        st.info("클러스터링할 데이터가 없습니다.")
        return

    # ── Compute theme tags ────────────────────────────────────────────────────
    theses = tuple(df["thesis"].fillna("").tolist())
    theme_lists = _tag_themes(theses)

    # Build a flat list of (row_index, theme) pairs
    tagged_rows = []
    for idx, themes in enumerate(theme_lists):
        for t in themes:
            tagged_rows.append({"_idx": idx, "theme": t})

    if not tagged_rows:
        st.info("투자근거 텍스트에서 매크로 테마를 찾지 못했습니다.")
        _render_kmeans_expander(df, labels, cluster_names, cluster_terms)
        return

    df_tagged = pd.DataFrame(tagged_rows)

    # ── Section 1: Theme Overview ─────────────────────────────────────────────
    st.subheader("테마 현황")
    theme_counts = df_tagged["theme"].value_counts().reset_index()
    theme_counts.columns = ["theme", "count"]

    bar_colors = [THEME_COLORS.get(t, _DEFAULT_BADGE_COLOR) for t in theme_counts["theme"]]
    fig_overview = px.bar(
        theme_counts,
        x="count",
        y="theme",
        orientation="h",
        title="매크로 테마별 리포트 수",
        labels={"count": "리포트 수", "theme": ""},
        text_auto=True,
        color="theme",
        color_discrete_map=THEME_COLORS,
    )
    fig_overview.update_layout(
        showlegend=False,
        coloraxis_showscale=False,
        margin=dict(l=160),
        yaxis=dict(categoryorder="total ascending"),
    )
    st.plotly_chart(fig_overview, use_container_width=True)

    # ── Section 2: Theme Deep-Dive ────────────────────────────────────────────
    st.divider()
    st.subheader("테마 심층 분석")

    theme_options = theme_counts["theme"].tolist()
    sel_theme = st.selectbox("테마 선택", theme_options)

    if sel_theme:
        theme_idx = df_tagged[df_tagged["theme"] == sel_theme]["_idx"].unique()
        theme_df = df.iloc[theme_idx].copy()

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 리포트", len(theme_df))
        m2.metric("종목 수", int(theme_df["company"].dropna().nunique()))
        buy_pct = (theme_df["rating_normalized"] == "BUY").mean() * 100
        m3.metric("BUY 비율", f"{buy_pct:.0f}%")
        avg_up = theme_df["upside"].dropna().mean()
        m4.metric("평균 업사이드", f"{avg_up:.1f}%" if pd.notna(avg_up) else "N/A")

        # Theme description
        desc = MACRO_THEMES.get(sel_theme, {}).get("description", "")
        if desc:
            st.caption(desc)

        # Top 10 stocks
        st.markdown("**상위 10 종목**")
        top_stocks = (
            theme_df.groupby("company", observed=True)
            .agg(
                reports=("id", "count"),
                buy_count=("rating_normalized", lambda x: (x == "BUY").sum()),
                avg_upside=("upside", "mean"),
                latest_date=("report_date", "max"),
            )
            .reset_index()
            .sort_values("reports", ascending=False)
            .head(10)
        )
        top_stocks["avg_upside"] = top_stocks["avg_upside"].round(1)
        top_stocks["buy_pct"] = (
            top_stocks["buy_count"] / top_stocks["reports"] * 100
        ).round(0).astype("Int64")
        st.dataframe(
            top_stocks.rename(columns={
                "company": "종목", "reports": "리포트", "buy_pct": "BUY %",
                "avg_upside": "평균 업사이드 %", "latest_date": "최근 리포트일",
            }).drop(columns=["buy_count"]),
            use_container_width=True,
            hide_index=True,
        )

        # Recent 10 reports
        st.markdown("**최근 리포트 10건**")
        recent = (
            theme_df.dropna(subset=["report_date"])
            .sort_values("report_date", ascending=False)
            .head(10)
        )
        st.dataframe(
            recent[["report_date", "company", "rating_normalized", "securities_firm", "thesis"]].rename(
                columns={
                    "report_date": "리포트일", "company": "종목",
                    "rating_normalized": "투자의견", "securities_firm": "증권사",
                    "thesis": "투자근거",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

        # Related themes co-occurrence
        st.markdown("**함께 언급된 테마**")
        cooc_rows = []
        for idx in theme_idx:
            for other_theme in theme_lists[idx]:
                if other_theme != sel_theme:
                    cooc_rows.append(other_theme)
        if cooc_rows:
            cooc_counts = pd.Series(cooc_rows).value_counts().head(8)
            badges = []
            for t, cnt in cooc_counts.items():
                color = THEME_COLORS.get(t, _DEFAULT_BADGE_COLOR)
                badges.append(
                    f'<span style="background:{color};color:#fff;padding:2px 10px;'
                    f'border-radius:12px;font-size:13px;margin-right:4px">'
                    f'{t} ({cnt})</span>'
                )
            st.markdown("&nbsp;".join(badges), unsafe_allow_html=True)
        else:
            st.caption("단독 테마 — 함께 언급된 테마 없음")

    # ── Section 3: Theme Trend ────────────────────────────────────────────────
    st.divider()
    st.subheader("테마 트렌드 (주간)")

    trend = get_theme_trend(df)
    if trend.empty or len(trend) < 2:
        st.info("주간 트렌드를 표시할 날짜 정보가 부족합니다.")
    else:
        top6 = (
            theme_counts.head(6)["theme"].tolist()
        )
        available_themes = [t for t in trend.columns if t in theme_counts["theme"].values]
        default_themes = [t for t in top6 if t in available_themes]

        sel_trend = st.multiselect(
            "표시할 테마",
            options=available_themes,
            default=default_themes,
            key="theme_trend_sel",
        )
        if sel_trend:
            long = (
                trend[sel_trend]
                .reset_index()
                .melt(id_vars="week", var_name="theme", value_name="reports")
            )
            long["week"] = long["week"].dt.strftime("%Y-%m-%d")
            fig_trend = px.line(
                long,
                x="week",
                y="reports",
                color="theme",
                color_discrete_map=THEME_COLORS,
                markers=True,
                title="테마별 주간 리포트 수",
                labels={"week": "주(월요일 기준)", "reports": "리포트 수", "theme": "테마"},
            )
            fig_trend.update_layout(
                xaxis_tickangle=-30,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                margin=dict(t=80),
                hovermode="x unified",
            )
            st.plotly_chart(fig_trend, use_container_width=True)

    # ── KMeans expander ───────────────────────────────────────────────────────
    _render_kmeans_expander(df, labels, cluster_names, cluster_terms)


def _render_kmeans_expander(
    df: pd.DataFrame,
    labels: list[int],
    cluster_names: list[str],
    cluster_terms: dict[int, list[str]],
) -> None:
    with st.expander("🔬 고급: TF-IDF 클러스터링", expanded=False):
        if not labels:
            st.info("클러스터 데이터가 없습니다.")
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
            key="kmeans_cluster_sel",
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
# Tab 5 – Sector Trends
# ---------------------------------------------------------------------------

def render_sector_trends_tab(df: pd.DataFrame) -> None:
    st.header("Sector Trends")

    if df.empty or "sector" not in df.columns:
        st.info("No sector data available.")
        return

    tagged = df[df["sector"].notna()].copy()
    if tagged.empty:
        st.info("No reports have been tagged with a sector yet.")
        return

    # ── Sector-level summary ─────────────────────────────────────────────────
    sector_stats = (
        tagged.groupby("sector")
        .agg(
            reports=("id", "count"),
            stocks=("company", "nunique"),
            avg_upside=("upside", "mean"),
        )
        .reset_index()
        .sort_values("reports", ascending=False)
    )
    sector_stats["avg_upside"] = sector_stats["avg_upside"].round(1)

    st.caption(
        f"{len(tagged):,} tagged reports · {sector_stats['stocks'].sum():,} stocks · "
        f"{len(sector_stats)} sectors"
    )

    # ── Chart row ────────────────────────────────────────────────────────────
    col_vol, col_up = st.columns(2)

    with col_vol:
        fig_vol = px.bar(
            sector_stats,
            x="sector",
            y="reports",
            color="reports",
            color_continuous_scale="Blues",
            title="Report Volume by Sector",
            labels={"sector": "", "reports": "Reports"},
            text_auto=True,
        )
        fig_vol.update_layout(
            coloraxis_showscale=False,
            xaxis_tickangle=-35,
            margin=dict(b=120),
        )
        st.plotly_chart(fig_vol, use_container_width=True)

    with col_up:
        upside_sorted = (
            sector_stats.dropna(subset=["avg_upside"])
            .sort_values("avg_upside", ascending=True)
        )
        fig_up = px.bar(
            upside_sorted,
            x="avg_upside",
            y="sector",
            orientation="h",
            color="avg_upside",
            color_continuous_scale="RdYlGn",
            title="Avg Analyst Upside by Sector (%)",
            labels={"avg_upside": "Avg Upside (%)", "sector": ""},
            text_auto=".1f",
        )
        fig_up.update_layout(coloraxis_showscale=False, margin=dict(l=160))
        st.plotly_chart(fig_up, use_container_width=True)

    # ── Surge Detection ──────────────────────────────────────────────────────
    st.divider()
    st.subheader("Surge Detection")
    st.caption("최근 30일 vs 이전 30일 비교 · 최소 3건 · ≥2× 배율")

    surges = detect_surges(tagged)
    total_sectors = len(sector_stats)

    if surges.empty:
        st.success("현재 급증 섹터 없음 (정상 범위)")
    elif len(surges) >= total_sectors * 0.8:
        st.warning(
            "데이터가 특정 기간에 집중되어 있어 급증 감지가 부정확할 수 있습니다"
        )
    else:
        cols = st.columns(min(len(surges), 4))
        for i, (_, row) in enumerate(surges.iterrows()):
            if i >= 8:
                break
            col = cols[i % 4]
            ratio_str = f"{row['ratio']:.1f}×" if row["ratio"] is not None else "신규"
            col.metric(
                label=f"{row['tier']}  {row['sector']}",
                value=f"{row['recent_n']} reports",
                delta=f"{ratio_str} vs 이전 30일 (이전 {row['prior_n']}건)",
            )

    # ── Weekly Trend ─────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Weekly Report Activity")

    pivot = weekly_sector_counts(tagged)
    if pivot.empty or len(pivot) < 2:
        st.info("Not enough dated reports to show a weekly trend.")
    else:
        # Default: top 8 sectors by total volume
        top8 = sector_stats.head(8)["sector"].tolist()
        available = [s for s in pivot.columns if s in sector_stats["sector"].values]
        default_sel = [s for s in top8 if s in available]

        selected = st.multiselect(
            "Sectors to display",
            options=available,
            default=default_sel,
            key="weekly_trend_sectors",
        )

        if selected:
            long = (
                pivot[selected]
                .reset_index()
                .melt(id_vars="week", var_name="sector", value_name="reports")
            )
            long["week"] = long["week"].dt.strftime("%Y-%m-%d")

            fig_trend = px.line(
                long,
                x="week",
                y="reports",
                color="sector",
                markers=True,
                title="Weekly Report Count by Sector",
                labels={"week": "Week starting", "reports": "Reports", "sector": "Sector"},
            )
            fig_trend.update_layout(
                xaxis_tickangle=-30,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                margin=dict(t=80),
                hovermode="x unified",
            )
            st.plotly_chart(fig_trend, use_container_width=True)
        else:
            st.caption("Select at least one sector above.")

    # ── Co-occurrence Heatmap ─────────────────────────────────────────────────
    st.divider()
    st.subheader("Sector Co-occurrence")
    st.caption("Number of days where both sectors had reports published — reveals analyst focus clusters")

    cooc = sector_cooccurrence(tagged, min_days=2)
    if cooc.empty:
        st.info("Not enough data for co-occurrence analysis.")
    else:
        fig_heat = px.imshow(
            cooc,
            color_continuous_scale="Blues",
            title="Sector Pair Co-occurrence (days)",
            aspect="auto",
            text_auto=True,
        )
        fig_heat.update_layout(
            xaxis_tickangle=-40,
            coloraxis_showscale=False,
            margin=dict(l=160, b=160),
        )
        fig_heat.update_traces(textfont_size=10)
        st.plotly_chart(fig_heat, use_container_width=True)

    # ── Sector deep-dive ─────────────────────────────────────────────────────
    st.divider()
    st.subheader("Sector Deep-Dive")

    sector_list = sector_stats.sort_values("reports", ascending=False)["sector"].tolist()
    selected_sector = st.selectbox("Select a sector", sector_list)

    sdf = tagged[tagged["sector"] == selected_sector].copy()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Reports", len(sdf))
    m2.metric("Stocks", int(sdf["company"].nunique()))
    avg_up = sdf["upside"].dropna().mean()
    m3.metric("Avg Upside", f"{avg_up:.1f}%" if pd.notna(avg_up) else "N/A")
    buy_pct = (sdf["rating_normalized"] == "BUY").mean() * 100
    m4.metric("BUY Rate", f"{buy_pct:.0f}%")

    # Top stocks table
    st.markdown("**Top Stocks**")
    stock_stats = (
        sdf.groupby("company")
        .agg(
            reports=("id", "count"),
            avg_upside=("upside", "mean"),
            buy_count=("rating_normalized", lambda x: (x == "BUY").sum()),
            latest_date=("report_date", "max"),
            latest_rating=("rating_normalized", "last"),
        )
        .reset_index()
        .sort_values("avg_upside", ascending=False)
    )
    stock_stats["avg_upside"] = stock_stats["avg_upside"].round(1)
    stock_stats["buy_pct"] = (stock_stats["buy_count"] / stock_stats["reports"] * 100).round(0).astype("Int64")

    st.dataframe(
        stock_stats.rename(columns={
            "company":      "Company",
            "reports":      "Reports",
            "avg_upside":   "Avg Upside %",
            "buy_pct":      "BUY %",
            "latest_date":  "Latest Report",
            "latest_rating":"Latest Rating",
        }).drop(columns=["buy_count"]),
        use_container_width=True,
        hide_index=True,
    )

    # BUY thesis snippets for top stocks
    st.markdown("**Recent BUY Theses**")
    buy_rows = (
        sdf[sdf["rating_normalized"] == "BUY"]
        .dropna(subset=["thesis"])
        .sort_values("report_date", ascending=False)
        .drop_duplicates(subset=["company"])
        .head(8)
    )

    if buy_rows.empty:
        st.caption("No BUY-rated reports with thesis text in this sector.")
    else:
        for _, row in buy_rows.iterrows():
            company = row.get("company") or "Unknown"
            date    = str(row.get("report_date") or "")[:10]
            firm    = row.get("securities_firm") or ""
            upside  = row.get("upside")
            thesis  = (row.get("thesis") or "").strip()[:400]
            up_str  = f"  ·  upside {upside:.1f}%" if pd.notna(upside) else ""
            label   = f"{company}  ·  {date}  ·  {firm}{up_str}"
            with st.expander(label):
                st.write(thesis or "*(no thesis text)*")


# ---------------------------------------------------------------------------
# Tab 6 – Company Detail
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

    # ── 왜 매수인가? ──────────────────────────────────────────────────────────
    st.divider()
    st.subheader("🧭 왜 매수인가?")

    buy_rows_macro = (
        cdf[cdf["rating_normalized"] == "BUY"]
        .dropna(subset=["thesis"])
        .sort_values("report_date", ascending=False)
        .head(5)
    )
    combined_thesis = " ".join(buy_rows_macro["thesis"].tolist())
    sector_val = (
        cdf["sector"].dropna().mode().iloc[0]
        if cdf["sector"].notna().any() else None
    )
    macro = explain_buy_reason(selected, sector_val, combined_thesis)

    if macro["confidence"] == "low":
        st.info("매크로 연결고리를 찾지 못했습니다")
    else:
        # Chain — coloured boxes with arrows
        chain_parts = [p.strip() for p in macro["chain"].split("→")]
        box_colors = ["#1565C0", "#2E7D32", "#6A1B9A"]
        boxes = []
        for part, color in zip(chain_parts, box_colors):
            boxes.append(
                f'<span style="background:{color};color:#fff;padding:4px 12px;'
                f'border-radius:4px;font-weight:bold;font-size:14px">{part}</span>'
            )
        chain_html = (
            ' <span style="color:#9E9E9E;font-size:18px;vertical-align:middle">→</span> '
            .join(boxes)
        )
        st.markdown(chain_html, unsafe_allow_html=True)
        st.write("")

        # Theme badges
        if macro["themes"]:
            badges = []
            for t in macro["themes"]:
                color = THEME_COLORS.get(t, _DEFAULT_BADGE_COLOR)
                badges.append(
                    f'<span style="background:{color};color:#fff;padding:2px 10px;'
                    f'border-radius:12px;font-size:13px;margin-right:4px">{t}</span>'
                )
            st.markdown("**매크로 테마** &nbsp; " + "".join(badges), unsafe_allow_html=True)

        # Matched keywords
        if macro["keywords"]:
            kw_md = "  ".join(f"`{kw}`" for kw in macro["keywords"])
            st.markdown("**핵심 키워드** &nbsp; " + kw_md)

        # Summary
        st.info(macro["summary"])

    st.divider()

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


# ---------------------------------------------------------------------------
# Tab 7 – Market Intelligence (cached helpers + sub-tab renderers)
# ---------------------------------------------------------------------------

_TIER_COLORS = {
    "🔥급상승": "#D32F2F",
    "📈상승":   "#F57C00",
    "➡️유지":   "#1976D2",
    "📉하락":   "#9E9E9E",
}


@st.cache_data(ttl=600, show_spinner=False)
def _c_momentum(df: pd.DataFrame) -> pd.DataFrame:
    return get_theme_momentum(df)


@st.cache_data(ttl=600, show_spinner=False)
def _c_overheat(df: pd.DataFrame) -> pd.DataFrame:
    return get_theme_overheat(df)


@st.cache_data(ttl=600, show_spinner=False)
def _c_network(df: pd.DataFrame) -> dict:
    return get_theme_network(df)


@st.cache_data(ttl=600, show_spinner=False)
def _c_new_themes(df: pd.DataFrame) -> list:
    return detect_new_themes(df)


@st.cache_data(ttl=600, show_spinner=False)
def _c_analyst_scores(df: pd.DataFrame) -> pd.DataFrame:
    return get_analyst_scores(df)


@st.cache_data(ttl=3600, show_spinner=False)
def _c_weekly_report(df: pd.DataFrame) -> dict:
    return generate_weekly_report(df)


def _build_network_figure(network: dict) -> go.Figure:
    nodes = network["nodes"]
    edges = network["edges"]
    if not nodes:
        return go.Figure()

    n      = len(nodes)
    angles = [2 * math.pi * i / n for i in range(n)]
    pos    = {nd["id"]: (math.cos(a), math.sin(a)) for nd, a in zip(nodes, angles)}

    fig = go.Figure()
    for edge in edges:
        x0, y0 = pos.get(edge["source"], (0, 0))
        x1, y1 = pos.get(edge["target"], (0, 0))
        fig.add_trace(go.Scatter(
            x=[x0, x1, None], y=[y0, y1, None],
            mode="lines",
            line=dict(width=max(1, edge["weight"] // 3), color="rgba(160,160,160,0.45)"),
            hoverinfo="none", showlegend=False,
        ))

    fig.add_trace(go.Scatter(
        x=[pos[nd["id"]][0] for nd in nodes],
        y=[pos[nd["id"]][1] for nd in nodes],
        mode="markers+text",
        text=[nd["id"] for nd in nodes],
        textposition="top center",
        textfont=dict(size=11),
        marker=dict(
            size=[max(20, min(60, nd["count"] * 3)) for nd in nodes],
            color=[_TIER_COLORS.get(nd.get("tier", "➡️유지"), "#1976D2") for nd in nodes],
            line=dict(width=2, color="white"),
        ),
        hovertext=[
            f"{nd['id']}<br>리포트: {nd['count']}<br>{nd.get('tier', '')}"
            for nd in nodes
        ],
        hoverinfo="text",
        showlegend=False,
    ))

    fig.update_layout(
        title="테마 연관관계 네트워크",
        height=520,
        margin=dict(l=20, r=20, t=50, b=20),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-1.6, 1.6]),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-1.6, 1.6]),
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def _render_mi_momentum(df: pd.DataFrame) -> None:
    momentum = _c_momentum(df)
    overheat = _c_overheat(df)

    if momentum.empty:
        st.info("모멘텀 분석에 필요한 날짜 데이터가 부족합니다.")
        return

    # Total theme counts for bubble size
    theses_tuple = tuple(df["thesis"].fillna("").tolist())
    theme_lists  = _tag_themes(theses_tuple)
    flat         = [t for tl in theme_lists for t in tl]
    total_counts = pd.Series(flat).value_counts().reset_index()
    total_counts.columns = ["theme", "total"]

    bubble = momentum.merge(total_counts, on="theme", how="left")
    bubble["total"]             = bubble["total"].fillna(1)
    bubble["momentum_display"]  = bubble["momentum_score"].fillna(5.0)

    fig_bub = px.scatter(
        bubble,
        x="recent", y="momentum_display",
        size="total", color="tier",
        color_discrete_map=_TIER_COLORS,
        hover_name="theme",
        hover_data={"recent": True, "prev": True, "total": True,
                    "momentum_display": False},
        size_max=60,
        title="테마 모멘텀 버블차트  (x: 최근 2주 언급수 · y: 모멘텀 배율)",
        labels={
            "recent": "최근 2주 언급 수",
            "momentum_display": "모멘텀 (×배)",
            "tier": "구분", "total": "전체 리포트",
        },
    )
    fig_bub.add_hline(y=1.0, line_dash="dash", line_color="gray",
                      annotation_text="기준선 (1×)", annotation_position="bottom right")
    st.plotly_chart(fig_bub, use_container_width=True)

    col_m, col_h = st.columns(2)
    with col_m:
        st.subheader("모멘텀 순위")
        st.dataframe(
            momentum.rename(columns={
                "theme": "테마", "tier": "구분",
                "recent": "최근 2주", "prev": "이전 2주",
                "momentum_score": "모멘텀(×)",
            }),
            use_container_width=True, hide_index=True,
        )
    with col_h:
        st.subheader("과열도")
        if overheat.empty:
            st.info("주간 데이터가 부족합니다.")
        else:
            st.dataframe(
                overheat.rename(columns={
                    "theme": "테마", "overheat": "과열도",
                    "avg_weekly": "주평균", "current_week": "이번주",
                    "z_score": "Z-score",
                }),
                use_container_width=True, hide_index=True,
            )


def _render_mi_network(df: pd.DataFrame) -> None:
    network = _c_network(df)
    if not network["nodes"]:
        st.info("네트워크 분석에 필요한 데이터가 부족합니다.")
        return

    st.plotly_chart(_build_network_figure(network), use_container_width=True)

    st.subheader("연관 테마 TOP 5")
    if network["edges"]:
        edges_df = (
            pd.DataFrame(network["edges"])
            .sort_values("weight", ascending=False)
            .head(5)
            .rename(columns={"source": "테마 A", "target": "테마 B", "weight": "공동 출현"})
        )
        st.dataframe(edges_df, use_container_width=True, hide_index=True)
    else:
        st.caption("공동 출현 2회 이상인 테마 쌍 없음")


def _render_mi_analyst(df: pd.DataFrame) -> None:
    all_sectors = sorted(df["sector"].dropna().unique().tolist()) if not df.empty else []
    sel = st.selectbox("섹터 필터", ["전체"] + all_sectors, key="mi_analyst_sector")
    work = df[df["sector"] == sel].copy() if sel != "전체" else df.copy()

    analyst_df = _c_analyst_scores(work)
    if analyst_df.empty:
        st.info("애널리스트 데이터가 없습니다 (애널리스트명 + 최소 2건 필요).")
        return

    st.subheader("애널리스트 신뢰도 TOP 20")
    st.dataframe(
        analyst_df.head(20).rename(columns={
            "analyst": "애널리스트", "firm": "증권사",
            "coverage": "커버 종목", "consistency": "반복커버(%)",
            "bullish_ratio": "Buy비율(%)", "avg_upside": "평균업사이드(%)",
            "reliability_score": "신뢰도점수",
        }),
        use_container_width=True, hide_index=True,
    )

    firm_agg = (
        analyst_df.groupby("firm")["reliability_score"]
        .mean().reset_index()
        .sort_values("reliability_score", ascending=True)
        .tail(10)
    )
    fig_f = px.bar(
        firm_agg, x="reliability_score", y="firm",
        orientation="h", color="reliability_score",
        color_continuous_scale="Blues",
        title="증권사별 평균 애널리스트 신뢰도 (상위 10)",
        labels={"reliability_score": "평균 신뢰도", "firm": ""},
        text_auto=".1f",
    )
    fig_f.update_layout(coloraxis_showscale=False, margin=dict(l=160))
    st.plotly_chart(fig_f, use_container_width=True)


def _render_mi_new_themes(df: pd.DataFrame) -> None:
    new_themes = _c_new_themes(df)
    if not new_themes:
        st.success("최근 7일간 급부상 테마 감지 없음 (기준: 5× 이상 + 3건 이상)")
        return

    st.caption("최근 7일 기준 · 이전 30일 대비 5× 이상 급증 · 3건 이상 언급")
    cols = st.columns(2)
    for i, t in enumerate(new_themes):
        kw        = t["keywords"][0] if t["keywords"] else "?"
        ratio_str = f"{t['surge_ratio']}×" if t["surge_ratio"] else "신규 등장"
        companies = ", ".join(t["sample_companies"]) if t["sample_companies"] else "—"
        first     = t["first_seen"] or "—"
        with cols[i % 2]:
            with st.container(border=True):
                st.markdown(f"**{kw}**")
                c1, c2 = st.columns(2)
                c1.metric("급증 배율", ratio_str)
                c2.metric("언급 건수", t["count"])
                st.caption(f"첫 등장: {first}")
                st.caption(f"관련 종목: {companies}")


def _run_weekly_report(df: pd.DataFrame) -> None:
    with st.spinner("Claude Haiku 분석 중..."):
        st.session_state["weekly_report"] = _c_weekly_report(df)
        st.session_state["weekly_report_time"] = datetime.now()


def _render_mi_weekly(df: pd.DataFrame) -> None:
    st.subheader("📰 주간 시장 리포트")
    st.caption("최근 7일 증권사 리포트를 Claude Haiku가 분석한 주간 요약입니다.")

    report = st.session_state.get("weekly_report")
    report_time: datetime | None = st.session_state.get("weekly_report_time")

    stale = report is None or (
        report_time is not None and datetime.now() - report_time > timedelta(hours=24)
    )

    if stale:
        if st.button("🔄 리포트 생성", key="btn_weekly_report", type="primary"):
            _run_weekly_report(df)
            st.rerun()
        st.caption("생성 비용 ≈ $0.007 (약 10원)")
    else:
        ts = report_time.strftime("%Y-%m-%d %H:%M") if report_time else ""
        st.success(f"✅ 오늘 리포트가 이미 생성되었습니다")
        if ts:
            st.caption(f"마지막 생성: {ts}")
        if st.button("🔄 강제 재생성", key="btn_weekly_force", type="secondary"):
            _run_weekly_report(df)
            st.rerun()
        st.caption("생성 비용 ≈ $0.007 (약 10원)")

    report = st.session_state.get("weekly_report")
    if report is None:
        st.info("버튼을 눌러 리포트를 생성하세요.")
        return

    if report.get("fallback"):
        st.warning("LLM 미사용 — 키워드 빈도 기반 결과입니다.")

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("#### 🔥 핫 테마 TOP 5")
        hot_themes = report.get("hot_themes") or []
        for theme in hot_themes:
            st.markdown(
                f'<span style="background:#D32F2F;color:#fff;padding:3px 10px;'
                f'border-radius:12px;font-size:13px;margin-right:4px">{theme}</span>',
                unsafe_allow_html=True,
            )
        st.markdown("")

        why_hot = report.get("why_hot") or {}
        if why_hot:
            with st.expander("왜 핫한가?", expanded=False):
                for theme, reason in why_hot.items():
                    st.markdown(f"**{theme}**")
                    st.caption(reason)

        rotation = report.get("rotation") or "-"
        st.markdown("#### 🔄 테마 로테이션")
        st.markdown(
            f'<div style="font-size:15px;padding:8px 12px;background:#1E1E2E;'
            f'border-radius:8px;color:#E0E0E0">{rotation}</div>',
            unsafe_allow_html=True,
        )

    with col_right:
        consensus = report.get("consensus_variables") or []
        st.markdown("#### 📌 공통 핵심 변수")
        if consensus:
            for var in consensus:
                st.markdown(f"- {var}")
        else:
            st.caption("(없음)")

        market_phase = report.get("market_phase") or "-"
        st.markdown("#### 🌐 시장 국면")
        st.info(market_phase)

        next_watch = report.get("next_watch") or []
        st.markdown("#### 👀 다음 주 주목 포인트")
        if next_watch:
            for item in next_watch:
                st.markdown(f"- {item}")
        else:
            st.caption("(없음)")

    st.divider()
    lineage = report.get("theme_lineage") or "-"
    st.markdown("#### 🧬 테마 계보")
    styled = lineage.replace("→", ' <span style="color:#FF7043;font-weight:bold">→</span> ')
    st.markdown(
        f'<div style="font-size:14px;padding:10px 16px;background:#1A237E22;'
        f'border-left:4px solid #3F51B5;border-radius:4px">{styled}</div>',
        unsafe_allow_html=True,
    )


def render_market_intelligence_tab(df: pd.DataFrame) -> None:
    st.header("📡 시장 인텔리전스")

    if df.empty or "thesis" not in df.columns:
        st.info("분석할 데이터가 없습니다.")
        return

    sub0, sub1, sub2, sub3, sub4 = st.tabs(
        ["📰 주간 리포트", "🔥 테마 모멘텀", "🕸️ 테마 네트워크", "🏆 애널리스트", "🆕 신규 테마"]
    )
    with sub0:
        _render_mi_weekly(df)
    with sub1:
        _render_mi_momentum(df)
    with sub2:
        _render_mi_network(df)
    with sub3:
        _render_mi_analyst(df)
    with sub4:
        _render_mi_new_themes(df)
