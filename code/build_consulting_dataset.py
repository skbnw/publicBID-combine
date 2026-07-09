from __future__ import annotations

import argparse
import html
import io
import json
import math
import re
import subprocess
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DOWNLOAD_URL = "https://api.p-portal.go.jp/pps-web-biz/UAB03/OAB0301?fileversion=v001&filename={}"
BIDDING_METHODS = {
    "8002010": "一般競争入札・最低価格", "8002020": "一般競争入札・最高価格",
    "8002040": "一般競争入札・総合評価", "8002050": "一般競争入札・複数落札",
    "8003010": "指名競争入札・最低価格", "8003020": "指名競争入札・最高価格",
    "8003040": "指名競争入札・総合評価", "8003050": "指名競争入札・複数落札",
    "8001010": "随意契約・オープンカウンタ", "8004020": "随意契約・特定業者",
    "8004025": "随意契約・複数業者", "8004030": "随意契約・公募型プロポーザル",
    "8011010": "随意契約・オープンカウンタ・少額", "8014020": "随意契約・特定業者・少額",
    "8014025": "随意契約・複数業者・少額", "8014030": "随意契約・公募型プロポーザル・少額",
}
MINISTRY_NAMES = {
    "A1": "衆議院", "B1": "参議院", "C1": "国立国会図書館", "D1": "最高裁判所",
    "E1": "会計検査院", "F1": "人事院", "F2": "国家公務員倫理審査会", "G1": "内閣官房",
    "H1": "内閣法制局", "I1": "安全保障会議", "J1": "内閣府", "J2": "宮内庁",
    "J3": "公正取引委員会", "J4": "国家公安委員会", "J5": "警察庁", "J6": "金融庁",
    "J7": "消費者庁", "J8": "個人情報保護委員会", "J9": "カジノ管理委員会",
    "K1": "総務省", "K2": "公害等調整委員会", "K3": "消防庁", "L1": "法務省",
    "L2": "検察庁", "L3": "公安審査委員会", "L4": "公安調査庁", "M1": "外務省",
    "N1": "財務省", "N2": "国税庁", "O1": "文部科学省", "O2": "文化庁",
    "O3": "スポーツ庁", "P1": "厚生労働省", "P2": "中央労働委員会", "Q1": "農林水産省",
    "Q2": "林野庁", "Q3": "水産庁", "R1": "経済産業省", "R2": "資源エネルギー庁",
    "R3": "特許庁", "R4": "中小企業庁", "S1": "国土交通省", "S2": "運輸安全委員会",
    "S3": "観光庁", "S4": "気象庁", "S5": "海上保安庁", "T1": "環境省",
    "T2": "原子力安全庁", "U1": "防衛省", "V1": "復興庁", "W1": "デジタル庁",
    "JA": "こども家庭庁", "JB": "サイバー通信情報監理委員会",
}


def normalize(value: object) -> str:
    return re.sub(r"\s+", "", "" if pd.isna(value) else str(value)).upper()


def download(year: int, raw_dir: Path, refresh: bool) -> Path:
    name = f"successful_bid_record_info_all_{year}.zip"
    target = raw_dir / name
    if target.exists() and not refresh:
        return target
    raw_dir.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(DOWNLOAD_URL.format(name), headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            target.write_bytes(response.read())
    except OSError:
        # The portal occasionally resets Python TLS connections on Windows.
        if __import__("os").name != "nt":
            raise
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Invoke-WebRequest -UseBasicParsing -Uri $args[0] -OutFile $args[1]",
             DOWNLOAD_URL.format(name), str(target)],
            check=True,
        )
    return target


def read_zip(path: Path, source_year: int) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive:
        csv_name = next(n for n in archive.namelist() if n.lower().endswith(".csv"))
        payload = archive.read(csv_name)
    frame = pd.read_csv(io.BytesIO(payload), header=None, dtype=str, encoding="utf-8-sig", on_bad_lines="skip")
    original_column_count = frame.shape[1]
    if original_column_count == 7:
        frame.columns = ["record_id", "title_ministry", "contract_date", "award_amount_yen", "bidding_method_code", "vendor_name", "reference_id"]
        split = frame["title_ministry"].fillna("").str.rsplit("／", n=1, expand=True)
        if split.shape[1] == 1:
            split = frame["title_ministry"].fillna("").str.rsplit("/", n=1, expand=True)
        frame["procurement_title"] = split[0]
        frame["ministry_name"] = split[1] if split.shape[1] > 1 else ""
    elif original_column_count == 8:
        frame.columns = ["record_id", "procurement_title", "contract_date", "award_amount_yen", "ministry_code", "bidding_method_code", "vendor_name", "reference_id"]
        # Preserve all eight official CSV fields exactly as delivered before conversion.
        frame["source_procurement_item_no"] = frame["record_id"]
        frame["source_procurement_item_name"] = frame["procurement_title"]
        frame["source_successful_bid_date"] = frame["contract_date"]
        frame["source_successful_bid_price"] = frame["award_amount_yen"]
        frame["source_ministry_code"] = frame["ministry_code"]
        frame["source_bidding_method_code"] = frame["bidding_method_code"]
        frame["source_trade_name"] = frame["vendor_name"]
        frame["source_corporation_number"] = frame["reference_id"]
        frame["corporation_number"] = frame["reference_id"]
        frame["ordering_body_code"] = frame["ministry_code"]
        frame["ordering_body_name"] = frame["ministry_code"].map(MINISTRY_NAMES).fillna("不明（" + frame["ministry_code"].fillna("") + "）")
        frame["ministry_name"] = frame["ordering_body_name"]
    else:
        raise ValueError(f"Unsupported column count {original_column_count} in {path.name}")
    frame["source_row_number"] = range(1, len(frame) + 1)
    frame["source_file_name"] = path.name
    frame["source_year"] = source_year
    return frame


def tag_rows(frame: pd.DataFrame, rules: dict) -> pd.DataFrame:
    categories = {k: [normalize(x) for x in v] for k, v in rules["categories"].items()}
    general = [normalize(x) for x in rules["general_title_terms"]]
    vendors = [normalize(x) for x in rules["vendor_terms"]]
    vendor_categories = {k: [normalize(x) for x in v] for k, v in rules.get("vendor_categories", {}).items()}
    canonical_names = {k: [normalize(x) for x in v] for k, v in rules.get("vendor_canonical_names", {}).items()}
    exclusions = [normalize(x) for x in rules["exclusions"]]

    def tag(row: pd.Series) -> pd.Series:
        title, vendor = normalize(row["procurement_title"]), normalize(row["vendor_name"])
        matched = [category for category, terms in categories.items() if any(term in title for term in terms)]
        title_hit = bool(matched) or any(term in title for term in general)
        firm_matches = [(category, term) for category, terms in vendor_categories.items() for term in terms if term in vendor]
        canonical_match = next((canonical for canonical, aliases in canonical_names.items() if any(alias in vendor for alias in aliases)), "")
        vendor_hit = bool(firm_matches) or any(term in vendor for term in vendors)
        excluded = any(term in title for term in exclusions)
        strict = title_hit and not excluded
        broad = (title_hit or vendor_hit) and not excluded
        reason = "案件名" if strict else ("受注者名" if vendor_hit and not excluded else "")
        vendor_category = "|".join(dict.fromkeys(category for category, _ in firm_matches))
        vendor_match = "|".join(dict.fromkeys(term for _, term in firm_matches))
        canonical_name = canonical_match or ("" if pd.isna(row["vendor_name"]) else str(row["vendor_name"]))
        return pd.Series([strict, broad, vendor_hit, "|".join(matched) if matched else ("その他コンサル" if strict else ""), vendor_category, vendor_match, canonical_name, reason, excluded])

    frame[["consulting_flag_strict", "consulting_flag_broad", "consulting_vendor_flag", "consulting_categories", "consulting_vendor_category", "consulting_vendor_match", "vendor_name_canonical", "tag_reason", "exclusion_flag"]] = frame.apply(tag, axis=1)
    return frame


def bar_rows(summary: pd.DataFrame) -> str:
    maximum = max(float(summary["award_amount_yen"].max()), 1)
    rows = []
    for row in summary.itertuples(index=False):
        width = 100 * float(row.award_amount_yen) / maximum
        rows.append(f"<tr><td>{int(row.fiscal_year)}</td><td>{int(row.contract_count):,}</td><td>{float(row.award_amount_yen)/1e8:,.1f}</td><td><div class='bar' style='width:{width:.1f}%'></div></td></tr>")
    return "".join(rows)


def category_pivot_html(category: pd.DataFrame, value: str, amount: bool = False) -> tuple[str, str]:
    pivot = category.pivot(index="fiscal_year", columns="consulting_categories", values=value).fillna(0)
    columns = list(pivot.columns)
    header = "".join(f"<th>{html.escape(str(column))}</th>" for column in columns)
    rows = []
    for year, values in pivot.iterrows():
        cells = "".join(
            f"<td>{float(values[column])/1e8:,.1f}</td>" if amount else f"<td>{int(values[column]):,}</td>"
            for column in columns
        )
        rows.append(f"<tr><td>{int(year)}</td>{cells}</tr>")
    return header, "".join(rows)


def top_firms_scatter_svg(top: pd.DataFrame, reporting_years: int) -> str:
    """Inline SVG: x=annual contracts, y=annual award amount, bubble=cumulative amount."""
    width, height = 1060, 560
    left, right, top_pad, bottom = 78, 350, 34, 64
    plot_w, plot_h = width - left - right, height - top_pad - bottom
    points = top.copy()
    points["avg_count"] = points["contract_count"] / reporting_years
    points["avg_amount_oku"] = points["award_amount_yen"] / 1e8 / reporting_years
    # Both measures currently fit naturally into a common, readable 0–150 scale.
    # If future data exceed it, expand by another round 150-unit block.
    x_max = max(180, math.ceil(float(points["avg_count"].max()) / 180) * 180)
    y_max = max(180, math.ceil(float(points["avg_amount_oku"].max()) / 180) * 180)

    def x_pos(value: float) -> float:
        return left + value / x_max * plot_w

    def y_pos(value: float) -> float:
        return top_pad + plot_h - value / y_max * plot_h

    grid = []
    for fraction in (0, .2, .4, .6, .8, 1):
        x = left + plot_w * fraction
        y = top_pad + plot_h * (1 - fraction)
        x_value = x_max * fraction
        y_value = y_max * fraction
        grid.append(f"<line x1='{x:.1f}' y1='{top_pad}' x2='{x:.1f}' y2='{top_pad+plot_h}' class='grid'/><text x='{x:.1f}' y='{top_pad+plot_h+25}' class='tick' text-anchor='middle'>{x_value:.0f}</text>")
        grid.append(f"<line x1='{left}' y1='{y:.1f}' x2='{left+plot_w}' y2='{y:.1f}' class='grid'/><text x='{left-10}' y='{y+4:.1f}' class='tick' text-anchor='end'>{y_value:.0f}</text>")
    max_amount = max(float(points["award_amount_yen"].max()), 1)
    plotted = []
    for row in points.itertuples(index=False):
        x, y = x_pos(float(row.avg_count)), y_pos(float(row.avg_amount_oku))
        radius = 6 + 13 * math.sqrt(float(row.award_amount_yen) / max_amount)
        full_name = html.escape(str(row.vendor_name_canonical))
        tooltip = f"{full_name}: 年平均 {row.avg_count:.1f}件 / {row.avg_amount_oku:.1f}億円、累積 {float(row.award_amount_yen)/1e8:,.1f}億円"
        plotted.append((y, x, radius, full_name, tooltip))
    # Put labels in a dedicated right-hand lane, ordered by y, so they never overlap.
    plotted.sort(key=lambda item: item[0])
    label_gap = plot_h / max(len(plotted) - 1, 1)
    bubbles, labels = [], []
    label_x = left + plot_w + 42
    for index, (y, x, radius, full_name, tooltip) in enumerate(plotted, 1):
        label_y = top_pad + (index - 1) * label_gap
        label = full_name if len(full_name) <= 24 else full_name[:23] + "…"
        bubbles.append(
            f"<g><title>{tooltip}</title><circle cx='{x:.1f}' cy='{y:.1f}' r='{radius:.1f}' class='bubble'/>"
            f"<text x='{x:.1f}' y='{y+4:.1f}' class='bubble-number' text-anchor='middle'>{index}</text></g>"
        )
        labels.append(
            f"<path d='M {x+radius:.1f} {y:.1f} L {left+plot_w+15:.1f} {label_y:.1f} L {label_x-8:.1f} {label_y:.1f}' class='leader'/>"
            f"<text x='{label_x:.1f}' y='{label_y+4:.1f}' class='label'>{index}. {label}</text>"
        )
    return (
        f"<svg class='scatter' viewBox='0 0 {width} {height}' role='img' aria-label='上位20社の年平均件数と年平均落札額の散布図'>"
        f"<style>.grid{{stroke:#dfe5ee;stroke-width:1}}.tick{{font-size:12px;fill:#667085}}.bubble{{fill:#3972e6;fill-opacity:.68;stroke:#155eef;stroke-width:1.5}}.bubble-number{{font-size:9px;font-weight:700;fill:white}}.leader{{fill:none;stroke:#aab4c4;stroke-width:.8}}.label{{font-size:11px;fill:#25324a}}</style>"
        + "".join(grid) + "".join(labels) + "".join(bubbles)
        + f"<text x='{left+plot_w/2:.1f}' y='{height-12}' text-anchor='middle' class='tick'>年平均件数</text>"
        + f"<text x='18' y='{top_pad+plot_h/2:.1f}' text-anchor='middle' class='tick' transform='rotate(-90 18 {top_pad+plot_h/2:.1f})'>年平均落札額（億円）</text></svg>"
    )


def ministry_firm_matrix_svg(consult: pd.DataFrame, ordering_bodies: pd.DataFrame, top_firms: pd.DataFrame) -> str:
    """Bubble matrix for the top ordering bodies and consulting firms."""
    bodies = ordering_bodies["ordering_body_name"].astype(str).tolist()
    firms = top_firms["vendor_name_canonical"].astype(str).tolist()
    pairs = (consult[consult["ordering_body_name"].isin(bodies) & consult["vendor_name_canonical"].isin(firms)]
             .groupby(["ordering_body_name", "vendor_name_canonical"], dropna=False)
             .agg(contract_count=("record_id", "size"), award_amount_yen=("award_amount_yen", "sum")).reset_index())
    ministry_totals = consult.groupby("ordering_body_name")["award_amount_yen"].sum()
    width, height = 1320, 850
    left, top_pad, right, bottom = 300, 34, 30, 190
    plot_w, plot_h = width - left - right, height - top_pad - bottom
    x_step, y_step = plot_w / len(bodies), plot_h / len(firms)
    max_amount = max(float(pairs["award_amount_yen"].max()), 1)
    body_index, firm_index = {v: i for i, v in enumerate(bodies)}, {v: i for i, v in enumerate(firms)}
    grid = []
    for i in range(len(bodies) + 1):
        x = left + i * x_step
        grid.append(f"<line x1='{x:.1f}' y1='{top_pad}' x2='{x:.1f}' y2='{top_pad+plot_h}' class='matrix-grid'/>")
    for i in range(len(firms) + 1):
        y = top_pad + i * y_step
        grid.append(f"<line x1='{left}' y1='{y:.1f}' x2='{left+plot_w}' y2='{y:.1f}' class='matrix-grid'/>")
    labels = []
    for i, body in enumerate(bodies):
        x = left + (i + .5) * x_step
        labels.append(f"<text x='{x:.1f}' y='{top_pad+plot_h+14:.1f}' class='matrix-label' text-anchor='end' transform='rotate(-55 {x:.1f} {top_pad+plot_h+14:.1f})'>{html.escape(body)}</text>")
    for i, firm in enumerate(firms):
        y = top_pad + (i + .5) * y_step + 4
        display = firm if len(firm) <= 27 else firm[:26] + "…"
        labels.append(f"<text x='{left-10}' y='{y:.1f}' class='matrix-label' text-anchor='end'>{html.escape(display)}</text>")
    bubbles = []
    for row in pairs.itertuples(index=False):
        x = left + (body_index[str(row.ordering_body_name)] + .5) * x_step
        y = top_pad + (firm_index[str(row.vendor_name_canonical)] + .5) * y_step
        amount_oku = float(row.award_amount_yen) / 1e8
        share = float(row.award_amount_yen) / max(float(ministry_totals.get(row.ordering_body_name, 0)), 1) * 100
        radius = 2.5 + min(x_step, y_step) * .42 * math.sqrt(float(row.award_amount_yen) / max_amount)
        tooltip = (f"{html.escape(str(row.ordering_body_name))} × {html.escape(str(row.vendor_name_canonical))}: "
                   f"{int(row.contract_count):,}件 / {amount_oku:,.1f}億円 / 機関内シェア {share:.1f}%")
        bubbles.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='{radius:.1f}' class='matrix-bubble'><title>{tooltip}</title></circle>")
    return (
        f"<svg class='matrix' viewBox='0 0 {width} {height}' role='img' aria-label='発注機関と受注コンサルのバブルマトリクス'>"
        "<style>.matrix-grid{stroke:#e7ebf1;stroke-width:1}.matrix-label{font-size:11px;fill:#344054}.matrix-bubble{fill:#2563eb;fill-opacity:.7;stroke:#174ea6;stroke-width:.8}</style>"
        + "".join(grid) + "".join(labels) + "".join(bubbles) + "</svg>"
    )


def relationship_type_scatter_svg(consult: pd.DataFrame) -> str:
    """Show whether concentrated ministry-firm relationships are repeated-small or few-large."""
    pairs = (consult.groupby(["ordering_body_name", "vendor_name_canonical"], dropna=False)
             .agg(contract_count=("record_id", "size"), award_amount_yen=("award_amount_yen", "sum")).reset_index())
    totals = consult.groupby("ordering_body_name")["award_amount_yen"].sum()
    pairs["share_pct"] = pairs["award_amount_yen"] / pairs["ordering_body_name"].map(totals).replace(0, pd.NA) * 100
    pairs["avg_amount_oku"] = pairs["award_amount_yen"] / pairs["contract_count"] / 1e8
    pairs = pairs[(pairs["contract_count"] >= 5) & (pairs["award_amount_yen"] >= 1e9)]
    pairs = pairs.sort_values("share_pct", ascending=False).head(20).copy()
    width, height = 1120, 630
    left, right, top_pad, bottom = 82, 400, 58, 68
    plot_w, plot_h = width - left - right, height - top_pad - bottom
    x_min, x_max, y_min, y_max = 5, 600, .1, 100

    def log_pos(value: float, minimum: float, maximum: float, start: float, length: float) -> float:
        return start + (math.log10(value) - math.log10(minimum)) / (math.log10(maximum) - math.log10(minimum)) * length

    grid = []
    for tick in (5, 10, 20, 50, 100, 200, 500):
        x = log_pos(tick, x_min, x_max, left, plot_w)
        grid.append(f"<line x1='{x:.1f}' y1='{top_pad}' x2='{x:.1f}' y2='{top_pad+plot_h}' class='relation-grid'/><text x='{x:.1f}' y='{top_pad+plot_h+23}' class='relation-tick' text-anchor='middle'>{tick}</text>")
    for tick in (.1, .3, 1, 3, 10, 30, 100):
        y = top_pad + plot_h - log_pos(tick, y_min, y_max, 0, plot_h)
        grid.append(f"<line x1='{left}' y1='{y:.1f}' x2='{left+plot_w}' y2='{y:.1f}' class='relation-grid'/><text x='{left-9}' y='{y+4:.1f}' class='relation-tick' text-anchor='end'>{tick:g}</text>")
    x_cut = log_pos(20, x_min, x_max, left, plot_w)
    y_cut = top_pad + plot_h - log_pos(2, y_min, y_max, 0, plot_h)
    grid.append(f"<line x1='{x_cut:.1f}' y1='{top_pad}' x2='{x_cut:.1f}' y2='{top_pad+plot_h}' class='relation-cut'/>")
    grid.append(f"<line x1='{left}' y1='{y_cut:.1f}' x2='{left+plot_w}' y2='{y_cut:.1f}' class='relation-cut'/>")
    colors = {"少数巨額型": "#f59e0b", "小口反復型": "#16a34a", "高頻度・大型型": "#7c3aed", "中間型": "#2563eb"}
    plotted = []
    for row in pairs.itertuples(index=False):
        count, average, share = int(row.contract_count), float(row.avg_amount_oku), float(row.share_pct)
        relation_type = ("高頻度・大型型" if count >= 20 and average >= 2 else
                         "小口反復型" if count >= 20 else "少数巨額型" if average >= 2 else "中間型")
        x = log_pos(count, x_min, x_max, left, plot_w)
        y = top_pad + plot_h - log_pos(max(average, y_min), y_min, y_max, 0, plot_h)
        radius = 5 + 15 * math.sqrt(max(share, 0) / 100)
        name = f"{row.ordering_body_name} × {row.vendor_name_canonical}"
        tooltip = f"{html.escape(name)}: {count}件 / 1件平均{average:.1f}億円 / シェア{share:.1f}% / {relation_type}"
        plotted.append((y, x, radius, name, tooltip, relation_type, count, average, share))
    plotted.sort(key=lambda item: item[0])
    label_gap, label_x = plot_h / max(len(plotted) - 1, 1), left + plot_w + 42
    shapes, labels = [], []
    for index, (y, x, radius, name, tooltip, relation_type, count, average, share) in enumerate(plotted, 1):
        label_y = top_pad + (index - 1) * label_gap
        display = name if len(name) <= 33 else name[:32] + "…"
        color = colors[relation_type]
        shapes.append(f"<g><title>{tooltip}</title><circle cx='{x:.1f}' cy='{y:.1f}' r='{radius:.1f}' fill='{color}' class='relation-bubble'/><text x='{x:.1f}' y='{y+4:.1f}' class='relation-number' text-anchor='middle'>{index}</text></g>")
        labels.append(f"<path d='M {x+radius:.1f} {y:.1f} L {left+plot_w+14:.1f} {label_y:.1f} L {label_x-8:.1f} {label_y:.1f}' class='relation-leader'/><text x='{label_x:.1f}' y='{label_y+4:.1f}' class='relation-label'>{index}. {html.escape(display)}［{relation_type}］</text>")
    legend = "".join(f"<circle cx='{left+i*145}' cy='23' r='6' fill='{color}'/><text x='{left+10+i*145}' y='27' class='relation-label'>{label}</text>" for i, (label, color) in enumerate(colors.items()))
    return (f"<svg class='relation-chart' viewBox='0 0 {width} {height}' role='img' aria-label='発注機関とコンサル会社の関係性の型'>"
            "<style>.relation-grid{stroke:#e3e8ef;stroke-width:1}.relation-cut{stroke:#94a3b8;stroke-width:1.2;stroke-dasharray:5 4}.relation-tick{font-size:11px;fill:#667085}.relation-bubble{fill-opacity:.72;stroke:#fff;stroke-width:1}.relation-number{font-size:9px;font-weight:700;fill:#fff}.relation-leader{fill:none;stroke:#aab4c4;stroke-width:.7}.relation-label{font-size:10px;fill:#344054}</style>"
            + legend + "".join(grid) + "".join(labels) + "".join(shapes)
            + f"<text x='{left+plot_w/2:.1f}' y='{height-12}' class='relation-tick' text-anchor='middle'>累積件数（対数目盛）</text>"
            + f"<text x='17' y='{top_pad+plot_h/2:.1f}' class='relation-tick' text-anchor='middle' transform='rotate(-90 17 {top_pad+plot_h/2:.1f})'>1件平均落札額（億円・対数目盛）</text></svg>")


def build_html(data: pd.DataFrame, yearly: pd.DataFrame, category: pd.DataFrame, output: Path) -> None:
    consult = data[data["consulting_flag_broad"]]
    # Empty CSV fields are restored as NaN when a generated dataset is reopened.
    # Normalize them before filtering so they do not become a visible "nan" group.
    consult = consult.copy()
    consult["consulting_vendor_category"] = consult["consulting_vendor_category"].fillna("")
    reporting_years = int(consult["fiscal_year"].nunique())
    now = datetime.now()
    current_fiscal_year = now.year if now.month >= 4 else now.year - 1
    includes_partial_year = int(data["fiscal_year"].max()) >= current_fiscal_year
    average_note = (f"対象期間の{reporting_years}年度（当年度の途中経過を含む）" if includes_partial_year
                    else f"完了済みの{reporting_years}年度")
    top = (consult.groupby("vendor_name_canonical", dropna=False).agg(contract_count=("record_id", "size"), award_amount_yen=("award_amount_yen", "sum"), active_years=("fiscal_year", "nunique"))
           .sort_values("award_amount_yen", ascending=False).head(20).reset_index())
    top_rows = "".join(
        f"<tr><td>{html.escape(str(r.vendor_name_canonical))}</td><td>{int(r.contract_count):,}</td>"
        f"<td>{float(r.award_amount_yen)/1e8:,.1f}</td><td>{int(r.active_years)}</td>"
        f"<td>{float(r.contract_count)/reporting_years:,.1f}</td><td>{float(r.award_amount_yen)/1e8/reporting_years:,.1f}</td></tr>"
        for r in top.itertuples(index=False)
    )
    top_scatter = top_firms_scatter_svg(top, reporting_years)
    firm_types = (consult[consult["consulting_vendor_category"].str.strip() != ""].groupby("consulting_vendor_category", dropna=False)
                  .agg(contract_count=("record_id", "size"), award_amount_yen=("award_amount_yen", "sum"))
                  .sort_values("award_amount_yen", ascending=False).reset_index())
    firm_rows = "".join(f"<tr><td>{html.escape(str(r.consulting_vendor_category))}</td><td>{int(r.contract_count):,}</td><td>{float(r.award_amount_yen)/1e8:,.1f}</td></tr>" for r in firm_types.itertuples(index=False))
    ordering_bodies = (consult.groupby(["ordering_body_code", "ordering_body_name"], dropna=False)
                       .agg(contract_count=("record_id", "size"), award_amount_yen=("award_amount_yen", "sum"))
                       .sort_values("award_amount_yen", ascending=False).head(20).reset_index())
    ordering_body_rows = "".join(
        f"<tr><td>{html.escape(str(r.ordering_body_name))}</td><td>{html.escape(str(r.ordering_body_code))}</td>"
        f"<td>{int(r.contract_count):,}</td><td>{float(r.award_amount_yen)/1e8:,.1f}</td></tr>"
        for r in ordering_bodies.itertuples(index=False)
    )
    vendor_consult = consult[consult["consulting_vendor_flag"]].copy()
    matrix_bodies = (vendor_consult.groupby(["ordering_body_code", "ordering_body_name"], dropna=False)
                     .agg(contract_count=("record_id", "size"), award_amount_yen=("award_amount_yen", "sum"))
                     .sort_values("award_amount_yen", ascending=False).head(20).reset_index())
    matrix_firms = (vendor_consult.groupby("vendor_name_canonical", dropna=False)
                    .agg(contract_count=("record_id", "size"), award_amount_yen=("award_amount_yen", "sum"), active_years=("fiscal_year", "nunique"))
                    .sort_values("award_amount_yen", ascending=False).head(20).reset_index())
    ministry_firm_matrix = ministry_firm_matrix_svg(vendor_consult, matrix_bodies, matrix_firms)
    relationship_type_scatter = relationship_type_scatter_svg(vendor_consult)
    pair_summary = (vendor_consult.groupby(["ordering_body_name", "vendor_name_canonical"], dropna=False)
                    .agg(contract_count=("record_id", "size"), award_amount_yen=("award_amount_yen", "sum")).reset_index())
    pair_summary["ordering_body_total_yen"] = pair_summary["ordering_body_name"].map(
        vendor_consult.groupby("ordering_body_name")["award_amount_yen"].sum())
    pair_summary["ordering_body_share_pct"] = pair_summary["award_amount_yen"] / pair_summary["ordering_body_total_yen"].replace(0, pd.NA) * 100
    pair_summary = pair_summary.sort_values("award_amount_yen", ascending=False).head(20)
    pair_rows = "".join(
        f"<tr><td>{html.escape(str(r.ordering_body_name))}</td><td>{html.escape(str(r.vendor_name_canonical))}</td>"
        f"<td>{int(r.contract_count):,}</td><td>{float(r.award_amount_yen)/1e8:,.1f}</td><td>{float(r.ordering_body_share_pct):.1f}%</td></tr>"
        for r in pair_summary.itertuples(index=False)
    )
    category_count_header, category_count_rows = category_pivot_html(category, "contract_count")
    category_amount_header, category_amount_rows = category_pivot_html(category, "award_amount_yen", amount=True)
    generated = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    document = f"""<!doctype html><html lang='ja'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>政府調達 コンサル案件集計</title><style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans JP',sans-serif;margin:0;background:#f4f7fb;color:#172033}}main{{max-width:1100px;margin:auto;padding:32px}}h1{{margin-bottom:6px}}.note{{color:#5d687c}}.small-note{{color:#667085;font-size:12px;margin-top:-12px}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:24px 0}}.card,section{{background:white;border-radius:12px;padding:20px;box-shadow:0 3px 16px #20304a12}}.big{{font-size:28px;font-weight:700;color:#155eef}}section{{margin:18px 0;overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{padding:9px;border-bottom:1px solid #e6eaf0;text-align:right;white-space:nowrap}}th:first-child,td:first-child{{text-align:left}}.bar{{height:14px;background:#4f7cff;border-radius:4px;min-width:2px}}.scatter,.matrix,.relation-chart{{display:block;width:100%;min-width:720px;height:auto;margin:12px 0 22px}}code{{background:#eef2f7;padding:2px 5px;border-radius:4px}}@media(max-width:700px){{.cards{{grid-template-columns:1fr}}main{{padding:16px}}}}
</style></head><body><main><h1>政府調達におけるコンサル関連案件</h1><p class='note'>落札実績オープンデータを案件名・受注者名でタグ付けした一次集計。作成: {generated}</p>
<div class='cards'><div class='card'><div>対象期間</div><div class='big'>{int(data.fiscal_year.min())}–{int(data.fiscal_year.max())}年度</div></div><div class='card'><div>広義コンサル案件</div><div class='big'>{len(consult):,}件</div></div><div class='card'><div>落札額合計</div><div class='big'>{consult.award_amount_yen.sum()/1e8:,.1f} 億円</div></div></div>
<section><h2>年度別推移</h2><table><thead><tr><th>年度</th><th>件数</th><th>落札額（億円）</th><th>相対規模</th></tr></thead><tbody>{bar_rows(yearly)}</tbody></table></section>
<section><h2>受注者 上位20社（対象期間累積・落札額順）</h2><p class='note'>年平均は{average_note}で除した値です。横軸は年平均件数、縦軸は年平均落札額、円の大きさは累積落札額です。軸は0〜180を基準とし、バブル内の番号と右側の会社名が対応します。</p>{top_scatter}<table><thead><tr><th>受注者</th><th>累積件数</th><th>累積落札額<br>（億円）</th><th>活動年度数</th><th>年平均件数</th><th>年平均落札額<br>（億円）</th></tr></thead><tbody>{top_rows}</tbody></table></section>
<section><h2>主要コンサルファーム類型別</h2><table><thead><tr><th>類型</th><th>件数</th><th>落札額（億円）</th></tr></thead><tbody>{firm_rows}</tbody></table></section>
<section><h2>発注機関 上位20（落札額順）</h2><table><thead><tr><th>発注機関</th><th>府省コード</th><th>件数</th><th>落札額（億円）</th></tr></thead><tbody>{ordering_body_rows}</tbody></table></section>
<section><h2>発注機関 × 受注コンサル</h2>{ministry_firm_matrix}<p class='small-note'>横軸はコンサル落札額上位20の発注機関、縦軸は同上位20の受注者です。円が大きいほど、その機関からその会社への累積落札額が大きいことを示します。円にカーソルを合わせると件数・金額・機関内シェアを確認できます。</p><h3>機関・受注者ペア 上位20</h3><table><thead><tr><th>発注機関</th><th>受注者</th><th>件数</th><th>落札額（億円）</th><th>機関内シェア</th></tr></thead><tbody>{pair_rows}</tbody></table></section>
<section><h2>発注機関との関係性の型</h2><p class='note'>累積5件以上・累積10億円以上の組み合わせのうち、機関内シェア上位20を表示します。横軸は累積件数、縦軸は1件平均落札額、円の大きさは機関内シェアです。破線は20件・平均2億円の目安です。</p>{relationship_type_scatter}<p class='small-note'>右上は高頻度・大型型、左上は少数巨額型、右下は小口反復型です。対数目盛のため、位置の差は比率として読みます。</p></section>
<section><h2>カテゴリ別・年度別 件数</h2><table><thead><tr><th>年度</th>{category_count_header}</tr></thead><tbody>{category_count_rows}</tbody></table></section>
<section><h2>カテゴリ別・年度別 落札額（億円）</h2><table><thead><tr><th>年度</th>{category_amount_header}</tr></thead><tbody>{category_amount_rows}</tbody></table><p class='note'>複数カテゴリに該当する案件は、それぞれのカテゴリに計上されます。</p></section>
<section><h2>読み方</h2><p><code>strict</code> は案件名による判定、<code>broad</code> は受注者名による補助判定を含みます。社名判定は誤検出を含み得るため、分析時は両者を比較してください。金額が欠損した案件は件数に含み、金額集計では0円扱いです。</p><p>出典: <a href='https://www.p-portal.go.jp/pps-web-biz/UAB02/OAB0201'>デジタル庁 調達ポータル</a></p></section>
</main></body></html>"""
    output.write_text(document, encoding="utf-8")


def build_firm_list(data: pd.DataFrame, rules: dict) -> pd.DataFrame:
    """Create one auditable row per registered consulting firm, including observed results."""
    category_aliases = {
        category: [normalize(alias) for alias in aliases]
        for category, aliases in rules.get("vendor_categories", {}).items()
    }
    rows = []
    for canonical, aliases in rules.get("vendor_canonical_names", {}).items():
        normalized_aliases = [normalize(alias) for alias in aliases]
        categories = [
            category for category, terms in category_aliases.items()
            if any(alias in term or term in alias for alias in normalized_aliases for term in terms)
        ]
        matched = data[data["vendor_name_canonical"] == canonical]
        observed = sorted(str(name) for name in matched["vendor_name"].dropna().unique())
        years = matched["fiscal_year"].dropna()
        rows.append({
            "vendor_name_canonical": canonical,
            "consulting_vendor_category": "|".join(dict.fromkeys(categories)),
            "registered_aliases": "|".join(aliases),
            "observed_vendor_names": "|".join(observed),
            "contract_count": len(matched),
            "award_amount_yen": matched["award_amount_yen"].sum(),
            "first_fiscal_year": int(years.min()) if not years.empty else "",
            "last_fiscal_year": int(years.max()) if not years.empty else "",
        })
    return pd.DataFrame(rows).sort_values(["consulting_vendor_category", "vendor_name_canonical"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, default=2013)
    parser.add_argument("--end-year", type=int, default=datetime.now().year)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    raw_dir, output_dir = ROOT / "data" / "raw", ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    rules = json.loads((ROOT / "config" / "consulting_tags.json").read_text(encoding="utf-8"))
    frames = [read_zip(download(year, raw_dir, args.refresh), year) for year in range(args.start_year, args.end_year + 1)]
    data = pd.concat(frames, ignore_index=True)
    data["contract_date"] = pd.to_datetime(data["contract_date"], errors="coerce")
    data["award_amount_yen"] = pd.to_numeric(data["award_amount_yen"].str.replace(",", "", regex=False), errors="coerce").fillna(0).clip(lower=0)
    # Japanese fiscal year: April through March.
    data["fiscal_year"] = data["contract_date"].dt.year - (data["contract_date"].dt.month < 4).astype("Int64")
    data["bidding_method_name"] = data["bidding_method_code"].map(BIDDING_METHODS).fillna("不明")
    data = tag_rows(data, rules)
    duplicate_key = ["record_id", "reference_id", "vendor_name"]
    data["duplicate_flag"] = data.duplicated(subset=duplicate_key, keep="last")
    data["analysis_included"] = ~data["duplicate_flag"]
    analysis_data = data[data["analysis_included"]].copy()
    consult = analysis_data[analysis_data["consulting_flag_broad"]].copy()
    yearly = consult.groupby("fiscal_year", dropna=True).agg(contract_count=("record_id", "size"), award_amount_yen=("award_amount_yen", "sum")).reset_index()
    exploded = consult.assign(consulting_categories=consult["consulting_categories"].replace("", "受注者名のみ").str.split("|")).explode("consulting_categories")
    category = exploded.groupby(["fiscal_year", "consulting_categories"], dropna=True).agg(contract_count=("record_id", "size"), award_amount_yen=("award_amount_yen", "sum")).reset_index()
    data.to_csv(output_dir / "government_procurement_all_complete.csv", index=False, encoding="utf-8-sig")
    consult.to_csv(output_dir / "consulting_procurement.csv", index=False, encoding="utf-8-sig")
    yearly.to_csv(output_dir / "consulting_summary_by_year.csv", index=False, encoding="utf-8-sig")
    category.to_csv(output_dir / "consulting_summary_by_category_year.csv", index=False, encoding="utf-8-sig")
    firm_yearly = (consult[consult["consulting_vendor_category"].fillna("").str.strip() != ""].groupby(["fiscal_year", "consulting_vendor_category"], dropna=True)
                   .agg(contract_count=("record_id", "size"), award_amount_yen=("award_amount_yen", "sum")).reset_index())
    firm_yearly.to_csv(output_dir / "consulting_summary_by_firm_type_year.csv", index=False, encoding="utf-8-sig")
    build_firm_list(analysis_data, rules).to_csv(output_dir / "consulting_firm_list.csv", index=False, encoding="utf-8-sig")
    ordering_body_yearly = (consult.groupby(["fiscal_year", "ordering_body_code", "ordering_body_name"], dropna=False)
                            .agg(contract_count=("record_id", "size"), award_amount_yen=("award_amount_yen", "sum")).reset_index())
    ordering_body_yearly.to_csv(output_dir / "consulting_summary_by_ordering_body_year.csv", index=False, encoding="utf-8-sig")
    vendor_consult = consult[consult["consulting_vendor_flag"]].copy()
    ordering_body_firm = (vendor_consult.groupby(["ordering_body_code", "ordering_body_name", "vendor_name_canonical"], dropna=False)
                          .agg(contract_count=("record_id", "size"), award_amount_yen=("award_amount_yen", "sum"),
                               first_fiscal_year=("fiscal_year", "min"), last_fiscal_year=("fiscal_year", "max")).reset_index())
    body_totals = ordering_body_firm.groupby("ordering_body_name")["award_amount_yen"].transform("sum")
    ordering_body_firm["ordering_body_share_pct"] = ordering_body_firm["award_amount_yen"] / body_totals.replace(0, pd.NA) * 100
    ordering_body_firm.sort_values("award_amount_yen", ascending=False).to_csv(
        output_dir / "consulting_summary_by_ordering_body_firm.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(sorted(MINISTRY_NAMES.items()), columns=["ordering_body_code", "ordering_body_name"]).to_csv(
        output_dir / "ordering_body_master.csv", index=False, encoding="utf-8-sig")
    build_html(analysis_data, yearly, category, output_dir / "consulting_report.html")
    print(f"Completed: {len(data):,} source rows / {len(analysis_data):,} analysis rows / {len(consult):,} broad consulting rows -> {output_dir}")


if __name__ == "__main__":
    main()
