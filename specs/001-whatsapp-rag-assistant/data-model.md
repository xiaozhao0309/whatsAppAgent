# Data Model: WhatsApp 企业知识问答助手 1.0

**Date**: 2026-08-02 | **Spec**: [spec.md](./spec.md)

本期无外部数据库。数据分两类：
- **持久数据**：Qdrant 本地向量库中的知识切片（来自文档导入）。
- **运行时状态**：进程内存中的会话、幂等集合、限流计数（不持久化，重启清空）。

---

## 1. 持久实体：知识切片（Knowledge Chunk）

存储于 Qdrant collection（本地文件模式）。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | int | 由 `sha1(source:index)` 派生的稳定 id；重复入库覆盖而非累积 |
| vector | float[384] | embedding 向量（all-MiniLM-L6-v2，归一化，余弦距离） |
| payload.text | str | 切片正文 |
| payload.source | str | 来源文件名（如 `hr_faq.md`），用于来源标注 |
| payload.chunk_index | int | 该切片在所属文件中的序号（新增，便于追溯） |

**规则**：
- 全量重建（FR-008）：重新导入时先删除 collection 内全部 point，再写入。
- 仅收录 `.md` / `.txt`（FR-007）。
- 切片由 [chunking.py](app/rag/chunking.py) 按段落 + 固定长度滑窗（size/overlap 可配）生成。

---

## 2. 运行时实体

### 2.1 会话（Session）

进程内结构：`dict[wa_id, SessionState]`，受锁保护。

```text
SessionState:
  turns: list[Turn]          # 最近若干轮（写入时截断到 10 轮）
  last_active_ts: float      # 最近一次交互时间（秒），用于 7 天滑动过期
  miss_streak: int           # 连续拒答次数（用于自动转人工，达 2 触发）
```

```text
Turn:
  role: "user" | "assistant"
  content: str
  ts: float
```

**校验与状态规则**：
- `wa_id` 为 WhatsApp 号码标识（如 `whatsapp:+86...`），是会话唯一键（FR-009）。
- 读取时：若 `now - last_active_ts > SESSION_TTL_SECONDS(7天)`，视为过期，清空后按新会话处理（FR-010/014）。
- 写入时：保留最近 `SESSION_MAX_TURNS(10)` 轮（FR-011）。
- 组装上下文时：从最近轮向前累计，总字符不超过 `SESSION_MAX_CHARS(2000)`，超出丢弃最早轮（FR-012）。
- 任何有效交互后刷新 `last_active_ts`（滑动过期）。
- "重新开始/清空/新话题"指令：删除该 `wa_id` 的 SessionState（FR-013）。
- `miss_streak`：拒答时 +1，成功回答时归零；达到 2 时触发自动转人工（FR-016）。

### 2.2 消息（Message）— 入站

来自 Twilio webhook 表单字段：

| 字段 | 来源 | 用途 |
|---|---|---|
| MessageSid | Twilio 表单 | 幂等去重的唯一标识（FR-027） |
| From | Twilio 表单 | 发送方 WAID，会话键 |
| Body | Twilio 表单 | 消息正文 |

处理前校验：Body 非空（空消息安全忽略）、长度 ≤ `MESSAGE_MAX_CHARS(2000)`（FR-026）。

### 2.3 幂等记录（Idempotency Record）

进程内：`dict[message_sid, expire_ts]`。
- 入站同步检查：存在则直接丢弃。
- 不存在则记录，`expire_ts = now + 24h`。
- 惰性清理过期条目。

### 2.4 限流计数（Rate Limit Counter）

进程内：`dict[wa_id, (window_start_ts, count)]`。
- 窗口长度 60 秒；窗口内计数超过 `RATE_LIMIT_PER_MINUTE(10)` 则拒绝（FR-025）。
- 超过窗口长度则翻窗重置。

### 2.5 回答结果（Answer Result）— pipeline 返回值

```text
AnswerResult:
  reply: str                 # 回答正文（已做长度控制）
  sources: list[str]         # 命中的来源文件名（去重，保持出现顺序）
  status: "answered" | "no_match" | "empty_kb" | "error"
  top_score: float | None    # 最高检索相关性（用于日志/阈值判断）
  need_handoff: bool         # 是否建议/触发转人工（连续2次拒答）
```

### 2.6 反馈（Feedback）

不入库，仅写日志（FR-022）。一条日志记录包含：
- request_id、脱敏 wa_id、反馈类型（👍/👎）、上一轮问题、上一轮回答摘要、来源、时间戳。
- 同一轮内重复表情只记一次（FR-023）：通过记录"该会话最后一条助手消息是否已被评价"实现。

### 2.7 转人工通知（Handoff）

触发时组装并发送（不持久化）：
- 客户 wa_id（日志脱敏；通知值班人时可用完整号码以便跟进）
- 最后问题
- 最近若干轮对话（建议最近 5 轮或 2000 字符内）
- 触发原因（用户主动 / 连续 2 次未答出）
- 时间戳
- 发送目标：`ON_DUTY_NUMBER`，失败时尝试 `ON_DUTY_FALLBACK_NUMBER`（FR-017）

---

## 3. 配置项（Settings）

新增/沿用配置（经 [app/config.py](app/config.py) 单一入口，FR-033/034）：

| 配置 | 环境变量 | 默认值 |
|---|---|---|
| 会话 TTL | SESSION_TTL_SECONDS | 604800 |
| 会话最大轮数 | SESSION_MAX_TURNS | 10 |
| 上下文最大字符 | SESSION_MAX_CHARS | 2000 |
| 相似度阈值 | RAG_SCORE_THRESHOLD | 0.5 |
| 召回条数 | TOP_K | 5 |
| 答案最大字符 | ANSWER_MAX_CHARS | 800 |
| 每分钟限流 | RATE_LIMIT_PER_MINUTE | 10 |
| 消息最大字符 | MESSAGE_MAX_CHARS | 2000 |
| 值班号码 | ON_DUTY_NUMBER | 空（未配置则降级） |
| 备用值班号码 | ON_DUTY_FALLBACK_NUMBER | 空 |
| Twilio / Ark / Qdrant / 切片 | （沿用现有） | — |
