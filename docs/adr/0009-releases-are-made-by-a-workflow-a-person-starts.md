# 9. Releases are made by a workflow a person starts

- **Status:** Accepted
- **Last revised:** 2026-11-24

## Context

ADR 0008 says a release is a tag, made on `main` by a person, and never moved. It
did not say *how*, and the first two releases showed that the answer matters.

- **A tag typed by hand can disagree with the package.** While preparing 0.3.0 the
  tag was first called `v0.2.1`, then corrected to `v0.3.0` once a policy check
  caught that the change was a minor one. Nothing but attention stood between the
  wrong name and a tag that, once pinned by a consumer, can never be moved.
- **The agent working on this repository cannot make tags.** The environment it
  runs in refuses to write a tag, whether through `git push` (HTTP 403) or through
  the Git references API. Every release therefore stopped, waiting for a person to
  find the Releases page and type a name.

**Where the facts came from.** Both observations are from this session: the two
refusals were run and the `v0.2.1`/`v0.3.0` history is in this repository's pull
requests. That a repository ruleset might also restrict tag creation was not
checked; see the consequences.

## Options considered

- **By hand, in GitHub's Releases page.** Rejected as the practice, kept as the
  fallback. It works, and it is how `v0.2.0` was made, but the name is typed and
  nothing checks it against the package or against CI.
- **A workflow a person starts (`workflow_dispatch`).** Chosen. The moment stays a
  human decision, which is what ADR 0008 asks for; what moves into the workflow is
  the typing and the checking.
- **Automatically, when a merge changes the version.** Rejected. A tag is a promise
  made at a time its maker chooses, and a version bump that has merged is not
  thereby ready to be pinned by two services. It would also make the tag a side
  effect of a merge, which is the reverse of ADR 0008's "after".
- **A script run from a developer's machine.** Rejected: it depends on one
  laptop's credentials and leaves no record of who released what, or when.
- **A third-party release tool such as `release-please`.** Rejected, but **not
  evaluated in depth**: it brings a dependency and an opinionated flow into a
  repository with one maintainer and one kind of release. It may deserve a proper
  look if releases become frequent.

## Decision

`.github/workflows/release.yml`, started by hand from the Actions tab:

- **The version is read from `pyproject.toml`**, not entered, so the tag cannot
  name something other than the package it releases.
- **It refuses** to run from any branch but `main`, to create a tag that already
  exists, and to release a commit whose `Lint, types, tests` check has not
  succeeded. "No run yet" counts as a refusal, not a pass.
- **It is a dry run by default.** Every check runs and the log says what would
  have happened; a person unticks `dry_run` to do it. The first real release is
  never also the first run.
- **It creates a GitHub release, which creates the tag**, on the exact commit the
  checks were made against, then reads the tag back and fails if it points
  anywhere else.

ADR 0008's rule stands unchanged: a tag is made on `main` after the version has
merged, and is never moved or deleted.

## Consequences

**Positive: a release cannot disagree with its package, or ship a red commit.**
Both were possible by hand, and the first nearly happened.

**Positive: the agent's inability to write tags stops blocking a release.** A
person starts one workflow; nothing else is needed from them.

**Negative: it has not been run.** Its pieces were checked against this
repository one at a time (reading the version, the exit codes of the
tag-exists check, the CI query for a commit with and without a result), but the
workflow as a whole, and `gh release create` in particular, had not been executed
when this was written, and `actionlint` was not run. The dry run is how the first
use finds out. Treat the first real release as the test of the second half.

**Negative: it is the only workflow in this repository that can write.** CI has
`contents: read`; this one has `contents: write`, which is what creating a release
takes. Starting it by hand, pinning its actions to commits and running it from
`main` only are what keep that exception small.

**Negative: a rule outside the repository could still stop it.** If a ruleset
restricts who may create tags, the final step fails after every check has passed.
That was not looked at, because rulesets live in GitHub's interface.

**Negative: it fails closed on a rename.** It looks for a check named exactly
`Lint, types, tests`. Renaming that job in `ci.yml` makes every release refuse,
loudly, until this file follows.

**Negative: a tag made this way starts no other workflow.** Events created with
the workflow's own token do not trigger further workflows. Nothing here listens
for a tag, but a future "on release" job would need a different credential.

**Negative: anyone with write access may start it.** One person does today.
