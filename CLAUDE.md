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

## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues (via the `gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default canonical labels (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
