### OpenDerisk

OpenDerisk は AI ネイティブな **Multi-Agent 開発・実行フレームワーク** です。連携するエージェントを構築・デバッグ・実行し、一つの Query を成果物まで導き、その達成経路を人間に可視化します。私たちのビジョンは、すべての本番システムに 7×24 時間協働する AI チームメイトを提供し、複雑なタスクを処理してシステムの安定性を守ることです。

<div align="center">
  <p>
    <a href="https://github.com/derisk-ai/OpenDerisk">
        <img alt="stars" src="https://img.shields.io/github/stars/derisk-ai/OpenDerisk?style=social" />
    </a>
    <a href="https://github.com/derisk-ai/OpenDerisk">
        <img alt="forks" src="https://img.shields.io/github/forks/derisk-ai/OpenDerisk?style=social" />
    </a>
    <a href="https://opensource.org/licenses/MIT">
      <img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-yellow.svg" />
    </a>
     <a href="https://github.com/derisk-ai/OpenDerisk/releases">
      <img alt="Release Notes" src="https://img.shields.io/github/release/derisk-ai/OpenDerisk" />
    </a>
    <a href="https://github.com/derisk-ai/OpenDerisk/issues">
      <img alt="Open Issues" src="https://img.shields.io/github/issues-raw/derisk-ai/OpenDerisk" />
    </a>
    <a href="https://codespaces.new/derisk-ai/OpenDerisk">
      <img alt="Open in GitHub Codespaces" src="https://github.com/codespaces/badge.svg" />
    </a>
  </p>

[**English**](README.md) | [**简体中文**](README.zh.md) | [**日本語**](README.ja.md) | [**動画チュートリアル**](https://www.youtube.com/watch?v=1qDIu-Jwdf0)
</div>

<p align="center">
  <img src="./assets/platform_hero.jpg" width="100%" />
</p>

### ニュース 
- [2026/07] 🔥 ワークスペース中心の実行態と ECP セマンティックレイヤーをリリース；`ReActMasterAgent` 2.3 のレジリエント実行。詳細は [OpenDerisk V0.2 ReleaseNote](./docs/docs/OpenDerisk_v0.2.md)
- [2025/10] OpenDerisk V0.2 をリリース —— 未来志向の Multi-Agent 開発・実行フレームワーク。

### 機能特徴

<p align="center">
  <img src="./assets/features.svg" width="100%" />
</p>

1. **Multi-Agent ビルダー** — 三ペインエディタでエージェントを構築：システム/ユーザープロンプト、コンテキストリソース編成、モデルとパラメータ調整、スキル/MCP バインディング、知識、記憶、リアルタイムデバッグプレビュー。
2. **ワークスペース（シナリオ空間）** — AI ネイティブなホームページ。価値デリバリーを中心に設計し、達成経路（計画 → 実行 → 結果）を表示。タスク、成果物、デリバリー、プレイブック、トリガーを含む。
3. **ReActMasterAgent** — 長時間タスク推論エンジン：デッドループ検出、コンテキスト圧縮、ツール出力切り詰め、履歴プルーニング、段階的プロンプト管理、ワークログ、レポート生成、カンバンタスク計画。
4. **ECP セマンティックレイヤー** — 信頼できる text2SQL とデータ分析。AI がセマンティクス（エンティティ/メトリック/リレーション）を提案し、人間が権限ゲートで確認。数値は確認済みメトリックからのみ。
5. **ナレッジボルト** — 完全な RAG パイプライン。ベクトル（Chroma、Milvus、PGVector 等）、グラフ（Neo4j、TuGraph）、全文検索ストア、S3/OSS ファイルストレージをサポート。
6. **ツール · スキル · MCP** — 組み込みツール（ファイルシステム、シェル、サンドボックス、スケジュール、Todo）、再利用可能なスキルパック、外部サービス接続用 MCP プロトコル。
7. **メディア生成** — 画像・動画生成を第一級のエージェントツールとして提供（OpenAI、Wanxiang、Google Banana、Seedance、Sora）。成果物としてワークスペースに配信。
8. **組み込みシナリオ** — AI-SRE（OpenRCA 根因診断）、DataExpert、フレームグラフアシスタント。すぐに使え、拡張可能。

### アーキテクチャ

<p align="center">
  <img src="./assets/architecture.svg" width="100%" />
</p>

OpenDerisk は 5 つの階層で構成されます：

- **インタラクション・プロダクト層** — ワークスペース（ホーム）、アプリ/エージェントビルダー、チャット/アシスタント（vis_manus デュアルパネルレイアウト）、シーンプロファイル、組み込みシナリオ。
- **エージェント実行層** — `ReActMasterAgent` を中核とする、差し替え可能な推論エンジン（ReACT、Summary ベース、RAG 深度検索、コンテキストエンジニアリング）、サブエージェント、レジリエント実行制御。
- **能力層** — ツール、スキル、MCP、ナレッジボルト、記憶、メディア生成。
- **データ・統合層** — 15 以上のデータソース、ECP セマンティックレイヤー、チャネル（DingTalk/Feishu）、サンドボックス（ローカル/Docker/ブラウザ）。
- **基盤層** — モデル管理（LLM/Embedding/Reranker）、ストレージ・ベクトル、権限/RBAC、監査・可観測性。

ここでのエージェントの本質は**価値デリバリー**です。一つの Query から成果物へ、人間が検査・信頼できる可視的な達成経路を伴います。

### インストール（推奨）

#### curl でのインストール

```shell
# 最新バージョンのダウンロードとインストール
curl -fsSL https://raw.githubusercontent.com/derisk-ai/OpenDerisk/main/install.sh | bash
```

#### 設定ファイル
インストール後、デフォルト設定ファイルは自動的に以下のパスに初期化されます：
`~/.openderisk/configs/derisk-proxy-aliyun.toml`

このファイルを編集し、API キーを設定してください：
```shell
vi ~/.openderisk/configs/derisk-proxy-aliyun.toml
```

#### 起動
```
openderisk-server
```

### ソースからのインストール（開発用）

#### uv のインストール（必須）

**macOS/Linux:**
```shell
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows:**
```shell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

#### クローンと依存関係のインストール

```shell
git clone https://github.com/derisk-ai/OpenDerisk.git

cd OpenDerisk

# uv で依存関係をインストール
uv sync --all-packages --frozen \
    --extra "base" \
    --extra "proxy_openai" \
    --extra "rag" \
    --extra "storage_chromadb" \
    --extra "derisks" \
    --extra "storage_oss2" \
    --extra "client" \
    --extra "ext_base" \
    --extra "channel_dingtalk"
```

> 注意：`channel_dingtalk` はオプションです。DingTalk チャネルのサポートが不要な場合は削除してください。

#### サーバーの起動

**🚀 クイックスタート（ゼロ設定、推奨）**

設定ファイルなしで起動：

```bash
# 方法 1：クイックスタートコマンド
uv run derisk quickstart

# 方法 2：起動スクリプト
./start.sh

# 方法 3：ポート指定
uv run derisk quickstart -p 8888
```

起動後、http://localhost:7777 にアクセスし、Web UI でモデルと設定を構成します。

詳細は [クイックスタートガイド](QUICKSTART.md) を参照してください。

**📝 設定ファイルで起動**

`derisk-proxy-aliyun.toml` で API_KEY を設定し、実行：

```bash
# 設定ファイルで起動
uv run derisk quickstart -c configs/derisk-proxy-aliyun.toml

# または従来の方法
uv run python packages/derisk-app/src/derisk_app/derisk_server.py --config configs/derisk-proxy-aliyun.toml
```

#### ウェブサイトへのアクセス

ブラウザを開いて [`http://localhost:7777`](http://localhost:7777) にアクセス

### 使用方法

#### 基本モジュール
【設定管理】メニューの下にあります：
- **モデル管理** — LLM、Embedding、Reranker モデルの追加/編集/削除（OpenAI、Aliyun、Zhipu、ローカル等）。マルチモデル優先度戦略をサポート。
- **ナレッジベース** — 組み込み RAG 検索パイプラインによるナレッジ管理。
- **MCP** — MCP サービスの管理とデバッグ（CRUD + ツールテスト）。
- **プロンプト** — システム/ユーザープロンプトの統合エディタ。

#### エージェントの構築
【アプリ管理】を開き → エージェントを作成または開く。三ペインエディタで推論エンジン、モデル、スキル/MCP、知識、サブエージェントを構成し、リアルタイムプレビューでデバッグできます。

#### 組み込みシナリオ
* **AI-SRE（OpenRCA 根因診断）**
  - 注意：OpenRCA データセットの [Bank データセット](https://drive.usercontent.google.com/download?id=1enBrdPT3wLG94ITGbSOwUFg9fkLR-16R&export=download&confirm=t&uuid=42621058-41af-45bf-88a6-64c00bfd2f2e) を使用
  - ダウンロード：`gdown https://drive.google.com/uc?id=1enBrdPT3wLG94ITGbSOwUFg9fkLR-16R`
  - データセットを `${derisk}/pilot/datasets` に解凍
* **フレームグラフアシスタント** — ローカルプロセスの Java/Python フレームグラフをアップロードして分析
* **DataExpert** — メトリクス、ログ、トレース、Excel データをアップロードして対話型分析

### 開発
* **エージェント開発** — `packages/derisk-core/src/derisk/agent/expand/`（例：`react_master_agent`）と `packages/derisk-ext/src/derisk_ext/agent/agents/` を参照
* **ツール開発** — スキル（`skills/`）と MCP（Model Context Protocol）
* **DeRisk-Skills 開発** — [derisk-skills](https://github.com/derisk-ai/derisk_skills)

### シナリオデモ
複数のエージェントが協調して複雑なタスクを処理 —— 一つの Query から成果物へ、達成経路が全程可視化：
<p align="center">
  <img src="./assets/scene_demo_new.jpg" width="100%" />
</p>

### 引用
このリポジトリがお役に立ちましたら、ぜひ引用してください：
```
@misc{di2025openderiskindustrialframeworkaidriven,
      title={OpenDerisk: An Industrial Framework for AI-Driven SRE, with Design, Implementation, and Case Studies}, 
      author={Peng Di and Faqiang Chen and Xiao Bai and Hongjun Yang and Qingfeng Li and Ganglin Wei and Jian Mou and Feng Shi and Keting Chen and Peng Tang and Zhitao Shen and Zheng Li and Wenhui Shi and Junwei Guo and Hang Yu},
      year={2025},
      eprint={2510.13561},
      archivePrefix={arXiv},
      primaryClass={cs.SE},
      url={https://arxiv.org/abs/2510.13561}, 
}
```

### 謝辞
- [DB-GPT](https://github.com/eosphoros-ai/DB-GPT)
- [GPT-Vis](https://github.com/antvis/GPT-Vis)
- [MetaGPT](https://github.com/FoundationAgents/MetaGPT)
- [OpenRCA](https://github.com/microsoft/OpenRCA)

OpenDerisk コミュニティは、AI ネイティブなマルチエージェントシステムの構築に専念しています。🛡️ コミュニティがより良いサービスを提供できることを願い、皆様が参加してより良い未来を共に創造することを願っています。🤝


[![Star History Chart](https://api.star-history.com/svg?repos=derisk-ai/OpenDerisk&type=Date)](https://star-history.com/#derisk-ai/OpenDerisk)


### コミュニティグループ

DingTalk グループに参加して、他の開発者と経験を共有しましょう！

<div align="center" style="display: flex; gap: 20px;">
    <img src="assets/derisk-ai.jpg" alt="OpenDerisk Community" width="200" />
</div>
