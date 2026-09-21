<div align="center">

<img src="docs/assets/readme/hero.webp" alt="AlignSpace: make &quot;I like this&quot; clear enough to design. A two-sided agent workspace for homeowners and interior designers." width="100%">

<h3>Turn "I like this" into one brief the homeowner and the designer both approve.</h3>

<p>A two-sided agent workspace for <b>Singapore homeowners and interior-design SMEs</b>.<br>
References, notes and practical constraints become one versioned living-room brief. AI suggestions stay proposals, conflicts stay visible, and approval is explicit.</p>

<p>
<img src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white" alt="Python 3.11">
<img src="https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI">
<img src="https://img.shields.io/badge/Storage-SQLite-003B57?logo=sqlite&logoColor=white" alt="SQLite">
<img src="https://img.shields.io/badge/LLM-Claude%20Sonnet%204.5-D97757?logo=anthropic&logoColor=white" alt="Claude Sonnet 4.5">
<img src="https://img.shields.io/badge/Deploy-AWS%20Lightsail-FF9900?logo=amazonaws&logoColor=white" alt="AWS Lightsail">
<a href="https://github.com/JaspinXu/AlignSpace/actions/workflows/ci.yml"><img src="https://github.com/JaspinXu/AlignSpace/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
<img src="https://img.shields.io/badge/UI-English%20%2F%20%E4%B8%AD%E6%96%87-6543ee" alt="English / Chinese">
<a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue" alt="MIT License"></a>
</p>

<p>
<a href="#quick-start"><b>Quick start</b></a> ·
<a href="#how-it-works"><b>How it works</b></a> ·
<a href="#the-agent-loop"><b>Agent loop</b></a> ·
<a href="#safety-and-evaluation"><b>Safety &amp; evaluation</b></a> ·
<a href="#deploy"><b>Deploy</b></a> ·
<a href="docs/writeup/AlignSpace-writeup.pdf"><b>Write-up (PDF)</b></a> ·
<a href="README.zh-CN.md"><b>简体中文</b></a>
</p>

</div>

A reference image does not say whether someone likes its oak, its lighting, its layout or the whole room. The same word ("warm", "hotel-like") means different things to a homeowner and a designer, and the misunderstanding usually surfaces at the first concept as another revision. AlignSpace focuses on **agreement, not image generation**: it keeps one explicit shared state, asks the question that removes the most uncertainty, and releases the brief only when both people approve the same version.

> [!NOTE]
> Built by **Four Wolf Kings (8QFDUS2I)** for the NUS-ISS *Show Me Your Agents* hackathon, Design Inspiration problem (Public category). Trial prototype: demo data is synthetic, and no time-saving or ROI result is claimed yet. AlignSpace is a requirements-alignment aid, not construction, structural, electrical, regulatory or pricing advice.

<p align="center">
<img src="docs/assets/readme/demo.gif" alt="Golden-path demo: homeowner answers, designer joins by private link, a constraint opens a conflict, both approve the same brief" width="92%">
</p>
<p align="center"><sub>Two browser sessions, synthetic data, offline note rules, sped up about 3×. Full captioned recording: <code>python scripts/e2e_golden_path.py &lt;url&gt; video</code>.</sub></p>

## Highlights

<table>
<tr>
<td width="33%" valign="top"><b>Real Singapore inspiration</b><br>Browse 57 attributed HDB, condo and landed homes, compare style cues and save up to six. Saved homes are weak evidence and never count as confirmed preferences.</td>
<td width="33%" valign="top"><b>Suggestions, not decisions</b><br>Notes are read through the organiser's Claude Sonnet 4.5 API, or by explicit offline keyword rules. Every result is labelled <i>proposed</i> until the homeowner confirms or rejects it.</td>
<td width="33%" valign="top"><b>One question at a time</b><br>8 core decisions and 55 conditional follow-ups. The next question is the one with the largest expected uncertainty reduction for that person's role, in ten-question rounds you can pause.</td>
</tr>
<tr>
<td width="33%" valign="top"><b>Suggested next step</b><br>An evidence-weighted belief per decision and a constrained policy that picks one safe action per role: ask, confirm, compare, resolve, approve or invite. The weights are hand-set and shown in the UI.</td>
<td width="33%" valign="top"><b>Two sides, one state</b><br>The designer joins from a private single-use link and owns layout, care and constraints. A constraint that contradicts a confirmed preference opens a conflict and blocks approval.</td>
<td width="33%" valign="top"><b>Explicit approval</b><br>Both people approve the same SHA-256 content hash from their own sessions, and any later edit clears both approvals. Export the brief as schema-valid JSON or print it to PDF.</td>
</tr>
<tr>
<td width="33%" valign="top"><b>Grounded references</b><br>Local BM25 over 22 attributed design-handbook excerpts plus Getty AAT terminology. Retrieval abstains on no overlap and skips excerpts that mention must-avoid items.</td>
<td width="33%" valign="top"><b>English / 中文</b><br>A persistent language switch covers the interface, the questions, the 28 housing types and bilingual search.</td>
<td width="33%" valign="top"><b>Guardrails by default</b><br>Prompt-injection resistant parsing, role-bound sessions, stale-write rejection, bounded model calls and an audit trail for every change.</td>
</tr>
</table>

## How it works

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/workflow-dark.png">
  <img src="docs/assets/readme/workflow-light.png" alt="Collect, Suggest, Ask, Align, Approve: a five-step loop between homeowner, agent and designer" width="100%">
</picture>

<p align="center">
<img src="docs/assets/readme/tour.webp" alt="Four screens: discover Singapore homes, adaptive question with suggested next step, designer constraint opening a conflict, and the dual-approved brief" width="100%">
</p>

| Step | Homeowner | Designer | Agent |
| --- | --- | --- | --- |
| Collect | Goals, must-avoid items, notes, saved homes | — | Stores evidence with source and consent |
| Suggest | Confirms or rejects each suggestion | — | Proposes attributes from notes; never confirms |
| Ask | Style, mood, colour, material, lighting, function | Layout, maintenance | Picks the highest-value question per role |
| Align | Revises a preference if needed | Adds constraints with rationale and severity | Opens conflicts, blocks approval, never picks the trade-off |
| Approve | Approves in own session | Approves in own session | Binds both approvals to one content hash |

## The agent loop

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/architecture-dark.png">
  <img src="docs/assets/readme/architecture-light.png" alt="Homeowner and designer sessions reach an orchestrator that alone writes the Project Design State; agents read the state and propose" width="100%">
</picture>

<table>
<tr>
<td width="42%" valign="top"><img src="docs/assets/readme/belief-panel.webp" alt="Suggested next step and per-decision clarity panel" width="100%"></td>
<td valign="top">

**Observe → estimate → decide → check → stop.**

1. **Observe.** Answers, notes, saved homes and constraints update one versioned Project Design State. Stale writes are rejected with HTTP 409.
2. **Estimate.** Each decision has an advisory Dirichlet belief. Evidence is weighted by quality (explicitness, reliability, dispersion). A human confirmation outweighs any machine signal, repeated evidence counts 1/k, and must-avoid items and constraints mask options first.
3. **Decide.** The next question maximises expected uncertainty removed × impact. A constrained policy ranks safe actions by uncertainty reduction, progress, confirmation and acceptance minus interruption cost. Clicks and dwell time are never rewards.
4. **Check.** Coverage, conflicts and blockers move the stage through Explore, Clarify, Focus and Commit.
5. **Stop.** The brief is released only when both roles approve the same hash.

The belief never confirms anything and is excluded from the signed brief. Every suggestion and what happened next is logged, so a policy can later be trained on real outcomes. Details: [docs/22](docs/22-bayesian-belief-and-next-action.md).

</td>
</tr>
</table>

| Layer | Technology and role |
| --- | --- |
| Web app | Vanilla JavaScript, English / Chinese, strict CSP, no keys in the browser |
| API and orchestrator | FastAPI, Pydantic; membership and role checks, typed actions, optimistic versioning, audit events |
| State | SQLite (WAL), one JSON design state per project, SHA-256 content hash for approvals |
| Reasoning | Adaptive question selection, evidence-weighted belief, constrained next-step policy, conflict and readiness checks |
| Model | Organiser Claude Sonnet 4.5 JSON API behind an adapter; schema-validated, bounded, never silently replaced by offline rules |
| Knowledge | Local BM25 over attributed handbook excerpts, Getty AAT terms, 57 attributed Singapore homes |
| Hosting | One AWS Lightsail medium instance, systemd service behind Caddy (HTTPS) |

<p align="center">
<img src="docs/assets/readme/bilingual.webp" alt="The same workspace in English and Chinese" width="100%">
</p>

## Quick start

Requires **Python 3.11**.

```bash
git clone https://github.com/JaspinXu/AlignSpace.git
cd AlignSpace
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                    # PowerShell: Copy-Item .env.example .env
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Open <http://127.0.0.1:8010>. Without credentials, set `ALIGNSPACE_ANALYSIS_MODE=offline`: offline rules read only explicit positive keywords in notes, and the UI says so.

### Try it in two minutes

1. Choose **Start my room brief**, or **Try a guided sample** for labelled sample notes.
2. Add goals, a must-avoid item and a note, then **Suggest preferences from notes**. Confirm or reject each suggestion.
3. Answer the questions. The side panel shows the suggested next step and how clear each decision is.
4. **Invite my designer** and open the link in a private window: a session cannot hold both roles.
5. As the designer, answer layout and care, then add a constraint that contradicts a confirmed preference and resolve the conflict.
6. Approve from both sessions, then export JSON or print to PDF. Edit anything afterwards and both approvals disappear.

<details>
<summary><b>Configuration</b></summary>

Keys belong in the server-side `.env` only (ignored by Git and the Docker context). Real environment variables take precedence.

| Variable | Purpose |
| --- | --- |
| `LLM_GATEWAY_URL`, `LLM_GATEWAY_API_KEY`, `LLM_MODEL` | Organiser JSON API for note analysis |
| `ALIGNSPACE_ANALYSIS_MODE` | `gateway` or `offline` |
| `ALIGNSPACE_ALLOW_IMAGES` | Enable image analysis (off until a vision endpoint passes a known-image check) |
| `VISION_API_FORMAT`, `VISION_GATEWAY_URL`, `VISION_GATEWAY_API_KEY`, `VISION_MODEL` | Optional vision provider: `openai`, `anthropic` or `ollama` format |
| `ALIGNSPACE_PROJECT_RUN_LIMIT`, `ALIGNSPACE_DAILY_RUN_LIMIT` | Analysis caps (defaults 20 per project, 100 per rolling day; 10 s cooldown) |
| `ALIGNSPACE_DB_PATH`, `ALIGNSPACE_UPLOAD_DIR` | SQLite file and private upload folder |
| `ALIGNSPACE_SECURE_COOKIES` | `true` when served over HTTPS |

Each analysis uses at most 10 references and two HTTP attempts. 401/403 errors and timeouts are not retried blindly. Model calls run outside the database transaction, and results are committed only if the state version still matches.

</details>

## Safety and evaluation

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/evidence-dark.png">
  <img src="docs/assets/readme/evidence-light.png" alt="77 of 77 tests, 19 of 19 two-session checks, 0 console errors, 7 of 7 earlier live checks, and the list of guardrail checks" width="100%">
</picture>

| Risk | Control |
| --- | --- |
| Prompt injection | Notes, image text and retrieved text are evidence only; model output is parsed against a closed vocabulary and can only create *proposed* attributes |
| Over-automation | People confirm preferences, resolve conflicts and approve; critical constraints require professional review |
| Cross-project access | Possession-based HttpOnly SameSite=Strict sessions, per-project membership, role bound at invitation claim, cross-origin writes rejected |
| Replay and races | Single-use 24-hour invitations stored as digests; optimistic versioning; approvals bound to a content hash |
| Privacy | Consent required; images decoded, resized, metadata-stripped and served only to project members |
| Runaway cost | Per-project and global request caps, cooldown, bounded retries, explicit offline mode |

```bash
python -m pytest -q                                   # 77 tests
python scripts/simulate_belief.py                     # belief recovery on synthetic data
# Two-session browser run (synthetic data, offline mode), writes docs/evidence/
ALIGNSPACE_ANALYSIS_MODE=offline ALIGNSPACE_DB_PATH=/tmp/e2e.db python -m uvicorn app.main:app --port 8011
python scripts/e2e_golden_path.py http://127.0.0.1:8011
```

Every push runs the same checks in GitHub Actions: ruff, the test suite, the belief simulation and a schema check on the recorded brief.

Evidence: [verification report](docs/16-verification-report.md) · [run results](docs/evidence/e2e-run.json) · [example approved brief](docs/evidence/approved-brief.example.json) · [evaluation plan](docs/08-evaluation-plan.md).

## Deploy

The assessed build runs on the organiser-provided AWS Lightsail medium instance. From Git Bash, macOS or Linux, with the change committed:

```bash
scripts/deploy_lightsail.sh ubuntu@<PUBLIC_IP> ~/.ssh/alignspace-lightsail.pem   # https://<PUBLIC_IP>.sslip.io
```

The script ships `git archive HEAD` only (no local database, uploads or secrets). It installs a versioned release, keeps `.env` and data between releases, runs a hardened systemd service behind Caddy, checks `/health`, and rolls back if the check fails. Open ports 80 and 443 in the Lightsail firewall first. See the [deployment runbook](docs/15-deployment-runbook.md). For local Docker: `docker compose up --build` (port 8000).

## Current limits

| Area | Status |
| --- | --- |
| User evidence | Owner trial pending; no external homeowner–designer study, time saving or ROI result yet |
| Image understanding | Adapter ready but disabled: the organiser gateway returned `NO_IMAGE` on a known-image probe. Notes are analysed; images are stored privately and displayed |
| Belief and policy | Hand-set, uncalibrated weights; a constrained bandit, not a trained RL policy |
| Identity | Possession-based browser sessions; no accounts or recovery |
| Scope | Living room only; single-instance SQLite |

<details>
<summary><b>Project structure</b></summary>

```text
app/
  main.py              FastAPI app, session middleware, typed endpoints
  engine.py            Design state, adaptive questions, conflicts, readiness, approvals
  belief.py            Evidence-weighted belief and constrained next-step policy
  gateway.py           Organiser LLM / vision adapters, bounded and schema-validated
  interview.py         55 conditional detail questions (EN / 中文)
  knowledge.py         BM25 retrieval over attributed handbook excerpts
  discovery.py         Singapore home previews (parse-only, no script execution)
  access.py, store.py  Memberships, invitations, SQLite store and audit
  static/              Web app, styles, locale data
schemas/               Design brief JSON schema
scripts/               Deploy, E2E run, belief simulation, locale build
deploy/                systemd unit and Caddyfile
tests/                 77 unit, API and regression tests
docs/                  Product, agent, safety, evaluation, deployment and submission docs
  evidence/            E2E results, screenshots, example brief
  writeup/             Write-up source and PDF
  assets/readme/       README figures
```

</details>

<details>
<summary><b>Documentation map</b></summary>

Documents under `docs/` include design proposals that are **not** what runs today — for example [docs/05](docs/05-technical-architecture.md) describes a serverless AWS target, while the assessed build is a single Lightsail instance. This README and the [verification report](docs/16-verification-report.md) are the current implementation record.

| Topic | Documents |
| --- | --- |
| Problem and scope | [Official context](docs/00-official-context.md) · [Product requirements](docs/01-product-requirements.md) · [Business case](docs/10-business-case.md) |
| Experience | [Research plan](docs/02-user-research-plan.md) · [Experience spec](docs/03-experience-spec.md) · [UI design](docs/18-ui-design.md) · [Singapore discovery](docs/19-singapore-discovery.md) |
| Agents and data | [Agent system design](docs/04-agent-system-design.md) · [Architecture](docs/05-technical-architecture.md) · [Contracts](docs/06-data-and-api-contracts.md) · [Belief and next step](docs/22-bayesian-belief-and-next-action.md) |
| Knowledge and language | [Grounded design knowledge](docs/20-grounded-design-knowledge.md) · [Adaptive interviews and languages](docs/21-adaptive-interviews-and-languages.md) |
| Safety and evaluation | [Safety and privacy](docs/07-safety-privacy-security.md) · [Evaluation plan](docs/08-evaluation-plan.md) · [Verification report](docs/16-verification-report.md) · [User trial](docs/17-user-trial.md) |
| Delivery | [Roadmap](docs/09-delivery-roadmap.md) · [Decision log](docs/13-decision-log.md) · [Assets register](docs/14-data-and-asset-register.md) · [Deployment runbook](docs/15-deployment-runbook.md) · [Demo and pitch](docs/11-demo-and-pitch.md) · [Submission checklist](docs/12-submission-checklist.md) · [Submission kit](docs/23-submission-kit.md) |

</details>

<details>
<summary><b>Hackathon delivery</b></summary>

- Shortlisting: **28 September 2026, 09:00 SGT**, posted in `#submission`: team code, project name, GitHub URL, video URL, PDF write-up, deployment evidence or URL.
- Finale: **10 October 2026, 08:30 SGT**, face-to-face demo; finalist updates in `#final-submission`.
- Assessed build on one organiser Lightsail medium instance, using the organiser's inference allocation.
- Post template, organiser questions, video script and link check: [submission kit](docs/23-submission-kit.md).

</details>

## Content and license

Code is released under the [MIT License](LICENSE). Design-handbook excerpts, Singapore listing metadata and linked images, and Getty AAT terms keep their original owners' terms: they are attributed and linked for discussion, not relicensed (see the end of `LICENSE`). All screenshots and demo data in this repository are synthetic.
