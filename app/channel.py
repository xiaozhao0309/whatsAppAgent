"""Twilio 通道层：负责"把消息发回 WhatsApp"。

收消息由 FastAPI webhook 处理，发消息统一走这里。
"""
from twilio.rest import Client

from .config import settings


def _client() -> Client:
    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


def send_whatsapp(to: str, body: str) -> None:
    """给某个 WhatsApp 用户发一条文本消息。

    to 格式为 "whatsapp:+8613..."，与 Twilio webhook 里 From 字段一致。
    """
    _client().messages.create(
        from_=settings.twilio_whatsapp_number,
        body=body,
        to=to,
    )
