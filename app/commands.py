"""指令识别：把客户消息中的特殊指令与普通问题区分开。

返回 (CommandType, 附带值)；普通消息返回 None。
识别基于归一化后的文本，去除首尾空白、大小写不敏感（针对英文 help）。
"""
from dataclasses import dataclass
from typing import Literal, Optional

CommandType = Literal["help", "reset", "handoff", "feedback", "greeting"]

HELP_KEYWORDS = {"帮助", "菜单", "功能", "help", "menu", "?"}
RESET_KEYWORDS = {"重新开始", "清空", "新话题", "重置", "reset", "clear", "new"}
HANDOFF_KEYWORDS = {"转人工", "找人工", "人工客服", "人工", "handoff", "agent", "human"}
POSITIVE_FEEDBACK = {"👍", "👍🏻", "👍🏼", "👍🏽", "👍🏾", "👍🏿", "满意", "有用"}
NEGATIVE_FEEDBACK = {"👎", "👎🏻", "👎🏼", "👎🏽", "👎🏾", "👎🏿", "不满意", "没用"}
# 纯问候语：只回欢迎/寒暄，不送 RAG（避免"你好"被当成问题去检索）
GREETING_KEYWORDS = {
    "你好", "您好", "嗨", "哈喽", "hi", "hello", "hey", "halo", "hola", "在吗", "在么", "在不在"
}


@dataclass(frozen=True)
class Command:
    type: CommandType
    value: str = ""  # feedback: "up" | "down"


def parse_command(body: str) -> Optional[Command]:
    """识别指令；非指令返回 None。

    反馈表情单独成条时识别为 feedback；包含在长句中的表情不识别，
    避免误判普通文本。
    """
    if not body:
        return None
    text = body.strip()
    lowered = text.lower()

    if lowered in HELP_KEYWORDS:
        return Command("help")
    if lowered in RESET_KEYWORDS:
        return Command("reset")
    if lowered in HANDOFF_KEYWORDS:
        return Command("handoff")
    # 问候语：去掉末尾中英文标点后再匹配，如"你好。""hi!"
    if lowered.rstrip("。.！!？?，,~～ ") in GREETING_KEYWORDS:
        return Command("greeting")
    if text in POSITIVE_FEEDBACK or lowered in {"yes", "good"}:
        return Command("feedback", "up")
    if text in NEGATIVE_FEEDBACK or lowered in {"no", "bad"}:
        return Command("feedback", "down")
    return None
