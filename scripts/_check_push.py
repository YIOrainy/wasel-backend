"""Offline self-check for the Expo push builders (no network, no DB).
Run: PYTHONPATH=. ./.venv/bin/python scripts/_check_push.py
This is the spec for the two TODOs in app/integrations/expo.py.
"""
from app.integrations import expo


def main() -> None:
    # build_messages: one message per token, default-locale (ar) copy, push extras
    data = {"type": "new_bid", "shipment_id": "s1", "bid": {"price": "45.00"}}
    msgs = expo.build_messages(["tokA", "tokB"], "new_bid", data)
    assert len(msgs) == 2, msgs
    title, body = expo.EVENT_COPY[expo.DEFAULT_LOCALE]["new_bid"]
    assert msgs[0] == {
        "to": "tokA", "title": title, "body": body, "data": data,
        "sound": "default", "priority": "high", "channelId": expo.CHANNEL_ID,
    }, msgs[0]
    assert msgs[1]["to"] == "tokB"
    print("build_messages shape (ar default + sound/priority/channel): ok")

    # explicit locale picks the right copy
    en = expo.build_messages(["t"], "new_bid", {}, locale="en")[0]
    assert en["title"] == expo.EVENT_COPY["en"]["new_bid"][0], en
    # unknown locale falls back to the default locale
    fb = expo.build_messages(["t"], "new_bid", {}, locale="fr")[0]
    assert fb["title"] == expo.EVENT_COPY[expo.DEFAULT_LOCALE]["new_bid"][0]
    print("locale select + fallback: ok")

    # every direct event type maps to copy (default locale)
    for ev in ("new_bid", "bid_accepted", "bid_rejected", "shipment_expired"):
        out = expo.build_messages(["t"], ev, {"type": ev})
        assert out and out[0]["title"] == expo.EVENT_COPY[expo.DEFAULT_LOCALE][ev][0], ev
    print("all event types covered: ok")

    # unknown event (e.g. a feed-only one that shouldn't reach push) → nothing
    assert expo.build_messages(["t"], "new_request", {"type": "new_request"}) == []
    print("unknown event -> no messages: ok")

    # dead_tokens: tickets are positional with tokens; flag DeviceNotRegistered only
    tickets = [
        {"status": "ok", "id": "1"},
        {"status": "error", "details": {"error": "DeviceNotRegistered"}},
        {"status": "error", "details": {"error": "MessageTooBig"}},
    ]
    dead = expo.dead_tokens(tickets, ["good", "gone", "other_err"])
    assert dead == ["gone"], dead
    print("dead_tokens picks only DeviceNotRegistered: ok")

    print("\nALL PUSH CHECKS PASSED")


main()
