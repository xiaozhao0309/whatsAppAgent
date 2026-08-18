"""Customer-facing reply strings, kept in one place.

All wording lives here so the business can review and change it without
touching the request-handling logic.
"""

WELCOME = (
    "Hi! I'm your company knowledge assistant 👋\n"
    "Just ask me a question, for example:\n"
    "• How many days of annual leave do I get?\n"
    "• How do I connect to the VPN?\n"
    "• What is the expense reimbursement process?\n"
    "Reply \"help\" to see everything I can do."
)

HELP = (
    "📖 I can answer questions from the company knowledge base.\n\n"
    "Send your question and I'll reply with a sourced answer.\n"
    "Commands:\n"
    "• help / menu: show this message\n"
    "• reset: clear the current conversation\n"
    "• agent: get the support phone number to reach a human\n"
    "After an answer you can reply 👍 / 👎 to give feedback."
)

NO_ANSWER = (
    "Sorry, I couldn't find a confident answer to that in the knowledge base.\n"
    "Try rephrasing your question, or reply \"agent\" to have the on-duty staff follow up."
)

# 连续答不出：回复联系电话（不自动通知值班人，把选择权交给客户）。
# {phone} 由调用方用 settings.contact_phone_number 填充。
NO_ANSWER_AUTO = (
    "Sorry, I couldn't find a confident answer to that. "
    "For further help, please contact our support team at {phone}."
)

# AI 服务连续报错：回复联系电话。
ERROR_AUTO = (
    "Sorry, the knowledge service is temporarily unavailable. "
    "For immediate help, please contact our support team at {phone}."
)

# 客户主动发 agent：回复联系电话（后台仍会通知值班人，见 main.py）。
CONTACT_HUMAN = "You can reach our on-duty staff at {phone}."

# 低置信度回答后追加的转人工提示（不自动转，只给客户选择权）。
LOW_CONFIDENCE_HINT = "\n\nNot sure that fully answers your question? Reply \"agent\" to reach our support team."

EMPTY_KB = (
    "The knowledge base isn't ready yet. Please import documents first "
    "(run `python scripts/ingest.py` or call /admin/ingest)."
)

RATE_LIMITED = "You're sending messages a bit too quickly. Please try again in a moment."
MESSAGE_TOO_LONG = "Your message is too long. Please shorten it and resend (under 2000 characters)."

RESET_DONE = "Conversation reset. Feel free to ask a new question."

THANKS_FEEDBACK = "Thanks for your feedback 🙏"

ERROR = "Sorry, something went wrong while handling your question. Please try again; if it keeps happening, contact an administrator."

SESSION_RESTARTED = "I've started a fresh conversation. Could you tell me your question again?"

FEEDBACK_HINT = "\n\n---\nReply 👍 / 👎 to let us know whether this answer was helpful."


def with_feedback_hint(text: str) -> str:
    """Append the feedback hint to the end of an answer."""
    return text + FEEDBACK_HINT
