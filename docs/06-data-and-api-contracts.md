# Data and API Contracts

Canonical briefs validate against [`schemas/design-brief.schema.json`](../schemas/design-brief.schema.json). This defines boundaries, not a final OpenAPI implementation.

## Entities

| Entity | Key fields | Owner |
|---|---|---|
| Project | id, roomType, status, retention, members | Project service |
| ImageAsset | id, objectKey, provenance, consent, status | Asset service |
| Attribute | dimension, value, status, confidence, evidence | Brief service |
| Constraint | category, statement, severity, verification | Designer review |
| Question | target, rationale, options, answer | Interview agent |
| Conflict | type, positions, impact, resolution | Alignment agent |
| BriefVersion | version, schemaVersion, hash, completeness | Brief service |
| Approval | role, actor, version, hash, timestamp | Approval service |
| AuditEvent | actor, action, resource, before/after hash | Audit service |

## Status semantics

Attribute: `proposed`, `confirmed`, `rejected`, `conflicted`, `unresolved`, `not_applicable`.

Project: `draft → analysing → homeowner_review → designer_review → alignment → awaiting_approval → approved → archived`.

Editing an approved brief creates a new version and returns to `awaiting_approval`.

## API surface

### Projects and assets

- `POST /v1/projects`
- `GET /v1/projects/{projectId}`
- `POST /v1/projects/{projectId}/members`
- `DELETE /v1/projects/{projectId}`
- `POST /v1/projects/{projectId}/assets:prepare-upload`
- `POST /v1/projects/{projectId}/assets/{assetId}:complete`
- `DELETE /v1/projects/{projectId}/assets/{assetId}`

### Workflow

- `POST /v1/projects/{projectId}/analysis-runs`
- `GET /v1/projects/{projectId}/analysis-runs/{runId}`
- `GET /v1/projects/{projectId}/questions/next`
- `POST /v1/projects/{projectId}/questions/{questionId}/answer`
- `POST /v1/projects/{projectId}/designer-reviews`
- `POST /v1/projects/{projectId}/conflicts/{conflictId}/resolve`

### Brief

- `GET /v1/projects/{projectId}/briefs/latest`
- `PATCH /v1/projects/{projectId}/briefs/{version}`
- `POST /v1/projects/{projectId}/briefs/{version}/approvals`
- `POST /v1/projects/{projectId}/briefs/{version}/exports`

## Write envelope

```json
{
  "idempotencyKey": "client-generated-uuid",
  "expectedStateVersion": 7,
  "data": {},
  "clientTimestamp": "2026-09-06T12:00:00+08:00"
}
```

Server time is authoritative. Reusing a key with different content returns `409`.

## Error shape

```json
{
  "error": {
    "code": "BRIEF_VERSION_STALE",
    "message": "The brief changed while you were editing it.",
    "correlationId": "01J...",
    "recoverable": true,
    "details": { "latestVersion": 4 }
  }
}
```

Provider details stay in restricted diagnostics.

## Approval invariant

Approved only when both roles approve the same brief version and content hash, neither approval is revoked, and no critical conflict is open. Backend enforces this.

## Retention

Default pilot hypothesis: project duration +30 days. Deletion covers originals, thumbnails, exports, cache, database, and search copies. Minimal audit records may follow a documented policy but never retain image content.

