"""Stable server-rendered web app for government procurement search."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from html import escape
import csv
import io
import os
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
import psycopg
from psycopg.rows import dict_row


APP_TITLE = "政府調達検索β"
PROCUREMENT_PORTAL_SEARCH_URL = "https://www.p-portal.go.jp/pps-web-biz/UAA01/OAA0101"
SEARCH_RESULT_LIMIT = 100
NO_SELECTION = "指定なし"
CONSULTING_ALL = "すべて"
CONSULTING_BROAD = "広義（周辺領域を含む）"
CONSULTING_STRICT = "狭義（コンサル中核）"

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


app = FastAPI(title=APP_TITLE)


def database_url() -> str:
    value = os.getenv("DATABASE_URL", "").strip().lstrip("\ufeff")
    if not value:
        raise RuntimeError("DATABASE_URL is not configured")
    return value


def database_schema() -> str:
    return os.getenv("DB_SCHEMA", "procurement").strip() or "procurement"


@contextmanager
def db_connection():
    connection = psycopg.connect(
        database_url(),
        autocommit=True,
        connect_timeout=10,
        prepare_threshold=None,
        row_factory=dict_row,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('search_path', %s, false)", (f"{database_schema()}, public",))
            cursor.execute("SET statement_timeout TO '30s'")
        yield connection
    finally:
        connection.close()


def fetch_all(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or [])
            return list(cursor.fetchall())


def fetch_one(sql: str, params: list[Any] | None = None) -> dict[str, Any] | None:
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


def sort_ministries(names: list[str]) -> list[str]:
    order = {name: index for index, name in enumerate(MINISTRY_DISPLAY_ORDER)}
    return sorted(names, key=lambda name: (order.get(name, 10_000), name))


def sort_bidding_methods(names: list[str]) -> list[str]:
    order = {name: index for index, name in enumerate(BIDDING_METHOD_DISPLAY_ORDER)}
    return sorted(names, key=lambda name: (order.get(name, 10_000), name))


@dataclass
class SearchOptions:
    vendors: list[str]
    bodies: list[str]
    bidding_methods: list[str]
    year_min: int
    year_max: int


def load_options() -> SearchOptions:
    years = fetch_one("SELECT MIN(fiscal_year) AS lo, MAX(fiscal_year) AS hi FROM procurements WHERE analysis_included")
    vendors = [
        row["vendor_name_canonical"]
        for row in fetch_all(
            """
            SELECT vendor_name_canonical
            FROM procurements
            WHERE analysis_included
              AND consulting_flag_broad
              AND COALESCE(vendor_name_canonical, '') <> ''
            GROUP BY vendor_name_canonical
            ORDER BY SUM(award_amount_yen) DESC NULLS LAST, COUNT(*) DESC
            LIMIT 120
            """
        )
    ]
    bodies = [
        row["ordering_body_name"]
        for row in fetch_all(
            """
            SELECT ordering_body_name, MIN(ministry_name) AS ministry_name
            FROM procurements
            WHERE analysis_included
              AND COALESCE(ordering_body_name, '') <> ''
            GROUP BY ordering_body_name
            ORDER BY COUNT(*) DESC, SUM(award_amount_yen) DESC NULLS LAST
            LIMIT 150
            """
        )
    ]
    methods = [
        row["bidding_method_name"]
        for row in fetch_all(
            """
            SELECT bidding_method_name
            FROM procurements
            WHERE analysis_included
              AND COALESCE(bidding_method_name, '') <> ''
            GROUP BY bidding_method_name
            """
        )
    ]
    return SearchOptions(
        vendors=[NO_SELECTION, *vendors],
        bodies=[NO_SELECTION, *sort_ministries(bodies)],
        bidding_methods=[NO_SELECTION, *sort_bidding_methods(methods)],
        year_min=int(years["lo"] or 2013) if years else 2013,
        year_max=int(years["hi"] or 2026) if years else 2026,
    )


def yen_oku(value: Any) -> str:
    amount = float(value or 0)
    return f"{amount / 100_000_000:,.1f}億円"


def portal_url(record_id: Any) -> str:
    return PROCUREMENT_PORTAL_SEARCH_URL


def selected(value: str, current: str) -> str:
    return " selected" if value == current else ""


def option_tags(values: list[str], current: str) -> str:
    return "\n".join(f'<option value="{escape(v)}"{selected(v, current)}>{escape(v)}</option>' for v in values)


def build_filters(params: dict[str, str]) -> tuple[str, list[Any]]:
    where = ["analysis_included", "fiscal_year BETWEEN %s AND %s"]
    values: list[Any] = [
        int(params.get("year_from") or 2013),
        int(params.get("year_to") or 2026),
    ]
    keyword = params.get("keyword", "").strip()
    vendor_pick = params.get("vendor_pick", NO_SELECTION)
    vendor_text = params.get("vendor_text", "").strip()
    body_pick = params.get("body_pick", NO_SELECTION)
    bidding_method = params.get("bidding_method", NO_SELECTION)
    consulting = params.get("consulting", CONSULTING_ALL)
    if keyword:
        where.append("procurement_title ILIKE %s")
        values.append(f"%{keyword}%")
    if vendor_pick and vendor_pick != NO_SELECTION:
        where.append("vendor_name_canonical = %s")
        values.append(vendor_pick)
    elif vendor_text:
        where.append("vendor_name_canonical ILIKE %s")
        values.append(f"%{vendor_text}%")
    if body_pick and body_pick != NO_SELECTION:
        where.append("ordering_body_name = %s")
        values.append(body_pick)
    if bidding_method and bidding_method != NO_SELECTION:
        where.append("bidding_method_name = %s")
        values.append(bidding_method)
    if consulting == CONSULTING_BROAD:
        where.append("consulting_flag_broad")
    elif consulting == CONSULTING_STRICT:
        where.append("consulting_flag_strict")
    return " AND ".join(where), values


def search_results(params: dict[str, str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    predicate, values = build_filters(params)
    summary = fetch_one(
        f"SELECT COUNT(*) AS n, COALESCE(SUM(award_amount_yen), 0) AS amount FROM procurements WHERE {predicate}",
        values,
    ) or {"n": 0, "amount": 0}
    rows = fetch_all(
        f"""
        SELECT record_id, fiscal_year, contract_date, procurement_title,
               ordering_body_name, vendor_name_canonical, award_amount_yen,
               bidding_method_name, consulting_categories
        FROM procurements
        WHERE {predicate}
        ORDER BY contract_date DESC NULLS LAST
        LIMIT {SEARCH_RESULT_LIMIT}
        """,
        values,
    )
    return summary, rows


def layout(content: str) -> str:
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{APP_TITLE}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; color: #17202a; background: #f6f8fb; }}
    header {{ background: #14213d; color: white; padding: 24px 32px; }}
    main {{ padding: 24px 32px 48px; max-width: 1280px; margin: 0 auto; }}
    .card {{ background: white; border: 1px solid #d9e2ec; border-radius: 12px; padding: 20px; margin-bottom: 18px; box-shadow: 0 1px 2px rgba(15,23,42,.04); }}
    .grid {{ display: grid; grid-template-columns: repeat(3, minmax(220px, 1fr)); gap: 16px; }}
    label {{ display: block; font-weight: 700; margin-bottom: 6px; }}
    input, select {{ box-sizing: border-box; width: 100%; padding: 9px 10px; border: 1px solid #bcccdc; border-radius: 8px; font-size: 15px; background: white; }}
    button, .button {{ display: inline-block; background: #1d4ed8; color: white; border: none; border-radius: 8px; padding: 10px 16px; font-weight: 700; text-decoration: none; cursor: pointer; }}
    .muted {{ color: #62748e; }}
    .metrics {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }}
    .metric {{ background: #eef4ff; border-radius: 10px; padding: 14px; }}
    .metric div:first-child {{ color: #486581; font-size: 13px; }}
    .metric div:last-child {{ font-size: 22px; font-weight: 800; margin-top: 4px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ border-bottom: 1px solid #e5eaf0; text-align: left; padding: 9px 8px; vertical-align: top; }}
    th {{ background: #f0f4f8; position: sticky; top: 0; }}
    .table-wrap {{ overflow-x: auto; }}
    footer {{ color: #62748e; font-size: 13px; padding: 20px 32px 40px; max-width: 1280px; margin: 0 auto; }}
    @media (max-width: 860px) {{ .grid, .metrics {{ grid-template-columns: 1fr; }} main, header {{ padding-left: 16px; padding-right: 16px; }} }}
  </style>
</head>
<body>
<header>
  <h1>{APP_TITLE}</h1>
  <div>出典：調達ポータル　オープンソースデータを検索できます</div>
</header>
<main>{content}</main>
<footer>© 2026 Government Procurement Search β project. 出典：調達ポータル。本サイトは非公式の研究用試作版です。</footer>
</body>
</html>"""


def render_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="muted">この条件に一致する表示対象データはありませんでした。</p>'
    body = []
    for row in rows:
        award_amount = f"{int(row.get('award_amount_yen') or 0):,}"
        body.append(
            "<tr>"
            f'<td><a href="{portal_url(row["record_id"])}" target="_blank" rel="noopener">外部</a></td>'
            f"<td>{escape(str(row.get('fiscal_year') or ''))}</td>"
            f"<td>{escape(str(row.get('contract_date') or ''))}</td>"
            f"<td>{escape(str(row.get('procurement_title') or ''))}</td>"
            f"<td>{escape(str(row.get('ordering_body_name') or ''))}</td>"
            f"<td>{escape(str(row.get('vendor_name_canonical') or ''))}</td>"
            f"<td>{escape(award_amount)}</td>"
            f"<td>{escape(str(row.get('bidding_method_name') or ''))}</td>"
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr>'
        "<th>外部</th><th>年度</th><th>契約日</th><th>案件名</th><th>発注機関</th><th>受注者</th><th>落札額（円）</th><th>契約方式・落札方式</th>"
        "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table></div>"
    )


def form_html(options: SearchOptions, params: dict[str, str]) -> str:
    year_from = params.get("year_from") or str(options.year_min)
    year_to = params.get("year_to") or str(options.year_max)
    return f"""
    <section class="card">
      <form method="get" action="/">
        <input type="hidden" name="searched" value="1">
        <div class="grid">
          <div><label>年度（開始）</label><input name="year_from" type="number" min="{options.year_min}" max="{options.year_max}" value="{escape(year_from)}"></div>
          <div><label>年度（終了）</label><input name="year_to" type="number" min="{options.year_min}" max="{options.year_max}" value="{escape(year_to)}"></div>
          <div><label>案件名キーワード</label><input name="keyword" value="{escape(params.get('keyword', ''))}"></div>
          <div><label>コンサル認定</label><select name="consulting">{option_tags([CONSULTING_ALL, CONSULTING_BROAD, CONSULTING_STRICT], params.get('consulting', CONSULTING_ALL))}</select></div>
          <div><label>受注者名（候補）</label><select name="vendor_pick">{option_tags(options.vendors, params.get('vendor_pick', NO_SELECTION))}</select></div>
          <div><label>受注者名（自由入力）</label><input name="vendor_text" placeholder="候補にない場合だけ入力" value="{escape(params.get('vendor_text', ''))}"></div>
          <div><label>発注機関名</label><select name="body_pick">{option_tags(options.bodies, params.get('body_pick', NO_SELECTION))}</select></div>
          <div><label>契約方式・落札方式</label><select name="bidding_method">{option_tags(options.bidding_methods, params.get('bidding_method', NO_SELECTION))}</select></div>
        </div>
        <p><button type="submit">この条件で検索</button> <a class="button" style="background:#64748b" href="/">条件をリセット</a></p>
        <p class="muted">入力中はDB検索を実行しません。候補にない受注者名は自由入力で検索してください。</p>
      </form>
    </section>
    """


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    try:
        options = load_options()
    except Exception as exc:
        content = f"""
        <section class="card">
          <h2>調達データを読み取れませんでした</h2>
          <p>データベース接続または初期データ取得でエラーが発生しています。</p>
          <p class="muted">{escape(exc.__class__.__name__)}</p>
        </section>
        """
        return HTMLResponse(layout(content), status_code=200)

    params = dict(request.query_params)
    content = form_html(options, params)
    if params.get("searched"):
        try:
            summary, rows = search_results(params)
            query_string = urlencode(params)
            content += f"""
            <section class="card">
              <div class="metrics">
                <div class="metric"><div>検索結果件数</div><div>{int(summary.get('n') or 0):,}件</div></div>
                <div class="metric"><div>落札額合計（検索結果全体）</div><div>{yen_oku(summary.get('amount'))}</div></div>
                <div class="metric"><div>画面表示</div><div>{len(rows):,}件</div></div>
              </div>
              <p class="muted">画面表示は最新{SEARCH_RESULT_LIMIT:,}件までです。</p>
              <p><a class="button" href="/download.csv?{escape(query_string)}">表示結果をCSVでダウンロード</a></p>
              {render_table(rows)}
            </section>
            """
        except Exception as exc:
            content += f"""
            <section class="card">
              <h2>検索中にエラーが発生しました</h2>
              <p>条件を少し絞るか、時間をおいて再度お試しください。</p>
              <p class="muted">{escape(exc.__class__.__name__)}</p>
            </section>
            """
    else:
        content += '<section class="card"><p>検索条件を設定して「この条件で検索」を押してください。</p></section>'
    return HTMLResponse(layout(content))


@app.get("/download.csv")
def download_csv(request: Request) -> StreamingResponse:
    params = dict(request.query_params)
    _, rows = search_results(params)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["record_id", "fiscal_year", "contract_date", "procurement_title", "ordering_body_name", "vendor_name_canonical", "award_amount_yen", "bidding_method_name", "consulting_categories"])
    for row in rows:
        writer.writerow([
            row.get("record_id"),
            row.get("fiscal_year"),
            row.get("contract_date"),
            row.get("procurement_title"),
            row.get("ordering_body_name"),
            row.get("vendor_name_canonical"),
            row.get("award_amount_yen"),
            row.get("bidding_method_name"),
            row.get("consulting_categories"),
        ])
    data = buffer.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=procurement_search.csv"},
    )
