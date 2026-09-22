# DeepSeek Asset ID Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent DeepSeek from persisting candidate preferences against fabricated or mismatched image IDs.

**Architecture:** Bind each image block to its real asset ID in the request, then validate model output against the request before the result crosses the provider boundary. Reuse the existing one-repair-attempt flow and reject unresolved violations atomically.

**Tech Stack:** Python 3.12, Pydantic, pytest, DeepSeek-compatible chat completions.

## Global Constraints

- Do not expose API keys or image bytes in logs or errors.
- Do not silently map an unknown model-supplied ID to an input image.
- Preserve the existing single repair attempt and local-write atomicity.
- Preserve the six pre-existing uncommitted files and exclude them from commits.

---

### Task 1: Lock the request and response contract with failing tests

**Files:**
- Modify: `tests/unit/providers/test_deepseek_contract.py`

**Interfaces:**
- Consumes: `DeepSeekPreferenceAnalysisProvider.analyze(request)`.
- Produces: regression coverage for image labels, unknown IDs, and evidence mismatch.

- [ ] Add a two-image request assertion that each image is immediately associated with its exact `assetId` in text content.
- [ ] Add a test where the first response uses `asset-1` for a UUID request and the repair response uses the UUID; assert two calls and a valid result.
- [ ] Add tests where both responses use an unknown ID or mismatched image evidence; assert `ProviderOutputError`.
- [ ] Run `uv run pytest -q tests/unit/providers/test_deepseek_contract.py` and confirm the new tests fail for the intended reasons.

### Task 2: Implement request-bound semantic validation

**Files:**
- Modify: `src/alignspace/providers/deepseek.py`
- Test: `tests/unit/providers/test_deepseek_contract.py`

**Interfaces:**
- Consumes: `PreferenceAnalysisRequest.assets` and parsed `PreferenceAnalysisResult`.
- Produces: `_validate(request, response)` that returns only request-consistent results.

- [ ] Replace the literal example ID with `<provided-asset-id>` and add an explicit allow-list rule to the system prompt.
- [ ] Emit `Reference image assetId: <id>` immediately before each image content block.
- [ ] Pass the request into `_validate`; reject unknown entry IDs and mismatched image evidence with `ProviderOutputError`.
- [ ] Include allowed IDs and the semantic error in the repair instruction without including image bytes or credentials.
- [ ] Run the provider contract tests and confirm they pass.

### Task 3: Verify regression scope and document the corrected live boundary

**Files:**
- Modify: `docs/references/deepseek.md`
- Test: backend and frontend suites.

**Interfaces:**
- Consumes: the corrected provider contract.
- Produces: current integration documentation and verification evidence.

- [ ] Document explicit asset-ID labels and request-bound output validation.
- [ ] Run `uv run pytest -q tests/unit/providers/test_deepseek_contract.py tests/api/test_preference_analyses.py`.
- [ ] Run `uv run ruff check src tests scripts`.
- [ ] Run the complete backend suite, frontend unit suite, and frontend build.
- [ ] Report real DeepSeek re-test separately; do not call it unless the user has already authorized the paid call.

