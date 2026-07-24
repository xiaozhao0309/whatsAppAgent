# WhatsApp 企业知识问答 Agent

一个最小可跑通的 demo：用户在 WhatsApp 里向机器人提问，机器人基于企业内部知识库（RAG）回答。

## 架构

```
用户 WhatsApp ──▶ Twilio webhook ──▶ FastAPI 后端
                                      ├─ 通道层：twilio SDK 收发消息
                                      └─ 问答层：RAG
                                           ├─ 向量库：Qdrant（本地文件模式）
                                           ├─ 向量化：sentence-transformers（本地，无需 key）
                                           └─ 生成：Claude（Anthropic）
```

设计要点：
- **webhook 立刻回 200**，RAG 在后台跑完再用 REST API 把答案发回去——避免 LLM 慢导致 Twilio 超时重试。
- **不引入 LangChain**，检索/生成用直接 SDK 调用，逻辑透明，方便算法同学接手。

## 前置准备

### 1. Python 环境
需要 Python 3.10+。建议用虚拟环境：
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
> `sentence-transformers` 会附带安装 PyTorch（较大，首次安装慢，属正常现象）。

### 2. Anthropic API Key
到 https://console.anthropic.com 申请 `ANTHROPIC_API_KEY`。

### 3. Twilio + WhatsApp Sandbox
1. 注册 https://www.twilio.com（有免费试用额度，够 demo）。
2. Console 首页拿到 `Account SID` 和 `Auth Token`。
3. 进入 Messaging → Try it Out → Send a WhatsApp message，启用 **Sandbox**。
4. 用你的手机 WhatsApp 给 Sandbox 号码（`+1 415 523 8886`）发送 `join <邀请码>`（页面会显示码，如 `join orange-cat`），完成绑定。

## 配置

复制环境变量模板并填写：
```bash
cp .env.example .env
```
编辑 `.env`，至少填这两个 Twilio 值和 Anthropic key：
```
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
ANTHROPIC_API_KEY=sk-ant-...
```
其余用默认即可（Sandbox 号码、模型名、向量库路径等）。

## 导入知识库

把 `app/sample_docs/` 下的示例文档向量化写入 Qdrant：
```bash
python scripts/ingest.py
```
> 注意：Qdrant 本地文件模式同一时间只能被一个进程打开。如果 FastAPI 服务正在运行，先停掉再跑此脚本；或改用接口：`curl -X POST http://localhost:8000/admin/ingest`。

## 启动服务

```bash
uvicorn app.main:app --reload --port 8000
```
浏览器打开 http://localhost:8000/health 看到 `{"status":"ok"}` 即正常。

## 暴露到公网（Twilio 要能访问到你的 webhook）

Twilio 需要一个公网 HTTPS 地址回调。本地开发用 ngrok 打洞：
```bash
ngrok http 8000
```
复制 ngrok 给的转发地址，形如 `https://abcd.ngrok-free.app`。

回到 Twilio Sandbox 设置页，把 **WHEN A MESSAGE COMES IN** 的 URL 填为：
```
https://abcd.ngrok-free.app/webhook
```
保存。

## 测试

用刚才绑定的手机号，在 WhatsApp 里给 Sandbox 号码发消息，例如：
- "年假有几天？"
- "怎么连 VPN？"
- "报销流程是什么？"

机器人应基于示例知识库回答，并附上来源文件名。

> Sandbox 限制：会话 24 小时后过期，需重新 `join`；使用的是共享号码。正式上线换成 Twilio 正式 WhatsApp 号码即可解除这些限制。

## 项目结构

```
.
├── app/
│   ├── main.py              # FastAPI 入口 + webhook
│   ├── config.py            # 环境变量配置
│   ├── channel.py           # Twilio 收发消息
│   └── rag/
│       ├── embeddings.py    # 文本向量化（本地模型）
│       ├── store.py         # Qdrant 向量库封装
│       ├── chunking.py      # 文档切片
│       ├── ingest.py        # 入库流程
│       └── pipeline.py      # 检索 + 生成（核心算法）
│   └── sample_docs/         # 示例知识库（可替换成你的企业文档）
├── scripts/ingest.py        # 命令行入库
├── requirements.txt
└── .env.example
```

## 替换成你的企业知识

把你的文档（`.md` / `.txt`）放进 `app/sample_docs/`，重新跑 `python scripts/ingest.py` 即可。

## 常见问题

- **收到消息没回复**：看 uvicorn 终端日志，多半是 `.env` 没填或 Anthropic/Twilio key 不对。
- **webhook 收不到**：确认 ngrok 在跑、Twilio Sandbox 里填的 URL 是 `<ngrok地址>/webhook` 且能访问。
- **想换更强的 embedding / 用 OpenAI**：改 `app/rag/embeddings.py`，并同步改 `EMBEDDING_DIM` 和 Qdrant collection 的向量维度（维度变了需删 `data/` 重建）。
- **想换 LLM**：改 `.env` 里的 `ANTHROPIC_MODEL`。
