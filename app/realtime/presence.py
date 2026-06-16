import asyncio
import uuid

_user_streams: dict[uuid.UUID, set[asyncio.Queue]] = {}
_request_feed: set[asyncio.Queue] = set()


def connect(user_id: uuid.UUID, queue: asyncio.Queue) -> None:
    _user_streams.setdefault(user_id, set()).add(queue)


def join_request_feed(queue: asyncio.Queue) -> None:
    _request_feed.add(queue)


def disconnect(user_id: uuid.UUID, queue: asyncio.Queue) -> None:
    streams = _user_streams.get(user_id)
    if streams is not None:
        streams.discard(queue)
        if not streams:
            _user_streams.pop(user_id, None)
    _request_feed.discard(queue)


def streams_for(user_id: uuid.UUID) -> list[asyncio.Queue]:
    return list(_user_streams.get(user_id, ()))


def request_feed() -> list[asyncio.Queue]:
    return list(_request_feed)
