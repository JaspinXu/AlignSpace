# Evidence-Based Belief and Suggested Next Step

This layer adapts the team's V7 model note (*装修设计贝叶斯动态偏好与方案执行模型 v7 强化学习协作决策版*) to what AlignSpace can support today. It is **advisory**: it never confirms a preference, never edits the brief, and is excluded from the signed content hash. Decision D-008 still holds: only a human answer or a human review changes a preference.

Code: `app/belief.py` (belief, evidence quality, policy, intervention log), wired in `engine.recompute`. Tests: `tests/test_belief.py`. Simulation: `scripts/simulate_belief.py`.

## What was adopted

| V7 concept | AlignSpace implementation | Why this form |
|---|---|---|
| Evidence `D_it` kept separate from context `c_it` | Answers, suggestions, reference notes and saved homes are evidence. Housing type is context (population prior only). | Prevents one action counting as both evidence and a reason for change. |
| Hidden preference `z_it` with posterior `Bel(z)` | Dirichlet posterior over each dimension's options. | The eight decisions are categorical choices; a Dirichlet is the categorical analogue of the note's Gaussian state and stays explainable. |
| Evidence quality `q_it` → observation noise `R_it` (eq. 4–5) | `q = sigmoid(-2 + 3·explicitness + 1·reliability − 1·dispersion)`; weight `= 2·q`. | Same functional form; β values are provisional and documented in code. |
| Confirmed preference as anchor, `R_conf ≪ R_0` (eq. 9) | A human answer or confirmation adds 8 pseudo-counts (vs ≤ 2 for any machine observation). | Human confirmation dominates any number of weak signals. |
| Duplicate / anomaly density lowers quality, applied once (eq. 3–4) | The k-th observation of the same value counts `1/k`; a note naming several values for one dimension has higher dispersion and lower q. | Repeats and bursts cannot manufacture certainty; no double penalty. |
| Time-dependent persistence `Φ(Δt)` (eq. 7) | Unconfirmed suggestions fade with a 30-day half-life. | Older machine suggestions matter less as the project moves on. Confirmed anchors do not decay. |
| Cross-homeowner group prior, not influence (eq. 6a–6b) | Style frequencies among attributed public homes of the same property group (HDB / Condo / Landed); total weight 1 pseudo-count. | Cold start only. The Singapore collection is mostly HDB, so the prior is deliberately weak. It states co-occurrence, not that homeowners influence each other. |
| Hard constraints `G_ij` before any reward (eq. 18, §6.3.8) | Must-avoid notes and active designer constraints remove options before scoring. A confirmed value that is now blocked shows as **Blocked**. | Constraints are never traded off against reward. |
| Confidence `C^Bayes` and "needs confirmation" is not a third preference class (eq. 15, 20) | Status per dimension: **Confirmed**, **Leaning — please check**, **Still open**, **Blocked**. | "Leaning" asks for a human check; it is never treated as agreement or mismatch. |
| Ask action valued by uncertainty reduction `ΔUnc` (eq. 13g) | Core questions are ranked by expected entropy removed from the posterior × impact. | With no evidence this equals the old option-entropy order, so existing behaviour is unchanged; evidence now moves the order. |
| Safe action set `U^safe` and policy `π` (eq. 13c–13f) | `ask / confirm / show / recommend / present / defer`, filtered by gates, ranked by `r = 1.0·ΔUnc + 0.8·ΔE + 0.6·P(confirm) + 1.2·acceptance − cost`. | This is the note's recommended first version: a constrained contextual bandit with hand-set weights. |
| Reward on consensus, not clicks (§6.3.6) | Clicks, dwell time and saves are never rewards. | Avoids optimising for curiosity or feed effects. |
| Intervention logs before RL (§6.3.8) | `decisionLog` records the suggestion shown, what the person did, whether it matched, and uncertainty before/after (last 200 events per project). | Without these logs a policy cannot be trained or evaluated. |
| State-space simulation (eq. 23, §8) | `scripts/simulate_belief.py` recovers known hidden values from noisy evidence. | Checks method logic only; not a user or business result. |

## What was deliberately not adopted yet

- **Continuous Kalman state with learned `H`, `Q(Δt)`, `Σ_g`.** No confirmed labels exist to learn a measurement map or covariance. Revisit with homeowner-confirmed labels from trials.
- **Density-aware attention over word-level evidence (eq. 2a–2c).** Notes are short (≤ 500 characters) and parsed by the model gateway or offline rules; there is no session-level click or dwell stream.
- **Full RL / TD learning (eq. 13d, 13h).** No intervention logs yet. `decisionLog` collects them first.
- **GAN / CTGAN augmentation (eq. 22).** No real train/validation/test split exists. If added later, fit only on the real training split and report results only on real, homeowner- and time-separated test data.
- **Plan-execution score `E_ij` against design proposals.** AlignSpace does not yet receive designer concept proposals to score. The belief statuses already provide the confidence part.

## User interface

Fallbacks were checked against the saved local projects: when the remaining decisions belong to the other role the step says so (**Invite your designer** / **Wait for the homeowner**); when a role's own decisions remain after a finished round it offers **Start another round of questions**; a readiness blocker (for example two confirmed values for one decision) opens the shared brief; an approved brief suggests export.

The alignment page shows **Suggested next step** above the design references: the action for the viewer's role, why it was chosen, its expected value, and a button that goes to the relevant control. **How clear is each decision so far?** lists the eight dimensions with status and top candidate. Both are bilingual (English / 中文).

## Simulation (method check only)

`python scripts/simulate_belief.py --homeowners 400 --seed 7`, 70 %-accurate machine suggestions, 25 % of wrong suggestions repeated four times:

| Seed | Top-1 belief | Top-1 vote count | Brier belief | Brier votes | "Leaning" precision |
|---|---|---|---|---|---|
| 7 | 0.724 | 0.686 | 0.520 | 0.524 | 0.783 |
| 11 | 0.726 | 0.696 | 0.515 | 0.517 | 0.783 |
| 23 | 0.710 | 0.677 | 0.528 | 0.544 | 0.765 |

Reading: the belief is modestly more accurate than counting votes and resists repeated wrong signals. About one in five "leaning" suggestions is still wrong, which is why the product asks for a human check instead of confirming. These numbers come from synthetic data and are not evidence of user satisfaction.

## Calibration and next data

1. Use trial sessions to collect `decisionLog`, confirmations, rejections and final approvals.
2. Split by project and time before any tuning. Tune `β`, thresholds and reward weights on the validation split only.
3. Report calibration (reliability of "leaning") and question count to approval on the real test split.
4. Only then consider learned policies.
