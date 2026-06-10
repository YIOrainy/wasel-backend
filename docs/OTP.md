# OTP Authentication — Theoretical Foundation (A–Z)

> Scope: phone-number sign-in OTP (the "enter your mobile, get a 6-digit code, log in" flow),
> **not** the shipment delivery code. This is `phase: auth` for Wasel — foundation, not code to merge yet.

## 0. First, what kind of OTP are we even building?

There are three families. Pick deliberately — people conflate them:

| Type | How it works | Use case |
|---|---|---|
| **Random OTP** | Server generates a random code, stores it, sends via SMS, compares on submit. **Stateful** (server remembers it). | ✅ Phone sign-in (what you want) |
| **HOTP** (RFC 4226) | Counter-based, derived from a shared secret. | Hardware tokens |
| **TOTP** (RFC 6238) | Time-based, derived from a shared secret + current time. **Stateless** (Google Authenticator). | App-based 2FA |

For **SMS phone sign-in**, you want **random OTP**, because:
- The user has no shared secret / authenticator app — they only have their phone.
- You control delivery, so you can store the code server-side and just compare.

TOTP is for when both sides hold a secret. SMS sign-in is a server-generated random code. Don't overthink it into TOTP.

---

## 1. The core flow (two phases)

OTP sign-in is **two independent requests**, never one:

```
Phase A — REQUEST
  Client: "Here's my phone +9665…, send me a code"
  Server: generate code → hash+store → hand to SMS provider → return a challenge id
                                                              (NOT the code!)

Phase B — VERIFY
  Client: "For challenge id X, the code is 123456"
  Server: look up challenge → check expiry/attempts → hash input → compare
          → on match: issue session tokens, delete challenge
```

The key insight: **verification is a separate stateless-looking call** that references a stored challenge. The code itself never round-trips back to the client.

---

## 2. The layered architecture

Here's the layered breakdown you asked for. Each layer has one job and depends only on the layer below it.

```
┌─────────────────────────────────────────────────────────┐
│ 1. API / Presentation layer                              │
│    POST /auth/otp/request   POST /auth/otp/verify        │
│    - input validation (phone format E.164, code shape)   │
│    - rate-limit middleware                               │
│    - maps domain errors → HTTP codes                     │
├─────────────────────────────────────────────────────────┤
│ 2. Application / Service layer                            │
│    OtpService.request()  OtpService.verify()             │
│    - orchestrates the use case                           │
│    - enforces business rules (cooldown, max attempts)    │
│    - calls domain + infra, no framework code here        │
├─────────────────────────────────────────────────────────┤
│ 3. Domain layer                                          │
│    OtpChallenge entity, value objects (PhoneNumber, Code)│
│    - the rules: "expired?", "attempts left?", "matches?" │
│    - pure logic, no I/O                                  │
├─────────────────────────────────────────────────────────┤
│ 4. Infrastructure layer                                  │
│    - OtpRepository (Redis / Postgres)                    │
│    - SmsGateway (Twilio / Unifonic / local SA provider)  │
│    - Crypto (RNG, hashing)                               │
│    - TokenIssuer (JWT / session)                         │
└─────────────────────────────────────────────────────────┘
```

The win of this layering: you can swap the SMS provider (Twilio → Unifonic for Saudi), swap Redis → Postgres, or change "6 digits" → "4 digits" without touching the API layer or the rules. **This is exactly the same philosophy as Wasel's `src/mocks/api.ts` swap boundary** — the use case doesn't know what's behind it.

---

## 3. Layer 4 — Generation (the crypto layer)

### 3a. Generating the code

**Rule #1: use a cryptographically secure RNG.** Never `Math.random()` — it's predictable and an attacker who sees a few codes can forecast the next.

```
// Node — secure
import { randomInt } from "node:crypto";
const code = randomInt(0, 1_000_000).toString().padStart(6, "0");
//          ↑ CSPRNG, uniform 000000–999999
```

Why `padStart`: `randomInt` can return `42`, which must become `"000042"` — otherwise codes are non-uniform length and you leak entropy.

**Length tradeoff:**
- 4 digits = 10,000 combos → too brute-forceable, only OK with *aggressive* attempt limits.
- **6 digits = 1,000,000 combos → industry standard.** Use this.
- The strength comes from **length × attempt-limiting × expiry**, not length alone.

### 3b. Storing the code — HASH IT

**Rule #2: never store the OTP in plaintext.** If your DB/Redis leaks, plaintext codes = live account-takeover tokens for every pending login.

But here's the nuance specific to OTP:

> You do **not** need slow hashing (bcrypt/argon2) like you do for passwords.

Why? A 6-digit code has only 1M possibilities and **lives for ~5 minutes with a 3-5 attempt cap**. Its security comes from the short lifetime + attempt limit, not from hash slowness. So a fast hash is fine and avoids a CPU DoS vector (bcrypt on every verify is expensive). Use:

```
hash = HMAC-SHA256(code, server_pepper)
```

- HMAC with a server-side secret ("pepper") means even a leaked DB can't be brute-forced offline without also stealing the pepper.
- Add a per-challenge random salt if you want defense in depth.

Store the **hash**, compare hashes on verify. (Some teams use bcrypt anyway "to be safe" — acceptable, just know it's not strictly necessary and costs CPU.)

---

## 4. Layer 4 — The data model (storage)

What a stored challenge looks like:

```
OtpChallenge {
  id            uuid            // the "challenge id" returned to client
  phone         string (E.164)  // +9665XXXXXXXX
  codeHash      string          // HMAC-SHA256(code, pepper)
  purpose       enum            // 'sign_in' | 'sign_up' (scope the code!)
  expiresAt     timestamp       // now + 5 min
  attempts      int             // incremented on each wrong guess
  maxAttempts   int             // e.g. 5
  consumedAt    timestamp?      // set once verified — prevents replay
  createdAt     timestamp
}
```

**Where to store it: Redis vs Postgres.**

- **Redis (recommended):** OTPs are ephemeral. Set the key with a TTL = expiry, and it auto-deletes. Atomic `INCR` for attempt counting. This is the natural fit.
- **Postgres:** fine too, but you need a cron/sweeper to purge expired rows, and you do attempt counting in a transaction.

Either works — that's the point of the repository abstraction in layer 4.

---

## 5. Layer 4 — Delivery (the SMS gateway)

- Abstract behind a `SmsGateway` interface: `send(phone, message): Promise<void>`.
- For **Saudi Arabia specifically**: Twilio works but **Unifonic, Taqnyat, or Msegat** have better SA carrier deliverability and Arabic sender-ID support. Worth noting for Wasel.
- Delivery is **fire-and-forget-ish but must be awaited for errors** — if the provider rejects the number, you want to fail the request cleanly.
- **Never** put the code in the API response "for testing." That's the #1 OTP bug. Use a dev-only logger/flag instead.

---

## 6. Layer 2/3 — The REQUEST use case (with all the rules)

```
OtpService.request(phone, purpose):
  1. Validate & normalize phone → E.164  (domain: PhoneNumber value object)
  2. Anti-abuse checks (see §8):
       - per-phone cooldown: last code sent < 60s ago? → reject "too soon"
       - per-phone daily cap: > N codes today? → reject
       - per-IP cap
  3. Generate code (CSPRNG)            [infra: crypto]
  4. Build OtpChallenge, hash code     [domain + infra]
  5. Persist with TTL                  [infra: repo]
  6. Enqueue SMS                       [infra: gateway]
  7. Return { challengeId, expiresAt } — NEVER the code
```

**Critical anti-enumeration rule:** the response for "phone exists" vs "phone doesn't exist" must be **identical**. Otherwise attackers map which numbers have accounts. For sign-in-or-sign-up flows this is naturally solved because you create the user lazily on first verify.

---

## 7. Layer 2/3 — The VERIFY use case

```
OtpService.verify(challengeId, submittedCode):
  1. Load challenge by id              [infra: repo]
       - not found?         → fail (generic "invalid or expired")
  2. Domain rules (pure):
       - consumedAt set?    → fail (replay attempt)
       - now > expiresAt?   → fail
       - attempts >= max?   → fail (locked)
  3. Compare:
       hash(submittedCode) vs stored codeHash
       → use CONSTANT-TIME comparison (crypto.timingSafeEqual)
  4a. MATCH:
       - mark consumedAt (or delete the challenge)  ← single-use!
       - find-or-create user by phone
       - issue tokens (§9)
       - return session
  4b. NO MATCH:
       - atomically INCR attempts
       - if now at max → invalidate challenge
       - fail with generic error + attempts-remaining (optional)
```

Three non-negotiables hide in here:

1. **Single-use:** delete/consume on success. A code that works twice is a replay hole.
2. **Constant-time compare:** `if (hash === stored)` short-circuits and leaks timing. Use `timingSafeEqual`. (Less critical with hashes, but free to do right.)
3. **Generic errors:** "invalid or expired code" for *all* failure modes. Don't tell the attacker "expired" vs "wrong" vs "too many attempts" in a way that helps them — though showing attempts-remaining to the legit user is a UX/security tradeoff teams make differently.

---

## 8. The security layer (this is where OTP lives or dies)

OTP's whole threat model is **brute force** (1M codes isn't that many) and **abuse** (SMS costs money / spams users). Defense is layered:

| Threat | Defense |
|---|---|
| **Brute-forcing the code** | Max 3–5 attempts **per challenge**, then invalidate. 5 guesses / 1M = negligible odds. |
| **Brute force across many challenges** | Per-phone cap on *verify* attempts in a window, not just per-challenge. Otherwise attacker requests 1000 challenges and gets 5000 guesses. |
| **SMS bombing / cost abuse** | Per-phone **cooldown** (60s between sends) + **daily cap** + per-IP cap. |
| **Replay** | Single-use + `consumedAt`. |
| **Predictable codes** | CSPRNG only. |
| **DB leak** | Hash + pepper. |
| **Enumeration** | Identical responses regardless of account existence. |
| **Interception (SIM swap, SS7)** | Out of your control, but: short expiry, device binding, anomaly detection. This is *the* known weakness of SMS OTP — it's "something you receive," not "something you have." |
| **Phishing relay** | Bind the challenge to context; consider not making codes copy-pasteable across sessions. |

**Rate limiting is itself layered:** per-challenge (attempts) → per-phone (sends + verifies) → per-IP → global. A token-bucket or sliding-window counter in Redis handles all of these.

---

## 9. After verification — issuing the session (the "now you're logged in" layer)

Verifying the OTP is **authentication**; you still need to establish a **session**. Standard pattern:

```
On successful verify:
  - access token  (JWT, short-lived ~15 min, stateless, holds userId/role)
  - refresh token (opaque, long-lived ~30–90 days, stored server-side, rotatable)
```

- **Access token (JWT):** signed, contains claims (`sub: userId`, `role: sender|captain`), self-verifying, short TTL so a leak is time-boxed.
- **Refresh token:** random opaque string, stored hashed in DB, used to mint new access tokens without re-OTP. **Rotate on every use** (issue new, revoke old) so a stolen refresh token is detectable.
- On mobile (Wasel = Expo), store tokens in **secure storage** (`expo-secure-store` / Keychain / Keystore) — **never** AsyncStorage/MMKV-plaintext for tokens. (Note: your CLAUDE.md says MMKV for app state, but auth tokens specifically should go in secure-store when `phase: auth` lands.)

For Wasel's two personas: the OTP flow is identical; the `role` is decided at **sign-up** (or a role-select screen) and baked into the token claims, not into the OTP itself.

---

## 10. End-to-end sequence (putting it together)

```
┌────────┐                ┌─────────┐         ┌────────┐      ┌─────┐
│ Client │                │   API   │         │  Redis │      │ SMS │
└───┬────┘                └────┬────┘         └───┬────┘      └──┬──┘
    │ POST /otp/request {phone}│                  │              │
    │─────────────────────────>│                  │              │
    │                          │ cooldown check   │              │
    │                          │─────────────────>│              │
    │                          │ gen code (CSPRNG)│              │
    │                          │ store hash + TTL │              │
    │                          │─────────────────>│              │
    │                          │ send code        │              │
    │                          │─────────────────────────────────>│
    │   { challengeId, expiresAt }                 │           sms│──> 📱
    │<─────────────────────────│                  │              │
    │                          │                  │              │
    │ POST /otp/verify {id, code}                  │              │
    │─────────────────────────>│ load challenge   │              │
    │                          │─────────────────>│              │
    │                          │ check exp/attempts/consumed      │
    │                          │ constant-time hash compare       │
    │                          │ consume + find-or-create user    │
    │                          │ issue JWT + refresh              │
    │  { accessToken, refreshToken, user }         │              │
    │<─────────────────────────│                  │              │
```

---

## 11. The minimum checklist (your A–Z TL;DR)

- [ ] 6-digit code from a **CSPRNG**, zero-padded
- [ ] **Hash** before storing (HMAC-SHA256 + pepper), never plaintext
- [ ] Store as a **challenge** with `expiresAt` (~5 min), `attempts`, `maxAttempts`, `purpose`, `consumedAt`
- [ ] **TTL-based storage** (Redis) so codes self-expire
- [ ] Return a **challengeId**, never the code
- [ ] **Cooldown** (60s) + **daily cap** + **per-IP** limits on request
- [ ] **Max 3–5 attempts** per challenge, plus per-phone verify cap
- [ ] **Constant-time** comparison
- [ ] **Single-use**: consume/delete on success
- [ ] **Generic errors**, no enumeration
- [ ] On success: **find-or-create user → JWT (short) + refresh (rotating)**
- [ ] Tokens in **secure storage** on device
- [ ] SMS behind a **swappable gateway** (Unifonic/Taqnyat for SA)

---

Want me to go a level deeper on any one layer? The usual follow-ups are: **(a)** concrete Redis key schema + rate-limit algorithm, **(b)** the JWT/refresh-token rotation mechanics in detail, or **(c)** how this wires into Wasel's Expo client + the two-persona role model.

> Note: this is purely theoretical — `auth` is a deferred phase in Wasel, so nothing here touches the repo yet.
