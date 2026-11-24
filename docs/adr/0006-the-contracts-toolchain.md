# 6. The contracts toolchain: the ingestion service's, and where it differs

- **Status:** Accepted
- **Last revised:** 2026-10-28

## Context

Phase 3 needs a package before it needs a schema: something that builds,
type-checks and tests, so that the first schema lands in a repository that
already verifies it. `CLAUDE.md` says the toolchain follows the ingestion
service's "unless an ADR here says otherwise". This is that ADR. Everything it
does not name — Python 3.14, `uv` pinned to 0.12.10 in CI, hatchling, the src
layout, the 23 `ruff` families, `mypy --strict` with its three gaps closed, one
CI job with actions pinned to commits — follows ingestion ADRs 0002 to 0006,
0008 and 0024, summarised in `docs/TOOLCHAIN-REFERENCE.md`.

What makes this repository different is one fact: **it is a library that its
consumers build from source**, as a pinned Git dependency, rather than a service
that is deployed.

## Options considered

### `requires-python`

- **`>=3.14`, as ingestion has.** Chosen, for a different reason. Ingestion
  called its floor "a floor, not a pin" because the runtime that matters is its
  image. A library's floor is a constraint on whoever installs it, so it must be
  a claim CI actually tests. Both consumers run 3.14.
- **A wider floor such as `>=3.12`.** Rejected: CI tests one interpreter, and a
  floor nothing tests is a promise nobody has checked.

### Runtime dependencies

- **None until the first schema.** Chosen. Pydantic arrives with the first
  module that imports it, by ingestion's rule "declare what you import". Its range
  is decided there; it has to admit 2.13.5, which ingestion locks.
- **Pydantic now.** Rejected: a dependency nothing imports, and a second concern
  in this change.

### How CI proves the package

- **Ingestion's steps alone.** Rejected, on evidence. Every one of them runs
  against an editable install, which reads `src/` directly. A module the build
  leaves out passes them all: a module under a `.gitignore`d path was imported
  by the test suite and was absent from the wheel, because hatchling's sdist
  honours `.gitignore` and `uv build` makes the wheel from the sdist.
- **`uv build` alone.** Rejected, on evidence: with the wheel's `packages` path
  pointed at a directory that does not exist, it still built successfully — an
  empty wheel.
- **Build, then import every module under `src/` from the wheel, in an isolated
  environment.** Chosen. It is what a consumer does, and both failures above
  make it fail. `python -I` keeps the checkout off `sys.path`, so each import can
  only come from the wheel.

  **It missed a third failure, and a consumer found it.** The first release,
  0.2.0, shipped without `py.typed`, and ingestion's `mypy --strict` refused to
  import it: *module is installed, but missing library stubs or py.typed marker*.
  Every check here ran against code that type-checks, so none could see it. The
  same step now asserts the file is in the wheel, and 0.3.0 ships it.

### Versions of the development tools

- **Whatever `uv lock` resolves.** Rejected: on 2026-10-28 it resolved `ruff`
  0.17.3, `mypy` 2.4.0, `pytest` 9.2.0 and `coverage` 7.17.0, while ingestion
  locks 0.16.5, 2.3.1, 9.1.1 and 7.16.1. Two linters at two versions are two
  standards, and the difference surfaces as a review comment in one repository
  and not the other.
- **The same versions ingestion locks.** Chosen. Upgrading a tool becomes a
  change made in both repositories, deliberately.

### Rule exemptions

Ingestion ignores `D107`, and `ARG001`/`ARG002` in tests, on the strength of its
domain exceptions and its `Protocol` fakes. **This repository has neither, so
it starts without them.** `D105`, and `S101` and `D` in tests, keep their
reasons and are kept.

### Version and release

- **A static `version` in `pyproject.toml`, tagged from `main`.** Chosen. It
  started at `0.1.0` with no tag; ADR 0008 is the policy and `0.2.0` the first
  release.
- **`hatch-vcs`, deriving the version from Git tags.** Rejected: a build
  dependency, and a version no diff shows.

## Decision

- `pyproject.toml`: distribution `devtools-rag-contracts`, import root
  `rag_contracts`, `requires-python = ">=3.14"`, no runtime dependencies, a `dev`
  group of `coverage`, `mypy`, `pytest` and `ruff` locked at ingestion's
  versions, and ingestion's tool configuration less the two exemptions above.
- `uv.lock` is committed. Consumers ignore it; it fixes the development tools, so
  a tool release cannot turn CI red without a commit (ingestion ADR 0008).
- Coverage: branches measured, and the floor is what CI measured, rounded down —
  ingestion ADR 0024's rule. Today that is **100**, over a package with no
  statements yet.
- CI: one job, `Lint, types, tests`, with ingestion's steps plus the package step
  above.

## Consequences

**Positive: the first schema is checked the way a consumer will use it**, not
only the way a contributor's editable install sees it.

**Negative: a floor of 100 measured over nothing.** It holds today because there
is nothing to miss. The first schema either keeps it or lowers it, in a pull
request that says why. Never with a `pragma`.

**Negative: ruff formats Python inside Markdown.** `ruff format --check .`
reformatted a Python block in `docs/INGESTION-AT-A-GLANCE.md` the first time it
ran. Fenced Python in the docs is held to the formatter like any source file,
which is right for code a reader may copy, and is one more thing a docs-only
change can fail on.

**Negative: tool upgrades are now paired.** A `ruff` release that ingestion
adopts is not adopted here until someone does it here too. Until then, the two
repositories are linted by different versions.

**Negative: the package step relies on `src/` mirroring the import tree.** It
derives module names from file paths. A file that is not meant to be importable
would fail it, and that would be the moment to decide what such a file is doing
in a library.
