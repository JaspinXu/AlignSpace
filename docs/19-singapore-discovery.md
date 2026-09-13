# Singapore discovery and visual refresh

The current interface replaces the cream/olive editorial direction with vivid purple, blue, lime and coral, bold sans-serif type, rounded photo cards and distinct content sections. The original “Make ‘I like this’ clear enough to design” headline and “Let’s make it clear” project entry are retained.

## Experience

Browse real Singapore renovation projects before starting a living-room brief. Search by project, town, style or designer; filter by HDB/BTO, resale HDB, condo, landed and published cost; sort by cost or completion year. Save up to six projects locally and compare up to three in an accessible dialog. Details include area, completed year, designer, published cost, listed works, original source and an AlignSpace discussion prompt.

The budget section provides whole-home planning ranges, duration and an optional arithmetic allowance. It does not change the separate living-room budget. Local guidance links to HDB flat types, renovation contractors and Singapore climate information. Saved source links can be imported on project creation; the server validates catalogue IDs and consent and never infers confirmed preferences from a saved home.

## Sources and maintenance

The manually curated snapshot is in `app/static/singapore.json`, checked on 13 September 2026. This is a collection of renovation case studies, not a live property-sales feed. Published project costs are historical, refer to different scopes and exclude no items by assumption. Furniture, appliance and tax inclusions are unverified. Garden Vines has no published price and remains null, including in sorting and comparison.

Every project source URL, designer credit, image URL and completion year is recorded in the JSON and exposed in the UI. The seven projects are Tampines Street 61, Waterway View 682A, View at Kismis, Champions Bliss 562B, Garden Vines 236B, Smith Road and Dunsfold Drive, published on Qanvast. Photos load directly from Qanvast’s CDN with no referrer; no third-party photos were copied into the repository. Their ownership remains with their creators. Image failure leaves a fallback and original-source link. CSP allows only this specific image host in addition to local/blob images.

- [Qanvast HDB renovation costs, 2026](https://qanvast.com/sg/articles/what-are-the-expected-renovation-costs-for-hdb-flats-in-2026-3568), published 12 February 2026: new and resale 3-, 4- and 5-room ranges.
- [Qanvast condo renovation costs, 2025](https://qanvast.com/sg/articles/singapore-condo-renovation-costs-new-and-resale-in-2025-3389), published 24 January 2025: explicitly labelled 2025 rather than presented as current-year figures.
- [HDB flat types](https://www.hdb.gov.sg/buying-a-flat/bto-sbf-and-open-booking-of-flats/finding-a-new-flat/types-of-flats).
- [Meteorological Service Singapore climate facts](https://www.weather.gov.sg/climate-climate-of-singapore/): approximately 82% mean annual relative humidity. Material and airflow discussion prompts are AlignSpace editorial suggestions.
- [HDB renovation contractor guidance](https://www.hdb.gov.sg/managing-my-home/renovation-and-maintenance/renovation/looking-for-renovation-contractors).

To update, verify original pages, revise records and their dates, and keep unknown values null. Update the homepage source-check text alongside `checkedAt`. Do not silently replace historical completion dates with retrieval dates. The earlier generated room image is retained as an unused first-iteration asset.

## Verification

Automated tests cover validated/consented import, deduplication, source persistence, unchanged confirmed preferences and room budget, project access isolation, invalid input and catalogue consistency. Browser checks cover image loading, filters, empty state, saving across reload, comparison, unavailable price, budget calculations and source years, and creating a brief from a saved case. Responsive checks include 320px and 390px viewports.
