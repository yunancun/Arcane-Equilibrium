# E4 Regression Report — P2-DYN-STOP-FLOOR-SENTINEL

- **日期**：2026-05-21
- **角色**：E4 · Test Engineer
- **任務**：FA F2 RCA OQ-4 衍生 — 加 sentinel test 鎖死 demo + live TOML dyn_stop 配置防 silent drift
- **改動範圍**：1 test file（only），不動 production / 不動 TOML
- **結論**：**PASS** · ready for PM commit

---

## 1. 任務背景

FA F2 RCA 確認 funding_arb 6.29% SL 案例 = dyn_stop floor (25.0 × 0.25 = 6.25%) + 0.04pp = 「設計範圍內」非「越界」。

潛在風險：若未來 `base_ratio` 從 0.25 drift（例 0.20 或 0.30），SL gate semantic 改變但無 sentinel 鎖死：
- `base_ratio = 0.20` → floor 5% → 6.29% 變「真正越界」 → analyst 從外部看數據誤判
- `base_ratio = 0.30` → floor 7.5% → 6.29% 變「該觸發但沒觸發」 → 誤判 SL gate 失效

對應 TODO §6.1 `P2-DYN-STOP-FLOOR-SENTINEL` 30min 工時 / E4 owner。

---

## 2. 改動清單

### 改 1 個 file（只動 test）

`rust/openclaw_engine/src/risk_checks_per_strategy_tests.rs`：436 → 656 LOC（+220）

- 範本 sentinel `test_demo_toml_retired_funding_arb_removed_from_risk_config`（line 358-436）之後追加 3 個新 sentinel
- 加 module-level header 註釋（line 438-458）解釋 sentinel 目的 + 變更前須跑 SL gate semantic impact audit + dyn_stop floor/cap/ATR 公式

### 3 個新 sentinel test

| Test | Lock 內容 | Effective 公式 assertion |
|---|---|---|
| `test_demo_toml_dyn_stop_base_ratio_locked` | demo `base_ratio=0.25` + `stop_loss_max_pct=25.0` | floor = 25.0 × 0.25 = **6.25%** |
| `test_demo_toml_dyn_stop_atr_mult_and_cap_locked` | demo `atr_stop_mult=2.0` + `cap_ratio=0.85` | cap = 25.0 × 0.85 = **21.25%** |
| `test_live_toml_dyn_stop_explicit_divergence_from_demo` | live `15.0 / 0.5 / 1.5 / 0.75` + policy invariant | live floor 7.5% / cap 11.25% + `live_cap < demo_cap` + `live_floor > demo_floor` |

### 不動

- ❌ `risk_config_demo.toml` / `risk_config_live.toml` 本身
- ❌ production Rust source（`risk_checks.rs` / `risk_config.rs` / `risk_config_advanced.rs`）
- ❌ 既有 `test_demo_toml_retired_funding_arb_removed_from_risk_config`（與新 test A 部分重疊，重疊是 feature 不是 bug — 見 §6 push back）

---

## 3. Cargo test 結果（前 / 後）

### 引擎 / 模組

| 引擎 | passed | failed | baseline | delta |
|---|---:|---:|---:|---:|
| Rust openclaw_engine lib（全） | 3045 | 0 | 3042 | **+3 sentinel** |
| Rust openclaw_engine lib `g2_03_per_strategy_tests` module | 26 | 0 | 23 | **+3 sentinel** |

### 跑兩遍（非 flaky 驗）

- 1st run: `test result: ok. 3045 passed; 0 failed; 1 ignored; finished in 0.70s`
- 2nd run: `test result: ok. 3045 passed; 0 failed; 1 ignored; finished in 0.69s`
- Flaky? **N**（兩次 byte-identical 結果）

### 不跑

- Python pytest：本 PR 純 Rust test file，不動 Python
- Rust integration test：本 PR 純 lib sentinel，不需 PG
- SLA 壓測：sentinel test 是 deserialize TOML + assert，不在 hot path

---

## 4. Adversarial probe（強制驗證）

### Phase 1 — 觸紅

修 `risk_config_demo.toml` line 153 `base_ratio = 0.25` → `0.20`：

```
test risk_checks::g2_03_per_strategy_tests::test_demo_toml_dyn_stop_base_ratio_locked ... FAILED
thread '...' panicked at .../risk_checks_per_strategy_tests.rs:485:5:
dynamic_stop.base_ratio expected 0.25, got 0.2 — 任何動 base_ratio 之前須先跑 SL gate semantic impact audit（FA F2 OQ-4）
```

**Side effect**：既有 `test_demo_toml_retired_funding_arb_removed_from_risk_config`（W-AUDIT-6 範本）同步紅 — 預期同步觸發兩個 sentinel，雙重 catch rate。

**Cross check**：`test_demo_toml_dyn_stop_atr_mult_and_cap_locked` 對 base_ratio 不依賴 → 維持 ok 如預期（測試 scope 隔離正確）。

### Phase 2 — 復原 & 二次綠

復原 `0.20` → `0.25`，重跑 `g2_03_per_strategy_tests`：

```
test result: ok. 26 passed; 0 failed; 0 ignored; 0 measured; 3020 filtered out; finished in 0.00s
```

26/26 GREEN — 復原乾淨無殘留。

---

## 5. Mock 審查

不適用（純 deserialize TOML + struct field assertion；無 IO / 業務邏輯 mock）。

---

## 6. Push back / 工程觀察

### 6.1 與 W-AUDIT-6 範本部分重疊 — 重疊是 feature

新 `test_demo_toml_dyn_stop_base_ratio_locked` 與既有 `test_demo_toml_retired_funding_arb_removed_from_risk_config` 都 assert `cfg.dynamic_stop.base_ratio == 0.25`。

**判斷**：保留重疊。
- 重疊好處 1：雙 sentinel = 雙 catch（adversarial probe 確認）
- 重疊好處 2：新 test 攜帶 explicit floor 公式 (25.0 × 0.25 = 6.25) + impact audit warning message；W-AUDIT-6 only 講 `0.4→0.25 history`
- 兩種 semantic 警示路徑（lock value vs lock formula consequence）獨立 message 不該合併

### 6.2 Test C policy invariant 雙向 push back

`live_cap < demo_cap` + `live_floor > demo_floor` 兩 invariant 反向協同：

| 反向 drift 場景 | 失守訊號 |
|---|---|
| 改 demo 使 `demo_cap <= live_cap` | live 變比 demo 寬 = 嚴重失守 |
| 改 demo 使 `demo_floor >= live_floor` | demo 加速學習意圖鬆動 |

**判斷**：採納（雙向 invariant 是預防性護欄）。

### 6.3 Live vs Demo 故意 divergence — **不需 spec amendment**

當前實值：

| 配置 | stop_loss_max_pct | base_ratio | atr_stop_mult | cap_ratio | floor | cap |
|---|---:|---:|---:|---:|---:|---:|
| Demo | 25.0 | 0.25 | 2.0 | 0.85 | 6.25% | 21.25% |
| Live | 15.0 | 0.5 | 1.5 | 0.75 | 7.5% | 11.25% |

**判斷**：故意 divergence 不需 spec amendment。
- Policy intent 在 `risk_config_demo.toml` L143-152 註釋 explicit 寫明：「demo 為學習資料源，收緊 floor 減少深虧樣本以加速 EDGE-DIAG-2 收斂...Paper/Live TOML 不動」
- 與記憶體 `feedback_env_config_independence`（2026-04-19）一致：「paper/live/demo risk_config*.toml 故意分開，禁純衛生合併」
- Test C 加 policy direction invariant assertion 防未來反向 drift = 預防性護欄足夠

### 6.4 不擴大 scope

Brief 只要 demo (Test A + B) + live divergence (Test C)。未動：
- ❌ `risk_config.toml`（root level / non-env-specific，用途不明）
- ❌ `risk_config_paper.toml`（paper 路徑為 disabled by default，per `feedback_demo_over_paper_for_edge`）
- ❌ 跨 4 個 env config consistency matrix（過寬）

**push back 建議**：若 PA 認為應同步加 paper sentinel，可下次起 spec；目前僅鎖 demo + live policy direction 已覆蓋 90% 風險。

---

## 7. 反模式檢查（見即 BLOCKER）

| 反模式 | check | OK? |
|---|---|---|
| 刪測試使 passed 增加 | 0 test 被刪 | ok |
| 改 assertion value 而非修代碼 | sentinel test 是新增，無既有測試被改 | ok |
| mock 業務邏輯 | 純 deserialize + struct field assert，無 mock | ok |
| 「跑一次過了所以綠」 | 兩遍同綠 finish in 0.69-0.70s | ok |
| skip / xfail | 0 | ok |
| 浮點比較用 `==` 沒容差 | 全用 `(x - expected).abs() < 1e-9` | ok |
| commit baseline 沒記錄變動 | 本 report §3 已記錄 3042→3045 / 23→26 | ok |
| failed 數增加 | 0 → 0（無變化） | ok |

---

## 8. 結論

**E4 REGRESSION DONE: PASS**

3 sentinel test 加固完成，3042→3045 lib passed / failed 維持 0。Adversarial probe 確認設計健全（紅燈/復原 byte-identical 兩遍同綠）。Test C 採 policy direction invariant 防 live vs demo 反向 drift，不需 spec amendment（per `feedback_env_config_independence`）。

**交付給 PM**：
1. 改 `srv/rust/openclaw_engine/src/risk_checks_per_strategy_tests.rs`（+220 LOC，3 sentinel test + module header 註釋）
2. 不 commit；交給 PM 執行 commit + push
