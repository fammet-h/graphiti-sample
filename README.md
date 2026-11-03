# Graphiti Sample

Graphiti と Neo4j を使った、最小構成の時系列ナレッジグラフアプリケーションです。FastAPI がデータ投入とチャット検索を受け持ち、Svelte の画面に回答と検索コンテキストのグラフを表示します。

## 起動

Docker と Docker Compose、OpenAI API キーが必要です。

1. `.env.example` を `.env` にコピーし、`OPENAI_API_KEY` を設定します。
2. `docker compose up --build` を実行します。
3. ブラウザーで `http://localhost:5173` を開きます。

API ドキュメントは `http://localhost:8000/docs`、Neo4j Browser は `http://localhost:7474` です。データは `neo4j_data` ボリュームに保存されます。

## 画面

- **チャット**: 左側で質問と回答を表示し、右側で検索結果に含まれるノードと関係を可視化します。
- **データ投入**: テキストを入力し、Graphiti にエピソードとして登録します。

## ドキュメント

- [要件定義](docs/requirements.md)
- [設計](docs/design.md)

## 設定

`.env.example` の `OPENAI_API_KEY` を設定してください。Graphiti の LLM 推論と埋め込み生成に使用します。ローカル開発用の Neo4j 接続情報とポートは Compose ファイルに記載しています。
