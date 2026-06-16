
from typing import Any

import httpx

from app.config import settings

# Default app language (Saudi market → Arabic). Override per user once a
# `locale` is threaded through (see build_messages).
DEFAULT_LOCALE = "ar"

# Android channel the messages target. The app must create a channel with this
# id (importance/sound/vibration are defined there, on the device).
CHANNEL_ID = "shipments"

# locale → { event type → (title, body) } shown on the OS banner. Copy is
# server-side so it's edited/translated in one place.
EVENT_COPY: dict[str, dict[str, tuple[str, str]]] = {
    "ar": {
        "new_bid": ("عرض جديد", "وصلك عرض جديد على شحنتك"),
        "bid_accepted": ("تم قبول عرضك", "تم قبول العرض الذي قدمته"),
        "bid_rejected": ("لم يتم اختيار عرضك", "لم يتم اختيار العرض الذي قدمته"),
        "shipment_expired": ("انتهت صلاحية الطلب", "لم تصل أي عروض قبل انتهاء المهلة"),
    },
    "en": {
        "new_bid": ("New offer", "You received a new offer on your shipment"),
        "bid_accepted": ("Offer accepted", "Your offer was accepted"),
        "bid_rejected": ("Offer not selected", "Your offer wasn't selected"),
        "shipment_expired": ("Request expired", "No offers came in before the deadline"),
    },
}


def _copy(event_type: str, locale: str) -> tuple[str, str] | None:
    """Banner (title, body) for an event in a locale; falls back to the default
    locale, then None if the event has no push copy (feed-only events)."""
    table = EVENT_COPY.get(locale, EVENT_COPY[DEFAULT_LOCALE])
    return table.get(event_type)


def build_messages(
    tokens: list[str],
    event_type: str,
    data: dict[str, Any],
    locale: str = DEFAULT_LOCALE,
) -> list[dict[str, Any]]:
    copy = _copy(event_type, locale)
    if copy is None:
        return []
    title, body = copy
    return [
        {
            "to": token,
            "title": title,
            "body": body,
            "data": data,
            "sound": "default",
            "priority": "high",
            "channelId": CHANNEL_ID,
        }
        for token in tokens
    ]


def dead_tokens(tickets: list[dict[str, Any]], tokens: list[str]) -> list[str]:
    return [
        token
        for ticket, token in zip(tickets, tokens)
        if ticket.get("status") == "error"
        and ticket.get("details", {}).get("error") == "DeviceNotRegistered"
    ]


async def push(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """POST the messages to Expo; return the list of tickets (same order).
    Raises httpx.HTTPError on network/5xx so the calling job can retry."""
    if not messages:
        return []
    headers = {"Content-Type": "application/json"}
    if settings.expo_access_token:
        headers["Authorization"] = f"Bearer {settings.expo_access_token}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(settings.expo_push_url, json=messages, headers=headers)
        resp.raise_for_status()
        return resp.json().get("data", [])
