# Delivery Roadmap and Backlog

The official build phase is 7–25 September 2026; final submission is 28 September. Preserve 26–27 September for packaging and recovery.

## Four roles (Public Category assumption)

- **Product/UX:** research, scope, workflow, prototype, story, acceptance.
- **AI/Backend:** schemas, orchestration, model integration, evaluation.
- **Frontend:** two-role app, accessibility, evidence/approval UI.
- **Cloud/Quality:** AWS, security, observability, test/release/demo.

Every critical change has a second-person review.

## 6 September — lock problem

Confirm category, deliverables, weights, pitch, AWS; recruit users; acquire lawful assets; agree scope/schema/metric/story.

Exit: no open decision that changes P0 architecture or story.

## Week 1, 7–11 September — prove risky loop

Three homeowner and two designer interviews; upload → extraction → correction slice; canonical schema/state; first 10 evaluation cases; threat model.

Exit: one real set becomes evidence-linked editable attributes.

## Week 2, 12–18 September — two-sided flow

Adaptive questions; designer constraints; conflict cards; orchestration; version/dual approval; 30 cases/red team; staging with logs, cost, deletion.

Exit: happy path and a failure path work end to end.

## Week 3, 19–25 September — validate/harden

Five paired tests; fix high severity; tune on development cases, keep holdout; demo dataset/manual fallback/reset; freeze P0 on 23rd; rehearse.

Exit: gates pass and demo succeeds three consecutive clean runs.

## Packaging, 26–28 September

- 26th: README, deployment, limitations, licenses, report.
- 27th: video if required; signed-out link check.
- 28th: submit early, retain receipt, tag release, freeze demo.

## Backlog

| ID | Story | Priority | Owner | Evidence |
|---|---|---:|---|---|
| P-01 | Consent/private upload | P0 | Cloud/Frontend | upload/deletion test |
| P-02 | Evidence-linked extraction | P0 | AI | labelled-case report |
| P-03 | Correct/confirm/reject | P0 | Frontend | usability pass |
| P-04 | Adaptive question | P0 | AI/Product | relevance/repetition |
| P-05 | Designer constraint review | P0 | Frontend | scripted flow |
| P-06 | Conflict card | P0 | AI/Frontend | seeded recall |
| P-07 | Version + dual approval | P0 | Backend | invariant tests |
| P-08 | Review/escalation | P0 | AI/Quality | red-team report |
| P-09 | Error/cost/latency metrics | P0 | Cloud | dashboard |
| P-10 | Fallback/reset | P0 | Quality | 3 rehearsals |
| P-11 | Reference retrieval | P1 | AI | rights/relevance |
| P-12 | Visual directions | P1 | AI/UX | preference test |
| P-13 | Chinese UI | P1 | Frontend | copy/layout review |
| P-14 | SME admin metrics | P2 | Product/Cloud | pilot feedback |

## Scope-cut order

Cut generated visuals, retrieval, multilingual UI, admin, then export styling. Never cut consent, evidence, correction, conflict visibility, approval integrity, or safety review.

## Daily rhythm

10-minute vertical-slice demo; midday smoke/eval; end-of-day decision log and deployable main; no P1 while a severity-1 P0 issue is open.

