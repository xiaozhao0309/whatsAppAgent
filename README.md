# WhatsApp 企业知识问答 Agent

一个最小可跑通的企业知识问答助手：客户在 WhatsApp 里提问，机器人基于企业内部知识库（RAG）生成带来源的回答，支持多轮对话、拒答兜底、转人工、限流与反馈。

> 详细功能需求见 [docs/需求文档/](docs/需求文档/)；规格与实施计划见 [specs/001-whatsapp-rag-assistant/](specs/001-whatsapp-rag-assistant/)。

## 架构（1.0 单实例）

```
客户 WhatsApp ──▶ Twilio webhook ──▶ FastAPI（单进程，单 worker）
                                        ├─ 幂等去重 / 限流 / 长度校验
                                        ├─ 指令识别（帮助/重置/转人工/反馈）
                                        ├─ 会话管理（进程内存，7 天 / 10 轮）
                                        ├─ RAG 问答：
                                        │    ├─ 向量化：sentence-transformers（本地）
                                        │    ├─ 向量库：Qdrant（本地文件）
                                        │    └─ 生成：火山方舟 Ark（OpenAI 兼容）
                                        └─ Twilio 通道：回发答案 / 转发值班人
```

设计要点：
- **webhook 立刻回 200**，RAG 在后台跑完再回发——避免 LLM 慢导致 Twilio 超时重试。
- **不引入 LangChain**，检索/生成用直接 SDK 调用，逻辑透明。
- **单实例单 worker**：会话、幂等、限流存在进程内存，因此必须用 `--workers 1` 运行。重启会清空会话（1.0 接受此限制）。
- 升级多副本时，把 `session.py`/`guards.py` 的内存实现换成 Redis、Qdrant 改 server 模式即可，业务逻辑不变。

## 前置准备

### 1. Python 环境
需要 Python 3.10+：
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
> `sentence-transformers` 会附带安装 PyTorch（较大，首次安装慢，属正常现象）。

### 2. 火山方舟 Ark API Key
在火山方舟控制台申请 `ARK_API_KEY`，并创建一个推理接入点（`ARK_MODEL`）。

### 3. Twilio + WhatsApp Sandbox
1. 注册 https://www.twilio.com（免费试用额度够 demo）。
2. Console 首页拿到 `Account SID` 和 `Auth Token`。
3. 进入 Messaging → Try it Out → Send a WhatsApp message，启用 **Sandbox**。
4. 用手机 WhatsApp 给 Sandbox 号码（`+1 415 523 8886`）发送 `join <邀请码>` 完成绑定。

## 配置

```bash
cp .env.example .env
```
编辑 `.env`，至少填写：
```
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
ARK_API_KEY=...
ARK_MODEL=...          # 你的方舟接入点/模型
# 转人工需要（可选）：
ON_DUTY_NUMBER=whatsapp:+86...
```
其余参数（阈值、会话 TTL、轮数、限流等）均有默认值，见 `.env.example` 注释。

> ⚠️ `RAG_SCORE_THRESHOLD` 默认 0.5 仅为起点，**上线前务必用真实知识库标定**（见下方“上线前标定”）。

## 导入知识库

把企业文档（`.md` / `.txt`）放进 `app/sample_docs/`，然后向量化写入 Qdrant（全量重建）：
```bash
python scripts/ingest.py
```
> Qdrant 本地文件模式同一时间只能被一个进程打开。服务运行中可用接口重建：`curl -X POST http://localhost:8000/admin/ingest`。

## 启动服务

```bash
# 必须单 worker（会话/幂等/限流在进程内存）
uvicorn app.main:app --reload --port 8000 --workers 1
```
健康检查：
```bash
curl http://localhost:8000/health
# {"status":"ok","kb":{"collection":"enterprise_kb","points":14,"accessible":true}}
```

## 暴露到公网（Twilio 要能访问 webhook）

```bash
ngrok http 8000
```
复制 ngrok 地址，在 Twilio Sandbox 设置页把 **WHEN A MESSAGE COMES IN** 填为：
```
https://<你的ngrok地址>/webhook
```

## 测试

### 自动化测试
```bash
pytest -q
```
覆盖会话截断/过期、限流、幂等、指令识别、pipeline 阈值/历史/长度、转人工主备回退等纯逻辑。

### 在 WhatsApp 里验证
- 问知识库内问题：“年假有几天？” → 基于文档回答并附来源。
- 问知识库外问题：“今天股价多少” → 拒答而不编造。
- 追问：“年假几天？”→“那病假呢？” → 结合上下文。
- 发“帮助”“重新开始”“转人工” 👍/👎 体验指令。

更多场景见 [specs/001-whatsapp-rag-assistant/quickstart.md](specs/001-whatsapp-rag-assistant/quickstart.md)。

## 项目结构

```
app/
├── main.py            # FastAPI 入口 + webhook 编排
├── config.py          # 环境变量配置（单一入口）
├── channel.py         # Twilio 收发消息
├── session.py         # 进程内会话（TTL/轮数/字符上限/miss 计数/反馈去重）
├── guards.py          # 幂等去重、限流、消息长度校验
├── commands.py        # 指令识别（帮助/重置/转人工/反馈）
├── handoff.py         # 转人工：组装上下文 + 通知值班号/备用号
├── observability.py   # 请求 ID、号码脱敏、结构化日志
├── responses.py       # 面向客户的话术文案
└── rag/
    ├── embeddings.py  # 本地向量化
    ├── store.py       # Qdrant 封装（含计数/清空）
    ├── chunking.py    # 文档切片
    ├── ingest.py      # 全量入库
    └── pipeline.py    # 检索 + 阈值 + 多轮 + 生成
tests/                 # pytest 单元测试
scripts/ingest.py      # 命令行入库
specs/001-.../         # Spec Kit 规格/计划/任务
docs/需求文档/          # 产品需求文档
```

## 上线前标定 / 注意事项

- **相似度阈值**：用真实知识库与典型问题集统计命中/无关问题的分数分布，调整 `RAG_SCORE_THRESHOLD`。
- **值班号码**：配置 `ON_DUTY_NUMBER`（及备用号），否则转人工会降级。
- **单 worker 运行**：生产环境务必 `--workers 1`；如需水平扩展，请按架构说明迁移到 Redis + Qdrant server。
- **进程守护**：用 systemd/supervisor 等在进程异常退出后自动重启。
- **正式号码**：客户正式服务使用 WhatsApp 商业号码；Sandbox 有 24 小时会话过期等限制，仅用于开发测试。
- Sandbox 限制：会话 24 小时后过期需重新 `join`，且使用共享号码。

## 常见问题

- **收到消息没回复**：看终端日志，多半是 `.env` 没填或 Ark/Twilio key 不对。
- **webhook 收不到**：确认 ngrok 在跑、Twilio Sandbox 里填的 URL 是 `<ngrok地址>/webhook`。
- **想换 embedding 模型**：改 `app/rag/embeddings.py`，同步改 `EMBEDDING_DIM` 并删 `data/` 重建 collection。
- **想换 LLM**：改 `.env` 里的 `ARK_*` 配置。
