# 1. Record the system's architecture decisions here

- **Status:** Accepted
- **Last revised:** 2026-10-28

## Context

The ingestion service has recorded its decisions since its first commit, under
the rules of its own ADR 0001. Those rules were written for one repository, and
the system now has two, with a third to come. Some decisions belong to none of
them alone: where the service boundary runs, what crosses it, how it crosses,
and what the documents are. `ARCHITECTURE.md` §4 principle 9 names three of
them — "service split, broker choice, outbox over direct call" — as needing an
ADR, and §2 says of the broker that "this decision belongs in an ADR". None has
one.

The ingestion repository already points here for them. Its `CLAUDE.md` says
"system-wide decisions live in `devtools-rag-contracts/docs/adr/`", and its
`README.md`, `CLAUDE.md` and `ARCHITECTURE.md` cite "ADR 0005 in the contracts
repository" for the corpus. **That link is broken until this directory exists.**

## Options considered

- **Record system-wide decisions in the ingestion repository.** It has the
  directory, the habit and twenty-five records already. Rejected: the retrieval
  service would then read its own boundary decisions in another service's
  repository, and the contracts package — the one repository both services
  depend on — would be the only one that holds none of the reasoning about
  what it carries.
- **Copy each system-wide record into every repository**, as `ARCHITECTURE.md`
  and `COLLABORATION.md` are copied today. Rejected: those two files already
  need a header explaining how to check they still match. Doing the same for
  every decision multiplies that obligation by the number of records, and a
  copy that drifts is worse than no copy.
- **One home for system-wide decisions, in this repository.** Chosen. It is the
  repository both services already depend on, and the one whose purpose is the
  space between them.

## Decision

Use Architecture Decision Records here exactly as ingestion ADR 0001 defines
them: one file per decision, Nygard's format, at least one rejected
alternative and at least one negative consequence in every record, and
`COLLABORATION.md` §8 as the trigger list.

### What belongs here and what does not

**A decision belongs here when it binds more than one repository**: where the
service boundary runs, how the services communicate, the broker, the event
contracts and their versioning policy, and the corpus. Decisions about the
contracts package itself — its toolchain, its layout — also live here, because
this is its repository; they share the one sequence.

**A decision belongs in a service's own `docs/adr/` when only that service has
to change if it is reversed**: its database schema, its HTTP API, its
container, its logging, its vector store, its chunking. The outbox is the
clearest case of the split. That services communicate through an outbox is
system-wide (ADR 0003 here); the table's columns, the payload function and who
commits are ingestion's (its ADRs 0012, 0013 and 0014).

### Numbering is per repository

Each repository numbers from 0001 on its own. "ADR 0002" means nothing without
a repository, so records here cite others as **"ingestion ADR 0012"** and this
directory's as **"contracts ADR 0004"** when the context is ambiguous. The
copied `ARCHITECTURE.md` and `COLLABORATION.md` carry a header saying that
unqualified numbers in them are ingestion's; that remains true.

### Records are corrected in place

The rule from ingestion ADR 0001 applies unchanged. When a decision changes, or
a record turns out to state something untrue, the record is edited through a
pull request, and `docs/adr/` shows only decisions in force. Each record
carries **`Last revised`**: the day its contents were last known to be true.

## Consequences

**Positive.** The decisions that every repository inherits have one place to be
read, argued with and corrected. The ingestion README's link to ADR 0005
resolves. A retrieval service, when it exists, starts with its boundary already
written down rather than spread across another service's records.

**Negative: ADRs 0002 to 0005 are written after the fact.** Each was decided
when the system was designed, recorded only in `ARCHITECTURE.md`, and is
written up here weeks later. Ingestion ADR 0001 names exactly that risk —
retroactive records "produce justification rather than reasoning". The defence
is that these records restate the reasons `ARCHITECTURE.md` and the ingestion
ADRs already give, and mark plainly what those sources leave open.

**Negative: the boundary between "system-wide" and "local" is a judgement.**
Ingestion ADR 0003 sets the import roots of all three repositories
(`rag_ingestion`, `rag_contracts`, `rag_retrieval`), which by the test above
makes it system-wide; it was written before this directory existed and stays
where it is. Moving it is not done here.

**Negative: a reader now needs two directories, and cross-references between
them are links between repositories**, which resolve only on GitHub or with
both clones side by side. Nothing in CI checks them.
