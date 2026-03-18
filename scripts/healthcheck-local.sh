#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json, urllib.request, sys
url='http://127.0.0.1:8000/health'
try:
    with urllib.request.urlopen(url, timeout=3) as r:
        print(json.dumps(json.loads(r.read().decode()), indent=2))
except Exception as e:
    print(f'Chef Claw health check failed: {e}', file=sys.stderr)
    sys.exit(1)
PY
