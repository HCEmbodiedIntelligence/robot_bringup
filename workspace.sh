#!/usr/bin/env bash
set -euo pipefail
entry_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec /usr/bin/python3 "${entry_dir}/scripts/workspace.py" "$@"
