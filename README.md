# 政府調達・コンサル案件データセット

デジタル庁の調達ポータルで公開されている「落札実績オープンデータ」を年度横断で統合し、コンサル関連案件の抽出・分類・集計を行うデータセットです。

> **データ範囲について**  
> 本データは調達ポータルに登録された政府電子調達システムの**落札実績**です。公告されたものの落札に至らなかった案件などを含む「全入札公告」ではありません。

## データ出典と対象期間

- 出典: [デジタル庁 調達ポータル「落札実績オープンデータ」](https://www.p-portal.go.jp/pps-web-biz/UAB02/OAB0201)
- 入力: 年度別全件ZIP（CSV、UTF-8 BOM付き）
- 取得対象: 2013年から実行時点の年まで（既定値）
- 年度: 契約日を基準とする日本の会計年度（4月から翌年3月）
- 当年度: 年度途中の暫定値であり、過年度との単純比較には注意が必要

## 出力ファイル

すべて `output/` に作成されます。

| ファイル | 内容 |
|---|---|
| `government_procurement_all_complete.csv` | 原本8項目・原本行・加工列を完全保持した全落札実績。コンサル以外も含む |
| `government_procurement_all.csv` | 旧版の全件統合CSV（互換・比較用） |
| `consulting_procurement.csv` | `consulting_flag_broad=True` の広義コンサル関連案件 |
| `consulting_firm_list.csv` | 登録コンサル会社の一覧。類型、別名、実データ表記、件数、落札額、対象年度を収録 |
| `consulting_summary_by_year.csv` | 会計年度別の件数・落札額 |
| `consulting_summary_by_category_year.csv` | 会計年度・業務カテゴリ別の件数・落札額 |
| `consulting_summary_by_firm_type_year.csv` | 会計年度・主要コンサルファーム類型別の件数・落札額 |
| `consulting_summary_by_ordering_body_year.csv` | 会計年度・発注府省庁別のコンサル案件件数・落札額 |
| `consulting_summary_by_ordering_body_firm.csv` | 発注府省庁・受注者ペア別の件数・落札額・機関内シェア |
| `ordering_body_master.csv` | 公式仕様に基づく府省コード・発注機関名の対応表 |
| `consulting_report.html` | メール添付や共有に使える外部ライブラリ不要の単体HTML |
| `article_ministry_consulting_share.md` / `.html` | 発注機関内シェア上位10組を題材にした記事原稿と共有用HTML |
| `article_series_plan_consulting_dependency.md` | 政府のコンサル依存を上下2回で論じる連載構成案 |
| `consulting_research_narrow_2016_2025.csv` | システム・建設調査を除いた狭義の調査研究案件（金額降順） |
| `consulting_research_vendor_summary_2016_2025.csv` | 狭義案件の受注者別件数、総額、平均、中央値、分位点 |
| `consulting_research_size_distribution_2016_2025.csv` | 狭義案件の規模帯別分布 |
| `consulting_research_large_projects_2016_2025.csv` | 1億円以上の狭義案件一覧 |
| `consulting_research_large_by_ministry_2016_2025.csv` | 大型案件の規模帯・発注機関別集計 |
| `consulting_research_report_2025.html` | 狭義案件の規模・受注者分布レポート |

2026年7月6日取得分の原本は308,742行です。完全保持版 `government_procurement_all_complete.csv` は原本行を削除せず保持し、重複の可能性がある行には `duplicate_flag=True`、分析対象行には `analysis_included=True` を付けます。

## コンサル関連案件の判定

判定ルール本体は [`config/consulting_tags.json`](config/consulting_tags.json) にあります。抽出結果には厳格判定と広義判定の両方を残します。

### 厳格判定

`consulting_flag_strict=True` は、案件名にコンサル業務を示す語が含まれ、除外語に該当しない案件です。受注者が有名なコンサル会社かどうかだけでは厳格判定にしません。

### 広義判定

`consulting_flag_broad=True` は、次のいずれかに該当し、除外語に該当しない案件です。

1. 案件名が厳格判定に該当する
2. 受注者名に「コンサルティング」「コンサルタント」「総合研究所」「リサーチ」「シンクタンク」「アドバイザリー」などを含む
3. 受注者が主要コンサルファームマスターに該当する

広義判定は、有名ファームが受注した案件を案件名にかかわらず把握するための補助的な範囲です。業務内容そのものを比較したい場合は厳格判定、コンサル各社の官公庁受注全体を比較したい場合は広義判定が適しています。

### 除外対象

案件名に次の語を含む場合は、原則としてコンサル関連から除外します。

- 健康診断、警備、清掃、印刷
- 翻訳、通訳
- 人材派遣、労働者派遣
- 機器賃貸、物品購入

除外結果は `exclusion_flag` に保持します。ルールは今後、誤判定の確認に応じて追加・修正できます。

## 業務カテゴリ

案件名のキーワードにより、以下のカテゴリを付与します。

| カテゴリ | 主な判定対象 |
|---|---|
| 戦略・政策 | 政策立案、政策調査、戦略策定、基本構想・計画、ロードマップ、BPR、伴走支援 |
| 調査・研究 | 調査研究、実態・動向・市場調査、アンケート、ヒアリング、効果検証、評価分析 |
| デジタル・IT | DX、ITコンサル、システム最適化・計画、要件定義支援、PMO、CIO補佐 |
| 組織・人材 | 人材育成、組織改革、研修企画、働き方改革、採用支援 |
| 広報・マーケティング | 広報・プロモーション戦略、マーケティング、ブランディング、情報発信支援 |
| 財務・会計 | 財務アドバイザリー、会計コンサル、経営分析、事業性評価、費用便益分析 |
| 建設・インフラ | 建設コンサル、設計、測量、地質調査、施工監理、発注者支援 |
| その他コンサル | 一般的なコンサル・支援・検討・調査語には該当するが、上記の個別カテゴリに該当しない案件 |

1案件が複数カテゴリに該当する場合、`consulting_categories` に `|` 区切りで複数タグを保持します。カテゴリ別集計では各カテゴリに1件ずつ計上するため、カテゴリ合計は案件全体のユニーク件数と一致しない場合があります。

## 主要ファームの分類対象

社名に「コンサル」を含まない企業の取りこぼしを防ぐため、次の主要ファームを別途マスター管理しています。法人格、全角・半角、スペース、旧表記などの別名も登録できます。

| 類型 | 主な対象企業 |
|---|---|
| 戦略系 | マッキンゼー、ボストン コンサルティング グループ、ベイン、ローランド・ベルガー |
| 総合・IT系 | アクセンチュア、デロイト トーマツ コンサルティング、PwCコンサルティング、KPMGコンサルティング、アビームコンサルティング |
| シンクタンク系 | 野村総合研究所、三菱総合研究所、日本総合研究所（株式会社） |
| FAS・財務アドバイザリー系 | PwCアドバイザリー、デロイト トーマツ ファイナンシャルアドバイザリー、KPMG FAS |
| 組織・人事系 | マーサージャパン、ウィリス・タワーズ・ワトソン、リンクアンドモチベーション |

同名別法人を避けるため、「一般財団法人日本総合研究所」は株式会社日本総合研究所のマスターには含めません。

## 受注者名の扱い

- `vendor_name`: 公開データに記載された原表記
- `vendor_name_canonical`: 法人格、旧表記、全角英字などを主要ファーム単位で統一した集計用社名
- `consulting_vendor_category`: 戦略系、総合・IT系などのファーム類型
- `consulting_vendor_match`: マスターのどの別名に一致したかを示す監査用文字列

主要ファーム以外は、原則として原表記を `vendor_name_canonical` に引き継ぎます。共同企業体や連名受注は、元データの受注者欄の記載単位で扱います。

## 集計ルール

- 件数: 原則として落札実績1行を1件として集計
- 落札額: `award_amount_yen` を数値化して合計
- 金額欠損・変換不能: 0円として金額集計し、件数には含める
- 負の金額: 0円に補正
- 全件保存: 原本行は重複を含めてすべて `government_procurement_all_complete.csv` に保存
- 分析時の重複除外: `record_id`、`corporation_number`、`vendor_name` の組み合わせが同一の場合は最後の行のみを採用
- 年度別集計: 契約日の会計年度を使用
- 年平均: HTMLでは対象期間に含まれる年度数で累積値を除算。当年度の途中経過も1年度として含む
- 上位受注者: `vendor_name_canonical` 単位で対象期間の落札額を合計し、降順に表示
- 金額表示: HTMLでは億円単位、CSVでは円単位

## 全リストの主な列

| 列 | 内容 |
|---|---|
| `record_id` | 公開データのレコードID |
| `procurement_title` | 調達件名 |
| `contract_date` | 契約日 |
| `award_amount_yen` | 落札金額（円） |
| `ministry_code` / `ministry_name` | 府省コード・府省名または元データ上の識別値 |
| `bidding_method_code` / `bidding_method_name` | 入札方式コード・名称 |
| `vendor_name` | 受注者の原表記 |
| `vendor_name_canonical` | 集計用の統一受注者名 |
| `corporation_number` | 公式CSV第8項目の法人番号 |
| `reference_id` | 旧コードとの互換用列。内容は法人番号（新規分析では `corporation_number` を使用） |
| `ordering_body_code` / `ordering_body_name` | 公式府省コードと名称化した発注機関 |
| `source_year` | 取得元ZIPの年度 |
| `fiscal_year` | 契約日から算出した会計年度 |
| `consulting_flag_strict` | 案件名による厳格判定 |
| `consulting_flag_broad` | 受注者名・主要ファームも含む広義判定 |
| `consulting_vendor_flag` | 受注者自身が主要ファームまたは受注者名ルールに該当するか |
| `consulting_categories` | 業務カテゴリ（複数の場合は `|` 区切り） |
| `consulting_vendor_category` | 主要ファームの類型 |
| `tag_reason` | 案件名判定または受注者名判定の根拠区分 |
| `exclusion_flag` | 除外語への該当 |
| `duplicate_flag` | 分析上の重複候補 |
| `analysis_included` | 集計対象として採用した行 |

### 原本保持列

公式CSVの8項目は加工前の文字列を次の列にそのまま保持します。

- `source_procurement_item_no`（調達案件番号）
- `source_procurement_item_name`（調達案件名称）
- `source_successful_bid_date`（落札決定日）
- `source_successful_bid_price`（落札価格）
- `source_ministry_code`（府省コード）
- `source_bidding_method_code`（入札方式コード）
- `source_trade_name`（商号又は名称）
- `source_corporation_number`（法人番号）

さらに `source_file_name` と `source_row_number` を保持するため、元ZIP・元行まで追跡できます。

## 実行方法

```powershell
python code/build_consulting_dataset.py
```

初回は公式サイトから年度別ZIPを取得します。取得済みファイルは `data/raw/` にキャッシュされ、2回目以降は再利用されます。

```powershell
# 2020年から2025年の取得・集計
python code/build_consulting_dataset.py --start-year 2020 --end-year 2025

# キャッシュを使わず再取得
python code/build_consulting_dataset.py --refresh

# 既存の全件CSVから2016～2025年度の固定期間レポートを作成
python code/build_period_report.py --start-fy 2016 --end-fy 2025 --output consulting_report_2025.html
```

必要パッケージは `requirements.txt` に記載しています。
