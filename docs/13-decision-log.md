# Decision and Assumption Log

## Decisions

| Date | ID | Decision | Rationale | Revisit when |
|---|---|---|---|---|
| 2026-09-06 | D-001 | Living-room MVP | Rich but fewer wet-area risks | research/sponsor differs |
| 2026-09-06 | D-002 | Optimise alignment, not discovery | Root issue is misunderstanding | evidence differs |
| 2026-09-06 | D-003 | Separate preferences/constraints | Preserve both intents | schema redesign |
| 2026-09-06 | D-004 | Dual approval same version | Explicit/auditable agreement | pilot friction high |
| 2026-09-06 | D-005 | Max 10 questions | Limit effort; force priority | test data available |
| 2026-09-06 | D-006 | Curated/user images only | Reduce rights/privacy risk | partner catalogue |
| 2026-09-06 | D-007 | Model abstraction | Quality/latency/availability change | unique capability needed |
| 2026-09-06 | D-008 | AI attributes are proposals | Preference needs human confirmation | never |
| 2026-09-18 | D-009 | Advisory Dirichlet belief per decision, excluded from signed brief | Rank questions and suggestions by evidence without changing D-008 | confirmed labels allow a learned measurement model |
| 2026-09-18 | D-010 | Hand-set constrained contextual bandit for next step, not RL | No intervention logs yet; hard gates must precede reward | enough `decisionLog` outcomes to train and validate |
| 2026-09-18 | D-011 | No synthetic (GAN) augmentation | No real train/validation/test split to fit or verify it | real homeowner- and time-split data exists |

## Open decisions

| ID | Question | Owner | Due | Evidence |
|---|---|---|---|---|
| O-001 | Category/team composition? | Team lead | 6 Sep | registration |
| O-002 | Submission artifacts/weights? | Team lead | 7 Sep | organiser |
| O-003 | Bedrock model choice? | AI lead | 10 Sep | benchmark |
| O-004 | Mandatory brief fields? | Product | 11 Sep | interviews |
| O-005 | Pilot retention default? | Product/Security | 14 Sep | review/feedback |
| O-006 | Retrieval vs generation for P1? | Product/AI | 18 Sep | P0/tests |
| O-007 | Region/data constraints? | Cloud/Security | 10 Sep | policy/availability |

## Assumptions to validate

Homeowners complete guided pre-work; designers prefer structured evidence; proposed dimensions are sufficient; ten questions work; serverless meets throughput needs; dual approval earns its friction.

