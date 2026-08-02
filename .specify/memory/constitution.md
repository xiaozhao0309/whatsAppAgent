# WhatsApp 企业知识问答 Agent Constitution
<!--
Sync Impact Report
==================
Version change: (uninitialized template) → 1.0.0
Modified principles: (none — initial fill of placeholder template)
Added sections:
  - Core Principles I–V (RAG 透明可溯源、Webhook 即时响应、密钥走环境变量、
    可观测与故障兜底、最小化技术栈)
  - 架构与技术约束
  - 开发工作流与质量门禁
  - Governance
Removed sections: none
Deferred TODOs:
  - RATIFICATION_DATE 无历史记录，采用首次填写日期 2026-08-01 作为批准日。
-->

## Core Principles

### I. RAG 透明可溯源（NON-NEGOTIABLE）

检索与生成逻辑 MUST 使用直接 SDK 调用，不引入 LangChain 等黑盒编排框架，确保每一步
都可读、可调试、可由算法同学接手修改。每个面向用户的回答 MUST 基于向量库召回的文档片段，
并在存在来源时附上来源文件名；模型在知识库无相关内容时 MUST 明确说明无法回答，而不是
编造事实。禁止把未经检索的模型自由生成当作知识答案返回。

**理由**：这是一个企业内部知识问答产品，幻觉与不可追溯的答案会直接误导员工。透明的
检索/生成链路是可维护性与可信度的前提。

### II. Webhook 即时响应（NON-NEGOTIABLE）

`/webhook` 入口 MUST 在收到消息后立即返回 HTTP 200，所有 RAG 检索、LLM 调用、回发消息
MUST 在后台任务中执行。禁止在 webhook 请求的关键路径上同步等待 LLM 或任何可能耗时数秒
的外部调用，以避免 Twilio 超时重试造成重复回复。

**理由**：Twilio 对 webhook 有响应时限，同步等待 LLM 会触发重试，导致用户收到重复消息，
并放大上游故障的影响面。

### III. 密钥与配置走环境变量（NON-NEGOTIABLE）

所有 API Key、Token、账号 SID 等敏感配置 MUST 通过环境变量（由 `.env` 加载）读取，
MUST NOT 在源码中硬编码。`.env` MUST 被 `.gitignore` 忽略，仅提交 `.env.example` 作为
模板。代码中引用配置 MUST 经由 `app/config.py` 的 `Settings` 单一入口，不得在业务代码里
散落 `os.getenv` 调用。

**理由**：Twilio Auth Token、Ark API Key 一旦泄露即可被冒用产生费用或窃取对话。集中配置
也便于在不同环境（本地/演示/生产）间切换。

### IV. 可观测性与故障兜底

服务 MUST 记录关键路径日志（收到消息、检索结果、发送回复、异常堆栈），但 MUST NOT 把
API Key、Auth Token 或完整用户隐私内容写入日志。后台处理 MUST 捕获异常，失败时给用户
返回友好的错误提示而不是让任务静默丢失或导致进程崩溃。异常 MUST 通过 `logger.exception`
保留堆栈以便排查。

**理由**：异步后台处理使问题不会直接暴露给调用方，没有日志和兜底就无法发现和定位故障；
同时日志本身不能成为新的泄密渠道。

### V. 最小化技术栈与本地优先（YAGNI）

在满足需求的前提下 MUST 选择最简单、依赖最少的方案：Qdrant 使用本地文件模式，embedding
使用本地 sentence-transformers 模型（无需额外 API Key）。引入新的重型依赖、外部服务或
抽象层 MUST 有明确的、当前存在的需求支撑，禁止为假想的未来需求提前引入复杂度。

**理由**：本仓库定位为可跑通的 demo，最小栈降低上手与部署成本；过度工程会拖慢验证速度。
当 demo 演进为生产时，再以规格驱动的方式替换对应组件。

## 架构与技术约束

- **语言与运行时**：Python 3.10+，依赖统一通过 `requirements.txt` 管理，开发使用虚拟环境
  （`.venv/`，不入库）。
- **Web 层**：使用 FastAPI + uvicorn。Twilio webhook 以 form 表单形式接入，使用
  `python-multipart` 解析。
- **通道层**：WhatsApp 消息收发通过官方 Twilio SDK 封装在 `app/channel.py`，业务代码不得
  直接调用 Twilio 原生客户端。
- **RAG 层**：组件职责固定为 `embeddings`（向量化）、`store`（Qdrant 封装）、
  `chunking`（切片）、`ingest`（入库）、`pipeline`（检索+生成）。各组件 MUST 保持单一职责，
  跨组件逻辑收敛到 `pipeline`。
- **LLM 提供方**：当前使用火山方舟 Ark（OpenAI 兼容接口）。切换提供方 MUST 只改动
  `config.py` 与相应的客户端封装，不得污染检索逻辑。
- **数据目录**：`data/`（Qdrant 本地文件）与 `__pycache__/`、`.venv/` 均为运行时/构建产物，
  MUST NOT 提交到版本库。
- **进程约束**：Qdrant 本地文件模式同一时刻只允许一个进程持有；ingest 脚本与在线服务
  MUST NOT 并发写同一个 collection。

## 开发工作流与质量门禁

- **规格驱动**：新功能或非平凡改动 MUST 按 Spec Kit 流程推进：
  `/speckit-specify` → `/speckit-clarify` → `/speckit-plan` → `/speckit-tasks` →
  `/speckit-implement`，规格、计划、任务文档随代码一起演进。
- **RAG 核心可测**：`pipeline` 的检索与生成、`chunking` 的切片边界、`store` 的存取 MUST
  具备可自动化验证的测试或可复现的验证步骤；改动 RAG 行为前 MUST 先确认现有回归用例通过。
- **提交规范**：提交信息使用约定式前缀（如 `feat:`、`fix:`、`docs:`、`refactor:`）。
  涉及规格/宪法变更时附在提交说明中。Git 扩展提供的钩子用于辅助提交，但不得跳过必要的
  人工审查。
- **变更审查**：MUST 验证 webhook 仍即时返回 200、密钥未被硬编码、回答仍带来源、
  异常路径有兜底，方可合并。
- **配置同步**：新增环境变量 MUST 同步更新 `.env.example` 与 `app/config.py` 的 `Settings`，
  并在 README 中说明用途。

## Governance

本宪法高于项目内其他开发惯例。当某条原则与临时便利冲突时，以本宪法为准。

- **修订程序**：修订 MUST 通过对 `.specify/memory/constitution.md` 的显式变更提出，附带
  修订理由与影响范围，经项目负责人批准后生效。受影响的规格、计划与任务文档 MUST 同步更新。
- **版本策略**：宪法版本遵循语义化版本：
  - MAJOR：删除或重新定义既有原则、引入不兼容的治理变更；
  - MINOR：新增原则或章节、实质性扩充既有指导；
  - PATCH：措辞澄清、错别字、不改变语义的微调。
- **合规审查**：每次代码审查 MUST 对照本宪法核验合规性，重点检查原则 II/III/IV 的不可协商
  条款。发现偏离 MUST 在合并前纠正，或在 PR 中记录明确的、经批准的豁免理由。
- **运行时指引**：具体的实现细节与日常开发约定在各功能的 spec/plan/tasks 与 README 中维护，
  这些文档 MUST 不与本宪法冲突；冲突时以本宪法为准。

**Version**: 1.0.0 | **Ratified**: 2026-08-01 | **Last Amended**: 2026-08-01
