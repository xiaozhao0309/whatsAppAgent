"""RAG pipeline 测试：mock 掉 embedding、检索与 LLM，验证阈值、历史、长度与状态。"""
from types import SimpleNamespace

import app.rag.pipeline as pipeline
from app.rag.pipeline import AnswerResult


def _hit(score: float, text: str, source: str):
    return SimpleNamespace(score=score, payload={"text": text, "source": source})


class _FakeMessage:
    def __init__(self, content):
        self.message = SimpleNamespace(content=content)


class _FakeCompletions:
    def __init__(self, reply):
        self._reply = reply

    def create(self, **kwargs):
        # 记录传入的 messages，便于断言多轮历史
        self.last_messages = kwargs.get("messages")
        return SimpleNamespace(choices=[_FakeMessage(self._reply)])


class _FakeClient:
    def __init__(self, reply):
        self.chat = SimpleNamespace(completions=_FakeCompletions(reply))


def _patch(monkeypatch, *, points=10, hits=None, reply="答案正文 [来源: hr.md]"):
    monkeypatch.setattr(pipeline, "count_points", lambda: points)
    monkeypatch.setattr(pipeline, "embed_one", lambda q: [0.1, 0.2])
    monkeypatch.setattr(pipeline, "search", lambda vec, limit: hits or [])
    fake_client = _FakeClient(reply)
    monkeypatch.setattr(pipeline, "OpenAI", lambda **kw: fake_client)
    # 用可变 stub 替换 frozen settings，避免真实 key 检查
    fake_settings = SimpleNamespace(
        ark_api_key="test",
        ark_model="test",
        ark_base_url="http://localhost",
        top_k=5,
        rag_score_threshold=0.5,
        answer_max_chars=800,
    )
    monkeypatch.setattr(pipeline, "settings", fake_settings)
    return fake_client


def test_answered_with_sources(monkeypatch):
    hits = [_hit(0.9, "年假 5 天", "hr_faq.md")]
    client = _patch(monkeypatch, hits=hits, reply="年假 5 天 [来源: hr_faq.md]")
    result = pipeline.answer("年假几天")
    assert result.status == "answered"
    assert result.sources == ["hr_faq.md"]
    assert "年假" in result.reply
    # 没有历史时 messages 为 system + 当前 user（2 条）
    assert len(client.chat.completions.last_messages) == 2


def test_empty_kb(monkeypatch):
    _patch(monkeypatch, points=0)
    result = pipeline.answer("随便问")
    assert result.status == "empty_kb"
    assert result.reply == ""


def test_no_hits(monkeypatch):
    _patch(monkeypatch, hits=[])
    result = pipeline.answer("无关问题")
    assert result.status == "no_match"


def test_score_below_threshold_rejects(monkeypatch):
    # 默认阈值 0.5，命中 0.3 -> 拒答，不调用 LLM
    hits = [_hit(0.3, "相关度低", "x.md")]
    client = _patch(monkeypatch, hits=hits)
    result = pipeline.answer("问题")
    assert result.status == "no_match"
    assert result.top_score == 0.3
    # LLM 不应被调用
    assert not hasattr(client.chat.completions, "last_messages")


def test_history_passed_as_messages(monkeypatch):
    hits = [_hit(0.9, "病假规定", "hr.md")]
    client = _patch(monkeypatch, hits=hits, reply="病假也有规定 [来源: hr.md]")
    history = [
        {"role": "user", "content": "年假几天"},
        {"role": "assistant", "content": "5 天"},
    ]
    result = pipeline.answer("那病假呢", history=history)
    assert result.status == "answered"
    msgs = client.chat.completions.last_messages
    # system + 2 history + current = 4
    assert len(msgs) == 4
    assert msgs[1]["content"] == "年假几天"
    assert msgs[-1]["content"] == "那病假呢"


def test_answer_truncated(monkeypatch):
    hits = [_hit(0.9, "内容", "x.md")]
    long_reply = "字" * 2000
    _patch(monkeypatch, hits=hits, reply=long_reply)
    result = pipeline.answer("问题")
    # answer_max_chars 默认 800
    assert len(result.reply) <= 800
    assert result.reply.endswith("…")


def test_truncate_helper():
    assert pipeline._truncate("短", 10) == "短"
    out = pipeline._truncate("a" * 50, 10)
    assert len(out) == 10
    assert out.endswith("…")


def test_model_self_refusal_treated_as_no_match(monkeypatch):
    hits = [_hit(0.9, "内容", "x.md")]
    _patch(monkeypatch, hits=hits, reply="资料里没有相关内容")
    result = pipeline.answer("问题")
    assert result.status == "no_match"
