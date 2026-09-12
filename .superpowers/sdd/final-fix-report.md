# Final Fix Report — Image Upload Storage

## Status

All findings from `final-fix-brief.md` are addressed.

## Changes

- Added post-commit, database-reference-counted storage GC for asset and project deletion. Soft-deleted assets clear their storage reference, while all remaining rows (including tombstones) protect shared content-addressed bytes.
- Added migration 3, which tombstones legacy asset payloads without `storage_key`; hardened project and workflow asset views for legacy payload fields.
- Applied fixed-window upload throttles (20/user/minute, 60/IP/minute) and pass request metadata through upload validation.
- Validated declared MIME type and recognized filename extensions against sniffed image content.
- Reject unrecognized non-empty filename extensions before accepting sniffed image content; preserved recognized-extension contradiction checks and extensionless filename behavior.
- Made reference-image lists/thumbnails visible to designers while retaining homeowner-only upload, delete, and analysis controls.

## Tests

- `uv run --no-sync pytest tests/api/test_asset_upload.py -q` — 12 passed
- `uv run --no-sync pytest -q` — 185 passed
- `uv run --no-sync ruff check src tests` — passed
- `cd frontend && npm test && npm run build` — 47 tests passed; build passed

## Concerns

- No outbox/queue was introduced; the existing `Storage` interface and content-addressed keys remain unchanged.
- Mock vision observation cardinality was not changed.
- The IP throttle's 60-request threshold was not exercised because it would add an intentionally expensive request loop; the existing per-account throttle coverage remains.
