# Trips Split — Implementation Plan (schema v2)

Implements the design settled in the 2026-08-19 grilling session, revised to **v2:
winning-bid-is-the-trip** (design page: claude.ai artifact "The Trips Split").

Target shape: `packages` (request + the single status machine) · `trips` (born at
accept, references the winning bid; price/captain **derived**, never copied) ·
`trip_otps` (hashed, ≤1 live per purpose) · `addresses` (normalized, immutable) ·
`ratings` per (trip, direction).

Seven phases, each one branch/PR with its own alembic migration. Ordering is
dependency-driven: **bids must freeze before trips can derive from them**; OTPs and
ratings need the trips FK; the rename goes last because it is pure mechanics.

> Migrations below are single-cutover (backfill + drop in one revision) because this
> is pre-production. If a real deployment exists by the time a phase lands, split that
> phase into expand → backfill → contract and keep dual-reads for one release.
> Either way: snapshot the DB before any migration that drops columns.

---

## Phase 0 — Lock the remaining decisions

Defaults staked here so nothing blocks; change them now or they ship as written.

- [ ] **Winning bid keeps `status = 'pending'`.** The enum becomes
      `pending / rejected / voided` — there is no `accepted` value; acceptance is
      expressed by the trip row referencing the bid. Consequence: "open bids for a
      package" queries must anti-join trips. Alternative (add a `won` value) is
      cosmetic; decide once.
- [ ] **Wire contract stays stable through phases 1–5.** `ShipmentRead` keeps its
      flat shape (`price`, `promisedDeliveryTime`, `acceptedAt`, milestones, `capitan`)
      and is populated from joins. Mobile breaks only at Phase 6 (rename), and even
      then old routes alias for one release.
- [ ] **OTPs become show-once.** With `code_hash` there is no way to re-display a
      code. `GET /shipments/{id}/otps` is replaced by plaintext-in-accept-response +
      a re-issue endpoint (void old, mint new, return plaintext once). This is a
      mobile-visible flow change — confirm with the app before Phase 3.
- [ ] **Addresses phase is deferrable.** Pure normalization, no lifecycle coupling.
      It stays Phase 5 but can slip after Phase 6 without breaking anything.

---

## Phase 1 — Freeze bids (immutability + history)

*Why first: `trips.bid_id` derives price and captain from the bid row. Today a
re-bid is an in-place UPDATE (`app/services/shipments/service.py:147`) and a
withdraw is a DELETE (`service.py:363`) — either would rewrite or erase a live
trip's source of truth.*

**Migration `p1_bids_freeze`**
- [ ] Recreate the `bidstatus` CHECK constraint with `voided` added
      (`native_enum=False` + `create_constraint=True` means it's a varchar CHECK —
      drop and re-add).
- [ ] Drop `uq_bids_shipment_capitan`; create partial unique index
      `uq_bids_live_per_capitan ON bids (shipment_id, capitan_id) WHERE status = 'pending'`.

**Code**
- [ ] `place_bid` (`service.py:119`): replace the upsert with, in one transaction:
      `UPDATE bids SET status='voided' WHERE shipment_id=… AND capitan_id=… AND status='pending'`,
      then INSERT a fresh row. Bid history is now real rows, not overwrites.
- [ ] `withdraw_bid` (`service.py:354`): DELETE → `status='voided'`. Response stays 204.
- [ ] `BidsDAL.get_for_shipment` / `get_for_captain` (`dal.py:73,82`): default to
      excluding `voided` unless a history flag is passed.
- [ ] `Bid` model (`app/db/models/bid.py:73`): swap the UniqueConstraint for the
      partial `Index`.

**Tests:** re-bid produces two rows (one voided); two concurrent live bids by the
same captain on one shipment → integrity error; withdrawn bid still queryable with
history flag.

---

## Phase 2 — `trips` table + accept rewrite (the core)

**Migration `p2_trips`**
- [ ] Create `trips`: `trip_id` PK · `shipment_id` FK (renamed in Phase 6) ·
      `bid_id` FK **UNIQUE** · `created_at` (≡ accepted_at) · `picked_at` ·
      `out_for_delivery_at` · `delivered_at` · `cancelled_at` · `cancelled_by` FK users ·
      `cancel_reason`.
- [ ] `CREATE UNIQUE INDEX uq_trips_live_package ON trips (shipment_id) WHERE cancelled_at IS NULL;`
- [ ] Backfill: for every shipment with `capitan_id IS NOT NULL`, insert a trip
      joined to its `status='accepted'` bid; copy `accepted_at → created_at` and the
      three milestone stamps. Cancelled-after-accept shipments get
      `cancelled_at = updated_at` (best available approximation), `cancelled_by = sender_id`.
- [ ] `UPDATE bids SET status='pending' WHERE status='accepted'` (winner is now
      expressed by the trip row), then recreate the CHECK as `pending/rejected/voided`.
- [ ] Drop from `shipments`: `capitan_id`, `price`, `promised_delivery_time`,
      `accepted_at`, `picked_at`, `out_for_delivery_at`, `delivered_at`.
      (OTP columns survive until Phase 3.)

**Code**
- [ ] New `app/db/models/trip.py`; remove from `Shipment`
      (`app/db/models/shipment.py`): `capitan_id`, `capitan`, `capitan_profile`,
      price/promise/milestones. Add `Shipment.trips` + a `live_trip` viewonly
      relationship (`and_(cancelled_at.is_(None))`).
- [ ] Remove `BidStatus.ACCEPTED` (`_enums.py:14`).
- [ ] `accept_bid` (`service.py:185`) becomes: verify bid is pending and belongs to
      the shipment → `INSERT trips (trip_id, shipment_id, bid_id)` — a unique
      violation here **is** the race loss, map to `ShipmentNotAcceptableError` (409) →
      `UPDATE shipments SET status='accepted' WHERE … status='pending' AND expires_at > now()`
      (0 rows → raise, whole txn rolls back, trip insert included) → reject other
      pending bids → notifications unchanged.
- [ ] Milestones: `mark_picked_up` / `mark_out_for_delivery` / `mark_delivered`
      (`service.py:388–430`) and `ShipmentsDAL.update_status` (`dal.py:55`) write
      `shipments.status` **and** the trip timestamp in the same transaction.
- [ ] **New: captain cancel / re-open** (the reason tombstones exist):
      `POST /shipments/{id}/trip/cancel` (captain-only) → set `cancelled_at`,
      `cancelled_by`, `cancel_reason`; void the winning bid; shipment back to
      `pending`; re-arm `expires_at = now() + BIDDING_WINDOW`; re-enqueue the expiry
      job (`jobs.py` dispatcher); `notify_request_feed("new_request", …)`.
      Sender cancel (`service.py:297,324`) additionally tombstones the live trip when
      one exists (reason `sender_cancelled`), status → `cancelled` as today.
- [ ] `ShipmentsDAL.get_for_user` role=captain (`dal.py:32`): join
      `trips → bids ON bids.bid_id = trips.bid_id WHERE bids.capitan_id = :user`.
- [ ] Eager loading: `_CAPITAN` (`dal.py:12`) → `live_trip → bid → capitan → capitan_profile`.
- [ ] `ShipmentRead` (`schemas.py:52`): same wire shape, fields resolved from
      `live_trip` (`price = trip.bid.price`, `accepted_at = trip.created_at`, …) via
      model validators — mobile sees no change.
- [ ] `CapitanProfile.shipments` viewonly (`capitan_profile.py:47`): rebuild through
      trips→bids or delete in favor of the DAL query.

**Tests:** two concurrent accepts → exactly one trip, loser 409; accept after
captain-cancel creates a second trip (first tombstoned); milestone writes touch both
rows atomically; captain "my shipments" returns via join; expiry re-arm fires.

---

## Phase 3 — `trip_otps` (hashed, shown once, re-issuable)

**Migration `p3_trip_otps`**
- [ ] Create `trip_otps`: `otp_id` PK · `trip_id` FK · `purpose` CHECK
      (`pickup`/`delivery`) · `code_hash` · `expires_at` · `consumed_at` · `created_at`.
- [ ] `CREATE UNIQUE INDEX uq_trip_otps_live ON trip_otps (trip_id, purpose) WHERE consumed_at IS NULL;`
      (expiry is enforced in code — a partial index can't reference `now()`).
- [ ] Backfill: hash `shipments.pickup_otp` / `delivery_otp` into rows for live,
      undelivered trips. Drop both columns from `shipments`.

**Code**
- [ ] OTP minting moves from `create` (`service.py:94`) to the accept flow — codes
      only mean something once a trip exists. Plaintext returned once in the accept
      response / sender push.
- [ ] Verification in `mark_picked_up` / `mark_delivered`: constant-time hash compare
      (`hmac.compare_digest` over a keyed hash — codes are 4 digits, so an unkeyed
      digest would be trivially reversible), check `expires_at`, set `consumed_at`.
- [ ] Replace `GET /shipments/{id}/otps` (`api/shipments.py:162`) with
      `POST /shipments/{id}/otps/reissue` (sender-only): void live code for the
      purpose, mint + return plaintext once.
- [ ] Update `OTP.md`.

**Tests:** consumed code can't be replayed; re-issue voids the old code; expired code
rejected; only one live row per purpose.

---

## Phase 4 — Ratings per (trip, direction)

**Migration `p4_ratings_direction`**
- [ ] Add `trip_id` FK, `rater_id`, `direction` CHECK
      (`sender_to_captain` / `captain_to_sender`).
- [ ] Backfill: `trip_id` via shipment's delivered trip; `rater_id = sender_id`;
      `direction = 'sender_to_captain'`.
- [ ] Replace `uq_ratings_shipment` (`rating.py:52`) with UNIQUE `(trip_id, direction)`.
      Drop `shipment_id` and `capitan_id`.

**Code**
- [ ] `RatingsService.rate` (`app/services/ratings/service.py`): gate on the trip
      being delivered; captain-side rating allowed for `direction='captain_to_sender'`.
- [ ] Captain stats (`get_stats_for_captain`, `_refresh_capitan_rating` — keep its
      existing concurrency handling): resolve captain via `trips → bids.capitan_id`,
      filter `direction='sender_to_captain'`.
- [ ] Routes (`api/ratings.py`): keep `POST /shipments/{id}/rating` as an alias that
      resolves the delivered trip; add trip-addressed routes; new endpoint for
      captain-rates-sender (product call — can ship disabled).

**Tests:** one rating per direction per trip; captain average unaffected by
captain→sender ratings; backfilled rows resolve the right trip.

---

## Phase 5 — `addresses` (deferrable)

**Migration `p5_addresses`**
- [ ] Create `addresses`: `address_id` PK · `city` · `address_line` · `lat` · `lng` ·
      `notes`. No UPDATE path — immutable once referenced; edits mint new rows.
- [ ] Backfill from `shipments` pickup/destination pairs and from `saved_locations`.
- [ ] `shipments`: add `pickup_address_id` / `destination_address_id` FKs (NOT NULL
      after backfill); drop the six inline columns.
- [ ] `saved_locations`: add `address_id` FK; replace
      `uq_saved_locations_user_coords` (`saved_location.py:19`) with UNIQUE
      `(user_id, address_id)`; drop `address_line`, `city`, `lat`, `lng`, `notes`.

**Code**
- [ ] `ShipmentRequest` (`schemas.py:39`): accept `pickup_address_id` **or** inline
      fields (inline → create address row). `ShipmentRead` keeps flat fields via join.
- [ ] `notify_request_feed` payload (`service.py:107`): cities come from the joined
      addresses.
- [ ] Saved-locations service/API switch to address references.

---

## Phase 6 — Rename `shipments` → `packages`

Pure mechanics, its own PR, **no behavior change mixed in**.

- [ ] Migration: `ALTER TABLE shipments RENAME TO packages`; rename PK column, FKs,
      indexes, CHECK constraints (`shipmentstatus` → `packagestatus`).
- [ ] Code: `Shipment` → `Package`, `ShipmentStatus` → `PackageStatus`, service/DAL/
      schema/exception renames (`ShipmentNotAcceptableError` → `PackageNotAcceptableError`, …).
- [ ] API: mount the router at `/packages` **and** keep `/shipments` as deprecated
      aliases (same handlers, two prefixes) until the app migrates. DTO field
      `shipmentId` gains alias `packageId`.
- [ ] Update `SHIPMENT.md`, `PRD.md`, `MVP.md` references.

---

## Phase 7 — Cleanup

- [ ] Remove `/shipments` alias routes once mobile is confirmed migrated.
- [ ] Delete dead code: any remaining viewonly joins, `ShipmentOtps` schema, unused
      enum values.
- [ ] Re-check `ix_shipments_open` (`shipment.py:136`) survived the rename with a
      matching predicate; add an index on `trips(bid_id)` companion FK lookups if the
      unique constraint didn't already create one (it did — verify).
- [ ] Docs pass: design artifact, `README.md`, ADR note if you keep one.

---

## Invariants to test at every phase (the regression net)

1. `packages.status ∈ {accepted…delivered}` ⇔ exactly one trip with
   `cancelled_at IS NULL` for that package.
2. A trip's `bid_id` always points at a bid whose row never mutates after the trip
   is created (voided old rows are new-row history, not edits).
3. At most one live OTP per (trip, purpose); consumed rows are permanent.
4. Two concurrent accepts on one package: one commit, one 409 — asserted by an
   actual two-session test, not code review.
