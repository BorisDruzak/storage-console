#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=deploy/scripts/common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
exec python3 -m deploy.scripts.backup backup "$@"
