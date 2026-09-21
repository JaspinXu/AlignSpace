# Submission kit — shortlisting round

Deadline: **28 September 2026, 09:00 SGT**, posted in `#submission` (not `#round1-submission`). Aim to post by 27 September evening.

## 1. What only a person can do

| # | Action | Where | Status |
|---|---|---|---|
| 1 | Make `JaspinXu/AlignSpace` public | GitHub → Settings → General → Danger Zone | **Done, 21 Sep** — verified by an anonymous clone; history has no secrets |
| 2 | Deploy the tagged release and note the public URL | `scripts/deploy_lightsail.sh ubuntu@<ip> <key.pem>` (see `docs/15`) | Pending — needs instance IP |
| 3 | Record the narrated video and upload it (YouTube unlisted or a direct MP4 link) | Script in section 4 | Pending |
| 4 | Fill the URL placeholders in `docs/writeup/writeup.html`, re-render (`python docs/writeup/render_pdf.py`) and link the PDF | `docs/writeup/AlignSpace-writeup.pdf` | Draft ready |
| 5 | Run the owner trial and fill `docs/17-user-trial.md` | Local app | Pending |
| 6 | Ask the organisers the open questions in section 3 | `#admin-related` | Pending |
| 7 | Publish the GitHub release `v1.0` with the PDF and demo MP4 attached | `gh release create` (section 6) | Pending |
| 8 | Check every link in a private/signed-out window, then post | Slack `#submission` | Pending |

## 2. Slack post (text only; do not attach the video)

```
Team Code: 8QFDUS2I
Team: Four Wolf Kings
Project Name: AlignSpace — Design Inspiration Agents
Problem: Design Inspiration (Public category)

GitHub Repo: https://github.com/JaspinXu/AlignSpace  (release tag: v1.0)
Video (MP4 / YouTube): <VIDEO_URL>
Write-up (PDF): <PDF_URL>
Deployment: <https://PUBLIC_IP.sslip.io>  — running on the organiser-provided Lightsail medium instance
Deployment evidence: docs/16-verification-report.md (live checks + date), docs/evidence/e2e-run.json

How to try it: open the deployment URL → "Start my room brief" → answer the questions → "Invite my designer" and open the link in a private window → add a designer constraint → resolve it → approve from both sessions.
```

Before posting: replace every `<...>`, open each link in a private window, and keep a screenshot of the post as the receipt.

## 3. Questions for organisers (`#admin-related`)

1. The briefing lists video "duration: 30mins". Is 30 minutes a maximum or a required length? Would a 5–10 minute demo plus walkthrough be acceptable?
2. Must the GitHub repository be public, or is adding specific judge accounts acceptable? If so, which accounts?
3. What counts as "deployment evidence" — is a public URL enough, or do you also want screenshots of the Lightsail console?
4. Is there a page limit or template for the PDF write-up?
5. Please confirm our topic selection (Design Inspiration, Public category) is recorded for team 8QFDUS2I.
6. Between the shortlisting deadline and the finale window (29 September – 5 October), does our Lightsail instance stay available, and should the deployment URL remain reachable for judging during that time?

## 4. Video plan and narration script

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

## 5. Link and packaging check (27 September)

- [ ] `main` contains the final code; tag `v1.0` created on the submitted commit (`git tag -a v1.0 -m "Shortlisting submission" && git push origin v1.0`).
- [ ] Repository opens in a private window; README renders; LICENSE present.
- [ ] Deployment URL opens in a private window; `/health` returns ok; guided sample works; designer invitation works in a second private window.
- [ ] Video link plays in a private window (unlisted, not private).
- [ ] PDF link downloads in a private window.
- [ ] `docs/16` updated with the live URL, date and checks; `docs/17` filled.
- [ ] Post in `#submission`; screenshot the post.

## 6. Release assets

A GitHub release gives permanent direct links for the write-up and the demo video, which also satisfies the "URL to download the video in MP4 format" requirement without YouTube:

```bash
gh release create v1.0 --title "AlignSpace v1.0 (shortlisting submission)" \
  --notes "Shortlisting submission for NUS-ISS Show Me Your Agents. Deployment: <URL>." \
  docs/writeup/AlignSpace-writeup.pdf "output/alignspace-golden-path-demo.mp4#Golden-path demo (2m12s, captioned)"
```

The asset links are then `https://github.com/JaspinXu/AlignSpace/releases/download/v1.0/<filename>`. Check both in a private window before posting.

## 7. Finale (only if shortlisted)

Finalists: 10 October 2026, 08:30 SGT, face-to-face. Updated artifacts go to `#final-submission`. Prepare: five-minute pitch (`docs/11`), live demo on the deployed URL with the captioned MP4 as fallback, three clean rehearsals, and answers to the judge Q&A in `docs/11`.
