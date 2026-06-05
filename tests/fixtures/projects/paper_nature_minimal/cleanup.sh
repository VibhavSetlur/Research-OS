#!/usr/bin/env bash
# Reset workspace/ + synthesis/ before each stress run.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
rm -rf "$HERE/workspace" "$HERE/synthesis" "$HERE/.os_state"
mkdir -p "$HERE/workspace" "$HERE/synthesis"
