"""Source-static 守衛:LR1(S2.2A)learning_runtime_manifest SSOT 模塊。

固定兩件事,任一被靜默改動即紅燈:
  1. 模塊源碼「無」下單 / PG 寫入 / Bybit / fetch / git-mutation token(source-only、
     NONE-effect 邊界)。
  2. digest 涵蓋面的「凍結 allowlist」——期望檔集 + metadata-projection sha256;任何對
     「digest 涵蓋什麼」的靜默增刪都會讓 projection sha 變動而被攔下。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_REL = "program_code/ml_training/learning_runtime_manifest.py"
MODULE = ROOT / MODULE_REL

# 凍結的 metadata-projection sha256(見下方 _projection());任何 allowlist 改動即需
# 同步刷新此值並經 review。
EXPECTED_PROJECTION_SHA256 = (
    "c1489a8798244b57d67c3e4e5ba1bf4b5b6b88c09f66a6c9915d9911704462d6"
)

# NONE-effect 邊界:下單 / PG 寫入 / Bybit / fetch / git-mutation 一律禁。git rev-parse
# 是唯讀,允許;但任何 git 變異動詞(以 subprocess arg 字面或 "git <verb>" 形式)禁。
FORBIDDEN_TOKENS = (
    # 下單 / 執行
    "place_order",
    "submit_order",
    "create_order",
    "cancel_order",
    "replace_order",
    "OrderManager",
    "order_router",
    "CreateOrderRequest",
    # PG 寫入
    "psycopg2",
    "cursor(",
    "INSERT INTO",
    "UPDATE ",
    "DELETE FROM",
    "COPY ",
    ".commit(",
    # 交易所
    "bybit",
    "Bybit",
    "ibkr",
    "IBKR",
    # 網路抓取
    "fetch",
    "requests.",
    "urllib",
    "httpx",
    # git 變異(唯讀 rev-parse 例外)
    "git commit",
    "git push",
    "git reset",
    "git checkout",
    "git merge",
    "git rebase",
    "git apply",
    "git fetch",
    "git pull",
    "git clone",
    '"commit"',
    '"push"',
    '"reset"',
    '"checkout"',
    '"merge"',
    '"rebase"',
    '"apply"',
)


def _source() -> str:
    return MODULE.read_text(encoding="utf-8")


def _projection() -> dict[str, object]:
    """從模塊 import allowlist 常量,建 canonical projection(與凍結 sha 對應)。"""
    if str(ROOT / "program_code") not in sys.path:
        sys.path.insert(0, str(ROOT / "program_code"))
    from ml_training import learning_runtime_manifest as lrm

    return {
        "capture_inputs": sorted(lrm.CAPTURE_INPUTS),
        "learning_code_inputs": sorted(lrm.LEARNING_CODE_INPUTS),
        "migration_inputs": sorted(lrm.MIGRATION_INPUTS),
        "regime_oos_label_contract": lrm.REGIME_OOS_LABEL_CONTRACT,
        "policy_template": lrm.POLICY_TEMPLATE,
        "dependency_lock_file": lrm.DEPENDENCY_LOCK_FILE,
        "policy_config_keys": sorted(lrm.POLICY_CONFIG_KEYS),
        "label_lineage_required_fields": sorted(lrm.LABEL_LINEAGE_REQUIRED_FIELDS),
        "runtime_config_template_keys": sorted(lrm._RUNTIME_CONFIG_TEMPLATE_KEYS),
        "snapshot_feature_schema_version": lrm.SNAPSHOT_FEATURE_SCHEMA_VERSION,
    }


def test_module_exists_and_stays_source_only() -> None:
    assert MODULE.is_file(), f"missing SSOT module {MODULE_REL}"


def test_module_has_no_effect_or_git_mutation_tokens() -> None:
    source = _source()
    violations = [token for token in FORBIDDEN_TOKENS if token in source]
    assert violations == [], f"forbidden tokens present: {violations}"
    # rev-parse 是允許的唯讀 git 用途——確認它就是模塊唯一的 git 觸點。
    assert "rev-parse" in source


def test_frozen_allowlist_projection_is_pinned() -> None:
    projection = _projection()
    blob = json.dumps(projection, sort_keys=True, separators=(",", ":")).encode("utf-8")
    actual = hashlib.sha256(blob).hexdigest()
    assert actual == EXPECTED_PROJECTION_SHA256, (
        "learning_runtime_manifest allowlist changed; review the new digest coverage "
        f"then update EXPECTED_PROJECTION_SHA256 to {actual}"
    )


def test_allowlisted_inputs_reference_real_repository_files() -> None:
    projection = _projection()
    referenced = [
        *projection["capture_inputs"],
        *projection["learning_code_inputs"],
        *projection["migration_inputs"],
        projection["regime_oos_label_contract"],
        projection["policy_template"],
        projection["dependency_lock_file"],
    ]
    missing = [rel for rel in referenced if not (ROOT / rel).is_file()]
    assert missing == [], f"allowlist references non-existent files: {missing}"


def test_migration_allowlist_is_exactly_v151_to_v160() -> None:
    projection = _projection()
    versions = sorted(
        Path(rel).name.split("__", 1)[0] for rel in projection["migration_inputs"]
    )
    assert versions == [f"V{index}" for index in range(151, 161)]
