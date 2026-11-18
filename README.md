# Graphiti Sample

Graphiti と Neo4j を使った、最小構成の時系列ナレッジグラフアプリケーションです。FastAPI がデータ投入とチャット検索を受け持ち、Svelte の画面に回答と検索コンテキストのグラフを表示します。

## 起動

Docker と Docker Compose、OpenAI API キーが必要です。

1. `.env.example` を `.env` にコピーし、API 接続設定を入力します。
2. `docker compose up -d --build` を実行します。
3. ブラウザーで `http://localhost:5173` を開きます。

このリポジトリでは `.env` を作成済みの場合、そのまま起動できます。

API ドキュメントは `http://localhost:8000/docs`、Neo4j Browser は `http://localhost:7474` です。データは `neo4j_data` ボリュームに保存されます。

## 画面

- **チャット**: 左側で質問と回答を表示し、右側で検索結果に含まれるノードと関係を可視化します。
- **データ投入**: テキストを投入し、バックグラウンド登録の状態をドキュメント一覧で確認します。一覧は Graphiti に登録された直近100件のエピソードから再構築されます。

## ドキュメント

- [要件定義](docs/requirements.md)
- [設計](docs/design.md)

## 設定

`.env.example` を参考に `.env` を設定してください。`OPENAI_API_KEY` は必須です。`OPENAI_API_BASE_URL` と `OPENAI_API_MODEL` は OpenAI 互換 API 用、`OPENAI_EMBEDDING_*` は埋め込みモデルの接続設定です。バックエンドは uv と Python 3.14 を使います。
