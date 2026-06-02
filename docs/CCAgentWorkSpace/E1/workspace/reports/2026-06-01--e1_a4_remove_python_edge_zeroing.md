# E1 IMPL — A-4 (B2)：移除 Python edge 歸零，靠 Rust demo/live 雙路徑接管 · 2026-06-01

Role: E1。Scope: 僅 `program_code/ml_training/james_stein_estimator.py`（移除歸零）+
`rust/openclaw_engine/src/intent_processor/tests.rs`（加 A-4 鎖死測試），2 檔。
與前面 E1 in-flight 改動（bb_breakout/bb_reversion/strategies-mod/tick_pipeline/ipc/dual_rail）disjoint。
未 commit（強制鏈 E1→E2→E4→QA→PM）。main HEAD `2e809b96` 未動。

## 1. 任務摘要

預防性、當前零傷害修。移除 `james_stein_estimator.py:319-321` 對「未過驗證的正 edge」的歸零
（`runtime_bps = 0.0`），讓 Rust 既有的 demo/live 非對稱 cost_gate 接管。當前零傷害因被歸零的
2 cell n=5 < min_n(30)，本就走低樣本探索臂（未成熟）；此修防 cell 成熟（n≥30）後正 edge 被
Python 歸零毒害，避免架空 Rust 本就正確的 demo-loose 探索設計。**B2 只移除 Python 歸零；
Rust gates.rs 邏輯一個 byte 不動，僅加測試鎖死。**

## 2. 根因鏈（親驗）

```
james_stein:319-321  runtime_bps=0.0（正 edge 未驗證 → 歸零）
        │ 寫進 edge_estimates.json runtime_bps
        ▼
edge_estimates.rs:149-152  runtime_field = val.get("runtime_bps")...    ← 優先讀 runtime_bps
        runtime_field.or_else(|| shrunk_bps)  →  CellEstimate.shrunk_bps = 0.0
        │（Rust 的 shrunk_bps 欄位實際裝 JSON 的 runtime_bps）
        ▼
demo gates.rs:177  Some(cell) if cell.shrunk_bps > 0.0   →  0.0 > 0.0 = FALSE
        │ 跳過「demo 放行未驗證正 edge 探索臂」(:177-194)
        ▼
gates.rs:216  Some(cell) =>  rejected(CostGateJsDemoNegative)   ← 正 edge 被當負阻擋（bug）
```

移除歸零後：runtime_bps 保留真實正值（如 +5bps）→ `cell.shrunk_bps = 5.0 > 0.0 = true`：
- **demo**：進 :177 → `validation_passed=false` → `:184 if !validation_passed` → `:194 return None`（探索放行，符合 demo-loose）。
- **live**：進 :268 → `validation_passed=false` → `:275 if !validation_passed` → `:280 return Some(rejected(CostGateJsLiveStaleOrUnvalidated))`（fail-closed reject）。

## 3. 修改清單

| 檔 | 改動 |
|---|---|
| `james_stein_estimator.py` :319-321 | **移除** `if not validation.validation_passed and runtime_bps > 0.0: runtime_bps = 0.0`（2 行刪除）+ 中文 rationale 註釋（為什麼移除 + Rust 雙路徑接管說明）|
| `james_stein_estimator.py` :545-546 | 同步更新過期 bilingual 註釋（原「未通過驗證的正 edge 會被歸零」與移除後行為矛盾 → 移英留中，依 chinese-only-comments skill）|
| `tests.rs` :+52 | A-4 module + 2 測試：`test_a4_live_unvalidated_positive_runtime_still_rejects` / `test_a4_demo_mature_unvalidated_positive_runtime_enters_exploration`（復用既有 `p1_09_estimates` fixture）|

## 4. CC #4-P0 guard — 全守

### Guard 1：call-path grep proof（live fail-closed 不靠歸零，無第二條繞過）

- **唯一非-test live caller**：`router.rs:1051` `GovernanceProfile::Production => cost_gate_live_with_slippage(...)`。
  grep `cost_gate_live` 其餘命中全是 `tests.rs` / `tests_predictor_router.rs` / 註釋 / config doc。
- **三 profile 各管各 gate**：Validation(Demo)→`cost_gate_moderate_with_slippage`(:1044) /
  Production(Live)→`cost_gate_live_with_slippage`(:1051) / Exploration→`None`(:1058)。
- **所有 `.shrunk_bps` 讀取站點無一在 live 決策路徑繞過 :275**：
  - `gates.rs:36/46/49/61/78` → `cost_gate_paper`（**paper-only**，讀獨立 `edge_estimates_paper.json`）
  - `gates.rs:144-221` → `cost_gate_moderate`（**demo-only**）
  - `gates.rs:268/297/300/312` → `cost_gate_live_with_slippage`（**唯一 live**，:275 fail-closed 守此）
  - `scanner/*` `tick_pipeline/*` `exit_features/*` → 全是 scoring / feature / opportunity ranking，
    不發 reject/approve 授權決策，不會繞過 :275 授權 live 開倉。
- **結論**：live 對「未驗證正 edge」的 fail-closed **純靠 `cost_gate_live_with_slippage:275` 的
  `!cell.validation_passed`**，不依賴 Python 歸零，且無第二條 live 路徑讀 shrunk_bps 繞過。B2 成立。

### Guard 2：Rust 測試鎖死（tests.rs，非 gates.rs）

- `test_a4_live_unvalidated_positive_runtime_still_rejects`：cell `has_runtime=true + validated=false`
  （即移除歸零後 live 仍遇到的形態）→ `cost_gate_live` 回 **rejected**，reason 含 `validated=false`
  （鎖 live fail-closed 不被連帶鬆動）。
- `test_a4_demo_mature_unvalidated_positive_runtime_enters_exploration`：**同一 cell**（mature n=100 ≥
  min_n(30) + 正 + 未驗證）→ `cost_gate_moderate` 回 **None（探索放行）**（證明移除歸零後 demo-loose
  探索臂 :184 正確觸發、不再誤落 :216 負阻擋）。

### Guard 3：只改 Python，不改 Rust gates.rs 邏輯

`git diff -- rust/openclaw_engine/src/intent_processor/gates.rs` = **0 行**。`cost_gate_live_with_slippage`
函數體一個 byte 未動（含對抗注入全還原後復查）。

### Guard 4：不放鬆 cost_gate

demo 探索臂門檻 :203（`shrunk_bps < threshold_bps` reject）保留；live :297 門檻保留；live :275
未驗證 reject 保留。無任何門檻放鬆。

## 5. 第二處歸零排查（load-bearing，確認 B2 不被架空）

grep `runtime_bps.*0\.0` 全檔：
- **`:545-547`** = 只是序列化已在 :319-327 算好的 `r["runtime_bps"]`（`round(r.get("runtime_bps", shrunk_bps), 4)`），
  **非第二處歸零**。歸零唯一執行點就是我移除的 :319-321。此處註釋過期已同步更新。
- **`:115`** = `_inject_sync_label_proxy_cells` 的 `min(grand_mean_bps, 0.0)`（sync-label 策略無直接觀測時
  注入負向保守先驗的合成格子），**獨立機制，與 A-4 正交，不動**（A-4 針對真實訓練格子的正 edge；
  proxy 是無觀測合成格子的保守先驗）。

## 6. 治理對照

- **live fail-closed（根原則 #5 生存 > 利潤）**：移除歸零後 live 對未驗證正 edge 仍 reject
  （`CostGateJsLiveStaleOrUnvalidated`），靠 :275 `!validation_passed`，Guard 2 live 測試 + 對抗驗證鎖死。
- **demo-loose（feedback_demo_loose_live_strict_policy / CLAUDE §四）**：demo 對未驗證正 edge 探索放行
  （學習資料源），Guard 2 demo 測試鎖死。LiveDemo 不降級（live 路徑嚴格不變）。
- **hard boundary**：max_retries / live_execution_allowed / execution_authority / system_mode / mainnet
  全未碰（僅改 ml_training 估計 + Rust 測試）。
- **無假功能**：runtime_bps 真實寫出，validation_passed 旗標隨 results[k] 一併序列化，Rust 雙路徑各自據此判斷。
- **註釋（chinese-only-comments skill）**：新註釋中文；觸及 :545-546 舊 bilingual block → 移英留中。

## 7. 驗證（誠實）

| 套件 | 結果 |
|---|---|
| `cargo test test_a4_` | **2 passed / 0 failed**（compile 14.24s，0 error）|
| `cargo test test_p1_09` | **8 passed / 0 failed**（既有 demo/live 非對稱回歸）|
| `cargo test test_cost_gate` | **17 passed / 0 failed** |
| Python `pytest test_james_stein_proxy_cells + test_edge_estimate_validation` | **11 passed** |
| Python 全 `ml_training/tests/` | **433 passed / 2 failed(pre-existing) / 31 skipped** |

- **對抗驗證（測試有 bite）**：
  - 注入 bug1（live :275 移除 `!validation_passed`）→ `test_a4_live` FAIL ✓
  - 注入 bug2（demo :177 `> 0.0` 改 `> 100.0`，等價「歸零落負阻擋」）→ `test_a4_demo` FAIL ✓
  - 均已還原，最終 gates.rs diff = 0 行。
- **2 個 pre-existing FAIL 與我無關**：`test_evidence_filter_capability`（`EVIDENCE_SOURCE_TIER_ALLOWLIST`
  缺 `synthetic_replay`）。我的改動未觸及 evidence filter；失敗測試 import 的是
  `mlde_demo_applier_evidence_filter` 非 james_stein；**stash 掉我的 james_stein 改動後該 2 測試仍 FAIL**
  （已實證 baseline 即 fail），不在我範圍。
- Mac advisory；E4 Linux regression authoritative。

## 8. 不確定之處 / 風險

1. **proxy cell (:115) 未動**：sync-label 無觀測格子仍灌 `min(grand_mean, 0.0)` 負先驗。這是設計上的
   保守 cold-start，與 A-4「真實格子正 edge 歸零」不同問題。若 PA 認為 proxy 負先驗也該重評 → follow-up
   （非本任務）。
2. **runtime 影響 deploy-gated**：james_stein 是 cron（每 3h），改後下輪快照 runtime_bps 不再歸零。
   實際 runtime 行為（成熟 cell 成正後 demo 放行 / live reject）需 E4 replay + runtime 驗（CLAUDE §六，
   out of scope）。
3. **2 cell 當前 n=5 未成熟**：本修零傷害，價值在 cell 成熟後不被毒；E4/QC 後續觀察 cell 跨 min_n 後行為。

## 9. Handoff to E2

Review 重點：(1) Python 歸零移除正確（:319-321 刪 2 行，runtime_bps 保留真實值）；(2) **第二處歸零排查
（:545 非歸零僅序列化 / :115 proxy 正交不動）** 確認 B2 不被架空；(3) Guard 1 grep proof（live :275 唯一
fail-closed，無繞過）；(4) Guard 2/3（測試在 tests.rs，gates.rs diff=0）；(5) 對抗驗證 bite。
然後 E4 Linux regression（authoritative）+ QA 驗 cron 下輪快照行為 + accumulate 語義。

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-06-01--e1_a4_remove_python_edge_zeroing.md）
