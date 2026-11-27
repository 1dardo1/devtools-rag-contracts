---
name: verification-before-completion
description: Use before saying that anything in devtools-rag-contracts is done, fixed, green or released, and before every commit, push, pull request or report to Carlos. Names the exact command that proves each claim in this repository, including the coverage floor, the wheel check and the two consumers.
---

# Evidence before claims

`docs/COLLABORATION.md` section 7 forbids hiding uncertainty behind confident
prose. This skill is that rule made mechanical.

**No claim of success without the output of the command that proves it, run in
this turn, on the code as it stands now.**

## The gate

1. **Name the command** that would prove the claim (table below).
2. **Run it**, complete, not a subset.
3. **Read the output**: exit code, counts, warnings.
4. **Say what it showed.** If it did not prove the claim, report the real state.
5. **If it cannot run here, say so** and name what would settle it.

## What proves what in this repository

| Claim | Proved by | Not proved by |
|---|---|---|
| Lint is clean | `uv run ruff check` | an editor |
| Formatting is clean | `uv run ruff format --check .` (fenced Python in `docs/` counts, ADR 0006) | `ruff check` |
| Types are clean | `uv run mypy` | tests passing |
| Tests pass and coverage holds | `uv run coverage run -m pytest`, then `uv run coverage report` | `pytest` alone |
| The package installs and imports | CI's wheel step, which imports every module under `src/` from the built wheel and checks for `py.typed` | an editable install |
| A schema change is safe for consumers | ADR 0008's rules, and the change considered for **both** ingestion and retrieval | this repository's tests alone |
| CI is green | `gh api repos/1dardo1/devtools-rag-contracts/commits/<head sha>/check-runs` on the **current** head | an earlier head |
| A release exists | `git ls-remote --tags origin` showing the tag, made by the `Release` workflow (ADR 0009) | a version number in `pyproject.toml` |

There is no integration half here, so **a local coverage report is the number CI
enforces**. A local failure of the floor is a real failure.

## Traps specific to this container

- **Python 3.14.0rc2 cannot import Pydantic.** Install a final 3.14 with
  `uvx uv@0.12.10 python install 3.14` and point `UV_PYTHON` at it.
- **An editable install hides a module the build leaves out.** Only the wheel
  step proves the package ships what `src/` contains.

## Red flags: stop and verify

- "should pass", "probably", "looks right";
- "Done", "Released", "Compatible" before the command ran in this turn;
- quoting a subagent's report as your own result;
- calling a schema change compatible without checking ADR 0008 and both consumers.

## Source

Adapted for this repository from `verification-before-completion` in
[obra/superpowers](https://github.com/obra/superpowers) at commit `22f0b46`,
under the MIT licence in `LICENSE` beside this file
(Copyright (c) 2025 Jesse Vincent).
