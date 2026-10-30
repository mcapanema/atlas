# Contributing

Architecture rules, layer boundaries and code conventions live in
[`CLAUDE.md`](CLAUDE.md) and the CLAUDE.md file in each code directory;
the design record is [`docs/architecture/overview.md`](docs/architecture/overview.md)
plus [`docs/adr/`](docs/adr/). This file covers the checks every change
goes through.

## Continuous Integration

Every push and pull request runs backend and frontend checks in parallel,
each split into four phases: test suite (with coverage floors, and on pull
requests ≥ 90% coverage of the changed lines), type check,
lint (including formatting, complexity ceilings, and — on the frontend —
dead-code detection), and a dependency security audit (`pip-audit` for the
backend, `npm audit` for the frontend). A ninth check builds the production
Docker image. `make check` runs all nine locally, after syncing
dependencies to the lockfiles the way CI does (Docker must be running), or
run them individually: `make test`, `make typecheck`, `make lint`,
`make security`; `make format` fixes formatting.

## Git hooks

`make hooks` installs two git hooks: pre-commit (ruff and prettier checks on
the staged files, plus the whole frontend eslint run whenever a `web/`
TypeScript file is staged) and pre-push, which runs `make check` on the
commit being pushed (`git push --no-verify` skips it). Expect side effects
from pre-push:
`uv sync --locked` removes packages added ad hoc with `uv pip install`;
after a package-file change `npm ci` reinstalls `web/node_modules`, which
breaks a running `make dev` until restarted; and during the hook's run
(about 40s) pre-commit stashes your unstaged edits, so files briefly look
reverted — don't edit them until the push finishes.

## Dependabot

[Dependabot](https://docs.github.com/en/code-security/dependabot) opens
weekly PRs for outdated backend (`uv`), frontend (`npm`), GitHub Actions,
and Docker base-image dependencies. Minor/patch bumps are grouped into one
PR per ecosystem, except Docker base images, which come one PR per image —
see `.github/dependabot.yml`.
