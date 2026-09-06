# Product Requirements Document

## Product summary

**Name:** AlignSpace  
**Proposition:** A two-sided AI alignment workspace that turns visual inspiration into a shared, evidence-backed renovation brief.  
**MVP:** Singapore living rooms.  
**Users:** homeowners and interior designers at small firms.  
**Buyer hypothesis:** interior-design SME owner or design lead.

## Problem

Inspiration images are high-bandwidth but ambiguous. A homeowner may like only the lighting in one image and cabinetry in another; a designer may interpret the whole image as the requested style. Mood boards rarely capture the reason for selection, confidence, constraints, rejected alternatives, or explicit agreement. The cost appears as repeated clarification, concept rework, slow sales cycles, and lost trust.

## Product outcome

Create a brief that a designer can use to start concept work without reinterpreting the homeowner's references from scratch.

### North-star measure

**Brief Alignment Rate:** percentage of required brief decisions for which homeowner and designer independently select the same interpretation after the guided session.

### MVP targets (hypotheses)

- At least 80% alignment on a defined 20-item rubric.
- Median guided-session time ≤20 minutes, excluding designer response time.
- At most 10 homeowner clarification questions.
- At least 90% of AI-extracted attributes supported by evidence or labelled uncertain.
- Zero unreviewed high-severity safety claims in release-gate tests.
- At least 70% of pilot users expect the brief to reduce discussion time.

Do not present targets as achieved results.

## Personas and jobs

### Homeowner: Mei, first renovation

Needs help expressing taste without learning design vocabulary; wants control over trade-offs and images. Job: “Help me show what I mean and confirm that my designer understands it.”

### Designer: Arjun, SME consultant

Needs structured requirements rather than another transcript, with constraints and open decisions visible. Job: “Help me turn scattered references into a usable brief with fewer clarification loops.”

### SME owner: Lina, studio director

Needs shorter pre-design cycles, consistency, auditability, and predictable cost. Job: “Help my team align projects without adding operational risk.”

## Value proposition

| Current pain | Product response | Evidence |
|---|---|---|
| “I like this image” is ambiguous | Attribute-level annotation | liked element + source region |
| Terms mean different things | Plain examples and comparison | selected/rejected option |
| Constraints arrive late | Designer constraint capture | rationale + impact |
| Conflict stays hidden | Explicit alignment states | agreed/conflicted/unresolved |
| Mood board lacks actionability | Structured editable brief | versioned state + approval |

## Scope

### P0 — must work in the demo

- Create/join project with homeowner and designer roles.
- Consent before upload.
- Upload 3–10 JPG/PNG/WebP images, max 10 MB each.
- Optional room dimensions; required budget band.
- Extract tentative style, colour, material, lighting, furniture, layout, mood, and liked-element attributes.
- Show evidence/confidence; allow correction/deletion.
- Ask adaptive single-purpose questions with “not sure.”
- Designer adds constraints, recommendations, and trade-offs.
- Detect contradictory preferences and preference–constraint conflicts.
- Alignment dashboard and editable brief.
- Separate homeowner and designer approval.
- Export as JSON and printable HTML/PDF in a later implementation task.
- Audit AI proposal, human edit, and approval.

### P1

- Approved reference retrieval and up to three explained directions.
- Link expiry and image deletion controls.
- English plus Simplified Chinese copy.
- Brief version comparison and SME admin metrics.

### Out of scope

- Construction drawings, compliance, structural/electrical guidance.
- Exact quotes, inventory claims, purchasing, or contracts.
- Social-media scraping or foundation-model training.
- Photorealistic guarantees, designer replacement, or whole-home support.

## Acceptance criteria

### FR-01 Project and consent

Before upload, show purpose, retention, deletion, and AI-use notices. Consent is time-stamped and withdrawable.

### FR-02 Image intake

Each asset receives ID, validation state, provenance, and deletion control. Unsupported files fail with recoverable guidance.

### FR-03 Preference extraction

Every proposal contains value, confidence, source, evidence, model version, and status `proposed`. Only humans can confirm it.

### FR-04 Adaptive interview

Rank candidate questions by impact, uncertainty, conflict relevance, repetition, and effort. Ask one at a time and stop at completion or 10.

### FR-05 Designer review

Designer may accept, challenge, constrain, and explain. Homeowner's original answer remains visible.

### FR-06 Conflict resolution

Create a neutral decision card with both views, evidence, impact, and allowed resolutions. Never silently choose.

### FR-07 Brief and approval

Validate against schema; distinguish preferences from constraints; require independent approvals. Edits create a version and invalidate prior approvals.

### FR-08 Safety response

Structural, electrical, regulatory, exact-price, and live-availability questions produce a limitation and professional-verification task.

## Required brief fields

Project/room metadata; goals; functional needs; style and anti-preferences; colour, material, lighting, furniture, layout, mood; budget/timeline context; liked/rejected references; designer constraints/trade-offs; agreement and unresolved decisions; provenance, confidence, version, approvals.

## Non-functional requirements

- Availability target: 99.5% during pilot hours.
- First progress ≤3s; 10-image analysis p95 ≤60s; interactive p95 ≤8s.
- Model/infrastructure target <S$3 per completed project; validate with telemetry.
- Keyboard access, labelled controls, colour-independent status, WCAG 2.1 AA contrast target.
- Private by default, least privilege, deletion workflow.
- Append-only audit of proposals, edits, approvals, and blocks.
- Idempotent jobs, bounded retries, timeout fallback, schema validation.

## Completion rule

Stop when required attributes are confirmed, not applicable, or explicitly unresolved; no critical conflict remains; completeness ≥85%; and question budget remains. Users may stop early, but missing decisions stay visible.

## Dependencies

- Lawful demo images and reference catalogue.
- AWS account and selected Bedrock models.
- At least three designers and five homeowners for tests.
- Organiser clarification of final artifacts and pitch constraints.

