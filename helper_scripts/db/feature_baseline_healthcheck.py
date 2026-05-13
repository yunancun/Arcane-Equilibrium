#!/usr/bin/env python3
"""Run only the W-AUDIT-4b feature baseline readiness healthcheck.

This is the lightweight companion used by
``helper_scripts/cron/feature_baseline_writer_cron.sh`` after the writer runs.
The full passive healthcheck also registers the same logic as check [67].
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SRV_ROOT = _HERE.parents[1]
if str(_SRV_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRV_ROOT))

from helper_scripts.db.passive_wait_healthcheck.checks_feature_baseline import (  # noqa: E402
    check_67_feature_baseline_readiness,
)
from helper_scripts.db.passive_wait_healthcheck.db import _get_conn  # noqa: E402


def main() -> int:
    try:
        conn = _get_conn()
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL [67] feature_baseline_readiness DB connect failed: {type(exc).__name__}: {exc}")
        return 2

    try:
        with conn.cursor() as cur:
            status, msg = check_67_feature_baseline_readiness(cur)
    finally:
        conn.close()

    print(f"{status:4s} [67] feature_baseline_readiness {msg}")
    return 1 if status == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
