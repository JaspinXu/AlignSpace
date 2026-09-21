# Verification report

## Live deployment — 21 September 2026

- **Public URL:** <https://54.255.93.19.sslip.io> on the organiser-provided Lightsail medium instance (Ubuntu 24.04, ap-southeast-1, 4 GB / 2 vCPU / 80 GB). Released commit `a1c8bd0` via `scripts/deploy_lightsail.sh`; releases are versioned under `~/alignspace/releases/<sha>` with `.env` and data in `~/alignspace/shared`.
- **Serving path:** Caddy on 80/443 in front of uvicorn bound to 127.0.0.1:8010; Let's Encrypt certificate issued by TLS-ALPN, valid to 20 December 2026; `ALIGNSPACE_SECURE_COOKIES=true`. Both `alignspace.service` and `caddy.service` are enabled, so they return after a reboot. The service runs with `ProtectSystem=strict`, `ProtectHome=read-only`, a single writable data path and `UMask=0077`.
- **Two-session run against the live URL** (`ALIGNSPACE_E2E_BROWSER=msedge python scripts/e2e_golden_path.py https://54.255.93.19.sslip.io`): **19/19 checks passed**, zero console errors, 18.6 s. Result recorded in `docs/evidence/e2e-live-run.json`. This exercised the golden path plus injection, invitation replay, cross-project read, stale edit and role-spoof checks on the deployed build with synthetic data and offline note rules (no model quota used).
- **Spot checks:** `/health` returns ok over HTTPS from outside the instance; `POST /api/demo/start` returns 201; the previous deployment's configuration, `.env` and database were backed up on the instance under `~/alignspace-backup-20260921/` before the switch, and the new release starts from an empty database.
- **Live model check (21 September, 09:05 UTC):** `/api/runtime` reports `analysisMode: gateway`, and one real analysis run on the public site returned five proposed observations from a single homeowner note. The recorded usage row names the model `global.anthropic.claude-sonnet-4-5-20250929-v1:0`, prompt `reference-observations-v3-grounded`, three retrieved knowledge chunks, one attempt, 7,476 ms, 1,873 input / 426 output tokens. The note deliberately contained none of the option labels, so the offline keyword rules could not have produced those observations; each arrived as `proposed` with a quoted source span. Image analysis remained disabled. Recorded in `docs/evidence/gateway-live-check.json`.
- **Analysis caps on the instance (21 September):** now that the URL is public, `~/alignspace/shared/.env` sets `ALIGNSPACE_PROJECT_RUN_LIMIT=20` and `ALIGNSPACE_DAILY_RUN_LIMIT=40` (previously the 100/day default). Service restarted; `alignspace` and `caddy` both active, `/health` ok locally and over HTTPS from outside, `analysisMode` still `gateway`.

## Update — 18 September 2026

- **Automated tests:** 77 passed (`python -m pytest -q`) on Linux and on the owner's Windows machine (Python 3.11). New since 13 September: advisory belief and suggested next step (`tests/test_belief.py`).
- **Two-session end-to-end run** (`scripts/e2e_golden_path.py`, Chromium, separate homeowner and designer browser contexts, synthetic data, offline analysis mode): **19/19 checks passed**, zero console errors. Result: `docs/evidence/e2e-run.json`; screenshots in `docs/evidence/screenshots/`; exported brief `docs/evidence/approved-brief.example.json` validates against the schema. Checks cover: injected instruction in a note not executed; must-avoid item never proposed; suggestions start unconfirmed; next step suggests inviting the designer; designer role from single-use invitation; designer constraint opens a conflict and blocks approval; designer is pointed to resolve it; readiness after human resolution; homeowner cannot approve as designer; dual approval on one content hash; post-approval edit clears approvals; invitation replay rejected; another session cannot read the project; stale edit rejected (409); role spoofing rejected; decision log recorded; duplicate suggestion hidden after confirmation.
- **Belief simulation** (`scripts/simulate_belief.py`, synthetic): top-1 recovery 0.71–0.73 vs 0.68–0.70 for vote counting over three seeds. Method check only.
- **Real saved projects** (copy of the local database, 10 projects): every project receives a sensible next step for each role after the fallback fixes.
- **Deployment script:** instance-side steps exercised in a container with stubbed systemd; not yet run on the Lightsail instance. The live deployment below predates the belief layer.

Pending: live deployment of the current release and a signed-out URL check; owner trial (`docs/17`); any external homeowner/designer session.

# Verification report — 13 September 2026

## Automated evidence

- Python suite: 51 tests passed after the visual discovery and alignment-schema update. Covers versioned approvals, stale concurrent model results, conflicting preferences, negation, constraints, source preview handling and avoid filtering, project isolation, role spoofing, invite replay, consent, actual image decoding, quotas and model output validation.
- Vision adapters for OpenAI-compatible, Anthropic and Ollama formats pass mocked contract tests; this does not demonstrate live image capability.
- Frontend JavaScript syntax checked with Node. Playwright browser checks exercised source expansion and the shared brief at desktop and 390px mobile widths, with zero console errors. Local screenshots: `output/playwright/grounded-knowledge.png` and `output/playwright/grounded-brief-mobile.png`.
- Real competition gateway text inference returned proposed light oak and light neutral preferences from a synthetic note while excluding disliked marble. One observed call took 3,203 ms and reported 393 input / 144 output tokens. This is one smoke test, not a performance benchmark.
- A synthetic known-image probe returned NO_IMAGE. Image inference remains disabled; note analysis works and reference images can be displayed privately.

Live browser checks confirmed the Japandi search returned 11 previews with a link to the complete source selection, then saved a result, compared two images and imported the saved reference into a new brief. The source CDN redirects some images through `api-neo.qanvast.com`; this specific host is now allowed by the image policy. A fresh browser run reported zero console errors. Mobile review used a 390px viewport.

New knowledge checks cover bilingual source retrieval, unsupported-query abstention, source revision identity, AAT broader mapping, citation snapshots and matching approval hashes. This change has not yet been deployed; the recorded live gateway observations belong to the earlier prompt version.

## Deployed checks

The application was tested on the supplied Ubuntu Lightsail instance. These results record the earlier deployment test; instance-specific networking and service configuration are not part of the repository's setup requirements.

Seven live checks passed using separate browser-equivalent HTTP sessions and synthetic project data: Secure cookie; project isolation; invitation replay rejection; role spoof rejection; distinct dual approvals; content revision invalidating approvals; service restart preserving state and access. Local check results are in ignored tmp/deployment-checks.json.

Browser trial confirmed guided sample creation and real note suggestions shown as proposed, with an explicit reminder that notes, not image pixels, are analysed.

## Evidence still needed

No authorised room-image dataset or independent designer study was supplied. The owner will run the trial worksheet in docs/17-user-trial.md. No time savings, satisfaction score or business ROI is claimed. This prototype does not verify professional construction constraints or provide account recovery.
