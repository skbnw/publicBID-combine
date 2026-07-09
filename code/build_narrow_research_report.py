from __future__ import annotations

import html
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
INCLUDE_PATTERN = (
    r"委託調査|調査研究|調査・研究|実態調査|動向調査|市場調査|アンケート調査|"
    r"ヒアリング調査|評価(?:業務|調査|分析)|効果検証|分析調査|調査分析|調査・分析|"
    r"調査及び分析|調査業務"
)
SYSTEM_EXCLUDE_PATTERN = (
    r"システム|ソフトウェア|アプリ(?:ケーション)?|クラウド|ネットワーク|サーバ|"
    r"基盤(?:構築|整備)|開発業務|運用業務|保守業務|改修業務"
)
INFRA_EXCLUDE_PATTERN = (
    r"地質|測量|施工|工事|建築|土木|橋梁|道路|河川|港湾|空港|発注者支援|設計業務|"
    r"施設整備|補償調査|用地調査|土質|地盤"
)


def money_oku(value: float) -> str:
    return f"{value / 1e8:,.1f}"


def main() -> None:
    data = pd.read_csv(OUTPUT / "government_procurement_all.csv", encoding="utf-8-sig", low_memory=False)
    base = data[
        data["analysis_included"].eq(True)
        & data["fiscal_year"].between(2016, 2025, inclusive="both")
        & data["consulting_flag_broad"].eq(True)
    ].copy()
    title = base["procurement_title"].fillna("")
    include = title.str.contains(INCLUDE_PATTERN, case=False, regex=True)
    system_excluded = title.str.contains(SYSTEM_EXCLUDE_PATTERN, case=False, regex=True)
    infra_excluded = title.str.contains(INFRA_EXCLUDE_PATTERN, case=False, regex=True)
    narrow = base[include & ~system_excluded & ~infra_excluded].copy()
    narrow["narrow_research_flag"] = True
    narrow["project_amount_oku"] = narrow["award_amount_yen"] / 1e8
    narrow = narrow.sort_values("award_amount_yen", ascending=False)

    bins = [-1, 1e7, 5e7, 1e8, 5e8, float("inf")]
    labels = ["1,000万円未満", "1,000万～5,000万円", "5,000万～1億円", "1億～5億円", "5億円以上"]
    narrow["project_size_band"] = pd.cut(narrow["award_amount_yen"], bins=bins, labels=labels)
    size_summary = (narrow.groupby("project_size_band", observed=False)
                    .agg(contract_count=("record_id", "size"), award_amount_yen=("award_amount_yen", "sum")).reset_index())
    size_summary["contract_share_pct"] = size_summary["contract_count"] / len(narrow) * 100
    size_summary["amount_share_pct"] = size_summary["award_amount_yen"] / narrow["award_amount_yen"].sum() * 100

    vendor = (narrow.groupby("vendor_name_canonical", dropna=False)["award_amount_yen"]
              .agg(contract_count="size", award_amount_yen="sum", mean_yen="mean", median_yen="median",
                   p75_yen=lambda s: s.quantile(.75), p90_yen=lambda s: s.quantile(.90), max_yen="max").reset_index())
    vendor["first_fiscal_year"] = vendor["vendor_name_canonical"].map(narrow.groupby("vendor_name_canonical")["fiscal_year"].min())
    vendor["last_fiscal_year"] = vendor["vendor_name_canonical"].map(narrow.groupby("vendor_name_canonical")["fiscal_year"].max())
    vendor = vendor.sort_values("award_amount_yen", ascending=False)

    narrow.to_csv(OUTPUT / "consulting_research_narrow_2016_2025.csv", index=False, encoding="utf-8-sig")
    vendor.to_csv(OUTPUT / "consulting_research_vendor_summary_2016_2025.csv", index=False, encoding="utf-8-sig")
    size_summary.to_csv(OUTPUT / "consulting_research_size_distribution_2016_2025.csv", index=False, encoding="utf-8-sig")

    large = narrow[narrow["project_size_band"].isin(["1億～5億円", "5億円以上"])].copy()
    large.to_csv(OUTPUT / "consulting_research_large_projects_2016_2025.csv", index=False, encoding="utf-8-sig")
    large_year = (large.groupby(["fiscal_year", "project_size_band"], observed=False)
                  .agg(contract_count=("record_id", "size"), award_amount_yen=("award_amount_yen", "sum")).reset_index())
    large_ministry = (large.groupby(["project_size_band", "ordering_body_name"], observed=False)
                      .agg(contract_count=("record_id", "size"), award_amount_yen=("award_amount_yen", "sum")).reset_index())
    large_ministry["band_amount_share_pct"] = large_ministry["award_amount_yen"] / large_ministry.groupby("project_size_band", observed=False)["award_amount_yen"].transform("sum") * 100
    large_ministry.to_csv(OUTPUT / "consulting_research_large_by_ministry_2016_2025.csv", index=False, encoding="utf-8-sig")

    yearly = (narrow.groupby("fiscal_year").agg(contract_count=("record_id", "size"), award_amount_yen=("award_amount_yen", "sum")).reset_index())
    yearly_rows = "".join(f"<tr><td>{int(r.fiscal_year)}</td><td>{int(r.contract_count):,}</td><td>{money_oku(r.award_amount_yen)}</td></tr>" for r in yearly.itertuples(index=False))
    max_size_count = max(int(size_summary["contract_count"].max()), 1)
    size_rows = "".join(
        f"<tr><td>{r.project_size_band}</td><td>{int(r.contract_count):,}</td><td>{r.contract_share_pct:.1f}%</td>"
        f"<td>{money_oku(r.award_amount_yen)}</td><td>{r.amount_share_pct:.1f}%</td>"
        f"<td><div class='bar' style='width:{100*r.contract_count/max_size_count:.1f}%'></div></td></tr>"
        for r in size_summary.itertuples(index=False)
    )
    year_pivot_count = large_year.pivot(index="fiscal_year", columns="project_size_band", values="contract_count").fillna(0)
    year_pivot_amount = large_year.pivot(index="fiscal_year", columns="project_size_band", values="award_amount_yen").fillna(0)
    large_year_rows = "".join(
        f"<tr><td>{int(year)}</td><td>{int(year_pivot_count.loc[year, '1億～5億円']):,}</td>"
        f"<td>{money_oku(year_pivot_amount.loc[year, '1億～5億円'])}</td>"
        f"<td>{int(year_pivot_count.loc[year, '5億円以上']):,}</td><td>{money_oku(year_pivot_amount.loc[year, '5億円以上'])}</td></tr>"
        for year in year_pivot_count.index
    )
    ministry_tables = []
    for band in ["1億～5億円", "5億円以上"]:
        rows = large_ministry[large_ministry["project_size_band"] == band].sort_values("award_amount_yen", ascending=False).head(12)
        row_html = "".join(
            f"<tr><td>{html.escape(str(r.ordering_body_name))}</td><td>{int(r.contract_count):,}</td>"
            f"<td>{money_oku(r.award_amount_yen)}</td><td>{r.band_amount_share_pct:.1f}%</td></tr>"
            for r in rows.itertuples(index=False)
        )
        ministry_tables.append(f"<h3>{band}</h3><table><thead><tr><th>発注機関</th><th>件数</th><th>落札額（億円）</th><th>規模帯内シェア</th></tr></thead><tbody>{row_html}</tbody></table>")
    theme_patterns = {
        "統計・大規模データ収集": r"統計|実態調査|アンケート|データ集計|動向調査",
        "デジタル・通信・技術実証": r"DX|ＤＸ|AI|ＡＩ|デジタル|通信|技術|サイバー|IoT|ＩｏＴ|情報",
        "政策モデル・制度検討": r"政策|制度|モデル|検討|評価|実証",
        "環境・エネルギー": r"環境|エネルギー|脱炭素|温室効果|気候",
        "医療・福祉・こども": r"医療|健康|福祉|こども|介護|予防接種",
    }
    theme_rows = []
    for theme, pattern in theme_patterns.items():
        cells = []
        for band in ["1億～5億円", "5億円以上"]:
            band_data = large[large["project_size_band"] == band]
            matched = band_data["procurement_title"].fillna("").str.contains(pattern, case=False, regex=True)
            cells.extend([f"{int(matched.sum()):,}", money_oku(band_data.loc[matched, "award_amount_yen"].sum())])
        theme_rows.append(f"<tr><td>{theme}</td><td>{cells[0]}</td><td>{cells[1]}</td><td>{cells[2]}</td><td>{cells[3]}</td></tr>")
    large_case_sections = []
    for band in ["1億～5億円", "5億円以上"]:
        rows = large[large["project_size_band"] == band].nlargest(15, "award_amount_yen")
        row_html = "".join(
            f"<tr><td>{int(r.fiscal_year)}</td><td class='wrap'>{html.escape(str(r.procurement_title))}</td>"
            f"<td>{html.escape(str(r.vendor_name_canonical))}</td><td>{html.escape(str(r.ordering_body_name))}</td>"
            f"<td>{money_oku(r.award_amount_yen)}</td></tr>" for r in rows.itertuples(index=False)
        )
        large_case_sections.append(f"<h3>{band}・代表案件</h3><table><thead><tr><th>年度</th><th>案件名</th><th>受注者</th><th>発注機関</th><th>落札額（億円）</th></tr></thead><tbody>{row_html}</tbody></table>")
    top_vendor_rows = "".join(
        f"<tr><td>{html.escape(str(r.vendor_name_canonical))}</td><td>{int(r.contract_count):,}</td>"
        f"<td>{money_oku(r.award_amount_yen)}</td><td>{r.mean_yen/1e4:,.0f}</td><td>{r.median_yen/1e4:,.0f}</td>"
        f"<td>{r.p90_yen/1e4:,.0f}</td><td>{money_oku(r.max_yen)}</td></tr>"
        for r in vendor.head(30).itertuples(index=False)
    )
    median_vendor = vendor[vendor["contract_count"] >= 5].sort_values("median_yen", ascending=False).head(30)
    median_rows = "".join(
        f"<tr><td>{html.escape(str(r.vendor_name_canonical))}</td><td>{int(r.contract_count):,}</td>"
        f"<td>{r.median_yen/1e4:,.0f}</td><td>{r.mean_yen/1e4:,.0f}</td><td>{r.p90_yen/1e4:,.0f}</td><td>{money_oku(r.award_amount_yen)}</td></tr>"
        for r in median_vendor.itertuples(index=False)
    )
    focus_names = ["アクセンチュア", "三菱総合研究所", "野村総合研究所", "PwCコンサルティング", "ボストン コンサルティング グループ"]
    focus = vendor.set_index("vendor_name_canonical").reindex(focus_names).dropna(subset=["contract_count"])
    focus_rows = "".join(
        f"<tr><td>{html.escape(str(name))}</td><td>{int(r.contract_count):,}</td><td>{money_oku(r.award_amount_yen)}</td>"
        f"<td>{r.mean_yen/1e4:,.0f}</td><td>{r.median_yen/1e4:,.0f}</td><td>{r.p75_yen/1e4:,.0f}</td>"
        f"<td>{r.p90_yen/1e4:,.0f}</td><td>{money_oku(r.max_yen)}</td></tr>" for name, r in focus.iterrows()
    )
    top_case_rows = "".join(
        f"<tr><td>{int(r.fiscal_year)}</td><td class='wrap'>{html.escape(str(r.procurement_title))}</td>"
        f"<td>{html.escape(str(r.vendor_name_canonical))}</td><td>{html.escape(str(r.ordering_body_name))}</td><td>{money_oku(r.award_amount_yen)}</td></tr>"
        for r in narrow.head(50).itertuples(index=False)
    )
    document = f"""<!doctype html><html lang='ja'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>狭義・調査研究コンサル分析 2016–2025</title><style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans JP',sans-serif;background:#f4f7fb;color:#172033;margin:0}}main{{max-width:1180px;margin:auto;padding:32px}}section,.card{{background:#fff;border-radius:12px;padding:20px;box-shadow:0 3px 16px #20304a12}}section{{margin:18px 0;overflow:auto}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:22px 0}}.big{{font-size:26px;font-weight:700;color:#155eef}}.note{{color:#5d687c;font-size:13px;line-height:1.7}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{padding:8px;border-bottom:1px solid #e6eaf0;text-align:right;white-space:nowrap}}th:first-child,td:first-child{{text-align:left}}.wrap{{white-space:normal;min-width:360px;text-align:left}}.bar{{height:13px;background:#4f7cff;border-radius:3px;min-width:2px}}code{{background:#eef2f7;padding:2px 5px}}@media(max-width:760px){{main{{padding:14px}}.cards{{grid-template-columns:1fr 1fr}}}}
</style></head><body><main><h1>狭義の調査・研究コンサル分析</h1><p class='note'>2016～2025年度。広義コンサル案件から、レポート型の調査・研究案件を抽出し、システム関連・建設インフラ調査を除外。</p>
<div class='cards'><div class='card'><div>狭義案件</div><div class='big'>{len(narrow):,}件</div></div><div class='card'><div>落札額</div><div class='big'>{money_oku(narrow.award_amount_yen.sum())}億円</div></div><div class='card'><div>平均</div><div class='big'>{narrow.award_amount_yen.mean()/1e4:,.0f}万円</div></div><div class='card'><div>中央値</div><div class='big'>{narrow.award_amount_yen.median()/1e4:,.0f}万円</div></div></div>
<section><h2>抽出条件</h2><p>母集団は2016～2025年度の広義コンサル関連案件 {len(base):,}件。案件名に「委託調査」「調査研究」「実態調査」「動向調査」「市場調査」「アンケート調査」「評価業務」「効果検証」「調査分析」「調査業務」等を含むものを抽出しました。</p><p>案件名に「システム」「ソフトウェア」「アプリ」「クラウド」「ネットワーク」「サーバ」「開発・運用・保守・改修業務」等を含むもの、または地質・測量・施工・工事・土木・設計・施設整備等の建設インフラ調査は除外しています。</p><p class='note'>名称による機械判定です。調査名でもデータ処理を大きく含む案件や、システムという語を使わない技術実証は残る場合があります。逆に、政策調査でも除外語を含めば対象外になります。</p></section>
<section><h2>年度別推移</h2><table><thead><tr><th>年度</th><th>件数</th><th>落札額（億円）</th></tr></thead><tbody>{yearly_rows}</tbody></table></section>
<section><h2>案件規模帯の分布</h2><table><thead><tr><th>規模帯</th><th>件数</th><th>件数比</th><th>落札額（億円）</th><th>金額比</th><th>件数分布</th></tr></thead><tbody>{size_rows}</tbody></table></section>
<section><h2>大型調査案件は増えているか</h2><table><thead><tr><th>年度</th><th>1～5億円 件数</th><th>同 落札額（億円）</th><th>5億円以上 件数</th><th>同 落札額（億円）</th></tr></thead><tbody>{large_year_rows}</tbody></table><p>1～5億円の案件は2016年度の8件から2025年度には49件へ、5億円以上は1件から7件へ増加しました。2016～2018年度と2023～2025年度の各3年間を比べても、大型案件の件数・金額はいずれも約3～4倍です。</p><p class='note'>5億円以上の金額は年度ごとの振れが大きく、2020年度は内閣官房の94.7億円案件が全体を押し上げています。件数の増加と、単発の超大型案件による金額増は分けて読む必要があります。</p></section>
<section><h2>大型案件の主な特徴</h2><table><thead><tr><th>特徴</th><th>1～5億円 件数</th><th>同 落札額（億円）</th><th>5億円以上 件数</th><th>同 落札額（億円）</th></tr></thead><tbody>{''.join(theme_rows)}</tbody></table><p>1～5億円では、デジタル・通信・技術実証、政策モデル・制度検討、環境・医療などテーマが比較的分散しています。5億円以上では、統計・大規模データ収集とデジタル・技術実証への集中が強くなります。</p><p class='note'>特徴は案件名キーワードによる重複分類です。各行を合計しても規模帯全体とは一致しません。</p>{''.join(large_case_sections)}</section>
<section><h2>大型案件の発注機関</h2>{''.join(ministry_tables)}<p>予想された経済産業省・内閣府よりも、総務省の比重が大きい結果です。1～5億円では総務省30.3%、環境省16.9%、厚生労働省12.3%。5億円以上では総務省30.7%、国土交通省29.5%、内閣官房19.5%、デジタル庁10.8%でした。</p><p>国土交通省の5億円以上は、地価調査のデータ集計・分析業務が中心です。内閣官房はコロナ後の主要技術実証、総務省は通信・AI・地域課題モデルや大規模統計、デジタル庁は技術実証型の調査研究が目立ちます。同じ「調査研究」でも、政策レポートだけでなく、大規模データ処理や実証事業を含む点に注意が必要です。</p></section>
<section><h2>主要5社の案件規模分布</h2><table><thead><tr><th>受注者</th><th>件数</th><th>総額（億円）</th><th>平均（万円）</th><th>中央値（万円）</th><th>第3四分位（万円）</th><th>上位10%水準（万円）</th><th>最大（億円）</th></tr></thead><tbody>{focus_rows}</tbody></table><p class='note'>中央値は「典型的な案件規模」、上位10%水準と最大値は大型案件への偏りを示します。平均が中央値を大きく上回る会社ほど、少数の大型案件に総額が引き上げられています。</p></section>
<section><h2>受注者別・累積落札額 上位30</h2><table><thead><tr><th>受注者</th><th>件数</th><th>総額（億円）</th><th>平均（万円）</th><th>中央値（万円）</th><th>上位10%水準（万円）</th><th>最大（億円）</th></tr></thead><tbody>{top_vendor_rows}</tbody></table></section>
<section><h2>受注者別・中央値 上位30</h2><p class='note'>偶発的な1件だけで上位になることを避けるため、5件以上の受注者に限定。</p><table><thead><tr><th>受注者</th><th>件数</th><th>中央値（万円）</th><th>平均（万円）</th><th>上位10%水準（万円）</th><th>総額（億円）</th></tr></thead><tbody>{median_rows}</tbody></table></section>
<section><h2>案件別・落札額 上位50</h2><table><thead><tr><th>年度</th><th>案件名</th><th>受注者</th><th>発注機関</th><th>落札額（億円）</th></tr></thead><tbody>{top_case_rows}</tbody></table></section>
</main></body></html>"""
    (OUTPUT / "consulting_research_report_2025.html").write_text(document, encoding="utf-8")
    print(f"narrow={len(narrow):,}, amount={money_oku(narrow.award_amount_yen.sum())} oku")


if __name__ == "__main__":
    main()
