#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
# Preserve the pre-built workspace (it's the whole point of this fixture).
rm -rf .os_state synthesis
echo "mid_pipeline_handoff reset (workspace preserved by design)"
