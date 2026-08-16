"""指令识别测试。"""
from app.commands import parse_command


def test_help_command():
    for text in ["帮助", "菜单", "help", "HELP", " 菜单 "]:
        cmd = parse_command(text)
        assert cmd is not None and cmd.type == "help", text


def test_reset_command():
    for text in ["重新开始", "清空", "新话题", "reset", "clear"]:
        cmd = parse_command(text)
        assert cmd is not None and cmd.type == "reset", text


def test_handoff_command():
    for text in ["转人工", "找人工", "人工客服", "人工", "agent", "human"]:
        cmd = parse_command(text)
        assert cmd is not None and cmd.type == "handoff", text


def test_feedback_command():
    up = parse_command("👍")
    assert up is not None and up.type == "feedback" and up.value == "up"
    down = parse_command("👎")
    assert down is not None and down.type == "feedback" and down.value == "down"
    for text in ["满意", "有用", "不满意", "没用"]:
        cmd = parse_command(text)
        assert cmd is not None and cmd.type == "feedback", text


def test_normal_question_is_not_command():
    for text in ["", "年假有几天？", "那病假呢", "人工怎么请假", "帮助我设置VPN"]:
        assert parse_command(text) is None, text


def test_greeting_command():
    for text in ["你好", "你好。", "hi!", "Hello", "在吗", "嗨～"]:
        cmd = parse_command(text)
        assert cmd is not None and cmd.type == "greeting", text
