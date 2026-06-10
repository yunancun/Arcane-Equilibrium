# E1 IMPL — Residual PART 4 Phase 2: Gap A orchestrator + Gap D

**Date**: 2026-06-08
**Branch/worktree**: `feature/residual-activation` @ `/private/tmp/wt-residual-act` (builds on P1 `da3aec6f`+`c6cc1578`)
**Commit**: `2a5df09e` (on branch, NOT pushed — chain E1→E2→E4→PM)
**Status**: E1 IMPLEMENTATION DONE — awaiting E2

---

## 任務摘要

把 β-residualization 晉升閘從「INERT by absence of producer inputs」變成**真正審判真實候選**（closes defer-by-absence），但**三重 flag-gated OFF**（部署即行為中性，零新 row / 零生產 cron 新路徑；operator 評估後才啟用）。嚴格執行 PA design §2 Gap A + Gap D + **PA REVISED ruling**（NO peer synthesis，PBO 誠實 defer），不做 A-full Rust replay。

---

## 修改清單

### 新檔
| 檔 | LOC | 用途 |
|---|---|---|
| `program_code/ml_training/residual_stage0r_preflight.py` | 727 | **orchestrator**（6-step flow，純編排 + 薄寫入） |
| `program_code/ml_training/tests/test_residual_stage0r_preflight.py` | 813 | 21 測（6-step / idempotency / fail-closed / no-peer / hash-identity / beta-trap / net_side / Gap D） |
| `helper_scripts/cron/tests/test_residual_preflight_cron.py` | 120 | 9 測（cron 行為中性 / dispatcher / flags-off skipped） |
| `helper_scripts/cron/residual_stage0r_preflight_cron.sh` | 126 | CLI shim（Linux-only / lock-dir / fail-soft / 三重 OFF doc） |

### 改檔
| 檔 | Δ | 改動 |
|---|---|---|
| `helper_scripts/cron/ml_training_maintenance.py` | +131/−? | `OPTIONAL_JOBS=("residual_preflight",)` 進 VALID_JOBS 但**不在 DEFAULT_JOBS**；`_run_residual_preflight`（flag gate + 建 cfg/actor/get_pg_conn）；`_parse_iso_env`；dispatcher 接線 |
| `program_code/ml_training/promotion_evidence.py` | +46/−? | 抽出 `write_demo_residual_alpha_report`（薄 drar writer）；`_persist_residual_alpha_report` 委派之（byte-identical） |
| `program_code/ml_training/residual_alpha_producer_db.py` | +186 | `derive_net_side_from_fills`/`load_candidate_net_side`（net_side）+ `load_symbol_lifecycles`/`load_klines_by_symbols`（多因子 DB 來源） |
| `program_code/learning_engine/residual_alpha_producer.py` | +17 | thread permutation 4 參數進 `build_residual_alpha_report`→protocol（defaults OFF，byte-identical） |
| `helper_scripts/SCRIPT_INDEX.md` | +6 | 註冊 CLI shim |

**無 migration**（lineage 欄位 `replay_experiment_id`/`manifest_hash`/`evidence_source_tier` 已存在）。

---

## 6-step 流程（orchestrator）

每個「數值預閘達標（expected_net_bps≥5/confidence≥0.65/sample≥30）但缺 lineage（`replay_experiment_id IS NULL`）」的 demo shadow rec：

1. **多因子 residual + permutation**：`evaluate_cell(required_factors=("btc","market","funding"), peer_variant_round_trips=None, permutation_enabled=True)` via bridge `**gate_kwargs`。PBO **誠實 defer**（無 peer → 既有 `pbo_missing_candidate_returns → defer_data`）。
2. **REAL net_side**：`load_candidate_net_side`（讀 trading.fills 入場成交淨 signed-qty 符號）；ambiguous → fail-closed。**絕不** +1 預設。
3. **Gap D**：`_build_selection_bias_block`（K=n_trials≥10 / oos_pct≥0.20 / cv_protocol / embargo≥7）+ `validate_selection_bias_correction`；fail-closed `selection_bias_invalid:<mode>`（在任何寫入前）。
4. **register experiment**：`register_residual_candidate_experiment`（**REUSE**：寫 replay.experiments + sealed hidden_oos_state_registry，4-layer leak guard）。
5. **write drar**：`write_demo_residual_alpha_report`（非 pass 報告誠實 skip）。
6. **stamp lineage**：`UPDATE mlde_shadow_recommendations SET replay_experiment_id/manifest_hash/evidence_source_tier WHERE id=? AND replay_experiment_id IS NULL`（防重蓋）。

---

## 關鍵設計決策（E2 重點）

### 1. NO peer synthesis（#1 方法論硬規則）
orchestrator 傳 `peer_variant_round_trips=None` → `evaluate_cell` 單配置路徑 → gate 因無 PBO peer 走**既有** `pbo_missing_candidate_returns`/`defer_data`。**絕不**捏造/重組 peer，**絕不**新增 verdict literal。grep-style 測試 `test_no_peer_synthesis_candidate_oos_returns_none` 攔 `evaluate_cell` 斷言實參 `peer_variant_round_trips is None` + verdict ∈ {promote,borderline,block,defer_data,pass,fail}。**mutation 驗**：改傳 fabricated peer → 測試紅。

### 2. Hash byte-identity（PA §5.6，最易靜默壞）— capturing register_fn wrapper
`run_register_in_pg_xact` 的 result **不回傳 report**。orchestrator 用 wrapping register_fn 從 **`body.manifest_jsonb[demo_residual_alpha_report]`** 抓那份 report（= registry hash 的 EXACT 物件），drar 用同一份算 hash，**絕不重算**（重算=第二序列化路徑→漂移）。三寫者（bridge canonical / drar report_hash / registry residual hash）同 canonical bytes。**mutation 驗**：把 wrapper capture 改 `{**rpt,"_mutated":True}` → drar-hash 測試紅。

### 3. net_side 從真實 fills 推導（MIT 硬條件）
`load_round_trips` FIFO 配對丟 side。新 `derive_net_side_from_fills` 從候選**入場成交**（strategy_name 匹配 + realized_pnl==0）淨 signed-qty（Buy+1/Sell−1）取符號。**用 +1 套到淨做空候選 → funding factor 反號 → 殘差化放大 carry beta = false-promote 向量**。測試 `test_net_side_long_candidate`（Buy→+1）+ short fixture（Sell→−1）。

### 4. P1 漏接線補上（permutation threading）
P1 把 permutation 加進 GATE protocol 但 `build_residual_alpha_report` **沒 thread**（硬編 protocol、無 `**kwargs`）→ `evaluate_cell(permutation_enabled=True)` 會 TypeError。補 4 參數（defaults OFF，byte-identical）。

### 5. Gap D embargo_days 與 sealed embargo_seconds 是兩個概念（澄清）
- sealed hidden_oos_state.`embargo_seconds` = 內部 train→eval purge `(eb+0.5)*bucket_sec` ≈ 0.25d。
- Gap D block `embargo_days` = V3 §8.3 selection-bias provenance floor（≥7）。
故 block `embargo_days` 由 cfg 顯式提供（預設 7），**不**沿用 sealed embargo_seconds（會 <7 撞 EMBARGO_TOO_LOW）。已於 `_build_selection_bias_block` docstring 文件化。

---

## 治理對照

| 硬約束 | 落實 |
|---|---|
| 行為中性（flags OFF + job absent ⇒ 零 row / 零生產路徑） | 三重 OFF：`OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT`(0) + `OPENCLAW_RESIDUAL_ALPHA_PRODUCER`(0) + 不在 DEFAULT_JOBS。`test_behavior_neutral_*`（conn_factory 0 call）+ cron `test_*_skipped_when_*_flag_off`（status=skipped 非 error） |
| DEMO evidence lane ONLY | 只寫 replay.experiments / hidden_oos_state_registry / demo_residual_alpha_reports + rec-stamp UPDATE；讀 demo only。`test_demo_lane_only_no_live_mutation` grep 禁字 0 hit |
| 零 live/auth/order/risk/lease 變動 | grep `live_reserved\|max_retries\|live_execution_allowed\|OPENCLAW_ALLOW_MAINNET\|authorization.json\|execution_authority\|decision_lease_emitted` on diff = **0 hits**。live-candidate INSERT 留 mlde_demo_applier（需 GovernanceHub+Lease，未碰） |
| NO peer synthesis / 無新 verdict literal | `candidate_oos_returns=None` → 既有 defer；verdict 落合法集合（測試斷言） |
| Hash byte-identity | capturing wrapper（§5.6）；cross-writer 測 + mutation 驗 |
| PIT/leak | hidden-OOS hold-out 由 bridge 強制（strict exit<oos_start + 跨界桶 DATA 過濾，P1/d5ec22d3 已驗）；net_side 真實；permutation in-window；idempotent re-run |
| 跨平台 | 0 hardcoded user path（shim 用 `$HOME`-relative 對齊 sibling cron） |
| 注釋規範 | 全中文 MODULE_NOTE + 中文 rationale（英文保留技術詞/SQL/symbol） |
| singleton | orchestrator 無新 mutable singleton（純函數 + dataclass cfg + per-call state） |

---

## 驗收（誠實）

- **full ml_training + learning_engine**：`848 passed, 31 skipped`（baseline 827/31 + **21 新** = orchestrator 測檔；**0 回歸**）。
- **cron tests**：`53 passed`（44 ac19 + 9 新）。
- **residual cluster（10 檔）**：`170 passed`。
- **mutation bite 自證**：①破 no-peer（傳 fabricated peer）→ `test_no_peer_synthesis` 紅；②破 hash-capture（mutate captured report）→ `test_drar_hash_matches_registry` 紅。兩者還原後 byte-identical 全綠。
- **py_compile** 全改檔 OK；**bash -n** shim OK。
- 命令：`PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 PYTHONPATH=/private/tmp/wt-residual-act python3 -m pytest program_code/ml_training/tests program_code/learning_engine/tests -q`。

---

## 不確定之處 / Deviation from spec

1. **drar 只寫 PASS 報告（沿用既有 `_persist_residual_alpha_report` 行為，非新增）**：`validate_demo_residual_alpha_report` 要 `verdict=="pass"`，故 real 候選的 defer/fail 報告 → drar skip（`drar_written=False`）。這是 by-design（下游 source contract 第一道也是該 validator，defer 報告本就擋在最前），非 bug。E2 確認此語意可接受。
2. **多因子 DB 來源 loaders 加在 `producer_db.py`**（非 orchestrator 私有）：`load_symbol_lifecycles`/`load_klines_by_symbols` 與既有 `load_btc_klines`/`load_funding_rates`/`load_round_trips` 同屬 DB-adapter 層，放一起最自然。schema 已 ssh 查證（market.symbol_universe_snapshots listed_at/delisted_at populate 948 symbol；market.klines 4h 142 symbol）。
3. **Gap D `embargo_days` 用 cfg 預設 7（非 sealed embargo_seconds）**：見上「關鍵設計決策 §5」。這是兩個獨立 embargo 概念，已文件化。若 E2/PA 認為 selection-bias embargo 應另有來源，可調 cfg。
4. **`net_side` 推導未擴 `load_round_trips`**（brief 允許「若 load_round_trips 丟 side 就加 helper」）：選擇加獨立 `load_candidate_net_side`/`derive_net_side_from_fills`（讀 fills 入場成交），不動 `load_round_trips`（最小影響，避免改既有 caller 的回傳 shape）。
5. **orchestrator 727 行 < 800 soft-warn**；測檔 813 行（測檔常規，非生產碼）。

---

## Operator / PM 下一步

- **E2 審查**（重點：行為中性 / hash byte-identity / no-peer-synthesis / net_side / Gap D embargo 語意 / drar-pass-only）。
- **E4 回歸**（full suite 已綠；Linux cargo 無 Rust 改動不受影響）。
- **OWED to PM（Linux flag-ON 真寫驗證）**：`ssh trade-core`，設 `OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT=1` + `OPENCLAW_RESIDUAL_ALPHA_PRODUCER=1` + 時間窗 env，跑 `residual_stage0r_preflight_cron.sh`（或 `ml_training_maintenance.py --jobs residual_preflight`）→ 驗恰 +1 replay.experiments / +1 hidden_oos_state_registry(sealed) / +1 demo_residual_alpha_reports（若 pass）/ stamp 恰 1 rec；再驗 flag OFF → 0 row。預期 real 候選 defer/fail（honest，非失敗）。**+ funding settlement-timing dry-run**（real market.funding_rates，§5.1 PIT）。

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-06-08--residual_part4_phase2_gap_a_orchestrator.md`）
