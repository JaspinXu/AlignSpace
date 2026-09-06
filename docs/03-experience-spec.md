# Experience Specification

## Principles

- Show evidence before asking for trust.
- Ask one consequential question at a time.
- Use plain language, examples, and “not sure.”
- Preserve both views before resolving disagreement.
- Make AI proposals easy to correct and impossible to mistake for approval.
- Keep the evolving brief visible.

## Information architecture

Projects → Project overview → References → My preferences → Designer review → Alignment decisions → Final brief → Activity/privacy.

## Happy path

### 1. Create project

Project name, living room, housing type, optional dimensions, budget band, completion band. Copy: “Budget helps discuss trade-offs; it is not a quotation.”

### 2. Consent and upload

Explain purpose, AI processing, retention, source responsibility, deletion, and review. Require an unticked checkbox. Each image supports source URL and “What caught your eye?”

### 3. Analysis review

Group chips by colour, materials, lighting, layout, furniture, style, mood. Each shows `AI proposed`, confidence category, and source evidence. Actions: confirm, edit, reject, not relevant.

- High: repeated or visually distinct evidence.
- Medium: plausible, requires confirmation.
- Low: weak or conflicting evidence.

### 4. Clarification interview

One question per screen; show `Question 3 of up to 10` and why it is asked. Support images, text, “both,” “neither,” and “not sure.” Example: “Which matters more: pale oak surfaces or uncluttered storage?”

### 5. Homeowner summary

Show confirmed preferences, anti-preferences, open decisions, evidence coverage. Submit for designer review.

### 6. Designer review

Brief first, evidence on demand. Each item: accept, suggest alternative, add constraint, request clarification. Constraint needs category, rationale, severity, verification, and impact.

### 7. Alignment decisions

Cards show homeowner preference, designer recommendation, difference, effect, neutral options, and “Discuss offline.” AI summarises; humans choose.

### 8. Approval

Show completeness, unresolved items, version, change summary. Both approve separately. Any edit increments version and clears approvals.

## Failure states

| State | Experience |
|---|---|
| No images | Explain useful references; offer licensed demo set |
| Analysis running | Per-image progress; review completed images |
| One image fails | Preserve others; retry/remove |
| Model timeout | Preserve state; retry once; offer manual tagging |
| Low confidence | Ask; never auto-confirm |
| No designer | Mark draft “awaiting designer review” |
| Professional question | State limit; create verification task |
| Brief edited | Invalidate old approvals |

## Accessibility

Text description for evidence regions; status uses icon/text and colour; keyboard and 200% zoom support; design terms explained plainly; no assumptions about household, wealth, culture, or ability from images.

## Analytics events

`project_created`, `consent_granted`, `image_uploaded`, `image_deleted`, `attribute_proposed`, `attribute_corrected`, `attribute_confirmed`, `question_shown`, `question_answered`, `designer_review_submitted`, `conflict_created`, `conflict_resolved`, `brief_generated`, `brief_edited`, `brief_approved`, `policy_blocked`, `professional_review_requested`.

Never put image pixels, unrestricted free text, email, or names in analytics.

