# E2 Review — P1-PORTFOLIO-RESTING-EXPOSURE-1 supplement

**Date**：2026-05-16
**Agent**：E2
**Scope**：Wave 2 Round 2 補測 (`test_resting_entry_qty_correlated_pair_blocks_oversize`, +82 LOC)
**Target commit**：`ad5e609e`（已 committed，非 working tree）
**Baseline commit**：`9980448a`（task 已 sign-off 進 main）

---

## §1 Race protocol 5 條 check

| # | check | 結果 |
|---|---|---|
| 1 | sibling 並行驗 | PASS — `git status` 列 14 dirty file（pending_sweep / commands / maker_rejection / grid_trading/* / event_consumer / database/* / passive_wait_healthcheck/*），**0 重疊** `intent_processor/`。 |
| 2 | dirty file overlap check | PASS — `intent_processor/tests.rs` 已 commit 進 `ad5e609e`，不在 dirty list；sibling Phase 1b 全在 tick_pipeline / event_consumer / strategies / database。 |
| 3 | commit message ID 對齊 | PASS — `ad5e609e` commit body 明確段「Wave B-4: P1-PORTFOLIO-RESTING-EXPOSURE-1 (E1)」+82 LOC + 2930/0/1。 |
| 4 | test baseline 來源驗 | PASS — `9980448a` commit body 自陳 2915/0/1 Linux + 2908/0/1 Mac baseline；E1 self-report 宣告 Mac post-Round 2 = 2930/0/1 = +1 規模一致（差 7 是 7 既有 P1 portfolio test 在 9980448a 加進去後 Mac 端 socket-permission ignored = +7+15=2930 範圍 plausible，但精確差不在本 review 職責 — E4 跑回歸驗）。 |
| 5 | PA dispatch stale 處置 | **FLAG-LOW** — E1 self-report §1+§7 已自陳 dispatch 基於 stale state（9980448a 已 land + sign-off），自行降級為「test coverage top-up」並做唯一未覆蓋 gap（3rd test 端對端 gate chain）。降級決策合理且明文 PM 待裁；非 race protocol fail，只是 dispatch governance 漏氣。**E2 verdict 不阻 commit**，但 PM 需在 sign-off ledger 註明「dispatch stale 接納為 P1 test coverage top-up」。 |

**§1 結論**：5 條全 PASS（含 1 LOW flag 屬 dispatch governance 非 race）。

---

## §2 Test scope necessity audit

對 dispatch §3 mapping 表逐項 grep + 行號核對：

| Dispatch 要求 | E1 mapping claim | E2 grep 核驗 | 等價判定 |
|---|---|---|---|
| `test_resting_maker_qty_counts_toward_exposure` | `test_p1_portfolio_resting_entry_only_added_to_long` (tests.rs:1652) | tests.rs:1652-1669 場景 (1)：0.002 BTC × 50_000 entry-side resting，filled=0，**修前** exp=0%，**修後** exp=1% / corr=1%；1e-4 tolerance assertion。E1 claim 「100% 等價」**成立** — 釘的是「resting maker qty 進 effective notional」核心不變式。 | ✅ 真等價，alias duplicate 確會 noisy |
| `test_resting_close_qty_does_NOT_double_count` | `test_p1_portfolio_resting_close_only_reduces_filled` (1672-1694) + `test_p1_portfolio_resting_close_reduces_capped_at_filled` (1726-1746) | 兩 test 對稱：(a) close-side resting **扣減** filled（200 - 100 = 100 不是 200 + 100 = 300） + (b) 扣減封頂於 filled 不翻面成負。E1 claim 「100% 等價 + 加強」**成立 + 比 dispatch 更嚴**。 | ✅ 比 dispatch 更嚴 |
| `test_resting_entry_qty_correlated_pair_blocks_oversize` | **缺 → 新加** (1793-1872) | 既有 7 test 全是 helper-level（直呼 `compute_*_exposure_pct`），無 `risk_checks::check_order_allowed` 端對端 chain。E1 claim「gap 確實存在」**成立**。 | ✅ 真 gap，必補 |

**新 test 場景設計檢查**：BTC filled 0.04 × 50_000 = 2_000 + ETH entry resting 1.0 × 4_000 = 4_000 → effective_long=6_000 → 60.0% = `default_correlated_exposure_max_pct()` (risk_config.rs:484)。**剛好觸 cap 行為**：`check_order_allowed` L175 用 `>=`（非 `>`），所以 60.0% 算觸發 reject。E1 場景設計**精準**。

**§2 結論**：dispatch 3 test 必要性分析正確；alias 補加非必要（會製造 noisy duplicate 但 alias 決策屬 PM）；唯一新加 test 真補 gap。

---

## §3 Test assertion 嚴謹性

逐行 audit 1820-1871：

1. **Float precision tolerance**：3 assertion 用 `1e-4`（line 1834/1841，與既有 7 test 1e-4 一致）。L1832 `compute_effective_long_short_notional` 返 `(6000.0, 0.0)` 對 `(eff_long - 6000.0).abs() < 1e-4 && eff_short.abs() < 1e-4` — 0 浮點累計風險（單 multiplication，無 chain）。OK。
2. **Reject reason 字串 match**：L1868 `check.reason.contains("correlated exposure")` ≡ risk_checks.rs:177 hard-coded `"correlated exposure {:.2}% >= limit {:.2}%"` 前綴。**精準**。E1 用 `contains` 不是 `==` — 兼顧 future format string 微調（如改成 `"correlated exposure (60.00%)"`），是**設計上正確**選擇。
3. **跨平台 robust**：assertion 純 f64 比較 + ASCII string contains，**無 OS-specific**。Mac/Linux 一致行為（per §5 ad5e609 cargo test 2930/0/1 Mac PASS + 9980448a Linux 2915/0/1）。
4. **Gate 確認設計**：L1846-1849 small qty(0.001 × 4000 = 4 USDT) intent 防止其他 gate（leverage / position size）先 reject — E1 advance design **正確 + adversarial-thinking 好習慣**（避免 false positive 誤判 root cause）。
5. **is_reducing=false 明示**：L1858 顯式注釋「新開倉走完整 gate」，**防範未來重構不誤改為 true**。Defensive coding 加分。
6. **顯式 helper call**：L1832 + L1839 + L1854 三 helper call **重複** — 與 router.rs:438-450 paper path 完全鏡像（E2 prior round MEDIUM-1 也指出 router.rs 三 caller 同 pattern），test 鏡像 production pattern 合理。

**§3 結論**：assertion 嚴謹 + cross-platform safe + adversarial-defensive。0 issue。

---

## §4 Pre-existing baseline integrity + sibling overlap check

1. **Pre-existing baseline 2930/0/1**（Mac）：base = 9980448a 之後 = 2908（pre-9980448a） + 22（7 P1 test + 15 sub-test 落地）= 2929（pre-Round 2）+ 1 新 = 2930。E1 算術成立。E4 跑 cargo test 驗。
2. **Sibling overlap 0**：
   ```
   git status:
     M event_consumer/pending_sweep.rs / unattributed_emit.rs
     M strategies/grid_trading/{constructors,mod,position_mgmt,tests}.rs
     M strategies/maker_rejection.rs
     M tick_pipeline/{commands,on_tick/step_4_5_dispatch,pipeline_helpers}.rs
     M database/{mod,trading_writer}.rs
     M helper_scripts/db/passive_wait_healthcheck/{__init__,runner}.py
   ```
   **0** 命中 `intent_processor/`。`ad5e609e` committed = clean。Sibling 不影響 ad5e609e 行為，本 review 範圍隔離。
3. **Sibling cargo test 衝突風險**：sibling 改 commands.rs / maker_rejection.rs / grid_trading/* 等可能觸 `cargo test --lib` 既有 test。**但本 IMPL 僅 tests.rs +82**，不引入 source 變化，sibling 即使編譯失敗也不退化 ad5e609e 的 2930/0/1 之 1 個新 test 是否 PASS（test 是 self-contained 不依 sibling source）。
4. **新 test 對 sibling 副作用**：0 — 純 unit test scope，state 用 `PaperState::new(10_000.0)` 構造，無 IPC / no global mutation。

**§4 結論**：baseline integrity OK + sibling 0 overlap + 新 test 0 副作用。

---

## §5 §九 + §七 + 跨平台合規

1. **§九 文件大小**：tests.rs 1875/2000（過 800 warning 線 + **餘 125 LOC** 未過 2000 hard cap）。Pre-existing baseline = 1793 → +82 = 1875，**新加未跨 2000 cap**，不觸 pre-existing exception clause。OK。下一輪建議拆 `tests_p1_portfolio_resting.rs` + `include!`（E1 §6 已標記）。
2. **§七 注釋規範（2026-05-05 governance 中文默認）**：L1794-1819 + L1829-1831 + L1846-1848 + L1858 全中文塊，0 純英文長段，0 hardcoded path。OK。L1835/1842/1863/1869 assertion message 用英文短句（Rust idiom + test debug 友好）— 接受。
3. **跨平台 grep**：
   ```
   $ grep -nE '/home/ncyu|/Users/[^/]+' rust/openclaw_engine/src/intent_processor/tests.rs
   (0 命中)
   ```
   PASS。
4. **CLAUDE.md §九 既有 8 條 checklist**：
   - 改動範圍與 PA 方案一致：✅（dispatch stale 但 E1 自行降級成補 gap，scope 縮小不擴大）
   - 沒有 except:pass：N/A (Rust test)
   - 日誌 %s：N/A
   - 新 API 端點 _require_operator_role()：N/A
   - except HTTPException order：N/A
   - detail=str(e) 改成 "Internal server error"：N/A
   - asyncio 中無 blocking threading.Lock：N/A
   - 沒有私有屬性穿透 ._xxx：✅（test 用 pub API + `pub(crate) resting_limit_orders_iter`，per 9980448a IMPL 已 expose）

**§5 結論**：§九 + §七 + 跨平台 100% PASS。

---

## §6 Verdict

### **APPROVE → PASS to E4**

E1 補測 +82 LOC 設計嚴謹 + scope 精準補 gap + 0 race + 0 cross-platform issue + 0 governance issue。Dispatch stale 但 E1 self-report §7 已明文降級為 test coverage top-up + PM 待裁 — 此為 dispatch governance 非 code review fail，不阻 commit。

### 必修清單

**0 BLOCKER / 0 HIGH / 0 MEDIUM / 0 LOW**。本 round 無修補需求。

### Advisory（不阻 E4）

1. **A-1（informational, → PM ledger）**：dispatch stale 處置採選項 A（commit 同 P1 ticket 補測標記），PM sign-off 註明「dispatch governance: PA 未察 9980448a 已 sign-off，E1 self-report §1 已誠實識別，採納為 test coverage 完整性 top-up」。
2. **A-2（→ P2 backlog）**：tests.rs 1875/2000 接近 cap，下一輪補測前先拆 `tests_p1_portfolio_resting.rs`（與 `tests_predictor_router.rs` 同 pattern），避免下次破 cap。E1 §6 已開 P2-PORTFOLIO-RESTING-TEST-COVERAGE，重用同 ticket scope。
3. **A-3（→ A3 不必跑）**：本 round 純 +82 LOC test 無 source 改動，per `feedback_impl_done_adversarial_review.md` 對抗審觸發條件（GUI/IPC/寫操作/共用 helper）**不命中**，A3 可省。E4 regression 仍跑。

---

**E2 REVIEW DONE: APPROVE → PASS to E4** · report path: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-16--p1_portfolio_resting_exposure_1_supplement_e2_review.md`
