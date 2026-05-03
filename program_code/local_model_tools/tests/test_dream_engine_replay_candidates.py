"""Wave 6 R20-P4-Q4 — DreamEngine generate_replay_candidates() unit tests.

Wave 6 R20-P4-Q4 — DreamEngine generate_replay_candidates() 單元測試。

MODULE_NOTE (EN):
    5 acceptance test cases for the new ``generate_replay_candidates()``
    API surface added to ``local_model_tools/dream_engine.py``. The tests
    cover:

      1. Generate 100 candidates with default n_candidates → list len == 100,
         all entries are ``ReplayCandidate`` dataclass instances.
      2. cell_key + symbol filter → fixture_payload_hash differs across
         distinct (symbol, cell_key) combinations (reproducibility +
         non-collision invariant).
      3. fixture_source dispatch → S2 yields confidence != 'none' (when
         calibrated), S3 always yields 'none' (V3 §6.2 non-actionable).
      4. Sort by expected_edge_bps descending → strict monotone non-increasing.
      5. All candidates carry valid Q3 selection_bias metadata
         (total_candidates_K + selection_method + sample_seed +
         intent_fingerprint + wave6_baseline keys non-empty).

    The tests are pure-Python (no DB / no exchange / no network); they
    instantiate ``ReplayIntent`` and call ``generate_replay_candidates``
    directly. ``conftest.py`` adds ``program_code/`` to ``sys.path`` so the
    ``local_model_tools.dream_engine`` import path resolves on Mac dev +
    Linux runtime alike.

MODULE_NOTE (中):
    新增 ``generate_replay_candidates()`` API 表面的 5 個驗收 test。
    Test 涵蓋：

      1. 預設 n_candidates 生成 100 候選 → list 長度 == 100，所有 entry
         皆 ``ReplayCandidate`` dataclass。
      2. cell_key + symbol filter → fixture_payload_hash 跨不同 (symbol,
         cell_key) 必異 (reproducibility + non-collision 不變量)。
      3. fixture_source dispatch → S2 calibrated 時 confidence != 'none'，
         S3 永遠 'none' (V3 §6.2 非 actionable)。
      4. 依 expected_edge_bps 由大到小排序 → 嚴格單調非升。
      5. 所有候選帶有有效 Q3 selection_bias metadata。

    Test 為純 Python (0 DB / 0 exchange / 0 network)；直接實例化
    ``ReplayIntent`` 並呼 ``generate_replay_candidates``。``conftest.py``
    將 ``program_code/`` 加入 ``sys.path``，``local_model_tools.dream_engine``
    在 Mac dev + Linux runtime 兩端皆可解析。

SPEC:
  - REF-20 V3 §6.1 / §8.3 / §12 #6 / §12 #17
Workplan:
  docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4 Wave 6 R20-P4-Q4
"""

from __future__ import annotations

import pytest

from local_model_tools.dream_engine import (
    MAX_CANDIDATES_PER_INTENT,
    ReplayCandidate,
    ReplayIntent,
    generate_replay_candidates,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: generate 100 candidates with default n_candidates.
# Test 1：預設 n_candidates 生成 100 候選。
# ─────────────────────────────────────────────────────────────────────────────


def test_generate_100_candidates_default():
    """100 candidates is the documented default + clean dataclass instances.

    100 候選為文件預設 + 全為 dataclass 實例。
    """
    intent = ReplayIntent(
        strategy_id="grid_trading",
        symbol="BTCUSDT",
        cell_key="grid_trading::BTCUSDT::buy",
        fixture_source="s2_bybit_public",
        manifest_id="00000000-0000-0000-0000-000000000001",
    )
    candidates = generate_replay_candidates(
        intent, seed=42, is_calibrated=True, sample_count=200
    )
    # Default n_candidates is 100 per ReplayIntent dataclass default.
    # ReplayIntent dataclass default n_candidates = 100。
    assert len(candidates) == 100
    # All entries are ReplayCandidate instances; no fall-through dicts.
    # 所有 entry 皆 ReplayCandidate；沒有殘留 dict。
    assert all(isinstance(c, ReplayCandidate) for c in candidates)
    # candidate_id is unique uuid4 hex (32 chars).
    # candidate_id 為 uuid4 hex (32 chars)，唯一。
    candidate_ids = [c.candidate_id for c in candidates]
    assert len(set(candidate_ids)) == len(candidate_ids)
    assert all(len(cid) == 32 for cid in candidate_ids)
    # strategy_params non-empty + JSONB-compatible (str / float values).
    # strategy_params 非空且 JSONB 相容。
    for c in candidates:
        assert c.strategy_params
        for k, v in c.strategy_params.items():
            assert isinstance(k, str)
            assert isinstance(v, (int, float))


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: cell_key + symbol filter — payload hash differs across cells.
# Test 2：cell_key + symbol filter — payload hash 跨 cell 必異。
# ─────────────────────────────────────────────────────────────────────────────


def test_cell_key_and_symbol_filter_payload_hash_unique():
    """Distinct (symbol, cell_key) → distinct fixture_payload_hash.

    不同 (symbol, cell_key) → 不同 fixture_payload_hash。

    Reproducibility + non-collision invariant: two intents differing only
    in ``symbol`` (or ``cell_key``) MUST yield candidates whose
    ``fixture_payload_hash`` does not collide. Otherwise V043
    advisory log cannot disambiguate cross-cell candidates.

    Reproducibility + 非碰撞不變量。
    """
    intent_btc = ReplayIntent(
        strategy_id="grid_trading",
        symbol="BTCUSDT",
        cell_key="grid_trading::BTCUSDT::buy",
        fixture_source="s2_bybit_public",
        manifest_id="00000000-0000-0000-0000-000000000002",
        n_candidates=10,
    )
    intent_eth = ReplayIntent(
        strategy_id="grid_trading",
        symbol="ETHUSDT",
        cell_key="grid_trading::ETHUSDT::buy",
        fixture_source="s2_bybit_public",
        manifest_id="00000000-0000-0000-0000-000000000002",
        n_candidates=10,
    )
    btc_candidates = generate_replay_candidates(
        intent_btc, seed=99, is_calibrated=True, sample_count=200
    )
    eth_candidates = generate_replay_candidates(
        intent_eth, seed=99, is_calibrated=True, sample_count=200
    )
    btc_hashes = {c.fixture_payload_hash for c in btc_candidates}
    eth_hashes = {c.fixture_payload_hash for c in eth_candidates}
    # No overlap — even with same seed, different (symbol, cell_key) salts
    # the payload hash bytes.
    # 即使同 seed，不同 (symbol, cell_key) 鹽化 payload hash bytes，
    # 故無交集。
    assert btc_hashes.isdisjoint(eth_hashes), (
        f"BTC and ETH cells share payload hashes: "
        f"{btc_hashes & eth_hashes}"
    )
    # Reproducibility: same intent + same seed → same hashes.
    # 重現性：同 intent + 同 seed → 同 hash。
    btc_repeat = generate_replay_candidates(
        intent_btc, seed=99, is_calibrated=True, sample_count=200
    )
    btc_repeat_hashes = {c.fixture_payload_hash for c in btc_repeat}
    assert btc_hashes == btc_repeat_hashes


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: fixture_source dispatch — S2 calibrated != none, S3 always none.
# Test 3：fixture_source dispatch — S2 calibrated != none，S3 永遠 none。
# ─────────────────────────────────────────────────────────────────────────────


def test_fixture_source_dispatch_confidence():
    """S3 synthetic always 'none'; S2 calibrated yields high/medium/low.

    S3 synthetic 永遠 'none'；S2 calibrated 給出 high / medium / low。

    V3 §6.2 + §6.3 invariant: synthetic / Mac fixtures non-actionable;
    actionable confidence requires S2 + calibrated + sample power.

    V3 §6.2 + §6.3 不變量：synthetic / Mac fixture 非 actionable；
    actionable 需 S2 + calibrated + sample 充足。
    """
    intent_s2 = ReplayIntent(
        strategy_id="ma_crossover",
        symbol="BTCUSDT",
        cell_key="ma_crossover::BTCUSDT::buy",
        fixture_source="s2_bybit_public",
        manifest_id="00000000-0000-0000-0000-000000000003",
        n_candidates=20,
    )
    intent_s3 = ReplayIntent(
        strategy_id="ma_crossover",
        symbol="BTCUSDT",
        cell_key="ma_crossover::BTCUSDT::buy",
        fixture_source="s3_synthetic",
        manifest_id="00000000-0000-0000-0000-000000000003",
        n_candidates=20,
    )

    # S2 + calibrated + n=200 → 'high'
    s2_high = generate_replay_candidates(
        intent_s2, seed=7, is_calibrated=True, sample_count=200
    )
    assert all(c.confidence == "high" for c in s2_high)

    # S2 + calibrated + n=50 → 'medium'
    s2_medium = generate_replay_candidates(
        intent_s2, seed=7, is_calibrated=True, sample_count=50
    )
    assert all(c.confidence == "medium" for c in s2_medium)

    # S2 + uncalibrated → 'low'
    s2_low = generate_replay_candidates(
        intent_s2, seed=7, is_calibrated=False, sample_count=200
    )
    assert all(c.confidence == "low" for c in s2_low)

    # S3 → 'none' regardless of calibration / sample_count.
    # S3 不論 calibration / sample_count 為何 → 'none'。
    s3_calibrated = generate_replay_candidates(
        intent_s3, seed=7, is_calibrated=True, sample_count=500
    )
    assert all(c.confidence == "none" for c in s3_calibrated)
    s3_uncalibrated = generate_replay_candidates(
        intent_s3, seed=7, is_calibrated=False, sample_count=0
    )
    assert all(c.confidence == "none" for c in s3_uncalibrated)


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: sort by expected_edge_bps descending — strict monotone non-increasing.
# Test 4：依 expected_edge_bps 由大到小排序 — 嚴格單調非升。
# ─────────────────────────────────────────────────────────────────────────────


def test_candidates_sorted_by_expected_edge_descending():
    """Output order MUST be expected_edge_bps[i] >= expected_edge_bps[i+1].

    輸出順序必為 expected_edge_bps[i] >= expected_edge_bps[i+1]。

    The contract is that callers (replay_routes.py POST /run) can grab the
    top-K candidates without resorting.

    契約是 caller (replay_routes.py POST /run) 可直接取 top-K 而不需重排。
    """
    intent = ReplayIntent(
        strategy_id="bb_breakout",
        symbol="BTCUSDT",
        cell_key="bb_breakout::BTCUSDT::buy",
        fixture_source="s2_bybit_public",
        manifest_id="00000000-0000-0000-0000-000000000004",
        n_candidates=50,
    )
    candidates = generate_replay_candidates(
        intent, seed=2026, is_calibrated=True, sample_count=300
    )
    edges = [c.expected_edge_bps for c in candidates]
    # Strict monotone non-increasing — equality permitted (ties).
    # 嚴格單調非升 — 允許 tie。
    for i in range(len(edges) - 1):
        assert edges[i] >= edges[i + 1], (
            f"Sort violated at index {i}: {edges[i]} < {edges[i + 1]}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: all candidates carry valid Q3 selection_bias metadata.
# Test 5：所有候選帶有有效 Q3 selection_bias metadata。
# ─────────────────────────────────────────────────────────────────────────────


def test_all_candidates_carry_selection_bias_metadata():
    """V3 §8.3 + §12 #17 selection_bias_metadata is mandatory + non-empty.

    V3 §8.3 + §12 #17 selection_bias_metadata 為必要且非空。

    Required keys:
      - total_candidates_K (int, V3 §8.3 mandatory)
      - selection_method (str)
      - sample_seed (int)
      - intent_fingerprint (str, 16 hex chars)
      - wave6_baseline (bool, marks pre-DSR/PBO baseline output)

    必填 key：總候選 K / 取樣方法 / 種子 / intent fingerprint / Wave 6 baseline。
    """
    intent = ReplayIntent(
        strategy_id="bb_reversion",
        symbol="ETHUSDT",
        cell_key="bb_reversion::ETHUSDT::sell",
        fixture_source="s2_bybit_public",
        manifest_id="00000000-0000-0000-0000-000000000005",
        n_candidates=15,
    )
    candidates = generate_replay_candidates(
        intent, seed=314, is_calibrated=True, sample_count=100
    )
    required_keys = {
        "total_candidates_K",
        "selection_method",
        "sample_seed",
        "intent_fingerprint",
        "wave6_baseline",
    }
    for c in candidates:
        meta = c.selection_bias_metadata
        # Non-empty + mandatory keys present.
        # 非空 + 必填 key 都在。
        assert meta, "selection_bias_metadata must not be empty"
        assert required_keys.issubset(meta.keys()), (
            f"missing keys: {required_keys - meta.keys()}"
        )
        # Type check + V3 §8.3 K = n_actual contract.
        # 型別檢查 + V3 §8.3 K = n_actual 契約。
        assert isinstance(meta["total_candidates_K"], int)
        assert meta["total_candidates_K"] == 15
        assert isinstance(meta["selection_method"], str)
        assert meta["selection_method"] == "parameter_axis_uniform_jitter"
        assert isinstance(meta["sample_seed"], int)
        assert meta["sample_seed"] == 314
        assert isinstance(meta["intent_fingerprint"], str)
        assert len(meta["intent_fingerprint"]) == 16
        assert meta["wave6_baseline"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Bonus: input validation — defensive raises ValueError on bad intent.
# Bonus：輸入驗證 — 壞 intent 觸發 ValueError。
# ─────────────────────────────────────────────────────────────────────────────


def test_invalid_intent_raises_value_error():
    """Defensive: invalid ``ReplayIntent`` fields → ValueError.

    防禦性：無效 ``ReplayIntent`` 欄位 → ValueError。
    """
    # Empty strategy_id.
    with pytest.raises(ValueError, match="strategy_id"):
        generate_replay_candidates(
            ReplayIntent(
                strategy_id="",
                symbol="BTCUSDT",
                cell_key="x::y::buy",
                fixture_source="s2_bybit_public",
                manifest_id="00000000-0000-0000-0000-000000000006",
            )
        )
    # n_candidates <= 0.
    with pytest.raises(ValueError, match="n_candidates"):
        generate_replay_candidates(
            ReplayIntent(
                strategy_id="grid_trading",
                symbol="BTCUSDT",
                cell_key="grid_trading::BTCUSDT::buy",
                fixture_source="s2_bybit_public",
                manifest_id="00000000-0000-0000-0000-000000000007",
                n_candidates=0,
            )
        )
    # n_candidates clamped to MAX_CANDIDATES_PER_INTENT (no raise).
    # n_candidates 夾到 MAX_CANDIDATES_PER_INTENT (不 raise)。
    huge_intent = ReplayIntent(
        strategy_id="grid_trading",
        symbol="BTCUSDT",
        cell_key="grid_trading::BTCUSDT::buy",
        fixture_source="s2_bybit_public",
        manifest_id="00000000-0000-0000-0000-000000000008",
        n_candidates=MAX_CANDIDATES_PER_INTENT + 100,
    )
    huge_out = generate_replay_candidates(
        huge_intent, seed=1, is_calibrated=True, sample_count=200
    )
    assert len(huge_out) == MAX_CANDIDATES_PER_INTENT
