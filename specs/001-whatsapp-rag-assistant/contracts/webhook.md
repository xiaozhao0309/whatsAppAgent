# Contract: HTTP 接口

**Date**: 2026-08-02 | **Spec**: [spec.md](../spec.md)

服务对外暴露的 HTTP 接口。消息收发主体为 Twilio webhook。

---

## 1. POST /webhook — Twilio 入站消息回调

Twilio 在收到 WhatsApp 消息时以 `application/x-www-form-urlencoded` 表单 POST 到本接口。

### 行为契约

- **必须立即返回 HTTP 200**（空响应体即可），不得在请求关键路径上等待 RAG/LLM/回发（FR-028，宪法原则 II）。
- 实际处理（幂等、限流、检索、生成、回发）在后台任务中完成。
- 幂等：相同 `MessageSid` 的重复投递只处理一次（FR-027）。

### 入站表单字段（Twilio 提供）

| 字段 | 类型 | 说明 |
|---|---|---|
| MessageSid | string | 消息唯一标识，用于幂等 |
| From | string | 发送方，形如 `whatsapp:+8613...` |
| Body | string | 消息文本正文 |

### 响应

- `200 OK`，空 body。所有业务结果通过 Twilio REST API 异步回发到用户会话。

### 后台处理结果（回发到 WhatsApp）

| 场景 | 回发内容 |
|---|---|
| 正常回答 | 答案正文 + 来源 + "回复 👍/👎 评价" |
| 知识库外/低分 | 拒答话术，引导换问法或转人工；连续 2 次触发转人工提示 |
| 知识库为空 | "知识库尚未就绪"提示 |
| 命中帮助指令 | 功能说明 + 示例 |
| 命中重置指令 | 会话已重置确认 |
| 转人工 | "已通知值班人员"；同时向值班号发送上下文通知 |
| 限流 | "操作过于频繁，请稍后再试" |
| 超长消息 | "消息过长，请精简后再发" |
| 反馈 👍/👎 | 感谢提示；反馈记录日志 |
| 处理异常 | 友好错误提示，错误堆栈记日志 |

---

## 2. GET /health — 健康检查

### 响应

`200 OK`

```json
{
  "status": "ok",
  "kb": {
    "collection": "enterprise_kb",
    "points": 123,
    "accessible": true
  }
}
```

- `kb.accessible=false` 时仍返回 200 但 `status` 反映异常（或返回 503，具体在实现中确定；契约要求反映知识库可访问状态，FR-032）。
- 不得在响应中泄露密钥、路径等敏感信息。

---

## 3. POST /admin/ingest — 重新导入知识库（沿用，行为增强）

### 行为

- 全量重建：清空当前 collection 后从文档目录重新导入 `.md`/`.txt`（FR-008）。
- 受单实例本地 Qdrant 文件锁约束：与在线服务同进程时安全；不得与外部 ingest 进程并发写同一 collection（宪法架构约束）。

### 响应

`200 OK`

```json
{ "ingested_chunks": 42 }
```

- 空文档或读取失败必须报错，不静默跳过（FR-008）。

---

## 4. POST /ask — 直接问答（开发/调试用，沿用）

请求体：

```json
{ "question": "年假有几天？" }
```

响应体：

```json
{
  "question": "年假有几天？",
  "answer": "...",
  "sources": ["hr_faq.md"],
  "status": "answered",
  "top_score": 0.82
}
```

- 该接口便于不带 Twilio 的本地调试；1.0 保留。可选择是否让其也走多轮会话（默认无状态单次问答，会话仅在 webhook 链路生效）。

---

## 配置与运行约束（影响契约行为）

- 必须以**单 worker** 运行（`uvicorn --workers 1`），因为会话/幂等/限流存于进程内存。
- 所有密钥通过环境变量注入，接口与日志均不得泄露（FR-031/033）。
