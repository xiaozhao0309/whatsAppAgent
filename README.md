# WhatsApp 企业知识问答 Agent

客户在 WhatsApp 里提问，机器人基于企业内部知识库（RAG）生成带来源的回答，支持多轮对话、拒答兜底、转人工、限流与反馈。

本仓库采用 **monorepo 双服务**结构，方便后端与 AI 两人分工协作：

- **`backend/`** — WhatsApp 接入与会话编排（Twilio webhook、幂等/限流、多轮会话、指令、转人工），通过 HTTP 调用 AI 服务。
- **`ai_service/`** — RAG/AI 服务（向量检索、embedding 模型、LLM 生成、文档入库），对外暴露 `/answer`、`/ingest`、`/health`。

> 详细功能需求见 [docs/需求文档/](docs/需求文档/)；规格与实施计划见 [specs/001-whatsapp-rag-assistant/](specs/001-whatsapp-rag-assistant/)；决策与排错见 [docs/开发决策与使用记录.md](docs/开发决策与使用记录.md)。

## 架构

```
客户 WhatsApp ──▶ Twilio webhook ──▶ backend (FastAPI, 单 worker, 端口 8000)
                                      ├─ 幂等去重 / 限流 / 长度校验
                                      ├─ 指令识别（help/reset/agent/反馈）
                                      ├─ 会话管理（进程内存，7 天 / 10 轮）
                                      │        │ HTTP POST /answer
                                      │        ▼
                                      ├─▶ ai_service (FastAPI, 端口 8001)
                                      │      ├─ 向量化：sentence-transformers（本地）
                                      │      ├─ 向量库：Qdrant（本地文件）
                                      │      └─ 生成：火山方舟 Ark（OpenAI 兼容）
                                      └─ Twilio 通道：回发答案 / 转发值班人
```

设计要点：
- **webhook 立刻回 200**，RAG（现在是一次 HTTP 调用）在后台跑完再回发——避免 LLM 慢导致 Twilio 超时重试。
- **不引入 LangChain**，检索/生成用直接 SDK 调用，逻辑透明。
- **后端单实例单 worker**：会话、幂等、限流存在进程内存，必须用 `--workers 1` 运行。
- AI 服务故障时后端不崩，降级为友好错误提示（故障隔离）。
- 两服务的唯一耦合是 `/answer` 的 HTTP 契约（见下方）；AI 同学可自由改模型/prompt/切片，只要契约不变。

### `/answer` 契约

```
POST /answer
Request:  {"question": str, "history": [{"role":"user"|"assistant","content":str}, ...]}
Response: {"reply": str, "sources": [str], "status": "answered"|"no_match"|"empty_kb"|"error", "top_score": float|null}
```

## 快速开始

需要两个终端，分别启动两个服务。

### 1. 安装依赖

```bash
# 推荐各自建虚拟环境（AI 服务会装 torch，体积较大）
python3 -m venv .venv && source .venv/bin/activate
pip install -r ai_service/requirements.txt
pip install -r backend/requirements.txt
```
> 若只是本地快速跑，也可以在同一个 venv 里装两份 requirements。

### 2. 配置

每个服务有自己的 `.env`（从 `.env.example` 复制）：
```bash
cp ai_service/.env.example ai_service/.env   # 填 ARK_API_KEY / ARK_MODEL
cp backend/.env.example backend/.env         # 填 TWILIO_*；RAG_SERVICE_URL 默认指向本地 8001
```
转人工可选填 `ON_DUTY_NUMBER`。

### 3. 导入知识库

把企业文档（`.md` / `.txt`）放进 `ai_service/app/sample_docs/`，然后入库：

```bash
# 方式一：AI 服务启动后，通过后端代理（推荐，无需停服）
curl -X POST http://localhost:8000/admin/ingest
# 方式二：AI 服务启动后直接调 AI 服务
curl -X POST http://localhost:8001/ingest
# 方式三：命令行（先确保 8001 没在跑，避免 Qdrant 文件锁冲突）
(cd ai_service && python scripts/ingest.py)
```

### 4. 启动两个服务

```bash
# 终端 1：AI 服务
cd ai_service && uvicorn app.main:app --port 8001 --workers 1

# 终端 2：后端
cd backend && uvicorn app.main:app --port 8000 --workers 1
```
> 生产环境不要加 `--reload`。AI 服务启动时会预热 embedding 模型（首次较慢）。

健康检查：
```bash
curl http://localhost:8001/health   # AI 服务 + KB 点数
curl http://localhost:8000/health   # 后端 + AI 是否可达
```

### 5. 暴露到公网（Twilio 要能访问 webhook）

```bash
ngrok http 8000
```
在 Twilio Sandbox 设置页把 **WHEN A MESSAGE COMES IN** 填为：
```
https://<你的ngrok地址>/webhook
```

## 测试

```bash
(cd ai_service && PYTHONPATH=. pytest -q)   # RAG pipeline 测试（8 个）
(cd backend    && PYTHONPATH=. pytest -q)    # 会话/指令/限流/幂等/转人工/HTTP 客户端测试（24 个）
```

### 不连 WhatsApp 快速验证

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"How do I connect to the VPN?"}'
```

### Twilio + WhatsApp Sandbox 准备
1. 注册 https://www.twilio.com（免费试用额度够 demo），拿到 `Account SID` 和 `Auth Token`。
2. Messaging → Try it Out → Send a WhatsApp message，启用 **Sandbox**。
3. 用手机 WhatsApp 给 Sandbox 号码（`+1 415 523 8886`）发送 `join <邀请码>` 完成绑定。

## 项目结构

```
backend/                      # 后端同学负责
├── app/
│   ├── main.py               # FastAPI 入口 + webhook 编排 + rag_client 调用
│   ├── rag_client.py         # 调 ai_service 的 HTTP 客户端（契约边界）
│   ├── config.py             # Twilio / 会话 / 限流 / RAG_SERVICE_URL
│   ├── channel.py            # Twilio 收发消息
│   ├── session.py guards.py commands.py handoff.py observability.py responses.py
└── tests/                    # 后端单测
ai_service/                   # AI 同学负责
├── app/
│   ├── main.py               # 暴露 /answer /ingest /health
│   ├── config.py             # Ark / Qdrant / RAG 调参 / DOCS_DIR
│   ├── rag/                  # embeddings / store / chunking / ingest / pipeline
│   └── sample_docs/          # 知识库源文档
├── scripts/ingest.py
└── tests/                    # RAG pipeline 单测
docs/ specs/                  # 需求、决策、时序图、架构图、Spec Kit（共享）
```

## 上线前注意事项

- **相似度阈值**：用真实知识库与典型问题集统计分数分布，调整 `ai_service/.env` 的 `RAG_SCORE_THRESHOLD`（默认 0.5 偏松）。
- **值班号码**：在 `backend/.env` 配置 `ON_DUTY_NUMBER`（及备用号），否则转人工会降级。
- **后端单 worker**：生产环境务必 `--workers 1`；水平扩展需先把 `session.py`/`guards.py` 的内存实现换成 Redis。
- **进程守护**：用 systemd/supervisor 等在进程异常退出后自动重启两个服务。
- **正式号码**：正式服务使用 WhatsApp 商业号码；Sandbox 有 24 小时会话过期等限制，仅用于开发测试。

## 常见问题

- **后端能启动但答不出**：`curl http://localhost:8000/health` 看 `ai_service` 是否可达；确认 8001 在跑、`backend/.env` 的 `RAG_SERVICE_URL` 正确。
- **改了文档没生效**：要重新入库（`POST /admin/ingest`）。
- **想换 embedding 模型**：改 `ai_service/app/rag/embeddings.py`，同步改 `EMBEDDING_DIM` 并删 `ai_service/data/` 重建 collection。
- **想换 LLM**：改 `ai_service/.env` 里的 `ARK_*`。
