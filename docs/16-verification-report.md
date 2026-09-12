# Verification report — 13 September 2026

## Automated evidence

- Python suite: 32 tests passed. Covers versioned approvals, stale concurrent model results, conflicting preferences, negation, constraints, budget and avoid filtering, project isolation, role spoofing, invite replay, consent, actual image decoding, quotas and model output validation.
- Vision adapters for OpenAI-compatible, Anthropic and Ollama formats pass mocked contract tests; this does not demonstrate live image capability.
- Frontend JavaScript syntax checked with Node.
- Real competition gateway text inference returned proposed light oak and light neutral preferences from a synthetic note while excluding disliked marble. One observed call took 3,203 ms and reported 393 input / 144 output tokens. This is one smoke test, not a performance benchmark.
- A synthetic known-image probe returned NO_IMAGE. Image inference remains disabled; note analysis works and reference images can be displayed privately.

## Deployed checks

Ubuntu systemd service and Caddy run on the supplied Lightsail instance. HTTPS is temporarily served at https://54-255-93-19.sslip.io:80/ because managed firewall port 443 is unavailable. External certificate validation and public health passed.

Seven live checks passed using separate browser-equivalent HTTP sessions and synthetic project data: Secure cookie; project isolation; invitation replay rejection; role spoof rejection; distinct dual approvals; content revision invalidating approvals; service restart preserving state and access. Local check results are in ignored tmp/deployment-checks.json.

Browser trial confirmed guided sample creation and real note suggestions shown as proposed, with an explicit reminder that notes, not image pixels, are analysed.

## Evidence still needed

No authorised room-image dataset or independent designer study was supplied. The owner will run the trial worksheet in docs/17-user-trial.md. No time savings, satisfaction score or business ROI is claimed. Candidate prices are illustrative. This prototype does not verify professional construction constraints or provide account recovery. Standard HTTPS port and certificate renewal need organiser follow-up; current certificate expires 11 December 2026.
