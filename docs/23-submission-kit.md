# Submission kit — final submission by email

Deadline as briefed: **28 September 2026, 09:00 SGT**. The organisers' final instructions (email to all four members, following the Slack announcement) ask for one email in a fixed format. Send it by 27 September evening; if the Slack announcement also asks for a post in `#submission`, post the same text there.

## 1. Status

| Item the email must include | Ready? | Where |
|---|---|---|
| Team Code | Yes | 8QFDUS2I |
| Problem Statement | Yes | Design Inspiration (public category) — wording in section 2 |
| GitHub Repository URL | Yes | <https://github.com/JaspinXu/AlignSpace> (public), release `v1.1` |
| Business Proposal (PDF) | Yes | `docs/submission/AlignSpace-Business-Proposal.pdf`, 10 pages |
| Technical Document (PDF) | Yes | `docs/submission/AlignSpace-Technical-Document.pdf`, 10 pages |
| Demo Video (YouTube/cloud URL) | Recorded by the team | Paste the link; YouTube must be *Unlisted*, not *Private* |
| Deployment Evidence (URL/artifact) | Yes | Live URL + 26 September snapshot + live 19/19 run |

## 2. The email (copy exactly)

**Subject:** `SMYA Final Submission - 8QFDUS2I`

**Attach:** `AlignSpace-Business-Proposal.pdf` and `AlignSpace-Technical-Document.pdf` (from `docs/submission/` or the `v1.1` release).

```
Dear NUS-ISS Show Me Your Agents Hackathon Team,

Please find below the final submission of Team Four Wolf Kings.

Team Code: 8QFDUS2I
Team: Four Wolf Kings (Chen Xiaoming, Xing Yiyuan, Xu Tengyang, Xu Zhaobin)
Project: AlignSpace - Design Inspiration Agents

Problem Statement: Design Inspiration (Public category).
Homeowners find it hard to communicate design preferences in words and spend
time collecting inspiration; designers compile references manually; misaligned
expectations lead to repeated design revisions before both sides agree.
AlignSpace is a two-sided agent workspace that turns a homeowner's references
and notes and a designer's practical constraints into one versioned
living-room brief that both people explicitly approve.

GitHub Repository URL: https://github.com/JaspinXu/AlignSpace
(release v1.1: https://github.com/JaspinXu/AlignSpace/releases/tag/v1.1)

Business Proposal (PDF): attached - AlignSpace-Business-Proposal.pdf
https://github.com/JaspinXu/AlignSpace/releases/download/v1.1/AlignSpace-Business-Proposal.pdf

Technical Document (PDF): attached - AlignSpace-Technical-Document.pdf
https://github.com/JaspinXu/AlignSpace/releases/download/v1.1/AlignSpace-Technical-Document.pdf

Demo Video: <VIDEO_URL>

Deployment Evidence:
- Live URL: https://54.255.93.19.sslip.io (organiser-provided AWS Lightsail
  instance, ap-southeast-1; health check: https://54.255.93.19.sslip.io/health)
- Deployment snapshot, 26 Sep 2026:
  https://github.com/JaspinXu/AlignSpace/blob/v1.1/docs/evidence/deployment-snapshot-2026-09-26.txt
- Live two-session browser checks, 19/19 passed, 26 Sep 2026:
  https://github.com/JaspinXu/AlignSpace/blob/v1.1/docs/evidence/e2e-live-run-2026-09-26.json
- Verification report:
  https://github.com/JaspinXu/AlignSpace/blob/v1.1/docs/16-verification-report.md

Best regards,
Xu Zhaobin, on behalf of Four Wolf Kings (8QFDUS2I)
```

## 3. Before pressing send

- [ ] Replace `<VIDEO_URL>` and play it in a private (signed-out) window.
- [ ] Both PDFs attached; each opens.
- [ ] Every link above opens in a private window (repository, release, live URL, `/health`, evidence files).
- [ ] Recipient: reply to the organisers' "SMYA Final Submission" email, or use the address it names; copy the three teammates.
- [ ] Keep the sent email (or a screenshot) as the receipt.

## 4. Release assets

`v1.1` carries both PDFs and the captioned golden-path demo (`alignspace-golden-path-demo.mp4`, 2 min 12 s, synthetic data, offline note rules) as a fallback reel. To replace a PDF after an edit:

```bash
python docs/submission/render_pdfs.py
gh release upload v1.1 docs/submission/AlignSpace-Business-Proposal.pdf docs/submission/AlignSpace-Technical-Document.pdf --clobber
```

## 5. Video plan and narration script (reuse for the finale)

Deliverables:

- `alignspace-golden-path-demo.mp4` (2 min 12 s): automatically recorded from two browser sessions with captions, synthetic data and offline note rules. Use it as B-roll or as the backup if a live demo fails. Regenerate with `python scripts/e2e_golden_path.py <url> video`.
- The narrated submission video: record the screen with OBS or the Windows Game Bar while following the script below against the deployed URL. The target is 8–12 minutes unless organisers confirm 30 minutes is required. If it is, extend sections D and E rather than padding.

| Time | Section | On screen | Say (condensed) |
|---|---|---|---|
| 0:00 | A. Problem | Home page, a few Singapore homes | "Homeowners say 'warm modern' or 'hotel-like'; designers decode it from screenshots. Misunderstanding shows up later as revision cycles. Our Design Inspiration problem is about agreement, not image generation." |
| 1:00 | B. Promise | How-we-align section | "AlignSpace turns references, notes and practical constraints into one versioned brief that the homeowner and designer both approve, and every AI suggestion stays a suggestion until a person confirms it." |
| 1:40 | C. Homeowner flow | Create project, goals, must-avoid "marble", note with an injected instruction, suggestions | "The note is evidence, not an instruction: the injected line is ignored. Marble is a hard constraint, so it is never proposed. Suggestions are labelled proposed." |
| 3:00 | D. Agent reasoning | Suggested-next-step panel, belief list, adaptive question | "The agent keeps an explicit shared state. For each decision it holds an evidence-weighted belief; repeats and scattered notes count less; confirmation dominates. It asks the question that removes the most uncertainty and suggests the safest next step — ask, confirm, compare, resolve or approve — with hand-set weights we state openly." |
| 5:00 | E. Two-sided alignment | Invite link → designer session; layout/care questions; constraint on light oak; conflict card | "The designer joins from a private single-use link and only owns practical decisions. A constraint that contradicts a confirmed preference opens a conflict and blocks approval. The agent never picks the trade-off." |
| 6:30 | F. Resolution and approval | Designer accepts constraint → homeowner revises material → both approve → export → edit clears approvals | "Both people approve the same content hash from their own sessions. Any later edit clears both approvals." |
| 7:30 | G. Guardrails and evidence | Test run, `docs/evidence/e2e-run.json`, verification report | "77 automated tests; 19/19 two-session checks including invitation replay, cross-project reads, stale edits and role spoofing. Model calls are bounded per project and globally, and failures never silently fall back." |
| 8:30 | H. Platform | Lightsail URL, `/health`, gateway note | "The assessed build runs on the organiser Lightsail medium instance and calls the organiser Claude Sonnet 4.5 JSON API behind an adapter. Image understanding is disabled until a vision endpoint passes a known-image test." |
| 9:15 | I. Honest limits and next steps | Verification report "Pending" | "No time-saving or ROI claim yet. Next: paired homeowner–designer trials, calibrate the belief and train the next-step policy from the decision log." |
| 9:45 | Close | Approved brief | "AlignSpace makes taste discussable, disagreement visible and approval explicit." |

Recording checklist: 1920×1080, browser zoom 100%, notifications off, synthetic data only, no API keys or `.env` on screen, audio check first, one clean take per section is fine.


## 6. Finale (only if shortlisted)

Finalists: 10 October 2026, 08:30 SGT, face-to-face. Updated artifacts go to `#final-submission`. Prepare: five-minute pitch (`docs/11`), live demo on the deployed URL with the captioned MP4 as fallback, three clean rehearsals, and answers to the judge Q&A in `docs/11`. Keep the Lightsail instance running through the finale.
