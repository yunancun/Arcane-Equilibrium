# E2 Sprint N+0 First-Pass Review — W-AUDIT-9 (T1+T2+T3+T6) + W-AUDIT-6d (4/5/6) + W-AUDIT-4b-M1

- **日期**：2026-05-09
- **Mac local HEAD**：`f5574c5a`
- **review scope**：4 wave 5 IMPL commit (`094f9914` E1-A / `200188ad` E1-C / `063f12d0` + `f6fb315a` E1-D / `4a90966a` E1-E) + cross-wave IPC test fail
- **Reports 讀完**：5/5 (E1-A T1+T2 / E1-C T3 / E1-D T6 / E1-D 6d-4/5/6 / E1-D DSR K-12 量化)

---

## TL;DR Verdict per Wave

| Wave | Owner | Local commit | Verdict | 嚴重度 |
|---|---|---|---|---|
| **Wave 1** W-AUDIT-9 T1+T2 (Rust schema + V080) | E1-A | `094f9914` | **RETURN-TO-E1-A** | 1 HIGH (cross-wave IPC test fail E1-A 引入) + 0 MED + 1 LOW |
| **Wave 2** W-AUDIT-9 T3 (Python stage-aware) | E1-C | `200188ad` | **APPROVE** | 0 HIGH + 1 MED (legacy False → Stage 1 投影邊界) + 0 LOW |
| **Wave 3** W-AUDIT-9 T6 + W-AUDIT-6d 4/5/6 | E1-D | `063f12d0` + `f6fb315a` | **APPROVE** | 0 HIGH + 1 MED (governance_core.rs 1838 接 2000 cap) + 0 LOW |
| **Wave 4** W-AUDIT-4b-M1 (V082 + producer) | E1-E | `4a90966a` | **APPROVE** | 0 HIGH + 0 MED + 0 LOW |
| **Cross-wave** IPC test fail (`test_g3_02_a2_patch_executor_*` ×2) | **E1-A** | `094f9914` 後遺 | **BLOCKER** | HIGH — E1-A 補 fix |

**整體 verdict**：**RETURN-TO-E1-A** for cross-wave IPC fix；其餘 3 wave 待 E1-A fix land 後一併放行 E4 regression。

---

## §1 Wave 1 — W-AUDIT-9 T1+T2 (E1-A `094f9914`) RETURN-TO-E1-A

### 1.1 結構驗證 PASS

✓ ExecutorConfig 升級 5-stage：CanaryStage enum 0..=4 + CanaryCohort + stage_entered_at_ms + observation_period_ms
✓ legacy `shadow_mode` 保留為 backward-compat projection（`as_shadow_mode()`：Stage 0 → true / Stage 1+ → false）
✓ validate() 8 條 invariant：
  - shadow_mode == projection 一致性（PA E2 audit point #1）
  - Stage 0 cohort=None / ts=0 / period=0
  - Stage 1/2 必 1×1 cohort + Stage 1=paper / Stage 2=demo
  - Stage 3 cohort=None + 全 universe + period > 0
  - Stage 4 LIVE_PENDING cohort=None
  - cohort.environment ∈ {paper/demo/live_demo/mainnet}
  - stage_entered_at_ms > 0 for Stage 1+
  - observation_period_ms > 0 for Stage 1+

✓ 4 個 risk_config*.toml 全保留 `shadow_mode = true`（serde default 補 Stage 0 + cohort=None）→ runtime 行為 0 改變
✓ V080 Guard A×2 (canary_stage_log + canary_stage_metric_registry) 必要欄位俱在
✓ V080 Guard C 對 hot-path index `idx_canary_stage_log_cohort_created_at` 的 `created_at_ms DESC` ordering 強制
✓ V080 PG-layer CHECK constraint `transition_kind != 'manual_promote' OR decision_lease_id IS NOT NULL`（invariant 11 PA-9）
✓ V080 UNIQUE (stage, metric_name) WHERE active=true partial index（drift 防線）
✓ Linux PG empirical dry-run：idempotent ×2 + manual_promote NULL lease REJECTED + auto_promote NULL ACCEPTED + stage=5 REJECTED + cleanup
✓ 21 個 mock pytest PASS

### 1.2 HIGH-1：Cross-Wave IPC Test Fail（E1-A 引入）

E2 跑 `cargo test -p openclaw_engine --lib --release`：**2622 passed / 2 failed**

```
ipc_server::tests::config::test_g3_02_a2_patch_executor_shadow_mode_via_patch_risk_config FAILED
ipc_server::tests::config::test_g3_02_a2_patch_executor_routes_to_demo_engine FAILED
```

#### Root cause（E2 獨立追蹤）

兩 test 共同 fail message：
```
"validation failed: risk.executor: shadow_mode=false inconsistent with canary_stage=0
 (Stage 0 ⇄ true, Stage 1+ ⇄ false). AMD-2026-05-09-03 §4.4 requires legacy shadow_mode
 equals canary_stage.as_shadow_mode() projection. Update either field atomically
 (TOML/IPC patch must set both)."
```

`rc1_stores()` 起始 `RiskConfig::default()` = `shadow_mode=true` + `canary_stage=Stage0`（一致）。Test patch JSON `{"executor":{"shadow_mode":false}}` 只翻 binary flag 但**未同時** set `canary_stage>=1` 等 4 fields → patch 後狀態 `shadow_mode=false` + `canary_stage=Stage0` → E1-A 新 invariant 拒。

E2 證據：
```bash
cd rust && cargo test --lib -p openclaw_engine --release ipc_server::tests::config::test_g3_02_a2_patch_executor
# test result: FAILED. 2 passed; 2 failed; 0 ignored
```

#### 屬誰：**E1-A `094f9914`**

E1-A T1 invariant 設計**正確**（防 config drift 雞蛋死循環，PA E2 audit point #1）；但 E1-A 應預見並同步更新既存 IPC test —— `test_g3_02_a2_patch_executor_shadow_mode_via_patch_risk_config` (line 426) 與 `test_g3_02_a2_patch_executor_routes_to_demo_engine` (line 549) 兩 test 是 G3-02 Phase A2 既有 binary patch test，T1 invariant land 後它們的 patch JSON 必更新對齊 graduated canary 5-field atomic semantics。

E1-A report §5.4 自報「**First run**（在 sibling B-M1 commit 之前）：`cargo build --release` 通過」+「後 sibling 200188ad commit：cargo build E0063 break」— 但 E2 實測**無視 sibling commit**：E1-A `094f9914` 自身 `cargo test --lib -p openclaw_engine --release` 已 fail 2 IPC test。E1-A 漏跑 ipc_server::tests::config scope（只跑 `config::risk_config` 139 PASS）。

#### Fix scope (RETURN-TO-E1-A)

選 (a) 較推薦：

**(a) 重命名既有 binary test + 新增 stage transition test**：
1. `test_g3_02_a2_patch_executor_shadow_mode_via_patch_risk_config` 改名為 `test_g3_02_a2_patch_executor_binary_shadow_only_rejected_invariant_drift`，斷言：patch `{"executor":{"shadow_mode":false}}` **應**回 validation error（驗 E1-A invariant 主動拒）
2. 新增 `test_g3_02_a2_patch_executor_stage_promotion_via_patch_risk_config`，patch 5-field atomic：
   ```rust
   let req = r#"{"jsonrpc":"2.0","method":"patch_risk_config","params":{"source":"operator","patch":{"executor":{"shadow_mode":false,"canary_stage":1,"canary_cohort":{"strategy":"ma_crossover","symbol":"BTCUSDT","environment":"paper"},"stage_entered_at_ms":1715270400000,"observation_period_ms":604800000}}},"id":9101}"#;
   ```
3. `test_g3_02_a2_patch_executor_routes_to_demo_engine` 同改 5-field atomic + 改 environment="demo" + canary_stage=2

**(b) 替代**（不推薦）：保留既有 binary test，但 wrap patch_risk_config 加「single shadow_mode flip = auto-derive canary_stage」shorthand —— 這違反 PA E2 audit point #1 的 atomicity 要求，**禁**。

#### 嚴重度：HIGH

**理由**：
- 不破 production behavior（4 TOML default 一致 Stage 0）
- 但 IPC patch path test fail = regression，**E2/E4 不能放行**
- E1-A 必補 IPC test fix 後 E2 second-pass 通過

### 1.3 LOW-1：governance.canary_stage_log COMMENT 包含過長英文段（minor）

`governance.canary_stage_log` table COMMENT 行 含舊 binary 路徑 reference + 對 W-AUDIT-9 T3 / T5 / T6 owner cross-link，文字密度高但仍可接受。**不阻 merge**。

---

## §2 Wave 2 — W-AUDIT-9 T3 (E1-C `200188ad`) APPROVE

### 2.1 invariant 9 fail-closed Stage 0 三 path 驗證 PASS

E2 對 `_read_canary_stage` 逐 path 追蹤：

| Path | 場景 | Result | 對齊 invariant 9 |
|---|---|---|---|
| 1a | canary_stage_provider 回 valid CanaryStage | return raw | ✓ success path |
| 1b | canary_stage_provider 回非 CanaryStage（int 0..=4）| return CanaryStage.from_raw(raw) | ✓ from_raw 對 invalid 也 fail-closed Stage 0 |
| 1c | canary_stage_provider 拋 exception | catch → log warning → return SHADOW | ✓ Stage 0（不是 Stage 1）|
| 2a | shadow_mode_provider 回 True（legacy） | SHADOW | ✓ |
| 2b | shadow_mode_provider 回 False（legacy） | PAPER_SINGLE_COHORT | ⚠️ MED-1 邊界 |
| 2c | shadow_mode_provider 拋 exception | catch → log warning → return SHADOW | ✓ |
| 3 | 雙 provider 缺失 | log warning → return SHADOW | ✓ |

invariant 9 critical path（1c / 2c / 3）全 fail-closed Stage 0 ✓。

### 2.2 backward-compat 0 break

✓ 既有 callsite `_read_shadow_mode()` 仍可工作（投影自 stage）
✓ 既有 contract test `test_executor_agent_has_no_unconditional_lambda_true_fallback`（line 56）grep `"lambda: True"` 0 hit + grep `"shadow_mode_provider unavailable"` PASS
✓ ExecutorAgent ctor 只**新增** `canary_stage_provider` Optional arg（line 186），既有 caller 0 break
✓ legacy `shadow_mode=False` config 在 `_parse_response` 的 AMD §4.4 backward-compat reject：legacy `False` 無 `canary_stage` field → reject 至 Stage 0 + log
✓ pytest 39 + 19 + 16 + 8 + 162 + 7 = 255 PASS / 7 skipped / 0 fail (本 review 重跑 85 PASS)

### 2.3 MED-1：legacy False → PAPER_SINGLE_COHORT 投影邊界（accepted trade-off）

`_read_canary_stage` path 2b 把 legacy `shadow_mode_provider` 回 False 投影至 **Stage 1 PAPER_SINGLE_COHORT**（不是 Stage 0）。

**對抗反問**：production runtime 仍只接 `shadow_mode_provider`（strategy_wiring.py line 555）。如果 IPC patch 成功 set canary_stage=2 + shadow_mode=false（atomic），cache 解析 canary_stage=2 但 ExecutorAgent (僅 legacy provider) 看 shadow=False → 投影 Stage 1（不是 Stage 2）→ cohort scope check 看到 paper 環境而非 demo → 路由錯誤。

**E1-C report §6 #1 已自報**：「如 PA / E2 認為 legacy False 應全 reject 至 SHADOW，可改為 Stage 0」。E1-C 選優先 graceful migration。

**E2 verdict**：**ACCEPT trade-off**。理由：
1. 當前 production 4 TOML 全 `shadow_mode=true` + Stage 0 default → production 走 path 2a（True → SHADOW）✓
2. IPC patch atomic set canary_stage=2 + shadow_mode=false 須**等 W-AUDIT-3b runtime smoke 後**配合 PA follow-up 在 strategy_wiring.py 加 `canary_stage_provider=cache.canary_stage_provider()`（E1-C report §8.3 documented）
3. 在 W-AUDIT-3b follow-up 之前，path 2b 的「legacy False → Stage 1」是 lint-level 邊界，0 production exposure

**Follow-up tracker**：必加入 W-AUDIT-3b runtime smoke 的 acceptance criteria：「strategy_wiring.py:549 ExecutorAgent ctor 必同時注入 `canary_stage_provider` 才 valid」。

### 2.4 §九 + 跨平台 + 文件大小

✓ §九 8 條 checklist 全 PASS（無 except:pass / 無 f-string log / 無 detail=str(e) / 無 _xxx 穿透）
✓ 跨平台 grep `/home/ncyu` `/Users/[^/]+` 0 hit
⚠️ `test_executor_agent_unit.py` 809 LOC 剛跨 800 警告（pre-existing baseline 612；W-AUDIT-9 加 +197）—— **不阻 merge**（< 2000 hard cap），但建議 P3 follow-up：fixtures 外移獨立 `tests/test_executor_canary_stage.py` 拆減

---

## §3 Wave 3 — W-AUDIT-9 T6 + W-AUDIT-6d 4/5/6 (E1-D `063f12d0` + `f6fb315a`) APPROVE

### 3.1 LeaseScope::CanaryStagePromotion 設計嚴謹 PASS

✓ TTL 60s strict (AMD §4.5)，不接受 caller override
✓ requires_operator_authority() = true 只在 CanaryStagePromotion variant
✓ acquire_canary_stage_promotion_lease 強制 GovernanceProfile::Production（caller profile 被忽略）→ 永遠走 is_authorized() hard gate
✓ make_canary_stage_promotion_audit_row 接 `&LeaseId`（不接 String）→ caller 不能傳偽 lease_id
✓ LeaseId::Bypass 直接 reject `LeaseScopeNotPermitted`（graduated canary 不適用 Exploration/Validation profile）
✓ LeaseScope enum 4 variant 完整，as_audit_str() 用 exhaustive match 防 typo
✓ 5 lease_scope tests + 4 governance_core::test_canary_stage_* tests 全 PASS

### 3.2 砍 6 grep blacklist 0 命中（E2 獨立 verify）

```bash
git diff bcf4f11a..HEAD --stat -- 'rust/openclaw_engine/src/strategies/'
# bb_reversion/mod.rs +77 / params.rs +55 / tests.rs +286
# 3 files changed, 415 insertions(+), 3 deletions(-)
```

`git diff bcf4f11a HEAD -- 'strategies/ma_crossover/' 'strategies/grid_trading/' 'strategies/bb_breakout/' 'strategies/funding_arb*' 'strategies/grid_helpers.rs'` 全 0 LOC delta ✓ — **invariant 3（PA-3）verified PASS**。

### 3.3 bb_reversion MA gate 邏輯（W-AUDIT-6d #6）PASS

✓ `is_finite()` 過濾 NaN/Inf → fail-closed 不入場 (line 166)
✓ `ma > 0.0` 過濾 0/負值 (line 166)
✓ `_ =>` arm 涵蓋 None + invalid ma_kind → fail-closed (line 174-183)
✓ `require_ma_confirmation=false` 短路（W-AUDIT-9 stage rollback 路徑）(line 162)
✓ entry path gate 位置正確：在 confluence scoring 之前 (line 465-467)
✓ helper auto-derive sma_50 by signal direction (long signal=51000 / short=49000 / neutral=50000) → 14 既有 test 不需逐一改
✓ 38 bb_reversion tests PASS（29 既有 + 9 new W-AUDIT-6d #6）

**對抗反問 1（boundary case）**：`price < ma` strict ⇒ price=ma 邊界拒絕入場，**過保守但安全**（不違 fail-closed）。✓ accept。

### 3.4 portfolio_var min_observations review（W-AUDIT-6d #5）PASS

✓ E1-D review 結論「不下調 200」對齊 statistical baseline：
  - 99% VaR 尾部需 ≥ 200 obs (n_tail = ⌊(1-0.99)×200⌋ = 2 穩定估計)
  - CVaR sampling variance 在 n=100 過大
  - bootstrap CI block_size = ⌈n^(1/3)⌉ 對 n=200 推得 6 合理
  - min_evt_excesses=10 對齊 200 × 5% = 10
✓ sampling unit doc gap fix（per-trade fractional decimal vs percentage）
✓ 5 new W-AUDIT-6d #5 tests PASS

### 3.5 portfolio VaR runtime apply spec（W-AUDIT-6d #4）PASS

✓ `tests/test_promotion_pipeline.py` +179 LOC TestWAudit6dRuntimeApplySpec class 4 tests PASS
✓ 不 deploy（spec/test only）

### 3.6 DSR penalty K -12 量化（invariant 16 FA-7）PASS

E2 獨立驗 Bailey-Lopez de Prado mu_0 公式：

```python
K=25 -> mu_0 = sqrt(2 * ln(25)) = 2.5374
K=13 -> mu_0 = sqrt(2 * ln(13)) = 2.2649
Δ mu_0 = -0.2723
Sensitivity: K=20 -> 2.4477 / K=25 -> 2.5374 / K=30 -> 2.6081
```

✓ E1-D report 數值全部一致（2.54 / 2.27 / -0.27 / sensitivity ✓）
✓ E1-D 自我糾正 TODO.md v19 §7 引用 mu_0=2.83 / 2.27 用了 log₁₀ 假設 → 採 ln（DSR 公式標準）為唯一權威
✓ 結論方向不變（mu_0 仍 < baseline）對 K baseline ±5 robust
✓ §五 invariant 16 sign-off 引用點：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-09--w_audit_6d_dsr_penalty_quantification.md`

### 3.7 MED-2：governance_core.rs 1838 LOC 接 2000 hard cap

E1-D 加 +329 LOC → 1838，**接 2000 hard cap 緊**。當前 < hard cap **不阻 merge**，但建議 P2 follow-up：W-AUDIT-9 T6 land 後規劃拆 governance_core.rs（lease facade / acquisition path / canary stage path / SM transition 邏輯分檔）。

不阻 first-pass review。

### 3.8 §九 + 跨平台

✓ §九 8 條 checklist 全 PASS
✓ 跨平台 grep 0 hit
✓ Migration guard 對 V080（E1-A 範圍）已驗
✓ Bybit API 改動 N/A（本 wave 不動 Bybit）

---

## §4 Wave 4 — W-AUDIT-4b-M1 (E1-E `4a90966a`) APPROVE

### 4.1 V082 schema 嚴謹 PASS

✓ V082 編號與 V080（E1-A）不衝突 ✓
✓ Guard A（learning schema 必存）+ A2（V017 decision_features 必要欄位俱在）+ A3（新表 schema drift 檢查）三層
✓ Guard C 對 outcome / tier 索引欄位驗證
✓ idempotency Linux PG dry-run x2 PASS（E1-E 自報；E2 verify mock pytest 13/13 PASS）
✓ 7-value evaluation_outcome enum 完整對齊 PredictorAction/PredictorGateOutcome：
  - accept / reject / reject_add / shadow_fill / fallback_use_legacy / fallback_fail_closed / use_legacy_no_predictor
✓ 2-value evidence_source_tier enum：evaluation_log / shadow_synthetic（**故意不重疊 V050 replay tier** 防 ML pool 污染）
✓ entry_context_id NULL（M2 trigger 鋪路）

### 4.2 Producer 改造 intent-only emit PASS

✓ `evaluate_predictor_gate` 不再頂端 emit production decision_feature
✓ `step_4_5_dispatch` 兩 success path 加 emit：
  - exchange path (line 511 persist_intent → line 532 emit) ✓
  - paper path (line 729 persist_intent → line 750 emit) ✓
✓ `try_emit_evaluation_log` 寫 V082 evaluation 表（每次評估都寫，無論 outcome）
✓ legacy `emit_decision_feature_snapshot` 完全清理（grep 0 hit）✓
✓ predictor_router tests 24/24 PASS（4 既有重命名 + 5 新 evaluation 通道驗）
✓ decision_feature_evaluation_writer 9/9 PASS

### 4.3 mlde_edge_training_rows view 不破 PASS

✓ View 從 `learning.decision_features`（intent-only 後 ~263/24h）讀，**不從** decision_features_evaluations 讀
✓ V082 拆表後 view schema 0 改變
✓ E1-E 自報 24h 22,405 rows query PASS（V082 apply 前 baseline；M1 land 後預期降至 ~263/24h * 30d = ~7900/30d 仍夠 LightGBM 訓練）
✓ PA spec line 540-541 明確接受 attribution_chain_ok 0.5% → 25-40% 路徑（denominator 縮 99%）

### 4.4 對抗反問 — shadow_mode=true 場景 outcome 字串

E1-E report §6 #2 自報：`cfg.shadow_mode=true` 時 PredictorAction=UseLegacyGate 但 evaluation_outcome 仍 = "accept"，對齊 PA spec 「shadow_mode 觀測」是否語意一致。

**E2 verdict**：**ACCEPT**。`evaluation_outcome` 是「predictor gate 評估的結果」（不是 PredictorAction），所以 `cfg.shadow_mode=true` 場景 predictor 算出 accept 但因 shadow_mode 不採用是合理的；下游 SELECT 必加 `evidence_source_tier IN ('evaluation_log','shadow_synthetic')` 區分。

### 4.5 §九 + 跨平台 + 文件大小

✓ §九 8 條 checklist 全 PASS
✓ 跨平台 grep 0 hit
✓ V082 Guard A/B/C 完整
✓ `decision_feature_evaluation_writer.rs` 287 LOC < 800 警告線
✓ `intent_processor/mod.rs` 1363 LOC（pre-existing baseline >800；W-AUDIT-4b-M1 +144 / -27 在 baseline 內）
✓ Bybit API N/A

---

## §5 Cross-Wave IPC Test Fail — RETURN-TO-E1-A

### 5.1 失敗 test 列表

```
ipc_server::tests::config::test_g3_02_a2_patch_executor_shadow_mode_via_patch_risk_config
ipc_server::tests::config::test_g3_02_a2_patch_executor_routes_to_demo_engine
```

### 5.2 Root cause 確認

E1-A T1 invariant `shadow_mode != canary_stage.as_shadow_mode() = reject` 直接破 既有 IPC binary patch test。test patch JSON 只翻 `shadow_mode=false` 但未同時 set `canary_stage>=1` 等 4 atomic fields → patch 後狀態 `(shadow_mode=false, canary_stage=Stage0)` → invariant reject。

### 5.3 屬誰 + Fix scope

**Owner**：**E1-A `094f9914`**（不是 E1-D，雖然 E1-D 整體 cargo test 才暴露）。

**Fix scope**（推薦 (a)）：

```rust
// (1) 重命名既有 binary patch test 為 invariant 主動拒驗證
#[tokio::test]
async fn test_g3_02_a2_patch_executor_binary_shadow_only_rejected_invariant_drift() {
    // W-AUDIT-9 T1 invariant：legacy `shadow_mode` 必與 `canary_stage` projection 一致；
    // patch 只翻 shadow_mode=false 不帶 canary_stage>=1 = config drift → validation reject。
    // ... 期望 resp.error.is_some() ...
}

// (2) 新增 stage promotion atomic patch test
#[tokio::test]
async fn test_g3_02_a2_patch_executor_stage_promotion_via_patch_risk_config() {
    // ... patch 5-field atomic: shadow_mode=false + canary_stage=1 + canary_cohort + stage_entered_at_ms + observation_period_ms ...
    // ... 期望 resp.error.is_none() + paper.executor.canary_stage == Stage1 ...
}

// (3) test_g3_02_a2_patch_executor_routes_to_demo_engine 同改 5-field atomic
//     environment="demo" + canary_stage=2
```

### 5.4 嚴重度：HIGH

**理由**：
- 不破 production behavior（4 TOML 預設 Stage 0）
- 但 cargo test --release 整體 fail = E2/E4 不能放行
- E1-A 補 IPC test fix → E2 second-pass → E4 regression 才能繼續

**E1-A report §5.4 自報問題**：「First run（在 sibling B-M1 commit 之前）：cargo build --release 通過」+「後 sibling 200188ad commit：cargo build E0063 break」。但 E2 實測 E1-A `094f9914` 自身 `cargo test --lib --release` 已 fail 2 IPC test —— **E1-A 漏跑 ipc_server::tests::config scope**（只跑 `config::risk_config` 139 PASS）。建議 E1-A 之後加 `cargo test --lib --release` 全套到 acceptance。

---

## §6 22 Invariant 對應驗證

| # | Invariant | 評估 |
|---|---|---|
| 1 | W-AUDIT-9 7 sub-task 全 land + `[58]` PASS + canary_stage_log active | ⚠️ partial（T1+T2+T3+T6 land；T4 healthcheck `[58]` / T5 GUI / T7 E4 regression 待）— Sprint N+0 W2 結束才驗 |
| 2 | W-AUDIT-8a Phase A | N/A（不在本批） |
| 3 | W-AUDIT-6d 保 6 + 砍 6 grep blacklist 0 命中 | ✓ E2 獨立 verify 0 LOC delta on ma_crossover/grid_trading/bb_breakout/funding_arb |
| 5 | W-AUDIT-4b 6 表 INSERT path 串行 | ⚠️ M1 land；M2/M3 後續 sprint；entry_context_id NULL 鋪路 ✓ |
| 9 | shadow_mode_provider exception → Stage 0 | ✓ E1-C 3 path 全 fail-closed Stage 0；唯一例外 = legacy False → Stage 1 投影是 documented backward-compat trade-off |
| 10 | Stage 0 binary fail-closed 不變式保留 4 範圍（DOC-08 §12 / SM-04 / Live 5-gate / §二 16） | ✓ T1 schema 升級不動 4 範圍；4 TOML Stage 0 default 保 binary fail-closed |
| 11 | canary_stage_log.decision_lease_id PG NOT NULL for manual_promote | ✓ V080 line 245-249 CHECK + Linux PG empirical reject test PASS |
| 13 | 3 新策略 declared_alpha_sources | N/A（不在本批） |
| 14 | Stage 2 abort gate | N/A（後續 sprint） |
| 16 | DSR K -12 mu_0 量化記入 sign-off | ✓ E1-D dsr_penalty_quantification.md 完整量化 + 公式正確 (ln 不是 log₁₀) + sensitivity K=20/25/30 |

---

## §7 §九 8 條 + OpenClaw 9 條 Combined Checklist

### §九 8 條（PASS All Waves）

| Item | 狀態 |
|---|---|
| 改動範圍與 PA 方案一致 | ✓ 4 wave 對齊 spec |
| 沒有 except:pass / 靜默吞 | ✓ grep 0 hit |
| 日誌 %s 格式 | ✓ logger.warning 用 %s |
| 新 API 端點有 _require_operator_role | N/A 0 新 HTTP API endpoint |
| except HTTPException raise 在 except Exception 之前 | N/A |
| detail=str(e) 已改為 "Internal server error" | ✓ grep 0 hit |
| asyncio 路由中無 blocking threading.Lock | ✓ 本批未新增 lock |
| 沒有私有屬性穿透 ._xxx | ✓ |

### OpenClaw 9 條（除 IPC test fail 外 All PASS）

| Item | 狀態 |
|---|---|
| 跨平台 grep（/home/ncyu / /Users/[^/]+） | ✓ 0 hit |
| 雙語注釋（默認中文）| ✓ 新代碼中文為主，原有英文未動 |
| Rust unsafe 零容忍 | ✓ 0 unsafe block |
| 跨語言 IPC schema | ✓ Rust CanaryStage int 0..=4 對齊 Python IntEnum 0..=4；CanaryCohort 三欄位 strategy/symbol/environment 字串對齊 |
| Migration Guard A/B/C | ✓ V080 Guard A×2 + Guard C×1；V082 Guard A/A2/A3 |
| healthcheck 配對 | T4 `[58]` 待 Sprint N+0 W2 IMPL（不阻 first-pass）|
| Singleton 登記 §九 表 | ✓ 本批 0 新 singleton；既有 _CACHE_INSTANCE 已登記 |
| 文件大小 800/2000 | ✓ 全 < 2000 hard cap；有 5 檔 > 800 警告（pre-existing 4 + new 1：test_executor_agent_unit.py 809） |
| Bybit API 改動先查字典手冊 | N/A 本批不動 Bybit |

---

## §8 對抗反問 5 條

### Q1：「E1-A 說 cargo test 139 PASS — 全範圍跑了沒？」

A：跑 `config::risk_config` 139 PASS 是 schema scope；**沒跑** ipc_server::tests::config（既有 G3-02 Phase A2 IPC test）。E2 實測 `cargo test --lib -p openclaw_engine --release` 暴露 2 IPC fail。**評估**：E1-A acceptance 漏層。

### Q2：「E1-D 說 stash 後 baseline 仍 fail — 真不是自己引入？」

A：✓ verified。stash E1-D 改動後跑 baseline = 相同 2 IPC fail（E2 獨立確認 fail message 含 "shadow_mode=false inconsistent with canary_stage=0"，這 message 字串 100% 來自 E1-A risk_config_advanced.rs validate() 新 invariant）。**評估**：E1-D 報告誠實，責任歸 E1-A。

### Q3：「invariant 9 fail-closed Stage 0 — 真是 Stage 0 不是 Stage 1？」

A：3 critical paths 全 Stage 0：(1c) canary_stage_provider exception → SHADOW (line 810)；(2c) shadow_mode_provider exception → SHADOW (line 833)；(3) 雙 None → SHADOW (line 843)。但 path 2b（legacy False success path）→ PAPER_SINGLE_COHORT，這是 backward-compat 投影不是 fail —— 這 trade-off E1-C report §6 #1 已 documented，待 W-AUDIT-3b runtime smoke land 後 PA 補 production wiring 接 canary_stage_provider 解。**評估**：Stage 0 fail-closed 嚴格保留。

### Q4：「砍 6 grep blacklist 0 命中 — E2 真獨立 grep 了？」

A：✓ `git diff bcf4f11a..HEAD -- 'rust/openclaw_engine/src/strategies/'` 只有 bb_reversion 動（保 6 #6），ma_crossover / grid_trading / bb_breakout / funding_arb.rs / grid_helpers.rs 全 0 LOC delta。**評估**：invariant 3 PA-3 verified PASS。

### Q5：「DSR K -12 mu_0 公式真用 ln？TODO §7 用 log₁₀？」

A：✓ E1-D 自我糾正 TODO §7 引用 mu_0=2.83/2.27（log₁₀ 假設）→ 採 ln 為唯一權威：K=25 mu_0=2.5374 / K=13 mu_0=2.2649 / Δ -0.2723。E2 Python 實測復算數值一致。**評估**：DSR 公式正確（Bailey-Lopez de Prado 2014/2020 standard），**TODO §7 mu_0=2.83/2.27 是 documentation 錯誤**，建議 PM merge 後同步更新 TODO §7 的 mu_0 文字（baseline ~2.54 / mid-G ~2.27）。

---

## §9 Findings 總表

| 嚴重度 | 位置 | 描述 | 建議修法 | Owner |
|---|---|---|---|---|
| HIGH-1 | `rust/openclaw_engine/src/ipc_server/tests/config.rs:426 + 549` | E1-A T1 invariant 直接破 既有 G3-02 binary patch IPC test 2 個 | 重命名既有 test 為 invariant drift 拒驗證 + 新增 stage_promotion atomic 5-field patch test（§5.3 fix scope (a)） | **E1-A** |
| MED-1 | `executor_agent.py:826` | legacy `shadow_mode_provider` 回 False → Stage 1 投影邊界（IPC patch atomic + production wiring 不接 canary_stage_provider 才暴露）| **ACCEPT trade-off**；W-AUDIT-3b runtime smoke land 後 PA follow-up：`strategy_wiring.py:549` ExecutorAgent ctor 必同時注入 `canary_stage_provider=cache.canary_stage_provider()` | E1-C / PA |
| MED-2 | `governance_core.rs` 1838 LOC | 接 2000 hard cap 緊（E1-D 加 +329 → 1838）| 不阻 first-pass；建議 W-AUDIT-9 T6 land 後 P2 follow-up：拆分為 lease facade / acquisition / canary stage / SM transition 4 檔 | E1-D + PA |
| MED-3 | TODO.md v19 §7 | DSR mu_0 引用 2.83/2.27 用 log₁₀ 假設 → 應改 ln | PM merge 後同步更新 TODO §7：baseline mu_0 ~2.54 / mid-G ~2.27 / Δ -0.27 | PM |
| LOW-1 | `V080.sql` table COMMENT | 含舊 binary 路徑 reference + W-AUDIT-9 T3/T5/T6 owner cross-link 文字密度高 | 不阻 merge | E1-A（可 P3 順手）|

---

## §10 Findings Severity 分級 + 建議

### CRITICAL：0
無硬邊界繞過 / SQL injection / panic 在交易路徑等 critical issue。

### HIGH：1
- IPC test fail（cross-wave，E1-A 補 fix）

### MEDIUM：3
- legacy False → Stage 1 邊界（accept trade-off，W-AUDIT-3b follow-up）
- governance_core.rs 1838 接 cap（P2 follow-up）
- TODO §7 DSR mu_0 文字錯誤（PM 順手修）

### LOW：1
- V080 COMMENT 文字密度（P3 可選）

---

## §11 PASS rate

- **E1-A T1+T2**：10 PASS items + 1 HIGH fail = RETURN-TO-E1-A
- **E1-C T3**：8 PASS items + 1 MED accept = APPROVE
- **E1-D T6 + 6d-4/5/6**：12 PASS items + 1 MED advisory = APPROVE
- **E1-E B-M1**：10 PASS items + 0 fail = APPROVE
- **Cross-wave**：1 BLOCKER（IPC test fail，屬 E1-A）

整體：3 wave APPROVE / 1 wave RETURN-TO-E1-A（cross-wave fix）/ 22 invariant 適用範圍內 0 FAIL。

---

## §12 結論

**RETURN-TO-E1-A** for cross-wave IPC test fix。其餘 3 wave (E1-C / E1-D / E1-E) 待 E1-A fix land + E2 second-pass 通過後一併放行 E4 regression。

### E1-A 修復清單

1. `rust/openclaw_engine/src/ipc_server/tests/config.rs:426` — 重命名 `test_g3_02_a2_patch_executor_shadow_mode_via_patch_risk_config` 為 `test_g3_02_a2_patch_executor_binary_shadow_only_rejected_invariant_drift`，斷言 patch error
2. `rust/openclaw_engine/src/ipc_server/tests/config.rs:549` — `test_g3_02_a2_patch_executor_routes_to_demo_engine` 改 5-field atomic patch + environment="demo" + canary_stage=2
3. **新增** `test_g3_02_a2_patch_executor_stage_promotion_via_patch_risk_config`：patch 5-field atomic（shadow_mode=false + canary_stage=1 + canary_cohort + stage_entered_at_ms + observation_period_ms）→ 期望 success + paper.executor.canary_stage == Stage1
4. E1-A acceptance 加 `cargo test --lib -p openclaw_engine --release` 全套（不只 `config::risk_config` scope）

### Follow-ups（不阻本 review）

1. W-AUDIT-3b runtime smoke land 後 PA：`strategy_wiring.py:549` ExecutorAgent ctor 加 `canary_stage_provider=cache.canary_stage_provider()` 補 invariant 9 production wiring
2. PM merge 後同步：TODO.md v19 §7 DSR mu_0 文字（log₁₀ → ln，2.83→2.54 / 2.27 不變 / Δ -0.27）
3. P2 follow-up：governance_core.rs 拆分（W-AUDIT-9 T6 land 後）
4. P3 follow-up：test_executor_agent_unit.py 拆 fixtures（809 LOC 跨 800 警告）

---

## §13 三端 git sync

```
Mac local HEAD:    f5574c5a (sub-agent 5 commit 全 push origin)
GitHub origin/main: f5574c5a
Linux trade-core:   f5574c5a (per task brief）
```

3 端同 `f5574c5a` ✓。

---

E2 REVIEW DONE: **RETURN-TO-E1-A** (1 HIGH cross-wave + 3 MED + 1 LOW；3 wave APPROVE pending E1-A IPC fix) · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-09--sprint_n0_first_pass_review.md`
