# Visual discovery for design alignment

The homepage starts with 57 lightweight, attributed previews from Singapore home projects. Each card foregrounds the image, source-labelled style, image tags and a style observation prompt. The prompt is editorial guidance about what to notice, not an assertion that every listed feature appears in the photograph. Home type, area, designer and source remain available; detail views also show completion year and photographed rooms where supplied.

Search locally by words and style, filter by home type, or select **Search more homes** to retrieve the first results from the wider [Qanvast project collection](https://qanvast.com/sg/interior-design-singapore). The app displays those previews directly and links to the complete matching source selection. It does not claim to have loaded every source result. **Show more homes** reveals additional local previews, 12 at a time.

Save up to six references and compare up to three by image, style cues, source tags and spaces. Add saved sources to a new brief with consent, then specify exactly which details to keep or change. Saving a reference never confirms a preference. The server owns source metadata; callers cannot inject arbitrary external URLs into the import flow.

## Source adapter

`app/discovery.py` reads the public server-rendered listing, parses its embedded JSON as data, and selects only preview fields. It never executes source JavaScript, imports a remote page into our DOM, or downloads image files. Images load from the attributed source CDN. Fixed hosts, HTTPS, redirect refusal, a 2 MB response ceiling, a 12-second request timeout and two concurrent fetch slots bound source access. Queries are at most 100 characters; supported style and home-type values are explicit.

Repeated searches use a 15-minute in-process cache with at most 64 entries. Up to 1,000 normalized public previews are retained in SQLite so saved IDs survive restarts. Imported projects embed their own source details independently. An old unimported saved ID that has been evicted is removed during resolution. Upstream failure shows matching saved previews with an explicit status and source link; legitimate empty live searches remain empty.

The public listing provides the first source result batch and supports keywords, styles and home types. No private API credentials, LLM or MCP dependency are needed for this deterministic query. A future supported provider can implement the same normalized preview contract.

## Maintenance

`app/static/singapore.json` contains preview metadata only. Run `python scripts/refresh_discovery.py` to refresh selected public style collections. Review metadata and the UI before committing. Source photos remain owned by their creators and are credited individually. This small snapshot remains usable if the source changes its markup; it is not a complete mirror.

Schema 1.1.0 projects older records into supported alignment fields at startup. Source details are narrowed, obsolete constraint categories and associated conflicts are removed, and prior approvals are cleared. Identity, access membership, preferences and references are retained. The migration is audited once and requires both participants to approve the updated brief.

## Verification

Tests cover import consent and isolation, unique attributed previews, live parsing, safe source URLs, source failure, empty results, caching, persistent saved-source imports and schema migration. Browser checks cover filtering, more previews, source searches, saving, comparison, details and project creation. Source search exposes public keywords to Qanvast; private project notes and uploaded images are not sent by this adapter.
