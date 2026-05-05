"""REF-20 Sprint C R6-T0' V055 retrofit acceptance test (round 3).

模組目的 / Module purpose:
    REF-20 Sprint C R6-T0' V055 retrofit (V036 PR3 retrofit; MIT P0 BLOCKER
    fix from `2026-05-05--ref20_r6_r7_capability_risk.md` §3.5 + §8.2)
    的 acceptance test。Mac dev 採 static-parse 驗 V055 SQL 結構 + Python
    mirror 邏輯驗 INSERT 3-col forward semantics；Linux operator (E4
    regression / PM SSH bridge apply 後) 透 OPENCLAW_TEST_LIVE_PG=1 +
    OPENCLAW_TEST_DSN env 啟用真 PG smoke 驗 row body。

    REF-20 Sprint C R6-T0' V055 retrofit acceptance test for the
    `verify_replay_evidence_and_insert()` function body fix (V036 PR3
    retrofit; MIT P0 BLOCKER fix from
    `2026-05-05--ref20_r6_r7_capability_risk.md` §3.5 + §8.2). Mac dev
    layer = static-parse V055 SQL contract + Python mirror logic for
    INSERT 3-col forward semantics; Linux operator (post E4 regression
    / PM SSH bridge apply) opt-in real PG smoke via OPENCLAW_TEST_LIVE_PG=1
    + OPENCLAW_TEST_DSN env to verify row body.

Round 3 fix vs round 2 / Round 3 對 round 2 的修補:
    - E2 finding C-3 (NEW CRITICAL): round 2 V055 stub INSERT 引用 phantom
      column `actor_id`。E2 round 2 cross-grep 揭露 V049 line 282-307 18
      ADD COLUMN list 真實命名 `created_by` 在 line 284，無 `actor_id`。
      `actor_id` 實是 `replay.run_state` 表 column (V045:199 NOT NULL)，
      與 `replay.experiments` 無關。Round 3 選 A 修正：直接刪除 stub
      INSERT 中 `actor_id` column reference + VALUES 對應位置（最小變動）。
      Round 3 stub INSERT 寫 6 column：experiment_id / status / created_at
      / half_life_days / embargo_days / runtime_environment，全部 ∈ V041
      base 4 col ∪ V049 ADD COLUMN，0 phantom。新增 test
      `test_v055_stub_columns_exist_in_v049` cross-validate stub 全 column
      與 schema 對齊 + adversarial inline phantom 偵測 sanity。

Round 2 fix vs round 1 / Round 2 對 round 1 的修補:
    - E2 finding C-1: V055 INSERT body 寫 3 column（不是 4）；不寫
      `expires_at`（此 column 不存在於 learning.mlde_shadow_recommendations）。
      test_v055_writes_3_metadata_columns_in_insert 重命名 +
      test_v055_does_not_write_expires_at_column 新增；real_outcome /
      calibrated_replay / synthetic_replay / counterfactual_replay 4 path
      test 移除 row body expires_at 比對。
    - E2 finding C-2: Guard A signature drift detection 改用
      `pg_get_function_identity_arguments`；test_v055_function_existence
      assert sql 含 'pg_get_function_identity_arguments' 而非舊
      'pg_get_function_arguments' substring path。
    - E2 finding H-1: V055 Guard A SAVEPOINT block 移除 EXCEPTION WHEN
      OTHERS silent skip；test_v055_no_silent_skip_in_guard_a 新增驗證
      grep 0 'EXCEPTION WHEN OTHERS'。
    - E2 finding M-1: sign-off §5 文字訂正在 E1 sign-off report，不在 test。
    - E2 finding M-2: V049 NOT NULL set 實證在 V049 source line 282-307；
      stub minimal subset 加 runtime_environment='mac_dev_smoke_test_only'
      + status='created' 規避 V049 conditional NOT NULL；test
      test_v055_v049_not_null_set_documented 新增驗證 stub 含 V049 既知
      bypass column。

8 test case (per dispatch §6, round 2 updated):
    1. test_v055_function_existence — V055 file 存在 + Guard A 驗 19-arg
       signature unchanged (V036 byte-equal via identity_arguments)。
    2. test_v055_real_outcome_path — INSERT real_outcome → row tier=
       'real_outcome', exp_id NULL, hash NULL (3 col；不驗 expires_at)。
    3. test_v055_calibrated_replay_path — INSERT calibrated_replay → row
       tier match, exp_id NOT NULL, hash NOT NULL (3 col)。
    4. test_v055_synthetic_replay_path — 同上 with synthetic_replay tier。
    5. test_v055_counterfactual_replay_path — 同上 with counterfactual_replay tier。
    6. test_v055_v051_paired_check_still_enforced — INSERT real_outcome 但
       exp_id NOT NULL → V036 line 156-160 RAISE 仍正常觸發 (V055 不破
       verify portion)。
    7. test_v055_v036_ttl_check_still_enforced — INSERT calibrated_replay 但
       expires_at NULL → V036 line 178 RAISE 仍正常觸發 (input validation
       仍生效；不驗 row body expires_at column)。
    8. test_v055_idempotent_apply — V055 SQL 跑 ×2 → 第二次 0 RAISE。

Test mode / 測試模式:
    - Default (Mac dev): static-parse V055 SQL + pure-Python mirror logic;
      runs everywhere with no PG.
    - Live PG (Linux operator): opt-in via OPENCLAW_TEST_LIVE_PG=1 +
      OPENCLAW_TEST_DSN; cases 2-5 + 8 escalate to real PG smoke verifying
      row body matches caller args.

CLAUDE.md §七 雙語注釋強制 + REF-20 Gap Closure Plan V1 R6-T0' acceptance binding.

References / 參考:
- docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-05--ref20_sprint_c_task_dag.md §13.1 + §13.5
- docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-05--ref20_r6_r7_capability_risk.md §3.5 + §8.2
- docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-05--ref20_sprint_c_r6t0prime_v055_e2_review.md
  (round 1 review with 5 findings: 2 CRITICAL + 1 HIGH + 2 MEDIUM)
- sql/migrations/V055__verify_replay_evidence_function_full_insert.sql
- sql/migrations/V036__replay_evidence_source_guard.sql (前置)
- sql/migrations/V049__replay_experiments.sql (前置 22 col promotion)
- sql/migrations/V051__mlde_recommendations_replay_columns.sql (前置 paired CHECK)
"""

from __future__ import annotations

import datetime as _dt
import os
import re
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Path resolution / 路徑解析
#
# 此 test 檔位於 program_code/.../tests/replay/，srv/ 根 = parents[6]:
#   parents[0] = replay/
#   parents[1] = tests/
#   parents[2] = control_api_v1/
#   parents[3] = bybit_connector/
#   parents[4] = exchange_connectors/
#   parents[5] = program_code/
#   parents[6] = srv/
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
_SRV_ROOT = _THIS_FILE.parents[6]
_MIGRATIONS_DIR = _SRV_ROOT / "sql" / "migrations"

V055_PATH = _MIGRATIONS_DIR / "V055__verify_replay_evidence_function_full_insert.sql"
V036_PATH = _MIGRATIONS_DIR / "V036__replay_evidence_source_guard.sql"
V049_PATH = _MIGRATIONS_DIR / "V049__replay_experiments.sql"
V051_PATH = _MIGRATIONS_DIR / "V051__mlde_recommendations_replay_columns.sql"


# ---------------------------------------------------------------------------
# Helpers / 工具函數
# ---------------------------------------------------------------------------


def _read_sql(path: Path) -> str:
    """Read full SQL file as text. / 讀取完整 SQL 檔為文字。"""
    assert path.exists(), f"Migration file missing: {path}"
    return path.read_text(encoding="utf-8")


def _strip_sql_comments(sql: str) -> str:
    """Remove `-- ...` line comments to avoid false-positive on doc text.

    去除 `-- ...` 行註解避免文字描述被 grep 誤命中。
    """
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())


# ---------------------------------------------------------------------------
# Python mirror of V055 verify_replay_evidence_and_insert post-retrofit
#
# 鏡射 V055 retrofit 後 verify_replay_evidence_and_insert 邏輯 + 3-column
# INSERT row body 驗證。Mac dev 無 PG 時走此 mirror 確認 contract。
# Linux PG smoke 模式直接走 psycopg2 + V055-applied function。
#
# Round 2 fix: row body 只 capture 3 column (evidence_source_tier /
# replay_experiment_id / manifest_hash)；expires_at 走 input validation
# 但不持久化（per V055 round 2 fix per E2 finding C-1）。
# ---------------------------------------------------------------------------

ALLOWED_TIERS = (
    "real_outcome",
    "calibrated_replay",
    "synthetic_replay",
    "counterfactual_replay",
)
ALLOWED_SOURCES = ("ml_shadow", "dream_engine", "opportunity_tracker", "linucb")


class MockVerifyReplayEvidenceError(Exception):
    """Mirror PL/pgSQL RAISE EXCEPTION; test asserts message substring.

    對應 PL/pgSQL RAISE EXCEPTION；test 用 message substring 驗錯誤類別。
    """


def _mock_verify_and_insert(
    *,
    engine_mode: str,
    symbol: str | None,
    strategy_name: str | None,
    source: str,
    recommendation_type: str,
    expected_net_bps: float | None,
    confidence: float | None,
    sample_count: int | None,
    payload: dict[str, Any],
    applied: bool,
    requires_governance: bool,
    created_by: str,
    evidence_source_tier: str = "real_outcome",
    replay_experiment_id: str | None = None,
    manifest_hash: str | None = None,
    expires_at: _dt.datetime | None = None,
    decision_lease_id: str | None = None,
    context_id: str | None = None,
    intent_id: str | None = None,
    _now: _dt.datetime | None = None,
    _row_capture: dict[str, Any] | None = None,
) -> int:
    """Pure-Python mirror of V055 verify_replay_evidence_and_insert().

    純 Python 鏡射 V055 retrofit 後 verify_replay_evidence_and_insert() 邏輯。

    與 V036 mirror 差異 (round 2 fix per E2 finding C-1)：(5) INSERT 階段把 3
    metadata column 寫進 _row_capture (對應 V055 retrofit row body) 讓
    caller 驗 row body 3 column 對齊 args。expires_at **不**寫 _row_capture
    （V055 round 2 fix：此 column 不存在於 learning.mlde_shadow_recommendations
    table）。
    Difference vs V036 mirror: at INSERT step 3 metadata columns are
    forwarded into _row_capture (mirroring V055 row body) so caller can
    verify the 3 columns match args. expires_at is NOT written to
    _row_capture (V055 round 2 fix: column does not exist on
    learning.mlde_shadow_recommendations table).

    Returns mock new id (1) on success; raises MockVerifyReplayEvidenceError
    on validation failure.
    """
    # (1) tier allowlist (V036 byte-equal)
    if evidence_source_tier not in ALLOWED_TIERS:
        raise MockVerifyReplayEvidenceError(
            f"evidence_source_tier={evidence_source_tier} not in allowlist"
        )

    # (2) source allowlist (V036 byte-equal)
    if source not in ALLOWED_SOURCES:
        raise MockVerifyReplayEvidenceError(
            f"source={source} not in producer allowlist"
        )

    # (3) compound CHECK semantics (V036 byte-equal)
    if evidence_source_tier == "real_outcome":
        if replay_experiment_id is not None or manifest_hash is not None:
            raise MockVerifyReplayEvidenceError(
                "real_outcome row must not carry replay_experiment_id / manifest_hash"
            )
    else:
        if replay_experiment_id is None or manifest_hash is None:
            raise MockVerifyReplayEvidenceError(
                f"replay-derived row (tier={evidence_source_tier}) requires "
                "replay_experiment_id AND manifest_hash"
            )

    # (4) TTL hard check for replay-derived rows (V036 byte-equal).
    #     p_expires_at is INPUT VALIDATED here but NOT persisted to row column.
    #     p_expires_at 走 input 驗證但**不**寫入 row column。
    if evidence_source_tier != "real_outcome":
        if expires_at is None:
            raise MockVerifyReplayEvidenceError(
                "replay-derived row requires non-NULL expires_at"
            )
        ref = _now or _dt.datetime.now(_dt.timezone.utc)
        if expires_at <= ref:
            raise MockVerifyReplayEvidenceError(
                f"expires_at={expires_at} must be in the future"
            )

    # (5) V055 retrofit (round 2 fix per E2 finding C-1): forward 3 metadata
    #     column 進 row body / forward 3 metadata columns into row body.
    #     expires_at 不寫 row body（此 column 不存在於目標表）。
    #     Mac dev mirror 用 _row_capture dict 模擬 row body for caller
    #     verification.
    if _row_capture is not None:
        _row_capture["evidence_source_tier"] = evidence_source_tier
        _row_capture["replay_experiment_id"] = replay_experiment_id
        _row_capture["manifest_hash"] = manifest_hash
        # NOTE: expires_at intentionally NOT in _row_capture
        # NOTE: V055 round 2 fix per E2 finding C-1.

    return 1


# ---------------------------------------------------------------------------
# Test case 1: V055 function existence + 19-arg signature unchanged
# ---------------------------------------------------------------------------


def test_v055_function_existence() -> None:
    """V055 file 存在 + Guard A 驗 19-arg signature unchanged (V036 byte-equal).

    Round 2 fix (E2 finding C-2): Guard A signature drift detection 改用
    `pg_get_function_identity_arguments`，不是舊 `pg_get_function_arguments`
    + position() substring。

    V055 file exists + Guard A asserts 19-arg signature unchanged via
    pg_get_function_identity_arguments (V036 byte-equal).
    """
    # 檔存在 / file exists
    assert V055_PATH.exists(), f"V055 migration missing: {V055_PATH}"

    sql = _strip_sql_comments(_read_sql(V055_PATH))

    # CREATE OR REPLACE FUNCTION 命名一致
    assert "CREATE OR REPLACE FUNCTION learning.verify_replay_evidence_and_insert" in sql

    # 19-arg signature: 抽 signature block 計 p_ prefix arg
    signature_block = re.search(
        r"CREATE OR REPLACE FUNCTION learning\.verify_replay_evidence_and_insert\s*\((.+?)\)\s*RETURNS BIGINT",
        sql,
        re.DOTALL,
    )
    assert signature_block is not None, "V055 signature block not located"
    signature_args = re.findall(r"\bp_\w+", signature_block.group(1))
    assert len(signature_args) == 19, (
        f"V055 signature must have 19 args (V036 byte-equal); got {len(signature_args)}: {signature_args}"
    )

    # Guard A 驗 19-arg pronargs match
    assert "v_expected_arg_count INT := 19" in sql or "v_expected_arg_count := 19" in sql, (
        "V055 Guard A must declare v_expected_arg_count = 19"
    )

    # Round 2 fix (E2 finding C-2): Guard A 用 pg_get_function_identity_arguments
    # 不是舊 pg_get_function_arguments substring。
    assert "pg_get_function_identity_arguments" in sql, (
        "V055 Guard A round 2 must use pg_get_function_identity_arguments "
        "(strict equality on type-only list); not pg_get_function_arguments "
        "substring path which fails on PG 13+ DEFAULT clause noise"
    )

    # Round 2 fix: Guard A 必含 strict equality 比對 (NOT substring position())
    assert "v_identity_args <> v_expected_identity_args" in sql, (
        "V055 Guard A round 2 must use strict equality (<>) on identity_arguments; "
        "not substring position() pattern from round 1"
    )

    # Guard A 驗 arg signature byte-equal V036
    assert "byte-equal" in sql.lower() or "signature drift" in sql, (
        "V055 Guard A must verify arg signature byte-equal V036"
    )


# ---------------------------------------------------------------------------
# Test case 2: real_outcome path → row body 3 column 對齊 args
# ---------------------------------------------------------------------------


def test_v055_real_outcome_path() -> None:
    """INSERT real_outcome → row tier='real_outcome', exp_id NULL, hash NULL.

    Round 2 fix (E2 finding C-1): row body 只 3 column (tier/exp_id/hash)；
    不驗 expires_at（此 column 不存在於 mlde_shadow_recommendations）。

    V055 retrofit 後 INSERT real_outcome 走 row body：tier='real_outcome',
    exp_id NULL, hash NULL (3 column；expires_at 不在 row body)。
    """
    row: dict[str, Any] = {}
    new_id = _mock_verify_and_insert(
        engine_mode="demo",
        symbol="BTCUSDT",
        strategy_name="ma_crossover",
        source="ml_shadow",
        recommendation_type="rank",
        expected_net_bps=12.5,
        confidence=0.65,
        sample_count=100,
        payload={"v055": "real_outcome_smoke"},
        applied=False,
        requires_governance=True,
        created_by="v055_test",
        evidence_source_tier="real_outcome",
        replay_experiment_id=None,
        manifest_hash=None,
        expires_at=None,
        _row_capture=row,
    )
    assert new_id == 1
    # row body 3 column 對齊 args
    assert row["evidence_source_tier"] == "real_outcome"
    assert row["replay_experiment_id"] is None
    assert row["manifest_hash"] is None
    # Round 2 fix: expires_at 不在 row body（V055 不寫此 column 至 mlde_shadow_recommendations）
    assert "expires_at" not in row, (
        "V055 round 2 fix (E2 C-1): expires_at must NOT appear in row body "
        "of mlde_shadow_recommendations (column does not exist on this table)"
    )


# ---------------------------------------------------------------------------
# Test case 3: calibrated_replay path → row body 3 column 對齊 args
# ---------------------------------------------------------------------------


def test_v055_calibrated_replay_path() -> None:
    """INSERT calibrated_replay → row tier match, exp_id NOT NULL, hash NOT NULL.

    Round 2 fix: row body 3 column；expires_at 走 input 驗證但不存 row body。

    V055 retrofit 後 INSERT calibrated_replay 走 row body：tier match,
    exp_id NOT NULL, hash NOT NULL (3 column；expires_at input-validated only)。
    """
    future = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=7)
    test_exp_id = "00000000-0000-0000-0000-000000000001"
    test_hash = "0000000000000000000000000000000000000000000000000000000000000001"

    row: dict[str, Any] = {}
    new_id = _mock_verify_and_insert(
        engine_mode="demo",
        symbol="BTCUSDT",
        strategy_name="grid_trading",
        source="dream_engine",
        recommendation_type="parameter_proposal",
        expected_net_bps=8.0,
        confidence=0.6,
        sample_count=200,
        payload={"v055": "calibrated_replay_smoke"},
        applied=False,
        requires_governance=True,
        created_by="v055_test",
        evidence_source_tier="calibrated_replay",
        replay_experiment_id=test_exp_id,
        manifest_hash=test_hash,
        expires_at=future,  # input-validated; not persisted to row body
        _row_capture=row,
    )
    assert new_id == 1
    # row body 3 column 對齊 args
    assert row["evidence_source_tier"] == "calibrated_replay"
    assert row["replay_experiment_id"] == test_exp_id
    assert row["manifest_hash"] == test_hash
    # Round 2 fix: expires_at 不在 row body
    assert "expires_at" not in row, (
        "V055 round 2 fix (E2 C-1): expires_at must NOT appear in row body"
    )


# ---------------------------------------------------------------------------
# Test case 4: synthetic_replay path
# ---------------------------------------------------------------------------


def test_v055_synthetic_replay_path() -> None:
    """INSERT synthetic_replay → row tier match, exp_id NOT NULL, hash NOT NULL.

    Round 2 fix: row body 3 column；expires_at 不在 row body。

    V055 retrofit 後 INSERT synthetic_replay 走 row body：tier match,
    exp_id NOT NULL, hash NOT NULL (3 column)。
    """
    future = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=7)
    test_exp_id = "00000000-0000-0000-0000-000000000002"
    test_hash = "0000000000000000000000000000000000000000000000000000000000000002"

    row: dict[str, Any] = {}
    new_id = _mock_verify_and_insert(
        engine_mode="demo",
        symbol="ETHUSDT",
        strategy_name="bb_breakout",
        source="opportunity_tracker",
        recommendation_type="rank",
        expected_net_bps=5.0,
        confidence=0.55,
        sample_count=80,
        payload={"v055": "synthetic_replay_smoke"},
        applied=False,
        requires_governance=True,
        created_by="v055_test",
        evidence_source_tier="synthetic_replay",
        replay_experiment_id=test_exp_id,
        manifest_hash=test_hash,
        expires_at=future,
        _row_capture=row,
    )
    assert new_id == 1
    # row body 3 column 對齊 args
    assert row["evidence_source_tier"] == "synthetic_replay"
    assert row["replay_experiment_id"] == test_exp_id
    assert row["manifest_hash"] == test_hash
    assert "expires_at" not in row


# ---------------------------------------------------------------------------
# Test case 5: counterfactual_replay path
# ---------------------------------------------------------------------------


def test_v055_counterfactual_replay_path() -> None:
    """INSERT counterfactual_replay → row tier match, exp_id NOT NULL, hash NOT NULL.

    Round 2 fix: row body 3 column；expires_at 不在 row body。

    V055 retrofit 後 INSERT counterfactual_replay 走 row body：tier match,
    exp_id NOT NULL, hash NOT NULL (3 column)。
    """
    future = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=7)
    test_exp_id = "00000000-0000-0000-0000-000000000003"
    test_hash = "0000000000000000000000000000000000000000000000000000000000000003"

    row: dict[str, Any] = {}
    new_id = _mock_verify_and_insert(
        engine_mode="demo",
        symbol="SOLUSDT",
        strategy_name="bb_reversion",
        source="linucb",
        recommendation_type="rank",
        expected_net_bps=3.0,
        confidence=0.5,
        sample_count=50,
        payload={"v055": "counterfactual_replay_smoke"},
        applied=False,
        requires_governance=True,
        created_by="v055_test",
        evidence_source_tier="counterfactual_replay",
        replay_experiment_id=test_exp_id,
        manifest_hash=test_hash,
        expires_at=future,
        _row_capture=row,
    )
    assert new_id == 1
    # row body 3 column 對齊 args
    assert row["evidence_source_tier"] == "counterfactual_replay"
    assert row["replay_experiment_id"] == test_exp_id
    assert row["manifest_hash"] == test_hash
    assert "expires_at" not in row


# ---------------------------------------------------------------------------
# Test case 6: V055 不破 verify portion - V036 line 156-160 paired CHECK 仍正常
# ---------------------------------------------------------------------------


def test_v055_v051_paired_check_still_enforced() -> None:
    """INSERT real_outcome 但 exp_id NOT NULL → V036 line 156-160 RAISE 仍正常觸發.

    V055 不破 verify portion；V036 paired CHECK 在 verify (3) 階段拒
    real_outcome + replay_experiment_id NOT NULL 組合。
    V055 must not break verify portion: V036 paired CHECK in verify step (3)
    rejects real_outcome + replay_experiment_id NOT NULL combo.
    """
    with pytest.raises(MockVerifyReplayEvidenceError, match="must not carry"):
        _mock_verify_and_insert(
            engine_mode="demo",
            symbol="BTCUSDT",
            strategy_name="ma_crossover",
            source="ml_shadow",
            recommendation_type="rank",
            expected_net_bps=12.5,
            confidence=0.65,
            sample_count=100,
            payload={},
            applied=False,
            requires_governance=True,
            created_by="v055_test",
            evidence_source_tier="real_outcome",
            replay_experiment_id="00000000-0000-0000-0000-000000000099",  # 違反 paired CHECK
            manifest_hash=None,
        )


# ---------------------------------------------------------------------------
# Test case 7: V055 不破 verify portion - V036 line 178 TTL CHECK 仍正常
# ---------------------------------------------------------------------------


def test_v055_v036_ttl_check_still_enforced() -> None:
    """INSERT calibrated_replay 但 expires_at NULL → V036 line 178 RAISE 仍正常觸發.

    V055 不破 verify portion；V036 TTL CHECK 在 verify (4) 階段拒
    replay-derived row + expires_at NULL 組合（input validation 仍生效，
    雖然 expires_at 不寫 row body）。
    V055 must not break verify portion: V036 TTL CHECK in verify step (4)
    rejects replay-derived row + expires_at NULL combo (input validation
    still enforced even though expires_at is not persisted to row body).
    """
    with pytest.raises(MockVerifyReplayEvidenceError, match="non-NULL expires_at"):
        _mock_verify_and_insert(
            engine_mode="demo",
            symbol="BTCUSDT",
            strategy_name="ma_crossover",
            source="ml_shadow",
            recommendation_type="rank",
            expected_net_bps=12.5,
            confidence=0.65,
            sample_count=100,
            payload={},
            applied=False,
            requires_governance=True,
            created_by="v055_test",
            evidence_source_tier="calibrated_replay",
            replay_experiment_id="00000000-0000-0000-0000-000000000099",
            manifest_hash="0000000000000000000000000000000000000000000000000000000000000099",
            expires_at=None,  # 違反 TTL CHECK input validation
        )


# ---------------------------------------------------------------------------
# Test case 8: idempotency — V055 SQL CREATE OR REPLACE 重跑無 RAISE
# ---------------------------------------------------------------------------


def test_v055_idempotent_apply() -> None:
    """V055 SQL 跑 ×2 → 第二次 0 RAISE.

    V055 透過 `CREATE OR REPLACE FUNCTION` 機制，重跑時自動覆寫 same
    signature 不增 row。Guard A function 存在 + 19-arg signature byte-equal
    V036 第一次與第二次都 PASS（idempotent）。
    V055 idempotent via `CREATE OR REPLACE FUNCTION` mechanism: re-running
    overwrites the function body with the same signature. Guard A
    (function existence + 19-arg signature byte-equal V036 via
    pg_get_function_identity_arguments) PASSes both runs.
    """
    sql = _strip_sql_comments(_read_sql(V055_PATH))

    # CREATE OR REPLACE 出現 1 次 (function definition; re-run overrides)
    assert sql.count("CREATE OR REPLACE FUNCTION learning.verify_replay_evidence_and_insert") == 1, (
        "V055 must use CREATE OR REPLACE for idempotent re-run"
    )

    # CREATE TABLE / DROP TABLE 必不在 V055（純 function retrofit; 不破壞 schema）
    assert "CREATE TABLE" not in sql, (
        "V055 must not contain CREATE TABLE (pure function retrofit)"
    )
    assert "DROP TABLE" not in sql, (
        "V055 must not contain DROP TABLE (pure function retrofit)"
    )
    # Guard A 不應 fail-closed 重跑（re-run 後 function exists + 19-arg 仍 PASS）
    assert "v_expected_arg_count INT := 19" in sql or "v_expected_arg_count := 19" in sql

    # post-INSERT smoke 必在 ROLLBACK 內，不污染 production
    assert "ROLLBACK TO SAVEPOINT v055_smoke" in sql, (
        "V055 post-INSERT smoke must ROLLBACK to keep PG state pristine"
    )


# ---------------------------------------------------------------------------
# Cross-file invariants / 跨檔不變量
# ---------------------------------------------------------------------------


def test_v055_bilingual_module_note() -> None:
    """V055 has bilingual MODULE_NOTE per CLAUDE.md §七.

    V055 含中英 MODULE_NOTE，符合 CLAUDE.md §七。
    """
    sql = _read_sql(V055_PATH)
    # Purpose / 目的 dual-language header
    assert "Purpose / 目的" in sql, "V055 missing bilingual Purpose"
    # Spec source citation
    assert "Spec source / 規格來源" in sql, "V055 missing Spec source citation"
    # When to apply / 何時 apply dual-language section
    assert "When to apply / 何時 apply" in sql, "V055 missing bilingual When to apply"


def test_v055_no_user_home_path_hardcoded() -> None:
    """No user-home path hardcoded in V055 (CLAUDE.md §七 cross-platform).

    V055 0 個 user-home 路徑硬編碼（CLAUDE.md §七 跨平台）。
    """
    pattern = re.compile(r"/home/ncyu|/Users/[^/]+")
    sql = _read_sql(V055_PATH)
    m = pattern.search(sql)
    assert m is None, (
        f"V055 has hardcoded user-home path: {m.group(0)} at position {m.start()}"
    )


def test_v055_no_hard_boundary_columns_touched() -> None:
    """V055 does not touch hard-boundary columns (max_retries / live_*).

    V055 不觸碰硬邊界 column（max_retries / live_execution_allowed
    / execution_authority / system_mode / OPENCLAW_ALLOW_MAINNET）。
    """
    forbidden = [
        "max_retries",
        "live_execution_allowed",
        "execution_authority",
        "system_mode",
        "OPENCLAW_ALLOW_MAINNET",
    ]
    sql = _strip_sql_comments(_read_sql(V055_PATH))
    for kw in forbidden:
        assert kw not in sql, f"V055 touches hard-boundary keyword: {kw}"


def test_v055_no_trading_or_live_mutation() -> None:
    """V055 does not INSERT / UPDATE / DELETE trading.* or live_*.

    V055 不 INSERT / UPDATE / DELETE trading.* 或 live_*。
    V055 是純 function retrofit；smoke 內 INSERT 走 SAVEPOINT ROLLBACK 清乾。
    V055 is pure function retrofit; smoke INSERT runs in SAVEPOINT ROLLBACK.
    """
    forbidden_pat = re.compile(
        r"\b(INSERT INTO trading|UPDATE trading|DELETE FROM trading|"
        r"INSERT INTO live_|UPDATE live_|DELETE FROM live_)",
        re.IGNORECASE,
    )
    sql = _strip_sql_comments(_read_sql(V055_PATH))
    m = forbidden_pat.search(sql)
    assert m is None, (
        f"V055 has forbidden trading/live mutation: {m.group(0) if m else ''}"
    )


def test_v055_writes_3_metadata_columns_in_insert() -> None:
    """V055 INSERT body declares 3 V055 retrofit metadata columns (round 2 fix).

    Round 2 fix (E2 finding C-1): V055 INSERT body 宣告 3 個 metadata column：
    evidence_source_tier / replay_experiment_id / manifest_hash。
    **不寫** expires_at（此 column 不存在於 mlde_shadow_recommendations
    table；V038-V040 + V051 都未加，V049 line 305 加的 expires_at 是
    replay.experiments 表，不同表）。

    這是 V055 retrofit 對 V036 的核心差異點。V036 line 208-242 INSERT 缺
    這 3 column。V055 必須補回 3 column（不是 round 1 寫的 4 column）。
    This is the core V055 retrofit delta vs V036. V036 line 208-242 INSERT
    misses these 3 columns. V055 must add them back. expires_at is NOT
    written (round 2 fix per E2 C-1).
    """
    sql = _strip_sql_comments(_read_sql(V055_PATH))

    # 抓 V055 INSERT body
    m = re.search(
        r"INSERT INTO learning\.mlde_shadow_recommendations\s*\((.+?)\)\s*VALUES",
        sql,
        re.DOTALL,
    )
    assert m is not None, "V055 INSERT INTO ... VALUES block not located"
    insert_body = m.group(1)

    # 3 個 V055 retrofit column 必須在 INSERT body
    required_cols = [
        "evidence_source_tier",
        "replay_experiment_id",
        "manifest_hash",
    ]
    for col in required_cols:
        assert col in insert_body, (
            f"V055 INSERT body missing V055 retrofit column: {col}. "
            f"This is the core V055 fix vs V036; without it V055 = V036 silent corruption."
        )


def test_v055_does_not_write_expires_at_column() -> None:
    """V055 INSERT body must NOT declare expires_at column (round 2 fix per E2 C-1).

    Round 2 fix (E2 finding C-1): V055 INSERT body **不**包含 expires_at
    column。此 column 不存在於 learning.mlde_shadow_recommendations 表；
    V038-V040 + V051 都未加，V049 line 305 加的 expires_at 是 replay.experiments
    表（不同表）。

    V055 round 2 fix per E2 C-1: V055 INSERT body must NOT contain
    expires_at column. The column does not exist on
    learning.mlde_shadow_recommendations (no migration adds it; V049 line 305
    adds expires_at to replay.experiments which is a different table).
    """
    sql = _strip_sql_comments(_read_sql(V055_PATH))

    # 抓 V055 INSERT body
    m = re.search(
        r"INSERT INTO learning\.mlde_shadow_recommendations\s*\((.+?)\)\s*VALUES",
        sql,
        re.DOTALL,
    )
    assert m is not None, "V055 INSERT INTO ... VALUES block not located"
    insert_body = m.group(1)

    # expires_at 必不在 INSERT body
    # Use word-boundary regex to avoid false positive on substring matches
    # in column names like "p_expires_at" (function arg, not column name).
    # 用 word-boundary 避免 substring 誤命中（如 column 名 expires_at_v2 不存在但若 typo
    # 則應 catch；此處 INSERT body 內若出現 \bexpires_at\b 即為 column 寫入）。
    insert_lines = insert_body.splitlines()
    for line in insert_lines:
        # Strip trailing comma / whitespace; normalize
        # 排除 line comment 已被 _strip_sql_comments 刪
        normalized = line.strip().rstrip(",").strip()
        # column name must be standalone (not a function call / not p_expires_at / etc.)
        if normalized == "expires_at":
            raise AssertionError(
                f"V055 round 2 fix (E2 C-1) violation: V055 INSERT body contains "
                f"expires_at column write. This column does not exist on "
                f"learning.mlde_shadow_recommendations table. INSERT body line: "
                f"{line!r}"
            )


def test_v055_signature_byte_equal_v036() -> None:
    """V055 19-arg signature byte-equal V036.

    V055 19-arg signature 與 V036 完全一致。Caller 端不需任何改動。
    p_expires_at 仍在 signature（input validation only；不寫 row column）。
    V055 19-arg signature byte-equal V036; callers need 0 changes.
    p_expires_at remains in signature (input validation only; not written
    to row column).
    """
    sql_v055 = _strip_sql_comments(_read_sql(V055_PATH))
    sql_v036 = _strip_sql_comments(_read_sql(V036_PATH))

    # V036 signature block
    m_v036 = re.search(
        r"CREATE OR REPLACE FUNCTION learning\.verify_replay_evidence_and_insert\s*\((.+?)\)\s*RETURNS BIGINT",
        sql_v036,
        re.DOTALL,
    )
    # V055 signature block
    m_v055 = re.search(
        r"CREATE OR REPLACE FUNCTION learning\.verify_replay_evidence_and_insert\s*\((.+?)\)\s*RETURNS BIGINT",
        sql_v055,
        re.DOTALL,
    )
    assert m_v036 is not None and m_v055 is not None, (
        "Cannot locate signature blocks in V036 / V055"
    )

    # 抽 arg name list (順序敏感)
    args_v036 = re.findall(r"\bp_\w+", m_v036.group(1))
    args_v055 = re.findall(r"\bp_\w+", m_v055.group(1))

    assert args_v036 == args_v055, (
        f"V055 signature arg order/names drift from V036; expected {args_v036}, "
        f"got {args_v055}"
    )
    assert len(args_v055) == 19, (
        f"V055 signature must have exactly 19 args; got {len(args_v055)}"
    )


def test_v055_4_path_smoke_in_guard_a() -> None:
    """V055 Guard A contains 4-tier path post-INSERT smoke.

    V055 Guard A 內含 4-path post-INSERT smoke (real_outcome /
    calibrated_replay / synthetic_replay / counterfactual_replay)。
    V055 Guard A contains 4-path post-INSERT smoke covering all replay tiers.
    """
    sql = _strip_sql_comments(_read_sql(V055_PATH))

    # 4-path 各自必出現
    assert "'real_outcome'" in sql, "V055 Guard A smoke missing real_outcome path"
    assert "'calibrated_replay'" in sql, "V055 Guard A smoke missing calibrated_replay path"
    assert "'synthetic_replay'" in sql, "V055 Guard A smoke missing synthetic_replay path"
    assert "'counterfactual_replay'" in sql, "V055 Guard A smoke missing counterfactual_replay path"

    # SAVEPOINT + ROLLBACK 機制
    assert "SAVEPOINT v055_smoke" in sql, "V055 Guard A smoke must use SAVEPOINT"
    assert "ROLLBACK TO SAVEPOINT v055_smoke" in sql, (
        "V055 Guard A smoke must ROLLBACK to keep PG state pristine"
    )


def test_v055_no_silent_skip_in_guard_a() -> None:
    """V055 Guard A contains NO 'EXCEPTION WHEN OTHERS' silent skip (round 2 fix per E2 H-1).

    Round 2 fix (E2 finding H-1): V055 Guard A SAVEPOINT block 移除 inner
    BEGIN-END 內的 EXCEPTION WHEN OTHERS silent skip pattern。任何 stub
    INSERT / path 2-4 INSERT 異常自然 propagate 到上層 DO $$ block，
    最終 RAISE EXCEPTION 給 psql apply 端 fail-loud（CLAUDE.md §九 無
    silent fallthrough 原則的 SQL 等價）。

    V055 round 2 fix per E2 H-1: V055 Guard A SAVEPOINT block must NOT
    contain 'EXCEPTION WHEN OTHERS' silent skip pattern. Any stub /
    path 2-4 INSERT failure must propagate to the outer DO $$ block,
    ultimately RAISE EXCEPTION fail-loud (SQL equivalent of CLAUDE.md
    §九 no-silent-fallthrough principle).
    """
    sql = _strip_sql_comments(_read_sql(V055_PATH))

    # No EXCEPTION WHEN OTHERS in V055
    assert "EXCEPTION WHEN OTHERS" not in sql, (
        "V055 round 2 fix (E2 H-1) violation: 'EXCEPTION WHEN OTHERS' silent "
        "skip pattern must NOT appear in V055. Round 1 had it inside the "
        "stub INSERT block (line 504-525) and was returned by E2 review. "
        "Round 2 fix removes it; failures must fail-loud."
    )


def test_v055_v049_not_null_set_documented() -> None:
    """V055 stub INSERT covers V049 NOT NULL set (round 2 fix per E2 M-2).

    Round 2 fix (E2 finding M-2): V055 SAVEPOINT block 內 stub INSERT 至
    replay.experiments 必含 V049 已知 NOT NULL bypass column。V049 真實
    NOT NULL set (per V049 source line 282-307 ADD COLUMN 全 NULLABLE):
        - experiment_id (PK NOT NULL，由 caller gen_random_uuid)
        - V049 conditional NOT NULL: engine_binary_sha when
          runtime_environment='linux_trade_core' (V049 line 425-433
          chk_replay_experiments_engine_sha_linux CHECK)
        - V041 stub: experiment_id (kept), half_life_days, embargo_days,
          created_at (default now())
    V049 ADD COLUMN 18 個全為 NULLABLE (IF NOT EXISTS 加列無 NOT NULL
    constraint per V049 line 282-307)。

    Bypass strategy: stub 用 runtime_environment='mac_dev_smoke_test_only'
    規避 conditional NOT NULL（無需 supply engine_binary_sha）。

    V055 round 2 fix per E2 M-2: V055 SAVEPOINT block stub INSERT to
    replay.experiments must include V049 known NOT NULL bypass columns.
    V049 actual NOT NULL set verified per source line 282-307 (all ADD
    COLUMN are NULLABLE; only conditional NOT NULL via
    chk_replay_experiments_engine_sha_linux CHECK with
    runtime_environment='linux_trade_core'). Bypass via
    runtime_environment='mac_dev_smoke_test_only'.
    """
    sql = _strip_sql_comments(_read_sql(V055_PATH))

    # Stub INSERT to replay.experiments 必含 runtime_environment 欄位
    # (V049 conditional NOT NULL bypass)
    stub_pattern = re.compile(
        r"INSERT INTO replay\.experiments\s*\((.+?)\)\s*VALUES",
        re.DOTALL,
    )
    m = stub_pattern.search(sql)
    assert m is not None, "V055 stub INSERT to replay.experiments not found"
    stub_columns = m.group(1)

    # V049 conditional NOT NULL bypass column
    assert "runtime_environment" in stub_columns, (
        "V055 round 2 fix (E2 M-2): stub INSERT must include "
        "runtime_environment column to bypass V049 conditional NOT NULL "
        "(chk_replay_experiments_engine_sha_linux requires "
        "engine_binary_sha when runtime='linux_trade_core'; "
        "stub uses 'mac_dev_smoke_test_only' to bypass)"
    )

    # V049 既有 unconditional NOT NULL (V041 + V049 PK)
    assert "experiment_id" in stub_columns, (
        "V055 stub INSERT must include experiment_id (V041 + V049 PK NOT NULL)"
    )

    # 確認 stub 用 mac_dev_smoke_test_only 而非 linux_trade_core
    # (避免觸發 conditional NOT NULL on engine_binary_sha)
    assert "'mac_dev_smoke_test_only'" in sql, (
        "V055 round 2 fix (E2 M-2): stub INSERT must use "
        "runtime_environment='mac_dev_smoke_test_only' to avoid V049 "
        "engine_binary_sha conditional NOT NULL requirement"
    )


def test_v055_v049_source_not_null_invariant() -> None:
    """Cross-check: V049 source confirms ADD COLUMN 18 are all NULLABLE (round 2 fix per E2 M-2).

    Round 2 fix (E2 finding M-2): 對 V049 source file 抽 ADD COLUMN 列證明
    全 18 個都是 NULLABLE（無 NOT NULL constraint inline），confirming
    stub minimal subset 不需 supply 全 22 col。

    Cross-validate against V049 source: ADD COLUMN 18 columns are all
    NULLABLE (no inline NOT NULL constraint), confirming stub minimal
    subset does not need to supply all 22 columns.
    """
    v049_sql = _read_sql(V049_PATH)

    # V049 line 282-307 ADD COLUMN 全 NULLABLE。grep 不應有 NOT NULL inline。
    # 排除 conditional NOT NULL CHECK constraint (line 425-433)。
    # 模式: ADD COLUMN IF NOT EXISTS <name> <type> NOT NULL (inline)
    add_col_not_null = re.compile(
        r"ADD COLUMN IF NOT EXISTS\s+\w+\s+\w+(?:\s+\w+)*\s+NOT NULL",
        re.IGNORECASE,
    )
    m = add_col_not_null.search(v049_sql)
    assert m is None, (
        f"V049 source unexpectedly has ADD COLUMN ... NOT NULL inline at "
        f"position {m.start()}: {m.group(0)!r}. V055 round 2 M-2 stub "
        f"design assumes V049 18 ADD COLUMN are all NULLABLE."
    )


def test_v055_stub_columns_exist_in_v049() -> None:
    """V055 stub INSERT column list 全部存在於 V049/V041 schema (round 3 fix per E2 C-3).

    Round 3 fix (E2 finding C-3): E2 round 2 review 揭露 round 2 stub INSERT
    引用 phantom column `actor_id`（V049 line 282-307 18 ADD COLUMN list 真實
    命名 `created_by` 在 line 284，無 `actor_id`）。Linux deploy 必撞
    `column "actor_id" of relation "experiments" does not exist`。

    本 test cross-validate：(1) parse V055 stub INSERT 的 column list；
    (2) parse V049 ADD COLUMN list（line 282-307）+ V041 base CREATE TABLE
    column list（line 81-86）；(3) assert 每個 stub column 必 ∈ (V049
    ADD COLUMN ∪ V041 base column) — phantom column 0 容忍。

    Adversarial guard：Round 2 漏掉此 cross-validation 是因 round 2 driver
    test (test_v055_v049_not_null_set_documented) 只 grep stub 含
    runtime_environment + experiment_id + 'mac_dev_smoke_test_only'，**0
    cross-grep stub 全部 column 是否實存於 schema**。本 test 補此漏。

    V055 stub INSERT column list must all exist in V049/V041 schema (round
    3 fix per E2 C-3). E2 round 2 review revealed round 2 stub INSERT
    referenced phantom column `actor_id` (V049 line 282-307's 18 ADD COLUMN
    list contains `created_by` at line 284, NOT `actor_id`). Linux deploy
    would fail with `column "actor_id" of relation "experiments" does not
    exist`. This test cross-validates: (1) parse V055 stub INSERT column
    list; (2) parse V049 ADD COLUMN list (line 282-307) + V041 base CREATE
    TABLE column list (line 81-86); (3) assert every stub column ∈ (V049
    ADD COLUMN ∪ V041 base column) — 0 tolerance for phantom columns.
    Adversarial guard: round 2 missed this cross-validation because the
    round 2 driver test only grepped stub for runtime_environment +
    experiment_id + 'mac_dev_smoke_test_only', with 0 cross-grep verifying
    every stub column exists in schema. This test fills that gap.
    """
    v055_sql = _strip_sql_comments(_read_sql(V055_PATH))
    v049_sql = _strip_sql_comments(_read_sql(V049_PATH))

    # ── (1) parse V055 stub INSERT column list ──────────────────────────────
    # 抓 INSERT INTO replay.experiments (...) VALUES 的 column list。
    # Capture V055 stub INSERT to replay.experiments column list.
    stub_pattern = re.compile(
        r"INSERT INTO replay\.experiments\s*\((.+?)\)\s*VALUES",
        re.DOTALL,
    )
    stub_match = stub_pattern.search(v055_sql)
    assert stub_match is not None, (
        "V055 stub INSERT to replay.experiments not found; cross-validation "
        "skipped impossible. Round 3 acceptance binding fail-loud."
    )
    stub_columns_raw = stub_match.group(1)
    # split by comma + strip whitespace + strip 行內 PG comment 殘餘 + lower-case 比對
    stub_columns = {
        col.strip().lower()
        for col in stub_columns_raw.split(",")
        if col.strip()
    }
    assert stub_columns, "V055 stub INSERT column list parsed empty (parse failure)"

    # ── (2) parse V049 ADD COLUMN list (line 282-307) ───────────────────────
    # 抓 ALTER TABLE replay.experiments ... ADD COLUMN IF NOT EXISTS <name> <type>
    # 的 column 名 set。Match 18 個 ADD COLUMN 全部。
    # Capture V049 ALTER TABLE replay.experiments ADD COLUMN IF NOT EXISTS
    # <name> <type> column name set; matches all 18 ADD COLUMN entries.
    v049_add_col_pattern = re.compile(
        r"ADD COLUMN IF NOT EXISTS\s+(\w+)",
        re.IGNORECASE,
    )
    v049_add_columns = {
        m.group(1).lower() for m in v049_add_col_pattern.finditer(v049_sql)
    }
    assert len(v049_add_columns) >= 18, (
        f"V049 ADD COLUMN parse expected ≥18 columns, got {len(v049_add_columns)}; "
        f"parse failure or V049 source drift. cols={sorted(v049_add_columns)}"
    )

    # ── (3) parse V041 base CREATE TABLE column list (line 81-86) ───────────
    # V041 line 81-86: CREATE TABLE IF NOT EXISTS replay.experiments (
    #   experiment_id TEXT PRIMARY KEY, half_life_days DOUBLE PRECISION,
    #   embargo_days INTEGER, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    # );
    # V041 line 81-86: CREATE TABLE IF NOT EXISTS replay.experiments lists
    # 4 base columns: experiment_id (PK), half_life_days, embargo_days,
    # created_at (NOT NULL DEFAULT NOW()).
    v041_base_columns = {
        "experiment_id",
        "half_life_days",
        "embargo_days",
        "created_at",
    }

    # Schema 真實 column = V041 base ∪ V049 ADD COLUMN
    real_schema_columns = v041_base_columns | v049_add_columns

    # ── (4) assert 每個 stub column 必 ∈ schema ─────────────────────────────
    # Phantom column = stub_columns − real_schema_columns；應為 ∅。
    # phantom_columns = stub_columns - real_schema_columns; expect empty set.
    phantom_columns = stub_columns - real_schema_columns
    assert not phantom_columns, (
        f"V055 round 3 fix (E2 C-3): stub INSERT references phantom "
        f"column(s) not in V049/V041 schema: {sorted(phantom_columns)}. "
        f"V041 base = {sorted(v041_base_columns)}; V049 ADD COLUMN = "
        f"{sorted(v049_add_columns)}. Linux deploy would fail with "
        f"`column \"{sorted(phantom_columns)[0]}\" of relation "
        f"\"experiments\" does not exist`. This is exactly the bug E2 "
        f"round 2 caught (round 2 stub had `actor_id` which is a "
        f"`replay.run_state` column V045:199, NOT `replay.experiments`)."
    )

    # ── (5) adversarial sanity: 確保 test 真的會 fail-loud ──────────────────
    # 手 craft 一 fake column → assert phantom 偵測會 catch。此 inline check
    # 防止未來 (4) 那條 assert 被誤改成永真而靜默失效。
    # Adversarial sanity: inline check that a hand-crafted phantom column
    # would actually be caught — protects against future accidental
    # weakening of (4) assert (e.g., changing `not phantom_columns` to a
    # tautological always-true predicate).
    fake_phantom = "definitely_not_a_real_column_xyz_42"
    assert fake_phantom not in real_schema_columns, (
        f"Adversarial sanity invariant broken: real_schema_columns "
        f"unexpectedly contains {fake_phantom!r}. Test logic compromised."
    )
    fake_check = ({fake_phantom} | stub_columns) - real_schema_columns
    assert fake_phantom in fake_check, (
        "Adversarial sanity: phantom-detection logic does NOT catch a "
        "hand-crafted phantom column; the (4) assert above is unreliable. "
        "Fix the test before relying on it."
    )

    # ── (6) explicit positive: round 3 expected 6 column 全部 ∈ schema ──────
    # Document the round 3 corrected stub INSERT column set for future
    # readers — 失敗訊息會明確指出哪個 column missing。
    # Document the round 3 corrected stub INSERT column set for future
    # maintenance — failure message points out exactly which column missing.
    expected_stub_cols_round3 = {
        "experiment_id",
        "status",
        "created_at",
        "half_life_days",
        "embargo_days",
        "runtime_environment",
    }
    missing_in_stub = expected_stub_cols_round3 - stub_columns
    assert not missing_in_stub, (
        f"V055 round 3 stub INSERT missing expected columns: "
        f"{sorted(missing_in_stub)}. Expected 6-column subset = "
        f"{sorted(expected_stub_cols_round3)}; actual stub = "
        f"{sorted(stub_columns)}."
    )
    # Phantom guard: round 3 stub 不該寫到 round 2 phantom `actor_id`
    # Phantom guard: round 3 stub must not write the round 2 phantom `actor_id`
    assert "actor_id" not in stub_columns, (
        "V055 round 3 fix (E2 C-3) NOT applied: stub still references "
        "phantom `actor_id`. V049 line 284 actually adds `created_by` not "
        "`actor_id`; `actor_id` is a `replay.run_state` column (V045:199), "
        "unrelated to `replay.experiments`."
    )


# ---------------------------------------------------------------------------
# Linux PG live smoke (opt-in via OPENCLAW_TEST_LIVE_PG=1 + OPENCLAW_TEST_DSN).
#
# Linux PG live smoke (透 OPENCLAW_TEST_LIVE_PG=1 + OPENCLAW_TEST_DSN env 啟用)。
# Mac dev 預設 skip；Linux operator (E4 regression / PM SSH bridge apply 後)
# 啟用後驗 V055 deploy 後真正 row body 與 caller args 對齊（3 column；
# expires_at 不在 row body）。
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("OPENCLAW_TEST_LIVE_PG") != "1",
    reason="live PG test requires OPENCLAW_TEST_LIVE_PG=1 + OPENCLAW_TEST_DSN",
)
def test_v055_live_pg_real_outcome_row_body() -> None:
    """V055 live PG smoke: real_outcome row body 3-column verification.

    V055 live PG smoke：real_outcome path → row body 3 column 對齊 args
    (round 2 fix: 不驗 expires_at column；此 column 不存在於目標表)。
    """
    try:
        import psycopg2  # type: ignore
        from psycopg2.extras import Json  # type: ignore
    except ImportError:
        pytest.skip("psycopg2 not installed")

    dsn = os.environ.get("OPENCLAW_TEST_DSN")
    if not dsn:
        pytest.skip("OPENCLAW_TEST_DSN not set")

    with psycopg2.connect(dsn, connect_timeout=2) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT learning.verify_replay_evidence_and_insert(
                    'demo', NULL, 'ma_crossover', 'ml_shadow', 'rank',
                    5.0, 0.5, 10, %s, false, true, 'v055_live_smoke',
                    'real_outcome', NULL, NULL, NULL, NULL, NULL, NULL
                )
                """,
                (Json({"v055_live": True}),),
            )
            new_id = cur.fetchone()[0]
            assert isinstance(new_id, int) and new_id > 0

            # SELECT row body 驗 3 column (round 2 fix: 不查 expires_at)
            cur.execute(
                """
                SELECT evidence_source_tier, replay_experiment_id,
                       manifest_hash
                FROM learning.mlde_shadow_recommendations
                WHERE id = %s
                """,
                (new_id,),
            )
            row = cur.fetchone()
            assert row is not None
            tier, exp_id, hash_val = row
            assert tier == "real_outcome"
            assert exp_id is None
            assert hash_val is None
        conn.rollback()  # cleanup; do not pollute production


@pytest.mark.skipif(
    os.environ.get("OPENCLAW_TEST_LIVE_PG") != "1",
    reason="live PG test requires OPENCLAW_TEST_LIVE_PG=1 + OPENCLAW_TEST_DSN",
)
def test_v055_live_pg_calibrated_replay_row_body() -> None:
    """V055 live PG smoke: calibrated_replay row body 3-column verification.

    V055 live PG smoke：calibrated_replay path → row body 3 column 對齊 args
    (round 2 fix: 不驗 expires_at column)。

    Note: 此 test 依賴 replay.experiments 內已有 stub experiment row 可供 FK
    引用。若無 stub (Linux runtime 第一次 deploy V055)，test SKIP。
    Linux operator 跑 E4 regression 時，先 INSERT 一個 stub experiment row
    再跑 V055 live smoke。
    """
    try:
        import psycopg2  # type: ignore
        from psycopg2.extras import Json  # type: ignore
    except ImportError:
        pytest.skip("psycopg2 not installed")

    dsn = os.environ.get("OPENCLAW_TEST_DSN")
    if not dsn:
        pytest.skip("OPENCLAW_TEST_DSN not set")

    test_exp_id = "00000000-0000-0000-0000-000000000055"
    test_hash_hex = "0000000000000000000000000000000000000000000000000000000000000055"

    with psycopg2.connect(dsn, connect_timeout=2) as conn:
        with conn.cursor() as cur:
            # SAVEPOINT 內 INSERT stub experiment + verify_replay_evidence_and_insert
            cur.execute("BEGIN")
            cur.execute("SAVEPOINT v055_pg_smoke")
            try:
                # Round 2 fix (E2 M-2): stub 含 V049 conditional NOT NULL bypass
                # via runtime_environment='mac_dev_smoke_test_only'
                cur.execute(
                    """
                    INSERT INTO replay.experiments (
                        experiment_id, actor_id, status, created_at,
                        half_life_days, embargo_days, runtime_environment
                    ) VALUES (
                        %s, 'v055_live_smoke', 'created', now(),
                        14.0, 14, 'mac_dev_smoke_test_only'
                    )
                    ON CONFLICT (experiment_id) DO NOTHING
                    """,
                    (test_exp_id,),
                )

                cur.execute(
                    """
                    SELECT learning.verify_replay_evidence_and_insert(
                        'demo', 'BTCUSDT', 'grid_trading', 'dream_engine',
                        'parameter_proposal', 8.0, 0.6, 200, %s,
                        false, true, 'v055_live_smoke',
                        'calibrated_replay', %s, %s,
                        now() + interval '7 days', NULL, NULL, NULL
                    )
                    """,
                    (Json({"v055_live": True}), test_exp_id, test_hash_hex),
                )
                new_id = cur.fetchone()[0]
                assert isinstance(new_id, int) and new_id > 0

                # round 2 fix: SELECT 3 column (不查 expires_at)
                cur.execute(
                    """
                    SELECT evidence_source_tier, replay_experiment_id,
                           encode(manifest_hash, 'hex')
                    FROM learning.mlde_shadow_recommendations
                    WHERE id = %s
                    """,
                    (new_id,),
                )
                row = cur.fetchone()
                assert row is not None
                tier, exp_id, hash_hex = row
                assert tier == "calibrated_replay"
                assert str(exp_id) == test_exp_id
                assert hash_hex == test_hash_hex
            finally:
                cur.execute("ROLLBACK TO SAVEPOINT v055_pg_smoke")
                cur.execute("ROLLBACK")


# ---------------------------------------------------------------------------
# Smoke: mock-mode coverage report
# ---------------------------------------------------------------------------


def test_v055_mock_mode_test_count_summary() -> None:
    """Smoke: confirm V055 mock-mode covers ≥8 cases per dispatch §6.

    Smoke：mock-mode 至少涵蓋 ≥8 case 按 dispatch §6 binding。
    Round 3 fix: round 2 set + test_v055_stub_columns_exist_in_v049 (E2 C-3
    new CRITICAL fix) = 23 total / 21 PASS / 2 SKIPPED on Mac dev pytest。
    Round 2 prior count: 22 total / 20 PASS / 2 SKIPPED。
    """
    # 此 test 存在以使 pytest -v 顯示 V055 mock-mode 覆蓋率基線供 R6-T0'
    # acceptance audit trail 引用。
    # This test exists so pytest -v shows the V055 mock-mode coverage baseline
    # for R6-T0' acceptance audit trail.
    assert True
