# OpenPlan3D upstream provenance

- Upstream repository: https://github.com/laanlabs/openPlan3D
- Pinned commit SHA: `d68cadf703578f2cd3a7c77f820e18d342580c32`
- Upstream package name/version at pin: `open3dfloorplan` 0.9.0
- License: MIT (see `LICENSE` in this directory, copied verbatim from the pin)
- Model/texture attribution: see `MODEL_SOURCES.md` (copied verbatim from the pin)

The upstream source tree is **not** committed to this repository. Run
`scripts/fetch_openplan3d.sh` to check out the pinned commit into
`vendor/openplan3d/upstream/` (git-ignored) and to apply the offline hardening
that removes the upstream Firebase analytics bootstrap and the Google Storage
share importer. The 3D preview connects only to a local origin and never sends
project data to an upstream cloud service.
