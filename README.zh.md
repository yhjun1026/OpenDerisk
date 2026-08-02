### OpenDerisk

OpenDerisk 是一个 AI 原生的 **Multi-Agent（多智能体）开发与运行框架**。它让你能够构建、调试并运行协同工作的智能体，将一个 Query 转化为可交付的结果，并将达成路径完整地展示给人。我们的愿景是为每一个生产系统提供一个 7×24 小时协同工作的 AI 队友，处理复杂任务并守护系统的稳定性。

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

[**English**](README.md) | [**简体中文**](README.zh.md) | [**日本語**](README.ja.md) | [**视频教程**](https://www.youtube.com/watch?v=1qDIu-Jwdf0)
</div>

<p align="center">
  <img src="./assets/platform_hero.jpg" width="100%" />
</p>

### 最新动态
- [2026/07] 🔥 工作空间运行态与 ECP 语义层上线；`ReActMasterAgent` 2.3 韧性执行能力。详见 [OpenDerisk V0.2 ReleaseNote](./docs/docs/OpenDerisk_v0.2.md)
- [2025/10] 发布 OpenDerisk V0.2 —— 面向未来的 Multi-Agent 开发与运行产品框架。

### 核心特性

<p align="center">
  <img src="./assets/features.svg" width="100%" />
</p>

1. **多智能体构建框架** — 三栏编辑器中完成智能体构建：系统/用户提示词、上下文资源编排、模型与参数调优、技能/MCP 绑定、知识、记忆，以及实时调试预览。
2. **工作空间（场景空间）** — AI 原生首页。围绕价值交付设计，展示达成路径（规划 → 执行 → 结果），包含任务、产物、交付物、剧本与触发器。
3. **ReActMasterAgent** — 长程任务推理引擎：死循环检测、上下文压缩、工具输出截断、历史裁剪、分阶段提示词管理、工作日志、报告生成与看板任务规划。
4. **ECP 语义层** — 可信的 text2SQL 与数据分析。AI 提议语义（实体/指标/关系），人工通过权限门确认，数字只能来自已确认指标。
5. **知识库** — 完整 RAG 流程，覆盖向量（Chroma、Milvus、PGVector 等）、图（Neo4j、TuGraph）与全文检索，支持 S3/OSS 文件存储。
6. **工具 · 技能 · MCP** — 内置工具（文件系统、Shell、沙箱、调度、待办）、可复用技能包，以及 MCP 协议接入外部服务。
7. **媒体生成** — 图像与视频生成作为一等公民智能体工具（OpenAI、通义万相、Google Banana、Seedance、Sora），以产物形式在工作空间交付。
8. **内置场景** — AI-SRE（OpenRCA 根因诊断）、DataExpert、火焰图助手，开箱即用且可扩展。

### 架构方案

<p align="center">
  <img src="./assets/architecture.svg" width="100%" />
</p>

OpenDerisk 分为五层：

- **交互与产品层** — 工作空间（首页）、应用/智能体构建器、对话/助手（vis_manus 双面板布局）、场景配置与内置场景。
- **智能体运行层** — 以 `ReActMasterAgent` 为核心，可插拔推理引擎（ReACT、基于 Summary、RAG 深度检索、上下文工程），子智能体与韧性执行控制。
- **能力层** — 工具、技能、MCP、知识库、记忆与媒体生成。
- **数据与集成层** — 15+ 数据源、ECP 语义层、渠道（钉钉/飞书）与沙箱（本地/Docker/浏览器）。
- **基础层** — 模型管理（LLM/Embedding/Reranker）、存储与向量库、权限/RBAC、审计与可观测性。

这里智能体的本质是**价值交付**：从一个 Query 到可交付的结果，并带有可视、可信的达成路径。

### 技术思考与分享

我们在构建 OpenDerisk 的过程中沉淀了一些技术思考，作为项目的设计积累持续维护。

- [三层 Loop 工程时代：OpenDerisk 的技术思考与实践](./docs/Three_Layer_Loop_Engineering.md) — 从 Prompt 到 Loop，AI 产品正从"一次性回答"走向"持续参与"。本文梳理 AI 工程的五个演进时代，拆解 OpenDerisk 如何通过 L1 LLM Loop / L2 Agent Loop / L3 业务场景 Loop 三层嵌套循环，配合业务数据自主飞轮进化，构建一个"团队原生、越用越强"的 AI 产品。

### 安装（推荐）

#### 使用 curl 安装

```shell
# 下载并安装最新版本
curl -fsSL https://raw.githubusercontent.com/derisk-ai/OpenDerisk/main/install.sh | bash
```

#### 配置文件
安装完成后，默认配置文件已自动初始化到：
`~/.openderisk/configs/derisk-proxy-aliyun.toml`

编辑该文件并设置您的 API 密钥：
```shell
vi ~/.openderisk/configs/derisk-proxy-aliyun.toml
```

#### 启动
```
openderisk-server
```

### 从源码安装（开发环境）

#### 安装 uv（必需）

**macOS/Linux:**
```shell
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows:**
```shell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

#### 克隆项目并安装依赖

```shell
git clone https://github.com/derisk-ai/OpenDerisk.git

cd OpenDerisk

# 使用 uv 安装依赖
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

> 注意：`channel_dingtalk` 为可选依赖，若不需要钉钉渠道支持可移除此行。

#### 启动服务

**🚀 快速启动（零配置，推荐）**

无需任何配置文件，直接启动：

```bash
# 方式一：使用快速启动命令
uv run derisk quickstart

# 方式二：使用启动脚本
./start.sh

# 方式三：指定端口
uv run derisk quickstart -p 8888
```

启动后访问 http://localhost:7777，通过 Web UI 配置模型和其他设置。

详细说明请查看: [快速启动指南](QUICKSTART.md)

**📝 使用配置文件启动**

在 `derisk-proxy-aliyun.toml` 中配置 API_KEY，然后运行：

```bash
# 使用配置文件启动
uv run derisk quickstart -c configs/derisk-proxy-aliyun.toml

# 或使用传统方式
uv run python packages/derisk-app/src/derisk_app/derisk_server.py --config configs/derisk-proxy-aliyun.toml
```

#### 访问 Web 界面

打开浏览器访问 [`http://localhost:7777`](http://localhost:7777)

### 使用说明

#### 基础模块
位于【配置管理】菜单下：
- **模型管理** — 新增/编辑/删除 LLM、Embedding、Reranker 模型（OpenAI、阿里云、智谱、本地等）。支持多模型优先级策略。
- **知识库** — 基于内置 RAG 检索流程管理知识。
- **MCP** — 管理与调试 MCP 服务（增删改查 + 工具测试）。
- **提示词** — 统一的系统/用户提示词编写与管理界面。

#### 构建智能体
打开【应用管理】→ 创建或打开智能体。三栏编辑器可配置推理引擎、模型、技能/MCP、知识与子智能体，并通过实时预览调试。

#### 内置场景
* **AI-SRE（OpenRCA 根因定位）**
  - 注意：默认使用 OpenRCA 数据集中的 [Bank 数据集](https://drive.usercontent.google.com/download?id=1enBrdPT3wLG94ITGbSOwUFg9fkLR-16R&export=download&confirm=t&uuid=42621058-41af-45bf-88a6-64c00bfd2f2e)
  - 下载命令：`gdown https://drive.google.com/uc?id=1enBrdPT3wLG94ITGbSOwUFg9fkLR-16R`
  - 下载后解压到 `${derisk项目}/pilot/datasets`
* **火焰图助手** — 上传本地应用服务进程的火焰图（Java/Python）进行分析
* **DataExpert** — 上传指标、日志、Trace 等 Excel 表格数据进行对话分析

### 开发
* **智能体开发** — 参考 `packages/derisk-core/src/derisk/agent/expand/`（如 `react_master_agent`）与 `packages/derisk-ext/src/derisk_ext/agent/agents/`
* **工具开发** — 技能（`skills/`）与 MCP（Model Context Protocol）
* **DeRisk-Skills 开发** — [derisk-skills](https://github.com/derisk-ai/derisk_skills)

### 场景演示
多智能体协同处理复杂任务 —— 从一个 Query 到可交付的结果，达成路径全程可见：
<p align="center">
  <img src="./assets/scene_demo_new.jpg" width="100%" />
</p>

### 引用
如对您的工作有帮助，请引用以下论文:
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

### 致谢 
- [DB-GPT](https://github.com/eosphoros-ai/DB-GPT)
- [GPT-Vis](https://github.com/antvis/GPT-Vis)
- [MetaGPT](https://github.com/FoundationAgents/MetaGPT)
- [OpenRCA](https://github.com/microsoft/OpenRCA)

OpenDerisk 社区致力于构建 AI 原生的多智能体系统。🛡️ 我们希望社区能够为您提供更好的服务，同时也期待您的加入，共同创造更美好的未来。🤝


[![Star History Chart](https://api.star-history.com/svg?repos=derisk-ai/OpenDerisk&type=Date)](https://star-history.com/#derisk-ai/OpenDerisk)

### 社区 

加入钉钉群，与我们一起交流讨论:

<div align="center" style="display: flex; gap: 20px;">
    <img src="assets/derisk-ai.jpg" alt="OpenDerisk 交流群" width="300" />
</div>
