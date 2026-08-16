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
    "• agent: notify the on-duty staff to follow up\n"
    "After an answer you can reply 👍 / 👎 to give feedback."
)

NO_ANSWER = (
    "Sorry, I couldn't find a confident answer to that in the knowledge base.\n"
    "Try rephrasing your question, or reply \"agent\" to have the on-duty staff follow up."
)

EMPTY_KB = (
    "The knowledge base isn't ready yet. Please import documents first "
    "(run `python scripts/ingest.py` or call /admin/ingest)."
)

HANDOFF_NOTIFIED = "The on-duty staff have been notified and will get back to you shortly. Please hold on."
HANDOFF_UNAVAILABLE = "Sorry, we couldn't reach the on-duty staff right now. Please try again later or contact us through another channel."

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
