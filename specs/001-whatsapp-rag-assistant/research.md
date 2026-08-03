# Research: WhatsApp 企业知识问答助手 1.0

**Date**: 2026-08-02
**Feature**: 001-whatsapp-rag-assistant

本阶段为技术决策记录。规格中的关键产品决策（7 天滑动过期、10 轮、单实例、转人工单向通知、全员开放+限流、纯文本知识库、相似度阈值）均已在需求阶段确认，无悬而未决的 NEEDS CLARIFICATION。以下记录实现层的选择与理由。

---

## R-1：会话存储 — 进程内内存，而非 Redis

**Decision**: 会话状态保存在单进程内存中（`dict` + `threading.Lock`），不引入 Redis 或数据库。

**Rationale**:
- 1.0 为单实例单 worker 部署（数十客户、低并发），所有请求落在同一进程，内存即共享。
- 会话是临时数据，天然带 TTL（7 天）、轮数上限、字符上限，不需要持久化与复杂查询。
- 宪法原则 V 要求最小化技术栈、本地优先；引入 Redis 属于为"未来多副本"提前加重型依赖，违反 YAGNI。
- 会话数据结构简单（号码 → 消息列表 + 时间戳），标准库即可满足。

**Alternatives considered**:
- **Redis**：适合多副本共享会话/幂等/限流，但 1.0 单副本用不到，且增加运维组件；列为未来升级路径（见 plan.md Summary）。
- **SQLite/文件持久化**：增加 I/O 与 schema 维护，会话不需要持久化，重启清空在 1.0 可接受。

**Implication**:
- 必须以 `uvicorn --workers 1` 运行（多 worker 各持独立内存，会导致会话/幂等/限流不一致）。
- 进程重启清空会话，客户需重新开始；由进程守护与通道重试兜底（已记入规格 Edge Cases）。

---

## R-2：会话过期与截断策略

**Decision**:
- 采用"惰性过期 + 滑动刷新"：每次访问某会话时检查其最旧活跃时间，超过 7 天则清空并视为新会话；每次有效交互后更新活跃时间戳。
- 写入时截断到最近 10 轮；组装上下文时若累计字符超 2000，从最早轮次丢弃直至不超限。

**Rationale**:
- 惰性过期无需后台清扫线程，实现简单、无额外调度；会话数量级小（数十），不会因未及时清理造成内存压力。
- 滑动过期匹配 FR-010（每条消息重置 7 天）。
- 双重上限（轮数 + 字符数）防止超长单轮对话把 prompt 撑爆（FR-011/012）。

**Alternatives considered**:
- 后台定时线程清理过期会话：多一个线程与锁竞争，当前规模无必要；若未来会话量增大可再加。
- 按 token 而非字符截断：需要 tokenizer 依赖；2000 字符是足够安全的保守上限，避免新增依赖。

---

## R-3：幂等去重 — 进程内带 TTL 的已见集合

**Decision**: 维护一个 `dict[MessageSid, expire_ts]`，入站时同步检查；已见 MessageSid 直接丢弃。惰性清理超过 24 小时的条目。

**Rationale**:
- Twilio 在 webhook 响应超时时会重试投递同一 MessageSid，幂等是 FR-027 的硬性要求，且必须在同步入站阶段完成（不能放后台，否则两条并发请求都会进入处理）。
- 重试窗口远小于 24 小时，设 24h TTL 足够覆盖又能自动回收内存。

**Alternatives considered**:
- 仅靠"立即回 200"避免重试：不能覆盖网络抖动、Twilio 服务侧重试，必须有显式幂等。

---

## R-4：限流 — 固定时间窗计数器

**Decision**: 按 WAID 的 60 秒固定窗口计数，超过配置阈值（默认 10 条/分钟）则拒绝该窗口内后续消息。计数存于进程内 `dict[WAID, (window_start, count)]`，惰性翻窗/清理。

**Rationale**:
- 固定窗口实现最简单，足以防止单用户刷爆 LLM 调用（FR-025）；精确的滑动窗口对本场景收益不大。
- 限流检查是同步轻量内存操作，放在后台任务最前面，不阻塞 webhook 返回 200。

**Alternatives considered**:
- 滑动窗口/令牌桶：更平滑但实现复杂；1.0 防滥用只需粗粒度阈值。
- 全局限流：本场景主要风险在单用户，按 WAID 更合理。

---

## R-5：相似度阈值

**Decision**: 直接使用 Qdrant `query_points` 返回的 cosine 分数（embedding 已归一化，分数即余弦相似度，范围约 [-1,1]，越高越相关）。取最高命中分数与配置阈值（默认 0.5）比较：低于阈值走拒答，不调用 LLM。

**Rationale**:
- 当前 embedding 使用 `normalize_embeddings=True` + COSINE 距离，分数可解释且跨查询可比。
- 阈值必须可配置（FR-034），0.5 仅为保守起点。
- 不依赖固定 top-k 的"第 k 名分数"，只看最高分是否达标，避免"凑够 k 条但都不相关"。

**Alternatives considered**:
- 相对阈值/MMR 重排：1.0 不需要，增加复杂度。
- 不设阈值直接让 LLM 判断：把拒答责任交给生成模型，幻觉风险更高；显式检索阈值更可控、更省 token。

**Action before go-live**: 用真实知识库 + 典型问题集标定阈值（记录在 quickstart 验证步骤中）。

---

## R-6：后台处理机制

**Decision**: 沿用 FastAPI `BackgroundTasks`，在 webhook 函数中 `add_task`，立即返回空 200。不引入 Celery/RQ/消息队列。

**Rationale**:
- 符合宪法原则 II，现有代码已采用该模式且 demo 验证可行。
- 单实例低并发下，BackgroundTasks 足够；进程在返回后、回发前崩溃导致的偶发丢消息，1.0 可接受（规格已声明），Twilio 在 24h 窗口内会重试（配合 R-3 幂等不会重复回复）。

**Alternatives considered**:
- Celery/RQ + Redis：提供"消息不丢"与可重试，但需要 Redis 与 worker 进程，明显加重栈；列为未来需求（当业务不能接受偶发丢失时）。

---

## R-7：会话历史如何送入 LLM

**Decision**: 将最近若干轮以 OpenAI 兼容的 `messages` 多轮格式传入（role=user/assistant），当前问题作为最后一条 user 消息；检索到的知识上下文与系统提示放在 system 消息中。回答长度通过 system 指令 + 结果截断双重控制（上限默认 800 字）。

**Rationale**:
- 多轮 messages 格式是 LLM 理解指代与上下文的标准方式，比把历史拼进单条 prompt 更清晰。
- 历史截断发生在送入前（10 轮 / 2000 字符），保证不超长。
- 长度控制双保险：prompt 中要求简洁，返回后若仍超长则硬截断并加省略提示。

**Alternatives considered**:
- 仅把历史摘要拼入单条 user 消息：需要额外摘要调用，增加延迟与成本；1.0 直接传最近原文轮次即可。

---

## R-8：转人工上下文组装

**Decision**: 触发转人工时，从该 WAID 会话取最近若干轮（建议最近 5 轮，或在 2000 字符内），拼接成纯文本通知，通过现有 Twilio 通道发送给值班号码；主号失败则试备用号。通知内含客户号码（可脱敏）、最后问题、对话上下文、时间。

**Rationale**:
- 复用 channel.py 的发送能力，不新增通道逻辑。
- 值班人只需在 WhatsApp 收到一条可读通知即可跟进，1.0 不做双向中继（FR-019）。

**Alternatives considered**:
- 邮件/工单系统：超出 1.0 范围；WhatsApp 通知与客户渠道一致、响应快。
- 双向桥接：需要维护用户↔值班人路由，复杂度高，列入未来。

---

## R-9：测试策略

**Decision**:
- 纯逻辑模块（session、guards、commands、chunking、pipeline 的阈值/历史拼接）用 pytest 单元测试，pipeline 测试 mock 掉 embedding 检索与 LLM 调用。
- 端到端（真实 Twilio + LLM）通过 quickstart.md 的手动步骤验证，不写依赖外部服务的自动化集成测试（1.0 demo 阶段）。

**Rationale**:
- 核心风险在会话截断/过期、限流、幂等、阈值判断、指令识别这些不依赖外部的逻辑，单元测试可完整覆盖。
- RAG 的真实命中率/阈值标定属于上线前人工评测，不适合固化为脆弱的单测。
