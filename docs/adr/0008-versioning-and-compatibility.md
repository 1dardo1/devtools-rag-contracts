# 8. Versioning and compatibility: two numbers, consumers first, pinned by tag

- **Status:** Accepted
- **Last revised:** 2026-11-24

## Context

Two services consume this package, and they are deployed on their own schedules.
ADR 0007 defined `DocumentIngested` and said what a *compatible* change is. It did
not say how a change reaches the two services, which is the part that decides
whether a deploy can go wrong. This record is the policy, and with it the package
gets its first release.

Two facts shape it. **The producer's outbox keeps rows after they are written**, so
an event written under one schema can be published long after the producer has
moved to the next. And **a consumer can refuse a payload it cannot read** (ADR 0007:
`schema_version` is `Literal[1]`), so the order in which the services upgrade is
not a detail.

## Options considered

### What the numbers mean

- **Two numbers.** Chosen. The *package version* (semantic versioning, in
  `pyproject.toml`, tagged `vX.Y.Z`) says what a consumer installs. The
  *`schema_version`* inside an event (an integer) says which shape one payload has.
  They move for different reasons: a new event or a documentation fix changes the
  first and not the second.
- **One number for both.** Rejected: a payload stored in an outbox for a week would
  carry a package version that no longer says which schema it follows, and every
  documentation fix would look like a schema change.

### How the package version moves

| Change | Bump |
|---|---|
| No change to any schema: documentation, tests, tooling | patch |
| A compatible schema change: an optional field with a default, a new `doc_type` value, a new event | minor |
| An incompatible one: removing or renaming a field, changing a type, making an optional field required | major, and a new `schema_version` |

### Rolling out an incompatible change

- **Expand, then contract, consumers first.** Chosen.
  1. A **major release** adds the new class beside the old one, `DocumentIngestedV2`
     next to `DocumentIngested`. Nothing is removed.
  2. **Consumers upgrade** and accept both versions.
  3. **The producer switches** to writing the new one.
  4. The old class is removed in a later major release, **only once no row carrying
     it is left unpublished in the outbox.** That is a query on the producer's
     database, and the producer is the one who runs it.
- **Producer first.** Rejected: a consumer that has not upgraded sees an event it
  refuses, and the relay has no one to hand it to.
- **Both services deployed together.** Rejected: it works until one deploy fails,
  and a lockstep release is the thing the split into two services was meant to end.

### How a service pins the package

- **A Git tag, in the dependency:** `devtools-rag-contracts @
  git+https://github.com/1dardo1/devtools-rag-contracts@v0.2.0`. Chosen. A version
  a person can read, in a file a person reviews. The consumer's lockfile records
  the commit as well.
- **A commit hash.** Rejected: it cannot be read, and a reviewer cannot tell a
  patch from a major version.
- **A branch (`@main`).** Rejected: it moves under the consumer, which is the
  opposite of pinning.
- **Publishing to a package index.** Rejected: two private consumers do not
  justify an account, a token to publish with and a release pipeline.

### Who may release

- **A tag is made on `main`, after the pull request that sets the version has
  merged, and is never moved or deleted.** Chosen. A moved tag is two services
  resolving one name to two different contents. It is made by the `Release`
  workflow, which a person starts (ADR 0009), rather than typed.
- **Tagging from a branch.** Rejected: it would publish something that review has
  not seen.

## Decision

- The package version is semantic and static in `pyproject.toml`. This change sets
  it to **`0.2.0`**: the first release with a schema.
- Compatible and incompatible changes are those of the table above and of ADR 0007.
- **Incompatible changes roll out consumers first**, by adding the new class beside
  the old one, as above.
- Consumers pin by tag. A tag is never moved.
- Until `1.0.0`, **a minor release may also be incompatible**, as semantic
  versioning allows for `0.y.z`. This is the one place the policy is looser than
  the table, and it ends with the first release both services run in production.

## Consequences

**Positive: an upgrade can be reasoned about before it is made.** The table says
what kind of release a change is, and the roll-out says who goes first.

**Negative: removing a field is slow on purpose.** It takes two major releases and
a query against another service's database. A field that should never have existed
stays for as long as that takes.

**Negative: the old and the new class coexist, and so does code that handles both.**
Every consumer carries the branch for the whole of the window, and a bug in the
branch that nobody exercises is a bug nobody sees.

**Negative: a tag is a promise a person has to keep.** Nothing in the repository
stops someone from moving it. The pin in a consumer's lockfile is what would show
the difference, after the fact.

**Negative: the `0.y.z` allowance is a loophole.** A minor release can break a
consumer without anyone having broken a rule. It is accepted because both services
are written by the same hands, and it is time-limited.
