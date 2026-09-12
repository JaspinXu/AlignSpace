# AlignSpace frontend runbook

React + TypeScript + Vite client for the authenticated AlignSpace backend. It
talks to the FastAPI service over the same origin (`/v1`), keeps the access
token in memory only, and refreshes the session through an HttpOnly cookie.

> **Demo status:** reference images are fixture records (`fixtureId`), not real
> uploads. Vision observations are deterministic mock output. The UI labels this
> as "演示样本 · 模拟分析" and does not claim real image understanding.

## Prerequisites

- Node.js 20.19+ or 22.12+ (Vite 7 requirement; tested on Node 24)
- Python 3.12 and [`uv`](https://docs.astral.sh/uv/) for the backend

## 1. Start the backend

From the repository root, use the authenticated application (not the legacy
`shawn` demo defaults):

```bash
export ALIGNSPACE_AUTH_SECRET="$(openssl rand -hex 32)"   # never print or commit this
export ALIGNSPACE_DEV=1
export ALIGNSPACE_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"
# optional overrides:
# export ALIGNSPACE_DATABASE_URL="sqlite:///alignspace-accounts.db"
# export ALIGNSPACE_CHECKPOINT_PATH="alignspace-accounts-checkpoints.db"
uv run uvicorn alignspace.main:app --host 127.0.0.1 --port 8000
```

The server refuses to start when the secret is missing or shorter than 32 bytes.
Re-running with a new secret invalidates existing access tokens.

## 2. Start the frontend

```bash
cd frontend
npm ci
npm run dev
```

Vite serves on `http://127.0.0.1:5173` and proxies `/v1` to
`http://127.0.0.1:8000` by default. Point it elsewhere with
`API_PROXY_TARGET=http://host:port npm run dev`.

Open `http://127.0.0.1:5173`. Register a homeowner account, create a project,
generate a project code, then register a second (designer) account and join with
that code — ideally in a separate browser profile so the two sessions do not
share cookies.

## 3. Tests and build

```bash
cd frontend
npm test          # Vitest: API client + workspace component
npm run build     # tsc --noEmit && vite build
```

Backend suites:

```bash
uv run pytest -q
uv run ruff check src tests
```

## What the frontend supports today

- Email/password registration, login, logout, and session restore after reload.
  No email verification and no password recovery in this version.
- Project list, project creation, and joining with a 12-character one-time code.
- Role-aware workspace: demo sample registration, analysis start, broad
  question, explicit preferences, confirm/reject of proposed observations,
  conflict decisions, designer review notes, brief edit and dual approval.
- Versioned writes keep `idempotencyKey` + `expectedStateVersion`; a 409 keeps
  the typed input, refetches state, and requires a deliberate resubmit with a
  new key. Waiting views poll every 5 seconds only while the tab is visible.

## Known boundaries

- Fixture-based analysis only; no real image upload, object storage, or LLM.
- Broad answers use a fixed mapping from Chinese sample options to supported
  English keywords. Arbitrary Chinese free text is not parsed.
- Brief editing exposes the goals list; other schema fields are not editable
  from the UI yet.
- Browser end-to-end (Playwright) acceptance is not set up in this version.
- The SQLite migrations are SQLite-specific.
