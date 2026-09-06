# Safety, Privacy, and Security Plan

AlignSpace is a communication tool, not a qualified architect, engineer, electrician, quantity surveyor, contractor, or authority. Outputs remain drafts until human review.

## Risks and controls

| Risk | Example | Prevention | Detection/recovery |
|---|---|---|---|
| False inference | Marble vs laminate | tentative labels, confidence, evidence | correction + accuracy tests |
| Unsafe advice | Recommends wall removal | blocked topic policy | professional task + log |
| Price/stock fabrication | Exact supplier claim | source/tool required | citation check; dated estimate |
| Privacy exposure | Family photo | consent, minimisation, private storage | delete + incident flow |
| Copyright misuse | Scraped image reuse | provenance; curated catalogue | rights review |
| Prompt injection | Image tells model to ignore policy | content is untrusted; tool allow-list | review agent + red team |
| Cross-project access | Guessed project ID | server membership checks | anomaly alert + audit |
| Over-automation | AI resolves conflict | human decision | approval invariant |
| Stereotyping | Infers wealth/culture | forbid sensitive inference | sampled review |
| Cost abuse | Repeated uploads | limits/quotas | alarms + circuit breaker |

## Data classes

- **Restricted:** original images, invitations, identifiers.
- **Confidential:** briefs, answers, constraints, identity-linked audit.
- **Internal:** de-identified aggregate metrics.
- **Public:** approved demo assets and published documents.

## Privacy requirements

- Collect only data needed for alignment.
- Explain purpose, AI, retention, source responsibility, deletion.
- No general model training on project data without separate explicit consent/contract.
- No raw content in analytics or notifications.
- Provide project and asset deletion.
- Private/non-indexable by default.
- Synthetic or consented content in demos/evaluation.
- Document subprocessors, region, retention, and model terms before pilot.

## Prompt-injection boundary

Image text, metadata, URLs, and retrieved text are untrusted evidence. They may populate quoted evidence but cannot change policy, tools, recipient, model, or state. Only typed authorised actions alter canonical state.

## Human controls

Homeowner confirms preferences; designer owns constraints; both resolve conflicts and approve the same version; qualified professionals verify safety-critical items; operator can disable models and use manual mode.

## Incident priority

- **P0:** cross-project exposure, unauthorized destructive action, invalid approval, credential compromise.
- **P1:** repeated unsafe output, deletion failure, large abuse.
- **P2:** low-risk bad inference, recoverable failure, isolated latency.

For P0: stop affected workflows, preserve restricted evidence, revoke access, notify owner, assess scope, meet applicable obligations, remediate, and review.

## Pre-pilot gate

Threat/data-flow review; privacy copy approval; dependency/secret/IAM/web/storage checks; cross-project and signed-URL tests; injection/unsafe-advice tests; deletion and kill-switch drills; no private demo data.

