# Submission and Readiness Checklist

Updated 21 September 2026. Initial submission is due **28 September, 09:00 SGT** in `#submission`. Required fields are now known; scoring weights and the exact interpretation of the 30-minute video remain open.

## Submission package

- [x] Team: Four Wolf Kings — 8QFDUS2I.
- [x] Project: AlignSpace — Design Inspiration Agents.
- [x] Judge-accessible GitHub repository URL: the repository is public (verified 21 September by anonymous clone), `main` carries the submitted code, and tag `v1.0` plus the published release sit on commit `4fb6ae4` (21 September): <https://github.com/JaspinXu/AlignSpace/releases/tag/v1.0>.
- [ ] Video viewing/download URL (do not upload the video to Slack). Captioned golden-path recording and narration script are ready (`docs/23-submission-kit.md`); team narration and upload pending.
- [ ] PDF write-up with problem, value, implementation and measured evidence. Draft generated: `docs/writeup/AlignSpace-writeup.pdf` (source `writeup.html`, re-render with `python docs/writeup/render_pdf.py`), 10 pages, published as a release asset: <https://github.com/JaspinXu/AlignSpace/releases/download/v1.0/AlignSpace-writeup.pdf>. Only the video URL row (line 51) and the trial results are still open — re-render and re-upload the asset (`gh release upload v1.0 docs/writeup/AlignSpace-writeup.pdf --clobber`) once they land.
- [x] Public Lightsail deployment URL: <https://54.255.93.19.sslip.io> (deployed 21 September, 19/19 live two-session checks). Re-check in a signed-out browser on submission day.
- [ ] Formal topic-selection record checked by the team.
- [ ] Owner trial results collected; external user/SME validation clearly distinguished.


## Official alignment

- [ ] Addresses Design Inspiration problem.
- [ ] Working prototype shows agent decisions and human control.
- [ ] SME relevance and pilot path are explicit.
- [ ] Security, responsibility, architecture, and impact have evidence.
- [ ] AWS use is accurate.
- [ ] Public-resource/IP implications reviewed.
- [ ] Submission planned before 28 September.

## Confirm

- [ ] Form URL/owner; repository visibility/license.
- [x] Mandatory fields recorded above; any file-size limits remain to be confirmed.
- [ ] Video/deck format, duration, accessibility.
- [ ] Pitch/Q&A timing and live-demo rules.
- [ ] Criteria/weights.
- [ ] Third-party model/library/data/generated-image/prior-work rules.
- [ ] AWS evidence requirements.
- [ ] Category/team/attendance details.

## Repository

- [x] README includes problem, value, flow, architecture, setup, demo, tests, limits, license.
- [x] `.env.example` placeholders only.
- [x] No secrets, tokens, private images, participant/customer data in history (scanned 18 September: no `.env`, database or key material ever committed).
- [x] Dependency and asset licenses/provenance documented (MIT `LICENSE` with third-party exclusions; Atelier and Getty attributions in `app/knowledge_data`).
- [x] Clean deployment; reproducible tagged release (`v1.0` on `4fb6ae4`, CI green, release published with the PDF and demo MP4).

## Product and agent evidence

- [ ] Research sample sizes; no stereotype personas.
- [ ] P0/non-goals; metrics have baseline/definition/target/result.
- [ ] Business assumptions exposed; pilot has cohort/metrics/stop criteria.
- [ ] Each agent has goals/tools/inputs/outputs/forbidden actions.
- [ ] Canonical state and transition owner clear.
- [x] Adaptive decision visible; loops/retries/request counts bounded.
- [x] Human approval cannot be bypassed (tests + two-session E2E).
- [ ] Model/prompt/evaluation versions recorded.

## Safety and technical

- [ ] Trust boundaries/data stores shown.
- [ ] Auth, encryption, rates, audit, deletion tested.
- [x] Injection, cross-project, malformed output, unsafe advice tested.
- [ ] No open critical finding.
- [ ] Manual fallback and kill switch.
- [ ] Observability excludes raw sensitive content.

## Demo and handoff

- [x] Synthetic/consented/licensed content.
- [ ] Three clean live runs; backup video/cached output.
- [ ] Claims labelled fact/finding/hypothesis/target/estimate.
- [ ] Charts show denominators; links tested signed out.
- [ ] Repository/tag, demo URL/accounts, deck, video if required, architecture, evaluation, security/privacy, licenses, team info, receipt.

