# Object Storage (Garage) — Implementation Plan

Implements the foundation settled in the 2026-08-22 grilling session: a self-hosted,
S3-compatible object store (**Garage**, single node) running inside the existing
`docker-compose.yml`, a storage abstraction in the app that hides the bucket and
exposes put/get/presign/multipart, and a live check script that proves the whole
add → read flow end to end — **before** any HTTP endpoint exists and before anything
touches the server.

Scope of this plan is infra + foundation only. Mobile-facing endpoints
(`/files/presigned-upload`, `/files/{id}/complete`, the worker pipeline) are a
separate plan after this one is verified.

---

## Decisions locked

Changing any of these changes the work; otherwise they ship as written.

| # | Decision | Why |
|---|----------|-----|
| D1 | **Garage**, not MinIO/RustFS. Single node, `replication_factor = 1`. | MinIO CE is archived; RustFS is alpha on a public IP. Garage has every feature the design needs (presign, multipart + `ListParts`, range GET, CORS, abort-incomplete lifecycle). |
| D2 | Garage is a **service in the same `docker-compose.yml`** for laptop and server. | Local = prod. Only `.env` differs. |
| D3 | The abstraction **hides the bucket**. Callers pass keys only. `S3_BUCKET=wasel`. | One app, one key, one bucket. |
| D4 | **Deterministic, entity-derived keys** with no file extension: `avatars/{user_id}`, `packages/{package_id}`, `documents/{user_id}/{doc_kind}`. Content type lives on the object. | Home page can build the avatar key from the captain id with no lookup. Re-upload overwrites. User ids are UUIDs → unguessable. |
| D5 | Prefix is `packages/` **now**, even though the table is still `shipments`. | Keys are forever; `TRIPS_SPLIT_PLAN.md` renames the table. |
| D6 | **Two endpoints**: `S3_ENDPOINT` (app → Garage, `http://garage:3900`) and `S3_PUBLIC_ENDPOINT` (what presigned URLs are signed for; `http://localhost:3900` locally, `https://s3.<domain>` on the server). | SigV4 signs the `Host`. A presigned URL only works at the host it was signed for. |
| D7 | Presigned PUT **always signs `Content-Length`**; `x-amz-checksum-sha256` is **optional** (signed when provided). | Size cap enforced by Garage on direct uploads. Hash becomes required in the endpoint phase when dedup lands. |
| D8 | **Multipart is in the foundation** (create / presign part / list parts / complete / abort). | It is the one Garage feature to prove before committing the server. |
| D9 | One-time **bootstrap script** per environment; resulting access key/secret pasted into `.env`. No auto-provisioning at app startup. | Explicit, idempotent, identical on the server. |
| D10 | **Everything runs in compose.** The check script runs inside the `app` container. `Dockerfile` gains `COPY scripts ./scripts`. | No host venv / uv exists. Same command verifies the server after deploy. |
| D11 | Check script proves presigned URLs **at the public host**: it connects to `host.docker.internal:3900` while sending the signed `Host: localhost:3900` header. Controlled by `CHECK_PRESIGN_CONNECT_HOST` (set locally, unset on the server). | Catches a wrong `S3_PUBLIC_ENDPOINT` before the mobile team does. |
| D12 | `S3_*` settings are **optional at boot**. The app starts without Garage; using storage when unconfigured raises `StorageNotConfigured`. | Does not break any existing dev flow or test. |
| D13 | One lifecycle rule installed by setup: **abort incomplete multipart uploads after 1 day**. | Abandoned pause/resume uploads must not leak disk. |
| D14 | Async client: **`aioboto3`**. | App and worker are async; presign is CPU-only but put/get are network. |

Stale-avatar note (decided, no work now): overwriting `avatars/{user_id}` keeps the key.
Presigned GET URLs change every time, so caches never stick today. If avatars ever become
public-read, append `?v=<updated_at>` to the URL.

---

## Phase 0 — Garage in compose

- [ ] `garage/garage.toml` (committed, **no secrets inside**):
      `replication_factor = 1`, `metadata_dir = /var/lib/garage/meta`,
      `data_dir = /var/lib/garage/data`, `db_engine = "lmdb"`,
      `rpc_bind_addr = "[::]:3901"`, `rpc_public_addr = "127.0.0.1:3901"`,
      `[s3_api] s3_region = "garage"`, `api_bind_addr = "[::]:3900"`, `root_domain = ".s3.garage.localhost"`,
      `[admin] api_bind_addr = "[::]:3903"`.
      Secrets (`GARAGE_RPC_SECRET`, `GARAGE_ADMIN_TOKEN`, `GARAGE_METRICS_TOKEN`) arrive via
      environment from `.env`. *Verify at implementation that the v2 image honours these env
      vars; fallback is `*_file` keys pointing at compose secrets.*
- [ ] `docker-compose.yml`: `garage` service — image `dxflrs/garage:v2.<pinned>`
      (pin the exact current tag; never `latest`), volumes `wasel_garage_meta`,
      `wasel_garage_data`, config mounted read-only, ports bound to **`127.0.0.1`** only
      (`3900` S3, `3903` admin), healthcheck `GET /health` on the admin port,
      `env_file: .env`.
- [ ] `app` and `worker`: `depends_on: garage (healthy)` and
      `extra_hosts: ["host.docker.internal:host-gateway"]` (needed on Linux for D11; harmless on OrbStack).
- [ ] `Dockerfile`: `COPY scripts ./scripts`.
- [ ] `.env.example` with compose hostnames (`DATABASE_URL=postgresql+psycopg://wasel:wasel@postgres:5432/wasel`,
      `REDIS_URL=redis://redis:6379/0`), the three Garage secrets (empty, with the `openssl rand`
      one-liner in a comment), and the `S3_*` block (empty key/secret until bootstrap).

**Exit:** `docker compose up -d` brings up `garage` healthy next to the existing services.

## Phase 1 — Bootstrap (once per environment)

- [ ] `scripts/garage_bootstrap.sh` — idempotent, runs from the host, drives the
      `garage` CLI inside the container:
      1. `garage status` → node id.
      2. `garage layout assign -z dc1 -c <capacity> <node>` + `garage layout apply`
         (skip if a layout is already applied).
      3. `garage bucket create wasel` (skip if exists).
      4. `garage key create wasel-app` (skip if exists; `key info --show-secret` to re-display).
      5. `garage bucket allow --read --write --owner wasel --key wasel-app`.
      6. Print the `S3_ACCESS_KEY=` / `S3_SECRET_KEY=` lines to paste into `.env`.
- [ ] `scripts/storage_setup.py` — runs in the `app` container **after** `.env` has the key:
      applies the lifecycle configuration from D13 via the S3 API (Garage's CLI has no
      lifecycle command). Idempotent.

**Exit:** `.env` holds working credentials; bucket `wasel` exists with the lifecycle rule.

## Phase 2 — Storage abstraction in the app

- [ ] `requirements.txt`: add pinned `aioboto3`.
- [ ] `app/config.py`:
      `s3_endpoint: str | None`, `s3_public_endpoint: str | None`,
      `s3_access_key: str | None`, `s3_secret_key: str | None`,
      `s3_bucket: str = "wasel"`, `s3_region: str = "garage"`,
      `s3_presign_ttl_seconds: int = 900`.
- [ ] `app/integrations/storage/` package:
      - `protocol.py` — `ObjectStorage` Protocol + dataclasses
        `ObjectInfo(key, size, etag, content_type, sha256?)`,
        `PresignedRequest(url, method, headers, expires_at)`, `PartInfo(part_number, size, etag)`.
        Errors: `StorageNotConfigured`, `ObjectNotFound`.
      - `s3.py` — `S3ObjectStorage`: **two** clients from one session — internal (D6
        `S3_ENDPOINT`) for data ops, public (`S3_PUBLIC_ENDPOINT`) used *only* to presign.
        Path-style addressing, region from settings, SigV4.
        Methods:
        `put(key, data, content_type, *, sha256=None) -> ObjectInfo`
        `get(key) -> (ObjectInfo, async byte stream)`
        `head(key) -> ObjectInfo | None`
        `delete(key)` (idempotent)
        `presign_put(key, *, content_type, content_length, sha256=None, ttl=None) -> PresignedRequest`
        `presign_get(key, *, ttl=None, download_name=None) -> str`
        `create_multipart(key, content_type) -> upload_id`
        `presign_part(key, upload_id, part_number, content_length, sha256=None) -> PresignedRequest`
        `list_parts(key, upload_id) -> list[PartInfo]`
        `complete_multipart(key, upload_id, parts) -> ObjectInfo`
        `abort_multipart(key, upload_id)`
      - `keys.py` — D4 builders: `avatar_key(user_id)`, `package_photo_key(package_id)`,
        `document_key(user_id, kind)`. The only module that knows the layout.
      - `fake.py` — `InMemoryObjectStorage` implementing the Protocol, for unit tests of
        future services.
      - `__init__.py` — `get_storage()` provider (lifespan-owned session, FastAPI dependency).
- [ ] Unit tests for `keys.py` and `fake.py`; `S3ObjectStorage` is covered by Phase 3
      against the real thing.

**Exit:** `pytest` green; app boots with and without `S3_*` set.

## Phase 3 — `scripts/_check_storage.py` (the proof)

Runs as `docker compose run --rm app python scripts/_check_storage.py`. Every step
asserts; prints one line per step. Uses a `check/<uuid>/…` prefix and cleans up.

1. `head` on a missing key → `None`.
2. `put` 1 KB with `content_type=image/png` → `head` returns size + content type; `get` streams identical bytes.
3. `presign_get` → fetch with `httpx` at the **public** host (D11 connect trick) → bytes match, `Content-Type` preserved.
4. `presign_put` with `content_length` + `content_type` → `httpx.put` → 200; `head` confirms.
5. **Wrong size** on the same presigned PUT → rejected (signature mismatch, 403).
6. `presign_put` with `sha256` → correct body accepted; **wrong body** → rejected.
   *If Garage ignores `x-amz-checksum-sha256`, fall back to `x-amz-content-sha256` as a
   signed header; if neither is enforced, record it and the Validation worker re-hashes
   (the diagram's Validation box) — hash then stays advisory at the store level.*
7. Multipart: `create` → `presign_part` ×3 (5 MiB each; S3 minimum part size) → upload parts
   1 and 2 → `list_parts` shows exactly 2 (**the pause/resume proof**) → upload part 3 →
   `complete` → `head` size = 15 MiB → `get` bytes match.
8. Multipart `abort` → `list_parts` raises / upload gone.
9. Lifecycle rule from D13 present (`GetBucketLifecycleConfiguration`).
10. `delete` → `head` → `None`; `delete` again → no error.

**Exit:** all 10 steps pass locally. This exact command is the post-deploy check on the server.

## Phase 4 — Server (separate session, outline only)

Same compose, plus: bind-mount `meta`/`data` to host dirs; Caddy vhost `s3.<domain>` →
`garage:3900` with TLS; `S3_PUBLIC_ENDPOINT=https://s3.<domain>`; bucket CORS rule for the
app's origins; `CHECK_PRESIGN_CONNECT_HOST` unset; nightly backup of both Garage dirs
(`replication_factor = 1` means the VPS disk is the only copy); run Phase 3 after deploy.

## Phase 5 — Endpoints (separate grilling)

`files` metadata (on the entity row vs. a `files` table), `/files/presigned-upload`,
`/files/{id}/complete` (HeadObject verify + procrastinate `defer()` in one transaction),
orphan sweeper, worker pipeline (validation → thumbnails → …), sha256 becomes required.

---

## Risks / things to verify during implementation

- **Garage v2 exact image tag and secret env-var names** — check the release page before pinning.
- **`x-amz-checksum-sha256` enforcement on presigned PUT** — unverified; step 6 decides, fallback documented there.
- **`Content-Length` as a signed header via `aioboto3.generate_presigned_url(ContentLength=…)`** — expected to land in `SignedHeaders`; step 5 proves it.
- **5 MiB minimum part size** applies to all parts but the last — the check uses ≥5 MiB parts deliberately.
- `host.docker.internal` requires `extra_hosts` on Linux; OrbStack provides it natively.
