# 霞が関・コンサル共同研究DB

## ローカル起動

```powershell
pip install -r requirements.txt
python code/build_research_db.py
streamlit run streamlit_app.py
```

`output/government_procurement_all.csv` から `data/research.duckdb` を生成します。研究DBには案件、受注者アクター、別名を収録し、検索結果をCSVで取得できます。

## 公開構成

初期公開は次の構成にします。

```text
Streamlit Community Cloud
  ↓ DATABASE_URLをSecretsに保存
Supabase polidata / procurement schema
  ↓
読み取り中心の調達DB
```

Supabaseは既存の `polidata` プロジェクトを使い、既存データと混ざらないように `procurement` スキーマへ調達DBを作成します。

## 共有と認証

初期運用はStreamlit Community Cloudの非公開アプリを使い、共同研究者をメールアドレスでViewer招待します。アプリ内にBasic認証は実装しません。共通ID・パスワードの共有、総当たり対策、失効、監査が弱いためです。

利用者やアプリが増えた場合は、StreamlitのOIDC（`st.login`）をGoogleまたはMicrosoftのID基盤につなぎます。認証は本人確認にすぎないため、データの読み書き権限はSupabaseのRow Level Securityで別途制御します。

## 試作版と本番版

- 試作版：DuckDB。高速で設定不要だが、Cloud上のローカルファイルは共同編集の正本にしない。
- 本番版：Supabase PostgreSQL。`polidata` プロジェクト内の `procurement` スキーマに `db/schema.sql` を適用し、原票の一括投入と差分更新を行う。
- 原票・整形値・名寄せ・研究者による解釈を別々に保持し、出典URL、作成者、更新日時を残す。

## 更新手順

1. `python code/build_consulting_dataset.py --refresh` で年度ZIPを更新する。
2. `python code/build_research_db.py` でローカル研究DBを再構築する。
3. 件数、対象年度、主要集計を確認する。
4. 本番移行後は、同じ変換結果をステージングテーブルへ投入し、`source_file_name + source_row_number` をキーにupsertする。

## Supabaseへの初期投入

1. Supabaseの既存 `polidata` プロジェクトを開く。
2. SQL Editorで `db/schema.sql` を実行し、`procurement` スキーマとテーブルを作成する。
3. SQL Editorで `procurement_reader` に強いパスワードを設定する。

   ```sql
   alter role procurement_reader with password 'REPLACE_WITH_STRONG_PASSWORD';
   ```

4. DashboardのConnect画面からDirect connection URIを取得する。
5. 初期投入用に、管理ユーザーのURIをローカル環境変数へ設定する。

   ```powershell
   $env:DATABASE_URL = "postgresql://postgres.PROJECT_REF:PASSWORD@HOST:5432/postgres?sslmode=require"
   $env:DB_SCHEMA = "procurement"
   ```

   Supabaseの接続形式はプロジェクト設定により異なるため、DashboardのConnect画面のURI形式に合わせる。

6. 初回だけ `--replace` つきで投入する。

   ```powershell
   python code/load_supabase.py --replace
   ```

7. Streamlit Community Cloud用には、URIのユーザー名とパスワードを `procurement_reader` 用に置き換える。

8. Streamlit Community CloudのSecretsへ `.streamlit/secrets.toml.example` と同じ形式で登録する。

通常更新では `--replace` を外します。ステージングテーブルへCOPYした後、出典ファイル名と行番号をキーにupsertされます。`--replace` は既存の案件・アクター台帳を消して再投入するため、初期構築または全面再構築時だけ使用します。

## Streamlit Community Cloudへの登録

1. GitHubにこのリポジトリをpushする。
2. Streamlit Community Cloudで `streamlit_app.py` を指定してアプリを作成する。
3. App settings > Secrets に以下を登録する。

   ```toml
   DATABASE_URL = "postgresql://procurement_reader.PROJECT_REF:PASSWORD@HOST:5432/postgres?sslmode=require"
   DB_SCHEMA = "procurement"
   ```

4. アプリを再起動し、画面左下のDB表示が `Supabase PostgreSQL` になっていることを確認する。
