"""转人工决策：纯函数，集中"什么情况该给客户联系方式、给什么文案"。

1.0 的转人工是让客户自己拨打人工电话：
- 客户主动发 agent：由 main 直接处理（通知值班人 + 回电话），不走本函数。
- 连续答不出/AI 连续报错达到阈值：给客户回一条联系电话，但不自动通知值班人；
  达到阈值当次之后（already_active）只回普通兜底文案，避免反复刷电话号码。
- 回答了但置信度偏低：答案末尾追加"回复 agent 联系人工"提示。

所有 streak 入参均为**本次之前**的当前值；record_miss/record_error 告诉调用方
是否需要 +1。
"""
from dataclasses import dataclass

from . import responses

AnswerStatus = str  # "answered" | "no_match" | "empty_kb" | "error"


@dataclass(frozen=True)
class HandoffDecision:
    customer_reply: str = ""       # 发给客户的文案（可能含 {phone} 占位符）
    record_miss: bool = False      # 调用方应给 miss_streak +1
    record_error: bool = False     # 调用方应给 error_streak +1
    record_hit: bool = False       # 调用方应清零两个 streak（成功回答）
    low_confidence: bool = False   # 回答置信度偏低，追加转人工提示
    mark_escalated: bool = False   # 调用方应在 handoff_store 标记"已给过联系方式"


def decide(
    *,
    status: AnswerStatus,
    top_score: float | None,
    miss_streak: int,
    error_streak: int,
    already_active: bool,
    miss_threshold: int,
    error_threshold: int,
    low_conf_min: float,
) -> HandoffDecision:
    """根据本次回答结果决定给客户的回复。

    low_conf_min<=0 关闭低置信提示。already_active 表示本会话已经给过联系方式，
    此时达到阈值也不再重复回电话号码（只发普通兜底文案）。
    """
    if status == "empty_kb":
        return HandoffDecision(customer_reply=responses.EMPTY_KB)

    if status == "no_match":
        will_be = miss_streak + 1
        if will_be >= miss_threshold and not already_active:
            return HandoffDecision(
                customer_reply=responses.NO_ANSWER_AUTO,
                record_miss=True,
                mark_escalated=True,
            )
        return HandoffDecision(
            customer_reply=responses.NO_ANSWER,
            record_miss=True,
        )

    if status == "error":
        will_be = error_streak + 1
        if will_be >= error_threshold and not already_active:
            return HandoffDecision(
                customer_reply=responses.ERROR_AUTO,
                record_error=True,
                mark_escalated=True,
            )
        return HandoffDecision(
            customer_reply=responses.ERROR,
            record_error=True,
        )

    # status == "answered"
    low_conf = (
        low_conf_min > 0
        and top_score is not None
        and top_score < low_conf_min
        and not already_active
    )
    return HandoffDecision(record_hit=True, low_confidence=low_conf)
