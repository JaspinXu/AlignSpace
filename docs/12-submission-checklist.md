# Submission and Readiness Checklist

Updated 26 September 2026. The organisers' final instructions (email to all four team members) ask for **one email** with the subject **`SMYA Final Submission - 8QFDUS2I`** containing: Team Code, Problem Statement, GitHub Repository URL, Business Proposal (PDF), Technical Document (PDF), Demo Video (YouTube or cloud URL preferred, MP4 where practical) and Deployment Evidence (URL or artifact). Deadline as briefed: **28 September 2026, 09:00 SGT**. The ready-to-send email is in [`docs/23-submission-kit.md`](23-submission-kit.md).

## Submission package (email format)

- [x] Team code: 8QFDUS2I — Four Wolf Kings (Chen Xiaoming, Xing Yiyuan, Xu Tengyang, Xu Zhaobin).
- [x] Problem statement: Design Inspiration (public category), with our one-paragraph framing in the email.
- [x] GitHub repository URL: <https://github.com/JaspinXu/AlignSpace> — public; `main` carries the submitted code; release `v1.1` (final submission package). The earlier `v1.0` release stays as the shortlisting snapshot.
- [x] Business Proposal (PDF): `docs/submission/AlignSpace-Business-Proposal.pdf` (10 pages), also a `v1.1` release asset. Source `business-proposal.html`; re-render with `python docs/submission/render_pdfs.py`.
- [x] Technical Document (PDF): `docs/submission/AlignSpace-Technical-Document.pdf` (10 pages), also a `v1.1` release asset.
- [ ] Demo video URL: recorded by the team; paste the YouTube (unlisted) or cloud link into the email and check it plays signed out.
- [x] Deployment evidence: <https://54.255.93.19.sslip.io>, `docs/evidence/deployment-snapshot-2026-09-26.txt`, `docs/evidence/e2e-live-run-2026-09-26.json` (19/19) and the 26 September entry in `docs/16`.
- [ ] Formal topic-selection record checked by the team (the organiser email already addresses the team by code).
- [ ] Owner trial results collected; external user/SME validation clearly distinguished. Neither PDF claims user results.

## Official alignment

- [x] Addresses Design Inspiration problem.
- [x] Working prototype shows agent decisions and human control.
- [x] SME relevance and pilot path are explicit (Business Proposal §02–§08).
- [ ] Security, responsibility, architecture, and impact have evidence.
- [x] AWS use is accurate (Technical Document §08, deployment snapshot).
- [ ] Public-resource/IP implications reviewed.
- [x] Submission planned before 28 September.

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
- [x] Clean deployment; reproducible tagged releases (`v1.0` shortlisting snapshot; `v1.1` final package with both PDFs and the demo MP4).

## Product and agent evidence

- [ ] Research sample sizes; no stereotype personas.
- [ ] P0/non-goals; metrics have baseline/definition/target/result.
- [x] Business assumptions exposed; pilot has cohort/metrics/stop criteria (Business Proposal §05–§08).
- [x] Each agent has goals/tools/inputs/outputs/forbidden actions (Technical Document §02).
- [x] Canonical state and transition owner clear (Technical Document §02–§03).
- [x] Adaptive decision visible; loops/retries/request counts bounded.
- [x] Human approval cannot be bypassed (tests + two-session E2E).
- [x] Model/prompt/evaluation versions recorded (model-run ledger, belief model version).

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
- [x] Claims labelled measured/source/assumption/hypothesis in both PDFs.
- [ ] Charts show denominators; links tested signed out.
- [ ] Repository/tag, demo URL/accounts, deck, video if required, architecture, evaluation, security/privacy, licenses, team info, receipt.

