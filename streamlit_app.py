"""Shared research browser for government procurement and consulting actors."""

from __future__ import annotations

from pathlib import Path
import os
import re
from urllib.parse import urlencode
import duckdb
import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "research.duckdb"
APP_TITLE = "政府調達サーチ β"
NO_SELECTION = "指定なし"
CONSULTING_ALL = "すべて"
CONSULTING_BROAD = "広義（周辺領域を含む）"
CONSULTING_STRICT = "狭義（コンサル中核）"
PROCUREMENT_PORTAL_SEARCH_URL = "https://www.p-portal.go.jp/pps-web-biz/UAA01/OAA0101"
MENU_PAGES = ["案件検索", "コンサル検索", "省庁分析", "データ概要", "About"]
MINISTRY_DISPLAY_ORDER = [
    "内閣官房",
    "内閣法制局",
    "人事院",
    "内閣府",
    "デジタル庁",
    "復興庁",
    "総務省",
    "法務省",
    "外務省",
    "財務省",
    "文部科学省",
    "厚生労働省",
    "農林水産省",
    "経済産業省",
    "国土交通省",
    "環境省",
    "防衛省",
    "警察庁",
    "金融庁",
    "消費者庁",
    "こども家庭庁",
    "消防庁",
    "国税庁",
    "文化庁",
    "林野庁",
    "水産庁",
    "特許庁",
    "観光庁",
    "気象庁",
    "海上保安庁",
    "運輸安全委員会",
    "会計検査院",
    "衆議院",
    "参議院",
    "国立国会図書館",
    "最高裁判所",
    "検察庁",
    "公正取引委員会",
    "個人情報保護委員会",
    "公害等調整委員会",
    "中央労働委員会",
    "カジノ管理委員会",
    "公安調査庁",
    "宮内庁",
    "原子力安全庁",
]
BIDDING_METHOD_DISPLAY_ORDER = [
    "一般競争入札・最低価格",
    "一般競争入札・総合評価",
    "一般競争入札・複数落札",
    "一般競争入札・最高価格",
    "指名競争入札・最低価格",
    "指名競争入札・総合評価",
    "指名競争入札・複数落札",
    "指名競争入札・最高価格",
    "随意契約・複数業者",
    "随意契約・オープンカウンタ",
    "随意契約・特定業者",
    "随意契約・公募型プロポーザル",
    "随意契約・複数業者・少額",
    "随意契約・オープンカウンタ・少額",
    "随意契約・特定業者・少額",
    "随意契約・公募型プロポーザル・少額",
]

st.set_page_config(page_title=APP_TITLE, page_icon="🏛️", layout="wide")


def database_url() -> str | None:
    if value := os.getenv("DATABASE_URL"):
        return value
    try:
        return st.secrets.get("DATABASE_URL")
    except FileNotFoundError:
        return None


def database_schema() -> str:
    if value := os.getenv("DB_SCHEMA"):
        return value
    try:
        return st.secrets.get("DB_SCHEMA", "procurement")
    except FileNotFoundError:
        return "procurement"


def contact_text() -> str:
    if value := os.getenv("CONTACT_TEXT"):
        return value
    try:
        return st.secrets.get("CONTACT_TEXT", "共同研究チームまでご連絡ください。")
    except FileNotFoundError:
        return "共同研究チームまでご連絡ください。"


@st.cache_resource
def duckdb_connection():
    return duckdb.connect(str(DB_PATH), read_only=True)


def postgres_connection():
    import psycopg

    url = database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    try:
        connection = psycopg.connect(url, autocommit=True, prepare_threshold=None)
    except TypeError:
        connection = psycopg.connect(url, autocommit=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('search_path', %s, false)", (f"{database_schema()}, public",))
    return connection


def query(sql: str, params: list | None = None) -> pd.DataFrame:
    if not database_url():
        connection = duckdb_connection()
        result = connection.execute(sql, params or [])
        if result is None:
            return pd.DataFrame()
        return result.fetchdf()
    postgres_sql = sql.replace("?", "%s")
    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(postgres_sql, params or [])
            rows = cursor.fetchall()
            return pd.DataFrame(rows, columns=[column.name for column in cursor.description])


def query_param(name: str) -> str:
    value = st.query_params.get(name, "")
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value) if value is not None else ""


def sort_ministries(names: list[str]) -> list[str]:
    order = {name: index for index, name in enumerate(MINISTRY_DISPLAY_ORDER)}
    return sorted(names, key=lambda name: (order.get(name, 10_000), name))


def sort_ordering_bodies(rows: pd.DataFrame) -> list[str]:
    """Sort ordering bodies by ministry display order, then by body name."""
    if rows.empty:
        return []
    order = {name: index for index, name in enumerate(MINISTRY_DISPLAY_ORDER)}
    sorted_rows = rows.assign(
        ministry_order=rows["ministry_name"].map(lambda name: order.get(name, 10_000))
    ).sort_values(["ministry_order", "ministry_name", "ordering_body_name"], na_position="last")
    return sorted_rows["ordering_body_name"].dropna().tolist()


def sort_bidding_methods(names: list[str]) -> list[str]:
    order = {name: index for index, name in enumerate(BIDDING_METHOD_DISPLAY_ORDER)}
    return sorted(names, key=lambda name: (order.get(name, 10_000), name))


def with_year_label_index(df: pd.DataFrame, year_column: str = "年度") -> pd.DataFrame:
    """Use year labels as strings so charts do not render fiscal years like 2,014."""
    chart_df = df.copy()
    if year_column in chart_df.columns:
        chart_df[year_column] = chart_df[year_column].astype(str)
        chart_df = chart_df.set_index(year_column)
    return chart_df


def row_value(row: pd.Series, name: str, position: int, default: object = 0) -> object:
    """Read an aggregate value by name, falling back to position for driver quirks."""
    if name in row.index:
        return row[name]
    if position < len(row):
        return row.iloc[position]
    return default


def first_column_values(df: pd.DataFrame) -> list[str]:
    if df.empty:
        return []
    return df.iloc[:, 0].dropna().astype(str).tolist()


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique_values.append(value)
    return unique_values


def order_bidding_method_rows(df: pd.DataFrame, method_column: str = "契約方式・落札方式") -> pd.DataFrame:
    if df.empty or method_column not in df.columns:
        return df
    order = {name: index for index, name in enumerate(BIDDING_METHOD_DISPLAY_ORDER)}
    return df.assign(
        _method_order=df[method_column].map(lambda name: order.get(name, 10_000))
    ).sort_values(["_method_order", method_column]).drop(columns=["_method_order"])


def show_footer() -> None:
    st.divider()
    st.caption(
        "© 2026 Government Procurement Search β project. "
        "出典：調達ポータル。本サイトは非公式の研究用試作版です。"
    )


def procurement_portal_url(record_id: str | None = None) -> str:
    return PROCUREMENT_PORTAL_SEARCH_URL


def app_search_url(vendor_name: str | None) -> str:
    return "./?" + urlencode({"page": "案件検索", "vendor": vendor_name or ""})


def safe_filename_part(value: object, max_length: int = 40) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r'[\\/:*?"<>|\s]+', "_", text)
    text = re.sub(r"_+", "_", text).strip("._")
    return text[:max_length]


def search_export_filename(
    fiscal_year_range: tuple[int, int],
    keyword: str,
    vendor_pick: str,
    vendor_text: str,
    body_pick: str,
    bidding_method: str,
    consulting: str,
    min_amount: int,
) -> str:
    parts = ["procurement", f"{fiscal_year_range[0]}-{fiscal_year_range[1]}"]
    if consulting != CONSULTING_ALL:
        parts.append(safe_filename_part(consulting, 20))
    vendor_label = vendor_text.strip() or (vendor_pick if vendor_pick != NO_SELECTION else "")
    if vendor_label:
        parts.append("vendor-" + safe_filename_part(vendor_label))
    if body_pick != NO_SELECTION:
        parts.append("body-" + safe_filename_part(body_pick))
    if bidding_method != NO_SELECTION:
        parts.append("method-" + safe_filename_part(bidding_method))
    if keyword.strip():
        parts.append("kw-" + safe_filename_part(keyword))
    if min_amount:
        parts.append(f"min{int(min_amount)}man")
    filename = "_".join(part for part in parts if part)
    return f"{filename[:180]}.csv"


def add_portal_links(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "record_id" not in df.columns:
        return df
    linked = df.copy()
    linked.insert(1, "外部", linked["record_id"].map(procurement_portal_url))
    linked.insert(2, "調達案件番号", linked["record_id"])
    return linked


def add_vendor_search_links(df: pd.DataFrame, vendor_column: str) -> pd.DataFrame:
    if df.empty or vendor_column not in df.columns:
        return df
    linked = df.copy()
    linked.insert(0, "案件検索", linked[vendor_column].map(app_search_url))
    return linked


def hide_internal_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop(columns=["record_id"], errors="ignore")


def require_database() -> None:
    if not database_url() and not DB_PATH.exists():
        st.error("研究DBがありません。`python code/build_research_db.py` を実行してください。")
        st.stop()


@st.cache_data(show_spinner=False)
def search_options() -> tuple[list[str], list[str], list[str]]:
    consulting_vendors = first_column_values(query(
        """
        SELECT vendor_name_canonical
        FROM procurements
        WHERE analysis_included
          AND consulting_flag_broad
          AND COALESCE(vendor_name_canonical, '') <> ''
        GROUP BY vendor_name_canonical
        ORDER BY SUM(award_amount_yen) DESC NULLS LAST, COUNT(*) DESC
        LIMIT 300
        """
    ))
    top_vendors = first_column_values(query(
        """
        SELECT vendor_name_canonical
        FROM procurements
        WHERE analysis_included
          AND COALESCE(vendor_name_canonical, '') <> ''
        GROUP BY vendor_name_canonical
        ORDER BY SUM(award_amount_yen) DESC NULLS LAST, COUNT(*) DESC
        LIMIT 500
        """
    ))
    vendor_candidates = unique_preserve_order([*consulting_vendors, *top_vendors])
    ordering_body_rows = query(
        """
        SELECT ordering_body_name, MIN(ministry_name) AS ministry_name
        FROM procurements
        WHERE analysis_included
          AND COALESCE(ordering_body_name, '') <> ''
        GROUP BY ordering_body_name
        ORDER BY ordering_body_name
        """
    )
    ordering_bodies = sort_ordering_bodies(ordering_body_rows)
    bidding_methods = sort_bidding_methods(
        query(
            """
            SELECT bidding_method_name
            FROM procurements
            WHERE analysis_included
              AND COALESCE(bidding_method_name, '') <> ''
            GROUP BY bidding_method_name
            """
        )["bidding_method_name"].dropna().tolist()
    )
    return [NO_SELECTION, *vendor_candidates], [NO_SELECTION, *ordering_bodies], [NO_SELECTION, *bidding_methods]


@st.cache_data(show_spinner=False)
def fiscal_year_range() -> tuple[int, int] | None:
    years = query("SELECT MIN(fiscal_year) AS lo, MAX(fiscal_year) AS hi FROM procurements WHERE analysis_included")
    if years.empty:
        return None
    row = years.iloc[0]
    lo_value = row_value(row, "lo", 0)
    hi_value = row_value(row, "hi", 1)
    if pd.isna(lo_value) or pd.isna(hi_value):
        return None
    return int(lo_value), int(hi_value)


require_database()
st.title(APP_TITLE)
st.caption("出典：調達ポータル　オープンソースデータを検索できます")
st.sidebar.caption("DB: Supabase PostgreSQL" if database_url() else "DB: Local DuckDB")

requested_page = query_param("page")
page_index = MENU_PAGES.index(requested_page) if requested_page in MENU_PAGES else 0
page = st.sidebar.radio("表示", MENU_PAGES, index=page_index)

if page == "案件検索":
    vendor_query = query_param("vendor")
    vendor_options, body_options, bidding_method_options = search_options()
    year_range = fiscal_year_range()
    if year_range is None:
        st.error(
            "調達データを読み取れませんでした。SupabaseのRLSポリシーで "
            "`procurement_reader` にSELECT権限があるか確認してください。"
        )
        st.stop()
    lo, hi = year_range
    with st.form("procurement_search_form"):
        c1, c2, c3 = st.columns(3)
        fy = c1.slider("年度", lo, hi, (lo, hi))
        keyword = c2.text_input("案件名キーワード")
        consulting = c3.selectbox("コンサル認定", [CONSULTING_ALL, CONSULTING_BROAD, CONSULTING_STRICT])
        with c3.expander("認定基準の注釈"):
            st.markdown(
                "- **広義**：コンサル会社・調査会社・シンクタンク等に加え、システム導入支援や調査分析など周辺領域を含めます。\n"
                "- **狭義**：戦略・業務改革・政策調査など、コンサルティング中核に近い案件・受注者を優先して抽出します。\n"
                "- いずれも機械的な暫定分類なので、共同研究の過程で見直す前提です。"
            )
        c4, c5, c6, c7 = st.columns(4)
        vendor_pick = c4.selectbox("受注者名（候補）", vendor_options)
        vendor_text = c5.text_input(
            "受注者名（自由入力）",
            value=vendor_query,
            placeholder="候補にない場合だけ入力",
            help="候補を選んだ場合は候補が優先されます。自由入力で探す場合は、受注者名（候補）を「指定なし」にしてください。",
            key=f"vendor_text_{vendor_query}",
        )
        body_pick = c6.selectbox("発注機関名", body_options)
        min_amount = c7.number_input("最低落札額（万円）", min_value=0, value=0, step=100)
        bidding_method_pick = st.selectbox("契約方式・落札方式", bidding_method_options)
        submitted = st.form_submit_button("検索", type="primary")

    search_requested = submitted or bool(vendor_query.strip())
    vendor_filter_label = ""
    if vendor_pick != NO_SELECTION:
        vendor_filter_label = vendor_pick
        if vendor_text.strip():
            st.caption("受注者名は候補選択を優先しています。自由入力で検索する場合は、受注者名（候補）を「指定なし」にしてください。")
    elif vendor_text.strip():
        vendor_filter_label = vendor_text.strip()

    if not search_requested:
        st.info("検索条件を設定して「検索」を押してください。入力中はDB検索を実行しません。")
    else:
        where = ["analysis_included", "fiscal_year BETWEEN ? AND ?", "award_amount_yen >= ?"]
        params: list = [fy[0], fy[1], int(min_amount * 10_000)]
        if keyword.strip():
            where.append("procurement_title ILIKE ?")
            params.append(f"%{keyword.strip()}%")
        if vendor_pick != NO_SELECTION:
            where.append("vendor_name_canonical = ?")
            params.append(vendor_pick)
        elif vendor_text.strip():
            where.append("vendor_name_canonical ILIKE ?")
            params.append(f"%{vendor_text.strip()}%")
        if body_pick != NO_SELECTION:
            where.append("ordering_body_name = ?")
            params.append(body_pick)
        if bidding_method_pick != NO_SELECTION:
            where.append("bidding_method_name = ?")
            params.append(bidding_method_pick)
        if consulting == CONSULTING_BROAD:
            where.append("consulting_flag_broad")
        elif consulting == CONSULTING_STRICT:
            where.append("consulting_flag_strict")

        predicate = " AND ".join(where)
        total_df = query(f"SELECT COUNT(*) AS n, COALESCE(SUM(award_amount_yen), 0) AS amount FROM procurements WHERE {predicate}", params)
        if total_df.empty:
            total = pd.Series({"n": 0, "amount": 0})
        else:
            total = total_df.iloc[0]
        total_n = int(row_value(total, "n", 0) or 0)
        total_amount = float(row_value(total, "amount", 1) or 0)
        m1, m2 = st.columns(2)
        m1.metric("該当件数", f"{total_n:,}件")
        m2.metric("落札額合計", f"{total_amount / 1e8:,.1f}億円")

        columns = "record_id, fiscal_year, contract_date, procurement_title, ordering_body_name, vendor_name_canonical, award_amount_yen, bidding_method_name, consulting_categories"
        results = query(f"SELECT {columns} FROM procurements WHERE {predicate} ORDER BY contract_date DESC NULLS LAST LIMIT 1000", params)
        results = hide_internal_columns(add_portal_links(results))
        st.dataframe(
            results,
            width="stretch",
            hide_index=True,
            column_config={
                "外部": st.column_config.LinkColumn(
                    "外部",
                    display_text="開く",
                    help="調達ポータルの「調達情報の検索」を開きます。案件番号でヒットしない場合は、案件名・発注機関・年度で検索してください。",
                )
            },
        )
        if total_n > 1000:
            st.caption("画面表示は最新1,000件まで。ダウンロードには全件を含めます。")
        export = query(f"SELECT {columns} FROM procurements WHERE {predicate} ORDER BY contract_date DESC NULLS LAST", params)
        export = add_portal_links(export)
        export_filename = search_export_filename(fy, keyword, vendor_pick, vendor_filter_label, body_pick, bidding_method_pick, consulting, min_amount)
        st.download_button("検索結果をCSVでダウンロード", export.to_csv(index=False).encode("utf-8-sig"), export_filename, "text/csv")

elif page == "コンサル検索":
    name = st.text_input("コンサル名・受注者名を検索")
    actor_summary_sql = """
        SELECT vendor_name_canonical AS canonical_name, COUNT(*) AS procurement_count,
               SUM(award_amount_yen) AS award_amount_yen,
               MIN(fiscal_year) AS first_fiscal_year, MAX(fiscal_year) AS last_fiscal_year
        FROM procurements
        WHERE analysis_included
          AND consulting_flag_broad
          AND COALESCE(vendor_name_canonical, '') <> ''
    """
    if name.strip():
        actors = query(actor_summary_sql + " AND vendor_name_canonical ILIKE ? GROUP BY vendor_name_canonical ORDER BY award_amount_yen DESC LIMIT 100", [f"%{name.strip()}%"])
    else:
        actors = query(actor_summary_sql + " GROUP BY vendor_name_canonical ORDER BY award_amount_yen DESC LIMIT 100")
    actors_display = add_vendor_search_links(actors, "canonical_name")
    st.dataframe(
        actors_display,
        width="stretch",
        hide_index=True,
        column_config={
            "案件検索": st.column_config.LinkColumn(
                "案件検索",
                display_text="開く",
                help="この受注者名を案件検索に入力した状態で開きます。",
            )
        },
    )
    selected = st.selectbox("詳細表示", actors.canonical_name.tolist() if not actors.empty else [])
    if selected:
        summary = query("SELECT COUNT(*) n, SUM(award_amount_yen) amount, COUNT(DISTINCT ordering_body_name) bodies FROM procurements WHERE analysis_included AND consulting_flag_broad AND vendor_name_canonical = ?", [selected]).iloc[0]
        a, b, c = st.columns(3)
        a.metric("落札件数", f"{int(summary['n']):,}件")
        b.metric("落札額", f"{float(summary['amount'] or 0)/1e8:,.1f}億円")
        c.metric("発注機関数", f"{int(summary['bodies']):,}")
        yearly = query("SELECT fiscal_year AS 年度, COUNT(*) AS 件数, SUM(award_amount_yen)/1e8 AS 落札額_億円 FROM procurements WHERE analysis_included AND consulting_flag_broad AND vendor_name_canonical = ? GROUP BY fiscal_year ORDER BY fiscal_year", [selected])
        st.line_chart(with_year_label_index(yearly))
        st.subheader("主要発注機関")
        st.dataframe(query("SELECT ordering_body_name AS 発注機関, COUNT(*) AS 件数, SUM(award_amount_yen) AS 落札額_円 FROM procurements WHERE analysis_included AND consulting_flag_broad AND vendor_name_canonical = ? GROUP BY ordering_body_name ORDER BY 落札額_円 DESC LIMIT 30", [selected]), width="stretch", hide_index=True)

elif page == "省庁分析":
    st.subheader("省庁・発注機関別の傾向")
    ministry_options = sort_ministries(query(
        """
        SELECT ministry_name
        FROM procurements
        WHERE analysis_included AND COALESCE(ministry_name, '') <> ''
        GROUP BY ministry_name
        ORDER BY SUM(award_amount_yen) DESC NULLS LAST, ministry_name
        """
    )["ministry_name"].dropna().tolist())
    ministry = st.selectbox("省庁", ministry_options)
    _, _, bidding_method_options = search_options()
    bidding_method_pick = st.selectbox("契約方式・落札方式", bidding_method_options, key="ministry_bidding_method")
    scope = st.radio("対象", [CONSULTING_ALL, CONSULTING_BROAD, CONSULTING_STRICT], horizontal=True)

    where = ["analysis_included", "ministry_name = ?"]
    params: list = [ministry]
    if bidding_method_pick != NO_SELECTION:
        where.append("bidding_method_name = ?")
        params.append(bidding_method_pick)
    if scope == CONSULTING_BROAD:
        where.append("consulting_flag_broad")
    elif scope == CONSULTING_STRICT:
        where.append("consulting_flag_strict")
    predicate = " AND ".join(where)

    summary = query(
        f"""
        SELECT COUNT(*) AS n,
               COUNT(DISTINCT vendor_name_canonical) AS vendors,
               COUNT(DISTINCT ordering_body_name) AS bodies,
               COALESCE(SUM(award_amount_yen), 0) AS amount,
               SUM(CASE WHEN consulting_flag_broad THEN 1 ELSE 0 END) AS broad_n,
               SUM(CASE WHEN consulting_flag_strict THEN 1 ELSE 0 END) AS strict_n
        FROM procurements
        WHERE {predicate}
        """,
        params,
    ).iloc[0]
    m1, m2, m3, m4 = st.columns(4)
    total_n = int(summary["n"] or 0)
    m1.metric("件数", f"{total_n:,}件")
    m2.metric("受注者", f"{int(summary['vendors'] or 0):,}")
    m3.metric("発注機関", f"{int(summary['bodies'] or 0):,}")
    m4.metric("落札総額", f"{float(summary['amount'] or 0) / 1e8:,.1f}億円")

    if scope == CONSULTING_ALL and total_n:
        c1, c2 = st.columns(2)
        c1.metric("広義コンサル比率", f"{int(summary['broad_n'] or 0) / total_n * 100:.1f}%")
        c2.metric("狭義コンサル比率", f"{int(summary['strict_n'] or 0) / total_n * 100:.1f}%")

    st.subheader("契約方式・落札方式 × 年度")
    st.caption("選択中の省庁・対象区分について、縦軸を契約方式・落札方式、横軸を年度として集計します。")
    matrix_where = ["analysis_included", "ministry_name = ?"]
    matrix_params: list = [ministry]
    if scope == CONSULTING_BROAD:
        matrix_where.append("consulting_flag_broad")
    elif scope == CONSULTING_STRICT:
        matrix_where.append("consulting_flag_strict")
    matrix_predicate = " AND ".join(matrix_where)
    method_year = query(
        f"""
        SELECT COALESCE(bidding_method_name, '不明') AS 契約方式・落札方式,
               fiscal_year AS 年度,
               COUNT(*) AS 件数,
               SUM(award_amount_yen) / 1e8 AS 落札総額_億円
        FROM procurements
        WHERE {matrix_predicate}
        GROUP BY bidding_method_name, fiscal_year
        ORDER BY fiscal_year, bidding_method_name
        """,
        matrix_params,
    )
    if method_year.empty:
        st.info("契約方式・落札方式別の集計対象データがありません。")
    else:
        method_year["年度"] = method_year["年度"].astype(str)
        method_year["落札総額_億円"] = method_year["落札総額_億円"].round(1)
        metric_choice = st.radio("表示指標", ["件数", "落札総額_億円"], horizontal=True, key="method_year_metric")
        method_matrix = method_year.pivot_table(
            index="契約方式・落札方式",
            columns="年度",
            values=metric_choice,
            aggfunc="sum",
            fill_value=0,
        ).reset_index()
        method_matrix = order_bidding_method_rows(method_matrix)
        year_columns = [column for column in method_matrix.columns if column != "契約方式・落札方式"]
        if metric_choice == "件数":
            method_matrix[year_columns] = method_matrix[year_columns].astype(int)
        else:
            method_matrix[year_columns] = method_matrix[year_columns].round(1)
        st.dataframe(method_matrix, width="stretch", hide_index=True)
        chart_source = method_year.pivot_table(
            index="年度",
            columns="契約方式・落札方式",
            values=metric_choice,
            aggfunc="sum",
            fill_value=0,
        ).sort_index()
        st.caption("年度ごとの契約方式・落札方式別の分布です。")
        st.bar_chart(chart_source)

    st.subheader("上位受注者")
    top_vendors = query(
        f"""
        SELECT vendor_name_canonical AS 受注者,
               COUNT(*) AS 件数,
               COUNT(DISTINCT ordering_body_name) AS 発注機関数,
               SUM(award_amount_yen) / 1e8 AS 落札総額_億円,
               AVG(award_amount_yen) / 1e8 AS 平均_億円,
               MAX(award_amount_yen) / 1e8 AS 最大_億円,
               MIN(award_amount_yen) / 1e8 AS 最小_億円,
               SUM(CASE WHEN consulting_flag_broad THEN 1 ELSE 0 END) AS 広義コンサル件数,
               SUM(CASE WHEN consulting_flag_strict THEN 1 ELSE 0 END) AS 狭義コンサル件数
        FROM procurements
        WHERE {predicate}
          AND COALESCE(vendor_name_canonical, '') <> ''
        GROUP BY vendor_name_canonical
        ORDER BY SUM(award_amount_yen) DESC NULLS LAST
        LIMIT 50
        """,
        params,
    )
    if not top_vendors.empty:
        for column in ["落札総額_億円", "平均_億円", "最大_億円", "最小_億円"]:
            top_vendors[column] = top_vendors[column].round(1)
    top_vendors_display = add_vendor_search_links(top_vendors, "受注者")
    st.dataframe(
        top_vendors_display,
        width="stretch",
        hide_index=True,
        column_config={
            "案件検索": st.column_config.LinkColumn(
                "案件検索",
                display_text="開く",
                help="この受注者名を案件検索に入力した状態で開きます。",
            )
        },
    )

    st.subheader("年度推移")
    yearly_ministry = query(
        f"""
        SELECT fiscal_year AS 年度,
               COUNT(*) AS 件数,
               COUNT(DISTINCT vendor_name_canonical) AS 受注者,
               SUM(award_amount_yen) / 1e8 AS 落札総額_億円
        FROM procurements
        WHERE {predicate}
        GROUP BY fiscal_year
        ORDER BY fiscal_year
        """,
        params,
    )
    if not yearly_ministry.empty:
        yearly_ministry["落札総額_億円"] = yearly_ministry["落札総額_億円"].round(1)
        st.line_chart(with_year_label_index(yearly_ministry)[["件数", "受注者"]])
    yearly_display = yearly_ministry.copy()
    if not yearly_display.empty:
        yearly_display["年度"] = yearly_display["年度"].astype(str)
    st.dataframe(yearly_display, width="stretch", hide_index=True)

    st.subheader("発注機関別")
    bodies = query(
        f"""
        SELECT ordering_body_name AS 発注機関,
               COUNT(*) AS 件数,
               COUNT(DISTINCT vendor_name_canonical) AS 受注者,
               SUM(award_amount_yen) / 1e8 AS 落札総額_億円
        FROM procurements
        WHERE {predicate}
          AND COALESCE(ordering_body_name, '') <> ''
        GROUP BY ordering_body_name
        ORDER BY SUM(award_amount_yen) DESC NULLS LAST
        LIMIT 50
        """,
        params,
    )
    if not bodies.empty:
        bodies["落札総額_億円"] = bodies["落札総額_億円"].round(1)
    st.dataframe(bodies, width="stretch", hide_index=True)

elif page == "データ概要":
    st.subheader("区分別サマリー")
    overview = query(
        """
        SELECT '政府調達全体' AS 区分,
               COUNT(*) AS 件数,
               COUNT(DISTINCT vendor_name_canonical) AS 受注者,
               SUM(award_amount_yen) / 1e8 AS 落札総額_億円,
               MIN(fiscal_year) AS 開始年度,
               MAX(fiscal_year) AS 終了年度
        FROM procurements
        WHERE analysis_included
        UNION ALL
        SELECT 'コンサル（広義）' AS 区分,
               COUNT(*) AS 件数,
               COUNT(DISTINCT vendor_name_canonical) AS 受注者,
               SUM(award_amount_yen) / 1e8 AS 落札総額_億円,
               MIN(fiscal_year) AS 開始年度,
               MAX(fiscal_year) AS 終了年度
        FROM procurements
        WHERE analysis_included AND consulting_flag_broad
        UNION ALL
        SELECT 'コンサル（狭義）' AS 区分,
               COUNT(*) AS 件数,
               COUNT(DISTINCT vendor_name_canonical) AS 受注者,
               SUM(award_amount_yen) / 1e8 AS 落札総額_億円,
               MIN(fiscal_year) AS 開始年度,
               MAX(fiscal_year) AS 終了年度
        FROM procurements
        WHERE analysis_included AND consulting_flag_strict
        """
    )
    overview["落札総額_億円"] = overview["落札総額_億円"].round(1)
    st.dataframe(overview, width="stretch", hide_index=True)

    st.subheader("年度別比較")
    yearly = query(
        """
        SELECT fiscal_year AS 年度,
               '政府調達全体' AS 区分,
               COUNT(*) AS 件数,
               COUNT(DISTINCT vendor_name_canonical) AS 受注者,
               SUM(award_amount_yen) / 1e8 AS 落札総額_億円
        FROM procurements
        WHERE analysis_included
        GROUP BY fiscal_year
        UNION ALL
        SELECT fiscal_year AS 年度,
               'コンサル（広義）' AS 区分,
               COUNT(*) AS 件数,
               COUNT(DISTINCT vendor_name_canonical) AS 受注者,
               SUM(award_amount_yen) / 1e8 AS 落札総額_億円
        FROM procurements
        WHERE analysis_included AND consulting_flag_broad
        GROUP BY fiscal_year
        UNION ALL
        SELECT fiscal_year AS 年度,
               'コンサル（狭義）' AS 区分,
               COUNT(*) AS 件数,
               COUNT(DISTINCT vendor_name_canonical) AS 受注者,
               SUM(award_amount_yen) / 1e8 AS 落札総額_億円
        FROM procurements
        WHERE analysis_included AND consulting_flag_strict
        GROUP BY fiscal_year
        ORDER BY 年度 DESC, 区分
        """
    )
    yearly["落札総額_億円"] = yearly["落札総額_億円"].round(1)
    yearly["年度"] = yearly["年度"].astype(str)
    st.dataframe(yearly, width="stretch", hide_index=True)

else:
    st.subheader("About")
    st.markdown(
        """
        **政府調達サーチ β** は、調達ポータル由来の政府調達データを検索・分析するための研究用試作版です。

        ### データについて

        - 出典：調達ポータル
        - 対象：調達ポータルで公開されている落札実績データをもとにした研究用データベース
        - 目的：政府調達における受注者、発注機関、省庁、契約方式の傾向を共同研究で確認すること
        - 注意：原データの更新、名寄せ、分類、重複判定には暫定処理を含みます

        ### コンサル認定について

        - **広義（周辺領域を含む）**：コンサル会社・調査会社・シンクタンク等に加え、システム導入支援、調査分析、政策支援など周辺領域を含めた暫定分類です。
        - **狭義（コンサル中核）**：戦略、業務改革、政策調査、制度設計など、コンサルティング中核に近い案件・受注者を優先した暫定分類です。
        - いずれも機械的な分類を含むため、共同研究の過程で見直す前提です。

        ### 利用上の注意

        - 本サイトは非公式の研究用試作版であり、調達ポータルまたは各府省の公式サービスではありません。
        - 正確な原情報は、調達ポータルおよび各調達機関の公表情報をご確認ください。
        - 金額、年度、受注者名、発注機関名、分類結果には、原データ由来または加工過程由来の誤差・表記揺れが含まれる可能性があります。
        - CSV出力データを引用・再利用する場合は、出典が調達ポータルであること、本アプリの分類が暫定であることを明記してください。
        """
    )
    st.markdown("### お問い合わせ・データ修正")
    st.info(
        "データの誤り、名寄せの問題、コンサル分類の修正提案、その他の確認事項がある場合は、"
        f"{contact_text()}"
    )
    st.markdown(
        """
        ### ライセンス・クレジット

        - データ出典：調達ポータル
        - アプリ：政府調達サーチ β project
        - 本アプリで付与した分類・名寄せ・集計ロジックは研究用の暫定成果です。
        """
    )

show_footer()
