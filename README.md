# Automatic Systematic Review

A web app that helps researchers run a systematic review: importing citations, screening
them against criteria with AI-assisted suggestions, tracking PRISMA flow counts, and
extracting data from full-text PDFs. The target audience is any researcher, with a
particular focus on doctors — including med students applying to residency who have no
institutional review tool available to them. The AI features suggest, they never decide:
every Include/Exclude/Maybe call is the Reviewer's, and AI suggestions are always shown
separately from the Reviewer's own decision.

The core review workflow (import, screen, extract, export) is free. Billing is off for the
pilot (`BILLING_ENABLED=false`) and will only ever apply to AI usage past a free allowance,
never to the workflow itself.

## AI disclosure

Every account must accept this before using the app — it's a required checkbox at sign-up,
enforced server-side, not just a UI nicety:

> Abstracts, PDFs and criteria you add are sent to Anthropic's API to generate suggestions.
> Don't upload patient-identifiable data.

Do not upload PHI or any patient-identifiable data. The pilot's hosting terms forbid storing
it, independent of this disclosure.

## Prerequisites

- Python managed by [`uv`](https://docs.astral.sh/uv/) (reads `backend/.python-version`)
- Node.js + `npm`, for the frontend
- PostgreSQL, reachable via a connection string (local install, Docker, or a hosted instance)
- An [Anthropic API key](https://console.anthropic.com/) for AI suggestions

## Backend setup

```
cd backend
uv sync
```

Create `backend/.env` (never commit it — it's gitignored) with these variables. Names only;
get real values from your own database, Anthropic account, and a generated secret — never
copy another environment's `.env`:

| Variable | Required | Note |
|---|---|---|
| `DATABASE_URL` | yes | `postgresql://...` — the app switches it to the `psycopg` driver itself |
| `ANTHROPIC_API_KEY` | yes | Your Anthropic API key |
| `JWT_SECRET_KEY` | yes | A generated random secret; rotating it signs everyone out |
| `TEST_DATABASE_URL` | for tests only | Points the test suite at a *separate* database it resets — never point this at data you want to keep, and never set it in a deployed environment |
| `ANTHROPIC_MODEL` | no | Defaults to `claude-haiku-4-5` |
| `FRONTEND_ORIGIN` | no | Defaults to `http://localhost:3000`; used for CORS |
| `FULL_TEXT_STORAGE_PATH` | no | Defaults to `./storage/full_texts` |
| `SIGNUP_ALLOWLIST` | no | Comma-separated emails allowed to register; empty means nobody can self-register |
| `TRUSTED_PROXY_COUNT` | no | Reverse proxy hops in front of the app, for rate-limit IP detection; defaults to `0` (no proxy). Get this wrong and the sign-in/sign-up rate limit either shares one bucket across every visitor or trusts a client-supplied address — see `docs/deploy/render.md` for how it was measured on Render |
| `BILLING_ENABLED` | no | Defaults to `false`. If set to `true`, four `STRIPE_*` variables become required — the app fails fast at startup and names which ones are missing |

Run the database migrations:

```
uv run alembic upgrade head
```

Start the dev server:

```
uv run uvicorn asr_backend.main:app --reload
```

It listens on `http://localhost:8000` by default; `/health` returns `{"status": "ok"}`
when it's up.

## Frontend setup

```
cd frontend
npm install
```

Set `NEXT_PUBLIC_API_URL` (e.g. in `frontend/.env.local`) to the backend's URL if it isn't
`http://localhost:8000`. This is a **build-time** value baked into the browser bundle — changing
it after a production build needs a rebuild, not just a restart (on Render specifically, a
plain redeploy can reuse a build cache and keep serving the old value; use "Clear build cache
& deploy" and confirm by checking the served bundle).

```
npm run dev
```

Serves on `http://localhost:3000` by default.

## Running, testing, linting

| | Backend (`backend/`) | Frontend (`frontend/`) |
|---|---|---|
| Dev server | `uv run uvicorn asr_backend.main:app --reload` | `npm run dev` |
| Tests | `uv run pytest` | `npm run test` |
| Lint | `uv run ruff check .` | `npm run lint` |

The backend test suite uses `TEST_DATABASE_URL`, a database it resets on every run — point it
at something disposable, never at data you want to keep. CI (`.github/workflows/ci.yml`) runs
both suites on every PR.

A deployed two-reviewer smoke run with fixed data and expected values is documented in
`docs/testing/pilot-smoke.md` — the same protocol used to validate every pilot release.

## Operator scripts

Password reset and account/project deletion are operator-run, on request — there is no
self-service email flow or in-app delete button for the pilot; the pilot terms say so. Run
these from `backend/`, against the deployed environment's database:

```
uv run python scripts/reset_password.py <email>
uv run python scripts/delete_project.py <project-id> --yes
uv run python scripts/delete_account.py <email> --yes
```

- `reset_password.py` sets a new random password and prints it once — it is not shown again,
  so relay it to the Reviewer through a channel you trust.
- `delete_project.py` and `delete_account.py` require `--yes` and remove rows (via
  relationship cascades) and any PDFs under `FULL_TEXT_STORAGE_PATH`, printing what was
  removed. Deleting an account also removes the projects it owns; see
  `asr_backend/operator_tasks.py` for exactly how projects where the account is only a
  Co-Reviewer are handled.

Run any script with `--help` for its exact arguments.

## Release flow

1. Open a PR against `main`. CI (`.github/workflows/ci.yml`) runs both test suites.
2. Rebase-merge to `main` once CI is green and the PR is reviewed.
3. Deploy: see `docs/deploy/render.md` for the full runbook (creating the Render Blueprint,
   environment variables, manual-deploy steps, backups, and the two restore tests to run
   before any real data exists). In short: **Manual Deploy** the merged commit on `asr-api`
   and `asr-web` from the Render dashboard; migrations run automatically before the new
   backend takes traffic.
4. After deploying, smoke test per `docs/deploy/render.md` — at minimum `/health`,
   registering, importing and screening a citation, attaching and reopening a PDF, and
   exporting. For a release that touches review flows, run the full protocol in
   `docs/testing/pilot-smoke.md` instead.

## Project structure

- `backend/` — FastAPI app (`src/asr_backend/`), Alembic migrations (`migrations/`),
  operator scripts (`scripts/`), tests (`tests/`). Managed with `uv`.
- `frontend/` — Next.js app (TypeScript/React). No business API routes of its own — the
  backend is the single source of truth for data access; the frontend calls it over HTTP.
- `docs/` — architecture (`CONTEXT.md`, `docs/adr/`), deploy runbook (`docs/deploy/render.md`),
  and the pilot smoke-test protocol (`docs/testing/pilot-smoke.md`).
