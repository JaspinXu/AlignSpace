# AlignSpace Backend Agent Workflow Design

**Status:** Ready for implementation planning after user review  
**Date:** 8 September 2026  
**Scope:** Local backend MVP only

## 1. Purpose

This design turns the existing AlignSpace product and agent specifications into a locally runnable backend. The backend accepts homeowner inspiration references and explicit preferences, structures designer constraints, coordinates five logical agents around one canonical project state, resolves high-impact uncertainty and conflict, generates a shared design brief, and enforces review and dual approval.

The first implementation proves the workflow and its invariants with deterministic mock providers. It does not depend on model credentials, AWS resources, or a frontend.

## 2. Scope

### Included

- Python backend using FastAPI, LangGraph, Pydantic, SQLAlchemy, and SQLite.
- Five logical agent nodes: Vision Analyst, Homeowner Interview Agent, Designer Agent, Alignment Agent, and Review Agent.
- One canonical Shared Project Design State assembled from persisted domain records.
- Typed agent proposals and state patches validated before persistence.
- Sparse preference storage: absent attributes are not materialised by default.
- Project creation, consent, test-asset registration and deletion, mock analysis, human correction or rejection, homeowner answers, designer reviews, conflict resolution, brief generation, and dual approval.
- Explicit workflow pauses while waiting for a homeowner, designer, or professional response.
- Optimistic concurrency, idempotency, audit events, bounded retries, and typed errors.
- Automated unit, workflow, and API tests.

### Excluded

- Frontend or mobile user interface.
- Generated room images, renderings, visual directions, or a Visualization Agent.
- Construction drawings, structural or electrical guidance, regulatory assurance, exact quotations, and live product availability.
- Production identity, Cognito, S3, DynamoDB, Step Functions, Bedrock, Lightsail deployment, or other AWS infrastructure.
- A live LLM or multimodal provider. Provider integration follows only after the deterministic backend is accepted.
- Reference-library retrieval beyond deterministic test fixtures.

## 3. Architectural Decision

The backend uses one LangGraph workflow behind a FastAPI application. The graph contains five logical agent nodes and conditional routing, but the nodes do not run as separate services. They may later share one model provider while retaining separate prompts, permissions, input contracts, and output schemas.

FastAPI owns transport concerns. An application service owns authorization, consent checks, idempotency, optimistic locking, graph invocation, patch validation, transactions, and error mapping. LangGraph owns workflow routing and pause/resume semantics. SQLAlchemy repositories own persistence. SQLite is the local store and is hidden behind repository interfaces so DynamoDB or another store can replace it later.

The SQLite domain data is authoritative. LangGraph state is a projection used for one workflow execution, and the checkpoint records workflow position rather than becoming a second source of business truth.

## 4. Component Boundaries

### API layer

The API validates request shape, creates an `ActorContext`, invokes an application service, and returns typed responses. It does not call an agent or database session directly.

For the local MVP, actor identity is supplied through explicit development headers and checked against persisted project membership. This is replaceable by Cognito claims without changing application-service interfaces.

### Application and orchestration layer

The workflow service performs this write sequence:

1. Authenticate the actor and authorize project membership and role.
2. Check consent when the action involves an image.
3. Check `expectedStateVersion` and the idempotency key.
4. Load the current `ProjectState` projection.
5. Invoke or resume the LangGraph workflow.
6. Validate every returned patch against domain rules and the caller's permissions.
7. Apply accepted patches, append audit events, and increment `stateVersion` in one SQLite transaction.
8. Save the new workflow position and return the resulting state or pending task.

If a checkpoint write fails after the domain transaction, the workflow is reconstructed from canonical records and the idempotency record prevents duplicate effects.

### Agent layer

Each agent receives only the project fields and tools permitted for its role. It returns typed proposals, questions, decisions, or review findings. It never receives a database session and cannot persist state directly.

Agent-to-agent collaboration is state-mediated. Agents do not exchange private free-form conversations or overwrite another actor's information.

### Provider layer

Provider interfaces isolate model-specific behavior:

- `VisionProvider.analyze(...)` returns typed visual observations.
- `LanguageModelProvider.generate(...)` returns a requested typed result for an agent task.

The local implementation uses deterministic fixture-based mock providers. The provider interface will later adapt to the organiser's JSON LLM API or another provider without changing graph routing or domain models.

### Repository layer

Repositories expose domain operations instead of SQLAlchemy internals. Transactions and version checks are coordinated by a unit-of-work abstraction. Tests can use a temporary SQLite database without replacing domain logic with mocks.

## 5. Canonical State and Sparse Attribute Semantics

`ProjectState` is assembled from the following record groups:

- Project metadata, members, consent, room type, budget context, status, and `stateVersion`.
- Image assets and their provenance and validation status.
- Attribute records for explicit preferences and actual visual observations.
- Designer constraints and recommendations.
- Questions, answers, and repetition fingerprints.
- Conflicts, positions, impact, and resolutions.
- Brief versions, content hashes, and completeness.
- Approvals and audit events.

An attribute records at least:

- Stable ID and controlled dimension.
- Target element or region, such as wall, floor, chair, or lighting.
- Value and concise description.
- Status: `proposed`, `confirmed`, `rejected`, `conflicted`, `unresolved`, or `not_applicable`.
- Source kind and source ID.
- Evidence, including image ID and normalised region when applicable.
- Confidence for model observations.
- Actor, timestamps, and project version.

The system uses sparse storage:

- An explicit homeowner preference creates a `confirmed` attribute with homeowner evidence.
- A visual property not explicitly liked by the homeowner may create a `proposed` observation with evidence and confidence.
- A property that is neither mentioned, observed, constrained, nor selected as a high-impact missing decision creates no record.
- `unresolved` is used only for a tracked, meaningful decision. It is not a placeholder for every absent field.
- `not_applicable` requires an explicit human decision or a deterministic domain rule.
- Unmentioned does not mean liked, disliked, or not applicable.

Human-confirmed information outranks model proposals, but newer information does not delete provenance or history. A designer constraint remains distinct from a homeowner preference even when the two conflict.

## 6. Patch and Version Rules

Agents return an `AgentResult` containing typed domain patches and a next-action proposal. A patch contains an actor or agent identity, source, reason, expected state version, idempotency key, and typed operations.

The application service rejects a patch when it:

- Targets another project.
- Exceeds the agent's allowed fields or action set.
- Attempts to confirm a human preference on behalf of an agent.
- Silently overwrites confirmed evidence.
- Converts a constraint into a preference or vice versa.
- Uses a stale project version.
- Violates a domain or brief schema.

Every successful state-changing request increments `stateVersion`. Reusing an idempotency key with identical content returns the original result; reusing it with different content returns a conflict.

Editing a brief creates a new version and invalidates prior approvals. A project becomes `approved` only when the homeowner and designer approve the same brief version and content hash and no critical conflict remains open.

## 7. Workflow and State Machine

The persisted business status follows the existing contract:

`draft -> analysing -> homeowner_review -> designer_review -> alignment -> awaiting_approval -> approved -> archived`

LangGraph separately records its current node, such as `vision_analysis`, `homeowner_interview`, `designer_review`, `alignment`, `draft_brief`, or `review`. A `waitReason` records `homeowner`, `designer`, or `professional` when human input is required. This keeps internal execution details out of the stable business-status contract.

The graph may return from review to alignment for repair and from approval to draft brief when an edit creates a new version.

### Primary workflow

1. Create a project, add homeowner and designer membership, record consent, budget band, and room context.
2. Register three to ten valid test assets.
3. Run the Vision Analyst and persist only validated `proposed` visual observations.
4. Let the Homeowner Interview Agent first confirm which image regions or elements the homeowner wants to borrow, then ask detailed questions only for selected, high-impact attributes.
5. Accept and structure designer constraints and recommendations.
6. Run the Alignment Agent after each relevant change to compare preferences, observations, constraints, history, and unresolved conflicts.
7. Route to one of: ask homeowner, ask designer, request professional review, draft brief, or stop with explicit unresolved decisions.
8. Generate a draft brief only when required decisions are confirmed, explicitly unresolved, or not applicable, completeness is at least 85%, and no critical conflict remains.
9. Run the Review Agent and either repair, downgrade, redact, escalate, or pass the draft.
10. Collect independent homeowner and designer approvals for the same version and content hash.

The question budget is at most ten homeowner questions. Each question is single-purpose and must have a repetition fingerprint. A question-selection function ranks candidates using uncertainty, impact, conflict relevance, coverage gap, effort, and repetition penalty. The ranking and limit are deterministic even when a model later generates candidate wording.

## 8. Agent Contracts

### Vision Analyst

Consumes validated image-asset references and allowed room context. Produces controlled visual observations with evidence and confidence. It cannot infer personal traits, confirm preferences, provide professional advice, or choose a final design.

### Homeowner Interview Agent

Consumes confirmed preferences, proposed observations, tracked missing decisions, conflicts, and question history. Produces one neutral question or a stop decision. It first establishes which image elements matter to the homeowner, then drills into relevant color, material, form, mood, function, or layout details. It cannot exceed the question budget or treat silence as a preference.

### Designer Agent

Consumes confirmed homeowner preferences and explicit designer feedback. Produces typed constraints, recommendations, plain-language trade-offs, or a clarification request. It cannot invent site facts, compliance, exact cost, availability, or professional approval.

### Alignment Agent

Consumes the complete permitted project-state projection and optional deterministic reference fixtures. Produces conflicts and one next action: `ask_homeowner`, `ask_designer`, `request_professional_review`, `draft_brief`, or `stop_unresolved`. It cannot resolve consequential trade-offs for either human.

The question selector is a deterministic module used by the Homeowner Interview and Alignment agents; it is not a sixth agent.

### Review Agent

Consumes the draft brief, evidence, permissions, conflicts, and approval preconditions. Produces `pass`, `repair`, `downgrade`, `redact`, or `escalate` with reason codes. Deterministic schema, permission, approval, and blocked-topic checks run regardless of any model judgement.

## 9. API Surface

The local backend implements these versioned endpoints:

- `POST /v1/projects`
- `GET /v1/projects/{projectId}`
- `DELETE /v1/projects/{projectId}`
- `POST /v1/projects/{projectId}/assets`
- `DELETE /v1/projects/{projectId}/assets/{assetId}`
- `POST /v1/projects/{projectId}/analysis-runs`
- `PATCH /v1/projects/{projectId}/attributes/{attributeId}`
- `GET /v1/projects/{projectId}/questions/next`
- `POST /v1/projects/{projectId}/questions/{questionId}/answer`
- `POST /v1/projects/{projectId}/designer-reviews`
- `POST /v1/projects/{projectId}/conflicts/{conflictId}/resolve`
- `GET /v1/projects/{projectId}/briefs/latest`
- `PATCH /v1/projects/{projectId}/briefs/{version}`
- `POST /v1/projects/{projectId}/briefs/{version}/approvals`

State-changing requests use this envelope:

```json
{
  "idempotencyKey": "client-generated-uuid",
  "expectedStateVersion": 7,
  "data": {}
}
```

Errors use a stable code, human-readable message, correlation ID, recoverability flag, and safe details. Provider diagnostics never appear in public responses.

## 10. Persistence

SQLite stores these domain tables:

- `projects`
- `project_members`
- `image_assets`
- `attributes`
- `constraints`
- `questions`
- `conflicts`
- `brief_versions`
- `approvals`
- `audit_events`
- `idempotency_records`
- `workflow_checkpoints`

The repository assembles a `ProjectState` projection for graph execution. All accepted domain changes, audit records, and version increments are committed transactionally. Checkpoints contain workflow-control information and reference the canonical project version.

## 11. Error Handling and Safety

The API distinguishes validation, authorization, stale-version, idempotency, provider, policy, and internal errors. Recoverable failures preserve the last committed state.

Provider output is parsed into a typed schema, repaired at most once, and rejected if it remains invalid. A model step has at most two attempts. A conflict has at most two resolution loops before human escalation. The homeowner question budget is ten.

Images, metadata, URLs, retrieved text, and user text are untrusted content. They may be recorded as quoted evidence but cannot modify policy, permissions, project identity, model configuration, or tool access. Agents use allow-listed operations and project-scoped data only.

Structural, electrical, regulatory, safety-critical, exact-price, and live-availability assertions are blocked or converted into professional-review tasks. Original image content, secrets, and sensitive personal data are excluded from logs. Manual state editing remains available through authorized API operations when a provider is unavailable.

## 12. Testing Strategy

Implementation follows test-driven development with pytest. Tests use deterministic providers and temporary SQLite databases.

### Unit tests

- Sparse attribute creation and source/status semantics.
- Patch permission and precedence rules.
- State transitions, question scoring, repetition limits, and conflict loops.
- Brief versioning, content hashing, approval invalidation, and approval invariant.
- Idempotency and optimistic concurrency.
- Schema and blocked-topic checks.

### Workflow tests

- Complete happy path from assets to dual-approved brief.
- Broad element-discovery question followed by selected detail questions.
- Budget or feasibility conflict routed to both humans and resolved.
- Explicit unresolved stop when the question budget is exhausted.
- Professional escalation.
- Invalid provider output and bounded repair.
- Prompt-injection evidence that cannot alter tools, recipients, or project scope.
- Review repair loop and manual-provider fallback.

### API tests

- Every endpoint's success and typed error responses.
- Membership and role isolation.
- Consent before image analysis.
- Human correction and rejection of proposed attributes.
- Project and asset deletion across domain records and workflow checkpoints.
- Stale writes, repeated idempotency keys, and concurrent edits.
- Resume behavior for homeowner, designer, and professional waits.

## 13. Acceptance Criteria

The backend MVP is accepted when:

- A deterministic test project completes the full workflow and produces a schema-valid brief.
- Explicit homeowner preferences become `confirmed`; visual-only observations remain `proposed` until a human confirms them.
- Ordinary unmentioned attributes do not create records.
- The workflow asks broad element-discovery questions before drilling into unmentioned details and asks no more than ten homeowner questions.
- Designer constraints remain distinct from preferences, and critical conflicts are never silently resolved.
- Invalid, unsafe, unauthorized, or stale patches cannot alter canonical state.
- Asset and project deletion remove active domain data and invalidate associated workflow checkpoints while retaining only policy-permitted minimal audit metadata.
- Every accepted state change is versioned, idempotent, and audited.
- Editing a brief invalidates earlier approvals.
- The project becomes approved only after both roles approve the same version and hash.
- Unit, workflow, and API test suites pass without dependence on network access or model credentials.

## 14. Evolution After Backend Acceptance

After this backend is accepted, the next increments are a real provider adapter, then a frontend, then competition-environment deployment. Those increments reuse the same agent contracts, workflow routing, API surface, and repositories. Generated design visualisations remain outside this design and require a separate design review before they are introduced.
