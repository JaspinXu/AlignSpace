# Task 4 Report: SQLite Persistence, Optimistic Locking, and Idempotency

## Status

Completed against base commit `0895420`; pending the Task 4 commit at the time this report was
written.

## Changed Files

- Created `src/alignspace/persistence/__init__.py`
- Created `src/alignspace/persistence/database.py`
- Created `src/alignspace/persistence/tables.py`
- Created `src/alignspace/persistence/repository.py`
- Created `src/alignspace/persistence/uow.py`
- Created `tests/integration/persistence/test_repository.py`
- Created `tests/integration/persistence/test_concurrency.py`
- Created `.superpowers/sdd/task-4-report.md`

## TDD Evidence

1. Baseline before Task 4 changes:

   ```text
   UV_CACHE_DIR=/private/tmp/alignspace-uv-cache uv run pytest -q
   ```

   Result: `46 passed in 0.05s`.

2. RED after adding the complete focused persistence tests and before creating production
   persistence modules:

   ```text
   UV_CACHE_DIR=/private/tmp/alignspace-uv-cache uv run pytest tests/integration/persistence -v
   ```

   Result: collection stopped with the expected two errors. Both test modules raised
   `ModuleNotFoundError: No module named 'alignspace.persistence'`; zero tests were collected.

3. Focused GREEN after the minimal persistence implementation:

   ```text
   UV_CACHE_DIR=/private/tmp/alignspace-uv-cache uv run pytest tests/integration/persistence -v
   ```

   Result: `10 passed in 0.26s`.

4. Refactor verification after resolving Ruff's `PYI034` return annotation and four `SIM117`
   test-context findings:

   ```text
   UV_CACHE_DIR=/private/tmp/alignspace-uv-cache uv run pytest tests/integration/persistence -q
   UV_CACHE_DIR=/private/tmp/alignspace-uv-cache uv run ruff check src tests
   ```

   Result: `10 passed in 0.15s`; Ruff reported `All checks passed!`.

5. Full-suite verification before the final report/commit gate:

   ```text
   UV_CACHE_DIR=/private/tmp/alignspace-uv-cache uv run pytest -v
   UV_CACHE_DIR=/private/tmp/alignspace-uv-cache uv run ruff check src tests
   ```

   Result: `56 passed in 0.20s`; Ruff reported `All checks passed!`.

6. Fresh final gate after writing this report:

   ```text
   UV_CACHE_DIR=/private/tmp/alignspace-uv-cache uv run pytest -v
   UV_CACHE_DIR=/private/tmp/alignspace-uv-cache uv run ruff check src tests
   git diff --check
   ```

   Result: `56 passed in 0.21s`; Ruff reported `All checks passed!`; `git diff --check`
   exited successfully with no output.

## Self-review

- Added all 11 required tables: projects, project members, image assets, six typed entity
  projections, audit events, and idempotency records.
- The `projects` row stores only project identity and scalar canonical state. It does not store a
  duplicate whole-state JSON snapshot.
- Attributes, constraints, questions, conflicts, brief versions, and approvals are persisted as
  project-scoped typed JSON rows with stable domain identity columns and explicit positions, so
  list ordering is preserved during reconstruction.
- Full-state round-trip coverage includes evidence, timestamps, canonical brief payload/hash,
  approvals, completeness, `current_node`, and `wait_reason`.
- Project creation accepts only state version 0. Later saves require exactly
  `expected_version + 1` and conditionally update the project row by ID and expected version;
  stale writes raise `StaleStateError` before entity replacement or audit insertion.
- Creation and each accepted save append an audit event inside the repository's current
  transaction. Repositories never commit or roll back.
- `SqlAlchemyUnitOfWork` owns commit, rolls back commit failures immediately, and rolls back on
  context exit whenever commit did not succeed. The rollback test proves project, audit, and
  idempotency writes all disappear together.
- Idempotency is project-scoped and stores the canonical SHA-256 request hash, original response
  payload, and resulting version. Matching lookup returns the stored result; a different hash for
  the same key raises `IdempotencyConflictError`.
- No application service, agent workflow, API route, or unrelated domain behavior was added.

## Concerns

- `project_members` and `image_assets` are intentionally schema-only scaffolding because
  `ProjectState` does not project them yet.
- Schema migration/version-management and project-deletion APIs remain outside Task 4; this task
  uses `Base.metadata.create_all` exactly as specified for the local SQLite MVP.
