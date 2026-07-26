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
    "975edf8900a429b8c3412e0cca93451cb7eaece62830647774381d422c8b8df9"
)

# S2-WP1 additive:v2 allowlist 的獨立凍結 projection(不動上方 v1 sha)。v2 對「digest 涵蓋
# 什麼」的任何靜默增刪(learning-code v2 集、dependency_lock 兩檔、v2 schema 版本)即讓此 sha 變動。
EXPECTED_PROJECTION_V2_SHA256 = (
    "d281f3dfe68149cb58c9e6ff279d3d63f42029a6c5e7ea3b66c99f38c23da717"
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


# ── S2-WP1 additive:v2 allowlist projection 守衛 ──────────────────────────────
def _projection_v2() -> dict[str, object]:
    if str(ROOT / "program_code") not in sys.path:
        sys.path.insert(0, str(ROOT / "program_code"))
    from ml_training import learning_runtime_manifest as lrm

    return {
        "schema_version_v2": lrm.SCHEMA_VERSION_V2,
        "receipt_schema_version_v2": lrm.RECEIPT_SCHEMA_VERSION_V2,
        "learning_code_inputs_v2": sorted(lrm.LEARNING_CODE_INPUTS_V2),
        "dependency_lock_spec_file": lrm.DEPENDENCY_LOCK_SPEC_FILE,
        "dependency_lock_lock_file": lrm.DEPENDENCY_LOCK_LOCK_FILE,
    }


def test_frozen_allowlist_projection_v2_is_pinned() -> None:
    projection = _projection_v2()
    blob = json.dumps(projection, sort_keys=True, separators=(",", ":")).encode("utf-8")
    actual = hashlib.sha256(blob).hexdigest()
    assert actual == EXPECTED_PROJECTION_V2_SHA256, (
        "learning_runtime_manifest v2 allowlist changed; review the new digest coverage "
        f"then update EXPECTED_PROJECTION_V2_SHA256 to {actual}"
    )


def test_v2_allowlist_references_real_repository_files() -> None:
    projection = _projection_v2()
    referenced = [
        *projection["learning_code_inputs_v2"],
        projection["dependency_lock_spec_file"],
        projection["dependency_lock_lock_file"],
    ]
    missing = [rel for rel in referenced if not (ROOT / rel).is_file()]
    assert missing == [], f"v2 allowlist references non-existent files: {missing}"


def test_v2_learning_code_is_v1_superset_plus_parquet_etl() -> None:
    from ml_training import learning_runtime_manifest as lrm

    assert set(lrm.LEARNING_CODE_INPUTS).issubset(set(lrm.LEARNING_CODE_INPUTS_V2))
    added = set(lrm.LEARNING_CODE_INPUTS_V2) - set(lrm.LEARNING_CODE_INPUTS)
    assert added == {"program_code/ml_training/parquet_etl.py"}


# --------------------------------------------------------------------------- #
# W2 P1-C(E3 P1-2):特徵 schema 契約葉 ↔ parquet_etl 的常量平價 + 身分不變
# --------------------------------------------------------------------------- #
def test_feature_schema_contract_leaf_is_byte_parity_with_parquet_etl() -> None:
    """兩側常量/雜湊必須逐位元組一致——否則 train/serve schema 會靜默分岔。"""
    from ml_training import edge_feature_schema_contract as leaf
    from ml_training import parquet_etl

    assert leaf.EDGE_P3_FEATURE_NAMES == parquet_etl.EDGE_P3_FEATURE_NAMES
    assert (
        leaf.EDGE_P3_FEATURE_SCHEMA_VERSION == parquet_etl.EDGE_P3_FEATURE_SCHEMA_VERSION
    )
    assert leaf.compute_feature_schema_hash() == parquet_etl.compute_feature_schema_hash()
    assert leaf.compute_feature_schema_hash(["a", "b"]) == (
        parquet_etl.compute_feature_schema_hash(["a", "b"])
    )


def test_learning_runtime_manifest_imports_the_pg_free_leaf_not_parquet_etl() -> None:
    """SSOT 模塊不得再 import 真連 PG 的 duckdb ETL 面(ambient DSN 逃逸縫)。"""
    source = MODULE.read_text(encoding="utf-8")
    assert "from ml_training.parquet_etl import" not in source
    assert "from ml_training.edge_feature_schema_contract import" in source
    # 葉自身必須零 PG/duckdb/env 面(否則等於把同一條縫搬家)。只掃「可執行碼」:
    # 以 AST 去掉 module docstring/註解後 unparse,避免文件敘述造成假紅。
    import ast

    tree = ast.parse(
        (ROOT / "program_code/ml_training/edge_feature_schema_contract.py").read_text(
            encoding="utf-8"
        )
    )
    body = tree.body[1:] if ast.get_docstring(tree) is not None else tree.body
    leaf_code = "\n".join(ast.unparse(node) for node in body)
    for token in ("duckdb", "psycopg2", "OPENCLAW_DATABASE_URL", "POSTGRES_",
                  "os.environ", "getenv", "ATTACH", "connect("):
        assert token not in leaf_code, token


def test_v2_identity_still_binds_parquet_etl_file_contents() -> None:
    """身分守恆:v2 learning-code 輸入仍含 parquet_etl.py(digest 不得因拆分而改變)。"""
    from ml_training import learning_runtime_manifest as lrm

    assert "program_code/ml_training/parquet_etl.py" in lrm.LEARNING_CODE_INPUTS_V2
    manifest_v2, errors = lrm.try_build_learning_runtime_manifest_v2(ROOT)
    assert errors == [] and manifest_v2 is not None
    assert manifest_v2["self_digest"] == (
        "sha256:58bb9cc3a827872284196f57811227d367e4ff4aed5f3b22a031df1b39904c62"
    )
    manifest_v1, errors_v1 = lrm.try_build_learning_runtime_manifest(ROOT)
    assert errors_v1 == [] and manifest_v1 is not None
    assert manifest_v1["self_digest"] == (
        "sha256:6cf76b60a763035d26d0d4e9e0e6aa0aa8877d99966367c778420e5f63a79595"
    )
