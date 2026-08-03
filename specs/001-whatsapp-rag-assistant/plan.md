# Implementation Plan: WhatsApp 企业知识问答助手 1.0

**Branch**: `001-whatsapp-rag-assistant` | **Date**: 2026-08-02 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/001-whatsapp-rag-assistant/spec.md`，后端使用 Python。

## Summary

在现有最小可跑通 demo（FastAPI + Twilio + 本地 Qdrant + 本地 embedding + Ark LLM）的基础上，补齐 1.0 产品能力：

1. **可信 RAG**：检索相似度阈值过滤、来源标注、答案长度上限、统一拒答话术、空库提示。
2. **多轮会话**：以 WhatsApp 号码为 key 的进程内会话，7 天滑动过期、保留最近 10 轮、上下文 2000 字符上限、手动重置。
3. **编排增强**：入站消息幂等去重、按号码限流、消息长度上限、指令识别（帮助/重置/转人工/反馈）。
4. **兜底与转人工**：异常友好提示；主动/自动转人工，将问题+上下文转发给值班号码（可配备用）。
5. **可观测**：结构化日志（脱敏）、健康检查增强。

**技术路线**：单实例 FastAPI 部署，会话/幂等/限流全部使用进程内存（线程安全的字典/锁/定时清理），不引入 Redis、外部数据库或任务队列；向量库保持 Qdrant 本地文件模式。这与宪法原则 V（最小化技术栈、本地优先）一致。

## Technical Context

**Language/Version**: Python 3.10+（沿用现有虚拟环境）
**Primary Dependencies**:
- Web：FastAPI、uvicorn、python-multipart（已用）
- 消息通道：twilio 官方 SDK（已用）
- 向量库：qdrant-client 本地文件模式（已用）
- 向量化：sentence-transformers（本地 all-MiniLM-L6-v2，已用）
- LLM：火山方舟 Ark，经 OpenAI 兼容 SDK 调用（已用）
- 会话/幂等/限流：Python 标准库（threading、time、collections），**不新增依赖**
- 测试：pytest

**Storage**:
- 向量库：Qdrant 本地文件（`data/qdrant/`），保持不变
- 运行时状态：进程内存（会话、幂等集合、限流计数），不持久化
- 知识库源文件：`app/sample_docs/*.md` / `*.txt`

**Testing**: pytest（新增），覆盖会话截断/过期、阈值拒答、限流、幂等、指令识别等纯逻辑；RAG 链路提供可复现的手动验证步骤。

**Target Platform**: Linux/macOS 服务器，单实例 `uvicorn --workers 1`（单 worker，保证内存状态一致）。

**Project Type**: web-service（WhatsApp bot 后端）

**Performance Goals**: 95% 消息 15 秒内回复（SC-002）；单实例支撑数十客户低并发。

**Constraints**:
- webhook 必须立即返回 200，RAG/回发在后台（宪法原则 II，FR-028）。
- 密钥只走环境变量与 `app/config.py`（宪法原则 III，FR-033）。
- 日志脱敏、异常兜底（宪法原则 IV，FR-030/031/029）。
- 不引入 LangChain 等黑盒编排框架（宪法原则 I，FR-035）。
- 单 worker 运行：多 worker 会导致内存会话/幂等不一致。

**Scale/Scope**: 数十客户、低并发；知识库为小规模纯文本文档（demo 级，单机可承载）。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

依据 [.specify/memory/constitution.md](../../.specify/memory/constitution.md)：

| 原则 | 要求 | 本计划合规性 |
|---|---|---|
| I. RAG 透明可溯源 | 直接 SDK、不引黑盒框架、回答带来源、无相关内容须拒答 | ✅ 沿用直接 SDK 调用；新增阈值过滤拒答、来源标注；不引入 LangChain |
| II. Webhook 即时响应 | 立即回 200，RAG/LLM/回发后台执行 | ✅ 保持 BackgroundTasks 模式，幂等在入站时同步完成 |
| III. 密钥走环境变量 | `.env` 加载、`config.py` 单一入口、不硬编码 | ✅ 所有新增配置项经 Settings；同步更新 `.env.example` |
| IV. 可观测与故障兜底 | 关键路径日志、不写隐私/密钥、异常捕获+友好提示+堆栈 | ✅ 新增结构化日志与脱敏；全链路 try/except |
| V. 最小化技术栈/本地优先 | Qdrant 本地文件、本地 embedding、不引入无需求的重依赖 | ✅ 会话/幂等/限流用标准库内存实现；**不引入 Redis/DB/任务队列**；embedding 保持本地 |

**Gate 结论**：全部通过，无宪法违背，无需 Complexity Tracking 豁免。

**设计后复检（Phase 1 后）**：见文末"Constitution Check 复检"。

## Project Structure

### Documentation (this feature)

```text
specs/001-whatsapp-rag-assistant/
├── spec.md              # 功能规格（已完成）
├── plan.md              # 本文件
├── research.md          # Phase 0：技术决策
├── data-model.md        # Phase 1：数据模型
├── quickstart.md        # Phase 1：端到端验证指南
├── contracts/           # Phase 1：对外接口契约
│   └── webhook.md       #   Twilio webhook 与 HTTP 接口
├── checklists/
│   └── requirements.md  # 规格质量清单（已完成）
└── tasks.md             # Phase 2：任务拆解（由 /speckit-tasks 生成）
```

### Source Code (repository root)

在现有 `app/` 布局上增量新增，不重排已有结构：

```text
app/
├── main.py              # FastAPI 入口：webhook 编排（幂等/限流/指令/会话/反馈/转人工）
├── config.py            # Settings：新增会话/阈值/限流/长度/值班号码等配置
├── channel.py           # Twilio 收发（新增：转发值班人复用）
├── session.py           # 【新】进程内会话管理（TTL/轮数/字符上限/线程安全）
├── guards.py            # 【新】幂等去重、限流、消息长度校验
├── commands.py          # 【新】指令识别（帮助/重置/转人工/反馈表情）
├── handoff.py           # 【新】转人工：组装上下文 + 发送值班号/备用号
├── observability.py     # 【新】脱敏、request_id、结构化日志辅助
└── rag/
    ├── embeddings.py    # 不变
    ├── store.py         # 检索结果带分数（已支持）；新增 collection 计数/清空（用于全量重建与健康检查）
    ├── chunking.py      # 不变
    ├── ingest.py        # 全量重建：入库前清空（FR-008）；返回切片数
    └── pipeline.py      # 改造：阈值拒答、拼会话历史、答案长度控制、返回结构化结果
tests/                   # 【新】pytest 单元测试
├── test_session.py
├── test_guards.py
├── test_commands.py
├── test_chunking.py
└── test_pipeline.py     # 阈值/拒答/历史拼接（mock LLM 与检索）
scripts/
└── ingest.py            # 不变（复用）
```

**Structure Decision**: 沿用现有单项目 `app/` 包布局（宪法既定结构），新增模块职责单一、可独立测试。不创建 `src/` 多项目结构，也不拆分前后端。

## Phase 0: Research

见 [research.md](./research.md)。核心技术决策：

1. **会话存储**：进程内 `dict` + `threading.Lock` + 惰性过期（访问时清理），不引入 Redis。
2. **幂等去重**：进程内带 TTL 的已见 MessageSid 集合（24h）。
3. **限流**：按号码的固定时间窗计数器（60s 窗口），标准库实现。
4. **相似度阈值**：直接读取 Qdrant 返回的 cosine 分数，配置阈值（默认 0.5，上线前标定）。
5. **后台任务**：沿用 FastAPI `BackgroundTasks`，单 worker 下足够；不上任务队列。
6. **worker 约束**：必须单 worker 运行以保证内存状态一致性。

## Phase 1: Design

- 数据模型：见 [data-model.md](./data-model.md)
- 接口契约：见 [contracts/webhook.md](./contracts/webhook.md)
- 端到端验证：见 [quickstart.md](./quickstart.md)

### 处理主流程（webhook）

```text
POST /webhook (form)
  ├─ 立即返回 200（空响应），其余加入后台任务
  └─ 后台 _handle(MessageSid, From, Body):
       1. 幂等：MessageSid 已见 → 丢弃
       2. 长度校验：超上限 → 回复"请精简问题"
       3. 限流：该号码本窗口超限 → 回复"过于频繁，请稍后再试"
       4. 指令识别：
          - 👍/👎 → 记录反馈，结束
          - 帮助/help/菜单 → 回帮助文案
          - 重新开始/清空/新话题 → 清空该号码会话，回确认
          - 转人工/找人工 → 触发 handoff
       5. 新用户（无会话且非指令）→ 回欢迎语
       6. 读会话历史 → pipeline.answer(question, history)
          ├─ embed → 检索 → 读最高分
          ├─ 空库 → "知识库尚未就绪"
          ├─ 最高分 < 阈值 → 拒答；连续2次拒答 → 触发 handoff
          └─ 达标 → 拼历史+上下文 → LLM → 截断到长度上限 → 附来源+反馈提示
       7. 写回会话（追加本轮，截断10轮/2000字符，刷新7天TTL）
       8. 发送回复；异常 → 友好提示 + logger.exception
```

### Constitution Check 复检（Phase 1 设计后）

- 设计未新增任何外部服务或重型依赖，会话/幂等/限流均为标准库内存实现 → 符合原则 V。
- webhook 仍在入站时同步完成幂等/限流（轻量内存操作），RAG/LLM/回发放后台 → 符合原则 II。
- 新增配置全部经 Settings 与 `.env.example` → 符合原则 III。
- 日志字段定义了脱敏规则（WAID 掩码、不记密钥/全文）、全链路异常兜底 → 符合原则 IV。
- RAG 链路保持直接 SDK 调用，阈值判断与历史拼接逻辑显式可读 → 符合原则 I。

**复检结论：通过。**
