# Verification report

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
