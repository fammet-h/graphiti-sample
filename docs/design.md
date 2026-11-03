# 設計

## 構成

Docker Compose で `frontend`、`api`、`neo4j` を起動する。フロントエンドは Vite の開発サーバー、API は FastAPI、Graphiti Core は API プロセス内で利用する。Graphiti が Neo4j に時系列グラフを保存する。

```mermaid
flowchart LR
  U[ブラウザー] -->|HTTP| F[Svelte / Vite]
  F -->|REST| A[FastAPI]
  A --> G[Graphiti Core]
  G --> N[(Neo4j)]
  G --> L[LLM / Embedding API]
```

## API

### `POST /api/episodes`

リクエスト: `{ "text": "投入するテキスト" }`

処理: テキストを Graphiti の `add_episode` に渡す。エピソード名は固定のサンプル名、エピソード種別は text、`group_id` は `default` とする。

レスポンス: `{ "status": "ok" }`

### `POST /api/chat`

リクエスト: `{ "message": "質問" }`

処理: Graphiti の検索 API で関連する関係・ノードを取得し、その結果から簡潔な回答文を組み立てる。チャット自体に別の LLM 呼び出しは行わない。

レスポンス: `{ "answer": "回答", "nodes": [{ "id": "...", "name": "..." }], "edges": [{ "id": "...", "source": "ノードID", "target": "ノードID", "name": "関係" }] }`

Graphiti の結果をこの画面用の JSON に変換する。ノード・関係は検索結果に含まれる範囲に限る。

## 画面

- 上部に「チャット」「データ投入」の切り替えを配置する。
- チャットは左右 1:1 程度の2ペインとする。左にメッセージ一覧と入力欄、右に SVG で描くグラフを置く。
- グラフは Cytoscape.js の `cose` レイアウトでノードと関係を表示する。
- データ投入はテキストエリア、送信ボタン、バックグラウンド状態付きドキュメント一覧で構成する。
- 登録要求時に UUID と `queued` 状態を作り、FastAPI `BackgroundTasks` で Graphiti に登録する。状態は queued / processing / completed / failed とする。
- 一覧 API は Graphiti の `retrieve_episodes` から永続化済みエピソードを読み、実行中の状態と合わせて返す。
- `DELETE /api/episodes/{episode_id}` は Graphiti の `remove_episode` を呼び、該当するエピソードとそれだけに属するグラフ要素を削除する。

## Compose と設定

- `neo4j`: Neo4j 5.26、データは名前付きボリュームに保存。
- `api`: FastAPI と Graphiti Core。チャット用と埋め込み用 API の URL / モデル / ベクトル次元を環境変数で受け取る。
- `frontend`: Vite 開発サーバー。`/api` を `api` サービスへプロキシする。
- Python の依存関係は uv で管理し、Python 3.14 を使う。各サービスのビルド手順は Compose の `dockerfile_inline` に置く。
- ホスト公開ポートはフロントエンド `5173`、API `8000`、Neo4j Browser `7474`。
- API 起動前に Neo4j が利用可能であることを Compose の依存関係で示す。
