# Shipment & Bidding Service — Architecture (A–Z)

> Scope: the **bidding half** of the shipment lifecycle — a sender posts a request, captains
> bid a price, the sender accepts one, and unaccepted requests die after **1 hour**. Plus the
> real-time delivery (SSE + FCM) that makes it feel live. This is the design we build now; the
> post-acceptance delivery flow (`picked → out_for_delivery → delivered` + receiver OTP) is a
> **separate** doc.

---

## 0. The decisions, up front

Every choice below was argued against its alternative. The short version:

| Decision | Choice | Rejected alternative | Why |
|---|---|---|---|
| Source of truth | **Postgres** | Redis-as-store | 10k/day ≈ ~1,500 peak open rows. Postgres is bored. A cache buys cache-invalidation pain for a load problem we don't have. |
| The 1h rule | **`expires_at` column + read filter** | Redis TTL | A timestamp is queryable, survives restarts, and the read filter hides expired rows instantly — for free. |
| Expire stale rows | **Procrastinate deferred job** | per-request timers in app memory / cron | Postgres-backed queue (no new infra), fires on time, doubles as shared async-job infra (FCM sends, future reminders). |
| Live updates | **SSE** | WebSocket | All live traffic is server→client (bids, accept, expiry). SSE is one-way, auto-reconnects, far less code. WebSocket only when we ship live GPS-on-map. |
| Wake closed apps | **FCM/APNs** | — | The OS kills the SSE connection when the app backgrounds. Only the platform push system can wake it. |
| Cross-server SSE | **Redis Pub/Sub — deferred** | build now | A single server delivers from local memory. Add Pub/Sub the day we run 2+ instances; it slots into one function. |
| Status type | **App-level `StrEnum` + VARCHAR + CHECK** | native PG `ENUM` | Status set is still growing. Native enum makes every new value an `ALTER TYPE` (non-transactional, irreversible). VARCHAR+CHECK = swap one constraint. |
| Money | **`Numeric(10,2)`** | `float` | `0.1 + 0.2 ≠ 0.3`. Never float for money. |
| Idempotency | **client-minted UUID PK** | idempotency-key middleware | Accept (gate) and bid (unique constraint) are already idempotent. Only *create* isn't — a client UUID fixes it with zero infra. |
| Cancellation | **sender (pending only) · captain withdraws own bid (if not accepted) · admin (any non-terminal)** | admin-only | Sender can abort a request before it's accepted; a captain can pull a bid until it wins; admin can force-cancel anytime. |

---

## 1. The state machine

Backend statuses are the source of truth. **UI states are not backend states** — the app's
`awaiting_offers` and `choose_offer` screens are *both* the single backend state `pending`
(`choose_offer` = `pending && has bids`, derived client-side, never stored).

```
pending ──accept──▶ accepted ──▶ picked ──▶ out_for_delivery ──▶ delivered   (delivery half: separate doc)
   │
   ├──1h job──▶ expired               (terminal; only reachable from pending)
   │
   ├──sender (while pending)──▶ cancelled
   └──admin (any non-terminal)──▶ cancelled
```

```python
class ShipmentStatus(enum.StrEnum):
    PENDING          = "pending"
    ACCEPTED         = "accepted"
    PICKED           = "picked"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED        = "delivered"
    EXPIRED          = "expired"
    CANCELLED        = "cancelled"
```

Rules:
- **Only `pending` (and `expires_at > now()`) accepts bids.** Bidding/accepting is locked to it.
- **`expired` only from `pending`.** Once accepted, the 1h rule is satisfied; the expiry job no-ops.
- **No `in_progress`.** It was a UI label for "accepted, not yet picked," with no distinct server
  event and no timestamp column. Add it later *with* a timestamp if a real "captain departed for
  pickup" event appears.
- **Cancellation:** the **sender** can cancel only while `pending`; the **captain** can withdraw
  their own bid only while it's `pending` (an accepted bid can't be pulled — they're committed);
  **admin** can force-cancel from any non-terminal state. `pending` also dies on its own by the
  expiry job. Captain bid-withdrawal is a hard `DELETE` (no withdrawal history).

---

## 2. Data model

### `shipments` (existing table — changes)

- **+ `status`** — `Enum(ShipmentStatus, native_enum=False, values_callable=enum_values)` → stored
  as VARCHAR + CHECK. Default `pending`. (Replaces the two `# should be enum` TODOs. The `type`
  TODO — document/box — is left untouched, out of scope.)
- **+ `expires_at`** — `DateTime(timezone=True)`, set at creation to `created_at + 1h`. The 1h rule.
- **`price`** → `Numeric(10, 2)` (was `float`).
- **+ partial index** for the captain browse query:
  ```sql
  CREATE INDEX ix_shipments_open ON shipments (created_at) WHERE status = 'pending';
  ```
  Only indexes pending rows (~1,500), stays tiny. (No city column in the index — see §5: inter-city
  delivery means we don't filter requests by city.)

### `bids` (new table)

```python
class Bid(Base):
    __tablename__ = "bids"
    bid_id:      Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True)
    shipment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("shipments.shipment_id", ondelete="CASCADE"), nullable=False)
    capitan_id:  Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    price:       Mapped[Decimal]   = mapped_column(Numeric(10, 2), nullable=False)
    status:      Mapped[str]       = mapped_column(
        Enum(BidStatus, native_enum=False, values_callable=enum_values),
        nullable=False, default=BidStatus.PENDING)
    created_at / updated_at  # standard pair

    __table_args__ = (
        UniqueConstraint("shipment_id", "capitan_id"),   # one bid per captain — re-bid = UPDATE
        CheckConstraint("price > 0"),
        Index("ix_bids_shipment_id", "shipment_id"),
    )

class BidStatus(enum.StrEnum):
    PENDING  = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
```

- **One updatable bid per captain** (not append-only history). Re-bidding is an `UPDATE` of `price`.
- `status` is stored (not derived from `shipment.capitan_id`) so the captain's "my offers" screen
  queries it directly. The accept transaction is already writing these rows anyway.
- On expiry, bids stay `pending` — the shipment's `expired` status tells the story; no extra write.

### `devices` (new table — app-level, shared infra)

FCM/APNs tokens. **Not a shipment thing** — this is the app's one push pipe, reused by every
feature that needs to reach a user when the app is closed.

```python
class Device(Base):
    __tablename__ = "devices"
    device_id: uuid (pk)
    user_id:   uuid (fk users, ondelete CASCADE)
    fcm_token: str (unique)
    platform:  str   # "ios" | "android"
    updated_at: datetime
```

One row per device (multi-device per user is real). Stale tokens are pruned when FCM reports a
token dead on send.

### `users` (existing table — prerequisite change)

- **+ `role`** — needed to gate the admin cancel endpoint. Neither `users` nor the access token
  carries a role today. Add a `role` column (default `"user"`, value `"admin"` for staff) **and put
  it in the access-token claims** so `get_current_user` can expose it without a DB hit. This is a
  **prerequisite** for §6's cancel endpoint.

---

## 3. The real-time layer (SSE + presence + FCM)

### The mental model

A normal request can only talk when the client calls. "A new bid arrived" originates on the server
and must reach a specific user who isn't making a request. So: a **held-open channel** + a
**directory of who's connected** + a **fallback for who isn't**. SSE is the channel, an in-process
dict is the directory, FCM is the fallback.

### The channel — SSE

`GET /events` returns a never-ending HTTP response. Each connection gets an `asyncio.Queue` (its
"mailbox"); the response generator parks on `await queue.get()` until someone elsewhere in the
process drops a message in.

```python
@router.get("/events")
async def events(user: CurrentUser, feed: str | None = None):
    q: asyncio.Queue = asyncio.Queue()
    presence.connect(user.user_id, q)
    if feed == "requests" and user.is_captain:      # captains browsing open requests
        presence.join_request_feed(q)
    async def stream():
        try:
            while True:
                event = await q.get()
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            presence.disconnect(user.user_id, q)
    return StreamingResponse(stream(), media_type="text/event-stream")
```

### The directory — presence (in-process)

Two structures:
- **`user_id → set[queue]`** — direct events to one user (a set, because multi-device).
- **one flat `set[queue]` — the request feed** — captains currently browsing open requests.

```python
_streams: dict[uuid.UUID, set[asyncio.Queue]] = {}   # direct
_request_feed: set[asyncio.Queue] = set()            # new-request broadcast
```

### The fallback — FCM

When `queues_for(user_id)` is empty, the app is backgrounded → no channel → send via FCM (see §2
`devices`). Google/Apple wake the phone; tap → app opens → SSE reconnects.

### `notify()` — the one seam

```python
async def notify(user_id, event_type, payload):
    msg = {"type": event_type, **payload}
    live = presence.queues_for(user_id)
    if live:
        for q in live:
            q.put_nowait(msg)        # SSE
    else:
        await fcm_send(user_id, msg) # fallback
```

Everything calls this. When we go multi-server, only the "push to queues" step changes (Redis
Pub/Sub carries the event to the server holding the queue) — the seam stays.

### Event payloads — fat events

Push **enough to render**, so the client never round-trips back for details:

```
event: new_bid
data: {"type":"new_bid","bid":{"bid_id":"…","shipment_id":"…","price":45.00,
        "captain":{"name":"Ahmad","rating":4.8,"avatar_url":"…","total_trips":312},
        "created_at":"2026-06-14T10:33:00Z"}}
```

### Snapshot + deltas

SSE can drop messages during a disconnect and does not replay by default. So:
1. On opening a page (and on every reconnect): `GET` the authoritative list (the **snapshot**).
2. SSE then streams **deltas** on top.

The REST endpoints and the stream are **not redundant** — snapshot vs deltas. (`Last-Event-ID`
resume is an optimization; deferred — re-GET-on-reconnect covers it.)

---

## 4. Event routing

| Event | Goes to | Transport |
|---|---|---|
| `new_bid` | the shipment's **sender** (`user_id`) | SSE if connected, **else FCM** |
| `bid_accepted` | the **winning captain** | SSE if connected, **else FCM** |
| `bid_rejected` | each **losing captain** | SSE if connected, **else FCM** |
| `shipment_expired` | the **sender** | SSE if connected, **else FCM** |
| `new_request` | **all captains in the request feed** (any city) | **SSE only** — offline captains catch up via `GET` on reopen |

There is no separate machinery for rejections or expiry — they ride the same `notify()`.

---

## 5. Why no city filtering on `new_request`

Wasel is **inter-city** delivery (Riyadh→Jeddah). Filtering open requests by pickup city is unfair —
a captain in Jeddah may want a Riyadh-origin job. So `new_request` broadcasts to **every captain
currently in the request feed**, regardless of city. No city index. Senders watching their own
shipment don't opt into the feed, so they aren't spammed with requests.

Offline captains are **not** FCM'd on new requests — at hundreds/day that's notification spam that
gets the app muted. They pull the open list on reopen. Targeted push to *nearby/relevant* offline
captains (geo + fairness) is a **v2** growth feature.

---

## 6. Flows

### Create — `POST /shipments` (any user)
- **Client mints the UUID** and sends it as the PK → idempotent create (a retry hits the PK, returns
  the existing row; catch `IntegrityError` like the `DuplicateLocationError` path).
- Server sets `expires_at = now() + 1h`, `status = pending`.
- Enqueue a **Procrastinate** job deferred to `expires_at` (see §7).
- `notify_request_feed("new_request", …)` → all browsing captains.

### Bid — `POST /shipments/{id}/bids` (captains only)
- Authz: `CurrentCaptain` (has a `capitan_profile`).
- Guard: shipment must be `pending` and not expired.
- Upsert (one bid per captain — `unique(shipment_id, capitan_id)`). Re-bid = `UPDATE` price.
- `notify(sender_id, "new_bid", …)`.

### Accept — `POST /bids/{id}/accept` (sender/owner only) — **the correctness keystone**

One conditional `UPDATE` is the lock. `rowcount` is the source of truth — not a prior `SELECT`.

```python
async with session.begin():
    bid = await dal.get_bid(bid_id)                 # grab price + capitan_id (same TX)
    result = await session.execute(
        update(Shipment)
        .where(Shipment.shipment_id == shipment_id,
               Shipment.sender_id == sender_id,      # authz folded into the gate
               Shipment.status == ShipmentStatus.PENDING,
               Shipment.expires_at > func.now())     # not expired
        .values(status=ShipmentStatus.ACCEPTED,
                capitan_id=bid.capitan_id,
                price=bid.price,                      # snapshot agreed price
                accepted_at=func.now()))
    if result.rowcount == 0:
        raise ShipmentNotAcceptableError()           # → 409 Conflict
    await session.execute(                            # winner accepted, siblings rejected
        update(Bid).where(Bid.shipment_id == shipment_id)
        .values(status=case((Bid.bid_id == bid_id, BidStatus.ACCEPTED),
                            else_=BidStatus.REJECTED)))
# after commit:
await notify(bid.capitan_id, "bid_accepted", …)
for loser in losers: await notify(loser, "bid_rejected", …)
```

Why it's correct:
- The `WHERE` predicate **is** the lock — Postgres row-locks for the statement; first matching writer
  wins, the rest get `rowcount=0`. No `SELECT ... FOR UPDATE`, no app lock, no Redis lock.
- **Double-tap** → second call sees `status=accepted` → `rowcount=0` → clean **409**. Client also
  disables the button.
- **Expiry race** (59:59) → disjoint predicates (`expires_at > now()` vs `< now()`) → exactly one wins.
- **`price` snapshotted** at accept → a later bid edit can't change the agreed price.
- Lost race → **`409 Conflict`**, code `shipment_not_acceptable`.

### Expire — Procrastinate job (see §7)

### Cancel — `POST /shipments/{id}/cancel`
- **No `/admin` prefix.** One handler, `CurrentUser`, branches on the JWT `role` claim:
  **admin → any non-terminal state**; **sender → only while `pending`** (`WHERE sender_id=? AND status='pending'`);
  anyone else → `404` (the sender path's ownership filter makes non-owners miss). Requires the
  `users.role` prerequisite (§2).

### Withdraw bid — `DELETE /shipments/{id}/bids/{bid_id}` (captain)
- A captain pulls **their own** bid, **hard `DELETE WHERE bid_id=? AND capitan_id=? AND status='pending'`**.
  `404` if not theirs/missing, `409` if already accepted/rejected.
- **Race with accept:** withdraw deletes `WHERE status='pending'`; accept's first gate claims the
  winning bid with `UPDATE ... WHERE status='pending'`. They contend on one row → exactly one wins,
  so a withdrawn bid can never be accepted and an accepted bid can never be withdrawn.

---

## 7. Expiry via Procrastinate

A **deferred guarded job**, not a polling loop and not a cancellable timer.

```python
@app.task
async def expire_shipment(shipment_id: uuid.UUID):
    # guarded: no-op if already accepted/cancelled. Same SQL whether the job is early or late.
    result = await session.execute(
        update(Shipment)
        .where(Shipment.shipment_id == shipment_id,
               Shipment.status == ShipmentStatus.PENDING,
               Shipment.expires_at <= func.now())
        .values(status=ShipmentStatus.EXPIRED)
        .returning(Shipment.sender_id))
    await session.commit()
    row = result.first()
    if row:
        await notify(row.sender_id, "shipment_expired", {"shipment_id": shipment_id})
```

- **Enqueued at create**, deferred to `expires_at`.
- **No cancellation on accept.** If a shipment is accepted before the hour, the job still fires,
  matches 0 rows (guard), and no-ops. Stale jobs are harmless by construction.
- **Enforcement is already instant** via the read filter (`WHERE status='pending' AND expires_at > now()`
  hides expired rows the moment the clock passes). The job only flips `status` and fires the
  *notification*.
- **Cost:** runs a `procrastinate worker` process; new dependency. Justified because it becomes
  shared async-job infra (async FCM sends, delivery-flow reminders, push retries).

---

## 8. Endpoint surface

| Method | Path | Who | Notes |
|---|---|---|---|
| `POST` | `/shipments` | any user | client UUID (idempotent); sets `expires_at`; enqueues expiry job |
| `GET` | `/shipments?status=pending` | captains | browse open requests (reopen catch-up) |
| `GET` | `/shipments/{id}` | owner or assigned captain | |
| `GET` | `/shipments/{id}/bids` | **owner only** | bid-list snapshot |
| `POST` | `/shipments/{id}/bids` | **captains only** | upsert; shipment must be `pending` & not expired |
| `DELETE` | `/shipments/{id}/bids/{bid_id}` | **captain (own bid)** | withdraw own `pending` bid; 409 if accepted/rejected |
| `POST` | `/shipments/{id}/bids/{bid_id}/accept` | **owner only** | bid-gate + shipment-gate; 409 on lost race / withdrawn |
| `POST` | `/shipments/{id}/cancel` | **sender (pending) or admin (any non-terminal)** | role-branched in one handler |
| `GET` | `/events` | any user | SSE; `?feed=requests` → request feed (captains only) |
| `POST` | `/devices` | any user | register/refresh FCM token *(not built yet)* |

Authz reuses `CurrentUser` + an owner/captain guard modeled on `get_owned_saved_location`
(**404 not 403** when it belongs to someone else, so existence doesn't leak). `CurrentCaptain` =
"has a `capitan_profile`" (existing `is_captain`).

---

## 9. Deferred (don't build yet)

| Item | Add when |
|---|---|
| Redis Pub/Sub for SSE | running 2+ app instances |
| WebSocket channel | shipping live captain-on-map GPS |
| FCM on `new_request` + targeted captain dispatch | v2 fill-rate optimization (needs geo + fairness) |
| Idempotency-key layer | an endpoint with a non-dedupable money side-effect (payment capture) — also where Redis TTL finally fits |
| `Last-Event-ID` SSE resume | gap-free reconnect becomes a real complaint |
| Admin RBAC | building the admin panel (a `role` flag stands in for now) |
| Delivery half (`picked → out_for_delivery → delivered` + receiver OTP) | separate doc/flow |
| `in_progress` status | a real "captain departed for pickup" event with a timestamp exists |
| Shipment `type` enum (document/box) | the type feature is scoped |
