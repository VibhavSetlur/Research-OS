#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
rm -rf workspace synthesis .os_state
echo "qualitative_interviews reset"
