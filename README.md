# AlignSpace — Design Inspiration Agents

AlignSpace helps a homeowner and an interior designer turn references, preferences and practical constraints into one versioned living-room brief. The hackathon team is **Four Wolf Kings — 8QFDUS2I**.

## Try it

The homepage now includes a colourful Singapore discovery experience: browse seven sourced renovation case studies, filter by home type or published cost, save up to six homes, and compare up to three. The budget guide separates 2026 HDB ranges from 2025 condo ranges. Saved source links can be added to a new brief with consent; they do not confirm preferences or set the living-room budget. See [Singapore discovery notes](docs/19-singapore-discovery.md) for sources and data maintenance.

Run the app locally using the setup below, then open http://127.0.0.1:8010.

1. Choose **Start my room brief**, or **Try a guided sample** for labelled sample notes.
2. Answer a few homeowner questions. Optionally upload an image you have permission to use and explain which elements you like.
3. Choose **Suggest preferences from notes**, then accept or reject each suggestion. Confirming a new value replaces the previous confirmed value for that dimension, retaining its history.
4. Select **Invite my designer** and share the private, single-use link. For solo testing, open it in another browser profile or private window. The same session cannot claim both roles.
5. The designer reviews layout, maintenance and constraints. Use **Refresh shared changes** after the other person edits.
6. Both participants approve the same brief from their respective sessions. Export JSON or Print / Save PDF. Any content edit invalidates approvals.

Invitations expire after 24 hours. Browser sessions are possession-based access, not verified personal identity. Clearing cookies loses access; recovery and account management are not implemented. Existing pre-authentication local demo projects are not automatically exposed to new sessions.

## What works today

| Capability | Implementation |
|---|---|
| Reference images | Decoded, resized, metadata removed, stored privately and displayed only to project members |
| Reference understanding | Real model-backed **note** analysis through the competition gateway; every result stays proposed until human confirmation |
| Image understanding | Adapter implemented, **disabled** pending a working vision endpoint; current competition gateway image probe returned `NO_IMAGE` |
| Interview | Deterministic information-gain selection from a controlled question bank, filtered by participant role |
| Candidate directions | 12 illustrative catalogue records; must-avoid filtering, budget-aware ordering, explicit match/trade-off explanations |
| Alignment | Controlled preference replacement, constraint checks, unresolved-risk blockers and versioned approvals |
| Collaboration | Separate homeowner/designer browser sessions, project isolation, single-use invitations |
| Reliability | SQLite transactions, stale-version rejection, per-project and global request caps, limited retry, explicit offline fallback |
| Evidence | Audit events, model run status, model/prompt version, latency, token counts where the provider returns them |

Workflow messages are deterministic coordination messages, not autonomous LLM-to-LLM conversations. Candidate budgets are illustrative, not quotes. Confidence is an uncalibrated model estimate; offline rules use 0 to indicate no calibrated estimate. There is no verified business ROI yet.

## Local setup

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
# Copy .env.example to .env and fill in server-side credentials.
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Open http://127.0.0.1:8010. `.env` is loaded locally, with real environment variables taking precedence. It is ignored by Git and Docker build context. Never place keys in frontend JavaScript, screenshots, or the submitted repository.

Without credentials, set `ALIGNSPACE_ANALYSIS_MODE=offline`. Offline rules only read explicit positive note keywords. They do not understand arbitrary language or image pixels. Failed model requests never silently become offline results: select the offline button explicitly.

### Optional image API

Fill these **in the backend .env**, not in the browser:

```dotenv
ALIGNSPACE_ALLOW_IMAGES=true
VISION_API_FORMAT=openai
VISION_GATEWAY_URL=https://your-vision-provider.example/v1
VISION_GATEWAY_API_KEY=your-private-key
VISION_MODEL=your-vision-model
```

Supported formats: `openai` compatible chat completions, `anthropic` messages, `ollama` chat. The vision endpoint and credentials are independent of the text gateway. Perform a known-image capability check before enabling. Adapter tests use mocked providers and do not certify a real provider.

### Request controls

Defaults: 20 analysis requests per project, 100 globally per rolling 24 hours, 10-second project cooldown. Reservations persist across restarts and failed calls count. Each request uses at most 10 references and makes at most two HTTP attempts; 401/403 and transport timeouts are not automatically retried. These caps bound request count, not dollar spend. Upstream generation limits and token reporting depend on the gateway. Check the team's Slack token report as the source for quota.

Model calls run outside the SQLite write transaction. Results are committed only if the original state version still matches. Malformed or unknown-schema output never changes preferences.

## Deploy

For assessment, run the application on one organiser-provided **medium Lightsail instance**. Transfer the code or pull it from Git, install dependencies, configure the backend `.env`, and start the application. The repository does not require a particular domain or web proxy.

See [deployment runbook](docs/15-deployment-runbook.md) for setup and verification. For local Docker use, copy `.env.example` to `.env`, then run `docker compose up --build` (trial port 8000).

## Verify

```sh
python -m pytest -q
```

Tests cover approval content hashes, stale edits, negation, preference replacement, budget/avoid filtering, project isolation, role spoofing, invitation replay, consent, image decoding, request caps and model schema boundaries. The [verification report](docs/16-verification-report.md) distinguishes automated evidence from pending user trials.

## Competition delivery

- Shortlisting: **28 September 2026, 09:00 SGT**, in `#submission`.
- Required: Team Code, Project Name, judge-accessible GitHub URL, video URL, PDF write-up, deployment evidence/URL.
- Do not upload the video directly into the submission channel. Briefing says 30 minutes; precise interpretation remains unconfirmed.
- Finalists: **10 October 2026, 08:30 SGT**, face-to-face demo; use `#final-submission` for finalist artifacts.
- AWS allocation is approximately USD 100 per team, shared across Lightsail and inference. Use a single medium instance; do not copy the starter kit's second-instance example.
- Kiro redemption deadline was 11 September; redeemed credits are valid through 31 October.

See [official context](docs/00-official-context.md) and [submission checklist](docs/12-submission-checklist.md). Reconcile later organiser notices before submission.

## Scope and remaining evidence

The current release is a trial prototype. No licensed room reference set, external designer evaluation, measured time-saving study, account recovery, deletion/retention automation or production-grade identity verification has been completed. Critical professional constraints stay blocked; the application cannot certify professional safety. See the [user trial worksheet](docs/17-user-trial.md) to collect evidence without representing hypotheses as outcomes.

Architecture and research documents under `docs/` include future design plans. Use this README and the verification report as the current implementation record.
