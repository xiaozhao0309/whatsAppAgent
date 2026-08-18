"""转人工决策纯函数测试。"""
from app import responses
from app.handoff_policy import decide

KW = dict(miss_threshold=2, error_threshold=2, low_conf_min=0.6)


def test_empty_kb():
    d = decide(
        status="empty_kb", top_score=None, miss_streak=9, error_streak=9,
        already_active=False, **KW,
    )
    assert d.customer_reply == responses.EMPTY_KB
    assert not d.record_miss and not d.record_error and not d.record_hit
    assert not d.mark_escalated


def test_no_match_first_time_no_phone():
    d = decide(
        status="no_match", top_score=0.3, miss_streak=0, error_streak=0,
        already_active=False, **KW,
    )
    assert d.record_miss is True
    assert d.customer_reply == responses.NO_ANSWER
    assert d.mark_escalated is False


def test_no_match_second_time_gives_phone():
    d = decide(
        status="no_match", top_score=0.3, miss_streak=1, error_streak=0,
        already_active=False, **KW,
    )
    assert d.record_miss is True
    assert d.customer_reply == responses.NO_ANSWER_AUTO  # 含 {phone} 占位
    assert d.mark_escalated is True
    assert "{phone}" in d.customer_reply


def test_no_match_after_already_active_does_not_repeat_phone():
    d = decide(
        status="no_match", top_score=0.3, miss_streak=5, error_streak=0,
        already_active=True, **KW,
    )
    assert d.customer_reply == responses.NO_ANSWER
    assert d.mark_escalated is False


def test_error_first_time_no_phone():
    d = decide(
        status="error", top_score=None, miss_streak=0, error_streak=0,
        already_active=False, **KW,
    )
    assert d.record_error is True
    assert d.customer_reply == responses.ERROR
    assert d.mark_escalated is False


def test_error_second_time_gives_phone():
    d = decide(
        status="error", top_score=None, miss_streak=0, error_streak=1,
        already_active=False, **KW,
    )
    assert d.record_error is True
    assert d.customer_reply == responses.ERROR_AUTO
    assert d.mark_escalated is True
    assert "{phone}" in d.customer_reply


def test_error_after_already_active_does_not_repeat_phone():
    d = decide(
        status="error", top_score=None, miss_streak=0, error_streak=5,
        already_active=True, **KW,
    )
    assert d.customer_reply == responses.ERROR
    assert d.mark_escalated is False


def test_answered_high_confidence():
    d = decide(
        status="answered", top_score=0.85, miss_streak=1, error_streak=1,
        already_active=False, **KW,
    )
    assert d.record_hit is True
    assert d.low_confidence is False
    assert d.mark_escalated is False


def test_answered_low_confidence_appends_hint():
    d = decide(
        status="answered", top_score=0.55, miss_streak=0, error_streak=0,
        already_active=False, **KW,
    )
    assert d.record_hit is True
    assert d.low_confidence is True


def test_low_confidence_disabled_when_min_zero():
    d = decide(
        status="answered", top_score=0.55, miss_streak=0, error_streak=0,
        already_active=False, miss_threshold=2, error_threshold=2, low_conf_min=0,
    )
    assert d.low_confidence is False


def test_answered_low_confidence_suppressed_when_already_active():
    d = decide(
        status="answered", top_score=0.55, miss_streak=0, error_streak=0,
        already_active=True, **KW,
    )
    assert d.low_confidence is False
