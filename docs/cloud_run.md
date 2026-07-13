# Cloud Run deployment

政府調達検索βを Google Cloud Run で動かすためのメモです。

## 方針

Streamlit Community Cloudで不安定な場合は、Cloud Runに分離して載せる。

- アプリ本体: このリポジトリの `streamlit_app.py`
- データベース: Supabase PostgreSQL
- 必須環境変数:
  - `DATABASE_URL`
  - `DB_SCHEMA=procurement`
- サブパス運用時の環境変数:
  - `STREAMLIT_BASE_URL_PATH=procurement`

## `/procurement` 配下で動かす場合

Cloud Runサービス自体を直接開く場合でも、`STREAMLIT_BASE_URL_PATH=procurement` を設定すると、アプリのURLは次の形になります。

```text
https://SERVICE-xxxxx.run.app/procurement
```

既存の `kokkai-nexus` のサブフォルダとして見せたい場合は、`kokkai-nexus` 側で次のどちらかが必要です。

1. 既存アプリ内にStreamlitアプリを組み込む
2. `/procurement/*` をこのCloud Runサービスへ中継するリバースプロキシを追加する

単に別Cloud Runサービスを作るだけでは、既存URL
`https://kokkai-nexus-305630672228.asia-northeast1.run.app/procurement`
には自動では生えません。

## 例: gcloud deploy

実際の `DATABASE_URL` はSecretsや環境変数で設定し、GitHubにはコミットしないでください。

```powershell
gcloud run deploy publicbid-search `
  --source . `
  --region asia-northeast1 `
  --allow-unauthenticated `
  --set-env-vars DB_SCHEMA=procurement,STREAMLIT_BASE_URL_PATH=procurement `
  --set-secrets DATABASE_URL=DATABASE_URL_SECRET:latest
```

Secret Managerを使わずに一時的に環境変数で設定する場合は、`DATABASE_URL` の値が履歴やログに残らないよう注意してください。

## 推奨

まずは別Cloud Runサービスとして安定動作を確認し、その後に `kokkai-nexus` 側の `/procurement` パスへ接続するのが安全です。
