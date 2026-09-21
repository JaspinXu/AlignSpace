#!/usr/bin/env bash
# Fetch the pinned upstream OpenPlan3D source for the local 3D preview.
#
# This does NOT vendor the upstream tree into git and never contacts an upstream
# cloud service. After checkout the script neutralises the upstream Firebase
# analytics bootstrap, so running the editor locally cannot phone home. Our own
# frontend only ever sends project geometry to the local editor over an
# origin-checked postMessage.
set -euo pipefail

UPSTREAM_URL="https://github.com/laanlabs/openPlan3D"
PINNED_SHA="d68cadf703578f2cd3a7c77f820e18d342580c32"
TARGET="${1:-vendor/openplan3d/upstream}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRIDGE_SRC="$SCRIPT_DIR/../vendor/openplan3d/bridge/alignspaceBridge.ts"

if [ -d "$TARGET/.git" ]; then
  echo "Updating existing checkout at $TARGET"
  git -C "$TARGET" fetch --quiet origin "$PINNED_SHA"
else
  echo "Cloning $UPSTREAM_URL into $TARGET"
  git clone --quiet "$UPSTREAM_URL" "$TARGET"
fi

git -C "$TARGET" checkout --quiet "$PINNED_SHA"
ACTUAL="$(git -C "$TARGET" rev-parse HEAD)"
if [ "$ACTUAL" != "$PINNED_SHA" ]; then
  echo "Refusing to continue: expected $PINNED_SHA but checked out $ACTUAL" >&2
  exit 1
fi

# Local hardening: replace the analytics bootstrap with an inert local module.
cat > "$TARGET/src/lib/firebase.ts" <<'EOF'
// Local AlignSpace hardening: the upstream analytics bootstrap is replaced with
// an inert module so the local 3D preview never contacts Firebase/Google.
export const app = null;
export const analytics = Promise.resolve(null);
EOF

# Local hardening: the upstream cloud share importer must never reach Google
# Storage. Point it at an unsupported local scheme so the fetch fails offline.
python3 - "$TARGET" <<'PY'
import pathlib
import sys

target = pathlib.Path(sys.argv[1])
page = target / "src/routes/editor/+page.svelte"
text = page.read_text()
cloud = "https://firebasestorage.googleapis.com"
if cloud in text:
    text = text.replace(
        "`https://firebasestorage.googleapis.com/v0/b/openplan3d.firebasestorage.app/o/inbox%2F${code}.json?alt=media`",
        "'local://disabled-upstream-share'",
    )
    page.write_text(text)
PY

if grep -RInE "google-analytics\.com|googletagmanager\.com|firebaseapp\.com|firebaseio\.com|firebasestorage\.googleapis\.com" \
  "$TARGET/src" >/dev/null 2>&1; then
  echo "Cloud endpoint reference still present under $TARGET/src; refusing to continue." >&2
  exit 1
fi

# Install the AlignSpace bridge (import + edit-back) into the pinned editor.
cp "$BRIDGE_SRC" "$TARGET/src/lib/alignspaceBridge.ts"
python3 - "$TARGET" <<'PY'
import pathlib
import sys

target = pathlib.Path(sys.argv[1])
page = target / "src/routes/editor/+page.svelte"
text = page.read_text()
if "startAlignSpaceBridge" not in text:
    text = text.replace(
        "import { onMount } from 'svelte';",
        "import { onMount } from 'svelte';\n  import { startAlignSpaceBridge } from '$lib/alignspaceBridge';",
        1,
    )
    text = text.replace(
        "onMount(() => {\n    void initializeEditor();",
        "onMount(() => {\n    startAlignSpaceBridge();\n    void initializeEditor();",
        1,
    )
    page.write_text(text)
PY
if ! grep -q "startAlignSpaceBridge" "$TARGET/src/routes/editor/+page.svelte"; then
  echo "AlignSpace bridge injection failed; refusing to continue." >&2
  exit 1
fi

echo "OpenPlan3D pinned at $ACTUAL and hardened for offline local use."
echo "Next: read docs/references/openplan3d.md for the local, cloud-free start procedure."
