# Proposal: reporting indexing back to ingestion (inventory gap 4.2)

- **Status:** Proposed. Nothing here is approved.
- **Scope:** how ingestion could learn that a document was indexed or failed, so
  that its `status` can leave `pending`. It compares four ways and recommends one.
  It decides the *mechanism* and leaves the event's *shape* for later, for the
  reason in §What is being decided.
- **Nothing here is code, an ADR or a schema.** If a decision is approved, the
  records named in §ADR triggers are written next, each in its own pull request.
- **How to read the citations.** "Contracts ADR n" is this repository's, "ingestion
  ADR n" is `devtools-rag-ingestion`'s. A claim about ingestion's code was read on
  its `main` (commit `1fea700`, 2026-11-26) and names the file. A claim marked
  **guess** is mine and unverified.

## The problem, as the system states it today

- Ingestion's `Document` has the state machine `pending → processing → indexed |
  failed`, with `indexed` and `failed` terminal (`docs/INGESTION-AT-A-GLANCE.md`
  §2.2, `domain/document.py`). **Nothing calls `start_processing()`,
  `mark_indexed()` or `mark_failed()`**, so every stored document is `pending`
  (same section; `docs/EVENT-INVENTORY.md` §4.2).
- `GET /documents/{id}` returns `status` (`docs/INGESTION-AT-A-GLANCE.md` §3.1),
  and `POST …/documents` answers `202`, "recorded, not finished" (ingestion ADR
  0015). The `202` promises a status that can move, and it cannot.
- Events flow one way. Contracts ADR 0003 says so as a negative consequence and
  says closing it "would make ingestion a consumer too, and is not decided".
- Two more facts shape every option. **`failed` is not only a label:** the
  deduplication index excludes failed documents, so marking one failed makes its
  content resubmittable (ingestion ADR 0012). And **the domain's `mark_failed()`
  takes no reason** (`domain/document.py`), and the `documents` table has no column
  for one (ingestion ADR 0012), so a failure reason has nowhere to land today.

## What is being decided

**A way to carry one fact from retrieval to ingestion: "document X is now indexed"
or "document X could not be indexed".**

Only the mechanism is decided here. **The event's fields are not**, because
`CLAUDE.md` forbids inventing a shape ahead of the domain that produces it: the
facts that go in a `DocumentIndexed` belong to retrieval's `IndexDocument` use case
(`ARCHITECTURE.md` §5 Phase 8), and that repository is empty. The one field the
mechanism itself forces is the document's identity, `document_id`, because
`docs/EVENT-INVENTORY.md` §1.5 says one event per document is identified by it. Any
other field, including a failure reason, waits for Phase 8 and for ingestion to
say whether it can store one.

## Options

### A. Retrieval publishes `DocumentIndexed` and `DocumentIndexingFailed`; ingestion consumes them (recommended)

Retrieval writes a result event to a **second Redis stream**. A new ingestion
process reads it through a consumer group and applies the transition.

- **Repositories affected:** all three. Contracts: two new event classes.
  Retrieval: a publisher. Ingestion: a consumer, an application use case, and a
  new method on `DocumentRepository`.
- **New event types:** two. **Schema change:** none to `DocumentIngested`.
- **What ADR 0008 requires:** a new event is a **minor** release (its table). No
  existing schema changes, so the consumers-first rollout does not apply. ADR 0007
  puts `schema_version` inside each payload, so I assume (**guess**) each new
  event carries its own, starting at 1. Under the `0.y.z` allowance (ADR 0008) a
  minor could also be breaking, and this one is not.

**Where ingestion's consumer runs.** Ingestion has no always-on process. Ingestion
ADR 0027 put the relay in a scheduled GitHub Actions workflow running `--once`
every 5 minutes, because Render's free plan has no background worker and the web
service sleeps after 15 idle minutes. The consumer meets the same constraints:

1. **A `--once` command in a scheduled workflow, same schedule family as the
   relay.** Recommended. It is free, it is a separate process from the API as
   ingestion `CLAUDE.md` requires, and it needs one more secret-bearing job on the
   existing pattern. Whether it is a second workflow or a second step after the
   relay in the same one is open (**guess**: a second step halves the scheduling
   risk, and couples the two failures).
2. **Inside the web service.** Rejected: it sleeps, and it would share the API's
   lifecycle (ingestion ADR 0027; ingestion `CLAUDE.md`).
3. **An always-on worker.** Rejected only by the no-payment constraint (about 7 USD
   a month, ingestion ADR 0027). It remains the clean way out if that constraint
   relaxes, and `--loop` makes the move a change of host.

**Cost of that choice, stated plainly:** a document's status lags by the relay's
schedule (up to 5 minutes), plus retrieval's indexing time, plus the consumer's
schedule (up to 5 minutes). The status is always late, never live. Command budget
(**guess, arithmetic only**): 288 runs a day is about 8,640 a month; at two or
three Redis commands per idle run that is roughly 17,000 to 26,000 of Upstash's
500,000 monthly commands, on top of the relay's. Ingestion ADR 0027 itself says the
Upstash free plan's persistence and its stream-command accounting are **not yet
verified**; this option inherits that unknown.

**The handler.** It is a new inbound adapter driving a new use case (name is a
**guess**: `RecordIndexingResult`), in the same hexagonal shape as the API.
`DocumentRepository` has no way to save a changed document today: its methods are
`add`, `get`, `exists_with_content_hash` and `count_in_collection`
(`domain/ports.py`). A port change needs approval (`COLLABORATION.md` §4), and no
migration is needed for the status itself, since the column and its `CHECK`
already exist (ingestion ADR 0012).

**Failure modes:**

| Failure | What happens | Why it is acceptable, or not |
|---|---|---|
| **Event lost** (retrieval crashes between indexing and publishing) | Retrieval does not acknowledge the `DocumentIngested` entry until the result is published, so the entry is redelivered, indexing runs again and publishes again. | Relies on retrieval's idempotent indexing (`ARCHITECTURE.md` §4 principle 7). Cost: re-chunking and re-embedding, which may cost money (**guess**). **Retrieval has no database** (`ARCHITECTURE.md` §3: PostgreSQL is "ingestion only"), so it **cannot use a transactional outbox**; this ack-after-publish rule is the substitute, and it is weaker. |
| **Event lost** (trimmed from the stream before ingestion reads it) | The status stays `pending`. | Ingestion's own stream is bounded by an approximate count (ingestion ADR 0029); the reverse stream would need the same. After this proposal `pending` means "no report received", not "not indexed". It is a stale value, never a wrong one. |
| **Duplicate** | The handler finds the document already in the target status and does nothing. | Idempotent by status. Needs a test per event type. |
| **Out of order, same event type** | Two events of one type for one document are duplicates, handled by the row above. | Nothing else can reorder them. |
| **Out of order, conflicting** (`Failed`, then `Indexed` after a redelivery that succeeds) | The state machine refuses it: `failed` is terminal (`IllegalStatusTransitionError`). The handler must choose: ignore and log, or fail. | **Not decided here**; see question 4. The opposite order is refused the same way. |
| **No global ordering** | Not a problem between documents, since each affects only its own row. Within one document, only the conflicting case above matters. | Ingestion ADR 0012 and contracts ADR 0003 still apply. A consumer must not assume an order. |
| **Ingestion down** | Entries wait in Redis. | This is the property the architecture bought (`ARCHITECTURE.md` §2). |

**The `processing` status.** The state machine requires `pending → processing`
before `indexed`. Two ways to honour that without a third event:

- The handler calls `start_processing()` then `mark_indexed()` inside one
  transaction. **No domain change.** `processing` then exists in the state machine
  and is never observable from outside.
- Retrieval publishes a `DocumentIndexingStarted` event. Rejected here: a third
  event, more stream traffic on a free command budget, and no consumer needs the
  intermediate state (**guess**: the only reader of `status` is `GET /documents/{id}`).

**ADR triggers (`COLLABORATION.md` §8):** defining an event contract and changing a
boundary between services. See §ADR triggers.

### B. Retrieval calls an ingestion HTTP endpoint to set the status

A new write endpoint on ingestion, for example a status transition on a document.
(Path and verb are not proposed.)

- **Repositories affected:** ingestion (endpoint, use case, port change) and
  retrieval (an HTTP client). **Contracts: none**, and that is a problem of its own.
- **New event type:** none. **Schema change:** none here.
- **What ADR 0008 requires:** nothing, because it governs events. `CLAUDE.md` says
  the HTTP API belongs to ingestion (ingestion ADR 0015), so this request would
  have **no versioning or compatibility policy at all**. Two services would share
  an unversioned interface, which principle 6 exists to prevent for events.

Rejected, for these reasons, in order of weight:

1. **The API is public and unauthenticated** until Phase 13 (ingestion ADR 0025).
   A write endpoint that moves status would let anyone mark any document `failed`,
   which makes its content resubmittable (ingestion ADR 0012), or `indexed`, which
   makes the status lie. Fixing it needs a credential, which is configuration and
   secrets (`COLLABORATION.md` §4), and pulls Phase 13 forward.
2. **It reintroduces the coupling the architecture rejected.** `ARCHITECTURE.md` §2
   rejects a direct call because "if the indexer is down, ingestion fails". The
   mirror is "if ingestion is down, the report fails". Ingestion's web service
   sleeps after 15 idle minutes and Neon after 5 (ingestion ADR 0025), so a cold
   service is the normal case, not the exception. Retrieval would need retries.
3. **Retrieval has no durable place to keep an unsent report**, for the reason in
   option A's first row. The only substitute is to withhold the acknowledgement
   until ingestion answers, which ties re-indexing cost to ingestion's uptime. Over
   Redis the report is much more likely to succeed.
4. **No rule forbids it, and that is why it is rejected on merit.** Contracts ADR
   0003 and ingestion `CLAUDE.md` forbid *ingestion* calling retrieval. Nothing I
   read forbids the inverse, so points 1 to 3 carry the rejection, not a rule.

**Interaction with gap 4.1.** If the content-fetch gap is closed with an ingestion
endpoint that retrieval calls, retrieval already depends on ingestion's HTTP API,
and point 2 weighs less. That decision is not made, and points 1 and 3 do not move.

**Failure modes:** a lost report (crash after indexing) is the same case as in A,
with a worse substitute. A duplicate is safe only if the endpoint is idempotent by
status (**guess**: the verb should make it so). Out-of-order is the same conflicting
case as in A.

### C. Ingestion polls retrieval

Ingestion periodically asks retrieval for the state of each `pending` document.

- **Repositories affected:** ingestion (poller, client, use case) and retrieval (a
  new status endpoint it does not have).
- **New event type:** none. **Schema change:** none, but a new HTTP contract with
  no policy, as in B.

Rejected. Ingestion `CLAUDE.md` is explicit: the service "does not read from the
retrieval service's store, and does not call it", and "knows nothing about AI". It
is also rejected on its merits: contracts ADR 0003 decides that "work crosses the
boundary only as published events", and ingestion calling retrieval is the
availability coupling `ARCHITECTURE.md` §2 rejects. A poller would also need to
visit every `pending` document on every run, which grows with the backlog, and it
would spend the scheduled workflow's minutes asking a service that is asleep.

### D. Do not report back; remove or redefine `pending`

Three variants, all of which leave the system one-directional:

- **D1. Remove the unreachable statuses.** Shrink `DocumentStatus` to what ingestion
  can observe. Touches the domain and the state machine, the `CHECK` constraint
  (ingestion ADR 0012, so a migration), the `GET` response (a change to a published
  API, and the README guard in ingestion ADR 0023), and `ARCHITECTURE.md` §5
  Phase 1, which names the machine. All of it needs approval (`COLLABORATION.md`
  §4). Also `mark_failed()`'s recovery story, "submit again", loses its trigger.
- **D2. Keep the enum, change what `pending` means.** Document and test that
  `pending` is "accepted, not known to be indexed", and that the other three are
  reserved. Cheapest. The domain keeps three methods nothing calls, and the `202`
  still promises less than it seems to. It is honest and unfinished.
- **D3. Move the answer to retrieval.** Retrieval exposes whether a document is
  searchable, and clients ask it. Ingestion's `status` is then renamed or dropped.
  Needs a new retrieval endpoint and leaves a client to join two services.

**What ADR 0008 requires:** nothing for D1 and D2, as no event exists. **Failure
modes:** none new, because nothing is transmitted. The cost is that the system
cannot say whether a document has been indexed, from ingestion's side or anyone's
in D1 and D2.

**ADR trigger:** D1 corrects a decision in force and the records that state it (in
place, contracts ADR 0001); D2 only needs a documentation change.

### Considered and not developed

Retrieval writing to ingestion's PostgreSQL directly. It breaks the split that
contracts ADR 0002 exists to justify, and gives two services one schema.

## Recommendation: A, for Carlos to decide

**Choose A, and approve only the mechanism now.** The reasons, in order:

1. **It is the only option that keeps both existing rules at once**: ingestion does
   not call retrieval (ingestion `CLAUDE.md`), and work crosses the boundary only as
   published events (contracts ADR 0003). B breaks neither in letter, but gives up
   the second in spirit. C breaks the first outright.
2. **It adds no public write surface.** The system's largest known exposure is an
   unauthenticated API (ingestion ADR 0025); A leaves it as it is.
3. **It reuses machinery already decided.** A stream, a consumer group, redis-py and
   a `--once` command on a schedule are what ingestion ADR 0027 and the relay
   proposal chose for the other direction.

**Honest costs of A**, which a reader should weigh against D2:

- It is the most work for the least visible benefit. The only reader of `status` is
  one endpoint (**guess**), and Phase 9's completion criterion does not mention it
  (`ARCHITECTURE.md` §5).
- Ingestion becomes a consumer, and gets a second scheduled job with the first
  one's risks: GitHub's schedule is not a promise, and a workflow nobody runs fails
  silently (ingestion ADR 0027).
- The status is minutes late, and retrieval's weaker delivery substitute (no
  outbox) is the real engineering risk.

**When to pick D2 instead:** if the status is not worth a second scheduled job and
a port change, D2 is the honest, cheap answer, and it can be undone later by
building A. D2 does not block A. B is not recommended in any case before Phase 13.

**Order, if A is approved** (the first two are other work):

1. The content-fetch gap (inventory §4.1) is settled first, because retrieval
   cannot consume anything until then (`CLAUDE.md`, "Next").
2. Retrieval's Phase 8 defines what indexing produces. **The event shapes are
   derived from that, not before.**
3. A contracts ADR and release adding the two events (minor, ADR 0008).
4. Ingestion's consumer ships **before** retrieval starts publishing, so entries
   never wait on a stream that may trim them.

## ADR triggers (`COLLABORATION.md` §8)

If A is approved, **three records**:

- **A contracts ADR for the decision itself.** It is a new direction on a boundary
  between services. It also corrects the "events flow one way" negative in
  contracts ADR 0003 in place, as `COLLABORATION.md` §8 asks, and settles the second
  stream's name, which ADR 0004 leaves to Phase 3.
- **A contracts ADR for the event contract**, written when the shape is known, in
  the pattern of ADR 0007. `CLAUDE.md` says every new event gets one.
- **An ingestion ADR** extending ingestion ADR 0027: where the consumer runs and how
  its silence is read. The port change is a decision for that repository.

`ARCHITECTURE.md` and `COLLABORATION.md` are kept identical in both repositories,
so a change to the topology diagram is a pair of pull requests (the header of each
file says so). That change is **not** part of this one.

## What this does NOT include

- **Any schema, field or event class.** Not even the names `DocumentIndexed` and
  `DocumentIndexingFailed` are decided; they come from the request that started
  this proposal.
- **A failure reason.** The domain's `mark_failed()` takes none and the table has no
  column for one. Adding it is a domain and schema change in ingestion.
- **The stream's name, its bound and its retention.** The bound for the existing
  stream is ingestion ADR 0029; the reverse stream needs its own, once retrieval
  states its outage tolerance.
- **The content-fetch gap** (inventory §4.1). It is the first of the two gaps and
  needs its own proposal. This one only notes where they touch.
- **Retrieval's retry policy and its definition of a permanent failure**, which
  belong to retrieval's domain.
- **A correction of the `202` and `pending` wording in ingestion**, which is D2 and
  would be ingestion's pull request.
- **Any change to `CLAUDE.md`'s "Next" list.**

## Consumers affected

| Repository | A | B | C | D1 / D2 / D3 |
|---|---|---|---|---|
| `devtools-rag-contracts` | Two event classes, a minor release, two ADRs | None | None | None |
| `devtools-rag-ingestion` | Consumer command, use case, port method, scheduled job, ADR | Write endpoint, auth, use case, port method | Poller and HTTP client | D1: domain, migration, API; D2: docs; D3: status dropped or renamed |
| `devtools-rag-retrieval` (empty today) | Publisher, ack-after-publish rule | HTTP client and retry | New status endpoint | D3 only: a status endpoint |

## Why this way (teaching notes)

- **The pattern is event-carried state transfer in the return direction**, over the
  same broker, which turns a one-way pipeline into a request and reply conducted
  through two queues. The vocabulary to look up is "choreography" against
  "orchestration": in A neither service tells the other what to do, each announces
  what it did.
- **Retrieval's missing outbox is the interesting engineering gap.** The
  transactional outbox exists to make "write my state and announce it" atomic
  (contracts ADR 0003). Without a relational store in retrieval, the substitute is
  to not acknowledge the input until the output is out. In .NET terms: a
  message-handler that completes the queue message only after `Publish` returns.
  It gives at-least-once and relies on the handler being idempotent. It is weaker
  because re-indexing costs money, where a duplicate outbox row costs nothing.
- **Idempotent consumer by state machine.** In A the handler needs no deduplication
  table: the status itself says whether the work is done. It is the same idea as an
  idempotent `PUT`, and the same as checking a saga's current step before applying
  an event.
- **Free-plan constraints decide the shape here as they did for the relay.** There
  is no always-on process, so a consumer is a command run on a schedule. That is a
  Kubernetes `CronJob`, or a Quartz job in Java, doing the work of a message
  listener, and the price is latency.
- **A status that is never reached is a lie in the type.** `DocumentStatus` has four
  values and three methods nobody calls. In C# it is an enum member with no writer,
  and the compiler cannot tell. That is why D is a real option, and not a way of
  dodging the work.

## Questions for the reviewer

1. **Which option?** A is recommended; D2 is the cheap honest alternative, and
   does not rule A out later. Is a status that lags by minutes worth a second
   scheduled job?
2. **Is it acceptable for ingestion to become a consumer?** It changes
   `ARCHITECTURE.md`'s topology and ingestion's `CLAUDE.md` description of what the
   service does, both in a pair of pull requests.
3. **One stream or two?** The request that started this proposal said a second
   stream. Contracts ADR 0007 chose one stream, `documents.events`, with
   `event_type` telling events apart, rejecting one stream per type "while there is
   a single event". Putting results on the same stream would make retrieval read
   its own output. I lean to a second stream (**guess**) and have not designed it.
4. **If `failed` arrives and then `indexed`** (a redelivery that succeeds), should
   ingestion ignore and log, fail the run, or is `failed` too strong a terminal
   state? That touches the domain, which needs your approval.
5. **Is `processing` meant to be observable?** If so, A needs a third event; if not,
   the handler walks two transitions in one transaction and the state is never
   seen.
6. **Do you accept settling the mechanism now and the shape only after Phase 8?**
   That keeps `CLAUDE.md`'s rule that a field no domain needs is a guess on the
   wire, and it leaves the gap open for longer.
7. **Should the scheduled consumer share the relay's workflow or have its own?**
   (**guess**: share it; that is for ingestion's proposal.)
