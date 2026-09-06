# AlignSpace — Design Inspiration Agents

## Project summary

**AlignSpace** is a reference-library-driven, two-sided requirements-alignment system for Singapore homeowners and interior-design SMEs. Rather than generating a design from a single prompt, it progressively turns inspiration images, informal preferences, designer feedback, and real-world constraints into a shared, actionable living-room design brief.

The system maintains one versioned **Project Design State** as its source of truth. It clearly separates confirmed requirements, AI inferences, rejected ideas, unresolved conflicts, and professional constraints, with every change linked to its source. After each interaction, hybrid retrieval analyses the remaining design space so the agents can ask the highest-value question, compare genuinely different directions, or focus on feasible details.

A deterministic readiness score guides the workflow through **Explore, Clarify, Focus, and Commit**. The final brief records agreed preferences, accepted reference elements, constraints, open risks, and approval history. The MVP targets alignment within 10 clarification questions while keeping structural, regulatory, pricing, and other consequential decisions under human review.

## Why this exists

Homeowners often say things such as “warm modern” or “hotel-like,” but the same words can mean different colours, materials, layouts, lighting, or price points. Designers spend time reverse-engineering what a client likes from unrelated images, then repeat early concepts when expectations were not actually aligned.

AlignSpace does not replace a designer and does not produce construction advice. Its job is to reduce ambiguity before concept design begins.

## MVP promise

> From 3–10 inspiration images to a mutually approved living-room design brief in one guided session, with every AI inference labelled, editable, and linked to evidence.

## Core workflow

1. Homeowner creates a project, gives consent, uploads references, and supplies room/budget context.
2. Vision analysis proposes attributes and evidence regions without treating guesses as facts.
3. The Interview Agent asks at most 10 adaptive questions chosen for expected uncertainty reduction.
4. The Designer Agent structures professional constraints and explains trade-offs plainly.
5. The Alignment Agent identifies agreement, conflict, and missing decisions.
6. The Review Agent checks provenance, confidence, safety, and brief completeness.
7. Both people edit and explicitly approve a versioned design brief.

## Repository guide

| File | Purpose |
|---|---|
| [Official context](docs/00-official-context.md) | Verified event facts vs team assumptions |
| [Product requirements](docs/01-product-requirements.md) | PRD, scope, users, stories, acceptance criteria |
| [Research plan](docs/02-user-research-plan.md) | Interviews, tests, consent, synthesis |
| [Experience specification](docs/03-experience-spec.md) | Flows, screens, states, copy |
| [Agent system design](docs/04-agent-system-design.md) | Agent responsibilities and orchestration |
| [Technical architecture](docs/05-technical-architecture.md) | AWS design, deployment, observability |
| [Contracts](docs/06-data-and-api-contracts.md) | Domain model and API boundaries |
| [Safety and security](docs/07-safety-privacy-security.md) | Threat model, privacy, controls |
| [Evaluation](docs/08-evaluation-plan.md) | Offline, human, business, red-team tests |
| [Delivery plan](docs/09-delivery-roadmap.md) | Three-week plan and backlog |
| [Business case](docs/10-business-case.md) | Value, adoption, pricing hypothesis, pilot |
| [Demo and pitch](docs/11-demo-and-pitch.md) | Script, fallback, judge Q&A |
| [Submission checklist](docs/12-submission-checklist.md) | Evidence and artifact checklist |
| [Decision log](docs/13-decision-log.md) | Decisions, assumptions, unresolved choices |
| [Design brief schema](schemas/design-brief.schema.json) | Machine-readable shared state |
| [Agent prompts](prompts/README.md) | Versioned behavioural contracts |
| [Demo brief](examples/project-haven.design-brief.json) | Schema-valid sample state for UI/tests |
| [Asset register](docs/14-data-and-asset-register.md) | Rights, consent, provenance, retention |

## Agent runtime and cloud tooling

These tools operate at different layers and are alternatives where noted:

| Tool | Role in AlignSpace |
|---|---|
| [OpenClaw](https://github.com/openclaw/openclaw) | Optional self-hosted gateway for a fast WhatsApp, Telegram, or WebChat demo. AWS provides a preconfigured [Lightsail deployment](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-quick-start-guide-openclaw.html) that can call Amazon Bedrock. It should remain a channel adapter rather than own multi-user project state. |
| [Hermes Agent](https://hermes-agent.nousresearch.com/docs/) | Alternative general-purpose agent runtime with persistent memory, skills, specialist bots, MCP, and delegation. Useful for experimenting with interview and alignment strategies. |
| [NanoClaw](https://github.com/nanocoai/nanoclaw) | Alternative lightweight runtime that isolates agent groups in containers. Useful when prototype security, limited filesystem access, and code auditability are the priority. |
| AWS cloud resources | Production foundation: Bedrock for multimodal reasoning, S3 for images and briefs, DynamoDB for structured alignment state, Cognito/API Gateway for access, and Lambda plus Step Functions or AgentCore for orchestration. |
| [Kiro](https://kiro.dev/docs/) | Development environment for specs, repository guidance, hooks, tests, and implementation; it is not part of the end-user runtime. |

Recommended MVP: use **Kiro for development and AWS-native services for the core product**, adding OpenClaw only if a messaging-channel demo is valuable. OpenClaw, Hermes Agent, and NanoClaw are competing runtime choices and should not all be introduced into the first version.

## Prototype definition of done

- A living-room project completes the full happy path with sample data.
- Image observations show confidence and source evidence.
- The next question comes from unresolved high-impact attributes, not a fixed chatbot script.
- Designer constraints can produce a visible conflict and homeowner decision.
- The final brief validates against `schemas/design-brief.schema.json`.
- Approval is explicit, attributable, versioned, and reversible.
- Unsupported structural, electrical, regulatory, quotation, or availability claims are blocked or escalated.
- Evaluation reports task completion, agreement, correction rate, latency, cost, and safety results.

## Working assumptions

This package is implementation-ready but not evidence-complete. Numeric goals are hypotheses until user tests establish baselines. Exact hackathon upload formats and judging weights are not public on the event page as of 6 September 2026 and must be confirmed with the organiser.

## Source

- [NUS-ISS Show Me Your Agents Hackathon](https://www.iss.nus.edu.sg/show-me-your-agents)
