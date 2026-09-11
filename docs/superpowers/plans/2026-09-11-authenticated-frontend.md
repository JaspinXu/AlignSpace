# Authenticated Frontend Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans. Work through the deliverables below; independent frontend files can be implemented alongside backend work using the fixed contracts here.

**Goal:** Two real accounts register, share a project by code, and complete the existing fixture-based alignment workflow through a Chinese React application.

**Architecture:** FastAPI owns accounts, revocable sessions, project membership and workflow state. React/Vite uses same-origin API calls, an in-memory access token and an HttpOnly refresh cookie. SQLite stores account and project records in a new local database.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Argon2id, PyJWT; React, TypeScript, Vite, Vitest, Playwright.

## Global Constraints

- First version: email/password registration, login, logout; no email verification or password recovery.
- JWT access lifetime 15 minutes; absolute session lifetime 7 days; refresh rotation and immediate session revocation.
- Password length 15–128 characters. Never trim passwords or log credentials.
- Project join codes: 12 unambiguous random characters, 24 hours, one successful use, revocable by replacement.
- One homeowner and one distinct designer per project; server resolves role from membership.
- Keep raw tokens out of localStorage; HttpOnly cookie and validated Origin on auth mutations.
- Frontend labels fixture-based analysis honestly; no real image upload or invented evidence.
- No cloud publication or GitHub push.

## API contract for parallel implementation

Auth requests are plain JSON, not workflow envelopes:

```ts
type User = { id: string; email: string; emailVerified: false };
type AuthResponse = { accessToken: string; user: User };
// POST /v1/auth/register, /login: {email,password} -> AuthResponse
// POST /v1/auth/refresh: no body -> AuthResponse, rotates refresh cookie
// POST /v1/auth/logout: no body -> 204, revokes session
// GET /v1/auth/me: Bearer -> User
type Project = {
  id: string; roomType: string; budgetBand: string; consent: boolean;
  status: string; stateVersion: number;
  assets: {id:string; fixtureId:string; mediaType:string; sizeBytes:number}[];
  role: 'homeowner'|'designer'; designerJoined: boolean;
};
// GET /v1/projects -> Project[]
// POST /v1/projects {roomType,budgetBand,consent} -> Project (201)
// POST /v1/projects/join {code:string} -> Project
// POST /v1/projects/:id/join-code -> {code:string,expiresAt:number}
// GET /v1/projects/:id/state -> {
//   project: Project, projectState: existing ProjectState,
//   pendingQuestion: Question|null
// }
```

Use existing workflow response schemas and routes. Frontend reads src/alignspace/agents/homeowner.py, workflow/graph.py, and tests/conftest.py for the supported answer payloads; it must not invent free-text parsing. Backend errors retain code/message/correlationId/recoverable/details. Add a shared client mapping for new auth errors.

## Task 1: Auth and membership backend (main agent)

**Files:** create src/alignspace/auth/{config,models,service,routes}.py, src/alignspace/application/membership.py, tests/api/test_auth.py, tests/api/test_membership.py; modify main.py, api/dependencies.py, project routes/resources, persistence database initialization, pyproject.toml, legacy test fixtures.

- [ ] Write failing API tests first: register establishes session, case-insensitive duplicate rejects, wrong password fails, Origin rejects, forged identity headers fail.
- [ ] Implement Argon2id hashes and strict JWT validation. Rotate refresh tokens transactionally, retain consumed token digests for reuse detection, and check session validity on access.
- [ ] Add persistent fixed-window throttling with atomic updates; no raw identities in throttle keys.
- [ ] Add account tables idempotently at startup via versioned migration; preserve old fixture database by changing default database filenames.
- [ ] Add real current-user dependency, project role lookup, and deny unsupported role writes. Legacy test identity injection exists only in tests.
- [ ] Test expiry, replay, logout, cross-project denial, one-use and concurrent code redemption; implement membership endpoints and full-state reads.
- [ ] Run focused tests, then the full backend suite and Ruff; commit only backend files.

Example behavioral assertion:

```python
result = client.post('/v1/auth/register', json={
    'email': 'Owner@example.com', 'password': 'a long test password'
}, headers={'Origin': 'http://localhost:5173'})
assert result.status_code == 201
access = result.json()['accessToken']
headers = {'Authorization': f'Bearer {access}'}
assert client.get('/v1/projects', headers=headers).json() == []
client.post('/v1/auth/logout', headers={'Origin': 'http://localhost:5173'})
assert client.get('/v1/projects', headers=headers).status_code == 401
```

Validation: `uv run pytest -q`, `uv run ruff check src tests`.

## Task 2: Frontend application (bounded worker)

**Files:** frontend/package.json, lockfile, index.html, vite.config.ts, tsconfig files, src/api.ts, src/types.ts, src/App.tsx, src/auth/*, src/projects/*, src/workflow/*, src/styles.css, unit tests. Own frontend only, excluding e2e directory and playwright config.

- [ ] Scaffold React/TypeScript/Vite and scripts for dev, build, test; proxy /v1 to configurable local backend.
- [ ] Build a typed API client. Access token stays in memory; request credentials include cookie. One refresh retry per 401. Serialize refresh in-tab and across tabs with Web Locks. Notify tabs of logout with BroadcastChannel.
- [ ] Implement auth forms with native email/autocomplete support and explicit no-password-recovery copy.
- [ ] Implement project listing, creation (unticked consent required for analysis), code generation and joining, and reloadable URL navigation.
- [ ] Implement project work area: role-specific task, shared state sidebar, sample cards, question controls with existing structured payload, editable attributes, constraints/conflicts, brief editing and dual approval.
- [ ] Preserve inputs on 409; refetch state and require a new deliberate submit. Retry ambiguous network writes with the same key/body.
- [ ] Refresh on focus and visible waiting every five seconds; clean up polling on navigation.
- [ ] Test client session recovery, logout, network retry/409 and role-sensitive UI; run build and tests, report changed files and commands.

Example client behavior test:

```ts
// A protected request receives 401, refresh succeeds, retry uses the new
// access token; a second 401 ends the session rather than looping.
expect(protectedAttempts).toBe(2);
expect(refreshAttempts).toBe(1);
```

Visual direction: warm off-white background, dark olive headings, restrained terracotta actions, calm readable cards, strong typography, a persistent task/status hierarchy. No stock imagery is needed. Responsive, labelled fields and visible keyboard focus.

Validation: `npm run build`, `npm test`.

## Task 3: Integration, browser acceptance and runbook (main agent)

**Files:** frontend/e2e/auth-workflow.spec.ts, frontend/playwright.config.ts, README.frontend.md, README.backend.md, .gitignore, local startup helper if needed.

- [ ] Start auth backend with an ephemeral secret and new development database; start Vite on loopback.
- [ ] Add Playwright acceptance using two isolated browser contexts: register, create, join, restore after reload, questions/preferences, constraints, conflict resolution, same-version approvals, logout.
- [ ] Add negative browser case for stale edits and preservation of input.
- [ ] Inspect desktop and mobile screenshots and fix clipping/contrast/empty-state problems.
- [ ] Document exact setup, secret generation without printing, dev Origin/Cookie settings, fixture limits, tests and current operational boundaries.
- [ ] Review complete changes for auth bypass, concurrent joins and incorrect approval handling; fix concrete findings and rerun covering tests.
- [ ] Commit verified local work, retain feature branch for user integration choice.

Validation: full pytest suite, Ruff, frontend build/unit tests, Playwright browser acceptance. Final report distinguishes real accounts from fixture AI and gives the local runbook.
