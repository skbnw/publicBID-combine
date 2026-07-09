# 政府調達サーチ 試作・公開準備レポート

作成日：2026-07-09  
対象リポジトリ：`skbnw/publicBID-combine`  
対象アプリ：政府調達サーチ

## 1. 目的

霞が関とコンサル業界の関係性を共同研究するため、調達ポータル由来の政府調達データを検索・分析できる共有システムの試作版を構築した。

主な目的は以下の通り。

- 政府調達の落札実績を、出典を保ったまま検索できるようにする
- 受注者、発注機関、省庁、契約方式・落札方式ごとに傾向を見られるようにする
- コンサル関連案件を「広義」「狭義」の暫定分類で分析できるようにする
- CSV出力により、共同研究者が再分析できるようにする
- SupabaseとStreamlit Community Cloudを使い、共同研究者向けの非公開アプリとして共有できるようにする

## 2. アプリの主な機能

### 案件検索

以下の条件で調達案件を検索できるようにした。

- 年度
- 案件名キーワード
- コンサル認定：すべて / 広義 / 狭義
- 受注者名
- 発注機関名
- 最低落札額
- 契約方式・落札方式

検索結果には、調達案件番号、案件名、発注機関、受注者、落札額、契約方式などを表示する。

調達ポータルへの外部リンク列は「外部」とし、内部遷移リンクと区別した。

### コンサル検索

広義コンサル判定された受注者を中心に、受注者別の落札件数・落札額・発注機関数を確認できるようにした。

受注者名から案件検索へ遷移し、受注者名が自動入力された状態で検索できるようにした。

### 省庁分析

省庁別に以下を確認できるようにした。

- 件数
- 受注者数
- 発注機関数
- 落札総額
- 広義/狭義コンサル比率
- 上位受注者
- 年度推移
- 発注機関別集計

省庁分析にも「契約方式・落札方式」フィルタを追加した。

### データ概要

政府調達全体、コンサル（広義）、コンサル（狭義）を比較できる概要表を作成した。

## 3. UI・表記の調整

ユーザー確認を踏まえ、以下を修正した。

- アプリ名を「政府調達サーチ」に変更
- キャプションを「出典：調達ポータル　オープンソースデータを検索できます」に変更
- 「アクター」表示を「コンサル検索」に変更
- 「Link」等の外部遷移列を「外部」に変更
- `record_id` は画面表示から除外し、代わりに「調達案件番号」として表示
- 年度表示で `2,014` のようにカンマが入る問題を修正
- 発注機関名プルダウンを省庁順に近い並びへ調整
- 受注者名プルダウンを「広義コンサル上位」だけでなく、政府調達全体の上位受注者も含む候補に拡張

## 4. CSV出力

検索結果をCSVで出力できるようにした。

CSVファイル名には、検索条件が分かるように以下を含める設計にした。

- 年度範囲
- コンサル認定
- 受注者名
- 発注機関名
- 契約方式・落札方式
- キーワード
- 最低落札額

例：

```text
procurement_2013-2026_vendor-アクセンチュア.csv
procurement_2020-2026_広義_周辺領域を含む_vendor-三菱総合研究所_body-経済産業省_method-一般競争入札_総合評価_kw-DX_調査_min100man.csv
```

## 5. データベース構成

ローカル開発ではDuckDBを使用し、本番・共有用にはSupabase PostgreSQLを使用する構成にした。

公開構成は以下の通り。

```text
Streamlit Community Cloud
  ↓ DATABASE_URLをSecretsに保存
Supabase polidata / procurement schema
  ↓
読み取り中心の調達DB
```

Supabaseでは既存の `polidata` プロジェクト内に `procurement` スキーマを作成した。

主なテーブル：

- `procurement.procurements`
- `procurement.actors`
- `procurement.actor_aliases`
- `procurement.actor_relations`
- `procurement.annotations`
- `procurement.data_imports`

## 6. Supabase投入

`db/schema.sql` をSupabase SQL Editorで実行し、スキーマ・テーブル・RLS・読み取り用ロールを作成した。

ローカルDuckDBからSupabaseへ投入するため、`code/load_supabase.py` を整備した。

対応した主な問題：

- `public` スキーマ前提から `procurement` スキーマ前提へ変更
- `--schema procurement` オプションを追加
- `actors` の重複 `actor_id` を投入時に1件へ畳むよう修正
- COPY用一時テーブルから自動採番列 `procurement_id` を除外

投入結果：

```text
Uploaded 308,742 procurements to Supabase
```

## 7. RLS・読み取り権限

Streamlit Community Cloudからは、管理ユーザーではなく読み取り専用ロール `procurement_reader` で接続する方針にした。

初回のRLS設定では、Supabase Authの `authenticated` 向けポリシーのみだったため、PostgreSQL直接接続の `procurement_reader` にはデータが0件に見える問題が発生した。

これに対応するため、以下を追加した。

- `db/add_procurement_reader_policies.sql`
- `procurement_reader` 向けSELECTポリシー
- `grant usage on schema procurement`
- `grant select on all tables in schema procurement`

Supabase SQL Editorで追加SQLを実行し、成功を確認した。

## 8. Streamlit Community Cloud公開方針

初期公開は、共同研究者のみ閲覧できる非公開アプリとする方針にした。

理由：

- 試作段階のため、まず共同研究者だけで動作確認したい
- データはオープンデータ由来だが、分類や名寄せは暫定的である
- 将来的な公開前に、表示・検索・CSV出力・注釈文言を確認したい

Streamlit Community Cloudでは以下を設定する。

```toml
DATABASE_URL = "postgresql://procurement_reader...（Secretsにのみ保存）"
DB_SCHEMA = "procurement"
```

注意：

- `DATABASE_URL` はGitHubにコミットしない
- `.streamlit/secrets.toml` は `.gitignore` 対象
- `.streamlit/secrets.toml.example` のみGitHubに置く

## 9. GitHub管理

GitHubリポジトリ：

```text
https://github.com/skbnw/publicBID-combine.git
```

主なコミット：

- `3cbed9b` Initial Streamlit procurement search app
- `724a2d2` Allow Streamlit reader role through RLS
- `e09d0b2` Expand vendor dropdown candidates

GitHubへ載せないもの：

- `.streamlit/secrets.toml`
- `.env`
- `data/*.duckdb`
- `data/raw/`
- `output/`
- ログファイル
- 秘密情報を含むローカルメモ

## 10. セキュリティ上の注意

作業中に、Supabaseの接続情報やService Role Key、読み取り用パスワードが画面上に表示された。

今後の安全運用のため、以下を推奨する。

- SupabaseのService Role Keyはローテートする
- DB管理ユーザーのパスワードも必要に応じてローテートする
- `procurement_reader` のパスワードも公開設定完了後に再設定する
- Streamlit CloudのSecrets以外に本番接続情報を保存しない
- GitHubにSecretsや実データDBファイルを置かない

## 11. 現在の到達点

2026-07-09時点で、以下まで完了した。

- ローカルStreamlitアプリの主要UI実装
- DuckDB研究DBの構築
- Supabase `procurement` スキーマ作成
- 308,742件の調達データ投入
- Streamlit Community Cloud向けSecrets構成の確定
- RLSポリシー修正
- GitHubへのpush
- 受注者候補プルダウンの拡張

## 12. 次の作業

次に行うべき作業は以下。

1. Streamlit Community CloudでアプリをRebootし、最新コミットを反映する
2. `受注者名（候補）` のプルダウンが表示されるか確認する
3. 案件検索・コンサル検索・省庁分析・CSV出力をCloud上で確認する
4. アプリを非公開に設定し、共同研究者をViewerとして招待する
5. 表示文言、分類定義、主要コンサル候補の妥当性を共同研究者と確認する
6. 秘密情報のローテートを実施する

