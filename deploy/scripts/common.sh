#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
DEPLOY_ROOT=$(cd -- "$SCRIPT_DIR/../.." && pwd -P)
export PYTHONPATH="$DEPLOY_ROOT${PYTHONPATH:+:$PYTHONPATH}"

deployment_command() {
  exec python3 -m deploy.scripts.lifecycle "$@"
}
