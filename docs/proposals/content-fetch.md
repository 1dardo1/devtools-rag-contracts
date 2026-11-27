# Proposal: how the retrieval service reads a document's content (inventory gap 4.1)

- **Status:** Proposed. Nothing here is decided. The recommendation in section
  "Recommendation" is for Carlos to accept, change or reject.
- **Scope:** the first gap named in `docs/EVENT-INVENTORY.md` §4.1: the retrieval
  service is told to fetch a document's bytes by `document_id`, and nothing can
  serve them. This proposal compares the ways to close it and recommends one. It
  does not cover gap 4.2 (indexing reported back), which needs its own proposal.
- **Nothing here is code, and nothing changes a schema.** If the recommendation is
  approved, the decisions marked *ADR* become one record in `docs/adr/` (the next
  number), and the implementation becomes pull requests in the repositories named
  under "Consumers affected". Those need their own proposals under
  `COLLABORATION.md` §3, because they touch ingestion's ports and API.
- **Evidence.** Every claim about the current system names the file or ADR it comes
  from. Where something is a guess or an inference, it says so. Ingestion ADR
  numbers are ingestion's. The snapshots in this repository date from 2026-10-28,
  so later ingestion work (ADRs 0026 to 0030) is cited from ingestion's
  `CLAUDE.md` and `docs/proposals/relay-internals.md`, which are not copied here.

## What is being decided

`DocumentIngested` announces a document and deliberately leaves out its bytes:
pushing up to 5 MiB per document through the broker "would make Redis Streams a
content store" (`EVENT-INVENTORY.md` §1.5, contracts ADR 0004). The event's
docstring says a consumer "fetches the bytes by `document_id`". Today that is not
possible: `GET /documents/{document_id}` returns `document_id`, `collection_id`,
`status` and `ingested_at` and no content (`INGESTION-AT-A-GLANCE.md` §3.1, ingestion
ADR 0015). The only copy of the bytes is `documents.content`, a `bytea` column in
ingestion's PostgreSQL (`INGESTION-AT-A-GLANCE.md` §4, ingestion ADR 0012).

Phase 9 ("the deployed ingestion service emits an event that this service consumes
and indexes", `ARCHITECTURE.md` §5) cannot be met until some path carries the bytes
from that column to the retrieval service. The question is which path, and it is a
boundary between two services, so it is an ADR trigger (`COLLABORATION.md` §8).

## The constraints any answer has to meet

Each one is a fact about the system today, with its source.

1. **The bytes live in one PostgreSQL column, written in the document's
   transaction.** Ingestion ADR 0012 rejected object storage because it "introduces
   a second system that the transaction cannot span, which is the exact failure the
   outbox exists to prevent".
2. **Content is at most 5 MiB decoded** (`max_document_size_in_bytes`,
   `INGESTION-AT-A-GLANCE.md` §2.3, §3.3). The 7 MiB cap is on the request body
   only, because base64 expands content by a third.
3. **Delivery is at-least-once, unordered and arbitrarily late**
   (`EVENT-INVENTORY.md` §2, contracts ADR 0003). Whatever fetches the content may
   run twice for one document, and long after the event was written.
4. **The ingestion API is unauthenticated until Phase 13**, writes included, and is
   bounded only by Neon's 0.5 GB (`INGESTION-AT-A-GLANCE.md` §5.3, ingestion ADR
   0025).
5. **Both hosts sleep.** Render's free web service sleeps after 15 idle minutes and
   takes "up to about a minute" to wake. Neon suspends after 5 minutes
   (`INGESTION-AT-A-GLANCE.md` §5.3). A keep-alive pinger was rejected in ingestion
   ADR 0025 because it would hide the cost, so cold starts are a design input, not
   a bug to be removed.
6. **The relay runs as a scheduled command, not inside the API** (ingestion ADR
   0027, per ingestion's `CLAUDE.md`). Inference, not a documented fact: the relay
   talks to PostgreSQL and Redis, never to the API, so publishing an event does not
   wake Render.
7. **A committed document always has its outbox row and an event exists only for a
   committed document** (contracts ADR 0003). So a consumer never meets an event
   whose document is not yet visible to a reader of the same database.
8. **Nothing deletes documents or collections** (`INGESTION-AT-A-GLANCE.md` §4: no
   `ON DELETE`, nothing deletes). So "the document is gone" is not a state the
   current system produces.
9. **Event schemas live only here** (principle 6) and **this repository holds no
   infrastructure clients and no service API** (`CLAUDE.md`, "What this repository
   is NOT"). The ingestion HTTP API belongs to ingestion (ingestion ADR 0015).
10. **The relay stays a dumb pipe**: it copies a row's payload and does not shape
    it (ingestion ADR 0014, contracts ADR 0007 §2). Anything the event must carry
    has to be written into the payload by ingestion, in the document's transaction.

## Options

### A. A read endpoint on ingestion's HTTP API

`GET /documents/{document_id}/content` returns the stored bytes. Retrieval builds
the URL from a configured base URL and the event's `document_id`, fetches, and
checks the SHA-256 of what it received against the event's `content_hash`.

- **Meets:** constraint 1 (the bytes stay where the transaction is), 7 (the
  document is committed before the event exists), 3 (a `GET` is safe to repeat).
- **Ingestion** gains a route, a use case and a read on the document repository.
  That is a change to a port, which `COLLABORATION.md` §4 reserves for Carlos.
- **Retrieval** gains an HTTP client and the failure handling below.
- **Contracts:** no schema change and no release. An ADR records the decision.
- **Authentication:** none today, like every other route (constraint 4). See
  decision 3.
- **Failure mode, ingestion asleep:** the request is slow or fails while Render
  wakes (up to about a minute, constraint 5). The consumer must wait or retry, and
  must not acknowledge the event until the document is indexed. Nothing is lost
  while the stream still holds the entry.
- **Failure mode, document gone:** `404 document_not_found`, the existing refusal
  (`INGESTION-AT-A-GLANCE.md` §3.2). Today this should not happen (constraint 8);
  it can happen if an event from one environment is read against another.

### B. The content inside the event

The payload carries the bytes (base64 in JSON, since the payload is `jsonb`).

- **Rejected by `CLAUDE.md` and `EVENT-INVENTORY.md` §1.5**, and the reasons hold
  up when measured against the rest of the system:
  - The stream stops being an announcement log and becomes a content store
    (contracts ADR 0004, "the broker carries announcements, never content").
  - The stream is bounded by count, not size: ingestion's relay proposal sets
    `MAXLEN ~ 100000` on Upstash's free plan of 256 MB, sized at a *guessed* 1 KB
    per event. With content, one event can be 6.7 MiB of base64, so that count
    could hold hundreds of gigabytes. The bound would have to be redone around
    bytes, and silent loss at the bound would then lose content, not just a notice.
  - The outbox payload would duplicate `documents.content` inside the same Neon
    database, which is capped at 0.5 GB.
  - The relay copies a row's payload unshaped (constraint 10), so every outbox
    read and every `XADD` moves megabytes.
- **Meets:** the best failure mode of any option. Retrieval needs nothing from
  ingestion after the event, so a sleeping ingestion does not matter.
- **Contracts:** adding an optional field with a default is a *compatible* change
  (ADR 0007), a minor release under ADR 0008. It would still be a schema change
  that needs Carlos's approval (`COLLABORATION.md` §4).
- **Variant considered, content inline only below a size:** two code paths in the
  consumer for the sake of the common case, and a threshold that is a guess.
  Rejected on that ground alone.

### C. A shared object store

Ingestion writes the bytes to an object store (S3, Cloudflare R2 or similar) and
retrieval reads them there.

- **Rejected by ingestion ADR 0012**, for a reason that still applies: the
  document row and the object are two writes to two systems, and a crash between
  them leaves a row with no object or an object with no row. That ADR said it was
  worth revisiting "only if documents stop being documentation pages". They have not.
- **Also:** a new hosted dependency and a credential in both services (a secret in
  each, `COLLABORATION.md` §4 on configuration), a second free tier with its own
  limits (unresearched, a guess that they exist), and a change to ingestion's
  storage adapter and a migration, for a corpus whose documents are at most 5 MiB.
- **Meets:** a good failure mode (the store is always awake, nothing wakes up) and
  no unauthenticated API read. But the price is a hole in the one invariant the
  service says matters most (ingestion's `CLAUDE.md`: the document and its outbox
  row are written in the same transaction).
- **Contracts:** the event would need to name the object (a key), an optional
  field, so a minor release.

### D. Retrieval reads ingestion's database directly

Retrieval connects to Neon with a read-only role and selects `content` from
`documents`.

- **Rejected on coupling.** The `documents` table is ingestion's private storage
  and ADR 0012 treats it that way (its constraints defend against "a row [that] is written by something that is
  not this application"). Reading it makes
  every ingestion migration a breaking change to a contract nobody wrote down, and
  contradicts the point of the split: independent deployment (contracts ADR 0002).
  A shared database between two services is the integration-database anti-pattern.
- **Variant, a SQL view as the published interface:** it names the contract but the
  two services still share a database, a credential and a migration schedule.
  Rejected for the same reason.
- **Also:** retrieval would need a PostgreSQL driver, which `CLAUDE.md` keeps out of
  this package, and a second credential for Neon.
- **Meets:** no new endpoint, no Render wake (only Neon). It is the cheapest thing
  to build and the most expensive to live with.
- **Contracts:** nothing changes, which is the problem: the real contract is
  invisible.

### E. A content URL or token in the event

The event carries a URL, or a signed token that authorises one fetch.

- **A plain URL.** Rejected: it is option A with the host baked into every event.
  Events outlive deployments, since outbox rows are kept and published late (contracts
  ADR 0008), and ingestion ADR 0025 reopens the platform question for the relay, with
  Fly.io possibly winning it. A stored host could end up pointing at a deployment
  that has moved (a guess, but a cheap one to avoid). It also makes the consumer fetch whatever
  URL an event names, so an event forged on the stream becomes a request to an
  address of the forger's choosing (a server-side request forgery risk, inferred
  here, not tested). Building the URL from configuration and `document_id` is safer.
- **A signed, expiring token.** It would remove the authentication gap without
  waiting for Phase 13, but: tokens must be minted when the row is written, since
  the relay does not shape payloads (constraint 10), so they would expire before an
  event delayed by an outage is read (constraint 3); ingestion would need a signing
  secret and a clock for expiry; and `jsonb` normalises key order, which matters the
  moment a payload is signed (ingestion ADR 0014). A re-issue endpoint would be
  needed as well, which is option A with more parts. Rejected.
- **Contracts:** an optional field, so a minor release, and an unusual one:
  a secret on the wire.

### Comparison

| | Bytes travel through | Schema change | Contracts release | Repositories touched | Ingestion asleep | Document gone |
|---|---|---|---|---|---|---|
| **A. Read endpoint** | HTTP, ingestion to retrieval | None | None (an ADR only) | ingestion, retrieval | Slow or failed fetch, retry, entry stays pending | `404`, permanent |
| **B. In the event** | Redis | Optional field | Minor | ingestion, retrieval, contracts | No effect | Not applicable |
| **C. Object store** | The store | Optional field (a key) | Minor | all three, plus a new service | No effect | Object missing, an unspecified error from the store |
| **D. Direct database read** | PostgreSQL | None | None | ingestion (as a constraint it never agreed to), retrieval | Neon wake only | No row |
| **E. URL or token** | HTTP, as A | Optional field | Minor | all three | As A | As A |

## Recommendation (for Carlos to decide)

**Option A, with the three sub-decisions below.** It is the only option that adds no
second system (against C), no second copy of the bytes (against B), no hidden
contract (against D) and no secret on the wire (against E). Its cost is a runtime
dependency of retrieval on ingestion being awake, and the design accepts that cost
on purpose: it is the same coupling that "why events and not a direct HTTP call"
(`ARCHITECTURE.md` §2) removes from the *write* path, moved to a *read* path that
can wait. **If Carlos prefers a different option, B is the strongest alternative if
the corpus is ever shown to be small, and C if documents stop being documentation.**
That is a judgement, not a measurement.

## Decisions

### 1. The endpoint returns the raw bytes, not JSON (ADR)

`GET /documents/{document_id}/content` answers `200` with the stored bytes as the
body and `Content-Type: application/octet-stream`. The path parameter is a `UUID`,
like the existing route, so a malformed id is the existing `422 invalid_request`.

**Why:** at the 5 MiB limit the body is 5 MiB, not about 6.7 MiB of base64
(ingestion ADR 0015 records that cost on the way in). There is no JSON response
model to define, so there is nothing to put in this repository, which matters
because it holds no HTTP API (`CLAUDE.md`). And the SHA-256 of the body is directly
comparable to the event's `content_hash`, which is the SHA-256 of the decoded bytes
(`EVENT-INVENTORY.md` §1.2).

**Rejected: a JSON body with the content in base64**, symmetric with the `POST`.
Symmetry is its one advantage. Against it: a third more bytes, a response model that
would have to live in ingestion or here, and a decode step in the consumer.

**Rejected: also returning metadata.** The event already carries it
(`EVENT-INVENTORY.md` §1.2), and two sources for the same fact can disagree.

**A limitation to know:** ingestion stores no media type or encoding
(`INGESTION-AT-A-GLANCE.md` §4), so `application/octet-stream` is the only honest
type, and retrieval has to know how to interpret the bytes. That is the chunking
adapter's concern in Phase 9, and it may turn out to be a gap of its own.

### 2. The status does not gate the read, and the bytes are immutable (ADR)

Any stored document's content is readable whatever its `status`. A document is
never updated after it is stored (a failed one is resubmitted as a new document,
`INGESTION-AT-A-GLANCE.md` §2.2), so two reads of one `document_id` return the same
bytes. That is what makes repeating the fetch under at-least-once delivery safe.

**Rejected: serving content only while the status is `pending`.** It would couple
the read to gap 4.2: the day something moves a document to `processing`, a retry
would start returning an error.

An unknown `document_id` answers `404` with `{"code": "document_not_found", ...}`,
the shape ingestion already uses (`INGESTION-AT-A-GLANCE.md` §3.2). No new code.

### 3. No authentication now, recorded as a known cost (needs approval)

The route is as open as the rest of the API: anyone who knows a `document_id` can
read the document. `document_id` is a random UUID minted by ingestion, never
chosen by a client (`INGESTION-AT-A-GLANCE.md` §2.1), and the corpus is public
developer documentation (`ARCHITECTURE.md` §1.1). But anyone may also submit
anything, so the endpoint is only as private as what strangers choose to upload,
and it offers anyone a way to spend bandwidth on a free plan (limits unresearched).

**Rejected: a shared secret header now.** It adds a secret to two services
(`COLLABORATION.md` §4: configuration and secrets), protects only the read while
the write stays open, and is replaced wholesale by Phase 13's hardening. It would
also be the first credential of a new shape, which ingestion ADR 0022 and ADR 0025
say is when the secret scanner must be revisited.

**The cost to record:** a second public, unauthenticated route, until Phase 13.

### 4. What retrieval is asked to do with the failures (a recommendation to Phase 9)

These are not decisions made here. They are what the failure modes imply, written
down so that Phase 9 does not discover them late. Retry and error handling is
retrieval's to decide (`COLLABORATION.md` §4).

| Situation | Recommended handling |
|---|---|
| Timeout, connection failure, or a `5xx` (ingestion or Neon waking) | Retry with backoff. The first request after an idle period can take close to a minute (constraint 5), so a fixed short timeout would fail by design. The value is a guess to be measured |
| `404 document_not_found` | Permanent. Do not retry for ever: acknowledge it and log it with the `document_id`. Contracts ADR 0004 notes the broker brings no dead-letter handling, so where a poisoned event goes is retrieval's own decision |
| The body's SHA-256 differs from the event's `content_hash` | An error, not a retry target. The bytes are not the ones announced |
| The event is redelivered | Check whether the `document_id` is already indexed before fetching again (principle 7) |
| The event is never read | If retrieval is down for longer than the stream holds, the entry is dropped by the `MAXLEN` bound (ingestion's relay proposal). The document then stays `pending` in ingestion with no event. Recovering it needs something that re-announces, which no one owns yet and which interacts with gap 4.2 |

Do not acknowledge the stream entry until the document is indexed. That is what
turns a slow fetch into a retry and not into a loss.

## What this does NOT include

- **Any implementation.** The route, the use case, the repository read and the
  consumer's client are separate proposals in ingestion and retrieval. The first
  one changes a port (`DocumentRepository`, or a new one beside it), which needs
  approval (`COLLABORATION.md` §4).
- **A change to `DocumentIngested`.** The event keeps its five fields and
  `schema_version` 1. **No contracts release follows from option A.**
- **Gap 4.2**, indexing reported back, and any way to re-announce a lost event.
- **Caching** of fetched content, on either side. `COLLABORATION.md` §4 names it as a
  decision of its own.
- **Streaming or range requests.** A single 5 MiB body is read into memory by an
  endpoint that holds one connection per request (ingestion ADR 0017). Fine at this
  size; a guess to measure if the limit ever rises.
- **Authentication and rate limiting**, which are Phase 13.
- **A health endpoint** for ingestion, which would help retrieval tell "asleep" from
  "broken". It is an API change in ingestion's own open decisions
  (`INGESTION-AT-A-GLANCE.md` §6).
- **Mitigating cold starts.** The keep-alive pinger was rejected in ingestion ADR
  0025 and stays rejected here.

## Consumers affected

| Repository | Under option A |
|---|---|
| `devtools-rag-ingestion` | A new read route, a use case, a read on the repository port, tests, an update to its README and the guard that holds routes against it (ingestion ADR 0023). Its snapshots in this repository (`INGESTION-AT-A-GLANCE.md` §3.1 and the "No endpoint returns content" line, `EVENT-INVENTORY.md` §4.1) become stale and are corrected in that pull request |
| `devtools-rag-retrieval` | An HTTP client for the route, the failure handling above, a configured base URL for ingestion (a new environment variable), and the SHA-256 check. Its repository exists but is empty (`CLAUDE.md`), so this is design input for Phase 8 and 9, not a change to anything built |
| `devtools-rag-contracts` | One ADR. No schema, no release, no tag, and ingestion does not move its pin |

Under B, C or E all three repositories change and contracts cuts a minor release
under ADR 0008 (compatible, so no consumer-first roll-out is required). Under D
only the first two change, and contracts is untouched.

## Why this way (teaching notes)

- **This is a "claim check", or in the Enterprise Integration Patterns catalogue,
  the Claim Check pattern.** The event is the ticket stub and the bytes stay in the
  vault. Look up "claim check pattern" (Hohpe and Woolf). Options B and E are the
  other two ways to hand over the goods: with the message, or with a pre-authorised
  link.
- **C# and Java analogy for option D:** two services that read each other's tables
  are two applications sharing one `DbContext` or one JPA persistence unit. Renaming
  a column breaks a deployment that was never in the pull request. The cost is
  invisible until it is paid, which is why contracts exists as a repository.
- **C# and Java analogy for the endpoint:** it is a read-only query side. In a CQRS
  vocabulary the outbox event is the command's notification and `GET .../content` is
  a query against the write side's store. A consumer calling the producer's query
  endpoint is ordinary in .NET and Jakarta EE services, and it is what a typed
  `HttpClient` or a Spring `RestClient` does.
- **What this choice makes easy:** nothing about the event, the broker or the
  outbox moves, and the bytes stay under the one transaction that the architecture
  protects. **What it makes hard:** retrieval can now be blocked by ingestion's
  sleep, and the repository has two kinds of boundary to keep in step, a message
  schema here and an HTTP route in ingestion, with only one of them versioned.
- **The honest cost of option A is a guard that does not exist.** Principle 6 holds
  event schemas in one place. Nothing equivalent holds this route's behaviour:
  that the bytes hash to `content_hash`. The recommendation relies on a test in
  ingestion asserting exactly that, and on retrieval's own check at runtime.
- **Safe and idempotent are different words.** A `GET` that changes nothing can be
  repeated by any redelivery. That is why the endpoint must not change the document's
  status, which is decision 2.

## Questions for the reviewer

1. **Accept option A** (a read endpoint on ingestion), or prefer B, C, D or E? If B,
   what is the smallest corpus size at which you would accept it? If C, are you
   willing to give up the single-transaction invariant?
2. **Raw bytes or JSON with base64** for the response (decision 1)?
3. **Open read now, authentication at Phase 13** (decision 3), or a shared secret
   now despite the cost named there?
4. **Where does the route's contract live?** `CLAUDE.md` says ingestion's HTTP API
   is ingestion's, but this route exists only for the other service. The proposal
   keeps it in an ADR here and the OpenAPI in ingestion, with no constant or model
   in `rag_contracts`. The alternative is a constant for the path beside
   `STREAM_NAME` and `EVENT_TYPE` (ADR 0007), at the price of a half-contract.
5. **Is retrieval's behaviour on failure (decision 4) yours to approve now, or at
   Phase 9?** The proposal treats it as a recommendation to Phase 9.
