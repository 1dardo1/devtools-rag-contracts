# Toolchain reference: how the ingestion service is set up

**What this is.** A reference copy of the toolchain and working conventions of
`devtools-rag-ingestion`, taken from its `main` on 2026-10-28, so that whoever
writes this repository's scaffold proposal has it to hand without opening the
other repository.

**What this is not.** A decision. `CLAUDE.md` calls ingestion's toolchain "a
starting point to be decided in the scaffold's proposal"; that proposal may
diverge from any line below.

**ADR numbers below are the ingestion service's** (`devtools-rag-ingestion/docs/adr/`),
not this repository's. Every TOML and YAML block marked *verbatim* was copied from
the file named above it, not written from memory. If ingestion changes, this file
is stale until someone re-copies it.

---

## 1. Python version

- `.python-version` contains `3.14`.
- `pyproject.toml` declares `requires-python = ">=3.14"`.
- `ruff` uses `target-version = "py314"`; `mypy` uses `python_version = "3.14"`.
- The image is built on `python:3.14-slim` (ADR 0019).

**Why (ADR 0002).** 3.12 was already security-only; 3.13 was weeks from leaving
its bugfix window when the decision was taken (2026-08-28), so the service would
have shipped on a security-only interpreter. 3.14 has the longest support runway
(bugfix until roughly October 2027), wheels for `pydantic-core` and
`psycopg-binary` were verified on PyPI, and PEP 649/749 (deferred evaluation of
annotations) removes the need for `from __future__ import annotations`. The
constraint is a floor, not a pin, *because ingestion is a deployed service, not a
library*: the runtime that matters is the `Dockerfile`'s. Recorded cost: Pydantic
and FastAPI introspect annotations heavily, a path with less mileage on 3.14.

## 2. `uv`

- CI pins **`uv` 0.12.10**, installed with `astral-sh/setup-uv`, pinned to a
  commit SHA: `astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d # v10.0.1`,
  with `version: "0.12.10"`. The same pin appears in `ci.yml` and `migrate.yml`.
- Python itself is fetched by `uv sync` from `.python-version`; there is no
  `actions/setup-python` step.
- `uv sync --locked --all-groups` is the install step **and** the lockfile
  check: it fails instead of re-resolving if `uv.lock` and `pyproject.toml` have
  drifted (ADR 0008).
- `uv.lock` header: `version = 1`, `revision = 3`, `requires-python = ">=3.14"`
  (49 packages). The image copies `ghcr.io/astral-sh/uv:0.12.10` into its build
  stage only (ADR 0019).

**Why the pin (ADR 0008).** "A release of the build tool should not be able to
change what this workflow does without a commit saying so."

In the environment where this file was written, `uv --version` printed
`uv 0.11.32 (x86_64-unknown-linux-gnu)` and `python3 --version` `Python 3.13.17`.

## 3. Build backend, layout and project metadata

Verbatim, `pyproject.toml` (comments between these lines omitted; the
`[project]` table carries a long comment block above `dependencies` explaining
each runtime dependency):

```toml
[project]
name = "devtools-rag-ingestion"
version = "0.1.0"
description = "Document intake service for a RAG system, with a transactional outbox."
readme = "README.md"
requires-python = ">=3.14"
license = { file = "LICENSE" }
dependencies = [
    "alembic>=1.19.2",
    "fastapi>=0.141.1",
    "psycopg[binary]>=3.3.5",
    "pydantic>=2.13.5",
    "pydantic-settings>=2.15.0",
    "uvicorn>=0.38.0",
]
```

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/rag_ingestion"]
```

- **src layout, single import root (ADR 0003).** `src/rag_ingestion/`, distribution
  `devtools-rag-ingestion`. ADR 0003 set the shared prefix `rag_ingestion`,
  `rag_contracts`, `rag_retrieval`. Keeping `src/` off `sys.path` makes the suite
  test the installed distribution; the cost is that `uv sync` must run first.
- **hatchling (ADR 0004)**, over setuptools (era-mixed documentation) and
  `uv_build` (youngest, ties packaging to one frontend). **The wheel `packages`
  line is not optional**: hatchling auto-detects `src/<normalised distribution
  name>`, and since the names differ the build fails without it
  (`Call to hatchling.build.build_editable failed`). Any further `[tool.hatch.*]`
  line "should be treated as a decision, not a detail".
- `hatchling` is unpinned in `[build-system]` and, as a build dependency, absent
  from `uv.lock`.
- `license = { file = "LICENSE" }` (MIT): hatchling checks the file exists; see
  trap 3. This repository already has a `LICENSE`.

## 4. `ruff`

Verbatim, `pyproject.toml`:

```toml
[tool.ruff]
target-version = "py314"

# ADR 0006: twenty-three rule families, chosen individually.
[tool.ruff.lint]
select = [
    "A",    # flake8-builtins — shadowed builtins
    "ARG",  # flake8-unused-arguments
    "B",    # flake8-bugbear — real defects, not style
    "C4",   # flake8-comprehensions
    "D",    # pydocstyle — docstrings; see ADR 0006 for the two exclusions
    "DTZ",  # flake8-datetimez — naive datetimes reach PostgreSQL
    "E",    # pycodestyle errors
    "EM",   # flake8-errmsg
    "F",    # Pyflakes
    "G",    # flake8-logging-format
    "I",    # isort
    "LOG",  # flake8-logging
    "N",    # pep8-naming
    "PT",   # flake8-pytest-style
    "PTH",  # flake8-use-pathlib
    "RUF",  # Ruff-specific
    "S",    # flake8-bandit — security; Phase 13 depends on this being on now
    "SIM",  # flake8-simplify
    "T20",  # flake8-print — a stray print is a data escape
    "TID",  # flake8-tidy-imports — bans relative imports, enforcing ADR 0003
    "TRY",  # tryceratops
    "UP",   # pyupgrade
    "W",    # pycodestyle warnings
]

# D105: a magic method's contract is defined by Python, not by this codebase.
# D107: every domain exception's `__init__` is one `super().__init__(f"...")`
# line under a class that already carries its own docstring.
ignore = ["D105", "D107"]

# Not optional: without it `D` selects two mutually exclusive pairs
# (D203/D211 and D212/D213) and `ruff` silences one of each with a warning.
[tool.ruff.lint.pydocstyle]
convention = "pep257"

[tool.ruff.lint.per-file-ignores]
# S101: `assert` is pytest's mechanism.
# ARG001/ARG002: fakes implementing a Protocol legitimately ignore parameters
# the port declares, and fixtures are requested for their side effects. See
# ADR 0006 for why renaming the parameter is not an acceptable workaround.
# D: a test's name is already its sentence. Docstrings stay welcome here for
# the ones that need a reason, but are not demanded of all 132.
"tests/**" = ["S101", "ARG001", "ARG002", "D"]
```

**Why (ADR 0006).** Default formatting; lint families chosen one by one, rejecting
the defaults (no mutable-default, import-order, naive-datetime or security checks)
and `ALL` (contradictory families; any upgrade can break CI). Excluded on purpose:
`ANN` (redundant with `mypy --strict`), `TC` (can break Pydantic's runtime
annotation introspection under PEP 649), `COM`/`ISC` (fight the formatter), `RET`,
`FBT`, `ERA`, `PL`. A snapshot of `ruff` 0.16.5, which is also the locked version.

## 5. `mypy`

Verbatim, `pyproject.toml`:

```toml
[tool.mypy]
python_version = "3.14"
strict = true
files = ["src", "tests"]
mypy_path = "src"
warn_unreachable = true
enable_error_code = [
    "ignore-without-code",
    "possibly-undefined",
    "redundant-expr",
    "truthy-bool",
]
```

**Why (ADR 0005).** `--strict` plus three gaps closed: untyped libraries
(`ignore_missing_imports` stays `false`; exceptions are per-module
`[[tool.mypy.overrides]]`, so debt is visible), scope (`tests` too, the only proof
under structural typing that fakes match ports), and silencing (a bare
`# type: ignore` is an error). The ADR's block omits `mypy_path = "src"`; the file
has it. Locked `mypy` is 2.3.1.

## 6. `pytest`

Verbatim, `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
# ADR 0011. The unit suite must stay runnable on a machine with no Docker, so
# anything that starts a container is marked and can be excluded with
# `-m "not integration"`. `--strict-markers` turns a typo in a marker name into
# an error rather than a silently unfiltered test.
addopts = "--strict-markers"
markers = [
    "integration: starts a real container; needs a Docker daemon",
]
```

**Why (ADR 0011).** Integration tests start their own PostgreSQL containers
(`testcontainers[postgres]`), so `uv run pytest` is the whole story; the marker lets
the unit suite run without Docker. `--strict-markers` turns a mistyped marker into
a collection error instead of a test that escapes every filter. Locked `pytest` is
9.1.1 (declared floor `>=8.4.2`).

## 7. Coverage

Verbatim, `pyproject.toml`:

```toml
[tool.coverage.run]
source = ["rag_ingestion"]
# Lines alone call an `if` covered when only one of its outcomes ever ran.
branch = true

[tool.coverage.report]
# The floor is what the whole suite reached in CI on the day it was set
# (99.86%), rounded down, not a figure from a style guide. It only moves up: lowering it is a
# decision, made in a pull request that says why. Without Docker the integration
# tests do not run and a local report falls below it; ADR 0024.
fail_under = 99
show_missing = true
skip_covered = true
```

**Why (ADR 0024).** `coverage run -m pytest` directly; `pytest-cov` is a wrapper
and a second dependency. Branches, because lines call an `if` covered when one
outcome ran. The floor is CI's whole-suite measurement (99.86%) rounded **down**;
one unreachable branch stays visible rather than `pragma`'d. No Codecov: it needs a
token. Locked `coverage` is 7.16.1.

## 8. Dependency groups

One PEP 735 group, `dev` (`uv sync --all-groups` installs it):
`coverage>=7.16.1`, `httpx2>=2.12.0`, `mypy>=2.3.1`, `pytest>=8.4.2`,
`ruff>=0.16.5`, `testcontainers[postgres]>=4.15.0`. Runtime dependencies are in
section 3. The manifest's stated rule: **declare what you import** — Pydantic is
declared although FastAPI pulls it in, because `api/` imports it.

### Pydantic: the version both services must agree on

`pyproject.toml` declares `pydantic>=2.13.5`. `uv.lock` resolves:

| Package | Locked version |
|---|---|
| `pydantic` | **2.13.5** |
| `pydantic-core` | 2.46.5 |
| `pydantic-settings` | 2.15.0 |

`rag_contracts` will depend on Pydantic too, and both services install it as a
pinned Git dependency, so whatever range this repository declares has to admit
2.13.5 or ingestion cannot resolve. Ingestion's declared floor equals its lock.

## 9. CI

From `.github/workflows/ci.yml` and `.github/workflows/migrate.yml`.

- Triggers: `push` to `main`, and every `pull_request`.
- `permissions: contents: read` at workflow level.
- `concurrency` group `${{ github.workflow }}-${{ github.ref }}`; cancels in
  progress only for pull requests, never on `main`.

**Jobs in `ci.yml`:**

| Job id | Name (status line) | What it does | Required in `main` ruleset |
|---|---|---|---|
| `checks` | Lint, types, tests | `uv` setup, sync, ruff, format, mypy, coverage+pytest | **Yes** |
| `image` | Image builds and starts | `docker build`, `docker run`, poll `/openapi.json` | No (ADR 0020) |
| `compose` | Compose starts the stack | `docker compose up --wait`, post a document | No (ADR 0021) |

Sources: ingestion `CLAUDE.md` ("`main` is protected by a ruleset and the check is
required"; `image` "is not a required check") and `OPEN-DECISIONS.md` §4.4 (only
the first job can block a merge). The ruleset lives in GitHub's interface.

**The `checks` job**, verbatim:

```yaml
jobs:
  checks:
    name: Lint, types, tests
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - name: Check out the repository
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1

      - name: Install uv
        uses: astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d # v10.0.1
        with:
          # Pinned for the same reason the dependencies are locked: a uv
          # release should not be able to change what this workflow does
          # without a commit saying so.
          version: "0.12.10"

      # Also the lockfile check. `--locked` fails rather than re-resolving if
      # `uv.lock` and `pyproject.toml` have drifted apart, which is the failure
      # a reviewer cannot see by reading the diff. Python 3.14 is fetched here
      # too, from `.python-version` (ADR 0002).
      - name: Install the locked dependency set
        run: uv sync --locked --all-groups

      # `!cancelled()` on every check after the first: a lint failure must not
      # hide whether the types and tests were also broken. One run should
      # report everything that is wrong, not the first thing.
      - name: Lint (ruff check)
        run: uv run ruff check

      - name: Format (ruff format --check)
        if: ${{ !cancelled() }}
        run: uv run ruff format --check .

      - name: Type check (mypy --strict)
        if: ${{ !cancelled() }}
        run: uv run mypy

      # Under `coverage` rather than beside it: the suite runs once, and the
      # number describes exactly the run whose result is shown above it.
      # Integration tests included — the runner has Docker, and without them
      # the PostgreSQL adapters would read as untested. ADR 0024.
      - name: Tests (pytest, measured by coverage)
        if: ${{ !cancelled() }}
        run: uv run coverage run -m pytest

      # Two reports, in that order. The first goes to the run's summary page
      # and is told not to enforce, so the table appears even when the number
      # is too low — which is when somebody most needs to see it. The second
      # prints the same table to the log and fails the job below the floor in
      # `pyproject.toml`.
      - name: Coverage (report and enforce the floor)
        if: ${{ !cancelled() }}
        run: |
          uv run coverage report --format=markdown --fail-under=0 >> "$GITHUB_STEP_SUMMARY"
          uv run coverage report
```

**Why (ADR 0008).** Four jobs would each pay the `uv` setup for seconds of work; one
script stops at the first failure. Actions are pinned to SHAs because a tag is a
third party's movable pointer (`setup-uv` floats tags only to `v7`, so `@v10`
resolves to nothing). ADR 0020's rule: a job that would repeat the `uv` setup
belongs in `checks`.

**`migrate.yml`**: `workflow_dispatch` only, refuses refs other than `main`, runs in
the `production` Environment, never two at once, `uv sync --locked --no-dev`, then
`alembic current` / `upgrade head` / `current`. Database-specific (ADR 0025).

## 10. Repository hygiene files

- **`.gitignore`**: `__pycache__/`, `*.py[cod]`, `*.egg-info/`, `.venv/`, `venv/`,
  `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`, `.coverage`, `htmlcov/`, `.env`,
  `.env.*`, `!.env.example`, `.idea/`, `.vscode/`, `*.swp`, `.DS_Store`,
  `.claude/settings.local.json`.
- **`.gitattributes`**: `* text=auto eol=lf`, with `*.bat` and `*.cmd` as
  `text eol=crlf`. Reason given: a CRLF shell script fails in a Linux container
  with a misleading "not found".
- **`.dockerignore`**: an explicit deny list for the image (ADR 0019).

## 11. Commit, branch and pull-request conventions

From `docs/COLLABORATION.md` §5, which this repository carries an identical copy of:

- **Conventional Commits**, e.g. `feat(domain): add content hash deduplication rule`.
- **Branch prefixes**: `feat/`, `fix/`, `refactor/`, `test/`, `docs/`, `chore/`.
- **One concern per PR**; "if the description needs the word 'and', it is
  probably two PRs".
- **Under 400 lines of diff**; above that, split.
- Never commit to `main`; every change goes through a branch and a PR.
- Everything in the repository is in English.
- `.github/pull_request_template.md`: a verbatim copy now sits here at the same
  path.

## 12. Known traps

Each was hit in ingestion and is recorded there.

1. **Python 3.14.0rc2 breaks Pydantic.** Cause: some sandboxed environments ship
   a `uv` whose interpreter catalogue predates the 3.14 release and offers only
   `3.14.0rc2` (ADR 0002); on it, five test modules fail at collection with
   `_eval_type() got an unexpected keyword argument 'prefer_fwd_module'`
   (ingestion `CLAUDE.md`). CI is unaffected. Fix: `uvx uv@0.12.10 python install 3.14`
   fetches a final release the older `uv` does not know about. On 2026-10-28 this
   environment no longer matched the trap: its `uv` 0.11.32 offered
   `cpython-3.14.6` in `uv python list`, and no 3.14 was installed at all.
2. **Relock with the container's `uv`, not 0.12.10.** Cause: the newer `uv` also
   prunes `greenlet` wheels SQLAlchemy never requests on s390x and riscv64, which
   shows up as an unrelated diff in any PR touching the lockfile. Fix: run
   `uv lock` with the environment's own `uv`; use 0.12.10 only to install Python.
   (Specific to ingestion's dependency set; `greenlet` arrives via SQLAlchemy.)
3. **hatchling validates that the licence file exists.** Cause:
   `license = { file = "LICENSE" }`; the `Dockerfile` copied `README.md` and not
   `LICENSE`, so the first image build failed with
   `OSError: License file does not exist: LICENSE` (ADR 0020). Fix, stated as a
   rule: **every path `pyproject.toml` points at has to be present wherever the
   package is built**, because the build backend reads the manifest. For a
   package installed as a Git dependency, that includes the consumer's build.
4. **`!cancelled()` belongs in independent checks, not in a sequence.** Cause: it
   was copied into the `image` job, so after a failed build `docker run` ran
   against a nonexistent image and polling buried the real error (ADR 0020). Fix:
   use it where steps are independent checks (`checks`); leave it off steps that
   depend on the previous one; use `always()` only for log and cleanup steps.
5. **The coverage floor is compared unrounded.** Cause: `coverage report`
   displays a rounded figure, but `fail_under` compares the exact value, so a
   floor equal to the displayed number can fail. Fix: always set the floor to a
   whole number *below* the measurement (ADR 0024).
6. **A local coverage run without Docker fails the floor.** Cause: the unit suite
   alone is about 93%. Fix: `-m "not integration"` and `--fail-under=0` locally;
   only CI's number is binding (ADR 0024).
7. **Stale local state hides breakage.** A stale `.mypy_cache` reported errors for
   a reverted file, and a hatchling misconfiguration left the package unbuildable
   while local commands still passed (ADR 0008). Fix: CI on a clean machine.

## 13. What probably does not carry over

Observations about the ingestion setup against what `CLAUDE.md` says this
repository is. None of them is a decision.

- **No database, no containers.** This repository has no infrastructure clients,
  so `testcontainers`, the `integration` marker and the Docker-dependent coverage
  gap have nothing to apply to. A suite with no integration half can be measured
  in full on any machine.
- **No image.** No `Dockerfile`, so no `image` or `compose` job, no
  `.dockerignore`, and trap 3 applies to the consumers' builds rather than to an
  image of this repository.
- **No deployment.** `migrate.yml` and the `production` Environment are
  database-specific.
- **Service dependencies.** `alembic`, `fastapi`, `psycopg`, `uvicorn`,
  `pydantic-settings`, and `httpx2` (for Starlette's `TestClient`) serve a process
  this repository does not have.
- **The `rag_ingestion` names** in `[tool.hatch.build.targets.wheel]`,
  `[tool.coverage.run] source` and the ruff comments would be `rag_contracts`; the
  distribution name would follow ADR 0003's pattern, `devtools-rag-contracts`.
- **The "floor, not a pin" reasoning for `requires-python`** was made for a
  deployed service. A library's `requires-python` constrains its consumers.
- **`D107` and `ARG` exemptions** were justified against domain exceptions and
  `Protocol` fakes. Whether a schema package has either is open.
- **The PR template's "No domain file imports infrastructure"** box describes
  ingestion's hexagonal layout.
