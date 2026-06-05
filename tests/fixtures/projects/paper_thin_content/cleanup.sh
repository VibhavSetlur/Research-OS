#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
rm -rf "$HERE/workspace" "$HERE/synthesis" "$HERE/.os_state"
mkdir -p "$HERE/workspace" "$HERE/synthesis"
