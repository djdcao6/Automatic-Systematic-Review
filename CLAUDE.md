## Info

See @README.md for what this project does.

## Tech stack

- Backend: FastAPI (Python) — paper ingestion, screening/extraction endpoints, calls the Anthropic API for AI screening/extraction, PDF text extraction via PyMuPDF/pdfplumber.
- Frontend: Next.js (TypeScript/React), a separate app that talks to the FastAPI backend over HTTP.
- Database: Postgres.

## Commands

Backend (run from `backend/`, uses `uv`):
- Dev server: `uv run uvicorn asr_backend.main:app --reload`
- Run tests: `uv run pytest`
- Lint: `uv run ruff check .`

Frontend (run from `frontend/`, uses `npm`):
- Dev server: `npm run dev`
- Run tests: `npm run test`
- Lint: `npm run lint`

## Code Style

- Frontend has no business API routes — the FastAPI backend is the single source
  of truth for data access; the frontend calls it over HTTP.
- Frontend: reusable UI in `src/components/`, shared logic in `src/lib/`.
  Page/layout files use Next.js's required default export; everything else uses
  named exports.
- Backend: request/response shapes defined as Pydantic models; route handlers
  stay thin and delegate logic to plain functions/modules, not inline in the route.

## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues (via the `gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default canonical labels (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
- Author a backlog-ready spec/issue → invoke /spec
