#!/usr/bin/env python3
"""S2.5(WP5)CLI 入口——與 ``agent_governance_s2_4_install.py`` 同級的新入口(不改其 owned 檔)。

verbs(全部離線、零 runtime 接觸;design §7):

* ``start-core``    —— 由參數組出 unsigned ``s2_5_start_core_v1`` 並列印;
* ``start-intent``  —— 讀 core JSON 檔,組出 closed ``s2_5_start_intent_v1`` 並列印;
* ``validate``      —— 把任一 s2_5 artifact 檔丟中央閘(``--now`` 必帶;過期 fail-closed);
* ``apply-start`` / ``apply-final`` —— source lane 施加:**永遠 driver=None**,零變更。
  note-3(tranche 2)對齊:本 CLI **沒有** permit/precheck-evidence/lock-probe 注入縫,
  而 typed ``EXTERNAL_VERIFICATION_PENDING`` 位於 §3.1 靜態 precheck 與 §5.6 授權**之後**
  ——所以從本 CLI 出發,apply 動詞的可達終點只有 typed ``REQUEST_REJECTED`` /
  ``AUTHORIZATION_REJECTED`` / ``RECOVERY_REQUIRED``(exit 2)。
  ``EXTERNAL_VERIFICATION_PENDING``(exit 0)是 lifecycle 葉的誠實終點,只在 EFFECT
  session(OPS 以 in-process API 注入完整 precheck 證據 + 已簽 permit + lock probe,
  driver 仍缺席)時可達;exit-0 分支保留給那條 lane,不是本 CLI 平常會走到的路。

⚠ 誠實邊界:本 CLI 只做離線結構/整合檢查,不能認證任何 runtime PASS;乾淨輸出「不」代表
unit 真的 enabled/running。九項 authority 恆 false。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_validator as central_validator  # noqa: E402
import agent_governance_s2_5_lifecycle as lifecycle  # noqa: E402


def _print(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)

    core_parser = sub.add_parser("start-core", help="組出 unsigned s2_5_start_core_v1")
    core_parser.add_argument("--phase", required=True, choices=["S2_5A_START", "S2_5B_FINAL"])
    core_parser.add_argument("--target-host", required=True)
    core_parser.add_argument("--unit-fragment-digest", required=True)
    core_parser.add_argument("--s2-4-receipt-digest", required=True)
    core_parser.add_argument("--launch-bundle-digest", required=True)
    core_parser.add_argument("--application-bundle-digest", required=True)
    core_parser.add_argument("--base-runtime-tree-digest", required=True)
    core_parser.add_argument("--native-loader-closure-digest", required=True)
    core_parser.add_argument("--s2-1-drill-receipt-digest", default=None)
    core_parser.add_argument("--pre-drill-attestation-digest", default=None)
    core_parser.add_argument("--source-head", required=True)
    core_parser.add_argument("--issued-at", required=True)
    core_parser.add_argument("--expires-at", required=True)

    intent_parser = sub.add_parser("start-intent", help="由 core JSON 組出 closed intent")
    intent_parser.add_argument("--core", required=True, type=Path)
    intent_parser.add_argument("--expires-at", required=True)

    validate_parser = sub.add_parser("validate", help="中央閘驗一份 s2_5 artifact(--now 必帶)")
    validate_parser.add_argument("--artifact", required=True, type=Path)
    validate_parser.add_argument("--now", required=True)

    for verb in ("apply-start", "apply-final"):
        apply_parser = sub.add_parser(
            verb,
            help="source lane 施加(恆 driver=None;CLI 無 permit/evidence 注入縫 ⇒ "
            "可達終點是 typed 拒絕/recovery 臂,零變更)",
        )
        apply_parser.add_argument("--intent", required=True, type=Path)
        apply_parser.add_argument("--now", required=True)

    args = parser.parse_args(argv)
    if args.action == "start-core":
        _print(lifecycle.build_s2_5_start_core(
            phase=args.phase,
            target_host=args.target_host,
            expected_unit_fragment_digest=args.unit_fragment_digest,
            s2_4_install_effect_receipt_digest=args.s2_4_receipt_digest,
            expected_launch_bundle_digest=args.launch_bundle_digest,
            expected_application_bundle_digest=args.application_bundle_digest,
            expected_base_runtime_tree_digest=args.base_runtime_tree_digest,
            native_loader_closure_digest=args.native_loader_closure_digest,
            s2_1_drill_receipt_digest=args.s2_1_drill_receipt_digest,
            pre_drill_attestation_digest=args.pre_drill_attestation_digest,
            source_head=args.source_head,
            issued_at=args.issued_at,
            expires_at=args.expires_at,
        ))
        return 0
    if args.action == "start-intent":
        _print(lifecycle.build_s2_5_start_intent(
            _load_json(args.core), expires_at=args.expires_at
        ))
        return 0
    if args.action == "validate":
        errors = central_validator.validate_aiml_artifact(
            _load_json(args.artifact), now=args.now
        )
        _print({"status": "PASS" if not errors else "REJECTED", "errors": errors})
        return 0 if not errors else 2
    if args.action in {"apply-start", "apply-final"}:
        applier = (
            lifecycle.apply_s2_5_start
            if args.action == "apply-start"
            else lifecycle.apply_s2_5_final
        )
        # CLI 沒有 driver 注入縫:恆 driver=None(reachable 但 authority-locked)。
        verdict = applier(_load_json(args.intent), None, None, now=args.now)
        _print(verdict)
        return 0 if verdict["status"] == lifecycle.S2_5_STATUS_PENDING else 2
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
