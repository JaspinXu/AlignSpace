# AlignSpace UI refresh

This records the first editorial iteration. The current visual direction and Singapore discovery experience are documented in [19-singapore-discovery.md](19-singapore-discovery.md).

The interface keeps the original headline: **Make “I like this” clear enough to design.**
The project entry also says **Let’s make it clear.**

## Design references

The 13 websites discussed with the user informed the following design choices. These are design interpretations, not copied layouts or imported components.

| Reference | Application in AlignSpace |
| --- | --- |
| [Houzz](https://www.houzz.com/) | Reference notes and a shared project remain central to the workflow. |
| [Pinterest](https://www.pinterest.com/) | An inspiration board with reference previews and clear individual entries. |
| [ArchDaily](https://www.archdaily.com/category/residential-interiors) | Clear project metadata and structured design information. |
| [Architectural Digest](https://www.architecturaldigest.com/) | Editorial headline hierarchy and a prominent room photograph. |
| [Dwell](https://www.dwell.com/) | Restrained typography, whitespace and a residential focus. |
| [Apartment Therapy](https://www.apartmenttherapy.com/) | Welcoming language grounded in everyday life. |
| [Planner 5D](https://planner5d.com/) | A clear next step and visible decision progress; no new 3D capability implied. |
| [Homestyler](https://www.homestyler.com/) | Visual comparison of design directions through illustrative palettes. |
| [Audo Copenhagen](https://audocph.com/) | Warm ivory, olive accents, serif titles and restrained card chrome. |
| [ferm LIVING](https://www.fermliving.com/) | Large lifestyle photography and a simple invitation to explore. |
| [Studio McGee](https://www.studio-mcgee.com/) | Muted green navigation accents and warm editorial sections. |
| [Norm Architects](https://normcph.com/) | Quiet architectural imagery and natural material emphasis. |
| [FRAMA](https://framacph.com/) | Split layouts, thin rules and rectangular controls. |

## Implementation

- Landing page: split hero, accessible material detail toggle, three-step process, separate project entry and saved projects.
- Workspace: confirmed preference ribbon, illustrative colour swatches, expandable matching explanations, source image tags and style cues and clearer role guidance.
- Shared brief: paper-like document layout with a separate approval area.
- Responsive layouts at 900px and 620px; keyboard focus, skip link and reduced-motion support.
- Navigation returns to the landing page without reloading. Opening another project resets the active workspace view.
- Local system fonts; no remote font or image dependency. Backend contracts and approval rules are unchanged.

## Original image

- File: `app/static/living-room.png` (1536 × 1024).
- Generated with the built-in image generation tool on 2026-09-13; not sourced from the reference websites.
- Labelled “AI-created inspiration” on the page. It is a decorative example, not a user reference or a generated project proposal.
- Final prompt:

> Use case: photorealistic-natural. Asset: original editorial interior photograph for AlignSpace interior design website hero. Wide landscape 3:2 composition. A beautifully restrained warm modern living room: cream linen low sofa on right, sculptural low oak coffee table with ceramic bowl center, dark olive accent lounge chair on left, floor-to-ceiling sheer curtains and sunlight on left, textured ivory plaster walls, one abstract neutral artwork, warm oak flooring and woven natural rug. Realistic modest apartment scale, serene afternoon light, tactile natural materials, refined architecture magazine photography with subtle film grain. Palette ivory, walnut, olive, sand. No people, text, logos, watermarks or collage. Camera at eye level, believable geometry, polished photo.

## Verification

- Existing automated suite: 32 tests passed.
- Browser checks use a separate `tmp/ui-review.db` database and offline analysis mode on port 8011.
- Desktop: landing page, material hint, project entry, project creation, preference answer, confirmed ribbon and shared brief.
- Mobile: responsive homepage and workspace, brief layout, activity view and horizontal overflow checks.
- No live model inference or production data changes were required.
