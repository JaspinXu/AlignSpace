# AlignSpace frontend runbook

React + TypeScript + Vite client for the authenticated AlignSpace backend. It
talks to the FastAPI service over the same origin (`/v1`), keeps the access
token in memory only, and refreshes the session through an HttpOnly cookie.

> **Demo status:** reference images are real uploads stored locally under
> `ALIGNSPACE_ASSET_DIR` (default `var/assets/`). Vision observations are still
> deterministic mock output — analysis remains simulated until step 2. The UI
> labels this as "真实图片 · 分析为模拟" and does not claim real image
> understanding.
>
> Accepted formats are JPEG, PNG and WebP, each up to 10MB and at most 10 per
> project. Use asset/project deletion APIs for normal removal. For a fresh demo,
> configure new database, checkpoint and asset paths together; do not clear only
> the asset directory while retaining database references. Back up all three together.

## Prerequisites

- Node.js 20.19+ or 22.12+ (Vite 7 requirement; tested on Node 24)
- Python 3.12 and [`uv`](https://docs.astral.sh/uv/) for the backend

## 1. Start the backend

From the repository root, start the authenticated application:

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
npm test          # Vitest: API client + App + workspace components
npm run build     # tsc --noEmit && vite build
npx playwright install chromium  # once per browser dependency update
npm run test:e2e  # real backend + two isolated Chromium account contexts
```

The browser test starts its own backend on `127.0.0.1:8013` and Vite on
`127.0.0.1:5174`, with a random secret and fresh databases in an
`alignspace-e2e-*` temporary directory. It refuses to reuse an existing server
on those ports and stops its servers on completion. Run `uv sync --extra dev`
from the repository root first; the harness uses `.venv/bin/uvicorn`.
Temporary databases are retained for local diagnostics; they contain test
accounts only. Screenshots are in ignored `frontend/test-results/`.

The acceptance drives registration, password login, code-based joining, reload into the same
project URL, broad/detail/conflict answers, separate explicit preferences,
brief edits, a real stale-write 409 with retained input, same-version dual
approval, and cross-tab logout. It also checks mobile overflow and captures
desktop/mobile workspace screenshots. No test identity bypass is used.

Backend suites:

```bash
uv run pytest -q
uv run ruff check src tests
```

## What the frontend supports today

- Email/password registration, login, logout, and session restore after reload.
  No email verification and no password recovery in this version.
  Logout clears the local UI immediately. Cookie-mutating auth operations use
  the same Web Lock, and late login/refresh responses cannot restore a logged-out
  local session. A non-secret localStorage logout-pending flag survives navigation
  and retries revocation before any cookie-based restore; tokens remain memory-only.
- Project list, project creation, and joining with a 12-character one-time code.
- Reloadable `?project=<id>` navigation and browser back/forward support.
- Role-aware workspace: reference image upload, analysis start, broad
  question, explicit preferences and revision of an existing preference,
  confirm/reject of proposed observations, designer constraint create/edit/
  withdraw with rationale and declared incompatible values, conflict decisions,
  designer review notes, brief edit, regeneration of a stale brief and dual approval.
- Versioned writes keep `idempotencyKey` + `expectedStateVersion`; a 409 keeps
  the typed input, refetches state, and requires a deliberate resubmit with a
  new key. Unsaved brief goals survive newer server versions; save them before
  approving. Edits typed while saving remain unsaved and cannot approve a
  different persisted goal list. Answers are kept by question ID; when another
  tab advances the task, previous unsent answers remain visible for copying in
  the current workspace (not persisted across reloads). Waiting views, including designer waits without a question and
  pending approvals, poll every 5 seconds only while the tab is visible.

## Known boundaries

- Image previews are bounded thumbnails with links to full images. Uploads retry
  one network failure with the same multipart body/key; 409 requires reselection
  after state refresh. Files are not retained across page reloads.
- The browser acceptance uses real 1600×1200 PNG uploads, checks thumbnail size,
  full-image links and deletion, then completes the two-account workflow.
  Each run isolates databases, checkpoints and uploaded files in a temporary directory.

- Vision analysis remains simulated mock output; no object storage or LLM yet.
  Uploaded images are real and stored locally (see the demo status above).
- Broad answers use a fixed mapping from Chinese sample options to supported
  English keywords. Arbitrary Chinese free text is not parsed.
- Brief editing exposes the goals list; other schema fields are not editable
  from the UI yet.
- Detail answers are recorded verbatim; they do not automatically become
  structured preferences. Confirm observations or add explicit preferences.
- Active conflict questions are answered by the homeowner to resume the graph;
  the sidebar directs both parties to that task instead of offering a second
  resolution action that would leave the graph paused.
- Designer constraints are entered as structured fields (category, applies-to,
  optional linked preference, declared incompatible values, statement,
  rationale, severity) and can be edited or withdrawn. A conflict is derived
  only when the designer explicitly lists an incompatible value that matches a
  confirmed preference; the system never estimates cost or feasibility itself.
  Changing attributes, constraints or conflicts clears stale approvals and
  marks the brief stale; the brief must be regenerated ("重新生成方案") before it
  can be approved again. Unresolved conflicts are never auto-resolved.
- The SQLite migrations are SQLite-specific.
