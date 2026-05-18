# PA Memory — 工作記憶

## Phase 1b Calibration Cell Selection Report（2026-05-18）

**觸發**：sweep run `sweep_20260518_125510` 完成（81 cells / 1.4 sec / `bybit_demo_ws`）；PA decision memo `5df39d13` §5 C1-C5 cleanup steps 應用 + top-2 pilot 推薦。

**核心發現**：
1. **N=78 post-dedupe**（81 raw − 3 Block 4 baseline overlap：G-D-D50/PG-D-D50/PS-D-D50）
2. **0 PASS / 0 CONDITIONAL / 35 INDETERMINATE / 43 TRUE FAIL** post-classification
3. **Top-2 INDETERMINATE candidates**（mechanical tiebreaker per memo §5 C3）：
   - #1 `G-AB-01-C90` (grid, A=0.5, B=1, C=90s, D=50, score 2.386, fill 70.8%, save 3.37 bps)
   - #2 `G-AB-02-C90` (差 B=0)
4. **5 cells tied at score 2.386**（all G C=90s, A∈{0.5,1.0,2.0,3.0} × B∈{0,1}）→ operator override 建議：替換 #2 為 G-AB-07-C90 (A=3.0) 最大化 information value

**3 個 NEW finding（非 SHOULD-FIX，未在 E2 report 內，sweep 後浮現）**：
1. **A axis (offset_bps) 對 G/PG family fill_rate 完全無感**：A 從 0.5→3.0 bps fill identical to 6 位小數。Hypothesis: (a) 60% spec design intent (BBO-cross 由 spread 主導, A 只進 fee saving 公式) (b) 25% IMPL bug (`_did_fill_within_window` 未傳 offset) (c) 15% sample artifact。**建議 SD-1 verify**.
2. **PS family (phys_lock_stale_roc_neg) 100% family_mismatch skip** (26 cells all n_eligible=0)：strategy router 不發 close events，pilot 完全無 PS 候選。**建議 SD-2 verify**.
3. **Spec v0.2 expanded denom 驗證**：sample G-AB-01-C30 `54 - (0+2+0+4+0) = 48 = n_eligible` ✓ 確定 v0.2 IMPL 對齊 spec。

**設計交付（9 段）**：
- §0 Exec summary（PnL-led, 35/0/0/43 tier）
- §1 Methodology（5 C cleanup steps + tier classification rule）
- §2 Raw sweep overview（per-family / parameter sensitivity / skip-reason distribution）
- §3 Post-dedupe + tier breakdown（35 INDETERMINATE 完整 list + 43 TRUE FAIL 摘要）
- §4 Top-2 pilot candidates + tied 5 cells + override 建議 + 24h pilot 5 ACs + rollback trigger
- §5 5 Risk + Caveats（E2 carry-over BBO-cross-proxy bias + NEW A axis anomaly + NEW PS family bug + v0.2 denom check + 24h ground truth list）
- §6 next dispatch（operator decision + SD-1 / SD-2 side dispatches + PnL-priority assessment + boundary 列表）
- §7 16 原則合規（A 16/16 全合規 + 5 硬邊界 0 觸碰 + DOC-08 §12 0 觸碰）
- §8 Race check 5/5 PASS

**影響評估**：
- ✅ 16 原則 16/16 全合規（read-only analysis + recommend only）
- ✅ §四 5 硬邊界 0/5 觸碰
- ✅ DOC-08 §12 9 不變量 0/9 觸碰
- 改動風險評級 = 低（無代碼改動，僅 selection report + pilot dispatch recommendation）

**核心教訓（3 個）**：
1. **BBO-cross-proxy 設計局限導致 A axis dead-variable 警報**：sweep harness 用 BBO-cross 是 spec §3 設計選擇，但這個選擇可能讓 A (offset) 在 fill detection 中無感（depends on IMPL 是否把 offset 餵 cross check）。**新 PA mandate**：sweep harness 設計時 必須 explicit 區分「fill detection」與「fee saving 計算」兩個用途的參數依賴，並在 spec 寫清。E2 review 漏 catch 此點是因為僅 verify denom 計算 + Wilson CI 數值，未做 sensitivity check。E2 SOP 應加「per-parameter axis sensitivity sanity check」step.
2. **Sweep 1.4-sec 過快是 adverse=NULL artifact 直接原因**：fill_ts + 60s look-ahead window 在 1.4 sec sweep 內全部來不及採；PA decision §3 已預期但 35 cells 全 INDETERMINATE 強化結論：1.4-sec sweep 是 fill calibration 的 viable approach 但 adverse 必須 24h pilot 補。下次類似 calibration 設計：spec 明確「sweep 只 fill+saving / adverse 走 pilot」divide。
3. **Tiebreaker SOP 與 information value 衝突需 PA push back**：mechanical tiebreaker (cell_id ASC) 推 top-2 為 G-AB-01-C90 + G-AB-02-C90（只差 B=0 vs B=1），但 5 個 tied cells 在 A axis 跨度大；override 推 G-AB-07-C90 為 #2 才能在 pilot 上同時驗證 §5.2 A axis anomaly。PA 守 SOP 出 official top-2 + surface information value override 建議，operator 自決。

**E2/E4 重點審查 3 點**（給後續 sweep harness IMPL revisit）：
1. `phase_1b_sweep_replay.py:200-300` `_did_fill_within_window` cross-check logic 是否 incorporate `offset_bps` — verify A axis dead variable hypothesis
2. close-maker family routing logic — verify PS family 為何 100% family_mismatch（spec design vs router bug）
3. spec v0.3 應新增「per-parameter axis sensitivity sanity check」step in spec §4.2 acceptance（防止下次 A-axis-dead 漏 catch）

**完整報告**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--phase_1b_calibration_cell_selection_report.md`（已複製到 `srv/docs/CCAgentWorkSpace/Operator/`）

---

## Memory Usage Contract (2026-05-16)

- 本文件保存歷史教訓與角色偏好，不是 active state、TODO 或 runtime ledger。
- 若舊條目與 `TODO.md`、`README.md`、`CLAUDE.md`、`.codex/MEMORY.md`、`docs/agents/context-loading.md`、代碼或 runtime 證據衝突，信任較新的有證據來源並顯式說明衝突。
- 不要靜默刪除舊條目；只追加可復用的 durable lesson。長報告放 `workspace/reports/`，active 進度放 `TODO.md`。

## F-FA-3 W-C Caveat 2 不變式 guard tests + grep guard rule 設計（2026-05-15 Wave 1 Track A4）

**觸發**：PM Wave 1 Track A4 派工；EDGE-P2-3 Phase 1b close-maker-first 4-agent review APPROVED-CONDITIONAL；FA round 2 §4 標明 F-FA-3「audit 欄位不走 spine lineage」為 blocking minor 必補 IMPL prereq。

**核心發現（PA empirical re-check 2026-05-15）**：
1. **`trading.fills.details JSONB` 已存在（V003 line 284，10 個月前）**：5 audit 欄位走 details JSON-extension **是 zero-schema-migration**，僅需新建 V094 加 `close_maker_attempt` BOOL hot-path column + writer 升級 + healthcheck 新 check
2. **`trading_writer.rs:430` INSERT INTO trading.fills 列表 不寫 details**（23 columns 無 details）— V094 IMPL 必同步升 writer 寫 details payload，否則 audit 100% NULL → guard tests 全 FAIL
3. **W-C Caveat 2 不變式雙層 short-circuit 已在 production**：commands.rs:812-815 entry 端寫 None 4 個 spine_*_id；event_consumer/loop_exchange.rs:264-283 fill_completion 端讀 PendingOrder 全 None → emit_fill_completion_lineage runtime_shadow/mod.rs:451-457 短路 return 0
4. **不變式違反場景**：IMPL agent 無意中把 audit 接 spine writer（看到 spine_order_plan_id 已存在於 OrderDispatchRequest 結構）→ 破 commands.rs:812-815 不變式 → 觸發 [55] WARN → 可能讓 W-D MAG-083/084 sign-off 後不變式回退（迴歸 W-C round 1 CONDITIONAL）

**設計交付（5 段）**：
- §2 4 integration test specs（IMPL E1 / E4 直接照寫 ~50-200 LOC each）：
  - test_1: close maker audit 100% 走 fills.details，spine 0 row
  - test_2: maker timeout fallback 仍 0 spine row
  - test_3: 8 reasons × 4 races = 32 case parameterized rstest，NULL rate ≤ 0.1%
  - test_4: 24h workload integration，[55] PASS 不變
- §3 6 grep guard patterns（覆蓋率 ~96%）：
  - Pattern 1a/1b: close path is_close=true 不能寫 spine_*_id Some
  - Pattern 2a/2b: spine writer emit_entry_lineage / emit_fill_completion_lineage callsite ±5 line 不含 close_maker_*
  - Pattern 3a/3b/3c: ML training 5 pipeline (linucb/scorer/quantile/mlde/dl3) 不餵 close_maker_* (mirror MIT-MF-1 non-training invariant)
- §4 V094 schema 兩段式：close_maker_attempt BOOL + close_maker_fallback_reason TEXT 為 hot column；3 price/reason 走 details JSON-extension
- §5 healthcheck [63] dual gate：Gate A (W-C Caveat 2 close path 0 spine row) + Gate B (audit 完整性 ≥ 99.9%)；與 [55] 互補避免「[55] PASS 但 close path 開始寫 spine」盲區
- §6 IMPL prereq 5 解除條件：F-FA-1/2/3 並行 ~1.5 PA-day total

**影響評估**：
- ✅ 16 原則 16/16 合規（強化原則 #3 trace 完整性 + #7 ML non-training invariant + #8 audit 完整性）
- ✅ DOC-08 §12 9 不變量 0/9 觸碰（其中「執行回報必落 fills 表」strengthens by 5 audit 欄位）
- ✅ §四 5 硬邊界 0/5 觸碰
- 改動風險評級 = 低（spec/design only，0 代碼改動；下游 IMPL 是純加新 test + 新 grep + 新 V094 column + 新 healthcheck）

**核心教訓**：
1. **PA empirical re-check 既有 schema + writer 對齊現實 mandate**：spec 假設「F-FA-1 V### migration 補入新欄位」基於 trading.fills.details 不存在；empirical 驗證發現 details JSONB V003 line 284 已存在 + writer 不寫 details 兩個獨立事實，徹底改變 schema 設計從「新增 5 column」變「JSON extension + 1 hot column + writer upgrade」。新 PA mandate：派 sub-agent 前必先 grep schema + writer 對齊現實，不能基於 spec 假設設計
2. **不變式雙層守護必要性 (positive + negative gate pattern)**：integration test 是「正面驗證」second-line（IMPL 後跑 cargo test），grep guard rule 是「負面攔截」first-line（IMPL 中審查時 grep）；兩者並行才能擋住 IMPL agent「無意識把 audit 接 spine writer」常見 drift。類比 W-D MAG-083 P1-1 抽 stable_id helper（正面導引）+ P2-N2-4 CI grep（負面攔截）雙防線 pattern
3. **healthcheck 互補性 (orthogonal coverage)**：[55] 看整體 lineage 完整性（分母含全部 chains），[63] 看 close path 特定的「不變式缺席性」（分母只 close path）；獨立 gate 設計避免「[55] PASS 但 [63] FAIL」盲區（如果 close path 開始寫 spine 但其他 lineage 仍完整，[55] 整體分母無感，[63] 專察 close path 異常）
4. **AMD §8 prereq 完整性對 IMPL drift 控制關鍵**：FA round 2 §6 識別 F-FA-1/2/3 pre-IMPL 未掛 §8 prereq 是 governance gap；本 report §6 細化 5 解除條件 + §8.2 列出 PM 派發 Action 清單，補完 AMD §8 第 5 條 prereq trace；治理紀律應對齊 AMD-01 詳細度

**E2 重點審查 3 點**（給 IMPL phase E2 review）：
1. trading_writer.rs INSERT INTO trading.fills 列表升級加 details JSONB 寫入 — TradingMsg::Fill enum 加 details 欄位是否破壞既有 23-column INSERT 的 SLA + Cross-language IPC contract
2. V094 close_maker_attempt BOOL hot column ADD COLUMN IF NOT EXISTS NOT NULL DEFAULT false — Guard B 型別驗證對 hypertable 行為（per V008/V015/V017/V028/V033 既有 pattern 驗證）；Guard C BTREE partial index `WHERE close_maker_attempt = true` 對 hypertable chunk 創建行為
3. healthcheck [63] dual gate 在 [55] PASS 同期是否會出現 false positive（如果 close maker 採樣 < 5/24h，必須 NEUTRAL 不評估，per §5.2 sample size gate）

**E1 派發建議（IMPL prereq 解後）**：
- E1-CMA-1: trading_writer.rs INSERT 列表加 details + TradingMsg::Fill enum 加 details 欄位 + apply_confirmed_fill 構造 details payload（~80 LOC）
- E1-CMA-2: V094 migration（~120 LOC + Guard A/B/C + idempotency 驗證）
- E1-CMA-3: helper_scripts/db/passive_wait_healthcheck/checks_close_maker_audit.py [63] check_close_maker_audit_lineage_integrity（~60 LOC）+ runner.py 註冊
- E4 並行：4 integration test specs 寫成 cargo test code（~470 LOC total per §2）
- 全 4 sub-agent 並行 0 file 重疊；估 ~2 E1-day total

**完整報告**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--f_fa_3_w_c_caveat_2_guard_tests_design.md`（也複製到 `srv/docs/CCAgentWorkSpace/Operator/`）

---

## 12-Agent Consolidated Audit Fix Plan（2026-05-16）

**觸發**：12 specialized agents (FA/AI-E/E5/E4/E3/CC/QC/MIT/BB/TW/R4/A3) 完成全系統 audit。PA 逐條 verify P0/CRITICAL/BLOCKER findings against actual code。

**核心結論**：
- 14 findings classified P0/CRITICAL/BLOCKER by agents；PA 確認 9 真實、2 moot（funding_arb deprecated / PG unverifiable from Mac）、3 by-design（shadow_mode / L2 manual / lease shadow-bypass）
- **真正 P0 3 項**：(1) A3-BLOCKER GUI Emergency Stop / Close All 一鍵無安全短語 (2) QC-P0 Donchian look-ahead bias `trend.rs:190` include current bar (3) P0-EDGE-1 negative edge（結構性，非代碼修復）
- **假 P0 4 項降級**：FA-P0-1 ONNX stub→P2（by-design graceful degradation）、FA-P0-2 shadow_mode→KNOWN-STATE、FA-P0-4 L2 no scheduler→KNOWN-STATE per ADR-0020、QC-P0-2 funding_arb→MOOT（deprecated strategy）
- 13 WP 拆分 4 wave 並行；Wave 1 = WP-01(GUI)+WP-02(Donchian)+WP-05(Security)+WP-09(Docs) 4 路並行無交叉
- 5 cross-audit dedup clusters（Cluster A negative edge 3 agents / Cluster C shadow-mode 3 agents / etc）

**關鍵副作用識別**：
- WP-02 Donchian fix changes indicator output → all bb_breakout tests need update + replay results differ + engine rebuild
- WP-03 OU sigma fix changes grid spacing → grid_trading strategy behavior change
- WP-06 Arc<str> migration → serde/IPC serialization compatibility
- WP-13 Reconciler channel renewal → deadlock risk at live pipeline respawn

**報告路徑**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--12-agent-consolidated-fix-plan.md`

## P0 Replay engine counterfactual fix design — Tier A v1（2026-05-11）

**觸發**：operator「修 replay engine 讓它能對策略修改做真實 counterfactual validation」；E1 a9729bbc4d61a 報告 6 hardcoded blockers。

**核心發現（PA empirical re-check after E1 report）**：
1. **#1 is_pinned**：真 hardcoded line 1151；scanner_timeline.is_active_at() 已存在；fix ≈ 30 LOC
2. **#2 position_state**：真 hardcoded；ReplayPaperSnapshot.positions Vec 已 mutate（apply_fill_open/close 1648-1745）；fix 需在 build_tick_context 構造 stack-local PaperPosition borrow 餵 ctx，~50 LOC + ReplayPosition 加 owner_strategy 是關鍵 attribution wire
3. **#3 alpha_surface_ref**：production runtime 今日也是 EMPTY（W-AUDIT-8a Phase B/C/D 未 land）— replay 用 EMPTY **反而與 production 對齊**，不是 bug；Tier A 不修，Tier B 等 alpha collector land
4. **#4 scanner_config**：Rust 端 config.rs:7-31 已可從 manifest.scanner_config 讀；Python `_build_manifest_jsonb` 從不寫該 key；fix = Python +25 LOC + 0 Rust
5. **#5 strategy_params**：Rust replay_runner.rs:435 已 deserialise；Python 路徑用 V049 detour（route_helpers.py:922-928）不可靠；fix = Python `_build_manifest_jsonb` 直接 echo +15 LOC
6. **#6 Kelly 3 億 ETH**：根因不是 Kelly bug 是 `ReplayPaperSnapshot.latest_price: Option<f64>` **全域單一 anchor** — 不同 symbol 共用 last-touched price；fix = 加 `latest_price_by_symbol: HashMap<String, f64>` per-symbol anchor，~50 LOC

**Tier A 設計**：~210 LOC，5 sub-agent 並行（E1-A T1+T2 / E1-B T3+T4 / E1-C T5 / E1-D T6 test / E1-E docs）；1.5 E1 days；風險中；forbidden_guard 全綠；16 原則 16/16；DOC-08 §12 0 觸碰；§四 5 硬邊界 0 觸碰。

**Tier B 推遲**：依賴 W-AUDIT-8a Phase B/C/D land；~500 LOC；N+2 末 / N+3 初規劃。

**E2 重點 3**：(1) T2 PaperPosition stack-local borrow lifetime per-iteration NLL；(2) T3 scanner TOML→JSON→ScannerConfig serde rename 對齊；(3) T5 grep `.latest_price` 全 callsite review backward compat

**核心教訓**：
1. **「Hardcoded」誤判 vs「wire-up 缺」**：E1 報告 6 hardcoded 中只有 #1/#2/#3 是真硬 code；#4/#5 是 Rust 端早就支援但 Python 從不寫；#6 是 ReplayPaperSnapshot 結構性局限。PA 真實復查 binary source > E1 categoric 判斷
2. **PaperPosition import 合規邊界**：`paper_state::containers.rs` 是 pure data struct（#[derive(Clone, Serialize)]），TickContext 已直接 import。forbidden_guard 禁的是 `PaperState mutate side`（全域 mutable + DB writer channel），data container 同 module 不同 layer。replay 引 PaperPosition data type 不破 forbidden invariant，但 E2 nm symbol audit 仍要驗
3. **Tier B 不應現在做**：alpha_surface 真值依賴 collector，collector 在 W-AUDIT-8a Phase B/C/D；現在做 Tier B = 重複 work + 設計可能變。Phase A spec 強調 EMPTY_ALPHA_SURFACE 與 production runtime 一致（CLAUDE.md §五 W-AUDIT-8a SPEC PHASE 2026-05-09），Tier A accept 是正確 trade-off
4. **per-symbol anchor 不只 Kelly cap 修正**：對齊 live `router.rs:373` price anchor 邏輯 = 強化 cross-language R5-T7 invariant equivalence，**理論上 replay 更綠**（不是更紅）
5. **§九 2000 LOC cap headroom**：Tier A 改 runner.rs +80 (1175→1255) / risk_adapter.rs +50 (562→612) 都安全；不需 pre-existing baseline exception clause

**完整報告**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p0_replay_engine_counterfactual_fix_design.md`

---

## P2 N+2 sprint backlog tickets integration doc（2026-05-11）

**觸發**：W2 IMPL chain FULL CLOSURE (HEAD `a771226d` → `ebbcc038` → `9463f778`) + E2 W2 chain review (`d4186c86`) + W2 signoff_pack §4 → 3 P2 N+2 sprint ticket 需正式入 backlog tracker；額外加 P1-1 stable_id helper CI grep rule follow-up（per PA memory 2026-05-11 §架構教訓 2）。

**4 P2 ticket scope**：
- **P2-N2-1** `panel_aggregator/btc_lead_lag.rs` 1771 LOC → 4-split (producer.rs / ingest_task.rs / snapshot.rs / db_writer.rs)，與 W1 sibling funding_curve/oi_delta pattern 對稱；~1.5 E1-day
- **P2-N2-2** `helper_scripts/reports/w2_paper_edge_report.py` NEW 1257 LOC → 4-split (metrics / render / smoke / report.py CLI)，CLI byte-equal output + smoke 3 case PASS + 1 sprint thin wrapper compat；~1 E1-day
- **P2-N2-3** Layer 2 helper share-code：抽 `panel_aggregator/mod.rs::should_spawn_btc_lead_lag_producer(paper_enabled_env, has_demo, has_live)`，main.rs:1005-1018 + integration test:119 mirror 兩 callsite 改 import；+30/−30 LOC 淨 0；~0.5 E1-day
- **P2-N2-4** stable_id CI grep rule：`helper_scripts/ci/check_no_literal_stable_id.sh` 攔截 `stable_id("decision"|"plan"|"report", &[…])` 字面複製違規（spine_ids.rs / events.rs / tests.rs / runtime_shadow.rs allowlist），與 W-D MAG-083 P1-1 helper 抽出搭配「正面導引 + 負面攔截」雙防線；~0.5 E1-day

**Aggregate P2 backlog**：active = 8 條（含本 doc 新增 4 條）+ DONE = 7 條 + N+5 mounted = 1 條；W-AUDIT-7c R2 7 P2 實際是 single false-positive round 3 撤回（非真 backlog）。

**N+2 capacity 評估**：N+2 (W5-W6) 48 E1-days；主線 W-AUDIT-8a Phase D + Stage 2 demo cohort 14d 觀察 + W-AUDIT-8d IMPL ~37 days；buffer 11 days；本 doc 4 ticket 3.5 days；剩 ~7.5 days buffer。**完全可吸收，不擠壓 N+2 主線**。

**Priority 排序**：P2-N2-2 (純 Python smoke-driven) → P2-N2-1 (Rust 對稱 W1 pattern) → P2-N2-3 (與 1 同 wave marginal cost ~0) → P2-N2-4 (E1a stand-by 吸收)。

**Operator 拍板項**：
1. P2-N2-1 4-split (PA Option A 推薦) vs single-file + MODULE_NOTE (Option B accept) vs 2-split (Option C 不夠細)
2. P2-N2-3 Layer 2 helper share-code (PA 略偏好 silent drift 防護) vs accept inline mirror + 強標注釋

**16 原則 + DOC-08 §12 + §四 5 硬邊界 觸碰**：全 0（純 refactor + CI script + 純治理改動，0 hot path touch / 0 lease 接觸 / 0 authorization 改動）。

**架構教訓**：
1. **「Pre-existing baseline exception clause」適用嚴格**：§九 clause 僅適用 baseline > 2000；W2-IMPL-1 baseline 1253 + 本 wave +518 → 1771 雖在 hard cap 內但 > 800 警告，必開 P2 ticket + 不阻 merge；signoff_pack §4 accept rationale 必明文「W1 sibling 已拆對稱」+「N+2 拆對齊」雙理由
2. **CI grep rule = silent drift 治本防線**：W-D MAG-083 P1-1 抽 stable_id helper 是「正面導引」(用 helper 就對了)；P2-N2-4 CI grep rule 是「負面攔截」(不用 helper 就 CI fail)；兩者並行才完整。類似 over-engineering ratio 30 LOC script vs 「audit chain silent drift = MAG-082 evidence 信任崩塌」風險
3. **W2 sibling 對稱優先級**：N+2 拆 btc_lead_lag.rs 對齊 W1 已拆 funding_curve.rs/oi_delta.rs pattern，後續 W-AUDIT-8a Phase B panel_aggregator 群家族 pattern 統一可借鑒
4. **N+2 capacity rule**：5 active + 1 stand-by × 8d = 48 E1-days；4 P2 ticket 3.5d = 7.3% capacity；可吸收且 7.5d buffer 充足，不需推 N+3

**Cross-reference**：
- PA W2 dispatch plan: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--w2_impl_v12_dispatch_plan.md` (commit `0e88b4a9`)
- E2 W2 chain review: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-11--w2_chain_e2_adversarial_review.md` (commit `d4186c86`) §5.5/§5.6
- W2 signoff_pack §4: `srv/docs/governance_dev/2026-05-11--w2_impl_signoff_pack.md` §4.1/§4.2/§10.1
- PA W-D MAG-083 audit: PA memory 2026-05-11 §架構教訓 2 + 報告 `2026-05-11--w_d_mag083_pa_audit.md`

**完整報告**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p2_n2_backlog_tickets.md`（~390 行）

---

## P1-RCA STRATEGIST-PARAMS-PERSIST-1 ma_crossover restore reject（2026-05-11）

**觸發**：每次 engine restart WARN `STRATEGIST-PARAMS-PERSIST-1: restore handler rejected strategy=ma_crossover error=validation failed: confluence weight sum must be 65, got 73.00 (adx=13.75, regime=28.75, volume=22.5, momentum=8)`；operator 要求 ≤ 45 min read-only RCA。

**Verdict = A 級（fallback 工作正常 + 不是 BLOCKER）**：runtime in-memory 跑 `ConfluenceConfig::default()` TOML defaults (25/20/12/8 sum=65)，**不是 stale 73 也不是任何持久化值**。restore reject = 設計上 fail-soft 邊界，PERSIST-1 commit `f1f7403` 明示「Fail-soft: DB unavailable / migration V019 not applied → empty vec, log single warn, engine starts normally」；雖然這個 case 不是 DB unavailable 是「persist 寫入質量退化」，但 fail-soft 仍守住。

**Root cause**：strategist_scheduler 對「weight 參數缺 key」處理 validate/apply/persist 三路徑不對稱：
- `validate_recommendation_with_reason` (mod.rs:365-368) 缺 key `continue` 跳過 weight_sum，sum=13.75+28.75+22.5=65 PASS
- `apply_params` → `handle_update_strategy_params` → `merge_strategy_params_json` (strategy_params.rs:79) 用 in-memory current 補入缺 key，cycle 跑時 in-memory mom=0（首次 explicit 設置 row id=5855 / 2026-05-05 17:16 UTC），sum=65 PASS
- `persist_applied_params` (persist.rs:67-81) 寫入 raw response（缺 weight_momentum）→ DB row 缺 key
- restart 後 `MaCrossover::new()` (mod.rs:437) `ConfluenceConfig::default()` 重置 mom=8 → restore handler 走同個 merge 用 TOML 8.0 補入 → sum=73 → `params.validate()` reject

**PG empirical 確認**：
- row 7143（2026-05-07 05:52，當前 restore target）weight_adx=13.75, weight_regime=28.75, weight_volume=22.5，**weight_momentum 缺**
- first partial weight row = 5924（2026-05-05 19:15）；first explicit mom=0 = 5855（2026-05-05 17:16）；first 4-weight loss transition = 5849→5855
- ma_crossover 24h Strategist activity = **0 row**（最後 4 天沒新推薦）；grid_trading 573 rows/24h 正常
- engine restart log（2026-05-11T10:57:42.492514Z）n=1 total=2：grid_trading 8936 PASS（row 只含 cooldown/max_cooldown_boost 無 weight key 不破 sum）；ma_crossover 7143 FAIL

**3 個 fix option**：
- **Option 1 改進版（推薦立即跑）**：PG DELETE `WHERE strategy_name='ma_crossover' AND engine_mode='demo' AND (params_json->>'weight_adx') IS NOT NULL AND (params_json->>'weight_momentum') IS NULL` — 5 SQL 5 秒消 WARN noise，destructive 需 operator sign-off
- **Option 2（Sprint N+2 治本）**：evaluate.rs:210-218 persist 前先 `merge_strategy_params_json(current_json, response)` 補完 → 寫 DB self-contained row；~50 LOC + E4 test 1-2h
- **Option 3（棄）**：放寬 sum=65 validate — 違反原則 4+5+6，破壞 confluence::compute_score 設計合約
- **架構級加固 4（建議 P3）**：restore reject 自動 DELETE row（GC，破壞 audit trail 需配合 audit log）
- **架構級加固 5（建議 P3 + QC）**：Ollama prompt schema constraint + validate_recommendation 加嚴 partial weight set

**Impact 評估**：
- ✅ 16 原則 0 觸碰、DOC-08 §12 9 不變量 0 觸碰、§四 5 硬邊界 0 觸碰
- ⚠️ 14 個 ML-tuned 非 weight 持久化值（cooldown_ms 2772000 / adx_threshold 13.75 / min_persistence_ms 231000 等）每次 restart 重置回 TOML default — Strategist 學習成果無持久性
- ⚠️ STRATEGIST-AUTO-PROMOTE-CRITERIA-1 「穩定計數器」設計意圖被破壞（但 ma_crossover 4 天沒新 row 即穩定計數器早已停滯，restart 影響 = 0）

**核心教訓**：
1. **Three-path inconsistency 反模式**：對同一 input（partial weight payload），validate / apply / persist 三條路徑用「current 補入 / 不補入」處理不一致 → 同時 PASS 與 FAIL 的 schism。新代碼設計 invariant gate（如 sum=65）時必確保所有 entry point 對同 input 收斂到同個 verdict
2. **Fail-soft != 設計不變式可違反**：fallback 守住 runtime 但 audit trail 不完整（row 7143 缺 weight_momentum 字段 → 無法重建「當時 in-memory mom=0」事實），原則 8「交易可解釋」實質受損
3. **PG empirical verify 必跑**：Mac 上只看 grep 規則 + log message 不夠，必 ssh trade-core + PG 直查 timeline transitions 才能精準鎖定 first partial row（5924 / 5855）和 root cause owner（Ollama L1 prompt design 演化）
4. **Strategist 24h 活躍度 cross-check**：「為什麼 ma_crossover restart 沒自動修」必查 `learning.strategist_applied_params` 24h 活躍度 — 0 row 表示 Strategist 對該策略無新推薦 → restart 重置永久卡 TOML default，不會被新 cycle overwrite
5. **persist 寫入質量是 latent risk**：寫入路徑用 raw response 短期看「省 LOC 與 cycle delta 對應」更乾淨，但 restore 需要 self-contained schema — 應始終 persist merged 結果，不是 raw delta

**E1 派發建議（Sprint N+2 Option 2 治本）**：
- 文件：`rust/openclaw_engine/src/strategist_scheduler/evaluate.rs` (1 hunk persist 前 merge)
- 公開：`event_consumer/handlers/strategy_params.rs::merge_strategy_params_json` 從 `pub(super)` 改 `pub(crate)`
- E4 test：persist round-trip — partial weight response in → DB row out → load + restore handler 過 validate
- 風險：低（只改 persist 寫入路徑，不動 cycle 邏輯）

**E2 重點審查 3 點**：
1. `merge_strategy_params_json` 從 `pub(super)` 改 `pub(crate)` 是否破壞 module encapsulation — 建議 wrap 一層 `strategist_scheduler` 內部 helper 不直接 expose
2. 對 ma_crossover 以外 4 個策略（grid_trading / bb_breakout / bb_reversion / funding_arb）同樣套用 — 是否有策略對 partial payload 有合法 reset semantics（部分 reset 是 feature 不是 bug）
3. 持久化 audit trail 變大（row 從 ~30 lines JSON 變 ~80 lines full schema）— V019 schema 字段大小 + idx 索引性能 + 90d retention rolling size impact

**完整報告**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p1_strategist_params_persist_ma_crossover_rca.md`

---

## W2 IMPL v1.2 chain dispatch plan — 5 sub-agent 拆分（2026-05-11）

**觸發**：Sprint N+1 Phase 4 待派；operator 要求 PA 寫 5 sub-agent dispatch plan（不寫業務 code）。

**重大發現**（reality check before dispatch）：operator 任務描述假設 W2 IMPL 未開工，但 Sprint N+1 D+0 pre-dispatch readiness 階段已把舊 spec §11 4 個 sub-task 大半 land：trait skeleton (alpha_surface.rs 650 LOC) / V088 migration (456 LOC) / BtcLeadLagPanelSlot / BtcLeadLagProducer (panel_aggregator/btc_lead_lag.rs 1253 LOC + run_loop + PG INSERT) / step_4_5_dispatch.rs paper-only fence Layer 1 / main.rs spawn / main_pipelines.rs 三 pipeline slot inject / ma_crossover + grid_trading declare CrossAsset + on_tick shadow log via cross_asset/mod.rs (441 LOC) / bb_breakout + bb_reversion 確認**不** declare CrossAsset。

**真實剩餘 W2 gap = 5 個（G1-G5）**：
- G1 orderbook 接線（`btc_book_imbalance: 0.0` placeholder line 113/271/273）— 用 既有 WS `orderbook.50.BTCUSDT` topic（per BB push back, 0 req/s ongoing）
- G2 Layer 2 fence spec amendment（Python writer obsolete → Producer env-gate；spec v1.2 → v1.3 inline edit + cross_asset/mod.rs MODULE_NOTE 同步）
- G3 healthcheck [57]（`passive_wait_healthcheck.py` 加 check_57：age < 120s + cohort 7-sym + regime_tag extreme ratio + book_imbalance != 0/NULL）
- G4 D+12 paper edge report 工具鏈（`helper_scripts/reports/w2_paper_edge_report.py` + `sql/queries/w2_btc_alt_lead_lag_counterfactual.sql`：spec §7.1 mandatory metric 6 條 + dual-layer σ acceptance + PSR(0) skew/kurt formula + +15/+5-15/<+5 三檔 gate verdict）
- G5 E2 三層 fence 對抗 + E4 regression test pack + sub-task sign-off pack（`tests/btc_lead_lag_panel_fence_integration.rs` 新檔 + signoff_pack.md）

**5 sub-agent 拆分**：W2-IMPL-1 (1.5d, G1) / W2-IMPL-2 (1d, G2) / W2-IMPL-3 (1d, G3) / W2-IMPL-4 (2d, G4) / W2-IMPL-5 (1.5d, G5)；前 4 個全並行 0 file 重疊（唯一弱衝突 main.rs:977-996 兩 hunk 改動方向正交：IMPL-1 加 orderbook slot inject、IMPL-2 加 env-gate wrap）；IMPL-5 rebase 等 IMPL-1+2 land。Acceptance window 5-7d，D+5 deploy paper engine，D+12 paper edge report land。

**Cross-wave 衝突檢查（全 0 撞）**：
- vs W1 IMPL chain（5/11 active funding panel staleness fix / cohort coverage / POLUSDT migration）：W1 panel.funding_rates_panel + panel.oi_delta_panel；W2 panel.btc_lead_lag_panel；三 sibling 檔 PA D+0 已預留 anchor，0 重疊
- vs Phase 3 V091 deploy（D+1 evening + D+2 ALTER VALIDATE）：V091 改 learning.decision_features reject/close reason CHECK NOT VALID；W2 改 panel namespace 不同
- vs P1-RCA-1 + P1-1 並行 sub-agent：弱衝突（P1-1 改 strategy_impl.rs on_rejection rollback；W2-IMPL-5 test rebase）；PM dispatch 排序：P1-1 / P1-RCA-1 先 land
- vs W6 RFC verdict + V086 IMPL / W7-2/4/5 / W3 Stage 1 / W4 RouterLeaseGuard Drop / W5 V089/V090：全不撞 file

**E2 重點審查 3 點**：
1. 三層 fence 主防線完整性（Layer 1 step_4_5_dispatch.rs default → None / Layer 2 IMPL-2 spawn env-gate 三狀態完整 / Layer 3 cross_asset/mod.rs evaluate_shadow_signal None handle）— 缺一 fence 失靈
2. Strict shift(N) lookahead-free（orderbook IMPL-1 必 shift(1) close-aligned 禁含 current tick；paper edge report IMPL-4 SQL 必對齊 producer 端 strict shift(N) past close 計算）
3. CC compliance + 硬邊界 5 項 + DOC-08 §12 9 條 0 觸碰（W2 IMPL chain 不動 lease / authorization / SM-04 Guardian / IntentProcessor / paper_state singleton）

**16 原則合規 16/16**；**DOC-08 §12 9 不變量觸碰 = 0**；**§四 5 硬邊界觸碰 = 0**；**改動風險評級 = 中-低**（hot path 影響可忽略：producer 60s tick + 11 strategy declare flag + 1 healthcheck + 1 report tool；3 層 fence 守住 demo/live 不污染）。

**核心教訓**：
1. **PA 派 sub-agent 前必先 reality check**：operator 任務描述基於數天前認知，spec §11 4 sub-task 大半已 land；直接重派 = duplicate work + sub-agent 撞既有 commit；應 grep + ls + wc -l 親自盤點再拆 dispatch plan
2. **Spec §11 IMPL 拆分 ≠ dispatch plan**：spec §11 是 spec-time 設計，dispatch plan 是 wave-time 真實 gap 收尾；現實 land 後新拆 dispatch 對齊真實剩餘 5 個 gap 比硬套 spec §11 4 sub-task 重派更合適
3. **Python writer Layer 2 fence 已 obsolete**：Producer 改 Rust pull 後，原 Python writer fence 設計失效；spec v1.2 → v1.3 必補 inline edit 對齊 code 現實，避免後續 reviewer 困惑

**完整報告**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--w2_impl_v12_dispatch_plan.md`（301 行）

---

## W-C MAG-082 Caveat 1+2 Fix Plan + No-24h Short-Window Verification（2026-05-10）

**觸發**：QA `2026-05-10--w_c_signoff_audit.md` 裁決 CONDITIONAL_PASS；operator Option B（先修再 sign-off）+ 拒絕重等 24h；需設計修復方案 + 並行 E1 task 拆分 + 短窗驗證協議。

**Caveat 1 RCA（PG + Rust empirical verified）**：`agent.decision_state_changes` 0 row 不是 schema 缺失，是 producer 0 caller — `put_state_transition` 在 `store.rs:105` ChannelAgentSpineStore::impl 完整 + `agent_spine_writer.rs:217-260` flush SQL 完整 + V064 schema 完整，但 `grep -rn put_state_transition rust/` 只回 trait/impl/test 4 個位置，**0 producer call**。Sprint 2 Track E 寫 wiring 但忘 emit。

**Caveat 2 RCA**：`runtime_shadow.rs:195+203` `filled_qty: Some(0.0)` + `liquidity_role: "unknown"` 是 by-design stub（status=`shadow_planned`，在 intent dispatch 後 emit）；真實 fill 在 `loop_exchange.rs:213 apply_confirmed_fill` 寫 trading.fills 但**沒 propagate** 回 agent.decision_objects.execution_report.payload。`PendingOrder` 沒 `order_plan_id` 鏡射欄位 → cross-ref join 不上。

**關鍵架構發現**：V064 `chk_agent_decision_state_changes_object_type` 列舉 6 object_type 不含 `decision_lease` — SM-02 lease lifecycle 已在 `learning.lease_transitions`（V054，24h 62,600 row 在跑）獨立寫。Spine state_changes 是 **Spine 自己的 5 object（signal/decision/verdict/plan/report）lifecycle SM**，不要重複層級。

**修復策略（3 task 並行）**：
- E1-W-C-FIX-1（Caveat 1 wiring, ~80-120 LOC）：在 `emit_entry_lineage` 末尾加 5 條 build SpineStateTransition + 在 `loop_exchange.rs:259 fully_filled` 加 2 條 change SpineStateTransition
- E1-W-C-FIX-2（Caveat 2 real-fill, ~180-250 LOC）：在 `PendingOrder` 加 3 個 Option id（order_plan_id/decision_id/verdict_id 鏡射）+ 新 `emit_fill_completion_lineage` fn + `loop_exchange.rs` fully_filled 呼叫 → 寫**新一條** ExecutionReport row 帶真值（**Option α additive**，不動 ON CONFLICT DO NOTHING）+ 一條 `executed_by + details.fill_completion=true` edge
- E1-W-C-FIX-3（[55] healthcheck, ~80-120 LOC）：加 `bad_report_value_quality` + `chains_with_real_fill_report` + `state_changes_24h` 指標；env var `OPENCLAW_AGENT_SPINE_VALUE_QUALITY_CUTOFF_TS` 排除 historical stub
- FIX-1+FIX-2 同檔（loop_exchange.rs）合 1 個 sub-agent；FIX-3 完全獨立可並行

**Option α vs β vs γ 設計取捨**：α = 寫新一條 filled ExecutionReport row（推薦，0 migration + audit-friendly + W-D compatible）；β = ON CONFLICT DO UPDATE（棄 — 違反 append-only event log + hypertable corner case）；γ = trading.fills writer dual-write spine（棄 — 耦合 hot path + 違反 spine fail-soft）。

**Historical 51h stub rows 處理**：留著 + healthcheck SQL 加 `WHERE created_at > $DEPLOY_TS::timestamptz` cutoff filter（env var `OPENCLAW_AGENT_SPINE_VALUE_QUALITY_CUTOFF_TS`）；不寫 backfill SQL（保 append-only event log 原則）。

**短窗驗證協議（取代 24h，核心）**：
- 為何短窗夠：24h 是 evidence accumulation **量**需求，現 W-C 已累 51h；caveat 修是 producer **correctness** wiring fix，短窗能證 wiring 正確即可
- (a) Unit test：8/8 test PASS（5 build transitions / fill_completion emit / paper disable / partial fill no-emit / value_quality cutoff / passes real / fails stub / state_changes count）
- (b) Post-deploy 30 min sample：state_changes rate ≥ 5/min + bad_report_value_quality=0 + chains_with_real_fill_report ≥ 50% complete_chains（50% baseline 來自 trading.fills 86/174=49.4% 真實 ratio）+ trading.fills↔agent.decision_objects 對抗 SQL missed_n=0
- (c) 退守 60 min；若無 fill 等到首筆（demo fill rate ~2/h）
- (d) MAG-083 audit pack 必加「Caveat 1+2 wiring delta verified at deploy+30min」章節

**[55] PASS 判定升級**：
- BLOCKED_STATE_CHANGES_EMPTY 若 state_changes_24h <= 0
- BLOCKED_REPORT_VALUE_QUALITY 若 bad_report_value_quality > 0
- WARN_REAL_FILL_PROPAGATION_PARTIAL 若 chains_with_real_fill_report < complete_chains × 0.5
- chains_with_real_fill_report ratio target 50%（不是 90%）— 因 unfilled intent = cancel/reject 合法 outcome

**E2 重點審查 4 點**：(1) hot path SLA bench < 50us 延遲增；(2) 0 unsafe/unwrap；(3) stable_id(`shadow_planned`) vs stable_id(`shadow_filled`) 必產生不同 id + 不同 idempotency_key；(4) emit_fill_completion_lineage 必過濾 paper 不 emit

**E4 regression 必跑**：cross-language 1e-4 + 1000 intent/sec SLA bench + 9 new unit test GREEN + 既有 runtime_shadow tests 不破 + 既有 loop_exchange tests 不破

**風險評級**：中。hot path 影響可忽略（5 try_send + 1 emit_fn，mpsc 非阻塞）；LiveDemo 30s 中斷可接受；硬邊界 0 觸碰；16 原則強化（原則 8 交易可解釋更完整）；DOC-08 §12 9 不變量 0 觸碰。

**核心教訓**：
1. **Spine state_changes 不是 lease SM**：V064 CHECK 列 6 object_type 不含 decision_lease；不要把 SM-02 lease 5-state 重複寫進 Spine（已在 learning.lease_transitions）
2. **stub row 是 by-design 不是 bug**：emit_entry_lineage 在 intent dispatch 後立刻 emit ExecutionReport 是 lineage chain 結構完整性的設計；修法是 **加新 row** 不改舊 row（append-only event log 哲學）
3. **PendingOrder 持 SoT id 是 propagation 盲區**：FILL-CONTEXT-LINKAGE-1 已示範鏡射 context_id；spine 對應補 3 個 id 鏡射（order_plan_id/decision_id/verdict_id）是 obvious follow-up；E5 後續 P2 candidate 統一 propagate
4. **24h vs 短窗本質**：24h 證量；短窗證 wiring correctness。Caveat 修正改後者，不需重等前者
5. **healthcheck keyspace vs value**：`bad_report_quality` v1 只查 key existence 是 limitation；`bad_report_value_quality` 才是真 evidence guard；所有 healthcheck 應同時設計 key + value 兩層 gate
6. **WriteAndConfirm 對等性**：PG empirical（producer 0 caller grep verify）+ Rust source line range 是 single most decisive evidence；先 grep 後 PG 驗 timeline 是標準 RCA chain

**完整報告**：`srv/docs/CCAgentWorkSpace/PA/2026-05-10--w_c_caveat_fix_plan.md`

---

## W2 A4-C spec v1 → v1.1 落 QC 5 conditions + σ MIT prerequisite（2026-05-10）

**觸發**：QC C-2 review CONDITIONAL APPROVE 5 conditions 必修 → PA inline edit spec 跳過 D+1 PA + QC integrate phase，MIT C-3 D+1 直接收。

**5 conditions 落地（spec v1 → v1.1）**：
1. §8.1 DSR K 6 → 95（active strategy×symbol cell 總數），引 Bailey-López de Prado 2014 §4.2；mu_0 = √(2 ln 95) = 3.018
2. §8.1 paper edge gate 單檔 +5 → 三檔（+15 promote N+2 / +5~+15 extend 14d / <+5 revise）；理由錨：demo cost 15-20 bps round-trip → +5 必虧 net −10~−15 bps
3. §3.1 N 鎖 120s + §4.1 schema 加 60s/300s shadow value column + §7.1 metric (4) R²(N=60/120/300) 7d rolling 30-min bucket decay curve 強制
4. §7.1 mandatory metric set 從 5 條擴 6 條：(a) per-symbol gate n≥100+t>2.0 (b) DSR K=95 deflate non-negotiable (c) PSR(0)≥0.95 skew/kurt-aware (d) Alpha decay regime test (e) Block-bootstrap 95% CI block_size=60min 1000 iter (f) Per-cohort counterfactual delta；§7.3 strict shift(N) 並列對比差異 > 30% 失敗
5. §9 BTC regime extreme guard \|1h return\| > 200 bps → regime_tag='extreme' shadow log 不計入 7d edge avg；§4.1 schema 加 regime_tag column；§7.2 SQL FILTER；§4.2 writer 步驟 4 加 1h kline regime 計算（strict shift(1)）；§4.3 rate budget 9→10 req/min

**σ MIT prerequisite（extra condition）**：§7.1 加 acceptance prerequisite「σ verified by MIT C-3」 — BTCUSDT 1m forward-return realized σ 7d 經驗值；σ ≥ 60 bps → 重算 power（t-stat 4.71 → 2.36）+ PSR(0) 必含 skew/kurt deflation；σ < 60 bps → 採 baseline σ=30 bps 繼續。為何 prerequisite 不是 risk：σ 是 power calculation foundation，σ 錯整套 power test 失效；不是 mitigation 後果可接受的「risk」。

**衝擊副作用**：
- V088 migration 加 3 columns（btc_lead_return_pct_60s + btc_lead_return_pct_300s + regime_tag）
- C-IMPL-2 LOC ~350 → ~400（+50 LOC for regime + shadow value + 1h kline）
- §7.1 metric 5 條 → 6 條 + acceptance prerequisite，D+12 paper edge report scope 擴大
- 16 原則 / DOC-08 §12 9 條 / 硬邊界 5 項 — **0 觸碰**（unchanged from v1）
- 改動風險評級 = 低（paper-only evidence + statistical metric 補強，無 runtime 邏輯改動）

**Sign-off path 變更**：QC 已 sign-off CONDITIONAL APPROVE → MIT C-3 D+1 直接收（**不需 D+1 PA + QC integrate phase**）。MIT focus 4 點：(1) σ verify (2) strict shift grep (3) V088 hypertable PL/pgSQL + retention (4) 60s/300s shadow value 寫入路徑與主 N=120 disjoint。MIT APPROVE → D+3 起派 C-IMPL-1..4 paper IMPL → D+5 paper engine deploy → D+12 paper edge report land 含三檔 gate verdict。

**E2 重點審查 3 點 v1.1 補強**：
1. Layer 1 paper-only fence default → None（unchanged）
2. Strict shift(N) 補：含 N=60/120/300 三檔 shadow value + BTCUSDT 1h kline regime 同 strict shift(1)
3. V088 hypertable retention + 必含 btc_lead_return_pct_60s + btc_lead_return_pct_300s + regime_tag 三新欄位

**核心教訓**：
- QC review 出 5 conditions 時，PA 直接 inline edit spec 而非開 D+1 integrate phase，省 1 day 又確保 W2 IMPL 走正確方向（避免 sub-agent 收 v1 spec 開工後又因為 v1.1 改動 rework）
- σ assumption 必須 verify 不是 estimate — power calculation foundation 是 prerequisite 不是 risk，需獨立 acceptance gate
- gate threshold 必須對應 demo cost baseline — 單檔 +5 bps 在 demo 必虧 net −10 bps 是 PA 草稿 blind spot；三檔（fast track / extend / revise）對應實際 cost 結構

**完整報告**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w2_a4c_spec_v1_1_qc_5_conditions_revision.md`
**Spec edited**：`srv/docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md` v1.1

---

## W6-1 RFC Final Verdict Draft — 三角共識整合 + Track A/B 解分歧（2026-05-10）

**觸發**：D+1 W6-1 RFC 三角 sign-off 入場前 PA 整合 PA + QC + MIT 3 視角立場為 final verdict draft，省 1 day RFC 討論。

**3 視角共識（Verdict 1+2+3+4 全 capture）**：
- Verdict 1：cost_gate hard rule 維持，不引 advisory mode（PA Q1 + QC Q1 + 16 root principle #4/#5/#6）
- Verdict 2：JS shrinkage 強收縮到 grand_mean 是設計預期；high B-factor signature（QC Q1 數學論證）
- Verdict 3：cost_gate 放行 expected new fills net edge ≈ -14 bps，不需也不應做 counterfactual backtest（QC Q2）
- Verdict 4：trainer task type confirm = LightGBM regression；W6-5 撤回 imbalance flag 試行改 sample_weight ratio sensitivity（MIT W6-5 category error 揭露）

**3 視角分歧（PA Q3 hold A vs MIT Q2 hold B）解決 = Track A / Track B 拆分**：
- Track A (regression scorer 微調 immediate, N+1)：trainer task type confirm = regression → 立即跑 W6-5；不需 V086；W6 N+1 acceptance 只需 Track A PASS
- Track B (multi-class / classification future, N+2/N+3)：4-gate (V086 land + dual-write 24h 0 NULL + multi-class 18+ enum 各 class ≥ 200 sample + classification trainer task 升級 spec) 全達才 enable
- 三方立場全保留：PA「立刻做 V086」+ MIT「regression 不需等」+ Track B 4-gate spec 同時成立

**8 sub-task 對齊 W6-1 ~ W6-10**（PA spec ready, E1/MIT IMPL D+1~D+5）：
- W6-1 RFC verdict (本 draft) → AMD 件 D+1
- W6-2 V086 schema add D+1~D+2
- W6-3a/b DONE (MIT close_tag audit + PA enum spec final)
- W6-3c/d/e V086 IMPL + ALTER VALIDATE D+1~D+2
- W6-4/5/6/7/9/10 healthcheck + sample_weight 試行 D+2~D+3

**真實 enum spec**：12 reject + 14 close = 26 enum + 2 catch-all（per W6-3b 5 ambiguous A1-A5 全 ACCEPT MIT）；V086 兩 column TEXT + Guard A/B/C + NOT VALID CHECK + one-shot 30-90s backfill in migration（不開 cron）；同次 backfill 加 trading.fills 17 row 雙前綴 normalize（per PA P2 RCA）。

**healthcheck 新增 4 + 1 enhancement**：[59] M4 reject reason mix + [60] M5 evaluations.entry_context_id + [61] strategy fire silence + [62] per_strategy_sample_gate + [40] fills/day rate snapshot baseline。

**16 root principles compliance = 16/16**；**DOC-08 §12 9 不變量觸碰 = 0**；**§四 5 硬邊界觸碰 = 0**。

**E2 重點審查 3 點**：
1. Backfill SQL CASE WHEN 評估順序（ATR unavailable 先於 JS-demo 先於 cost_gate_other；雙前綴先於單前綴；bare-name 先於 prefix）— PG dry-run 9757 row distribution 比對
2. Guard A/B/C 完整性（缺一拒簽，per memory `feedback_v_migration_pg_dry_run`）
3. Producer dual-write race（V086 land 與 dual-write deploy 差 ≤ 5 min；否則 ALTER VALIDATE 會失敗）

**D+1 sign-off 流程預期**：
- Phase 1 (上午 1.5h 並行)：PA + QC + MIT 各 verify draft 是否如實 capture 各自立場
- Phase 2 (下午 1h 三角 sync)：3 全 APPROVE → 升 AMD-2026-05-1X-W6-1-rfc-verdict.md，dispatch v3.5 §6 對齊 commit
- 如 ≥1 CONDITIONAL → PA 24h 內補修 draft 重 sign-off
- 如 ≥1 REJECT → 重 RFC（不應發生，三方立場已預跑且 draft 全 capture）

**核心教訓**：
- 三角 RFC 立場分歧不一定要重 RFC 解；找到 trade-off 維度（regression vs multi-class）拆 Track 即可保全 3 立場
- counterfactual backtest 一切看 ROI：known expected -14 bps 跑 1 sprint backtest 工程 ROI 為負
- LightGBM imbalance flag 對 regression silently ignore 是經典 category error；reviewer 必先 grep `_lgb_params` objective 再批評 imbalance 算法
- enum spec 「保留 empty enum」(A3 cost_gate_atr_unavailable / A5 strategy_close_regime_shift) 比「合 catch-all」更安全；NOT VALID CHECK 一旦鎖死不可逆
- backfill 從 raw column 取字串會繼承上游所有 historical bug；trainer schema migration 是 cleansing 機會（不必另開 producer fix）

**完整報告**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_1_rfc_final_verdict_draft.md`

---

## P2-DECISION-FEATURES-DOUBLE-PREFIX 預跑 RCA — bug 早已 fix（2026-05-10）

**觸發**：MIT W6-3a §1.2 揭露 `learning.decision_features.label_close_tag` 16 row 雙前綴 `risk_close:risk_close:phys_lock_gate4_giveback`，dispatch v3.3 W5 P2 ticket 預跑。

**RCA verdict = NO P2 NEEDED**：
- True source = `trading.fills.strategy_name` 17 row（PG empirical，2026-04-23 02:39-11:55 +0200）
- Bug commit `46a9cadc` 已 fix 於 2026-04-23 13:54:11 +0200（`build_risk_close_tag()` idempotent helper in `tick_pipeline/on_tick/helpers.rs:38-45`）
- 16 row in `learning.decision_features` 是 `edge_label_backfill.py:285,304` Python backfill 從 trading.fills `array_agg(strategy_name)` 複製字串的副作用
- Rust `decision_feature_writer` + `intent_processor:1261` 寫入路徑只 emit `Some("rejected_governance")`，**不寫 `risk_close:*`** → Rust producer chain 0 bug
- Post-fix 17 天運行 0 新增雙前綴 row（PG 驗：495 row `risk_close:phys_lock_gate4_giveback` 全單前綴）

**影響範圍**（極小）：
- 16 row demo only（live/paper 0），9.3 hours window，PENGUUSDT 100% 單一 cluster
- grid_trading (10) / ma_crossover (5) / bb_reversion (1)，單一 reason `phys_lock_gate4_giveback`

**修補 plan = Option A in V086 backfill normalize**（不開 P2 ticket）：
- MIT W6-3a §6.2 spec line 189 已含 `WHEN label_close_tag LIKE 'risk_close:risk_close:phys_lock_gate4_giveback%' THEN 'risk_close_phys_lock_gate4_giveback'` mapping
- **PA 補充**：V086 同 migration 加 `UPDATE trading.fills SET strategy_name = REPLACE(strategy_name, 'risk_close:risk_close:', 'risk_close:') WHERE strategy_name LIKE 'risk_close:risk_close:%'` 對 17 row trading.fills 上游清理
- 不污染 raw `label_close_tag` 欄位，保留歷史 bug fingerprint

**dispatch v3.3 update**：
- W5 P2 list 不加任何雙前綴 ticket（無 IMPL 需求）
- W6-3c V086 SQL spec 補充 trading.fills 17 row 上游 UPDATE
- §5 A2 PA 拍板：採 V086 normalize（與 MIT 推薦一致）

**Lesson learned**：
- 「producer bug」假設前必先 grep producer chain 確認寫入點 + git log 看 fix 是否已落地 + PG 看分布時窗
- MIT 報告「open new P1 ticket」推薦在 PA RCA 下被推翻 → MIT 看到 raw 字串就推 P1 是合理的，但 PA 必須親自確認 fix 狀態，避免 ticket inflation
- backfill 從 raw column 取字串時會繼承上游所有 historical bug，trainer 端 schema migration 是 cleansing 機會（不必另開 producer fix）
- bug 早已 fix 案例（17 天前）但 backfill 表面看仍有 bug fingerprint → 預跑 RCA 是必要 dispatch hygiene
- PG empirical（fix commit timestamp vs 16 row ts）是 single most decisive evidence，先 grep code + 後 PG 驗 timeline 是標準 RCA chain

**完整報告**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--p2_decision_features_double_prefix_bug_audit.md`

---

## P1-MA-CROSSOVER-DUPLICATE-INTENT root cause audit（2026-05-10）

**觸發**：Sprint N+1 W5 ticket — W6 baseline 揭露 ma_crossover INXUSDT live_demo 6.87h 內 duplicate_position guard reject 2331 次（其中 11:34 一分鐘 burst 2319 次，~50/sec），audit phase 找 root cause。

**Root cause（HIGH confidence）= cross-strategy position state 盲區**：
- ma_crossover 用 `self.positions: HashMap<String, bool>` 追蹤**自己策略**的倉位（strategy_impl.rs:140）
- router gate 1.5 用 `paper_state.get_position(&intent.symbol)` 比對 **symbol-level（不分 strategy）** dedup（router.rs:228-241）
- 兩個獨立 source of truth：strategy 內部 cache vs paper_state singleton；strategy 看不見其他策略開的倉
- on_rejection rollback（strategy_impl.rs:44-65）把 strategy.positions 還原到 prev_position（None），形成 infinite hot loop

**Smoking gun SQL 證據**：
- `trading.fills` INXUSDT 7d 內**只有 grid_trading 真實成交**（11 fills，11:29 SHORT 1810 → 11:39 close）；ma_crossover **0 fills**
- `trading.risk_verdicts` 11:34:00 burst 2319 次 → 11:35:00 12 次 → 立即停（not 高頻 cross，是 hot loop）
- `market.klines` INXUSDT 4h 1m close-to-close diff ±5-400bps，物理上不可能 50/sec cross

**Hypothesis verdict**：
- **A 變體 = CONFIRMED**（cross-strategy 不 dedup，非單策略每 tick 不 dedup）
- B（pyramiding by-design）= REJECTED（strategy 設計是 1 leg；router gate 1.5 沒 pyramiding awareness 是 architectural gap）
- C（INXUSDT 高 vol）= REJECTED（vol 正常）
- D（timing race）= REJECTED（grid 開倉 11:29 vs reject burst 11:34，5 min gap，不是 race）

**Fix scope 建議（D+3-5 W5 IMPL）**：
- **Option A 推薦**：strategy.on_tick 進 entry path 前查 paper_state.get_position；TickContext 加 read-only position handle；副作用 = 5 策略 on_tick signature 全動 → PA 統一審
- **Option B 應急**：on_rejection 識別 "duplicate_position" reason 後解析寫 strategy.positions（補丁，依賴 reason 字串契約）
- Option C（observability only）非治本

**Risk if not fix**：
- HIGH: 真 live 下 hot loop + lease cancel 浪費 SM-02 throughput
- MEDIUM: demo/live_demo audit pollute（[40] avg_net + W-AUDIT-4b-M3 negative label）
- HIGH (architectural): single-strategy assumption vs multi-strategy reality 不對齊；DOC-01 §16 組合級風險未來必修

**Systemic 風險**：bb_breakout / bb_reversion 同樣設計（self.positions 不查 paper_state）— W6 沒看到只是 signal 沒對齊；W5 IMPL phase 同 phase 開 P2 ticket audit 全策略。

**核心教訓**：strategy 內部 state machine 跟 paper_state 是兩個 SoT 是 architectural debt；2026-04-26 G2-03 ma_crossover SL/TP RFC 當時也指出 separation of concerns 邊界；本案是同 architectural gap 的不同表現面。

**E2 重點審查 3 點**：
1. TickContext signature 變動是否 break 4 其他策略 on_tick borrow 對齊
2. on_rejection rollback 邏輯改前 audit RC-04 spec（cooldown clear 副作用）
3. paper_state.get_position() 在 strategy on_tick 是否違反 borrow checker（已被 step_4_5_dispatch.rs 同層 borrow）

**報告**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--p1_ma_crossover_duplicate_intent_audit.md`

---

## Sprint N+0 sign-off invariant 17 closure 4 governance docs land（2026-05-10）

**觸發**：Operator 拍板 Sprint N+0 sign-off invariant 17 closure-blocking action — 起草 ADR-0021 (strategist cap)、ARCH-04 (graduated canary 5-stage)、AMD-2026-05-09-03 (invariant 5 wording)、AMD-2026-05-09-03 配套 (TOML drift) 4 governance docs。

**Action 採納**：
1. **ADR 編號衝突**：原任務指定 ADR-0021 = strategist cap，但 ADR-0021 已被 alpha-source-architecture-upgrade 占用（2026-05-09 land）；改為 **ADR-0022** strategist-cap-wide-parameter-adjustment-skill。Push back 採納：ADR 編號漂移是 multi-session drift 的具體實例（見 R-5 Push Back 5 + W-AUDIT-1 sync issue）。
2. **AMD 編號**：AMD-2026-05-09-03 actual 已是 graduated-canary-default（land 在 governance_dev/amendments/）；invariant 5 wording 改為 **AMD-2026-05-10-03**；TOML drift fix 改為 **AMD-2026-05-10-04**（2026-05-10 series）。docs/README.md line 170-171 兩條 phantom AMD-03/04 entry（標 strategist_wide_adjustment_skill 和 demo_promotion_evidence_push 為 AMD-03/04，但實際檔不存在）已修正。
3. **ARCH-04**：放在 architecture/（之前無 ARCH-XX 系列檔；ARCH-02/03 是 README 標的 alias 而非檔名）；新建 `2026-05-10--ARCH-04-graduated-canary-5-stage.md` 含完整 component diagram、stage transition 表、boundary 4 範圍、IMPL wave 對應、failure fallback。

**核心設計決策（4 docs 通識）**：
- **freedom-not-gate**（ADR-0022）：30%→50% 是 Strategist LLM payload skill 升級，不是風控 ceiling 放鬆；雙 zone 教學 (normal 0-30% / wide_skill 30-50%) + ledger + monthly Guardian review；對齊 §二 原則 11
- **graduated canary 5-stage**（ARCH-04）：Stage 0/1/2/3/4 + cohort scope；DOC-08 §12 / SM-04 ladder / Live 5-gate / §二 16 原則 4 範圍仍硬不變；rollback 永遠回 Stage 0
- **invariant 5 wording**（AMD-03）：option A 對齊 N+0 actual M1→M2→M3 IMPL；invariant 5b N+1 預告 feature_baselines→drift_events→scorer→3 advisor
- **TOML drift B-later**（AMD-04）：Sprint N+0 守 Stage 0 baseline；Sprint N+1 W3 cohort 拍板時同 commit atomic patch 4 欄位（shadow_mode/canary_stage/cohort/stage_entered_at_ms）+ W-AUDIT-9 T7 regression + W-AUDIT-3b runtime smoke pre-launch

**commit + push status**：
- 本地 commit `75b6e5f2` 已 land main（5 files / 1189 insertions / 3 deletions）
- `git push origin main` 被 permission rule 阻擋（main = default branch protected）；需 operator 手動執行 `cd srv && git push origin main` 或拍板開 feature branch + PR
- 4 docs untracked → staged 用 `git add` 個別檔；commit 用 `--only` 隔絕 BB WIP（race-safe per `feedback_git_commit_only_for_metadoc.md`）

**未動的檔**（per dispatch 守則「不動 TODO.md / CLAUDE.md」）：
- TODO.md v19 §5.3 invariant 17 wording 不動（仍 reference ADR-0021 — 需 PM commit 時順手修正為 ADR-0022 或加 cross-ref note）
- CLAUDE.md §四 / §五 不動（dispatch 寫「如需」；本次認定不需 — ADR-0022 + ARCH-04 + AMD-03/04 互引足夠 + docs/README.md index 完整覆蓋；CLAUDE.md §三 W-AUDIT-9 IMPL land 後同 commit 加 healthcheck `[58]` 時順手 cross-ref ARCH-04 即可）

**E2 重點審查 3 點**（PA 標）：
1. ADR-0022 §配套機制 V### migration `agent.strategist_wide_skill_invocations` schema 是 W-AUDIT-7 IMPL land 時拍板，現在只是 spec；E2 不應 reject「未 IMPL」
2. ARCH-04 §3.3 `shadow_mode_provider` exception path fail-closed Stage 0 invariant（不是 Stage 1）— 是雞蛋死循環防線，break 即 W-A 復活；W-AUDIT-9 T3 IMPL 必逐字實踐
3. AMD-04 §2.4 W-AUDIT-3b runtime smoke pre-launch — Stage 1 launch 必先 ssh trade-core run + engine restart + log evidence；不可只跑 Mac mock

**Sprint N+0 sign-off 後續配對動作**（PM 接手）：
- 通知 PM commit 已 land + 通知 push origin main 阻擋（operator 手動 push）
- TODO §5.3 invariant 17 wording 補正：「ADR-0021」→「ADR-0022」（或加註：「ADR-0022 完成 ADR-0021 占用後重編號」）
- 對 22 invariant 全 PASS 後 PM 可拍板 Sprint N+0 sign-off

---

## ADR-0021 升 Accepted + R-2..R-5 IMPL Spec 拆分（2026-05-09 後續）

**觸發**：Operator 拍板 ADR-0021 從 Proposed → Accepted（中文「ADR 0021 可以」），同 batch 要求拆 R-2..R-5 IMPL spec 為獨立可派 E1 文件。

**Wave 命名 schema 三套並存問題**：
- redesign report 用 R-1..R-5 amendment 級
- PA fix plan v2 §5 表用 W-AUDIT-8a/8e/8f/8g + W-ARCH-3 schema
- TODO.md v18 用 W-AUDIT-8a/8b/8c/8d/8e/8f schema
- PM 任務指定 b/c/d/e 對應 R-2/3/4/5

**處置**：本次拆 spec 用 PM 任務指定命名為 SoT（W-AUDIT-8b/8c/8d/8e 對應 R-2/3/4/5），dispatch plan §0 明確標示三套對應關係，TODO.md v18 dispatch table 應在 PM Sign-off 時 alignment。教訓：跨會話 wave 編號漂移是治理 drift 的具體實例（見 R-5 Push Back 5）；本來應該在 ADR-0021 land 時鎖死 wave 編號。

**Push Back 修正採納情況**：
- Push Back 1（Strategy Interface 偏差降一檔）— **部分推翻**（4-agent consensus + 22 fail-closed defaults dead loop math 證明 R-1 architectural 級正確），但 R-2 仍接受「Strategist 不越權」修正
- Push Back 2（Strategist 合 spec，責任在 Analyst）— **完全採納**：W-AUDIT-8b R-2 不 reframe Strategist 為「Alpha Source Orchestrator 唯一職責」，是擴展加 propose 通道；`_REGIME_STRATEGY_PREFERENCES` 漸進升 Bayesian update 而非 hard replace
- Push Back 3（Analyst L2-L5 IMPL 獨立於 ADR-0020）— **完全採納**：W-AUDIT-8c R-3 設計明確 L0+L1 跑 95% workload，Layer 2 manual 維持 ADR-0020 invariant
- Push Back 4（W-AUDIT-4b 必先於 R-3）— **完全採納**：W-AUDIT-8c R-3 §5.1 把 W-AUDIT-4b 標 hard prerequisite
- Push Back 5（Spec-Runtime drift 真正 Root Cause 5）— **完全採納**：W-AUDIT-8e R-5 設計 CI gate + Module Lifecycle SM 替代原「5-Agent skeleton without soul」結論

**Critical path estimate**：
- 整 Track A R-1..R-5 IMPL 估 ~122 person-day（spec 級對齊各 wave §3 表）
- ~11 sprint 樂觀 / 11-13 sprint 中位（22-26 weeks）
- R-1 Phase A → R-2 開（Phase A 完即開）；R-3 等 W-AUDIT-4b；R-4 等 LG-X 1-5 baseline + R-3
- R-5 全並行不阻塞，可 Sprint N+0 即啟動

**16-tab GUI 擴展接受**：
- 13 (current) → 14 (alpha_sources, R-2) → 15 (hypothesis_lab, R-3) → 16 (live_budgets, R-4)
- A3 v2 NEW-7/8 已建議 13→15，本 plan 累加到 16
- CLAUDE.md §五 13-tab dictionary 在每個 R-2/R-3/R-4 land 時同 commit 補

**衝突 / 並行確認**：
- R-1..R-5 與 Track W W-AUDIT-3b/4b/6/7/9 全無同檔案改動衝突
- W-AUDIT-3b 必先於 W-AUDIT-9 T3（per fix plan v2 PM push back 1），與 R-1..R-5 全無衝突
- W-AUDIT-9 graduated canary 是 R-1 alpha source candidate + R-4 per-alpha-source budget 的 deploy substrate（協同非衝突）
- W-AUDIT-1 doc sync wave 在 R-5 land 後 reframe 為 substrate-driven（per ADR-0021 §「Supersedes / impacts」）

**輸出物**（5 件 spec docs + 1 dispatch plan）：
- `docs/adr/0021-alpha-source-architecture-upgrade.md`（升 Accepted）
- `docs/execution_plan/2026-05-09--w_audit_8b_strategist_alpha_orchestrator_spec.md`（387 行）
- `docs/execution_plan/2026-05-09--w_audit_8c_hypothesis_pipeline_spec.md`（483 行）
- `docs/execution_plan/2026-05-09--w_audit_8d_per_alpha_source_promotion_gate_spec.md`（492 行）
- `docs/execution_plan/2026-05-09--w_audit_8e_spec_as_code_spec.md`（469 行）
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--track_a_dispatch_plan.md`（415 行）

教訓：
1. 收到「IMPL spec 拆分」任務時必先核 fix plan v2 / redesign report 內描述深度（< 200 行 IMPL guide 就拆）；此次 R-2..R-5 在 fix plan v2 §5 + redesign report Layer 4 合計 ~200 行但分散，按 PM 指示拆比 reference 安全（避免 IMPL 端再次 PA round-trip）。
2. ADR Accepted 升級不只改狀態欄；應同時補 Sign-off Date + Sign-off Mode + 中文引用，留 audit trail。
3. wave 編號 schema 漂移是 R-5 Spec-Runtime drift 的真實案例；ADR Accepted 時應同 commit 鎖死命名（本次留下 dispatch plan §0 alignment 表 + TODO.md update 後 sync）。

---

## 4-Agent Loss Audit 後 Full Dispatch Plan（2026-05-09）

**觸發**：Operator 拍板 4-agent loss audit 後 dispatch list（A 新策略 / B ML 三斷層 / C Promotion + Dormant / D Architectural Wave / E G3-08 enable）合計 ~140 person-day across 6 sprint。要求 sprint-by-sprint engineering plan + 11-item sign-off pre-flight checklist。

**Critical Path**：W-AUDIT-9 graduated canary + W-AUDIT-8a Phase A trait migration → first per-alpha-source supervised live ~12 weeks（6 sprint × 2 weeks）。Stage 1/2/3 觀察期 7d/14d/21d 不可壓縮，是 first supervised live milestone 的 hard limit。

**Sprint N+0 滿載 5/5 HOT**：
- E1-A: W-AUDIT-9 T1 (Rust schema)+T3+T6
- E1-B: W-AUDIT-9 T2 (V### migration)+T4
- E1-C: 8a Phase A trait 升級
- E1-D: B-M1+M2+M3 ML 三斷層
- E1-E: W-AUDIT-6 mid-ground 6 子項 + C-A6 + D-05-wire
- ops 並行: A2-followup G3-08 enable

**3 大跨 wave conflict 處理**：
1. **W-AUDIT-8a Phase A vs W-AUDIT-6 mid-ground 5 策略 file overlap**（bb_breakout/mod.rs / ma_crossover/strategy_impl.rs / bb_reversion/mod.rs）→ Sprint N+0 序列化（W1 mid-G + W2 Phase A），禁並行
2. **W-AUDIT-9 T3 stage-aware vs ExecutorAgent shadow_mode 接線** → exception path 必 fail-closed Stage 0（不是 Stage 1），E2 必查 invariant
3. **W-AUDIT-8a Phase B+C vs W-AUDIT-5 性能 wave 同 tick_pipeline/mod.rs** → 序列化或 Phase B+C 後 split

**W-AUDIT-6 mid-ground 派工**（保 6 / 砍 6）：
- 保: ma_crossover R:R audit / bb_breakout 5m sweep / bb_reversion 配 ma pair / Kelly tier config 化（4 risk_config*.toml + kelly_sizer.rs）/ funding_arb retire (done) / DSR/PBO wired (done)
- 砍: OU σ sweep / EWMA λ sweep / Kelly sub-fraction / fast_track threshold / per-strategy cost_gate / hardcoded magic patch
- E2 必 grep 6 砍項字面 0 命中

**W-AUDIT-8f (R-3) 含 W-AUDIT-4 併入 schema**：
- `learning.hypotheses` table state machine（DRAFT→REGISTERED→EXPERIMENTING→EVIDENCE_GATE→PROMOTED/REJECTED/EXPIRED）
- 6 dead schema 全加 `hypothesis_id` FK column（feature_baselines / drift_events / outcome_features / attribution_chain / calibration_sets / label_distributions）
- Decision Lease + ExecutionPlan + fills 全 propagate `originating_hypothesis_id`
- attribution chain rewire base on hypothesis_id → trivial join → ratio 從 0.5% 拉到 80%+ via Step 1 (B-M1/M2/M3) ~30% → Step 2 (C-A6) ~50% → Step 3 (W-AUDIT-8f IMPL) ~80%+

**11-Invariant Sign-off Checklist**：
- 結構 4 條（Sprint N+0 W-AUDIT-9 7 sub-task + 8a Phase A byte-diff + W-AUDIT-6 mid-G 6 保 0 動砍 + Stage 1 7d 觀察未提前升級）
- 安全 4 條（DOC-08 §12 / live boundary 5-gate / §二 16 原則 / shadow_mode_provider exception fail-closed Stage 0）
- 治理 3 條（manual_promote PG NOT NULL / SM-04 L3 hard FAIL / A 群 declared_alpha_sources 對齊）

**Push back 給 Operator**：Sprint N+0 5/5 HOT 任一 E1 故障 = 阻塞 critical path；建議預備 1 個 stand-by E1（6 並行 5 active + 1 stand-by）；如不接受須 operator 顯式 sign-off Sprint N+0 5/5 HOT capacity 風險。

**最早 supervised live**：~2026-08-01 ± 2 weeks（Sprint N+5 結束點，event-driven），不是 hard date。對應 milestone = first per-alpha-source budget slice，不是整 system live_reserved。

**報告**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_dispatch_engineering_plan.md`（689 行 / 51K chars / 中文+表為主）

---

## 全系統虧損架構級根因 + 真升級藍圖（2026-05-09）

**觸發**：Operator 拒絕「disable / 縮頻 / block bad symbols」笨辦法，要求對 5 策略 7d demo gross -26.44 USDT 做架構級根因分析；QC + MIT 並行從 alpha / ML 視角，本份從 system architect 視角。

**5 個結構性 root cause（不是 88 finding 列表）**：
1. **Strategy interface alpha-poverty** — `TickContext` 字段已含 funding_rate/index_price/OI/orderbook（`tick_pipeline/mod.rs:665-708`）但 IndicatorEngine + SignalEngine 中央化使「TA 路徑」是高速公路，funding skew / orderflow / liquidation cascade / cross-asset basis 等都是策略自己 buffer 的二等公民。5 策略全 OHLCV-driven 是必然輸出。
2. **Strategist scope 是「調參器」非「策略發現器」** — `_REGIME_STRATEGY_PREFERENCES` 4×5 hardcoded（`strategist_agent.py:128-134`）+ `max_param_delta_pct` 30→50 微調，沒有 alpha-discovery 路徑。EX-06 V1 寫「自主孵化策略」但代碼層 0 IMPL。
3. **Analyst L2-L5 進化階梯 100% dormant + Layer 2 ADR-0020 manual-only** — alpha discovery loop 是 spec 但 IMPL 0%。attribution_chain_ok 0.5% 不是 ML bug，是「沒有 hypothesis 來歸因」的必然。
4. **風控側 forcing function 完備 vs alpha 側放羊** — risk 有 5-step state machine + 4 TOML + Guardian veto + Cost Gate + StopManager，alpha 只有「Strategist 自由發揮」+ Ollama 提示詞。
5. **5-Agent 是合法骨架但靈魂沒裝** — Scout / Strategist / Guardian / Analyst / Executor 拆分職責正確，但運行時 4 個是空殼（Scout IntelObject 主要 logging / Strategist alpha-discovery 缺 / Analyst L2-L5 dormant / Layer 2 manual-only）。不是 over-engineered，是 under-implemented over-spec。

**88 finding 公因式聚類**（2026-05-09 verification v2 後）：
- **Cluster A 策略 alpha 貧乏 ~25-30 findings**（包含 5 策略 verdict / DSR/PBO / Kelly / Donchian leak / VaR/CVaR）：88 patch 修不到根
- **Cluster B 學習 loop 死 ~15-20 findings**（attribution_chain / feature_baselines / 5 ML 腳本 / Layer 2 / ContextDistiller）：部分修能解，但無頂層架構支撐
- **Cluster C 治理 drift ~12-15**（shadow_mode / lease flag stale / spec-runtime 漂移）：v2 已修部分，仍需 forcing function
- **Cluster D dead weight ~10-15**（24 表 0 row / 909MB damaged / openclaw_core 9 模組 sunset）
- **Cluster E doc churn ~10-15**（CLAUDE.md / docs/README / SCRIPT_INDEX / SPEC_REGISTER / ADR）
- **Cluster F 性能/平台 ~8-10**：v2 部分 closed
- **Cluster G security edge ~5-8**：v2 部分 closed

**Architectural Redesign Sketch**：
- **R-1（Tier-1, 3-4 sprint）**：升級 Strategy Interface 為 AlphaSurface Bundle + AlphaSourceTag declared dependency；Strategy Registry 拒絕全 [TA1m] 新提案
- **R-2（Tier-1, 2-3 sprint）**：Strategist 重定義為 Alpha Source Orchestrator + AlphaSourceRegistry；移除 4×5 hardcoded；Layer 2 解封路徑 = alpha-source proposal（vs trade signal）
- **R-3（Tier-1, 2-3 sprint）**：Hypothesis Pipeline as first-class governance object（與 Decision Lease 同層級）；Decision Lease + ExecutionPlan + fills propagate `originating_hypothesis_id`；attribution chain rewire base on hypothesis_id
- **R-4（Tier-2, 2 sprint）**：Per-alpha-source Live Promotion Gate（取代 LG-2/3/4/5 整 system 線性放權）；LiveBudget(alpha_source_id, slice) 動態 risk budget
- **R-5（Tier-2, 1-2 sprint）**：Spec-as-Code + Module Lifecycle SM（自動化 doc plane）

**W-AUDIT-1..7 vs R-1..R-5**：W-AUDIT-2/-5 純維護必做；W-AUDIT-3 是 R-4 baseline 必做；W-AUDIT-4 應併入 R-3；W-AUDIT-7 Layer 2 部分換成 R-2；**W-AUDIT-6 戰略 ROI 低 — 5 既存 TA 策略修完仍會 gross negative 高機率，建議只做 minimum**（funding_arb 退役 + DSR/PBO + Kelly config 化），不重寫 ma / bb，把帶寬留給 R-1/R-2/R-3。

**核心 push back（給 Operator）**：
- 「先修完 88 再說架構」是錯的順序 — 它讓系統繼續精煉一條結構性無回報路徑
- 5 策略不是「需要更好參數」，是站在已無 alpha 的 territory（5 個 TA 策略其實是 1 個 TA alpha 上的 5 種包裝）
- CLAUDE.md §一「Agent 自主完成交易決策」+ 原則 #11 與代碼 scope（Agent 實際自主範圍 = [P2 參數 ± 50%]）強烈不一致，**架構在生產 Agent 微調權，不是 Agent 自主**
- §五「KlineManager → IndicatorEngine → SignalEngine」措辭強化 TA-default mental model；建議改寫為「市場數據 → AlphaSurface (kline + funding + basis + orderflow + xasset) → Strategy → Orchestrator」

**最早 supervised live 重定義**：不是「整 system live_reserved」，而是「first alpha source 拿到 budget slice」；6-8 sprint。同數量級 vs 88 finding patch，但長期收斂可能性提升（不是修一條已知必虧路徑）。

**報告**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md`

---

## REF-20 Sprint 2 Track E — Decision Lease retrofit AMD-2026-05-02-01（2026-05-03）

**Sprint scope：** Sprint 1 close 後接續開工；解 18 Live Blocker #5（Decision Lease Rust 熱路徑 0 觸發）+ #6（agent 三表 all-time 0 row）；對應 amendment `docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md`。

**4-task DAG（最大並行 3 E1，總 3 day E1 work）：**
- **E-1（critical path / 串行）Rust facade** `governance_core.rs` 加 `acquire_lease/release_lease/get_lease_by_id`；`pub lease: DecisionLeaseSm` 改為 `pub lease: parking_lot::Mutex<DecisionLeaseSm>`（interior mutability，process_with_features `&self` 通過 `lock()` 修改）；新增 `lease_id_to_idx: HashMap<String, usize>` reverse lookup（解決 Rust idx vs Python lease_id impedance mismatch）；新增 `lease_transition_tx: Option<mpsc::Sender<LeaseTransitionMsg>>` audit emit channel；既有 5 處 `&mut self` cascade 需用 `lock()` 重寫；28 處 Production test fixture 同步重寫**+0.3 day 緩衝**（push back #4）；總 1.1 day。
- **E-2（依賴 E-1）Rust router gate** `intent_processor/router.rs` `process_with_features()` + `process_gates_only_with_features()` Gate 1（is_authorized）後加 Gate 1.4（lease）；`if profile.requires_lease() { acquire_lease()? else fail-closed reject }`；fill 完成後 `release_lease(Consumed)` / 拒絕 `release_lease(Failed)`；`IntentResult/ExchangeGateResult` 加 `pub lease_id: Option<String>` 由 `step_4_5_dispatch.rs` 寫 `replay.simulated_fills.decision_lease_id`（V050 placeholder column 終於有 caller）；**feature flag `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0` 默認 OFF 灰度啟動**（push back #5）；0.6 day。
- **E-3（並行 E-2）Python IPC bridge** `governance_hub.py:693-783` 改 IPC 轉呼 Rust（保簽名 backward-compat）；shadow caller short-circuit（push back #2 — shadow=true 直接回 `"shadow_lease:no_op_<intent_id>"` 不打 IPC 不寫 lease_transitions 避免 §4 #2 假綠）；dual-write 4 週 namespace prefix `py_*` / `rs_*`；0.6 day。
- **E-4（並行 E-2/E-3）V054 schema + audit writer** 新表 `learning.lease_transitions`（amendment §4 AC-1 觀察點，hypertable + 3 索引）；`governance.audit_log` event_type CHECK 13 → 20（加 7 lease event types）；`lease_transition_writer.rs` 新 actor 訂閱 lease_transition_tx 寫 PG；**agent 三表 writer 加 sampling**（push back #3 推薦 Option A：LOW 1% / NORMAL 10% / HIGH+CRITICAL 100%；hypertable 即使 1KB payload × 4.3-8.6M row/day 撐不住 4-8GB PG memory）；TOML config `agent_audit_writer.sampling_*`；fail-soft（DB error 不阻塞 send）；1.0 day。

**5 個關鍵 push back：**
1. **HIGH**：W8 P6 typed-confirm handoff（session 級 EarnedTrust ladder）vs Decision Lease（per-intent 30s 短期授權）絕對不可混；Validation profile 必短路 `LeaseId::Bypass` 不打 SM；E2 必查 demo 路徑 0 觸發 lease_transitions row。
2. **HIGH**：ExecutorAgent shadow_mode_provider `lambda: True` fail-close default（CLAUDE.md §三 P1-FAKE-1）→ shadow path 仍會走 Python `acquire_lease()` IPC → Rust SM 真做 transition → 沒對應 release_lease → 卡 ACTIVE 直到 ExpiryGuardian 清。對策：Python caller-side shadow short-circuit + V054 audit writer 加 `engine_mode='shadow'` 過濾 + AC-1 query 加 `AND engine_mode != 'shadow'`。
3. **MEDIUM**：MessageBus DB sink 對 `agent.messages` 24h 4.3-8.6M row 寫入威脅；Linux PG 4-8GB shared_buffers 撐不住。Option A sampling（LOW 1%/NORMAL 10%/HIGH+CRITICAL 100%）為 PA 推薦；E2 必查 sampling logic + fail-soft + TOML config 不 hardcode。
4. **MEDIUM**：retrofit 後既有 28 處 `GovernanceProfile::Production` test fixture 集體 fail（沒 grant lease）；E-1 同 E1 task 重寫 fixture +0.3 day；E2 必查 fixture **不能用 LeaseId::Bypass 短路**（會掩蓋 router gate bug）。
5. **MEDIUM**：amendment §5.4 排程 ~2026-05-15 P0-EDGE-2 後派發 vs Sprint 2 直接接續啟動衝突。PA 立場：Sprint 2 直開 + feature flag 灰度（E-1/E-3/E-4 land + E-2 land 但 OFF）；2026-05-15 P0-EDGE-2 結論後 flip flag canary 24h；amendment §6 回退條件「IPC failure > 0.5%」變成 flag flip 第二次 commit 前的觀察條件。

**Rust SM impedance mismatch 解：** Python `_lease_sm` 用 `lease_id: str` 為 SM operation handle / Rust `DecisionLeaseSm` 用 `idx: usize`（Vec index）。Facade 維護 `HashMap<String, usize>` reverse lookup；對外 API 用 `lease_id: String`（與 Python 對等）；不動 lease.rs 既有 9 unit test。

**5 條 AC acceptance probe SQL** + **6 phase deploy chain（feature flag gradual rollout）** 全在報告。

**完成定義：**
- 設計報告 `2026-05-03--ref20_sprint2_track_e_decision_lease_retrofit_design.md` ✅
- AC-1~5 + 5 push back 全收 + Sprint 1 commits cross-impact map（V050 decision_lease_id 是 sprint 1 為 sprint 2 預留接口；V053 → V054 event_type 13→20）
- E2 重點審查 3 點：fixture 重寫不能 Bypass / Python IPC shadow short-circuit / agent.messages sampling
- 不寫業務碼 + 不 commit ✅

**接續節點：** PM Sign-off 設計後 → Task E-1 派發給 E1（單 E1 串行 1.1 day）→ E-1 facade signature land → Task E-2/E-3/E-4 三 E1 並行派發。最早 2026-05-04 啟動，~2026-05-07 全部 land；feature flag 觀察期至 2026-05-15+。

詳：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_sprint2_track_e_decision_lease_retrofit_design.md`

## REF-20 Sprint 1 partition design（2026-05-03）

**Sprint scope：** REF-20 8-agent cold audit NO-GO 後，4 並行 Track 解 19 P0 + 補 PA W1 自身 schema drift。

**Track 全景：**
- **Track D（schema 阻塞）**：V049 replay_experiments(22 col + EXCLUDE GIST) / V050 replay_simulated_fills(17 col + FK to V049) / V051 mlde_shadow_recommendations 補 replay_experiment_id + manifest_hash + 雙路 CHECK / V052 V045/V046 FK redirect ALTER ADD CONSTRAINT（**禁改 V045/V046 file** 避免再撞 P0 sqlx hash drift）。3 並行 + 1 串行 = 4 task / ~2.75 day E1 work。
- **Track A（spawn argv 修）**：Python `route_helpers.py:266-271 argv` 對齊 Rust `--manifest <path> --output-dir <path>`；移除 `--manifest-id <UUID> --run-id <UUID>` 直接 argv 傳遞；`run_id` 改藏在 manifest fixture JSON `serde(default) Option<String>`；spawn 後 `asyncio.sleep(1.5) + proc.poll()` 失敗 → UPDATE V045 status='failed' exit_code。1 task 跨 3 file（route_helpers.py + replay_routes.py + replay_runner.rs struct）。
- **Track B（Rust manifest verify）**：`replay_runner.rs:386-470 load_and_verify_manifest` 改 `verify` 用 manifest 自帶 `signature` + `manifest_hash` 為 expected（非重簽 tautology）；key.hex 缺改 hard error fail-closed；移除 `#[allow(dead_code)]`。1 task 純 Rust 1 檔。V042 SQL archive 是 Wave 6（不在 Sprint 1）。
- **Track C（Python 3 安全洞）**：（P0-2）`OPENCLAW_REPLAY_VERIFY_TEST_KEY` 加 `OPENCLAW_RELEASE_PROFILE=live` gate 強制清空 + boot guard；（P0-4）`os.kill(pid, SIGTERM)` 加 `psutil.Process(pid).cmdline()` 驗 `replay_runner` substring 防 PID reuse；（P0-5）IDOR 加 `WHERE actor_id = %s` filter（admin bypass）+ 路徑遍歷加 `is_relative_to(allowlist_root)` 驗。3 改點獨立區段同 E1 1 commit。

**依賴關鍵：** Track D 必先 land schema → A+B+C 三者並行（B 純 Rust 解耦，A 與 C 同檔 replay_routes.py 但區段不重疊）。最大並行 3 E1，Sprint 1 預估 3.5-4 day。

**5 個關鍵 push back：**
1. **HIGH**：V045 既有 row 對 V052 FK redirect 的 dangling 風險 — `manifest_id` UUID5 衍生但無對應 V049 row → ALTER ADD CONSTRAINT 直接 fail。對策 = T-D4 preflight LEFT JOIN 統計 + operator 決定 reconcile 或 archive。
2. **MEDIUM**：Track A 把 `run_id` 從 argv 移到 manifest JSON → manifest_id 與 V045 PK 一致性無 enforce。對策 = Rust replay_runner 啟動自驗 `manifest.run_id == output_dir.basename()`。
3. **MEDIUM**：Track B fail-closed 後 V042 land 前的「key.hex 必在 manifest 旁」是運維契約 not engineering 無 healthcheck 監測。對策 = Sprint 1 順手加 `check_replay_manifest_key_presence()`（WARN-only，已知過渡期）。
4. **MEDIUM**：Track C 假設 `_require_replay_admin` 已存在；E1 起手必 grep 驗，缺則加 task。
5. **HIGH**：5 V### file 必 Mac dev pytest（idempotency × 2 + Guard A/B/C 全 NOTICE PASS）→ Linux operator 才 deploy（CLAUDE.md §七 跨平台合規）。

**PA 自審：W1 派發 R20-P2a-T1+T3+T5 為 migration，IMPL 偷換成 fixture 沒 catch。** 根因：(1) reservation L47-48「P2b runner SQL fixture，不佔 migration 編號」用詞當時讀過去視為合法選項；(2) V045+V046 簽收時沒交叉檢查 V3 §4.1 22 column 是否在內。**未來防線：** V### reservation 從「fixture」回 migration 必 PA + PM 雙簽 + E2 加 spec-vs-SQL column count check。

**跨 Track 共同 helper 統籌：** `_table_present(cur, schema, table)` factory（取代 `_v045_table_present`）/ `_emit_audit_stub` 加 5 新 event_type → 同 commit 加 V053 migration extending V035 CHECK enum / `_verify_replay_runner_pid(pid)` 放 route_helpers.py / `_write_manifest_fixture(run_id, manifest_data, output_dir)` 同 sibling 寫 key.hex（dev only）。

詳：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_sprint1_partition_design.md`

## STRATEGY-WIRING-SPLIT P2（2026-04-28）

**結論**：`strategy_wiring.py` 1060 → **784 LOC**（≤800 進入合規），抽 2 sibling：
`strategy_wiring_h_state.py` 133 LOC（H State Invalidator G3-08 Phase 1C，純 leaf top-level）+
`strategy_wiring_scanner.py` 338 LOC（MarketScanner/AutoDeployer/ScoutWorker/scout_routes/Auto-Observation 5 子塊，函數 `wire_market_scanner_and_workers(deps)` 模式）。Pure refactor 0 production behavior change。

**Mac pytest**：143/143 PASS（6 critical wiring suites）+ 25 module-attr smoke 全綠。

**設計選擇**：
1. H state cluster 用 **top-level executable** 模式（無 deps，純 env 驅動），strategy_wiring.py `from .strategy_wiring_h_state import _H_STATE_INVALIDATOR` re-import 保 grep 穩定
2. Scanner cluster 用 **函數 + ScannerWiringResult dataclass** 模式（需 ORCHESTRATOR/KLINE/PAPER_ENGINE/SCOUT_AGENT/MESSAGE_BUS 注入避循環 import），strategy_wiring.py 在原 init 順序位置呼叫並 bind 回 module attribute（`MARKET_SCANNER = _scanner_result.market_scanner` 等）
3. 5-Agent ~440 LOC 塊**故意不抽** — init order 鼓互交織（cognitive_modulator / LOSSES-WIRING lambda / ExecutorConfigCache / 5 audit_callback wires），P2 scope 邊界「strategy_wiring.py only」嚴守

**保 grep 穩定鍵**：
- `app.strategy_wiring.MARKET_SCANNER` / `AUTO_DEPLOYER` 屬性查找不破（strategy_read_routes / strategy_write_routes `from ... import` + h_state_collectors `getattr(_sw, ...)` + tests `sys.modules` patch）
- `app.strategy_wiring._H_STATE_INVALIDATOR` 屬性 sys.modules 反射不破

**保不變量**：W1 cognitive ticking + G8-01-FUP-LOSSES-WIRING lambda（Analyst→Strategist callback）+ ExecutorConfigCache shadow_mode_provider + 5 audit_callback wires + TruthSourceRegistry inject + DEAD-PY-2 paths（PIPELINE_BRIDGE=None / Auto-observation no-op pass / DEMO_CONNECTOR=None）。

**CLAUDE.md §九 同步**：`_H_STATE_INVALIDATOR` row 467 wire site updated `strategy_wiring.py:535` → `strategy_wiring_h_state.py` + re-import 註；新增 `MARKET_SCANNER / AUTO_DEPLOYER / _SCOUT_WORKER` row 顯式登記（前為「12+」隱含覆蓋）。Wave E cost_edge_advisor_boot row 補登先例延續。

**教訓**：sibling-by-function-call 與 sibling-by-top-level-import 兩種 pattern 視 dependency 取捨 — 純 env/讀文件 leaf 用 top-level、需注入 singleton 用函數。Wave E + main_scanner_init + 本次 strategy_wiring split 三個案例累積形成 Python 端 sibling 拆分標準作業：1) leaf cluster 優先 2) caller surface (sys.modules / getattr / from-import) 全盤點 3) singleton bind-back 維持屬性 grep 4) §九 row 同步避 drift。

詳：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--strategy_wiring_split.md`

## MAIN-RS-PRE-EXISTING-CLEANUP P2（2026-04-28）

**結論**：main.rs 1210 → **1158 LOC**（§九 1200 hard cap 進入合規），新 sibling `main_scanner_init.rs`（170 LOC）抽出 Scanner D4 pre-init（config + registry + edge estimates + relay channel + tokio relay task spawn）。Pure refactor 0 production behavior change，cargo build 綠 + lib 2308/0 + cost_edge_advisor 11/0 + 2/0。Wave E `cost_edge_advisor_boot` split 後遺留的 governance ambiguity（E2 PB1 MED-1）解除。

**設計選擇**：5 候選中選 Scanner pre-init（67 LOC、最自包含、避開 cost_edge_advisor_boot scope）。Sibling 命名 `main_scanner_init.rs` 對齊既定 main_* sibling pattern（boot_tasks / pipelines / fanout / ws / watchdog / shutdown / instruments）。

**保留 grep stability**：`scanner_store` / `symbol_registry` / `scanner_edge_estimates` / `scanner_ws_tx` / `current_ws_client_tx` 五原變數名透過 destructure pattern 維持，下游 5 個 site 零改動。

**教訓**：`pub(crate) struct + pub(crate) fn` sibling pattern 對 main.rs 1200 cap 維護優於把工作擠回既有 sibling — Wave E 用 cost_edge_advisor_boot 已做對的事，本 P2 同 pattern 完成第二個 sibling。下次小改若再撞 cap，相同 pattern 可重複套（main_phase4_init / main_db_init 等候選仍在）。

詳：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--main_rs_pre_existing_cleanup.md`

## 架構狀態快照（2026-03-31）

### 關鍵模塊狀態
- `pipeline_bridge.py`：PipelineBridge 主管線，on_tick 同步，H0 Gate warn-only
- `governance_hub.py`：GovernanceHub 4 SM（SM-01/02/04/EX-04），RLock 可重入
- `multi_agent_framework.py`：MessageBus + 5 Agent 訂閱完整，Scout→Strategist bus.send 已有代碼
- `strategist_agent.py`：shadow=True（只記錄不產生 TradeIntent），Ollama 已注入
- `phase2_strategy_routes.py`：Strategist shadow=True 在 L155，可通過 directive 動態切換

### H1-H5 真實位置（重要）
- `ai_agents/bybit_thought_gate/` = 獨立腳本體系，從 JSON 讀寫，與 app 層完全無連接
- app 層的 H1-H5 功能分散在：
  - H1 雛形：`pipeline_bridge._check_edge_filter()`（advisory-only）
  - H2：`layer2_cost_tracker.check_daily_budget()`
  - H3：`strategist_agent._ai_evaluate()` + `layer2_engine._l1_triage()`
  - H4：Ollama timeout + max_retries=0
  - H5：`layer2_cost_tracker.record_claude_cost()`（無 Ollama tracking）

### OpenClaw 定位決定（2026-03-31）
- OpenClaw = HTTP 反向代理（/openclaw/{path} → 18789）
- **決定**：Wave 5 不把 OpenClaw 改為通信總線，而是作為審計 sidecar
- MessageBus 保留同進程通信主通道
- OpenClaw 接入方式：MessageBus.audit_callback → async fire-and-forget 推送

## 架構教訓

### asyncio/threading 混用邊界（高頻問題）
- FastAPI async 路由 → event loop，不能直接調用 threading.Lock 的阻塞操作
- `pipeline_bridge.on_tick()` 是同步線程，可以用 threading.Lock
- `layer2_engine.run_session()` 是 async，用 asyncio.Lock（Wave 3b 已修）
- **記住**：每次設計方案時，先確認調用者是 async 還是 sync

### Shadow→Active 切換風險
- Strategist shadow=False 後，TradeIntent 量可能爆炸（650 symbols × Scout 情報頻率）
- **記住**：必須確認 `max_pending_intents = 50` 上限真實生效，且 H0 Gate 從 warn-only 改 blocking

### API Schema 變更風險
- 改 governance endpoint 的 response field name = 高風險（前端 JS 讀取失敗）
- GUI 術語友好化應只改顯示文字，不改 API schema

## Wave 5 架構評估結論（2026-03-31 完成後）

### 關鍵新發現：雙執行路徑並存
- **路徑 A（推薦）**：StrategistAgent → MessageBus → APPROVED_INTENT → ExecutorAgent.acquire_lease() → submit_order() — 完整實施 Principle 3
- **路徑 B（遺留）**：pipeline_bridge._process_pending_intents() → Guardian → submit_order() 直接調用 — **缺少 acquire_lease**
- **影響**：Principle 3 在路徑 B 未完整實施；demo_only 模式下 PaperTradingEngine GovernanceHub gate 兜底，影響有限
- **修復**：TD-1 = pipeline_bridge 注入 governance_hub，Guardian APPROVED 後加 acquire_lease（2h）

### Wave 5 完成狀態
- H0 Gate：blocking 模式已啟用（on_tick 中 continue 替換 warn-only）
- H1-H5：全部接入 StrategistAgent，fail-closed，無 allow-all
- ScoutWorker：daemon thread，30min 定期掃描，produce_intel → MessageBus → StrategistAgent
- ExecutorAgent：訂閱 APPROVED_INTENT，acquire_lease → submit_order 路徑閉合
- 測試：2912 passed（24 pre-existing failures + 17 errors）

### 架構健康度評分：7.2/10
- 治理閉環 8.5 / AI 治理 8.0 / Scout 鏈路 8.5 / 執行路徑一致性 5.5 / 技術債 6.0

### 遺留技術債優先級
- TD-1 (P1)：pipeline_bridge 缺 acquire_lease（pipeline_bridge.py:701）
- TD-2 (P2)：StrategistAgent 雙路徑語義模糊（collect vs bus.send）
- TD-3 (P2)：H5 cost_tracker except Exception: pass 無 logger（strategist_agent.py:485）
- TD-4 (P2)：_h1_cooldown 無容量上限（strategist_agent.py）

### 下一步派發建議摘要
Wave 6 第一批（最大並行）：
- E1-Alpha：TD-1 pipeline_bridge acquire_lease（2h）
- E1-Beta：Batch 1B Cooldown 聯動（1.5h）
- E1a：GUI 術語友好化第一批（3h）

## 報告索引

| 日期 | 報告類型 | 文件位置 |
|------|---------|---------|
| 2026-03-31 | Wave 5 B 方案技術設計 | workspace/reports/2026-03-31--wave5_tech_design.md |
| 2026-03-31 | Phase 1 Batch 1B 可行性評估 | workspace/reports/2026-03-31--batch1b_feasibility.md |
| 2026-03-31 | Wave 5 完成後全鏈路評估（本報告）| workspace/reports/2026-03-31--wave5_architecture_review.md |

## 2026-04-24 PA TODO Audit 發現

### 關鍵架構發現（本次 audit）

1. **ConfigStore + IPC hot-reload 基礎完整** — ArcSwap + Mutex + TOML persist 運作；28 字段 (legacy 21 + EDGE-DIAG-1-FUP-IPC 7) 已支持。唯缺 FUP-SHADOW-ENABLED-IPC (1d 補丁) → Phase 2 Combine shadow flip 無需 rebuild。

2. **ExecutorAgent shadow→live 無 GUI 切換路徑** — `_shadow_mode=true` 硬編碼 (line 482)；預設安全但過渡受限。建議新增 ConfigStore<ExecutorConfig> + IPC endpoint (3-4d)。

3. **Path A/B 互斥機制鬆散** — Path A 代碼完整，Path B 仍存活但缺 acquire_lease；demo_only 時 PaperTradingEngine sandbox 兜底，live 時風險提升。設計上無致命缺陷，ExecutorAgent shadow=true 預設降事件發生機率。

4. **Migration Guard 強化** — V023/V021 雙 DO block Guard A/B RAISE EXCEPTION ✅，符合 CLAUDE.md §七新規則 (2026-04-24 強制)。past silent-noop 問題得解。

5. **Combine/Registry 骨架風險降低** — INFRA-PREBUILD-1 Part A/B 完整落地；Phase 1a dormant、Phase 4 延後，但無架構阻塞。

### Leverage Points TOP 3 (PA 視角)

| # | Leverage | 工作量 | ROI | 優先級 |
|---|----------|--------|-----|--------|
| 1 | FUP-SHADOW-ENABLED-IPC (1 字段補丁) | 1d | Phase 2 無需 rebuild (~3min → <60s) | P2 |
| 2 | ExecutorAgent ConfigStore + GUI toggle | 3-4d | Path A→Live 過渡敏捷 + Principle 3 完整 | P1 |
| 3 | Combine shadow 監控自動化 (健檢+cron) | 2d | 量化 Track P vs L 一致性 + Phase 3 前置條件 | P2 |

### 架構健康度溫度計

- **確定性路徑** (Rust + governance): 8.5/10 — SM-01/04/02 完整、H0 Gate blocking ✅
- **AI 治理接線** (H1-H5 + 5-Agent): 7.5/10 — 實裝完、Conductor stub、ExecutorAgent toggle 缺 GUI
- **IPC 邊界清晰度**: 8.0/10 — 28 字段、FUP-SHADOW 待補
- **交易路徑一致性**: 6.5/10 — Path A/B 互斥鬆散、lease 債標示、demo 兜底
- **技術債**: 6.0/10 — P1-6/7/10/11/19、無架構阻塞
- **整體評分**: **7.2/10** (與 2026-03-31 評估同級)

### 遺留待解項

- **EDGE-DIAG-1 Phase 3 auto-gate 前置** — 等 clean window ≥200 rows (ETA ~2026-05-01)
- **P1-10 PostOnly fee 驗證** — 下 2026-04-28 判決
- **Model Registry canary auto-promote** — Phase 4 第二階段待實施
- **Learning pipeline 下游消費** — 21 schema 表無 consumer，experiment_ledger 結構異常

### 報告路徑

📄 `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit.md`

- 10 個主題（架構完整性、Path A/B 設計、Leverage 3+、架構債分類、依賴圖、TODO 重組、技術建議、CLAUDE 一致性、風險熱點、PA 最終判決）
- ~3400 字、詳細文件指針與備查表
- 簽核路由：PM → 下一輪 10-agent 審議

---

## 2026-04-24 PA TODO 完整提案盤點完成

### 關鍵工作

執行**完整的 PA 10 份歷史報告盤點 + 當前 TODO.md + FIX-PLAN 對比分析**，產出：

**輸出**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--todo_complete_proposal.md`（333 行）

### 核心發現

1. **未入當前 TODO 的潛在遺漏項**：~5-8 條
   - DI-UNIFY-01：governance_routes DI 模式統一（High/Mid 級）
   - STARTUP-VERIFY-01：依賴完整性 fail-closed check（High 級）
   - PIPELINE-TIMING-WINDOW-01：注入時間窗口防衛（Mid 級）
   - COST-GATE-NEW-01：cost_gate.py 實裝（Mid 級）
   - 5 個 RFC + 文檔 spec（Etc 級）

2. **完整提案表**：~80 條 TODO items
   - High（架構/安全/合規）：19 項
   - Mid（技術債/可讀性）：28 項
   - Low（文檔/QoL）：15 項
   - Etc（RFC/規範）：10 項
   - Backlog：~8 項

3. **架構債分類**（PA 視角）
   - 架構債：7 項（Path A/B、DI、ExecutorAgent toggle、risk_manager 拆分、MessageBus 路徑、startup check、timing window）
   - 功能債：8 項（TruthRegistry 注入/持久化、BacktestEngine 數據、MessageBus 路徑、detail=str、FIX-26、PostOnly、auto-revoke）
   - 參數債：5 項（scheduler、PostOnly、hard_cap、shadow_enabled、FUP-IPC）
   - 文檔債：6 項（CLAUDE.md 同步、Guard retrofit、healthcheck、model canary playbook 等）

4. **3 大 Leverage Points**（確認強化）
   1. FUP-SHADOW-ENABLED-IPC（1d，Phase 2 無 rebuild）
   2. ExecutorAgent ConfigStore + IPC toggle（3-4d，原則 #11 完整）
   3. event_consumer fn 拆分（3-4d，8 檔 refactor 解阻）

5. **當前 TODO.md 對比**
   - ✅ Wave 1-4 + G1-G6 + P0/P1/P2/P3/P4 主軸已覆蓋
   - ✅ healthcheck + 被動等待規則已納入
   - 🆕 新增強調項：DI 統一、startup verify、文檔 RFC 清單明確化

### 方法論

PA 10 份報告盤點流程（可重複使用）：
1. 逐份讀取歷史報告，提取架構發現 + 技術債 + 遺漏項
2. 對比當前 TODO.md + FIX-PLAN，去重+分優先級
3. 按「架構級 vs 功能級」、「High/Mid/Low/Etc」分類
4. 提出新增遺漏項 + 強化 Leverage points + 關鍵決策點
5. 輸出完整提案表（含工時、前置、並行）

### 下次行動

- 【提案交付】：本報告給 PM 審核 + 後續整合核實會
- 【Memory 同步】：記錄新遺漏項 + 10 份報告盤點方法論
- 【Wave 1 啟動】：G1-01~05 + G2-01~05 + G6-01~04 的實施時序確認

---

## 2026-04-26 Wave 3 派發前架構研究

### 觸發

PM 啟動 Wave 3（W20-W23 · 5/22→6/12）派發規劃，要求 4 問題答覆：G8-01 RFC / G8-02 parity 設計 / G8-04 DAG 線性化 ROI / 撞檔風險矩陣。

### 報告路徑

`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--wave3_dispatch_research.md`

### 3 大關鍵發現

1. **G8-01 範圍 scope drift 風險**：PM profile.md 提及「認知自適應三模組」，但代碼層只 CognitiveModulator（193 LOC）存在，OpportunityTracker / DreamEngine **代碼不存在**（grep 0 命中）。建議完成標準從「80+ coverage」改為「**CognitiveModulator ≥85% line cov + 注入點 integration 綠**」，後二者標 deferred。**派發前必說明**避免 E1 撞 NotImplementedError。

2. **G8-02 decision points 縮窄**：scope 應限 RiskConfig.executor 三欄（shadow_mode / per_symbol_position_cap / max_position_pct），不含 cost_gate / 5-gate auth / Reconciler 降級 / Hurst regime（屬其他 Config 子切片）。建議 70 case golden + replay 混合，case-level binary agree ≥95%（70 中 ≥67）。

3. **G8-04 ROI 太低**：1955 LOC healthcheck 平鋪可讀；隱性依賴只 2 層深 [1] → ratio group；無假 PASS 事件觸發。**降級 backlog**，待真 pain 出現再啟，**Wave 3 完成標準應移除**。

### 撞檔風險矩陣

| 項目 | Isolation | 衝突風險 |
|---|---|---|
| G2-06 bb_breakout calibrate | **必 isolation** | 與 G7-03-Phase-B-FUP-grid（grid 5 檔 WIP）潛在撞區 |
| G8-01 認知 e2e | 主樹 | 純新測試檔，禁改 strategist_agent production |
| G8-02 parity | 主樹 | 純新測試檔，0 Rust diff |
| G8-04 DAG | n/a | 降級 backlog |

### W20 派發建議

第一批並行：**G8-01 + G8-02 主樹同步**（E4 + QA / E2 review / 1-3d）。G2-06 等 healthcheck [12] FAIL ≥7d 才啟（**isolation**）。Wave 3 isolation worktree ≤2 不會撞 §35-39 上限。

### 沒做的事（E1/E2 領域）

- 沒設計實作代碼 / cargo test / pytest
- 沒審查現有 commit
- 純架構決策建議

### 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|------|---------|---------|
| 2026-04-26 | Wave 3 派發前架構研究 | workspace/reports/2026-04-26--wave3_dispatch_research.md |

---

## 2026-04-26 G2-06 bb_breakout disposal RFC

### 觸發

PM Wave 3 第二波派發 G2-06：bb_breakout 7d entries=0（healthcheck [12] FAIL）+ FIX-26-DEADLOCK-1 已 3 次 rebuild 排除 deadlock 嫌疑後，根因 = 1m bandwidth mis-scale CONFIRMED。需二選一決策：disable 永久（C） vs 升 5m + recalibrate（B）。

### 報告路徑

`workspace/reports/2026-04-26--g2_06_bb_breakout_disposal_rfc.md`

### 核心發現

1. **架構級檢查**：5m WS 訂閱 + KlineManager 5m buffer **已就緒**（`multi_interval_topics::DEFAULT_INTERVALS` 含 Min5、`klines.rs:31 DEFAULT_TIMEFRAMES` 含 5m）— 升 5m 不需動 WS 層
2. **真正 5m 改動瓶頸**：`step_1_2_klines_indicators.rs:62` (黑天鵝 1m) + `step_3_signals.rs:108` (`signal_engine.evaluate(sym, "1m", ...)` 寫死) + `on_tick_helpers.rs:299 const TIMEFRAME` + `bb_breakout/mod.rs` squeeze_expiry 換算 — 5 檔 Rust 改動，bit-identical 保證消失
3. **disable 路徑成熟**：`registry.rs:160 set_active(p.bb_breakout.active)` 已是冷啟路徑，TOML flip + rebuild 即生效；無 Rust 代碼改動
4. **sweep 工具 5m bug**：line 686 `horizons_bars = forward_mins if args.timeframe == "1m" else forward_mins` buggy（5m 下需 `[m // 5 for m in forward_mins]`），改造工時 ~1d
5. **量化推薦 C**：B ROI 不利（10d wall-clock 對單策略，擠 EDGE-P3/P1b/Wave 3 主軸），且 F2「signals ≠ edge」對 5m 同樣可能成立（未驗證機制假設），C 是無 regret 路徑（5/03 後仍可改選 B）

### 推薦結論

**選項 C（永久 disable）** — dominated strategy 分析：C 上行小下行也小 vs B 上行大下行也大（且 B 上行有條件機率，C 下行有反悔機制）。架構決策原則「fail-closed + 可逆優先」推 C。

### 沒做的事（E1/E2 領域）

- 沒寫 Rust per-strategy timeframe 接線代碼
- 沒跑 1m vs 5m sweep（資料密集，由 E1 + MIT 接管）
- 沒派 E1 sub-agent（等 PM 拍板 C 後派 4 子任務並行）

### 教訓備忘

- bb_breakout 6 個月內若再啟 → 必先驗 5m sweep 結構級結論（不能再硬調 1m bw）
- F2「signals ≠ edge」是反 replication crisis 紅旗，未來任何「找到能觸發的 bw」提案先問「fee-net forward return 也正嗎」
- §6 自動轉 C 條件（healthcheck [19] cron）為未來「passive 觀察 + 自動兜底」模板，可複用至其他策略 viability 評估

### 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|------|---------|---------|
| 2026-04-26 | G2-06 bb_breakout disposal RFC（推 C disable）| workspace/reports/2026-04-26--g2_06_bb_breakout_disposal_rfc.md |

---

## 2026-04-26 Wave 3 第三波 — 3 C 級 RFC 補 spec

### 觸發

PM 第三波派發指令：FA Wave 3 spec readiness audit 評 EDGE-P1b / EDGE-P2-flip / G2-03 三項為 C 級（核心 spec 缺）。E1 不能開工至 RFC 補完。串行寫 3 RFC。

### 報告路徑

- `workspace/reports/2026-04-26--edge_p1b_7dim_bind_rfc.md`
- `workspace/reports/2026-04-26--edge_p2_flip_sop_rfc.md`
- `workspace/reports/2026-04-26--g2_03_option_b_rfc.md`

### 3 RFC 核心結論（每個 1-2 句）

1. **EDGE-P1b 7 維 bind**：7 維 confirm `est_net_bps / peak_pnl_pct / atr_pct / giveback_atr_norm / time_since_peak_ms / price_roc_short / entry_age_secs`（dim 6 ROC 此 bind 不消費，留 v3）；bind 路徑**不擴 ExitConfig schema**，改現有 5 字段（min_net_floor / min_peak_atr / giveback_base/floor / stale_peak_ms / min_hold_secs）為 percentile-derived；calibrator cron + manual approve（per memory `feedback_env_config_independence` 自動 IPC 寫風控值風險高）；per-strategy stratification + rolling 14d + 7d embargo + ≥200 rows/strategy；ETA ~5/10。

2. **EDGE-P2-flip SOP**：flip 範圍是 **Combine Layer** `RiskConfig.exit.shadow_enabled`（**不是** ExecutorAgent shadow_mode，後者是 G3-02/G3-03）；acceptance = healthcheck [15] 24h agreement ≥95% + per-strategy 分層 ≥95%；推 IPC patch 直接 flip（非灰度，因 Combine 不影響真實決策）+ manual revert SOP（90s 內）；P1-10 並行 = passive 觀察 maker fee（不阻塞）；與 EX-04 / SM-02 物理隔離。

3. **G2-03 Option B**：採 **B2 候選**（擴 `RiskConfig.per_strategy.StrategyOverride` 加 4 個 SL/TP override 字段），非 strategy params 也非 Strategy trait hook；3 道 enforce（validate / runtime cap / calibrator dry-run）守 P1 硬頂；G2-02 counterfactual → G2-03 binding **必 manual approve**（QC §Q2 預期 alpha 結構問題，自動 binding 會掩蓋根本問題）；G2-03 強制依賴 G2-02 完成；per-regime override 留 G2-03-FUP。

### 派發架構建議（給 PM 第三波）

| RFC | E1 子任務 | E1 instance | isolation | 工時 |
|---|---|---|---|---|
| EDGE-P1b | T1 calibrator + T2 summary + T3 IPC restore + T4 healthcheck 升級（4 sub）| Alpha + Beta（並行 2） | 主樹 | 3.5d |
| EDGE-P2-flip | T1 dry-run smoke + T2 healthcheck per-strategy + T3 SOP wrappers（3 sub） | Alpha + Beta（並行 2） | 主樹 | 2.5d |
| G2-03 Option B | T1 schema + T2 risk_checks + T3 TOML + T4 SOP wrapper（4 sub）| Alpha worktree + Beta 主樹 | T1+T2 isolation worktree | 3d |

**啟動順序**：3 RFC schema 部分可並行（T1）；EDGE-P1b + EDGE-P2-flip 可立即派；G2-03 schema 可同步起，但**binding 必等 G2-02 結論**（~5/03+）。

### 關鍵架構發現

1. **MaCrossoverParams 完全無 SL/TP 字段** — 全部走 `RiskConfig.limits` + `RiskConfig.agent`，無 per-strategy 切片；G2-03 是真實 gap（不是 cosmetic）。對比 bb_breakout 已有 trailing_stop_atr_mult 但只控 trailing 距離。
2. **ExitConfig 8 字段 IPC 已通** — `patch_risk_config` deep-merge 直寫 `exit.*` 任意字段（test_g3_05 證明），EDGE-P1b 不需新 IPC method
3. **shadow_enabled 與 shadow_mode 不可混淆** — 兩者分屬 Combine Layer (close-path) vs ExecutorAgent (intent-path)，物理隔離；EDGE-P2-flip 只動前者
4. **G3-03 Phase B 已將 ExecutorAgent `_shadow_mode` 從 hardcoded 改為 IPC provider**（`executor_agent.py:140-181`）— 對齊根原則 #3
5. **per-strategy override 唯一 active 機制是 RiskConfig.per_strategy** — 其他 over-engineering 候選（Strategy trait sl_tp_advice / MaCrossoverParams 內加字段）違反 separation of concerns

### 治理對照亮點

- 3 RFC 全部不觸碰 §四 5 項 live 硬邊界
- §5.7 學習 ≠ 改寫 Live：3 RFC 寫入路徑均經 IPC + manual approve
- §5.4 策略不能繞過風控：G2-03 三道 enforce 確保 override ≤ P1 max
- memory `feedback_risk_changes_scoped`：每個 RFC 範圍精準，不連帶改其他風控

### 沒做的事（E1/E2 領域）

- 沒寫 calibrator 實作代碼（T1）
- 沒寫 risk_checks 接線代碼（T2）
- 沒跑 cargo test / pytest
- 沒 spawn sub-agent（主 agent 串行寫即可）

### 教訓備忘

- **shadow_enabled vs shadow_mode 字面相近但語意完全不同** — 未來任何 RFC 寫此類字段必先註明物理層次與控制平面
- **「per-strategy 定制」3 候選層次** B1/B2/B3 各有 separation of concerns trade-off，B2 (RiskConfig.per_strategy 擴展) 最低架構債（與既有 G3-02 ExecutorConfig 模式對齊）
- **manual approve > 自動 binding** 適用所有 W3 階段風控值寫入（calibrator / counterfactual / shadow flip）— 統一 SOP 模式

### 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|------|---------|---------|
| 2026-04-26 | EDGE-P1b 7 維閾值 bind contract RFC | workspace/reports/2026-04-26--edge_p1b_7dim_bind_rfc.md |
| 2026-04-26 | EDGE-P2-flip shadow→live SOP RFC | workspace/reports/2026-04-26--edge_p2_flip_sop_rfc.md |
| 2026-04-26 | G2-03 ma_crossover SL/TP Option B RFC（推 B2 RiskConfig.per_strategy 擴展）| workspace/reports/2026-04-26--g2_03_option_b_rfc.md |

---

## 2026-04-26 G5-08 strategist_scheduler/mod.rs 拆分計劃

### 觸發

PM 派發 G5-08（P1 Wave 2）：mod.rs 1770 行（§九 1200 hard cap 47% over）。
最近 3 commit（G3-11 CycleCounters + TUNE-TARGET-CONFIG + PERSIST-AUDIT-GAP-COUNTER-1）
累積 ~520 行膨脹回去。已有 sibling persist.rs 446 行（commit 4108849 first-pass 拆完後）。

### 報告路徑

`workspace/reports/2026-04-26--g5_08_strategist_scheduler_split_plan.md`（535 行）

### 推薦結論

**Method A（保守 4-sibling）**：
- mod.rs ~280 行（header + const + StrategistScheduler ctor/getters/builder + 4 mod decl + 4 pub use）
- cycle_counters.rs ~250（CycleCounters atomic 共享單元 + 5 tests）
- validation.rs ~220（pure validate × 2 + 8 tests）
- evaluate.rs ~370（impl: run_forever + evaluate_cycle + 4 helpers + PairMetrics + rank_by_deviation + PairMetricsRow）
- tests.rs ~250（剩餘 13 tests + mk_deps）
- persist.rs 446（不動）

vs Method B（runtime.rs 大塊 + tests.rs 集中 620）— 拒因 tests.rs 接近 800 警告線 + sibling 結構不齊（runtime.rs 用 sibling-child-module，cycle_counters 純 type，pattern 雜）。

### 5 大關鍵架構發現

1. **既有 persist.rs 已是「first-pass 拆」的模型**：commit 4108849 把 mod.rs 從 1342→880，採 `impl StrategistScheduler { pub(super) async fn ... }` sibling-child-module pattern；G5-08 完全沿襲此模板，不創新 pattern
2. **CycleCounters 是 IPC 共享 atomic struct**：ipc_server/mod.rs L103 + L566 + L709 + handlers/misc.rs L210 + main_boot_tasks L170/316 共 5 個外部 callsite，全走 `crate::strategist_scheduler::CycleCounters` path；拆檔 = pub use 維持 path 不動
3. **G5-08 與 G5-FUP-IPC-MOD-SPLIT 完全獨立**：patch_risk_config handler 在 ipc_server/mod.rs 不在本檔；可同時派 2 個 E1（無 isolation 需求）
4. **15 條熱路徑 invariant 全識別**：含 G3-11 cycle_counters Arc + atomic ordering / SCHED-CLOSE-FILTER-1 三條 NOT LIKE filter / FA-1 Demo-only debug_assert / PERSIST-AUDIT-GAP-COUNTER 的 i64 cast bug 規避 / 6 reject reason 字串 / mod.rs 9 條 pub path / run_forever pub async fn 等
5. **31 tests 完整盤點 + 拆分後分布表**：cargo test --release baseline 31 PASS（與 PM 採集相符），分到 cycle_counters 5 / validation 8 / tests 13 / persist 5；任一 sibling test 名變動 = 必打回（healthcheck cron 監控可能讀名）

### 派發架構建議

| 子任務 | E1 instance | isolation | 工時 |
|---|---|---|---|
| G5-08 全 4 step（cycle_counters → validation → evaluate → tests）| 單實例串行 | 主樹 | 2.5-3h |
| G5-FUP-IPC-MOD-SPLIT | 隔壁實例 | 主樹 | ~3-4h（推測）|
| **可並行** | | | |

E2 review 1-1.5h + E4 regression 1.5-2h = 全鏈 5-6.5h。

### 沒做的事（E1/E2 領域）

- 沒寫拆分代碼（4 step 全留 E1）
- 沒實際移動檔案 / 跑 cargo build
- 沒派 sub-agent（純 PA design 主 agent 串行讀+寫）
- 沒擴範圍到 G5-09/10/11/13/FUP-IPC（隔壁 ticket）

### 教訓備忘

- **既有 first-pass 拆過的檔再次膨脹是常態** — persist.rs 拆完後 mod.rs 又被 G3-11 + TUNE-TARGET + PERSIST-AUDIT-GAP-COUNTER 三波加回 ~520 行；§九 拆分需 design 「未來 N 次新功能不撞警告線」的 buffer，A 方案全 sibling <450 留 350+ buffer 是這個考量
- **拆分計劃必含「外部 caller path 全盤點」**：本 design 第一輪寫到 §1.4 才發現 main_boot_tasks 5 個 callsite + ipc_server 4 個 callsite + handlers/misc 1 個 callsite，全走 `pub use` re-export 必須維持；漏一條 = 下游 5 檔同時編譯掛
- **既有 sibling 是最好的 reference 模板** — persist.rs 446 行（doc + use + impl extension + standalone fn + cfg(test) tests）就是教科書級的 sibling-child-module；G5-08 不需要重新發明，evaluate.rs/cycle_counters.rs/validation.rs/tests.rs 都套此模板

### 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|---|---|---|
| 2026-04-26 | G5-08 strategist_scheduler/mod.rs 拆分計劃（推 Method A 保守 4-sibling）| workspace/reports/2026-04-26--g5_08_strategist_scheduler_split_plan.md |

---

## 2026-04-26 G3-08 H1-H5 → Rust IPC Gateway 設計（plan only）

### 觸發

PM 派發 G3-08（Wave 2 P3，TODO.md L223）。前置 G3-03 ExecutorConfigCache（commit `51608fe` 2026-04-25 ✅）。
Layer 2 自主推理 + ExecutorAgent shadow→live 整合需要 Rust hot-path 看到 H1-H5 + 5-Agent state，當前 Python-only ~4552 行隔離。

### 報告路徑

`workspace/reports/2026-04-26--g3_08_h1_h5_ipc_gateway_design.md`（680 行）

### 推薦結論

**Option C 混合模型（cache + invalidation push）** — 鏡射 G3-03 ExecutorConfigCache pattern 但**反向**（Python SSOT，Rust pull）+ 新增 invalidation push 通道。

A push（pure push）/ B pull（pure pull）對比 A IPC 量 5000/min 爆炸 + Python crash 立刻 stale；B 每 hot-path query 1-3ms breach SLA。C 混合：Rust 端 DashMap cache 10s daemon poll + invalidation hint 立刻觸發 ad-hoc poll → hot-path lookup ≤1ms p99 + IPC ~50/min 可控 + Python crash 沿用 last good。

### 5 大關鍵架構發現

1. **G3-03 pattern 反向重用**：G3-08 SSOT 是 Python（H1/H5 stats / Layer2 cost），Rust 端只讀；G3-03 SSOT 是 Rust（RiskConfig.executor），Python 端只讀。**鏡射 cache + poll + fail-closed default 三件套**但流向反 — 命名「鏡射 G3-03」實為反 pattern 反向擴展
2. **DashMap atomic stats 已驗為 Rust hot-path 觀測標配**：commit G3-11 CycleCounters 已示範 5 個外部 callsite + atomic ordering pattern；G3-08 沿用避免 lock-based concurrent struct
3. **Schema 演化用 HashMap<String, i64>** + `#[serde(default)]`：5-Agent stats 不固化 schema（rust struct 一改 Python 必跟，違 G6 漸進可逆），改用 forward-compat dynamic dict
4. **multi-worker uvicorn race 是 Phase 1 接受不一致**：4 worker 各自 STRATEGIST_AGENT singleton 是 worker-local，query_h_state_full 看到隨機某 worker view；Phase 4+ 評估 leader-only flock pattern（沿襲 EDGE-SCHEDULER-LEADER-1 commit `f32629c`）
5. **DEFAULT-OFF env-gate 是大範圍改動的必要保險**：G3-08 ~2180 LOC 若無 phase 切割易堵 Wave 2 主軸；env-gate 確保 wave 2 阻塞時可 unset 立即 zero overhead 不影響其他工作流

### 派發架構建議

| Phase | 子任務 | E1 instance | isolation | 全鏈工時 |
|---|---|---|---|---|
| Phase 1 | A Rust h_state_cache + B Python invalidator + C 接線 | E1-Alpha worktree（A）+ E1-Beta 主樹（B）+ 主 agent 串行（C） | A 必 isolation / B+C 主樹 | 4.5d |
| Phase 2 | H1+H3 接（最高量 query） | E1 主樹 | 主樹 | 3d |
| Phase 3 | H2+H4+H5 接（解阻 G3-09 cost_edge_ratio） | E1 主樹 | 主樹 | 3.5d |
| Phase 4 | 5-Agent state events（解阻 G8-01） | E1 主樹 | 主樹 | 4d |

合計 wall-clock ~13.5d（Phase 1 並行折扣後），LOC ~2180 全鏈。

### Top 3 風險

1. **IPC poll 競態**（10s daemon + invalidation hint 重疊）— 緩解：tokio::sync::watch dedup logic（30s 內 N 次合併為一次 poll）
2. **multi-worker uvicorn 鎖競爭** — Phase 1-3 接受不一致（observability advisory），Phase 4+ 評估 leader-only schema
3. **Schema drift（Python 加新字段 Rust 沒解）** — AgentState 用 HashMap<String, i64> 動態 schema + `#[serde(default)]` 新字段；release notes 記載 14d grace period

### 治理對照亮點

- 16 根原則 #1/#2/#3/#4/#5/#6/#7/#9/#10 全 ✅（純 observability，不繞 lease，fail-closed default + DEFAULT-OFF）
- ★ 直接強化 #13 AI 成本感知（解阻 G3-09 cost_edge_ratio）+ #15 多 Agent 協作（5-Agent → Rust 觀測通道）
- §四 5 項 live 硬邊界全不觸碰（H state 純讀、無 order 路徑、不影響 mainnet gate）

### 沒做的事（E1/E2 領域）

- 沒寫 Rust h_state_cache 任何實作代碼（Phase 1A 全留 E1）
- 沒寫 Python invalidator 實作（spec + prompt template only）
- 沒改 H1-H5 / 5-Agent 業務代碼（Phase 2-4 個別小改）
- 沒跑 cargo test / pytest
- 沒派 sub-agent（純 PA design，主 agent 串行讀+寫）
- 沒擴範圍到 G3-09 cost_edge_ratio 演算法 / G8-01 認知 e2e（隔壁 ticket）

### 教訓備忘

- **「鏡射 G3-03 pattern」命名不嚴謹**：流向相反（Python vs Rust SSOT）但 cache + poll + fail-closed default 三件套通用 — 未來 IPC bridge design 第一句先確定 SSOT 在哪邊
- **Phased rollout + DEFAULT-OFF env-gate** 是大範圍改動（~2000 LOC+）的必要保險：G3-08 4 phase 設計可單獨 rollback、不堵 wave 主軸、unset 立即 zero overhead
- **forward-compat HashMap dynamic schema** 對 observability 字段是 dominated strategy：lock-step Rust+Python deploy 太貴；observability 字段不需強型別保證

### 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|---|---|---|
| 2026-04-26 | G3-08 H1-H5 → Rust IPC Gateway 設計（推 Option C 混合模型，4 phase wall-clock ~13.5d）| workspace/reports/2026-04-26--g3_08_h1_h5_ipc_gateway_design.md |

---

## 2026-04-26 Tier 6 Track 2 — G3-08 H3 schema align A/B/C 決策

- 觸發：E2 Tier 5 batch review T5.3-MED-1（H3 Python 10 keys vs Rust H3RouteStats 7 fields 0/7 對齊；Phase 3 接 real fetcher 前必修，silent regression 隱形地雷）
- 報告：`workspace/reports/2026-04-26--g3_08_h3_schema_align_decision.md`
- Recommend **Option B（Rust rename 對齊 Python + 加 3 缺欄）**：~25 LOC Rust 內部 vs A 的 ~50 LOC Python+test+GUI break vs C 的永久雙詞彙負債；Python 是 SSOT、Rust H3RouteStats 0 hot-path consumer 是黃金時間窗
- 下次 session E1 ready-to-deploy（§7 prompt template + §8 Phase 3 dependency check）
- Phase 3 unblock path：yes（H3 align 完即可派 H2/H4/H5 + RealHStateFetcher + Rust hot-path consumer 一波 ~3.5d）

---

## 2026-04-26 Tier 6 Track 3 — PAPER-STATE-DUST-RESTORE-AUDIT design

推 **Option B**（保持現狀 + 加 healthcheck [19]）— restore_from_db 只還原 counter 不重建倉位；STRKUSDT dust 不來自 restore 是 runtime partial close 殘留；EXIT-FEATURES-FIX A1 fast_track Gate 1 USD floor 已從消費端徹底防 spiral；A 直 evict / C flip owner 對 live user 真實小單有誤刪/誤卡風險（cross-env hard fail）。Healthcheck [19] one-liner SQL：`SELECT COUNT(*) FILTER (WHERE realized_pnl=0) FROM trading.fills WHERE strategy_name LIKE 'risk_close:fast_track%' AND ts > now() - interval '1 hour' AND engine_mode IN ('demo','live','live_demo')` — 0 = PASS / 1-10 = WARN / >10 OR distinct_dust_symbols ≥3 = FAIL。

報告：`workspace/reports/2026-04-26--paper_state_dust_restore_audit.md`

---

## 2026-04-26 Tier 7 Track 3 — G3-08 Phase 3 sub-task split design

推 **Pattern B（per-H 模組整鏈，3 sub-task）** — Pattern A (9 sub-task) 過細空 α / Pattern C (4 sub-task with audit prelude) audit 已併入 RFC §2.3；3-1 H2 + 3-2 H4 並行（不同檔），3-3 H5 串行（同檔 layer2_cost_tracker 避雙修衝突）；ETA 3.5d wall-clock；H4 必補 `validation_pass` counter（Phase 3 前缺，stateless validator 的 stats 由 caller-strategist 維護）；strategist_agent.py 1170+~25=~1195 行接近 §九 1200 硬上限，Phase 4 Strategist sub-task 必先拆檔；Sub-task 3-3 完成 unblock G3-09 cost_edge_ratio + Phase 4 5-Agent 整鏈。報告：`workspace/reports/2026-04-26--g3_08_phase3_subtask_split.md`

---

## 2026-04-26 Tier 8 Track 3 — T7-FUP-DUST-SQL-DEVIATION-DOC RFC §7.4 amend

PM follow-up amend：`2026-04-26--paper_state_dust_restore_audit.md` §7.1 prompt SQL + §7.2 spec SQL 同步 E1 Tier 7 commit `8241133` 落地版本（drop `partial_reduce_real_count` + 加 `FILTER (WHERE realized_pnl = 0)` 到 `COUNT(DISTINCT symbol)`），加雙語 deviation 解釋；新增 §13 Deviation Log 紀錄此 amend 歷史 + slot 編號 [19]→[21] 修正。E2 Tier 7 batch review T7-LOW-1 評為 improvement not regression；Linux production cron 16:09 UTC LIVE PASS 確認。RFC §1-§6 + §8-§12 結論不變。

---

## 2026-04-26 三 P0 fix design（接 STRKUSDT RCA 後 — F3 evict-on-dust / F4 unmatched WS fill drop / F6 edge reload）

### 觸發

PM operator 18:30 派發：af48ee1 涵蓋 STRKUSDT spiral 上游（Gate 1 USD floor + A3 backfill）但 E5 engine.log dive + MIT DB audit 揭發 3 個獨立 P0 bug — F3 phantom dust 殘留 evict-on-dust 缺、F4 trading.fills 7d 0 LIVE rows 但 engine.log 有真 LIVE WS fill、F6 edge_estimator scheduler 寫 hot 但 engine inject boot-only 14h 0 reload。要 read-only 設計（不寫實作碼）。

### 報告路徑

`workspace/reports/2026-04-26--three_p0_fixes_design.md`

### 5 大關鍵架構發現

1. **F4 RCA：trading_writer 無 engine_mode filter**（grep verified `database/trading_writer.rs:259-338` 無條件寫所有 mode）— 真正 drop 點在 **`event_consumer/loop_handlers.rs:555-560` 的 `else { warn!(); }` branch**。LIVE WS fill 全 unmatched（ExecutorAgent shadow_mode hardcoded → 0 SubmitOrder → 0 PendingOrder → 100% unmatched），fallback 路徑 silent return 無 emit `TradingMsg::Fill`。F4 設計：對 unmatched WS fill 落 `unattributed:bybit_auto` audit row（live/live_demo/demo only，paper 不接 WS），同步加 ML pipeline `WHERE strategy_name NOT LIKE 'unattributed:%'` 過濾防污染學習資料。

2. **F6 RCA：PH5-WIRE-1 inject 確認 boot-only**（grep `set_edge_estimates` callsite = bootstrap.rs:586 唯一一處 + intent_processor/mod.rs:480 setter，**無 IPC reload arm**）。`settings/edge_estimates.json` mtime 22:30 28KB scheduler 確實熱寫，但 engine 02:28 boot 後沒 reload 路徑。F6 設計：mirror G3-08 `spawn_h_state_poller_if_enabled` pattern 加 `spawn_edge_estimates_reloader` daemon — 1h periodic + manual IPC `reload_edge_estimates` 雙路徑（advisory pattern 同 PIPELINE-SLOT-1 Phase 3 `trigger_live_auth_recheck`）。3 pipeline (paper/demo/live) 各自 IntentProcessor 需獨立 reload，mode 隔離（paper 讀 `_paper.json`，demo/live 讀 production）必嚴守。

3. **F3 設計：USD-denominated evict-on-dust 4 觸發點 + 不寫 trading.fills**：
   - T1 `reduce_position` 後 / T2 `apply_fill` 反向減倉 / 同向加倉殘餘 / T3 startup boot reaper（在 migrate_legacy_entry_notional 之後）/ T4 status interval 30s 守底 reaper
   - re-use `RiskConfig.limits.ft_dust_qty_floor_usd`（af48ee1 已 land schema），不新增 schema
   - **不寫 trading.fills**（避免污染 ML 學習資料 — `PAPER-STATE-DUST-RESTORE-AUDIT` §4 教訓對齊）；改 `tracing::warn!` 結構化 audit + `pipeline.stats.dust_evictions` counter
   - paper_state 既有 dust_gate.rs（`triage_bybit_sync` + `DUST_FROZEN_STRATEGY`）是 **startup-time triage**，與 F3 runtime evict 互補不衝突

4. **F3-3 與 F4-1 同檔不同 line block**（`event_consumer/loop_handlers.rs` line ~354 status arm vs line 555-560 unmatched else branch）— **必 isolation worktree** 派發避撞。Wave 1 5 個 E1 instance 並行（F3-1/F3-3/F4-1/F6-1/F4-3），3 個必 worktree。

5. **派發 schedule wall-clock**：Wave 1（5 並行 ~2h）+ Wave 2（6 子任務並行 ~2h）+ Wave 3（E2 review + E4 regression 3.5h）= **7.5h 全鏈**。對比串行 23.5h 省 **16h**。

### 推薦結論

3 fix 全 P0 必與 af48ee1 一起 land。F6 是 cost_gate 99.98% reject **真正 root cause**（vs 之前 Phase 5 reframe 假設 strategy gross negative edge）— 部署後 cost_gate reject ratio 應顯著下降，配合 EDGE-DIAG-1 Phase 3 strategy-scoped fallback 雙管齊下。

### 16 原則對照

3 fix 全不觸碰 §四 5 項 live 硬邊界。F4 #6 fail-closed default + #7 ML filter 阻 unattrib 進訓練。F6 #9 災難保護（1h periodic + manual fallback 雙路徑）。F3 #5 生存強化 + #7 evict 不寫 ML 表。

### 沒做的事（E1/E2 領域）

- 沒寫任何實作碼（E1 領域全部留待派發）
- 沒 spawn sub-agent（純 PA design 主 agent 串行讀+寫）
- 沒擴範圍到 ExecutorAgent shadow→live 切換 / ML-TRAINING-DATA-HYGIENE-1 / Reconciler EX-04 對 drift 補正

### 教訓備忘

- **「文件 mtime 新」≠「engine 看到新值」**：F6 RCA 第一波若只看 JSON mtime fresh 會錯判；必驗 engine 內 inject callsite（grep `set_edge_estimates`）。runtime evidence 優於 file system evidence。
- **「writer 沒 silent skip」≠「DB 有 row」**：F4 假設「writer skip live」是 trap；真正 drop 在更上游 `else { warn!(); }` branch。debug fill drop 必順鏈條從 `private_ws emit` → `event_consumer` → `apply_confirmed_fill` → `trading_writer` 全程查，不可只看 last hop。
- **「dust evict via qty threshold」對 funding-accrued residue 無效**：`pos.qty < 1e-12` 對 STRKUSDT 7e-13 生效但對 `qty*price < 1.0 USD` 但 `qty > 1e-12` 的 sub-cent residue 失效。USD-denominated floor 是更穩健 invariant。
- **`spawn_h_state_poller pattern` 是 reusable template**：spawn fn → main.rs spawn call → IPC notification → cancel_token shutdown。F6 reloader 0 創新沿用同 pattern。未來任何 background daemon 先 grep reference 而不是重新發明。
- **多 fix 派發前必 dependency-graph 全攤開**：派發前 `git diff main...HEAD --name-only` 比對所有 fix 主檔，撞區必標 isolation worktree。F3-3 vs F4-1 同檔不同 line block 案例。

### 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|---|---|---|
| 2026-04-26 | 3 P0 fix design（F3 evict-on-dust / F4 unmatched WS fill audit / F6 edge reload daemon）| workspace/reports/2026-04-26--three_p0_fixes_design.md |

---

## 2026-04-26 STRKUSDT dust spiral + Demo silent RCA

### 觸發
PM operator 18:10 報「Demo 引擎自 08:13:59 CEST 0 fills 連續 ~10h，但 watchdog alive=true；07:37→08:13 STRKUSDT 被 risk_close:fast_track_reduce_half 切半 38 次，qty 0.05→7.27e-13，price 全 0.04261」。要 4 問題答覆 + fix design。

### 報告路徑
`workspace/reports/2026-04-26--strkusdt_dust_spiral_rca.md`

### 5 大關鍵發現

1. **Operator 假設「reduce_half 走另一條 path」錯誤** — STRKUSDT 與 BTCUSDT 都走同一條 `step_0_fast_track` ReduceToHalf 分支（trigger_tag = `risk_close:fast_track_reduce_half` 寫死於 step_0_fast_track.rs:454，emit_close_fill + execute_position_close 兩 sink 共用此 tag）。差異是同一 ratio gate 對 STRKUSDT entry_notional=0 fail-open，對 BTCUSDT entry_notional=76.08 正常擋住。
2. **MIT audit + commit `af48ee1` 已 land 完整 cohesive 1+2 RCA fix**（15:48 CEST）但運行 binary mtime 04:29（PID 2033577）**未含此 commit**。Fix 包含 (a) Gate 1 USD floor `ft_dust_qty_floor_usd: 1.0` (b) A3 `migrate_legacy_entry_notional()` defence-in-depth (c) B1 `is_partial_reduce_tag` 跳 EF emit。**部署 = `restart_all.sh --rebuild`** 即 done。
3. **08:13 後 demo silent 不是 STRKUSDT 引起的次生災害** — 假設 A/B/C 全 REJECTED，假設 D 確認：spiral 結束後 BTCUSDT entry_notional 76.08 vs current 9.75 永久 ratio gate 擋（floor 19.02），ma_crossover 沒在發 strategy_close，新開倉 0 entries 是「策略選擇」+ regime 等獨立 question，**不是 engine 故障**。Engine 18:23 仍 print BTCUSDT MICRO-PROFIT-FIX-1 + 04:00/12:00/16:00 三次 funding WS fill = 整路徑 alive。
4. **STRKUSDT entry_notional=0 的具體 path 不可確認** — log 顯示 startup avg_price=0.04261，import_positions line 67 應寫 entry_notional=0.004261，但 ratio gate 0 條 print 證明 entry_notional==0。MIT audit §6.1 已 acknowledge follow-up；不在 PA 範圍但 Gate 1 USD floor 對「path 為何」不依賴（fail-closed 永遠生效）。
5. **paper_state ↔ Bybit drift 對賬 gap** — emit_close_fill 寫 trading.fills 37 條成功 + execute_position_close dispatch 全部被 Bybit min_notional=5.0 reject + dispatch.rs:395 `continue;` 無回滾邏輯。Reconciler EX-04 應 5min 偵測 paper_state qty 0.05→7e-13 vs Bybit 0.1 drift 但實際沒 trigger 降級。F2 follow-up audit。

### 改動風險評級

**部署既有 fix `af48ee1` = 低風險**：
- 純 `--rebuild`，無 schema migration / 無 IPC service breakage / 無 DB write
- 17 new tests 已綠（lib 12 + integration 5）
- Hot-reloadable IPC `patch_risk_config` schema 兼容（new field `ft_dust_qty_floor_usd` 已 serde default + range validate）
- Regression 風險低（real position 名義 ≥5 USD min，1 USD floor 不誤殺）

### 派發架構建議

**已不需派發**（fix 已 in-tree）—— 通知 PM operator 觸發 `restart_all.sh --rebuild`。

但若 PM 仍需 follow-up，3 子任務（**MIT audit §6 acknowledged but not yet done**）：
- F1 (0.5d) STRKUSDT entry_notional=0 path 深查 audit
- F2 (0.5d) Reconciler EX-04 對 spiral 期間 drift 補正 path 驗證
- F3 (0.5d) 加 `[19]` healthcheck dust spiral 偵測（MIT §6.6）

**全 isolation 否**（純 audit + 1 healthcheck check），單 E1 串行 1.5d。

### 16 原則對照

- #6 失敗默認收縮：pre-fix ratio gate 對 entry_notional=0 fail-OPEN **違反**；af48ee1 Gate 1 修正 → 符合
- 其他 15 條無觸碰

### 沒做的事（E1/E2 領域）

- 沒寫 fix patch（已存在於 `af48ee1`）
- 沒派 sub-agent（純 PA RCA + design）
- 沒跑 cargo test（已綠 lib 2210 / 0 failed per E1 report）
- 沒擴範圍到 ML-TRAINING-DATA-HYGIENE-1 P2（隔壁 ticket）

### 教訓備忘

- **Operator 假設「另一條 path」需先驗 grep emit 點** — 本 RCA 一開始就用 grep `risk_close:fast_track_reduce_half` 找到 step_0_fast_track.rs:454+468 single emit 點，立刻證偽假設。任何「不同 strategy_name → 不同 path」假設先 grep 字串 source 而不是相信 reasoning。
- **Binary mtime 是現場第一手證據** — MIT audit + commit + E1 fix report 三邊對齊 fix 已 done 但 `stat openclaw-engine` mtime 04:29 vs commit ts 15:48 證明 binary 未含 fix。runtime 證據優先於 git 證據。
- **「engine silent」不等於「engine broken」** — engine.log tail 18:23 仍持續 print 非 spiral 相關訊息（BTCUSDT MICRO-PROFIT-FIX-1）= alive。「0 fills」可由「無新 strategy 信號」單純解釋，沒必要假設 wedged / 降級 / spiral 鎖死。silent 因果先驗「strategy signal layer 是否 emit」而不是先假設 hot-path lock。
- **fail-OPEN guard pattern 是反 #6 設計** — `if entry_notional > 0.0 { ratio gate } else { pass through }` 是典型反模式：legacy/restored snapshot 的 zero-state 拿到無門檻通行。Fix pattern：Gate 1（絕對 floor）+ Gate 2（相對 ratio）都 active，相對門開不到的場景由絕對門兜底。

### 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|---|---|---|
| 2026-04-26 | STRKUSDT dust spiral + Demo silent RCA + fix 形狀（ack `af48ee1` 已 land 待 deploy）| workspace/reports/2026-04-26--strkusdt_dust_spiral_rca.md |

---

## 2026-04-26 Tier 9 Track 2 — G3-09 cost_edge_ratio design RFC + T8-FUP typo fix

Phase 3 H5 解阻後派發 G3-09 設計 + T8-FUP-RFC-TYPO-FIX 一次合 1 commit。Recommend integration = **新建 cost_edge_advisor 模組**（候選 4 vs intent_processor cost_gate 重疊 / combine_layer 違 Gate-4-only / phys_lock_v2 違 per-position semantic mismatch）。3 Phase rollout: A schema+advisory (4.5d) → B shadow dry-run (1.5d) → C live triggered gate (2.5d) 全鏈 8.5d。CLAUDE.md §二 #13「ratio ≥ 0.8」字面義與公式方向矛盾，採解釋 A 變體 = threshold 為負值（預設 -0.5 保守起點，operator-tunable）。「建議關倉」語意 = Phase C 阻新倉**不**強制關現有倉（fail-soft，避 false-positive 直接虧損）。env-gate `OPENCLAW_COST_EDGE_ADVISOR` + RiskConfig.cost_edge.enabled 雙保險。Phase 4 5-Agent state events 與本 RFC 並行可派（互不阻塞）。報告：`workspace/reports/2026-04-26--g3_09_cost_edge_ratio_design.md`。同 commit T8-FUP typo fix `paper_state_dust_restore_audit.md` §7.2 "improvement not improved spec" → "improvement not regression"（業務內容不變，1 字 amend）。

---

## 2026-04-27 G3-08 Phase 4 5-Agent state events design RFC

### 觸發

PM Tier 8 sign-off `e5f1b2d` next-step：Phase 1+2+3 完成（H1-H5 5-bucket live），Phase 4 = 5-Agent (Strategist/Guardian/Analyst/Executor/Scout) state events 接入 Rust h_state_cache。Strategist sub-task hard pre-condition = G3-08-PHASE-4-STRATEGIST-SPLIT 並行進行中，其他 4 agent 主檔 LOC < 800 無拆檔阻塞。

### 報告路徑

`workspace/reports/2026-04-27--g3_08_phase4_5agent_design_rfc.md`（1415 行）

### 推薦結論

**Pattern B 5 sub-task per-agent**（鏡 Phase 3 Pattern B per-H 模組）：
- 4-1 Strategist (~60 LOC) — hard pre-cond STRATEGIST-SPLIT
- 4-2 Guardian (~35 LOC) — 並行
- 4-3 Analyst (~26 LOC) — 並行（§七 警告）
- 4-4 Executor (~36 LOC) — 並行（shadow_mode wire 注意）
- 4-5 Scout (~27 LOC) — 並行（§九 接近）

ETA 全鏈 **3.75d 並行版**（≤ PA design §11.1 估 4d），順序 5d。

### 5 大關鍵架構發現

1. **query_handler 升級採 Option B 拆兩個 collector**（vs A 同函式擴展 10 參數 / 10-tuple）：`_collect_h_snapshots` Phase 3 簽名不變 + 新增 `_collect_agent_snapshots` 返回 dict 而非 tuple → Phase 5 加 agent 不破壞 caller（forward-compat 模板）

2. **Phase 4 invariant：所有 snapshot 字段必為 int 或 bool→int**（不准 float / string）對齊 Rust `AgentState.stats: HashMap<String, i64>`。Executor `total_slippage_bps` (float)、cognitive/emergency bool / shadow_mode 必 cast int。Phase 5+ 若需 float（如延遲 ms） → 新增 `gauges: HashMap<String, f64>` 兄弟字段不混入 stats

3. **Sub-task 4-4 Executor `_shadow_mode_provider()` call 必在 self._lock 之外**（避 G3-03 ExecutorConfigCache 內部 lock + self._lock 死鎖）+ provider raise 必 fail-closed = 1（shadow on，CLAUDE.md §二 原則 #6）。snapshot vs ConfigStore SSOT 物理層次區分必寫進 docstring（避未來開發者誤改方向破壞 G3-03 契約）

4. **2 條 Backlog FUP 必排**：
   - **G3-08-FUP-ANALYST-SPLIT**：Analyst 主檔 834 LOC（pre-Phase-4 即超 §七 800 警告線），Phase 4 4-3 land 後 ~860；下 wave 拆檔目標 ~480 LOC（鏡 Phase 4 split RFC §6.4 Method A）
   - **G3-08-FUP-MAF-SPLIT**：multi_agent_framework.py 1137 LOC + 27 = ~1164 距 §九 1200 hard cap 僅 36 LOC headroom；下 wave 拆 ScoutAgent (~183 LOC) 出獨立 `scout_agent.py`（建議 P1 優先級避 Phase 5 觸 §九）

5. **healthcheck [20] expected set 漸進式 rollout 是 5 sub-task 並行的關鍵**：每 sub-task 必同 commit 升級 healthcheck（baseline 5 H bucket → Sub-task 4-N land 後 += {對應 agent slot} → 4-5 land 後 expected = 10 bucket）；半途部署 set diff 非空且非全空 → WARN（容忍 missing slot），全空 → PASS。E2 review 必查每 sub-task healthcheck 同步升級

### 派發架構建議（PM Phase 4 wave）

| Sub-task | E1 instance | isolation | 依賴 | ETA |
|---|---|---|---|---|
| 4-1 Strategist | E1-Alpha worktree | YES | STRATEGIST-SPLIT 必先 land | 1d |
| 4-2 Guardian | E1-Beta 主樹 | NO | 4-1 land 後（_collect_agent_snapshots dict skeleton） | 0.75d 並行 |
| 4-3 Analyst | E1-Gamma 主樹 | NO | 同上 | 0.75d 並行 |
| 4-4 Executor | E1-Delta 主樹 | NO | 同上 + G3-03 ConfigStore | 0.75d 並行 |
| 4-5 Scout | E1-Epsilon 主樹 | NO | 同上 | 0.75d 並行 |

**multi-track absorb pattern**（per Phase 3 commit 8cd257e 經驗）：4-1 落主樹 → PM merge → 4-2/3/4/5 同步 fetch → 4 個 E1 並行 worktree → PM 序貫 merge 4 個 commit。`_collect_agent_snapshots` h_state_query_handler.py 共改但每 sub-task 加自己的 `if include_<agent>:` 區塊（互不重疊 dict literal）→ 後 commit `git pull --rebase` 自動合併。

### Top 風險

1. **R1 4 並行 sub-task 同改 h_state_query_handler.py 衝突**（中機率/中影響）→ absorb pattern + per-arm if 區塊隔離
2. **R3 Analyst / multi_agent_framework.py 過 §七 警告線**（高機率/低影響）→ 警告線非 hard cap 不阻塞，Backlog FUP 排下 wave
3. **R4 Executor `_shadow_mode_provider()` 與 self._lock 死鎖**（低機率/高影響）→ 4-4 prompt §高風險警告強制 provider call 在 self._lock 外
4. **R6 strategy_wiring SCOUT_AGENT singleton 名稱**（中機率/中影響）→ 4-5 prompt 前置 grep 步驟強制驗證

### 治理對照亮點

- 16 根原則 #1-#10 全 ✅（純 observability extension）
- ⭐ #13 AI 成本感知：Strategist `ai_evaluations` + Analyst `l2_analyses` 解阻 G3-09 cost_edge_advisor 跨維度判斷
- ⭐⭐ #15 多 Agent 協作：Phase 4 直接強化（5-Agent → Rust 觀測通道全 wired）
- §四 5 項 live 硬邊界全零觸碰
- §九 Singleton table 不需更新（重用 Phase 1C `_H_STATE_INVALIDATOR`）
- §七 文件大小：2 警告（Analyst / multi_agent_framework）→ Backlog FUP

### unblock 下游

- **G8-01 認知自適應 e2e 測試**：Phase 4 4-1 + 4-3 提供 `cognitive_modulator_connected` + `experiment_ledger_connected` Rust fixture 端 ≤1ms p99 即時驗證 wire 接通
- **G3-09 cost_edge_advisor**：Rust hot-path `query_agent_state(cache, "strategist", "ai_evaluations")` + `query_agent_state(cache, "analyst", "l2_analyses")` + `query_h_state(cache, "h5", "cost_edge_ratio")` 三條合判，cost_edge_advisor 規則 = `if cost_edge_ratio >= 0.8 AND ai_evaluations_per_min > 5 AND l2_analyses_per_min > 1: advise(REDUCE_POSITION_SIZING)`
- **未來 GUI 6-pane dashboard**：H1-H5 + 5-Agent 同 IPC pull

### 沒做的事（E1/E2 領域）

- 沒寫 5 sub-task 任何實作代碼（純 design + 5 prompt template）
- 沒派 sub-agent（純 PA 主 agent 串行讀+寫）
- 沒跑 cargo test / pytest
- 沒驗 STRATEGIST-SPLIT 是否已 land（next session PM 派發前驗）
- 沒擴範圍到 G3-09 cost_edge_advisor 演算法 / G8-01 認知 e2e
- 沒實際拆 Analyst / multi_agent_framework.py（屬 Backlog FUP）

### 教訓備忘

1. **Phase 4 比 Phase 3 並行性更高**（5 不同主檔 vs Phase 3 共享 layer2_cost_tracker.py），但仍需 absorb pattern（PM 序貫 merge h_state_query_handler.py 共改）
2. **Phase 4 split RFC 預留 90 LOC headroom 是 plan-ahead 投資**：4-1 用 60 LOC + Phase 5 預留 30 LOC 仍 < 800（per RFC §11.4）。**未來大型 cross-cutting 工作前必先評估各影響檔的 §七/§九 headroom**，提前 split 是最便宜的解法
3. **snapshot vs config cache 物理層次區分**（Sub-task 4-4 Executor 案例）是未來凡 Rust ConfigStore + Python observation 雙資料流共存的標準模式：prompt template 必明確標記方向（read vs write、SSOT vs mirror、cache vs state）
4. **bool→int cast 規則** + **dict-not-tuple collector return value** 兩個 forward-compat 設計原則，Phase 5+ 模板可直接套用
5. **multi_agent_framework.py 1137 LOC 是 Phase 1+2+3 合計擴展副作用**：5 個 agent class 集中一檔的歷史包袱，Phase 4 揭發 §九 距離只剩 36 LOC headroom — ScoutAgent 拆檔（FUP-MAF-SPLIT）優先級提升至 P1
6. **healthcheck expected set 漸進式 rollout** 是 N sub-task 並行的關鍵：每 sub-task 必同 commit 升級，避免半途部署持續 FAIL；rollback 時 expected set 也 reverse

### 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|---|---|---|
| 2026-04-27 | G3-08 Phase 4 5-Agent state events design RFC（推 Pattern B 5 sub-task / ETA 3.75d 並行 / 2 Backlog FUP filed）| workspace/reports/2026-04-27--g3_08_phase4_5agent_design_rfc.md |

---

---

## 2026-04-27 G8-01 認知自適應 e2e RFC

### 核心發現

`CognitiveModulator` (193 LOC) live-wired in `strategy_wiring.py:407-409` 但**邏輯 dead**：
- **BUG-A**：caller `strategist_cognitive.py:160` + `strategist_edge_eval.py:191` 呼 `modulator.get_current_params()`，**該方法不存在**（modulator 只有 `get_all_params`），try/except 靜默吞 → 永遠回 default `(min_confidence, 1.0)`
- **BUG-B**：`modulator.update(...)` production code 0 caller（grep 證），permanent 卡 base value (`confidence_floor=0.60`/`qty_ceiling=1.0`/`update_count=0`)

### 設計決策

不直接派 E4 寫測試（會測 dead code），先派 E1-Alpha W1 production fix：
- FIX-A：rename `get_current_params` → `get_all_params`（2 處）
- FIX-B：`strategist_cognitive.py` 新增 `tick_cognitive_modulator(agent)` helper + `strategist_agent.handle_intel()` 末尾每 N=10 次 tick（Option γ）

W2 unit cov ≥85%（22 case，零 mock）+ W3 integration ≥5 case（7 留 buffer）並行。

### namespace 確認

- `local_model_tools/cognitive_modulator.py` = class (193 LOC)
- `control_api_v1/app/strategist_cognitive.py` = sibling helper (169 LOC, 4 functions, no class)
- 兩者語意分離無 confusion

### ETA

3-3.5d wall-clock（W1 1d → W2/W3 並行 1.5d → E2/E4/QA 1d）

### 報告路徑

`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g8_01_cognitive_e2e_design.md`

### 教訓（lessons.md candidate）

「test coverage 不等於 live behavior」— G8-01 原 spec「≥85% line cov」若無人發現 BUG-A+B，可能達標但測的全是 dead code。**Coverage RFC 派發前必先 grep call sites + 驗 method-name parity**。屬 `feedback_no_dead_params` 的 corollary。

---

## 2026-04-27 G3-09 Phase B shadow dry-run RFC（cost_edge_advisor 觀察期）

**RFC**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g3_09_phase_b_shadow_dryrun_design.md`

**Phase B 重定義（vs RFC §7.2 原計畫）**：
- RFC §7.2 line 511 寫「IntentProcessor 加 would_reject_intent shadow check」— 違反 Phase B「0 trade impact」原則（即使 pure fn 也改 hot path 形狀且必須 cost_gate 並排 audit）
- 本 Phase B 把「shadow IntentProcessor」整塊移 Phase C，退回純 advisor observability（觀察 advisor 自己的 evaluate cadence + ratio distribution + status transitions）
- 1.5d 工時與工作量匹配後保持

**範圍**（in/out 嚴格切）：
- IN：持久化 evaluate cycle 採樣（V026 hypertable）+ IPC schema 增 4 欄（counter rolling 24h）+ healthcheck [30] 升級從 schema 哨兵 → trigger frequency sanity + observation deliverable
- OUT：IntentProcessor changes / shadow_reject_count / RiskConfig.cost_edge_gate_enabled / per-strategy ratio（屬 Phase C 或 Phase D）

**Phase A FUP 升級**：`G3-09-PHASE-A-DAEMON-INTEGRATION-TEST` 從 P3 升 **P1**，列 Phase B Wave 0 prerequisite — Phase B observation 沒 daemon 整合測試 = 無 ground truth

**避 decision_outcomes 2 bug**：
- `engine_mode` NOT NULL CHECK + INSERT 路徑顯式 bind（避「100% paper」bug）
- 不存 timeframe（Phase B 不依賴 K 線）+ 全欄位 NOT NULL/explicit DEFAULT
- V026 加 Guard A/B（per CLAUDE.md §七 SQL migration 規範）

**Sanity range**（per RFC §2.2）：
- evaluations_24h ≥ 8000 healthy / < 4000 FAIL（10s cycle × 24h × 95% uptime baseline）
- triggers_24h 0-10 healthy / 11-50 WARN noise / >50 FAIL spam
- triggers_per_hour peak ≤ 5 healthy / 6-20 WARN / >20 FAIL
- dead gate detection at 7d：0 trigger + ratio 全離 threshold ≥0.3 → WARN calibrate

**Down-sample 1/min**：daemon 每 10s evaluate 但 INSERT 1/min（24h 1440 row/day），transition row 不 down-sample（保 burst 100% 紀錄）

**新 Rust 程式碼量**：~180 LOC（mod.rs +120 + types.rs +30 + handler +30）+ V026 SQL +120 + Python healthcheck +80 + observation tooling +150 — **不算純 observability tooling**

**派發**：Wave 0 prerequisite (FUP daemon integration test ~2h) → Wave 1 (Rust+SQL+Py 1d) → Wave 2 E2 (0.25d) → Wave 3 E4 (0.25d) → Wave 4 PM Sign-off → Wave 5+6 passive observation → Wave 7 Phase C GO/NO-GO

**E2 必查 3 點**：
1. daemon INSERT 不阻 evaluate cycle（tokio::spawn fire-and-forget）
2. down-sample boundary 1/min 嚴格 + transition 不 down-sample
3. counter rolling 24h 沒 leak（VecDeque pop_front while ts < cutoff）

### 教訓（lessons.md candidate）

「Phase 計畫的 line item 落地時要拆 trade-impact vs observability」— RFC §7.2 把 shadow IntentProcessor 與「觀察 advisor 行為」混在 Phase B 1.5d，落到具體實作才發現前者實質是 Phase C 一半工作量。下次寫 PA RFC §7.x 工時估算前，用「trade impact」 vs 「pure observability」做 binary 切，工時不混算。

---

## 2026-04-28 G3-09-PHASE-B-FUP-STICKY-TS（sticky `triggered_at_ms`）

**RFC / 報告**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--g3_09_phase_b_fup_sticky_ts.md`

### 任務性質

E2 Phase A daemon test review (`2026-04-27--g3_09_daemon_test_review.md`) INFO finding 升 P2 prep-gate — `advisor.rs:114-120` 註解聲稱 daemon 會 sticky 覆寫 `triggered_at_ms`，但 `mod.rs` daemon body 0 此邏輯，每 cycle 蓋掉。Phase B Shadow 若 dedup / once-per-trigger 邏輯依賴 sticky 時戳會出 bug，所以列為 Phase B Wave 1 派發前 prep-gate。

主會話授權 PA 三角合一執行（PA design + 自寫 ≤80 LOC Rust + 自寫 ≥2 unit test），不擴 scope。

### 設計決策

選 **A（daemon enforce sticky）** vs B（doc-only 對齊現行非 sticky 行為）：
- A 案 30 LOC daemon 改 + 25 LOC docstring + 175 LOC test = 在 80 LOC 上限內
- 避免 Phase B Wave 1 又要踩雷自己維護 sticky state（重複工作）
- `triggered_at_ms` 命名語意是「進入時間」，非 sticky 行為違反命名
- daemon-local `let mut sticky_triggered_at_ms: i64 = 0;` 0 共享 state、0 race、0 額外 lock
- `evaluate()` 純 fn 簽名/行為/測試全保留 — 32 既存 unit case 不動

### 核心邏輯（mod.rs 4-arm match）

```rust
match (&prev_status, &new_state.status) {
    (Trigger, Trigger) => new_state.triggered_at_ms = sticky_triggered_at_ms,  // sticky preserve
    (_, Trigger)       => sticky_triggered_at_ms = new_state.triggered_at_ms,  // entering: capture now_ms
    (Trigger, _)       => sticky_triggered_at_ms = 0,                          // exit: clear
    _                  => {}                                                   // non-Trigger ↔ non-Trigger
}
```

### 驗收

- cargo build release tests clean
- daemon integration test **6/0 → 8/0**（+2 sticky test）
- lib test **2290 / 0 不變**
- Phase A advisory-only 路徑 0 production behavior change（IPC consumer healthcheck `[30]` schema 哨兵不依賴此欄語意）

### Phase B Wave 1 對接

`triggered_at_ms`（contiguous Trigger 區段進入時戳）與 Phase B RFC `last_trigger_ms`（24h rolling 內最後 Trigger transition）語意正交但不衝突 — Wave 1 可直接讀 `triggered_at_ms` 取「episode 進入時間」，不需自維護 sticky state。Wave 1 工時估 1d 不變。

### 教訓（lessons.md candidate）

「pure fn 表達 stateful semantic 時必有 caller 接 sticky/transition 對手戲」— `evaluate()` 永遠回 `now_ms` 對 first entry 正確，但對 contiguous run 錯。caller (daemon) 必須補 sticky enforcement。如果 doc 與實作其中一邊放鬆，另一邊就成 silent bug 種子。**規則**：pure fn doc 寫「caller 會 X」就必須有 caller 那邊的 enforce + regression test，否則 doc 砍掉等同實作。

### 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|---|---|---|
| 2026-04-28 | G3-09-PHASE-B-FUP-STICKY-TS sticky `triggered_at_ms` 設計+落地+驗收 | workspace/reports/2026-04-28--g3_09_phase_b_fup_sticky_ts.md |

---

## 2026-04-28 — G8-01-FUP-LOSSES-WIRING（P2 prep-gate for W2/W3）

**Topic**：Wire `_stats["consecutive_losses"]` from trade outcome callback so `tick_cognitive_modulator` 真正收到非零輸入；解 RFC `2026-04-27--g8_01_cognitive_e2e_design.md` §3.1 acknowledged limitation。

**模式**：3-合一（PA design + 直派 E1 + sanity test，主會話授權）。Scope 嚴格 bounded — 不碰 W2/W3、regret/dream placeholder、Rust IPC。

### 決策摘要

- **Wiring 模式**：Hybrid Option 1（in-process callback path）
  - Analyst gains `set_strategist_loss_callback(Callable[[float], None])`，於 `analyze_trade` 內 fail-open invoke。
  - Strategist gains `record_trade_outcome(net_pnl)` + `_stats["consecutive_losses"]` + `_stats["trade_outcomes_observed"]`。
  - `strategy_wiring.py` 在 Batch-10 Analyst 重 init 後綁 lambda。
- **Reject Option 2**（新 MessageType）— 擴 ALLOWED_FLOWS 矩陣，無功能優勢。
- **Reject Option 3**（Rust IPC）— 違反 Python-as-SSOT-for-Strategist-stats、touch IPC schema 出 P2 scope。
- **Reject Option 4**（subscribe ROUND_TRIP_COMPLETE）— 現場 0 producer（DEAD-PY-2 後 `pipeline_bridge.py` 已刪），會繼續 dead。
- **Breakeven (net_pnl==0) 視為 loss**：per Principle #5（生存>利潤）+ #13（成本-edge 感知）—— fee-eaten trade 耗資本無 edge，正是 modulator 該調製場景。

### 重要現場發現（archived dead path）

- `MessageType.ROUND_TRIP_COMPLETE` 於 `multi_agent_framework.py:63` 仍定義，AnalystAgent.on_message 仍 dispatch，但 **Python production 0 producer**（`pipeline_bridge._emit_round_trip` 隨 DEAD-PY-2 已刪）；`WIRING_AUDIT_SUMMARY.txt:74`/`L1_01_TRADE_ATTRIBUTION_FIX_SUMMARY.md` 等審計引用全 stale。
- 真實 live trade-outcome 入口 = Rust → IPC `analyst_evaluate(analysis_type="round_trip")` → `AIService._handle_analyst()` (`ai_service_dispatch.py:478`) → `analyst.analyze_trade(record)`。Hook 點選對。

### 數字

- 改動：3 files, +194 LOC business code（analyst +70 / strategist +79 / wiring +45）。
- 測試：1 new file, 8 test cases, ~330 LOC test code。Mac pytest 8/8 + W1 6/6 + 相關套件 157/157 全綠。
- §九 警告：strategist_agent.py 854→933（>800 警告線、<1200 硬上限）— 不本 FUP 拆，留 G3-08 Phase 5 未來處理。

### 教訓（lessons.md candidate）

**「派工前必先 grep『有沒有真實 producer』」**：原 spec 提的 Option 1（Strategist 直接訂 Fill 事件）+ Option 2（Analyst broadcast trade_outcome_processed）若不先 grep `MessageType.ROUND_TRIP_COMPLETE` 的真實 producer，可能設計出「訂閱 dead event 的 PR」浪費一輪 E1 工時。本 FUP 第一步 grep 一次就避開，省下 ~2-3 day rework。應該變成 PA RFC §2 (架構評估) 強制 checklist 一條：「列出 trigger event 的 production producer 與 mtime / 過去 7d 觸發次數」。

---

## 2026-04-28 G8-01-FUP-REGRET-DREAM-WIRING — ESCALATE (concept dead)

### 結論

**不寫碼，escalate 主會話**：`OpportunityTracker` + `DreamEngine` 兩個 producer 已於 2026-04-12 RC-11 Cat A 刪除（~1003 LOC，`docs/archive/2026-04-12--changelog_archive_pre_0408.md:575`）。Production 0 caller / 0 class def / 0 import；只剩 docstring placeholder + Rust roadmap `R02-9 core/dream.rs`（未動工）+ V1.1+R1 SPEC（`docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md`，~577 LOC class 設計仍可 reference）。CognitiveModulator `_compute_stoploss_mult` + `direction` 分支結構性不可達；任何 placeholder 都不影響 modulator 行為。

### Wiring 模式選擇

**Path B/C 否決，選 escalate**（per task §3 escalation rule）。3 個推薦 option 留主會話 + operator 判斷：
- **Option A**：刪除 placeholder 參數 + dream branch（~30 LOC，最小 scope）
- **Option B**：依 SPEC 重做 OpportunityTracker + DreamEngine（~600 LOC + tests，3-5d，需新 PA RFC）
- **Option C（PA 推）**：保留接線、加 explicit defer doc + 開 ticket `G8-01-FUP-REGRET-DREAM-DEFERRED P3` 等 R02-9 / 新 wave；零 LOC、honest

### Modulator update() 真實 signature

`update(*, consecutive_losses: int=0, weekly_net_pnl: float=0.0, regret_data: dict|None=None, dream_data: dict|None=None) -> dict`。Schema：`regret_data["net_regret_direction"]` ∈ `{"overtrading","undertrading","balanced"}`；`dream_data["global"]["stoploss_multiplier"]` + `["confidence"]`（>0.6 才生效）。**LOSSES-WIRING 對 update() signature 的假設成立** — `update()` 確實接這 4 個 kwarg，無需改 modulator API。

### 6 個 candidate proxy 全部 fail

(a) H4 missed-opp / (b) Analyst trade outcome / (c) H1 reject log / Scout exploratory / ML registry canary / epsilon-greedy schedule — 6 個 task §2 列舉的潛在源 grep + semantic 比對全 fail：H1 reject ≠ skipped opportunity 虛擬 PnL（spec §3.5 定義）；ML registry 是模型晉升 lifecycle 不是策略 MC 模擬；Scout 無 epsilon-greedy state machine。**任何 fabricated heuristic 都會違反原則 #10 認知誠實 + `feedback_no_dead_params`**。

### 數字

- 改動：0 files, 0 LOC business code（純 escalate 報告）。
- 測試：W1 6/6 + LOSSES 8/8 = 14/14 baseline 全綠（worktree HEAD `e106c5d`）。
- §九 file-size：unchanged。

### 教訓（lessons.md candidate）

**「P2 prep-gate scope 不容忍 fabricated heuristic」**：當 spec'd producer 已被刪、roadmap 未動工，正確回應是 escalate 三選一決策（remove / re-implement / defer），不是「想個 proxy 餵 placeholder」假裝有 wiring。後者是 `feedback_no_dead_params` + 原則 #10 的反模式 — 看似閉環但 `_compute_*` 分支永遠不可達真實 outcome。本 escalation 同模式 LOSSES-WIRING 的「先 grep producer」紀律：**spec docstring ≠ live producer**，`OpportunityTracker.get_regret_summary()` 之類 docstring claim 必須當第一可疑點 grep。

## 2026-04-28 — G3-09 Phase C Intent Gate RFC

- **報告**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--g3_09_phase_c_intent_gate_design.md`
- **HEAD**: `decf712`
- **預決策**:
  - Gate 注入點 = Rust IntentProcessor Gate 1.7（在 1.6 negative-balance 後、Guardian 2 前）
  - **Reject 只阻新倉**（is_reducing=true 完全跳過）— 嚴守 CLAUDE.md §二 #5 生存>利潤反向防線
  - 三層 default-off safeguard：env=1 + cost_edge.enabled=true + cost_edge.gate_enabled=true
  - Dedup window 60s 控 V026 INSERT 頻率；reject decision 本身不受 dedup 影響
  - Per-strategy `cost_edge_threshold_override` + `cost_edge_exempt` 給 emergency exit 路徑
  - 重用 Phase B V026 hypertable，`transition_from='GATE_REJECT:<strategy>'` 字面前綴標記
  - **Python ExecutorAgent 0 改動** — 既有 `rejected_reason` 處理 generic
- **拒絕的替代設計**:
  - Alt 1 Python ExecutorAgent 注入 — 漏 Rust 內部 strategy 直發 path（100% intent 必須 Rust 注入）
  - Alt 2 Guardian 內注入 — 違反 SRP + 跨 crate circular dep 風險
  - Alt 3 IPC submit_intent handler 注入 — 漏 tick_pipeline 內部 process path + audit shape 不一致
  - Alt 4 強制關現有倉 — 違反 #5 生存>利潤 + #11 Agent 自主權
- **Wave 拆分**: Wave 1 Rust gate (~2d, 不可並行) → Wave 2 Python metric (~1d, 與 W1 並行) → Wave 3 Linux deploy + 7d observation
- **Top 3 風險**:
  - R-C1 False-positive reject 平倉 — 複用 Gate 2.7 `is_reducing` pattern + unit test 釘死
  - R-C5 Live mainnet 提早啟用 — TOML default false + Phase A RFC §8.3 Operator checklist
  - R-C6 系統凍結 — IPC 60s rollback + healthcheck WARN + per-strategy exempt
- **副作用識別**:
  - V026 重用 `transition_from` field 增 `'GATE_REJECT:<strategy>'` 語意（下游 query LIKE 'GATE_REJECT:%'）
  - RejectionCode enum 新 variant → exhaustive match compiler-enforced E2 catch
  - IntentProcessor 持 `Option<Arc<CostEdgeAdvisor>>` setter pattern 同 risk_config snapshot
- **教訓**:
  - Phase B RFC R-B6 標的「shadow IntentProcessor would_reject」直接整合到 Phase C binding gate，跳過獨立 shadow stage（理由：Phase B observation 已提供等價證據；多 phase 過長 operator UX 差）
  - Gate 注入點選擇強耦合「單一寫入口」原則 — 任何漏 Rust 內部 path 的設計都先排除

---

## 2026-04-28 PA STRATEGIST-SINGLETON-POLLUTION P3 RFC 完成

### 投查結論
- **35 fail in `test_h_state_query_handler.py`** — bisect 確認 polluter 為 `test_api_contract.py:16` `build_client()` 的 `importlib.reload(main_legacy)` + `importlib.reload(main)`
- **Root cause 不是 singleton state pollution**，是 **CPython `from PKG import SUB` attribute precedence**：
  1. test_api_contract reload main → transitive import strategy_wiring → Python 設 `app.__dict__["strategy_wiring"] = <real module>`
  2. test_h_state 的 `_install_fake_strategy_wiring` 只 patch `sys.modules`，未 patch `app.strategy_wiring` attribute
  3. `_collect_h_snapshots()` 內 `from . import strategy_wiring as _sw` 解析到 attribute（真模組），fake bypass
- **Reproducibility**: Python REPL 直驗 attribute precedence 機制；35 fail 在 `pytest control_api_v1/tests/` 100% 重現；Mac/Linux 跨平台一致

### Fix 推薦
- **Option B + A 合**（治本 + defense-in-depth）
  - B (production): `h_state_query_handler.py:334` `from . import strategy_wiring as _sw` → `_sw = sys.modules.get("app.strategy_wiring")`
  - A (test fixture): `_install_fake_strategy_wiring` 同時 patch `app.strategy_wiring` attribute
- 不推 Option C (autouse fixture overkill) / Option D (pytest-forked 新依賴 + CI 開銷)
- ETA: E1 1.5-2h + E2 0.5h

### 教訓
- **「Singleton pollution」命名陷阱**：實際是 module-level import path 污染，與 singleton 物件狀態無關 — 命名引導排錯方向錯誤
- **CPython `from PKG import SUB` 規範**：先讀 `PKG.__dict__["SUB"]` 再落 `sys.modules` → test fixture 必須雙端 patch（W3 fix 已示範但只修一處測試端，未推到 h_state）
- **Bisect 法則**：alphabetical pytest collection + 二分法 30 秒內定位 polluter；future similar issue 可標準化此流程
- **Test fixture audit**：`_install_fake_X` / `_restore_X` helpers 凡 patch `sys.modules[<pkg>.<sub>]` 必同時 patch `<pkg>.<sub>` attribute，否則 `from . import <sub>` 形 import 會繞過

### 報告路徑
📄 `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--strategist_singleton_pollution_investigation.md`

---

## 2026-04-28 PA+E1 SINGLETON-SIBLING fix (executor + strategist) 合一完成

### 任務範圍
- 2 ticket：SINGLETON-POLLUTION-EXECUTOR-SHADOW-TOGGLE-API P3 (17 fail) + STRATEGIST-PROMOTE-API P3 (18 fail)
- 主會話授權「PA design + 直接 E1 寫碼 + sanity test」三角合一
- 邊界：嚴禁碰第 3 個 ticket (test_phase2_routes P4 Mac-only)；若 root cause 非 sibling-pollution → escalate

### 結論
- **17→0 + 18→0 = 35 fail 全消** ✅
- **同 sibling-pollution family（同 polluter `test_api_contract::build_client`），但 root cause 與 W3 SINGLETON 不同**：
  - W3：`from PKG import SUB` attribute precedence (h_state_query)
  - 本 wave：**FastAPI `Depends(base.current_actor)` route-build-time freeze callable**，reload main_legacy 後 `current_actor` 變新 fn obj，但 router 內 frozen 仍是舊 → `dependency_overrides` 對不上 → 401
- **Fix = Option A only（test fixture）**：`_make_app` 內 `importlib.reload(executor_routes / strategist_promote_routes)` 重建 router 使 Depends 重新 freeze
- **Option B 不適用**：production code 改 Depends 會破壞 FastAPI introspection — Depends freeze 是設計語意，非 bug
- 0 production code 改動，2 test 檔 +42 -4 line

### 驗證
- 隔離跑：35/35 PASS
- Same-session（含 polluter）：53/53 PASS（test_api_contract 18 + executor 17 + strategist 18）
- 完整 control_api_v1：38 fail → 3 fail（剩 phase2_routes 3 個 out-of-scope per ticket bound）
- W1+W2+W3+SINGLETON regression（h_state + cognitive_integration + api_contract）：116/116 PASS

### 教訓
- **「Sibling-pollution family」不是單一機制** — 同 polluter (importlib.reload) 可觸發**多種**下游模式（attribute precedence、Depends freeze、可能還有更多未發現），future fix 不可預設「同 W3 fix pattern」即可
- **FastAPI Depends + importlib.reload 是已知陷阱**：`Depends(callable)` 在 route 建構期解 callable obj reference，後續 reload 換新 obj 不會傳遞給 frozen Depends
- **Test fixture pattern 必備**：任何 `_make_app(...)` style helper 凡 `app.dependency_overrides[base.X]`，若 sibling 可能 reload base，必先 reload route module 重建 router
- **PA+E1 合一適用情境**：root cause 簡單 + 改動 isolated test 端 + 已有 W3 fix 範本 — 跳過獨立 E1 派發省時，但**仍要驗 baseline 與規劃 fix option 對齊**才動手

### Follow-up（主會話）
- Commit + push 兩 test 檔 + 本報告
- Linux ssh trade-core 端再驗 53 PASS
- 補 memory `feedback_fastapi_depends_reload_freeze.md`（跨 session 偏好）

### 報告路徑
📄 `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--singleton_sibling_fix_executor_promote.md`

---

## 2026-04-28 G3-08-FUP-ANALYST-SPLIT P2 — analyst_agent.py 拆分

### 背景
Wave A LOSSES-WIRING (`aced662`) 加 +70 LOC 至 `analyst_agent.py` (874→944)，超過 §九 800 警告線。

### 設計
2 sibling 抽出（鏡 Strategist split / cost_edge_advisor_boot 範式）：
- `analyst_records.py`（142 LOC）：純 dataclass — `TradeRecord` / `PatternInsight` / `AnalystConfig`
- `analyst_pattern_claims.py`（264 LOC）：純函式 helpers — `KNOWN_STRATEGIES` / `extract_strategy_from_pattern` / `register_pattern_claims` / `record_pattern_observations`

### 結果
- `analyst_agent.py`：**944 → 781 LOC**（-17.3%，達 ≤800 首選目標）
- 0 production behavior change
- BWD-compat 4 機制：re-export + class-level alias + staticmethod delegator + instance method delegator
- LOSSES-WIRING callback 接線完整保留（Wave A `aced662` 不破）
- Mac pytest：spec 主測試 22/22 + 擴展回歸 146/146 + 廣度 166/166 全綠

### 教訓
- **Pattern claim helpers 完全 stateless**：原 instance method 看似緊耦 self，實際只讀 `len(self._records)` snapshot + 注入物件 → 可完全提為 module-level free fn，傳 keyword args 即可。Strategist split 已驗範式，此次 100% 重複利用。
- **Class-level frozenset 屬性**：移為 module-level `KNOWN_STRATEGIES` 常量 + class-level `_KNOWN_STRATEGIES = KNOWN_STRATEGIES` 別名，identity check `is` 通過，零 BWD 破壞。
- **Dataclass re-export 用 `__all__`**：明示 `from app.analyst_agent import TradeRecord` 等 import path 是 public API，未來若再拆分務必保此 re-export。

### 報告路徑
📄 `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--g3_08_fup_analyst_split.md`

## 2026-04-28 G3-08-FUP-HSQ-SPLIT P2 — h_state_query_handler.py sibling extraction

### 觸發
Wave E SINGLETON fix（commit `b579dae`）+33 LOC dual `sys.modules.get` pattern → handler 826→**859 LOC** 觸 CLAUDE.md §九 800 LOC 警告線。E2 SINGLETON review LOW-1 升 ticket。

### 抽法（PA + E1 + sanity test 三角合一）
新 sibling `app/h_state_collectors.py` 547 LOC（per E2 推薦 + cost_edge_advisor_boot.py split pattern）；handler 859 → **452 LOC**（首選 ≤800 47% under）。

抽 4 函式：`_collect_h_snapshots` / `_collect_agent_snapshots` / `_safe_snapshot` / `_safe_snapshot_self`（+ Wave E `sys.modules.get` 完整 28 行雙語 rationale 原子搬移）。
保留：`build_h_state_full_response` envelope + schema 常數 + `_is_gateway_enabled` env-gate + 完整 MODULE_NOTE。

### Re-export 策略（delegator）
handler 頂部 `from .h_state_collectors import _collect_agent_snapshots, _collect_h_snapshots, _safe_snapshot, _safe_snapshot_self  # noqa: F401`。所有既有 `from app.h_state_query_handler import _safe_snapshot[_self] / _collect_agent_snapshots`（test_h_state_query_handler.py 共 ~50+ patch sites）零修改透明工作。

### 驗證鏈
- `test_h_state_query_handler.py` alone: **90/90 PASS**
- `test_api_contract.py + test_h_state_query_handler.py` same-session: **108/108 PASS**（critical SINGLETON fix integrity — `_install_fake_strategy_wiring` dual patch 機制不破）
- W1+W2+W3 + Strategist 8 檔 regression: **234/234 PASS** 零退化

### 關鍵教訓
- **SINGLETON `sys.modules.get` 字串 literal**：`"app.strategy_wiring"` 這行字串是 fixture-vs-real-module 區分的唯一 anchor，移檔時 1 個 char drift 就會導致 35 個測試讀到 real STRATEGIST_AGENT (zero stats) 而非 fake；新 sibling 內 collector 兩函式各 1 處共 2 字串 literal 必須與原檔字字相符。
- **`noqa: F401` 註記不可省**：handler re-export 4 個 underscore-prefixed symbol 是給下游 test patch site 用，非自身使用；Python style checker 預設會誤報 unused，加 noqa 防 CI 紅。
- **CLAUDE.md §九 800/1200 雙閾值的 sibling extract pattern**：本次第 N 度驗證 — handler 從 859 切到 452 + sibling 547 是「兩半都遠低於 800」的乾淨例；若再加 H6 / 第 6 agent 自然在 sibling 內擴張、handler 仍維持 ≤500。下下次若 sibling 自身觸 800 → 按 H-buckets vs 5-Agent 二度拆。

### 報告路徑
📄 `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--g3_08_fup_hsq_split.md`

---

## 2026-04-28 PA+E1 G3-09-DAEMON-TEST-SPLIT P3 合一完成

### 任務範圍
- 拆 `test_cost_edge_advisor_daemon.rs` 1159 LOC > §九 800 警告線
- 三角合一：PA design + E1 寫碼 + sanity test
- 邊界：嚴格 test file split only，0 production code 改

### 結論（5+3+3=11 切分）
- **proofs.rs (534 LOC, 5 tests)**：Proof 1, 2, 3a, 4, 5 — daemon 核心活性 + cadence + cancel
- **dual_safeguard.rs (380 LOC, 3 tests)**：Proof 3b + sticky #1 + sticky #2 — RiskConfig 短路 + 時戳語意
- **spawn_decision.rs (485 LOC, 3 tests)**：FUP Case A/B/C — wrapper-decision parity
- 全 ≤ 800 LOC ✓ · Total 11/0 不變 · lib 2308/0（spec 寫 2299，sibling +9）· persistence 2/0 不變
- 共用 helper 採 **inline 重複** vs `tests/common/mod.rs` — 3 個小 helper × 3 檔 = 120 LOC overhead 可接受

### 教訓
- **Cargo `tests/*.rs` 獨立 binary env race 邊界**：跨 binary process 間 env 不共享，**`OnceLock<Mutex<()>>` 各檔自持是安全的**（無需共用 mutex instance）。糾正任務 spec 中「同 mutex instance 防 race」隱含假設 — 對單 binary 內 parallel test 為真，跨 binary 無意義
- **Test split module-level docstring 必須改寫**：新檔明確標 wave 中位置 + 互相 cross-reference 其他兩檔，避免 future maintainer 不知為何被拆
- **Inline helper 重複 vs tests/common/**：3 個小 helper × 3 檔 = 120 LOC overhead 可接受時 inline 比 Cargo subdir trick 簡單。閾值大概 5+ 檔或 helper > 200 LOC 才值得抽 common module
- **Lib test count drift 不是 regression**：spec 2299 vs actual 2308 — sibling session 在 spec 寫好後加 +9 lib test。判 regression 看 `0 failed` 而非 count number
- **PA+E1 合一適用情境**：純 test split + 0 production diff + 規格邏輯極清晰 — 跳過獨立 E1 派發省時，PA 自寫 Cargo binary 隔離分析 + 直接落地

### 報告路徑
📄 `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--g3_09_daemon_test_split.md`

---

## 2026-04-28 — G3-08-FUP-STRATEGIST-DELEGATOR-SLIM P3

### 任務
- 主會話派 PA+E1 合一執行 strategist_agent.py 933 LOC > §九 800 警告線瘦身
- 三角合一：PA design + 直接 lift body + 自寫 sanity test，worktree pattern 不 commit

### 結論（782 LOC，達 ≤800 首選）
- **strategist_agent.py 933 → 782**（-151 / -16.2%）
- 25 method delegator 壓 1-line（16 sibling + 4 H1/H4 + 4 cognitive + record_trade_outcome）
- 2 method body lift：`_produce_intents` (~80 LOC) → strategist_edge_eval.py / `record_trade_outcome` (~55 LOC) → strategist_cognitive.py
- E2 4-1 NIT-1 LOW 附帶：`_handle_intel` 5 early-return 補 `_invalidate_h_state_async` hint
- pytest spec 6 檔 98/98 ✅ / 廣度 251/251 ✅ / 0 production behavior change

### 關鍵技術發現：sibling stub 模式不能完全 lift class method
- **Spec 原建議**「sibling fn + module-level re-export」**對 method-level test patch 失敗**
- 22 處 test 用 `agent.method = MagicMock(wraps=agent.method)` — 純 module re-export 不創建 class attr → instance lookup `AttributeError`
- **正解**：class-level `def` 必留作 1-line delegator；瘦身靠「壓縮 def 形式」+「搬大 body」雙軌
- 範例 anti-pattern：直接 `from .x import _evaluate_edge` 後刪 class method → `agent._evaluate_edge` 取不到 callable wraps

### 教訓
- **Test patch 模式 `MagicMock(wraps=agent.method)` 是 BWD-compat 硬性 contract**：判斷 spec 「lift to module-level」是否可行，必先 grep `agent\.<method>\s*=\s*MagicMock` / `wraps=agent\.<method>`，命中即必保 class-level def
- **`# noqa: E704` 1-line def 是 LOC slim 合法工具**：E5 既有規範允許薄 delegator 此用法（pycodestyle E704 = statement on same line as def），標 noqa 比拆兩行省一半 LOC，header 區段 docstring 解釋意圖即可
- **Body lift 選 sibling 看 producer/consumer 凝聚度**：`_produce_intents` 依 `evaluation` → 進 strategist_edge_eval（與 producer 同檔）；`record_trade_outcome` 寫 `consecutive_losses` → 進 strategist_cognitive（與 consumer `tick_cognitive_modulator` 同檔）。**不要照「方法名前綴」分類，看資料流向**
- **Early-return hint 補完是純診斷利好**：env=0 時 0 負擔；env=1 時讓 Rust h_state cache 對「intel_received++ 但被拒絕」事件保鮮，避免 `intel_received` 動了 stats stale 的誤導。E2 NIT 級 LOW 推薦本 wave 一起做 ROI 高
- **PA+E1 合一適用情境再驗證**：worktree pattern + 純 refactor + 規格清晰 + 既有 sibling 已存在（不需設計新 sibling 結構）— 跳過獨立 E1 派發省時。本 ticket 是 Phase 4 後的「再瘦身」，技術風險已被前 wave 探明

### 報告路徑
📄 `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--g3_08_fup_strategist_delegator_slim.md`

---

## 2026-04-29 STRATEGY-NAME-ATTRIBUTION-CLEANUP design

### 觸發
PM operator 報告 GUI Learning tab 24h fills 顯示 demo bucket 25 個 distinct `strategy_name`、live_demo 9 個。實測 PG 確認 cardinality 來自 Rust dispatch 把 funding rate / basis / TRAILING peak / current pct / 6 浮點 trace 拼進 strategy_name（vs 設計上 enum-like 5 strategy）。

### 報告路徑
`workspace/reports/2026-04-29--strategy_name_attribution_cleanup_design.md` + `docs/CCAgentWorkSpace/Operator/2026-04-29--strategy_name_attribution_cleanup_design.md`

### 推薦結論
**Option A（schema migration + new column `exit_reason`）** — 16 emit point 規範 + V033 ADD COLUMN nullable + healthcheck [38] cardinality drift。**估 ~430 LOC / 15h 全鏈 / 4 sub-task isolation pattern**。

### 5 大關鍵架構發現

1. **動態 format!() emit 共 7 點**：funding_arb_exit (6 浮點) + risk_checks 5 條（HARD/DYNAMIC/TRAILING/TIME/TAKE PROFIT）+ halt_session 系列。其餘 9 個 close emit 是 static enum-like（fast_track / phys_lock / ipc_close）。grid_trading / bb_reversion / ma_crossover exit 已是 static 字串。
2. **真實破壞點是 strategist_history.effect**：`WHERE strategy_name = %s` 等值匹配對 close fill 永遠不命中 → 7d edge effect endpoint 從 day 1 就錯（讀 entry 0 元 realized_pnl，不是 close real PnL）。
3. **realized_edge_stats 已 immune**：FIFO pair entry/exit 時 exit 用 prefix detect (`strategy_name.startswith("strategy_close")`) 但**結果 strategy_name 取自 entry 端**，所以 dynamic suffix 不污染輸出。**這是 reusable pattern**。
4. **V031 mlde_edge_training_rows view 已 normalize**：CASE WHEN 把 raw_strategy_name → 5 enum；但 base table 是 trading.intents 不是 trading.fills（intents 寫入 strategy_name 是 entry-only enum）。所以 ML pipeline 自然不被 fills cardinality 影響；GUI passthrough 才暴露。
5. **trading.fills.details JSONB 欄位 V003 早已建但 trading_writer 不寫**：方案 B 走 JSONB 路理論上 0 schema cost，但 GIN index + JSON schema 維護成本超過新 column；本 audit 推 A 不推 B。

### 5 大次要技術發現

- 16 emit 點全集中 `tick_pipeline/on_tick/`、`risk_checks.rs`、`strategies/funding_arb.rs`、`tick_pipeline/commands.rs`、`event_consumer/unattributed_emit.rs`，跨檔但有焦點
- TradingMsg::Fill 加欄位是 compile-time enforced（destructure callsite ~5 處），漏一處 = compile fail，**比 JSONB 安全**
- healthcheck `LIKE 'risk_close:phys_lock_%'` 等 prefix-based 對 fix 後新 row 仍工作（phys_lock / fast_track 是 static prefix），只有 6 個 LIKE 需升級雙語法
- 7d 老 row 自然 phase out — 不需 backfill，rollback 完美
- E1 派發架構：W1-T1（schema + Rust enum，必 isolation）+ W1-T2（16 emit point，必 isolation）+ W1-T3（Python adapt，主樹）+ W1-T4（healthcheck upgrade，主樹）

### 16 原則對照

- ⭐ #8 交易可解釋：直接強化（enum + structured trace 比 dynamic format 易 audit）
- #1 / #3 / #4 / #5 / #6 全 ✅ 0 觸碰
- §四 5 項 live 硬邊界全保（authorization v2 / mainnet env / live_reserved 全不動）
- §七 V033 Guard A/B 強制（template 從 V021 複製，pre-existing pattern 已熟）

### 派發 schedule

| 子任務 | E1 instance | isolation | 依賴 | ETA |
|---|---|---|---|---|
| W1-T1 Rust schema + TradingMsg::Fill | E1-Alpha | YES | 無 | 8h |
| W1-T2 16 emit point 改寫 | E1-Beta | YES | T1 結束 schema 後可重疊 | 10h |
| W1-T3 Python adaptation | E1-Gamma | NO 主樹 | T1+T2 後 | 3h |
| W1-T4 healthcheck upgrade | E1-Delta | NO 主樹 | T1+T2 後（與 T3 並） | 3h |

Wall-clock：~10h parallel + E2/E4 ~5h = **~15h 全鏈**

### 沒做的事（E1/E2 領域）

- 沒寫 V033 migration（純 PA design + audit）
- 沒寫 Rust / Python 業務代碼
- 沒派 sub-agent（純 PA 主 agent 串行讀+寫）
- 沒跑 cargo test / pytest
- 沒擴範圍到 historical backfill（P3 backlog）/ V032 mlde_param_applications schema / G2-01 fee monitoring

### 教訓備忘

- **「動態 trace 拼進 enum 欄位」是反模式**：strategy_name 是 aggregation key（enum dim），funding_arb_exit / TRAILING STOP 動態 reason 是 free-text payload（trace dim）。混淆兩者破壞下游 GROUP BY / equality match / cardinality 衛生 — 屬 `feedback_no_dead_params` 的同族反模式。
- **Cardinality healthcheck 應該成為標配**：對任何「列 enum 的 column」（strategy_name / risk_verdict / exit_source / engine_mode），cron 6h 跑一次 `COUNT(DISTINCT)` = 1 SQL 即可釘死「字面值規範」這條 invisible contract，比逐個 emit 點 grep 強。
- **realized_edge_stats 的 entry-strategy 取法是 reusable pattern**：對「需要 exit prefix detect 但結果歸 entry strategy」的場景，**FIFO pair → 從 entry queue 取 strategy_name** 是 immune to suffix dynamics 的最優設計；未來相關場景優先套此 pattern。
- **view-layer normalize（V031）是好的補丁但不是根因解**：適合「writer 不能改」場景；可改 writer 時優先從根 normalize，view 是次選。

### 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|---|---|---|
| 2026-04-29 | strategy_name attribution cleanup design（推 A schema migration + new exit_reason col + healthcheck [38]）| workspace/reports/2026-04-29--strategy_name_attribution_cleanup_design.md |
| 2026-05-01 | Passive observation proactive plan + TODO archive audit（21d 規劃 34 任務 / 5 軸線；補回 9 active backlog；Top 10 派發優先序）| workspace/reports/2026-05-01--passive_observation_proactive_plan.md |

---

## 2026-05-01 · Passive Observation Proactive Plan + TODO 歸檔審計

### 任務背景

Operator 質疑：(a) PM 把 TODO 從 v3 (713 行) → v4 (197 行) 過程砍掉內容是否全為已完成 (b) 21d passive observation (2026-05-01 → 05-22) 沒真正規劃可主動推進的工作。PA 接手做 audit + 主動規劃。

### 結論摘要

- **歸檔內容無誤**（archive `2026-05-01--completed_waves_1_2_3_and_backlog.md` 完整覆蓋已完成 Wave 1-3 + 60+ backlog 項）
- **v4 漏 9 條 active 條目**（operator 6 條 + PA 額外發現 3 條：G7-04 Phase B/C wiring / STRATEGIST-AUTO-PROMOTE / STRK-FUP-HEALTHCHECK-PRE-EXISTING / ORPHAN-ADOPT-1 / IP-DEDUP-1 / G-7 ClaudeTeacher）
- **規劃 34 任務 / 5 軸線**，~28-35 PA/E1 工作日；並行壓縮 21d 內可完成 ~70%
- **最關鍵 3 行動**：(1) LG-2-RFC PA 1.5d (2) STRK-FUP-HEALTHCHECK-PRE-EXISTING design 1d (3) G4-03 Phase B 部署 3d

### 5 軸線拆分

1. **軸線 1 Wave 4 LG-2/3/4/5 PA Design**（PA 7.5d）：必須 P0-3 (~05-15) 之前寫好，否則 outcome A/C 啟動時阻塞 3-5d；即使 outcome B 也作為 dead-code-prevention 學習材料
2. **軸線 2 條件性獨立工作**（~17.5d）：G4-03 Phase B / G7-04 wiring / G8-05 / LEARNING-COCKPIT / STRK-FUP-HEALTHCHECK-PRE-EXISTING / 3 sibling splits / 2 P4 maintenance
3. **軸線 3 Pre-Live 基礎設施**（~7.5d）：Slack alert decision (~05-15) / HTTPS deploy / Dashboard 強化 / 災難恢復演練
4. **軸線 4 P0-3 決策會準備**（~4.5d）：Edge decision protocol / P0-3-01 報告 outline / agent pre-meeting briefs / adversarial review playbook
5. **軸線 5 Documentation/Test/Maintenance**（~4.5d）：live first-day SOP / Wave 4 deploy runbook / E2E live gate tests / 3 maintenance items

### 教訓備忘

- **「passive observation」不等於閒置**：21d 是準備密集期；CLAUDE.md §八 工作流編排 6 條第 1 條「規劃優先 Plan-First」+「規劃要前瞻」明示
- **PM 砍 TODO 容易誤殺 active backlog**：v3 backlog 表中沒打 ~~strikethrough~~ 的條目被同時砍掉；建議下次 TODO refactor 時 PA + PM 並行 audit，PA 從「active backlog 完整性」視角獨立掃過一次
- **依賴關係圖 / 時序表是架構性內容，不該砍**：即使重複也讓接手 agent 一眼看懂 phase；建議精簡保留而非全砍
- **RFC 寫得早 ≠ 浪費**：P0-3 outcome B 風險下 LG-2/3/4/5 RFC 部分作廢，但 (1) 文件結構保留 (2) 重啟時免重做 (3) 從「P0-3 後阻塞 3-5d」對比 7.5d 投入回報率仍正

### 沒做的事（E1/PM 領域）

- 沒寫業務代碼
- 沒直接 edit TODO.md（建議由 operator 審後派 PM 補）
- 沒派 sub-agent（純 PA 主 agent 串行讀寫）
- 沒派發 LG-2/3/4/5 RFC（建議在 operator 審後再派）

---

## 2026-05-02 · Step 2 Cold Audit — codex 4-day window

**Trigger**：CC step-1 cold audit 收 4 個 P1（5 SQL Guard A/B / stale grep test / .coverage / .codex governance）全 closed 後，operator 要 PA + MIT + QC + E3 並行 step 2 不依賴 commit message 自報的深層 audit。

**Window**：2026-04-28 → 2026-05-01，162 commit / 581 file / +64k LOC（22 Co-Authored-By Claude / 139 非 Claude）。

**Verdict**：0 P1 / 1 P2 / 4 P3。**不需要 stabilization wave**，接 PRE-LIVE-3 邊緣觀察軸線。

**Findings**：
- LOC-GOV-1 P2 — `tick_pipeline/commands.rs` 1343 LOC（baseline 1169）+ `scanner/scorer.rs` 1437 LOC（baseline 901）兩處 §九 1200 硬上限違反；都是 audit window 內把已在限內的檔推過界，不適用 pre-existing exception clause
- DRY-1 P3 — commands.rs 行 203/576 `is_legacy_close_tag` 4-line check 完全複製貼上（commit 854cae1 同時引入兩處）；可同 LOC-GOV-1 一起解
- SCANNER-PAPER-CMD-1 P3（pre-existing 不在 window 內惡化）— scanner 用 paper_cmd_tx query 開倉，PAPER-DISABLE-1 後 oneshot 永不 resolve → 2s timeout → 回空集合
- SCRIPT-PROC-1 P3 — `5db4e29` 引入 `/proc/<pid>/cwd` Linux-only 路徑識別，Mac 沒 /proc，違反 §七 ★★ 跨平台
- TEST-WATCHER-SLOT-1 P3 — live_auth_watcher_tests.rs 缺 end-to-end slot 寫入/清空 assertion

**驗證真接線（無 dead code）**：
- LIVE-AUTH-WATCHER slot pattern 全鏈完整：watcher teardown 清 → spawner closure 寫 → fan-out 每 tick read → IPC `live_snapshot()` try_read non-blocking → position_reconciler closure provider 動態讀 → strategist_scheduler `with_promote_cmd_slot` Arc clone
- close_sizing 接所有 close 路徑：commands.rs 3 處 + step_0_fast_track.rs 1 處
- scanner_snapshots 真有 producer：runner.rs:278 emit → trading_writer.rs:1025 collect → flush_scanner_snapshots 寫 PG
- STRATEGY-WIRING-SPLIT 拆分後 strategy_wiring.py:563/657-659 重新 bind module attribute，下游 grep 穩定
- Schema v2 authorization 雙端對齊：Rust + Python signer 都用 `version|tier|...|approved_system_mode|env_allowed_csv` payload
- per_trade_risk_pct 2%→3% 默認改動只動 Rust default，4 個 risk_config TOML 都顯式 override → 零 effective 改變

**架構 posture 整體健康**：
- Rust SSOT 守住（scanner / scorer / market_judgment 全 Rust；Python 純 normalizer + DB enrichment fail-soft）
- 16 根原則全保（live REST close fallback 移除 強化 原則 1；schema v2 + approved_system_mode 強化 原則 6 fail-closed）
- §四 硬邊界全保（live_execution_allowed / max_retries / OPENCLAW_ALLOW_MAINNET / authorization HMAC — 反而再收緊）
- 16 個新測試 / 0 刪測

**PA 經驗教訓**：
- 「不採信 commit message 自報 Verified ...」原則奏效：若採信則 LOC-GOV-1 P2 會錯過（commit message 沒提 LOC 增量）
- batch-a `b46660a` 13.6k LOC mass commit 真有風險點（schema v2 backward-compat），但 Python signer + Rust verifier 雙端同步 + `unsupported_version` fail-closed 是正確設計，運維已透過 renew 完成切換
- pre-existing 問題（SCANNER-PAPER-CMD-1）audit window 沒惡化即不阻塞接後續工作，但要在 ticket 系統登記避免遺忘
- Mac/Linux 跨平台 (CLAUDE.md §七 ★★) 容易在 helper_scripts 違反 — `/proc` / `lsof` / `ps -E` 差異要 platform guard

**派發建議給 PM**：
1. COMMANDS-RS-LOC-SPLIT P2 (解 LOC-GOV-1 + DRY-1) — PA→E1→E2→E4
2. SCANNER-SCORER-LOC-SPLIT P2 — PA+QC→E1→E2→E4
3. SCRIPT-PROC-1 P3 — E1→E2→E4 Mac+Linux smoke
4. TEST-WATCHER-SLOT-1 P3 — E1→E4
5. SCANNER-PAPER-CMD-1 P3 observe-first — MIT 加 7d healthcheck 再排修

**沒做的事（E1/PM 領域）**：沒寫業務代碼；沒直接 edit TODO.md；沒派 sub-agent（純 PA 主 agent 串行 grep）；沒 commit/push（PA 不寫碼不 commit）

**報告**：
- SoT: `/Users/ncyu/Projects/TradeBot/srv/.claude_reports/20260502_134432_pa_step2_audit.md`
- workspace mirror: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--step2_cold_audit_4day_window.md`

## 2026-05-02 · LG-5 Live Candidate Eval Contract RFC

Unified MIT-S2-2 (P2) + QC-S2-02 (P2) into single design spec at
`workspace/reports/2026-05-02--lg5_live_candidate_eval_contract_rfc.md`.

Core design:
- Producer (mlde_demo_applier._insert_live_candidate:587-622) adds payload.demo_cost_baseline + demo_realized_window + demo_attribution_chain_ratio sub-keys (no SQL change, JSONB extension)
- Consumer (new GovernanceHub.review_live_candidate) applies R1 cost regime check / R2 distribution-shift haircut / R3 PSR(0)>=0.95 / R4 multiple-testing deflation / R5 cost_edge_ratio bands (0.5/0.8) / R6 hard veto / R-meta attribution chain >=0.50
- Lease TTL bands: 6h default, 2h if R3 borderline, 1h if R5 warn band; auto-revoke triggers tied to [22]/[33]/[40]/[42]
- 24 pending candidates: bulk re-evaluate via lg5_re_evaluate_pending.py one-off script after IMPL-1+2 land

Implementation breakdown (5 sub-tasks):
- LG-5-IMPL-1 producer schema (E1, parallel safe)
- LG-5-IMPL-2 consumer + backfill (E1, blocked on IMPL-1)
- LG-5-IMPL-3 [42] healthcheck (E1, blocked on IMPL-2 audit)
- LG-5-IMPL-4 unit + integration tests (E4, can scaffold parallel after IMPL-1 schema)
- LG-5-IMPL-5 QC retro 7d post-deploy (QC, wall-clock gated)

Side-effect warnings logged for E2:
- governance_hub.py LOC budget (may need sibling file split)
- Lock contention: review_live_candidate must NOT hold _lock during DB reads
- Audit fail-closed mandatory (defer not approve on audit write failure)

Acceptance gate: PM + QC + MIT 三方 sign-off required before LG-5-IMPL-* dispatch.

Open questions logged for QC/MIT cross-review (R1 thresholds / R2 formula form / R3 sample window / R4 deflation method / R-meta interim threshold given MIT-S2-1 84.6% broken / lease TTL default).

Hard boundary check: untouched (live_execution_allowed / max_retries / OPENCLAW_ALLOW_MAINNET / live_reserved / authorization.json all preserved).

Root principle check: 16/16 preserved or strengthened (especially #3/#5/#6/#8/#10/#13).

---

## 2026-05-02 — LG-5 LIVE-CANDIDATE-EVAL-CONTRACT RFC v2 (12 must-fix + V035)

Path: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--lg5_live_candidate_eval_contract_rfc_v2.md`. Supersedes v1 (2026-05-02--lg5_live_candidate_eval_contract_rfc.md, kept as history).

吸收 12 must-fix:
- QC 7 (公式校準): MF-Q1 R1 floor 0.20→0.15 / MF-Q2 R2 加 clamp(0.3,1.0) + pass 1.5bps / MF-Q3 R3 window 7d-14d + n=100 / MF-Q4 R4 Bailey-LdP simplified SR_0 + trigger ≥5 / MF-Q5 R5 改用 demo gross 避 double-count / MF-Q6 R6 7-daily-snapshot 解讀 + R1 0.15 vs R6 0.10 floor 區分 + SQL pseudocode / MF-Q7 audit schema 18 欄位 raw input
- MIT 5 (結構性): MF-M1 §1+§11 重述 (MIT-S2-1 已 ship 2026-04-29 production 24h ratio 55.07%/today 68.97% 已過 0.50 binary gate, 真正 block 是 R6 hard veto live regime negative) / MF-M2 R-meta + payload 改 per-strategy dict (5 strategy keys + fallback defer_attribution_chain_strategy_unknown) / MF-M3 §2.2 status filter 改 status='candidate' AND application_type='live_promotion_candidate' / MF-M4 BLOCKER §13 從零設計 V035 governance_audit_log spec / MF-M5 healthcheck [42b]/[43] per-strategy 7d attribution drift PASS/WARN/FAIL=0.50/0.30/0.10

V035 spec (PA 從零設計, §13): TimescaleDB hypertable 7d chunk + Guard A 強制 (schema=learning + 23 必要欄位驗) + 2× Guard C (idx_gov_audit_candidate_ts + idx_gov_audit_event_type_ts via pg_get_indexdef substring 比對) + 23 個 bilingual COMMENT ON COLUMN + idempotent (psql -f ×2 無 RAISE) + optional fixture test sql/migrations/tests/test_v035_guards.sql 不阻塞。E1 IMPL-V035 直接從 §13 落 srv/sql/migrations/V035__governance_audit_log.sql 無設計餘地。

§11 v1 8 條 open Q 全部拍板:
1. R1 0.85 ratio 維持 + floor 0.15
2. R2 multiplicative + slippage 相減 + clamp; Bayesian shrinkage 留 IMPL-5 retro 後評估
3. R3 PSR 0.95 + window 7d/14d + n=100
4. R4 Bailey-LdP simplified SR_0
5. R-meta per-strategy dict; MIT-S2-1 已 ship 不再 block all promotions
6. Lease TTL default 6h + first 30 days post-deploy 全局 cap 2h (learning period)
7. Audit sink = learning.governance_audit_log (V035)
8. Bulk re-eval 24 candidates 數據 gap 接受 fail-closed (defer)

PM 派發建議 (新 §14):
- Wave 1 並行: V035 + IMPL-1 (~0.5d, 完全 independent — SQL vs Python producer)
- Wave 2 並行: IMPL-2 + IMPL-4 unit/fixture shells (~1.5d, blocked on Wave 1)
- Wave 3 並行: IMPL-3 + IMPL-4 integration finish (~0.5d, blocked on IMPL-2)
- Wave 4: IMPL-5 7d retro (QC analysis only, blocked on Wave 3 deploy + 7d wall clock)
- 唯一序列瓶頸: V035/IMPL-1 → IMPL-2

E2 重點審查 3 點: GovernanceHub LOC budget ≤1500 (已升 hard cap, governance_hub.py 加 ~400 LOC 大概率超界, 需 split sibling) / Lock contention (review_live_candidate 不在 self._lock 持鎖期間 DB read) / Audit fail-closed (audit write failure 真回 defer 非 silent swallow)

Hard boundary check: untouched (live_execution_allowed / max_retries / OPENCLAW_ALLOW_MAINNET / live_reserved / authorization.json 全保留)。
Root principle check: 16/16 preserved or strengthened (#3/#5/#6/#8/#10/#13 各 strengthened)。

不確定處: 0 (operator 已 ack per-strategy 改動 + V035 PA 從零設計 + PM/QC/MIT 已決定 12 must-fix; v1 8 open Q 全部拍板)。

---

## 2026-05-02 — LG5-W3-FUP-2 Fix 2 R-meta Window 7d→3d Amendment RFC

Report: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--lg5_w3_fup2_fix2_r_meta_window_3d_amendment_rfc.md`

Trigger: MIT FUP-2 diagnosis 顯示 7d window 含 4/24-28 attribution_chain_ok 結構 bug 期殘留 sample，over-penalizing 當前 promotion candidates (grid 7d 14% vs post-4/30 39.6%)。

Design summary (10 章節):
- 不拆 `_DEMO_BASELINE_WINDOW_DAYS=7` rename，純加 `_R_META_WINDOW_DAYS=3` 新常數（PA 推薦 Open Q1 答 B 保守版）
- producer `_compute_attribution_chain_ratio_by_strategy` SQL 改 3d；payload 加 `demo_attribution_window_days=3` sub-key（schema_version 不 bump）
- consumer R-meta evaluator 邏輯不變；audit row payload_snapshot echo `demo_attribution_window_days`
- healthcheck 拍板：`[42b]` 維持 7d long-window observability + 新 `[42c]` 3d gate-aligned mirror（雙窗）
- 不動：R3 PSR window (7d/14d Q3 拍板)、R5 cost_edge_ratio 公式 (Q5 demo gross 拍板)、R_META_RATIO_FLOOR=0.50

Backward compat: 既有 27 pending candidates 沿用 v1 7d 評估（payload 缺 window_days sub-key → consumer default 7）；新 candidate 用 3d；**預設不 bulk re-synth**（PA 推薦 Open Q2 答 A）。

Side-effect highlight: bb_breakout (~30→13) / bb_reversion (~6→3) cardinality 稀薄；推薦加 `_R_META_MIN_SAMPLE_PER_STRATEGY=10` + 新 `defer_attribution_chain_low_sample` reason 區分「strategy 真壞」vs「樣本不足」（PA 推薦 Open Q3 答 A）。

IMPL 派發（4 sub-task / wall ~8h）:
- IMPL-1+2 (E1, ~30+10 LOC, group A 同檔合併): producer SQL window + payload sub-key
- IMPL-3 (E1, ~50 LOC, group B 獨立檔): healthcheck `[42c]`
- IMPL-4 (E4/E1, ~80 LOC, group C 跨 3 test 檔): unit tests for IMPL-1/2/3
並行性：A+B Round 1 並行；C Round 2 依賴 Round 1；E2 review parallel 3 PR；E4 SSH Linux regression sequential。

Acceptance gate: **只需 PM Sign-off**（QC 已 sign-off R-meta 公式 + 0.50 floor / MIT 已 sign-off per-strategy structure / Fix 2 純 window 縮放不改公式不改邊界）。

Open questions for PM: Q1 rename vs additive constant / Q2 bulk re-synth pending policy / Q3 sample threshold fallback。

Hard boundary check: 0 violation（live_execution_allowed / max_retries / OPENCLAW_ALLOW_MAINNET / live_reserved / authorization.json 全保留）。
Root principle check: 16/16 全合規 + 加強原則 #6 #8 #12。

---

## 2026-05-03 — REF-20 Wave 1 R20-P0-T2 + T3 + T9 合併 deliverable（replay_runner scaffold）

PM 派發 V3 Wave 1 三 task 合併同一 PA owner：
- T2 = `replay_runner` Rust binary scaffold（spec only）
- T3 = `ReplayProfile::Isolated` cfg gate 設計 review
- T9 = `replay_runner` crate 邊界白名單 + E2 sign-off

**Wave 1 Exit Criteria 嚴守**：spec only / scaffold only / 0 runtime IMPL。Compiler 過 + 0 new warning。

### Deliverable 5 件

| # | File | LOC | 性質 |
|---|---|---:|---|
| A | `rust/openclaw_engine/src/bin/replay_runner.rs` | 117 | binary scaffold；`#![cfg(feature = "replay_isolated")]` + `panic!("REF-20 P2b-S7/S8 will land runtime; this is Wave 1 scaffold only")` + 4 條 TODO marker（P2b-S7/S8/S9/S10）+ 雙語 module-level doc + 完整 forbidden/allowed list 注釋 |
| B | `rust/openclaw_engine/Cargo.toml` | +24 LOC | 新 `[features] replay_isolated = []` 純 marker（0 deps）+ 新 `[[bin]] replay_runner` with `required-features = ["replay_isolated"]` |
| C | `rust/openclaw_engine/src/replay/profile.rs` | 116 | `pub enum ReplayProfile { Live / LiveDemo / PaperLegacy / Isolated }` 純宣告 + `#[allow(dead_code)]` + 雙語 doc（每 variant 含「為何」+ invariant）+ 0 impl 0 method body |
| D | `rust/openclaw_engine/src/replay/mod.rs` + `lib.rs +5 LOC` | 30 + 5 | 新 `pub mod profile;` + lib.rs 加 `pub mod replay;` 並附 Wave 3 forward-looking comment |
| E | `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--replay_runner_crate_boundary_allowlist.md` | 18.6KB | Crate allowed/forbidden 雙欄列表（每項 V3 / workplan / CLAUDE.md ref）+ nm/objdump CI script + 雙層 cfg gate 設計 + 15 條 E2 sign-off ready checklist + 5 條 ambiguity for PM clarify |

### `cargo check` 兩次驗收

| 變體 | 結果 | 說明 |
|---|---|---|
| `cargo check -p openclaw_engine`（無 feature） | ✅ PASS | 21 lib + 3 bin warnings = pre-existing baseline；replay_runner **未編譯**（required-features 阻擋）— compile-time isolation 證明 |
| `cargo check -p openclaw_engine --bin replay_runner --features replay_isolated` | ✅ PASS | 21 lib pre-existing baseline；replay 三檔（profile.rs / mod.rs / replay_runner.rs）**0 new warnings** |
| `cargo build -p openclaw_engine --bin replay_runner --features replay_isolated` | ✅ PASS | 產 artifact；run 會以預期訊息 panic |
| `grep -E '^use |^extern crate' replay_runner.rs profile.rs mod.rs` | 0 hit | 0 import 0 extern crate — 純 spec |

### 雙層 cfg gate 設計（V3 §7.1 #2）

- 第一層 = compile-time `replay_isolated` feature gate（binary 預設不編入 graph，避免 4-feature × 多 mode = matrix 爆）
- 第二層 = runtime `ReplayProfile` enum（Wave 3 IMPL 加 `requires_lease()` / `enforce_isolated_or_panic()` method）
- CI 只需 2 build target：(a) default no-feature / (b) `--features replay_isolated`

### 派發給 Wave 3 R20-P2b-S7/S8/S9/S10 的 5 條 ambiguity（PM 派發前 clarify）

1. `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA` 命名（41 字 vs 建議 14 字 `OPENCLAW_REPLAY_MAC_NO_PRIVATE`）
2. `tokio` feature subset 限定 `rt-multi-thread + macros`，是否允許 `tokio::time`
3. `canonical_config_parser` reuse 既有 `crate::config` 讀端 vs fork 子集（read-only assert lint 配套）
4. `ReplayProfile::requires_lease()` 預期語意（Isolated => false / 其餘 => true）
5. CI runner 平台（`nm -gU` macOS 兼容）

### Hard boundary check

0 violation：
- ❌ 未觸 `live_execution_allowed`（Python concept，replay binary 永不 reach）
- ❌ 未觸 `max_retries=0`（hard boundary 不變）
- ❌ 未觸 `OPENCLAW_ALLOW_MAINNET`（feature 純 marker）
- ❌ 未觸 `live_reserved`（無 Python 改動）
- ❌ 未觸 `authorization.json`（無 live_authorization write 路徑）
- ❌ 未觸 `decision_lease`（Python 唯一 caller，replay 不接 GovernanceHub）

### Root principle check（16 條）

✅ 16/16 — 加強原則 #1（單一寫入口：replay 物理上不可能寫；compile-time 阻擋）+ #2（讀寫分離：feature gate）+ #4（策略不繞風控：replay 不進 intent dispatch）+ #6（失敗默認收縮：scaffold panic）+ #7（學習 ≠ 改寫 Live：crate boundary 強制）。

### Side-effect identification

- ✅ 既有 `cargo check`/`cargo build` 行為 0 變動（replay_runner 預設不編）
- ✅ 既有 21 lib warnings = pre-existing baseline，未添 1 條
- ✅ `lib.rs` 加 `pub mod replay;` 不影響其他模組（replay 無 dep on engine 任何 module）
- ✅ Cargo.toml 加 features + 1 bin entry，現有 `openclaw-engine` / `repair_migration_checksum` 0 變動
- ⚠️ Wave 3 R20-P2b-S7 IMPL 派發後：`nm` CI script 需在 Linux/macOS 雙平台驗證；macOS `nm` 默認行為差異（不顯示 undefined symbols）需 `-gU` flag 處理

### E2 sign-off readiness

15/15 checklist 全 ✅（report §7）。E2 必查 3 點（per workplan §8）：
1. `grep -rE 'acquire_lease|ipc_server|build_exchange_pipeline' replay_runner.rs replay/` Wave 3 IMPL 後 0 hit
2. `nm target/release/replay_runner | grep -E 'acquire_lease|build_exchange_pipeline|ipc_'` 0 hit
3. Wave 3 unit test 4 fail-mode（Wave 1 不要求）

**APPROVE FOR E2 SIGN-OFF.** PM commit message 草稿：`feat(replay): scaffold replay_runner binary + ReplayProfile enum spec (REF-20 Wave 1 R20-P0-T2/T3/T9)`

---

## 2026-05-04 PA — REF-20 Sprint A 設計派工（Sprint A R1+R2+R3）

**Trigger**: plan `2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md` (commit `a4ea3571`) Sprint A scope 派工設計。

**4 個 gap 已被 PM pre-flight 證實**：
1. P0-2 binary path bug — `route_helpers.py:138/143` 找 `rust/openclaw_engine/target/...` 但實際 `rust/target/...`（cargo workspace layout）。
2. audit script 同 bug — `replay_runner_symbol_audit.sh:91` `RUST_CRATE_DIR/target/release/`。
3. `/api/v1/replay/health` 404 — 只有 `/health/signature`（line 1336）存在。
4. `replay.experiments / run_state / report_artifacts / simulated_fills / handoff_requests / mlde_replay_veto_log` 6 表全 0 rows（Linux PG 直查確認）。

**設計要點記錄**：

- R1 4 sub-tasks file 互不重疊 → 不需 worktree isolation；可派 1-2 E1 並行。
- R2 高風險：當前 `/run` 用 `uuid5(experiment_id)` 自衍生 `manifest_id` 寫入 `replay.run_state`，但**從來沒 INSERT `replay.experiments` 任何行**；V052 FK redirect 是 vacuously true（兩表都 0 行）。R3 一旦真跑會撞 FK constraint。R2 必先於 R3 land + deploy。
- R2 LOC 估算：`replay_routes.py` 當前 1494 LOC + R2 預估 +160 LOC = 1654 LOC，**越過 baseline+5（1499+5=1504）邊界 150 LOC**。**必拆**：R2-T1 抽到 `replay/experiment_registry.py`（沿 `route_helpers.py` 模式）；R2-T3 verify SQL archive 拆到既有 `manifest_signer.py`。
- R3 是純串行，依 R1+R2 完成後才能跑；不可並行。
- R2-T3 拿掉 `OPENCLAW_REPLAY_VERIFY_TEST_KEY` 改走 secrets file fallback（`$OPENCLAW_SECRETS_DIR/<env>/replay_signing_key`），不選同次 land V042 SQL archive（會把 sprint 變 1500 LOC migration，scope creep）。
- R1-T3 `/api/v1/replay/health` auth 政策 = `Depends(base.current_actor)` 已登入即可，**不 require_scope_and_operator**（與 `/health/signature` line 1336 對齊；plan §6 R1 acceptance "behind the intended auth policy" 即此意）。

**Hidden risk 結論**：
- Decision Lease retrofit feature flag OFF + replay 子系統不走 IntentProcessor → router gate → R2 改動**不會**誤觸 lease（grep `acquire_lease|release_lease` symbol_audit.sh:226 為 0 是回歸線）。
- 14d observation 期間 Sprint A 改動會讓 metric 從 vacuous truth 變 evidence；observation 可在 Sprint A 結束後重啟計時。
- V049-V054 schema 已 deploy，R2 不需新 migration，但 INSERT col list 必對 V049 22-col contract 全 enumerate。

**5 Open Questions 留 PM 決定**（已寫入報告 §6）：
1. R1+R2 同 sprint 還是分 sprint（PA 推薦分波，3 cycle 各 1 day）。
2. R2-T3 SQL archive vs secrets file fallback（PA 推薦 secrets file，V042 留 P2 ticket）。
3. R3 後是否立即啟動 Wave R4 UI 啟用（PA 推薦 至少間隔 1 sprint）。
4. Sprint A 是否拉 QC 介入 R2-T1 manifest schema（PA 推薦 1h soft consult，非強制）。
5. Decision Lease flag flip 是否疊 Sprint A（PA 答 NO，不疊 deploy 視窗）。

**Report**: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-04--ref20_sprint_a_task_dag.md`
**File overlap warning**: `replay_routes.py` baseline+5 violation 風險 → R2 LOC 拆解設計已含於報告（無 PM override 不可 land）。


## 2026-05-05 PA — REF-20 Sprint A R3 Round 6 Task DAG（real HMAC + stderr capture + fixture provisioning）

**Trigger**：QA round 3 e2e smoke 揭第 4 層 blocker — `route_helpers.build_default_manifest_payload` 寫 placeholder signature/hash → Sprint 1 Track B fail-closed verifier 拒 → subprocess exit=1 → V046/V050 永遠 0 row。

**根因 stack（按 spawn 時序）**：
1. P0-NEW Placeholder signature collision — `placeholder_signature_wave6_v042_pending` + `placeholder_hash_wave6_v042_pending`（route_helpers.py L669-670）vs Rust `manifest_signer.rs:548-557` fail-closed sibling key.hex 缺即 hard error；即使 round 5 cp key.hex 進 output_dir，placeholder sig != HMAC(canonical_body, real_key) → SIGNATURE_MISMATCH。
2. P0-NEW-INFRA stderr DEVNULL silent-dead — `route_helpers.spawn_replay_runner:549` `stderr=subprocess.DEVNULL`；任何 spawn fail 都需 ssh manual reproduce → 違反 CLAUDE.md §九 silent-dead 反模式。
3. P2-A-NEW fixture_uri env — API process 仍缺 `OPENCLAW_REPLAY_FIXTURE_URI` 自動 fixture provision。

**4-Task 設計（R3-R6-T1/T2/T3/T4）**：

| Task | scope | LOC est | parallel? |
|---|---|---|---|
| T1 | `route_helpers.py::write_manifest_fixture` 真 HMAC sign（重用 R2-T3 `load_signing_key_from_secrets_dir` + `compute_manifest_canonical_bytes` + `compute_body_hash` + `ManifestSigner.sign`） | +85 | ❌ T1+T2+T3 同檔 |
| T2 | `route_helpers.py::spawn_replay_runner` stderr→file + post-mortem read | +50 | ❌ |
| T3a | restart_all.sh::restart_api() 加 export `OPENCLAW_REPLAY_FIXTURE_DEFAULT` + route_helpers fallback | +25 | ✅ 跨檔 |
| T4 | tests（unit×3 + integration×1）+ E3 path allowlist 重審 | +250 | ✅ 跨檔 |

**派工順序（serial 4 個 E1 commit）**：
- Commit-1：T1+T2 同 E1（同檔 LOC ≤+135 接 baseline 1249→1384，仍 < 1500 硬限）
- Commit-2：T3a 另一 E1（跨檔，可與 Commit-1 同時派但需等 Commit-1 land 才能 e2e 驗）
- Commit-3：T4 第三 E1（純 test 可並行 Commit-2）
- 串聯總 LOC：route_helpers.py 1249 → 1384（warning line 800 已破，但 wave 4 P2b-T2 已知接受；本 round 不加新警告）

**T3 (a) vs (b) 推薦 = (a)**：
- (a) restart_all 加 env export：對 production deploy + dev smoke E2E 都有效；不破 build_default_manifest_payload 既有 default `<output_dir>/fixture.json` semantic；不額外做 disk I/O（避免 cp 100MB+ fixture）；對 R4 UI integration 路徑也直接生效。
- (b) write_manifest_fixture 自動 cp：多了一個 mkdir+copy 的失敗點；fixture_uri 從 hint 變強制；違背 manifest_jsonb 不可變式（client 提供的 fixture_uri 被靜默改寫）。

**簽名 key 來源優先級（T1）**：(a) `OPENCLAW_REPLAY_SIGNING_KEY_FILE` env override（dev/test 直接指 `key.hex`）→ (b) R2-T3 `load_signing_key_from_secrets_dir(env_label)` → (c) None → 寫 fail-closed marker 並回 ValueError 讓 caller 路徑進 503。**永不 fallback 回 placeholder**。dev/test smoke 路徑用 (a) 指 fixture key.hex；production live path 用 (b) 經 secrets_dir live profile 守門。

**key.hex sibling 寫入語意（T1）**：write_manifest_fixture 在 sign 完成後 sibling write `<output_dir>/key.hex`（覆寫 round 5 cp 的副本，內容相同字節）；permission 寫 0o600（Mac umask 022 default 0o644 + Linux secrets dir 期望 0o600）；test override path（OPENCLAW_REPLAY_SIGNING_KEY_FILE）下 cp 來源 file content；secrets_dir path 下 hex-encode 從 32-byte raw key 重生成 file content（含 trailing newline 對齊 generate_replay_signing_key.sh：90/93/111 fingerprint 算法）。

**Hidden risk**：
- canonical_bytes contract drift — 必重用 既有 helper，禁複製 sort_keys/separators kwargs。
- Pre-existing baseline exception clause (CLAUDE.md §九)：route_helpers.py 1249 → 1384 增 +135，未越 baseline+5 或 1500 硬限。
- Mac/Linux portability：`os.chmod(0o600)` 在 Mac/Linux 都正常；fixture key.hex 已 git tracked 兩平台一致。
- multi-worker uvicorn race — M-1 V045 FOR UPDATE 已修，本 round 不重複；T1 是 process-internal sign 不涉跨 worker 共享。

**E2/E3/E4 重點**：
- E2：(1) T1 簽名 key fallthrough 順序逐條對齊（不 fallthrough placeholder）；(2) T2 stderr_path 經 artifact_path_within_allowlist 守門；(3) canonical bytes contract 重用而非複製。
- E3：path allowlist 對 stderr_path + key.hex sibling write 兩條新 disk write 路徑審計（T3 a 不寫 disk 跳過）。
- E4：(1) integration test mock PG + 真 spawn replay_runner 端到端 4 表 row > 0（V045/V046/V050 + V054 audit）；(2) round 3 mock-only 假綠教訓（test 必 spawn 真 binary）。

**PM open question 答案**：
1. T3 (a) — 已答。
2. 簽名 key 優先級 (a)→(b)→fail-closed — 已答。
3. key.hex 寫 disk 0o600 — operator pre-deploy 問是否影響 Mac dev / 答：no, restart_all run-as-user 即可寫；dev mode 下 0o600 一樣有效。
4. LOC 拆檔 — 1384 < 1500 硬限不必拆；若 R4 啟動 UI subtab 再評估抽 manifest_provisioning.py。

**預期 R3 Round 6 commit 後 4 表達成路徑**：
- V045 replay.run_state — pid + status='running' + completed_at + exit_code=0（spawn-then-poll 後 wait runner finish）
- V046 replay.report_artifacts — replay_report.json 落盤 + INSERT 1 row
- V050 replay.simulated_fills — runner walks fixture 6 events + INSERT N rows（evidence_source_tier='synthetic_replay'）
- V054 replay.audit_trail — register/run/finalize 三 audit emit 各 1 row



## 2026-05-05 PA — REF-20 Sprint B Task DAG Design (R4 UI Enable + R5 Real Decision/Risk Replay Path)

**Trigger**: PM 派發 Sprint B scope (R4 + R5) per `2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md` plan §6/§9.

**Critical PA push back**: Sprint B should NOT be a single sprint covering R4+R5。**強烈建議切 B1（R4 + R0-T0 LOC budget release）+ B2（R5 grid_trading + ma_crossover pilot）**。理由：
1. R5 涉 5 strategy + IntentProcessor 8-Gate pipeline architectural refactor，觸 GovernanceHub SM / Lease / paper_state 任一接縫；
2. 既有 `replay_runner` runner.rs 刻意不接 IntentProcessor（V3 §6.2 forbidden list vs §6.1 「可共用 strategy/risk」張力未解），R5 必先 carve pure decision path；
3. replay_routes.py 1500 LOC EXACT cap（0 margin）— 必先拆 thin handler（R0-T0 0.5-1d）；
4. Sprint A 8-commit chain 顯示「即使簡單 IMPL 也會 6-layer blocker」，R5 複雜度 2-3 倍。

**設計核心結構**：
- §1A Strategy call graph：5 strategy 的 `Strategy trait` 本身 0 副作用（pure on `(IndicatorSnapshot, prices, signals)` → `Vec<StrategyAction>`）— 直接 `Box<dyn Strategy>` 復用即可，0 trait 改動。
- §2 Risk call graph：`IntentProcessor::process_with_features` 8-Gate（1.0 auth / 1.4 lease / 1.5 dup / 1.6 neg balance / 2.0 Guardian / 2.5 Kelly / 2.6 P1 cap / 2.7 admission）。其中 1.0/1.4 必跳過（plan §4 hard boundary）；其餘 6 個由 `Guardian / check_order_allowed / compute_kelly_qty` 純函數重做即可。
- §4.1 ReplayStrategyAdapter：~150 LOC 新檔 `replay/strategy_adapter.rs`，wrap `Box<dyn Strategy>` + 紀錄 trace；profile fail-closed `Isolated`-only constructor。
- §4.2 ReplayRiskAdapter：~250 LOC 新檔 `replay/risk_adapter.rs`，重做 6-Gate mini-pipeline（不共用 IntentProcessor），加 `ReplayPaperState` 純 in-mem struct（不接 `crate::paper_state::PaperState`）。
- §6 evidence schema：**reuse `simulated_fills.payload jsonb`**（V050 既有 column），不新加 V### migration。rejected intent 寫 simulated_fills with `qty=0.0` 保 lineage。
- §8.1 LOC: replay_routes.py 1500 EXACT — Sprint B 第一手必拆 R0-T0 sub-router（4 endpoint /run /list /health /status 各 ~250 LOC）。
- §8.2 indicators 處理：fixture builder 預計算 → 寫 fixture.json events[i].indicators 子鍵；replay binary 直讀，不接 KlineManager singleton。
- §11 LOC 估算：R4 ~310 LOC + R5 ~1500 LOC = ~1810 LOC total（含 ~1300 test LOC）。

**Wave 結構（R5 假設拆 B2）**：
- W1 並行 4 task（T1 strategy_adapter / T2 risk_adapter / T5 simulated_fills_writer / T6 experiment_registry）— 4 sub-agent 並行 ~1d wall
- W2 序列 2 task（T3 runner.rs rewrite → T4 replay_runner.rs main）~0.75d
- W3 並行 2 test task（T7 strategy adapter integration + T8 parameter-delta proof）~1d
- W4 序列 E2/E4 review ~0.5d
- 總 wall ~3.25d for B2 / ~1.5-2d for B1

**Hard boundary check**: 0 violation
- replay 物理上 0 接 lease / IPC / mainnet / bybit / live_authorization / decision_lease
- ReplayProfile::Isolated.requires_lease=false 強制
- forbidden_guard.rs runtime symbol audit 防 import 越界

**16 root principle check**: 16/16 — 加強 #1/#2/#3/#4/#6/#7/#8

**10 PM open questions**：(1) sprint 切分；(2) Rust vs Python；(3) pilot vs full 5；(4) jsonb vs new table；(5) reject intent 寫不寫；(6) indicator 預計算 vs 重算；(7) R6 fee 加不加；(8) lease flag canary；(9) QC consult；(10) wholesale replace synthetic walker。

**E2/E4 重點 3 點**：(1) R5-T1/T2 import audit grep 無 paper_state/canary_writer/ipc_server/bybit；(2) R5-T3 IsolatedPipeline 0 silent fallback；(3) R5-T6 canonical_bytes contract reuse 不複製 sort_keys/separators kwargs。

**Report**: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-05--ref20_sprint_b_task_dag.md`
**Status**: design ready，awaits PM Q1 拍板（切 B1+B2 vs single B），其餘 9 OQ 並行回。


## 2026-05-08 PA — 12 Audit 整合修復計劃（W-AUDIT-1~7）

**Trigger**: PM 派 12 audit cold review 整合（FA/AI-E/E5/E4/E3/CC/QC/MIT/BB/TW/R4/A3）→ 88 finding 去重 → 7 wave 派工 DAG。

**88 finding 分佈**：Critical 8 / High 28 / Medium 22 / Low 18 / Advisory 12（去重前 142 → 去重後 88）

**Top 30 verified rate**：80% ✅ VERIFIED (24/30) + 13% ⚠️ PROBABLE (4/30) + 7% ❌ DISPUTED/OUTDATED (2/30)

**6 個跨 agent 共識 Critical**：
1. K-1 ExecutorAgent shadow_mode `lambda: True` + TOML × 3 全 true（FA/CC/E5/E4/AI-E 5 共識）— ✅ verified
2. K-2 CLAUDE.md §三 lease flag default OFF stale 5 day（FA/CC/R4/E4/TW 5 共識）— ✅ verified runtime `=1`
3. K-3 lease_transitions audit channel 寫端 wiring 死綁（E3/FA/E5/MIT 4 共識）— ✅ verified spawn_lease_transition_pipeline 0 caller
4. K-4 H0_GATE Python 0 production caller（FA/E4/E5/E3 4 共識，E3 解釋更精確：Rust h0_gate active hot path）— ✅ verified
5. K-5 5 策略 7d gross net negative；CLAUDE.md §三 -6.98 stale（FA/QC/AI-E/CC 4 共識）— ✅ PG 直查 demo 7d -26.44 USDT
6. K-6 ❌ DISPUTED LG-5 reviewer 0 audit row — PG 22,790 row（reviewer 已 deploy active）；FA/CC/E5 引用 stale

**7 個 Wave 設計（總 ~140h / 8-14 session / 6-8 sprint）**：
- W-AUDIT-1 文檔同步（4.5h，TW+R4+PM+PA 4 sub-agent 並行）— 解 F-02/F-19/F-14/spec-reg/script-idx
- W-AUDIT-2 安全 + 認證硬補（7-8h，E1×4 並行）— 解 F-23/F-24/F-25 + F-03 partial
- W-AUDIT-3 ExecutorAgent fake-live + decision spine（10h，2 session）— 解 F-01/F-15/F-17 + 部分 M-9
- W-AUDIT-4 ML 基座 + dead schema（30h，3 session）— 解 F-08/F-09/F-11/F-16/F-22/F-29 + 部分 M-2/M-3/M-10
- W-AUDIT-5 性能 + 結構（17+17h，2 session）— 解 F-12/F-20/F-21/F-26/F-27 + 部分 M-5
- W-AUDIT-6 策略 + 量化（30h，3 session）— PM 5 策略決策 + DSR/PBO promotion gate + 5 策略 IMPL
- W-AUDIT-7 AI 棧 + GUI（25h，2 session）— 解 F-07/F-28/F-30 + 部分 A3 30 issues

**5 個 PM 必拍板決策（PA push back）**：
1. AMD-2026-05-02-01 §5.4 流程搶跑 — 立即補 W-C 操作授權檔 + amendment §5.4.1（不可放過合規）
2. shadow_mode TOML × 3 設計意圖鎖定 — PA 推薦 (a) 「demo TOML 是 W-A demo fail-close」+ 補 SM-05 spec
3. CLAUDE.md §三 數值 vs runtime drift 防線 — PA 推薦 (i) 把 runtime 數值搬出 §三 + (ii) 7-day cron
4. 5 策略決策（QC verdict 4/5 REJECT）— PA 推薦 (ii) grid CONDITIONAL / ma REVISE / bb 1m→5m / funding RETIRE / bb_reversion pair
5. openclaw_core 9 模組 + Layer 2 14 天 0 動作 sunset — PA 推薦 ADR-0015 永久 sunset + W-AUDIT-5 P2 drop

**4 條 PM 簽收的 hard truth**：
1. 88 finding 至少需 6-8 sprint 才達 supervised live；不可 1-2 sprint 速通
2. 5 策略 net negative 是結構性問題（QC 4/5 REJECT or REVISE）
3. AI 棧 cost = $0 / cost_edge_advisor 0 row / Layer 2 0 流量 — advisory-dormant 真實狀態
4. CLAUDE.md 治理規則執行不徹底（§七 7-day rule + §九 hard cap 違反）

**核實過程**：
- ssh trade-core PG 直查 4 critical 表（lease_transitions=0 / governance_audit_log=22790 / cost_edge_advisor_log=0 / ai_usage_log=0 / feature_baselines=0 / directive_executions=0 / agent.messages=2 / state_changes=11 / ai_invocations=2）
- engine env 取 OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1 + OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow（驗 K-2）
- grep `H0_GATE.{check,evaluate,decide}(` Python 0 hit / Rust step_0_5_h0_gate.rs:41 active（驗 K-4）
- grep `lambda: True` executor_agent.py:223-224（驗 K-1）
- TOML × 3 shadow_mode = true（驗 K-1）
- restart_all.sh:489 + clean_restart.sh:390 `--host 0.0.0.0`（驗 F-23）
- phase4_routes.py:822/832 0 actor / scout_routes.py:325/431 0 require_operator（驗 F-24/F-25）
- PG 7d demo gross = funding_arb -15.43 / grid -11.15 / ma +0.20 / bb -0.06 ≈ -26.44 USDT（驗 K-5）

**Report**: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-08--full_audit_pa_fix_plan.md`（同次複製到 Operator/）

---

## 2026-05-09 — AMD-2026-05-09-03 graduated canary default amendment（Operator Decision-1 拍板後起草）

**任務**：Operator 拍板採納 4-agent (PA/FA/QC/MIT) 共識 + FA push back，把 AMD-2026-05-09-02 §2 Option A「shadow_mode = fail-closed default」修訂為 5-stage graduated canary default。PA 起草 amendment 並落地 governance。

**核心邏輯**：
- AMD-2026-05-09-02 binary `shadow_mode true/false` 與其他 21 個 fail-closed default 累加 → P(全 PASS) ≈ 0
- 「P0-EDGE-1 雞蛋死循環」：edge 證據需要真 demo fill / 真 demo fill 需要 shadow_mode 翻 / shadow_mode 翻需要 edge 證據
- graduated canary 改用「stage 邊界 + 觀察期 SLA」而非「binary flip」，rollback 仍是 stricter（回 Stage 0），與 §二 原則 #6 完全相容

**5 stage 設計**：
- Stage 0 = shadow only（默認；不送 intent）
- Stage 1 = 1 strategy × 1 symbol × paper × 7d，升級條件 entry_fills ≥ 10 + boundary=0
- Stage 2 = 1 strategy × 1 symbol × demo × 14d，升級 gross > -5 + DSR > 0.5 + n=30；rollback gross < -10 或 DSR < 0
- Stage 3 = 5 active strategies × demo × 21d，升級 gross > 0 + DSR/PBO PASS + chain ratio ≥ 0.7；rollback gross < -20
- Stage 4 = LIVE_PENDING（operator 顯式拍板 + 全 5-gate live boundary）

**不適用範圍仍強制 fail-closed（明文列）**：
- DOC-08 §12 9 條安全不變量
- SM-04 CIRCUIT_BREAKER 5 ladder
- Live boundary 5-gate
- §二 16 原則硬不變式

**配套機制**：
- 新 healthcheck `[58] graduated_canary_stage_invariant`（升級 metric + rollback metric 必存在 + trip 偵測）
- PG schema `governance.canary_stage_log` + `governance.canary_stage_metric_registry`（V### migration，Guard A/B/C，Linux PG dry-run）
- GUI Settings/Governance tab 加 cohort + stage + rollback metric live + manual promote 按鈕（IPC 動作 + Decision Lease）
- Rust schema `RiskConfig::executor.canary_stage / canary_cohort / stage_entered_at_ms / observation_period_ms`（向後相容，ArcSwap hot-reload）
- Decision Lease 加 `LeaseScope::CanaryStagePromotion`（manual promote 必伴隨 lease）

**IMPL Wave**：W-AUDIT-9（新建，不併入 W-AUDIT-1..7），1.5-2 sprint，T1-T7 七個 sub-task；T1+T2+T3+T6 四向並行，T7 final regression。R-1 Alpha Surface Foundation IMPL 之前必須完成（R-1 後新 alpha source 必走完整 5-stage canary）。

**§二 16 原則合規逐條核**：14/16 ✅ + 2/16 不適用本 amendment scope（原則 12/15）；無違反 — 詳 amendment §6.3。

**Push back 給 PM**：
- AMD-2026-05-09-02 §3 / §4 / §5 不變（策略 verdict / openclaw_core sunset / Layer2 boundary）— 只取代 §2 字面
- AMD-2026-05-09-01 SM-05 invariants（IPC failure / cache miss / schema fail / provider exception → fail-closed）完全保留
- 不放鬆任何 live boundary（live default 仍是 Stage 0）
- 不放鬆 §二 16 原則任何硬不變式

**Commit**：`b1891023` `governance: graduated canary default amendment`
- 3 files changed: CLAUDE.md §四 注釋引用 / SPECIFICATION_REGISTER amendment 索引 + SM-05 status 更新 / 新 amendment 文件
- `git commit --only` 隔絕同 session 其他 WIP（multi-session race 守則，CLAUDE.md `feedback_git_commit_only_for_metadoc`）

**E2 重點審查 3 點**（PA 標）：
1. `shadow_mode` legacy `false` 配 `canary_stage=0` 必 reject；`shadow_mode_provider` exception path 仍 fail-closed 至 Stage 0（不是 Stage 1）— break 即雞蛋死循環復活
2. `canary_stage_log.decision_lease_id` for `manual_promote` 必填 NOT NULL constraint 在 PG 層強制（不只 application 層）
3. healthcheck `[58]` 對 SM-04 ≥ L3 escalate 必 hard FAIL → 觸 stage = 0 rollback；不可降為 WARN

**Report**：`docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md`（同次同步至 SPECIFICATION_REGISTER + CLAUDE.md §四）

**教訓**：
- 4-agent 共識 + push back 採納是高 leverage point — operator Decision-1 採納 FA push back 是治理 maturity 信號
- amendment 必明列「不適用範圍」防 scope creep — graduated canary 只動 alpha-bearing pathway，不動 hard boundary
- 用 `git commit --only` 在 multi-session 並行寫作下隔絕對方 WIP；本次成功避開 TW memory + 4 個 v3 verification report + W-AUDIT-8a spec 等其他 session 的 untracked/staged 檔

---

## 2026-05-09 — W-AUDIT-8a Alpha Surface Foundation spec phase 落地

**任務**：Operator 拍板開新 wave W-AUDIT-8a，把 PA audit `2026-05-09--full_loss_architectural_root_cause_redesign.md` Layer 4 R-1 動作落地為 spec phase。

**輸入**：自己同日 audit 報告 + QC 候選 A/B/C/D + Rust strategies/mod.rs:72-159 Strategy trait + tick_pipeline/mod.rs:665-708 TickContext + 5 策略 IMPL + CLAUDE.md §五。

**Spec 寫法決策**：
- spec phase 嚴格 = 接口契約 + DAG，**不寫 IMPL 細節**（Rust struct 定義、字段、生命週期、來源、staleness rule、retention 規範化）
- 4 phase 拆分：Phase A foundation schema + 5 策略 declare → Phase B Tier 2 panel collector → Phase C Tier 3 micro + liquidation 真接 → Phase D Tier 4 + 7d replay E2E
- DAG：A 必先；B 與 C 可並行；D 必待 B+C
- 邊界明確劃：本 wave **不含**任何具體 alpha source 業務 IMPL（候選 A/B/C/D 留 8b/c/d）/ Strategist reframe（R-2 留 8e）/ Hypothesis Pipeline（R-3 留 8f）/ per-alpha-source budget（R-4 留 8g）

**接口設計核心**：
- `AlphaSourceTag` enum 10 個 tag（TA1m/TA5m/FundingSkew/Basis/OIDeltaPanel/OrderflowImbalance/LiquidationCascade/EventDriven/CrossAsset/Sentiment）
- `AlphaSurface<'a>` 4 tier struct + lifetime 對齊 TickContext
- `Strategy::on_tick(ctx, surface)` 簽名升級 + `declared_alpha_sources()` 強制聲明
- 5 既存策略 declare：bb_breakout=[TA1m,TA5m,OIDeltaPanel] / bb_reversion=[TA1m] / ma_crossover=[TA1m] / grid_trading=[TA1m] / funding_arb=[FundingSkew,Basis]

**識別風險**：
1. 5 策略 trait 簽名 migration regression → Phase A 強制 byte-identical baseline E2E
2. collector PG 寫入 → V### migration 強制 retention（funding/oi 14d、liquidations 30d）+ MIT must-review
3. AlphaSurface lifetime 複雜 → 採 `&'a` 單層 borrow，fallback `Cow`/`Arc`
4. Scout IntelObject IPC schema mismatch → CC must-review Phase D EventAlert wire
5. Bybit `allLiquidation` rate-limit → BB must-review topic spec
6. Phase A 後 hold 風險 → Phase A 即達 R-1 80% 價值（trait 升級 + struct + declare），B-D 漸進

**Mandatory review chain**：
- Phase A：QC enum + E2 trait + E4 baseline regression
- Phase B：MIT V### + E2 + E4
- Phase C：BB Bybit topic + MIT V### + E2 + E4
- Phase D：CC Scout IPC schema + E2 + E4 7d replay E2E

**Side effect 落地**：
- TODO.md 加 rank 15 W-AUDIT-8a row（用 git commit --only 規則）
- CLAUDE.md §三 active blockers 加 W-AUDIT-8a entry
- CLAUDE.md §五 [策略工具包] reframe：`KlineManager → IndicatorEngine → AlphaSurface → SignalEngine → 5 策略`
- §五 加 AlphaSurface footnote 段落（與 Decision Lease/EarnedTrust 平行）
- 舊 §五 framing 歸檔 `docs/archive/2026-05-09--claude_md_section5_pre_alpha_surface.md`
- Spec 同次 mirror 至 Operator workspace

**Spec**：`docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`（30K bytes / ~3500 字）

**教訓**：
- spec phase 不寫 IMPL — 寫接口契約 + DAG + retention rule + freshness rule + acceptance criteria，避免 overpromise
- alpha source registry 用 Rust enum SoT 比 string-based tag 安全（exhaustive match catch 漏 tag）
- 4 tier 設計把舊 TickContext 中已有的 raw 字段（funding_rate / index_price / open_interest / best_bid/ask）再 architectural classification 一次，避免「舊欄位已存在 = 工作已做完」陷阱：funding_rate 是 single-symbol raw，funding_curve 才是 cross-section panel；二者 architectural meaning 不同
- E2E byte-identical baseline 是 trait 簽名升級的唯一可信驗證 — 任何 mock test / unit test 都無法 catch 邊角 callback 漏改
- Phase A 設計成「即使 hold N sprint 仍達 R-1 80% 價值」是 spec 的 fallback insurance — 接口升級即賺，後續 phase 漸進

**E2 重點審查 3 點**（PA 標）：
1. Phase A E2E baseline binary diff test — 必跑 fixed-seed replay 1h paper session 驗 stdout fingerprint byte-identical；任何 callback 漏改（on_external_close / on_close_confirmed / on_close_skipped / on_post_only_rejected）會 silent-skip 直到生產才暴露
2. AlphaSurface `'a` lifetime 與 TickContext `'a` 對齊 — Rust 編譯通過 ≠ 沒 dangling reference；E2 grep callsite 確認 surface 構造在 on_tick scope 內，不從 tick_pipeline state 借
3. V### migration retention policy（Phase B 兩條 + Phase C 一條）— Guard A/B/C 強制 + idempotency double-run 強制 + MIT review row-rate 估算；漏 retention 將致 PG 4-8 GB 限額溢

**Report**：`docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`（同次 mirror 至 `docs/CCAgentWorkSpace/Operator/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`）

## 2026-05-09 PA — Fix Plan v2 self-adversarial + W-AUDIT-8a/9 反饋 (post 5 commits + AMD-03)

**HEAD baseline**：`faf2d131`（v2 land 點）→ `da2aba11`（5 commits 後 + W-AUDIT-8a SPEC PHASE + AMD-2026-05-09-03 land）

**Self-adversarial 6 點 push back 結論**（對自寫 5/9 redesign report）：
- Push Back 1 **部分被 4-agent consensus 推翻**：原立場「Strategy Interface 偏差降一檔」過度保守；FA+PA+QC+MIT 4-agent 共識 + 22 fail-closed defaults 累加 P(全 PASS) ≈ 1e-3 死循環數學論證，operator 已採納 W-AUDIT-8a SPEC PHASE + AMD-03 graduated canary supersedes binary fail-closed
- Push Back 2 **仍站得住**：Strategist 合 EX-06 spec（不越權），EX-06 line 159 是「策略匹配」非「策略孵化」；責任在 Analyst L2-L5；R-2 = W-AUDIT-8e 改為 Strategist→Analyst propose 通道 + Analyst L2-L3 IMPL（不 reframe Strategist scope）
- Push Back 3 **仍站得住**：Analyst L2-L3 IMPL 不需 ADR-0020 reverse；L0+L1 Ollama 13B 可跑 95% workload；只 L4 跨策略戰略提案 escalate Layer 2 manual
- Push Back 4 **仍站得住**：ML 0.5% 是 writer chain + cron 三段斷下游症狀；W-AUDIT-4b 是 W-AUDIT-8f Hypothesis Pipeline prerequisite，不是合併（per AMD-03 §5.4）
- Push Back 5 **仍站得住**：原 5-Agent 拆分 root cause 無新意，replace 為「Spec-Runtime drift 自動偵測缺位」
- Push Back 6 **仍站得住**：Alpha Surface 升級工時 3 sprint → 4-5 sprint；BB Bybit API survey + E5 LOC budget 必驗；W-AUDIT-8a operator land spec 估 4 sprint × 40 person-day（PA 估算與 operator land 一致）
- Push Back 6.1 **仍站得住**：5 策略不是「全無 alpha territory」，是「2 個有負 alpha 證據 + 3 個樣本不足」

**operator 在 PA 撰報告同時拍板**：
- W-AUDIT-8a "Alpha Surface Foundation" SPEC PHASE 2026-05-09 / Phase A-D × 4 sprint × ~40 person-day（CLAUDE.md §三 加 row + spec doc land）
- W-AUDIT-9 "Graduated Canary Foundation"（AMD-2026-05-09-03 起 / 1.5-2 sprint / 7 sub-task DAG / E1-A 至 E1-G）
- AMD-03 supersedes AMD-02 §2 binary fail-closed default → 5-stage graduated canary（shadow / single-symbol-paper / single-symbol-demo / multi-symbol-demo / live-pending），每 stage 條件 fail-closed + auto-rollback
- 4-agent consensus FA+PA+QC+MIT 集中 22 fail-closed defaults 死循環論證；CLAUDE.md §四 加 executor_canary_stage AMD-03 reference

**fix plan v2 verdict**：DUAL-TRACK
- Track W 收尾 ~92h / 9-11 session：W-AUDIT-3b/4b/6c/6d/7c/1d/5b（7 增量 wave）
- Track A operator 已 active：W-AUDIT-8a/8b/8c/8d/8e/8f/8g + W-AUDIT-9 + W-ARCH-3（9 ARCH wave，~270-330h 6-12 weeks，含 graduated canary stage gate）
- 整合視圖 6-12 weeks roadmap；最早 supervised live：6/15 樂觀/6/30 中位/7/15 悲觀（基本同 v2 baseline，W-AUDIT-9 IMPL land 後 P0-EDGE-1 evidence path 才真實 active 為樂觀帶補可信度）

**5 commits cover**：3 個 P0-V2-NEW source/test + 1 governance（blocked symbols）+ 1 audit 校正（cron scope）；runtime apply 全 outstanding；W-AUDIT-4b 6 表 0 INSERT 仍最大 critical gap

**PM push back 5 點**（修正後反映 W-AUDIT-8a/9 既已 active）：W-AUDIT-9 與 W-AUDIT-3b commit 衝突協調 / W-AUDIT-8e R-2 修正 / W-AUDIT-4b 串行先 W-AUDIT-8f / W-AUDIT-6 redesign 策略走 Stage 1 / Layer 2 解耦

**Report**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_audit_pa_fix_plan_v2.md`

---

## 2026-05-09 P0-V3-PA-SPEC-FIX：BB v3 對抗性 review 揭發 PA Alpha Surface spec 3 條技術錯誤

**觸發**：BB v3 verification (`docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-09--bybit_compatibility_verification_v3.md`) NEW-5/NEW-6/NEW-8 Bybit-side 對 PA Alpha Surface Bundle 投票 CONDITIONAL APPROVE，要求 PA spec 修 3 條再進 R-1 IMPL。

**3 條技術錯誤**：
1. **L25 不存在**：PA 草案多處用「L25/L50 orderbook」，但 Bybit V5 WS linear orderbook 真實 depth levels = `1 / 50 / 200 / 1000`，**沒有 25**。OpenClaw 已預設訂閱 `orderbook.50.{symbol}`；如需 deeper book 改 L200。寫 L25 進 spec 會撞 Bybit endpoint validation。
2. **liquidation_pulse 已 4 weeks ago deleted**：PA 草案把 `LiquidationPulse` 當 W-AUDIT-8a Phase C「真接 Bybit allLiquidation WS」，但 OpenClaw 於 2026-04-06 已刪除 `allLiquidation` WS handler（字典手冊 line 990 證明）。`market.liquidations` 表 reserved 保留，但 R-1 IMPL 需 +1 sprint 重接 WS handler + 重啟 writer；期間 surface field 必須以 `requires_revival: true` flag 標 dormant，禁 stub mock。
3. **basis 沒分 demo observation vs execution**：PA 草案把 `basis_curve` 列入 Tier 2 alpha source，但 Bybit demo **不支援 spot lending execution**（與 funding_arb v2 retire 同因 ADR-0018）。R-1 spec 必須明文「basis = observation-only until mainnet」+ 加 `requires_spot_capability: true` flag；demo 環境下吃 `Basis` 的策略 StrategyAction 必須 fail-closed 不可進 IntentProcessor。忽略此邊界 = funding_arb v2 demo n=13 -36.76 bps 陷阱重演。

**3 個檔案修法**（同步 patch 結構，不破壞既有章節）：
1. `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md` §3.1 AlphaSurface struct 注釋 + 新增 3 個對齊段落（Bybit V5 levels / liquidation 復活前置 / basis execution 邊界）
2. `srv/docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md` §2.3 三個子節 Tier 3.1 (OrderflowFeatures) / Tier 3.2 (LiquidationPulse) / Tier 2.2 (BasisCurveSnapshot) 各自加 require flag + 邊界明文 + 對應 Sprint 影響
3. `srv/docs/CCAgentWorkSpace/Operator/2026-05-09--full_loss_architectural_root_cause_redesign.md` mirror 同步 3 條（per TW v3 push back，本次只更新核心 3 條，不字面複製整份）

**核心教訓（PA 自我檢討）**：
- **Bybit endpoint 真實能力沒在 PA spec drafting 階段查 BB**：草案寫 L25 是 mental model 從別家交易所（Binance L20 / OKX L25 等）誤帶過來，OpenClaw 唯一交易所是 Bybit V5 必對齊 1/50/200/1000。
- **「已刪除模組」識別失敗**：liquidation_pulse 寫入 PA spec 時沒查 4 weeks ago handler 已刪事實。應在 spec 提到任何 alpha source 時呼叫 `grep -r "allLiquidation\|liquidation_handler" rust/ python/` 驗 handler 存在。
- **demo execution capability 邊界遺漏**：basis 是 funding_arb v2 同類陷阱（perp+spot 對沖），PA 應記住 funding_arb v2 retire reason（demo 無 spot lending）並先驗 demo 是否支援 spot execution。

**Push back 給未來 PA**：spec drafting 階段必跑 BB pre-review（不只 BB post-review），對任何 alpha source 提案必先確認 (1) Bybit endpoint 真實 shape、(2) 既有 handler / writer / parser 存在、(3) demo vs mainnet capability 邊界。否則 BB review 會打回，浪費 round。

**Report**：本次直接 patch 3 個檔案，無單獨 report；參考 BB v3 verification 路徑。

---

## 2026-05-09（夜）TODO v18 ⇄ QCTODO 統一 merge 分析

**任務**：Operator 拍板「重新梳理全部工作流程」— 把 srv/QCTODO.md（4-agent loss audit dispatch；327 行）整合進 srv/TODO.md（v18；573 行）成統一 v19，最後 rm QCTODO.md。PM 寫 merge code，PA 寫 read-only merge analysis。

**輸入文件**：
- TODO v18（13-agent v3 verification + DUAL-TRACK Track W/A）
- QCTODO（PM Sign-off banner accepted；6-sprint roadmap N+0..N+5；16 sign-off invariant + 4 追蹤；5 群 dispatch；Cross-Wave Conflict 4 條）
- 上一份 PA full dispatch engineering plan `2026-05-09--full_dispatch_engineering_plan.md` commit d3bf7be2
- FA business chain validation `2026-05-09--full_dispatch_business_chain_validation.md` commit 5a2dee98

**結論文件**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--todo_qctodo_merge_analysis.md` + Operator mirror `srv/docs/CCAgentWorkSpace/Operator/2026-05-09--todo_qctodo_merge_analysis.md`

**關鍵發現 1：3 大 wave label 衝突需重命名**
- TODO v18 line 554-558 把 `W-AUDIT-8b/c/d/e/f` 對應到 R-1/R-2/R-3/R-4/R-5 spec wave
- QCTODO + PA dispatch §2.4 + FA report §5 三端對齊把 `W-AUDIT-8b/c/d` 對應到 A4-A/B/C 候選新策略
- merge verdict：採 QCTODO labeling（PA dispatch + FA report 後對齊正解）；R-1..R-5 改名 `W-AUDIT-8a/8e/8f/8g/10`
- 影響：v19 必含 explicit Wave Label Reconciliation 表防 cross-doc 引用斷裂

**關鍵發現 2：W-AUDIT-6 不是衝突而是兩個不同 wave**
- TODO v18 line 340 `W-AUDIT-6` SOURCE/TEST CLOSED 2026-05-09（既有 8 子項 closed）
- QCTODO 「保 6 / 砍 6」是 mid-ground 新 batch（5 既存策略 audit + sweep + Kelly tier config 化）
- merge verdict：v18 W-AUDIT-6 closed 不變；新加 `W-AUDIT-6d` mid-ground entry；v19 保兩個 entry 不衝突

**關鍵發現 3：QCTODO §5 16 sign-off invariant 大半 v18 未含**
- 11/20 條 🆕 全新（DSR K -12 量化 / Stage 2 abort gate / canary_stage_log NOT NULL / etc）
- 9/20 條 📦 v18 已含 IMPL-level entry 但無 sign-off form
- merge verdict：v19 加新 §4 Sign-off Pre-flight Checklist 整 QCTODO §5 原文搬入

**關鍵發現 4：6-sprint capacity 規劃全 🆕**
- v18 line 449 只有「2026-06-15 supervised live target (悲觀帶)」一句話 calendar date
- QCTODO §1 6-sprint table + 4 概率帶（30/40/25/5）+ 5 active + 1 stand-by capacity + stand-by 啟用 5 條 + critical path
- merge verdict：v19 加新 §5 Sprint Roadmap N+0..N+5 完整保留 QCTODO §1

**關鍵發現 5：Cross-Wave Conflict 4 條全 🆕**
- #1 8a Phase A migration ↔ W-AUDIT-6d mid-ground 5 策略改動同 file overlap → 序列化（先 6d 再 8a Phase A）
- #2 W-AUDIT-9 T3 stage-aware ↔ ExecutorAgent shadow_mode 接線 → T3 land 後 stage-aware reload
- #3 W-AUDIT-8a Phase B+C ↔ W-AUDIT-5b 性能 wave 同 tick_pipeline/mod.rs → Phase B+C 並行於 N+1
- #4 A 群新策略 ↔ W-AUDIT-9 Stage 1 cohort 選擇 → A4-C 用 Stage 1 paper cohort 入場驗 stage 機制
- merge verdict：v19 §3 加 Cross-Wave Conflict Resolution sub-section

**關鍵發現 6：A2-followup G3-08 status drift**
- TODO v18 line 414 `P2-STRUCT-1` ACTIVE
- QCTODO §1 標 ✅ DONE 2026-05-09 17:27 UTC commit dddc5dc1（cost_edge_advisor daemon spawned 已驗）
- merge verdict：v19 P2-STRUCT-1 status flip → DONE，不漏 commit dddc5dc1 evidence

**關鍵發現 7：2 個 Decision-2/3 是新 P0-DECISION-AUDIT，不是已 closed P0-DECISION-AUDIT-2/4**
- TODO v18 P0-DECISION-AUDIT-2/4/5 處理的是 shadow_mode TOML / 5 策略 verdict / openclaw_core sunset
- QCTODO Decision-2 是 W-AUDIT-6 mid-ground 保 6 / 砍 6 verdict；Decision-3 是 W-AUDIT-4 ML 基座併入 W-AUDIT-8f
- merge verdict：v19 加 P0-DECISION-AUDIT-6（W-AUDIT-6 mid-ground）+ P0-DECISION-AUDIT-7（W-AUDIT-4 併入）

**v19 Outline 7 大 section**：
- §0 Banner（v19 + sync timestamp + PM sign-off + operator (a) 採納）
- §1 Architecture Boundary（沿用 v18 line 11-37）
- §2 Latest State（v18 既有 + QCTODO milestone）
- §3 Active Dispatch Queue（v18 Dispatch Order + DUAL-TRACK Wave + Cross-Wave Conflict + Day-by-Day + P0/P1/P2 + Wave Label Reconciliation）
- §4 Sign-off Pre-flight Checklist（QCTODO §5 整搬入 16+4 invariant）
- §5 Sprint Roadmap N+0..N+5（QCTODO §1 整搬入）
- §6 D-02 SOP / Push Back / Risk（QCTODO §6+§7 + FA push back 4 條）
- §7 Schedule（v18 calendar 沿用 + 4 概率帶）
- §8 Dispatch Rules / Handoff Checks（v18 + 砍 6 grep blacklist）
- §9 References（v18 references + QCTODO §8）

**PM 必含 5 類 anchors**（任一漏 = cross-ref 斷裂）：
1. 文件路徑（30+ ADR/AMD/spec/audit-summary/archive 路徑全列）
2. 命名格式（Wave / P0/P1/P2 / Sub-task A4-X B-MX C-XX T1-T7 Phase A-D / E1-A..F slot / Sprint N+X WX-WX）
3. Cross-reference（CLAUDE.md §三/§四/§五/§九 + DOC-08 §12 + §二 16 原則 + EarnedTrust）
4. Healthcheck id（17 條 [14] [33] [37] [38] [40] [41] [42] [42b] [42c] [43] [45] [50] [51] [54] [55] [56] [58] [Xc] [Xb]）
5. Commit hash（24+ 條：b91487f2 / 503eeb33 / e858ae2 / 6cb1c3b / 3681f83 / dddc5dc1 / d3bf7be2 / 5a2dee98 / ad59765b / b1891023 / c13c811e / 862e79b7 / e97a333b / 276a9b17 / cc6476dd / 6d3ea046 / 75741eff / ad14db07 / e95c779 / 306993e）

**v19 預估規模**：~700-750 行（v18 573 + ~150 sprint dispatch 細化 + 16 invariant + Cross-Wave Conflict + D-02 SOP - 重疊歸併 / 30 closed entries archive）

**Push back 給 PM**：
- v19 規模逼近 TODO 衛生上限（700-750 行）；v19 land 後 1-2 sprint 內若 §3 closed entries 多到 ~30+，再啟動 v20 archive cycle 防膨脹
- archive 操作建議同 commit：`mv srv/QCTODO.md → docs/archive/2026-05-XX--qctodo_sprint_n0_n5_archive.md` + 新加 `docs/archive/2026-05-XX--todo_v18_closed_entries_archive.md`

**核心教訓**：
- 「QCTODO 是 v18 順承擴張」是正確 framing，operator 拍板「整合進統一」對 — 拒絕 v19 不是替代 v18，是擴張結構保留 + 細化 dispatch
- 派工分析必對「衝突 vs 細化 vs 全新」三類分清，不能合併處理（label 衝突當細化 = cross-ref 斷裂；新 wave 當衝突 = 漏 entry）
- merge analysis 必含 Wave Label Reconciliation table，cross-doc 引用 PA dispatch + FA report 三端對齊事實，避免後續 codex / agent 引用斷裂

**Report**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--todo_qctodo_merge_analysis.md`

---

## 2026-05-10 — W6 RFC PA 預備立場（4 questions 自答）

**性質**：D+1 W6 RFC 三角入場前 PA read-only 預跑；MIT W6 baseline `2026-05-10--governance_reject_baseline_w6_rfc.md` 揭露 govern 沒 over-fit 後 PA 視角立場固化

**Source code 取證**：
- `intent_processor/gates.rs:14-260` — cost_gate 三層 paper/moderate/live by-design fail-closed
- `intent_processor/tests.rs:1360-1421` — duplicate_position 同方向 reject + 反方向 allow 是架構級不變式（test 雙證）
- `strategies/ma_crossover/strategy_impl.rs:75-170` — on_tick 內部已有 `match self.positions.get()` None 才 entry → 被 duplicate 阻 2331 次 = self.positions 跟 paper_state 不同步 bug

**4 立場**：
- Q1 cost_gate hard vs advisory → **hold A** 維持 hard，降 advisory + LinUCB 自學會違反根原則 #5/#4
- Q2 duplicate_position pyramiding → **hold A** 不開（架構級不變式）；2331 reject 是 ma_crossover state sync bug 不是 guard 過嚴
- Q3 V086 metadata 時機 → **hold A** V086 立刻做（producer-side 改動越早越好）；ML retrain enable 等 4-gate（V086 land + dual-write 24h 0 NULL + multi-class 3 類 sample ≥ 200 + imbalance 試行 PASS）
- Q4 bb_*/funding_arb 0 fire → **depends** funding_arb dormant by design（ADR-0018）；bb_breakout = AlphaSurface consumer gap（W1 B-4）；bb_reversion 三源因素需另查

**核心整體立場**：W6 不是 governance 工程而是 observability + ML metadata 工程。三方向都不觸碰 §四 三硬邊界 / DOC-08 §12 9 條 / cost_gate / duplicate_position 不變式。**16 根原則合規 16/16；硬邊界觸碰 0**。

**對 v3.1 dispatch 6 條 update 建議**（出建議 only operator 拍板）：
1. §3.0 W6-1 RFC verdict 明文「cost_gate hard rule 維持」記入
2. §3.0 加 W6-7 [60] strategy fire silence healthcheck (funding_arb 排除)
3. §3.5 P1-MA-CROSSOVER-DUPLICATE-INTENT audit 補 3 fix 候選（on_fill / bootstrap / RC-04 rollback）
4. §3.5 加新 P1-BB-REVERSION-FIRE-AUDIT
5. §6 acceptance 第 5 條明「LightGBM imbalance 試行不 deploy production cron」
6. §6 acceptance 加 ML retrain 4-gate

**教訓**：
- W6 baseline 預跑後 v2「conditional relax governance」設計轉 v3 已正確。本 PA 立場固化，避免 N+2 又重提 advisory 路徑
- duplicate_position guard 是 router Gate 1.5 + paper_state + Guardian 三方共識的架構級不變式，下次有人提 pyramiding 必走 ARCH-AMD 三角不能 hack
- ma_crossover self.positions 跟 paper_state 不同步是「策略內部 state vs runtime authority state」典型 sync bug — 5 策略都該 audit on_fill / bootstrap / rollback 三條 sync path

**Report**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_rfc_pa_questions_self_answer.md`

## 2026-05-10 — Sprint N+1 W2 PA C-1 spec phase pre-run（A4-C BTC→Alt Lead-Lag）

dispatch v3.3 §3.2 W2 fast-track 預跑：A4-C 是 W-AUDIT-8c 候選 C 的 N+1 paper-only fast-track，operator 2026-05-10 拍板 B 路徑（不只 spec，直接派 paper IMPL 拿 7d evidence，gate avg_net_bps ≥ +5 bps 進 N+2 demo IMPL）。

**Spec land path**：`srv/docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md`（draft v1，QC C-2 + MIT C-3 三角 review pending D+1，1 day）

**關鍵設計決策**：
- Cohort = BTCUSDT (lead) + ETHUSDT/SOLUSDT/XRPUSDT/DOGEUSDT/ADAUSDT/AVAXUSDT/DOTUSDT (7 alt follower)；BUSDT (ADR-0018) + INXUSDT (W7-3 hot loop 殘留風險) + grid_trading.blocked_symbols 全列入 excluded
- Lead signal = btc_lead_return_pct(N) + btc_volume_z + btc_book_imbalance；N 預設 120s（QC C-2 拍板 60/120/300）；strict shift(N) 必排除 current bar（per `feedback_indicator_lookahead_bias`）
- Predicted dir = expected_dir(±1/0)，threshold_X = 10 bps + threshold_Y = 0.40 預設
- V088 panel `panel.btc_lead_lag_panel` hypertable 1d chunk + 14d retention（paper-only 期；N+2 升 30d 開新 V###）
- Strategy 接收：ma_crossover + grid_trading paper engine only **shadow log no trade**（C-IMPL-3）；bb_breakout/bb_reversion/funding_arb 不接（避免污染既有 oi_delta panel evidence + 既有 demo edge baseline）
- 三層 paper-only fence：Layer 1 step_4_5_dispatch engine_mode gate（主防線，default → None）+ Layer 2 Python writer paper-only fence（OPENCLAW_ENABLE_PAPER）+ Layer 3 Strategy if let Some guard（被 contract 覆蓋）
- E1 派發：C-IMPL-1 NO-OP（trait 已 PA D+0 c9fb0b8f land）+ C-IMPL-2 producer + V088 + IPC slot（~350 LOC）+ C-IMPL-3 strategy paper-only shadow（~80 LOC）+ C-IMPL-4 paper engine 7d evidence collection
- Bybit V5 rate budget = 9 req/min (BTC kline + BTC orderbook + 7 alt kline)，well under 120 req/s upper bound；W1+W2+W3 同窗 BB 必審

**E2 重點審查 3 點**：
1. Layer 1 paper-only fence default `_ => None`（不是 `_ => Some(...)`）— 漏 = 主路徑污染
2. Strict shift(N) lookahead-free：所有 BTC return / volume z 計算 grep `rolling()` / `[t-N..t]` slice 確認 strict shift 排除 current bar
3. V088 hypertable retention `add_retention_policy('panel.btc_lead_lag_panel', INTERVAL '14 days')` 必設 + idempotency dry-run 兩次

**16 原則 + DOC-08 §12 不變量 + 硬邊界 5 項**：全 0 觸碰（W2 paper-only shadow log no trade，不動 lease / auth / SM-04 / live boundary 任何路徑）。

**Risk**：MIT 揭露 W6-5 同類 category error 風險待 D+1 三角 review；如類似 → revise spec 重派；如三輪 revise 仍 < +5 bps → A4-C archive，W-AUDIT-8c 候選 D（orderbook imbalance）替補 fast-track。

---

## 2026-05-10 PA — W6-3b enum spec final + 5 ambiguous (A1-A5) 拍板

**Trigger**: MIT W6-3a audit `2026-05-10--w6_3a_close_tag_distribution_audit.md` (HEAD `da6c1f80`) 揭露 real enum 比 dispatch v3.3 preliminary 多 30% (preliminary 8+10 → real 12+14 含 catch-all)；5 ambiguous A1-A5 標需 PA 拍板才能進 V086 IMPL。

**Report**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_3b_enum_spec_final_pa_decision.md`

**5 拍板結論（全 ACCEPT MIT）**：
- A1 strategy_close_legacy_bare_name 615 row → 1 enum 不拆（strategy column SoT 區分）
- A2 雙前綴 16 row → backfill SQL 加 normalize；**無需 P1 producer ticket**（PA grep 確認 `helpers.rs:38` `build_risk_close_tag()` 已 2026-04-23 land = idempotent helper；step_6_risk_checks.rs:275 已 migrate；雙前綴是歷史污染，post-2026-04-23 active code 正確）
- A3 cost_gate_atr_unavailable empty-but-reserved → 保留（SEC-11 fail-closed signal，與 cost_gate_other 不同 trader semantic）
- A4 funding_arb 29 sub-reason → 合 1 enum (ADR-0018 退役，0 future incremental)
- A5 strategy_close_regime_shift 1 row → 保留 (R-3 hypothesis pipeline pilot)

**Final spec**：
- reject_reason_code 12 enum (11 + catch-all `reject_other`)
- close_reason_code 14 enum (13 + catch-all `close_other`)
- catch-all 命名 rename `other_reject` → `reject_other` / `other_close` → `close_other`（prefix consistency）
- V086 兩 column TEXT not jsonb (per MIT Q3)，partial index `(reject_reason_code, close_reason_code) WHERE NOT NULL`
- backfill **one-shot** 30-90 sec UPDATE in V086（不開 cron，dispatch v3.3 §3.0 修文）
- ALTER VALIDATE CONSTRAINT timing: D+2 14:30 UTC (24h dual-write drift PASS 後)

**Code grep evidence (副作用 audit)**：
- `rust/openclaw_engine/src/tick_pipeline/on_tick/helpers.rs:38` `build_risk_close_tag(reason)` idempotent helper RUST-DOUBLE-PREFIX-1 (2026-04-23) = 雙前綴 fix 已落地
- `step_6_risk_checks.rs:275` 用 `super::build_risk_close_tag(&reason)`，無雙前綴
- `risk_checks.rs:400` `format!("risk_close:{}", reason)` 傳入裸字串 (`"phys_lock_gate4_giveback"`) → 單前綴

**Dispatch v3.3 §3.0 修建議**：
- W6-3a/W6-3b checkbox flip DONE
- W6-3c E1 IMPL 立即可派（spec final）
- W6-3d 改為 W6-3c sibling 並行（不依賴 V086 deploy timing）
- 數量改：reject 8→12 enum / close 10+→14 enum

**E2 必查 3 點**：
1. Backfill SQL CASE WHEN evaluation order（ATR unavailable 必先於 JS-demo / cost_gate_other；雙前綴必先於單前綴；bare-name exact 必先於 prefix regex）— PG dry-run 9757 row distribution 比對 audit table
2. Guard A/B/C 完整性（V086 缺一 = E2 拒簽，per memory `feedback_v_migration_pg_dry_run`）
3. Producer dual-write race（V086 land 與 dual-write code deploy 不能差 >5 min；否則 24h 後 ALTER VALIDATE 會失敗）

**16 原則 + DOC-08 §12 不變量 + 硬邊界 5 項**：全 0 觸碰（W6-3 是 ML 平面 schema add column + read-only backfill，不動 lease / auth / SM-04 / live boundary / IntentProcessor 寫入路徑）。

## 2026-05-10 W-AUDIT-8a Phase B Tier 2 panel collector spec (W1 PA spec phase deliverable)

**Spec path**: `srv/docs/execution_plan/2026-05-10--w_audit_8a_phase_b_tier_2_collector_spec.md`

**Pre-condition**: PA D+0 trait skeleton 已 land HEAD `c9fb0b8f`（FundingCurveSnapshot + OIDeltaPanel typedef + AlphaSurface 對應 field + slots.rs/dispatch anchor 全預留）。

**關鍵設計決策**：
1. **Schema 對齊 trait struct field 校正**（task scope 與 trait 不一致 → 以 trait 為準）：
   - V085 `funding_rate_bps` (NOT scalar `funding_rate` + `curve_8h/curve_24h`) 對齊 `FundingCurveSnapshot.funding_rates_bps: Vec<f64>`
   - V087 `oi_delta_5m_pct / 15m_pct / 1h_pct` (NOT 1m/5m/15m) 對齊 `OIDeltaPanel.{oi_delta_5m_pct, oi_delta_15m_pct, oi_delta_1h_pct}: Vec<f64>` — 1m delta 噪音太高，5m/15m/1h 才是 informational tier
2. **Bybit endpoint 選用**：`/v5/market/tickers` 拿 funding rate + next_funding_time 一次（既有 layer2_tools_g3_07 pattern 對齊；不用 funding-history endpoint）；OI 用 `/v5/market/open-interest` 三 interval (5min/15min/1h) 各一 GET
3. **Cohort = 25 symbol**（grid_trading active ∪ ma_crossover active ∪ bb_breakout active；exclude BUSDT + frozen list；W1 hardcoded snapshot；W-AUDIT-8c 才 dynamic discovery）
4. **W1 vs W2 engine_mode 範圍**：W1 demo+live 都接（NO paper-only fence），W2 paper-only fence by step_4_5_dispatch.rs engine_mode gate
5. **bb_breakout fail-closed**：surface.oi_delta_panel.is_none() OR symbol 不在 cohort OR oi_delta_5m_pct=NaN → write `evaluation_outcome='oi_panel_unavailable'` 入 V082 decision_features_evaluations；V086 migration ADD VALUE TO V082 enum；對齊 P1-BB-BREAKOUT-FAIL-CLOSED-1 (dispatch v3.3 §3.5)
6. **3 E1 sub-agent 完全並行 0 file 重疊**：E1-α (B-1 funding) / E1-β (B-2 OI) / E1-γ (B-4 bb_breakout consume)；slots.rs + step_4_5_dispatch.rs anchor 隔離
7. **Rate budget 待 BB B-3 final**：funding 25 req/min (4.2%) + OI 75 req/min (12.5%) = 100 req/min (16.7% production budget)；若超推 90s cycle fallback；D+1 PA + BB final review
8. **Freshness gate**: 30s WARN / 300s FAIL（同 task scope 要求）；puller 自檢 + healthcheck [57]/[58] 監測

**E2 重點審查 3 點（spec §6）**：
1. V085/V087 schema 名稱嚴格對齊 trait struct field（funding_rate_bps NOT funding_rate；5m/15m/1h_pct NOT 1m/5m/15m）— grep verify
2. V086 V082 enum 加 `oi_panel_unavailable` value via Guard A IF NOT EXISTS + backward-compat 既有 row 不變
3. bb_breakout fail-closed 路徑無 silent fallback to internal `oi_buffer`（W-AUDIT-8d 才完全移除 buffer）

**16 原則 + DOC-08 §12 + 硬邊界 5 項全 0 觸碰**（spec §7）。

**Next action**: D+1 BB B-3 review final → PA integrate rate budget table → push spec → dispatch W1 E1-α/β/γ → D+5-D+6 land + E2/E4 → W1 land 後 ≥ 24h 再進 W3 Stage 1。

## 2026-05-10 W7-4 — 5 策略 cross-strategy position sync systemic audit

PA #3 P1-MA-CROSSOVER root cause `da2d2a46` 揭露 ma_crossover 用 `self.positions: HashMap` 不查 paper_state、router gate 1.5 symbol-level dedup、RC-04 rollback 到 None → cross-strategy desync hot loop（INXUSDT 11:34 一分鐘 reject 2319 次）。W7-3 Option B 補丁 `d8697c41` 已 land 提供 1-tick defense + W7-1 trait skeleton `c9fb0b8f` 已加 `TickContext.position_state: Option<&'a PaperPosition>`（step_4_5_dispatch.rs:219 暫 None 待 W7-2 wire）。

W7-4 systemic audit verdict（read-only，不改 code）：
- **HIGH (P1)**：`ma_crossover` (confirmed) + `bb_reversion` (potential，與 ma_crossover 同結構：用 `PerSymbolState<bool>` + RC-04 rollback 到 None + 不查 paper_state；W6 0 顯眼是 RSI/percent_b/MA gate 苛刻未對齊，結構性風險高)
- **MEDIUM**：`bb_breakout` — 同結構但 6 重 gate（squeeze 45min + expansion + vol + Donchian + persistence 60s + confluence）自然限頻到 ~1/min reject
- **LOW**：`grid_trading` — M-2 30s `reject_cooldown_until_ms` backoff 結構性護欄（on_rejection arm + signal.rs 開頭 check），hot loop 不可能；inventory model 與 boolean position 不對齊，硬塞 W7-2 pattern 反引入複雜度
- **RETIRED-LOW**：`funding_arb` — ADR-0018 dormant `active=false` + 1h cooldown + funding 8h cycle 自然限頻

W7-2 fix pattern（Option A 治本）：(1) step_4_5_dispatch.rs per-iteration borrow `paper_state.get_position(sym)` 寫入 ctx.position_state ~10 LOC；(2) ma_crossover/strategy_impl.rs None 分支 query ctx.position_state 命中即 sync self.positions + skip entry ~15 LOC。保留 W7-3 Option B 作為 reason 字串契約 fallback 冗餘，不可拿掉。

W7-5 same-Wave optional 建議：bb_reversion 同 pattern apply ~15 LOC + 3 tests，與 W7-2 共用 trait skeleton 邊際成本低，提早結 P2-BB-REVERSION-POSITION-SYNC。

P2 ticket refinement：(a) 保留 P2-BB-BREAKOUT-POSITION-SYNC 降為 MEDIUM 延 Sprint N+2；(b) 保留 P2-BB-REVERSION-POSITION-SYNC 升為 HIGH 建議 W5 一併 IMPL；(c) 不開 grid_trading / funding_arb 新 P2。

E2 重點審查 3 點：(1) TickContext clone 成本（per-iteration shallow copy ns 級，需 1000 burst micro-bench）；(2) paper_state borrow scope（strategy on_tick 完才 mirror_insert/apply_fill，immutable get 在前可行，PA #3 §8 重點 3 已驗）；(3) Option A + Option B 共存無衝突，但不可拿掉 Option B（reason 字串契約 fallback 最後防線）。

派生發現：RC-04 rollback 到 None 設計 4/5 策略共用（grid_trading 例外用 inventory + M-2）。Hot loop 風險差別不在 RC-04 而在「entry path 後是否有 reject backoff」。Sprint N+2 候選：考慮為 4 策略引入「strategy 通用 reject backoff」trait default 對齊 grid_trading M-2 模式（設計題，不阻當前任務）。

Report: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w7_4_systemic_position_sync_audit.md`

---
## 2026-05-10 17:50 UTC — Sprint N+1 W5 三 P1 ticket spec 預寫（W5 IMPL phase E1 直接收）

PM 派 PA 預寫 W5 三 P1 ticket spec 省 PA D+1-3 spec phase；W5 sub-agent E1 IMPL 直接收 spec。

**三 spec land 路徑**（並行寫，互不依賴）：
1. `srv/docs/execution_plan/2026-05-10--p1_canary_stage_criteria_1_spec.md`（QC HIGH push back 2 Stage 1→2→3 promotion + demote criteria 寫死；對齊 AMD-2026-05-09-03 §2.2；新 AMD-2026-05-10-05 起草）
2. `srv/docs/execution_plan/2026-05-10--p1_canary_cohort_freq_23_spec.md`（CC 22 invariant gap → 新 invariant 23 cohort frequency cap 30d ≤2 + PA+QC override SOP；新 healthcheck `[63]`；對齊 AMD-2026-05-09-03 §2.4）
3. `srv/docs/execution_plan/2026-05-10--p1_dynamic_unblock_check_1_spec.md`（QC v3 NEW-ISSUE-V3-4 — reuse `blocked_symbols_7d_counterfactual.py` 改 30d 版 + auto unblock criteria + manual override SOP + reverse audit chain；新 healthcheck `[64]`；新 `governance.unblock_candidates` table）

**設計核心**（共用 pattern）：
- 全部 read-only design 階段，0 IMPL 落地（W5 sub-agent E1 phase 才寫 code）
- 三 spec 加總 LOC 估 ~1100-1200 LOC + ~260 LOC test
- 三 spec 都對齊 §二 16 原則（特別是 #4/#6/#16）+ DOC-08 §12 9 不變式 + 硬邊界 5 項 0 觸碰
- 都加新 healthcheck（`[58]` enrich + `[63]` + `[64]`）對應 silent-dead 偵測
- 都需 V086+ migration（cohort_freq_cap V086 + unblock_candidates V0XX）+ Guard A/B/C + Linux PG dry-run 強制

**E2 重點審查 3 點**（PA 跨 spec 標）：
1. `boundary_violation_count` 在 P1-CANARY-STAGE-CRITERIA-1 §2.4 list 7 source 必與 §4.1 healthcheck 對齊（drift = `[58]` invariant break）
2. P1-CANARY-COHORT-FREQ-23 「cohort identity 三元組」(strategy, symbol, environment) 在 Rust + Python + SQL 三處比對 case-sensitive 一致
3. P1-DYNAMIC-UNBLOCK-CHECK-1 §5.1 force_eval API **不可 override §3 criteria**（force_eval 只插隊跑，不放寬條件）— 違反即 selection-bias 機制失效

**派發策略**（dispatch v3.5 §3.5）：
- P1-CANARY-STAGE-CRITERIA-1 + P1-CANARY-COHORT-FREQ-23 與 W3 同窗（W3 stage 1 cohort entry 必先 close 此兩 spec）
- P1-DYNAMIC-UNBLOCK-CHECK-1 與 P1-TONUSDT-CONDITIONAL-WATCH 同窗（TONUSDT 30d evidence 是此 spec 的 first real customer）

**派生教訓**（補入 memory）：
- spec 預寫 pattern：PA 在 dispatch sign-off 後立即預寫高 priority P1 spec → W5 sub-agent E1 IMPL 直接收 → 省 PA D+1-3 spec phase 約 2-3 day 並行壓縮
- AMD wording 起草必 cross-ref 既有 AMD（如 AMD-2026-05-09-03 §2.2/§2.4/§4.2/§4.5）— 避免 spec drift；新 AMD 編號預留（AMD-2026-05-10-05 / -06）
- healthcheck `[63]` `[64]` 編號續 `[58]`-`[62]`（W6/W-AUDIT-9 已用），與既有 family `checks_governance.py` 同 module
- frozen cells unblock 是治理空白：當前 17 cells 無自動 reverse 機制 → selection-bias 累積；此 spec 是 first formal unblock 治理框架

## 2026-05-10 W1 spec v1 → v1.1 BB WS-first revision (採納 HIGH push back)

**Trigger**: BB W1+W2 rate budget review report `2026-05-10--w1_w2_bybit_v5_rate_budget_review.md` §6 HIGH push back — v1 spec 100 req/min REST polling 是 over-engineering，`tickers` WS topic 已 broadcast `fundingRate` + `openInterest`。

**v1.1 design**：
- Producer 從 Python writer 切換到 **Rust `panel_aggregator/{funding_curve,oi_delta}.rs`** 訂閱既有 WS `tickers.{sym}` topic broadcast (`enable_extended_ws=true` 預設 25 sym subscribed)
- WS event_rx 從 mpsc → broadcast::channel(2048) migration（critical gating dependency by E1-α leader）
- Funding ongoing **0 req/s** (WS broadcast)，OI ongoing **0 req/s** (WS broadcast)，cold-start 僅 75 req batch (OI history) once at startup
- WS reconnect gap 由既有 RE-2 supervisor (main_ws.rs:75-131) 自動重連 + cold-start backfill 重跑（aggregator broadcast Lagged event 觸發）
- Aggregator 60s flush 視窗：buffer Vec → 雙寫 PG (audit/training) + Rust slot (hot path)；`panel_puller.rs` 不建（v1 設計刪除）
- bb_breakout consumer 邏輯**完全不變** with producer side 切換無關
- 5s WS-tick freshness threshold（嚴於 v1 30s 因 WS push-based）；PG-side healthcheck [57]/[58] 30s WARN / 300s FAIL 寬鬆閾值

**Source code 取證**：
- `srv/rust/openclaw_engine/src/main_ws.rs:47-66` — `enable_extended_ws=true` 預設加 tickers topic
- `srv/rust/openclaw_engine/src/multi_interval_topics.rs:128-147` — `full_subscription_list()` 含 `ticker_topic()`
- `srv/rust/openclaw_engine/src/ws_client/parsers.rs:225-263` — `parse_ticker_item()` 已 extract `fundingRate` + `openInterest`
- `srv/rust/openclaw_engine/src/ws_client/dispatch.rs:111-114` — `topic.starts_with("tickers.")` route to parser
- `srv/rust/openclaw_types/src/price.rs:73,84` — `PriceEvent.funding_rate / open_interest` Option<f64> 已存在
- **`PriceEvent.next_funding_ms` 缺，W1 IMPL E1-α 必加 field + parsers.rs 加 `nextFundingTime` extract**

**E1 sub-agent dispatch sequence (v1.1 critical change)**：
- E1-α (B-1) leader：先 land event channel mpsc → broadcast migration + funding_curve aggregator + V085 + slot + dispatch wire + healthcheck [57]
- E1-β (B-2)：D+3 等 E1-α push 後 rebase 接 broadcast::Receiver pattern + oi_delta aggregator + V087 + slot + dispatch wire + cold-start REST backfill helper + healthcheck [58]
- E1-γ (B-4)：parallel with E1-β（B-4 邏輯 producer-side agnostic）+ V086 + bb_breakout consume + fail-closed evaluation_outcome
- **E1-α gating critical**：mpsc → broadcast migration 影響全 PriceEvent caller（dispatch / paper_state / scanner / tap），E1-α 必須先 grep 全 caller 寫 migration 表，E2 必驗 migration 完整性

**E2 重點審查 3 點 (v1.1)**：
1. Event channel mpsc → broadcast migration 完整性 — 全 caller 是否適配 broadcast::Receiver + Lagged variant handling（漏接 = 策略 silent starve）
2. V085 / V087 schema 對齊 trait struct field + V086 V082 enum 加 `oi_panel_unavailable` value via Guard A IF NOT EXISTS
3. bb_breakout fail-closed 路徑無 silent fallback to internal `oi_buffer` + Aggregator broadcast Lagged 走 WARN log + 計數 + 下次 flush slot 寫 None

**新 risk (v1.1)**：
- Event channel migration silent break：**極高**（E1-α IMPL 必先寫 caller migration 表 + E2 verify）
- WS reconnect gap stale：中（既有 RE-2 supervisor 60s exponential backoff cap，gap 預期 < 60s）
- OI WS rolling delta vs Bybit 5m close-bar 偏差 > ±0.5%：中（W3 Stage 2 evidence 監測，超開 P2 + 啟用 5min REST baseline 加固）

**16 原則 + DOC-08 §12 + 硬邊界 5 項**：v1.1 全 0 觸碰（producer side 切換為純 read-only WS broadcast subscribe + PG write，不動 lease/auth/SM-04/live boundary/IntentProcessor 寫入路徑）

**D+1 sign-off 預期**：PA + BB joint sign-off 直接收（無需 D+1 PA edit + BB integrate 再走一輪）。PM 把 spec v1.1 整合進 dispatch v3.6 §3.1 W1 update（producer side 從 Python writer 改 Rust aggregator + B-3 status DONE + sub-agent dispatch sequence v1.1 update）→ D+2 dispatch W1 IMPL E1-α leader。

**派生教訓**：
- BB push back 採納 pattern：BB 是 Bybit 立場 push back 設計，看似 over-engineering 但 BB 從 rate budget + WS broadcast 既有資源 + 架構一致性三角度正當化 — **HIGH 級 push back 採納省下 100 req/min 永久成本 + lateny 從 60s grain → 即時**
- WS-first vs REST-first 設計選擇：當 WS topic 已 broadcast 所需 field 且 connection 已預設訂閱 → WS-first 永遠優於 REST polling（zero ongoing cost + 即時 + 既有 connection reuse）
- Producer side 切換不影響 consumer：bb_breakout consumer 邏輯與 producer 是 Python writer / Rust aggregator / WS push 完全 decoupled — 設計 boundary 清晰
- Sub-agent sequential gating：mpsc → broadcast 這類 channel migration 類型 IMPL 必有 leader 先 land + 後續 rebase 才安全並行，不可 3 sub-agent 同時改 main.rs

**Report**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w1_spec_v1_1_bb_ws_first_revision.md`


---

## 2026-05-10 W2 A4-C spec v1.1 → v1.2 inline edit (dual-layer σ + PSR(0) strict + +15 gate power verify)

**Trigger**: MIT C-3 σ verify report CONDITIONAL PASS（path: `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w2_c3_sigma_verify_btcusdt_1m_forward_return.md`）

**Key finding from MIT C-3**: BTCUSDT 7d raw market σ_60=4.54 / σ_120=6.28 / σ_300=10.08 bps（比 spec 30 bps preliminary 低 3-7×）；EDGE-DIAG-1 net edge σ=50-80 bps（含 fee+slippage+adverse selection）；spec 30 bps 不對應任何真實層；excess kurt 7-12 ≫ 0 → 必用 PSR(0) skew/kurt-aware formula。

**5 inline edits to spec `srv/docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md`**:
1. §7.1 acceptance prerequisite — 從單一 σ verify line 改 dual-layer σ table（L1 raw + L2 net edge）+ 強制 prerequisite condition（spec power calc 用 net edge σ，禁 raw σ）
2. §7.1 metric (3) PSR(0) — 從 soft 描述改強制條件 formula `Φ((SR - 0) × √(n-1) / √(1 - skew·SR + (kurt-1)/4·SR²))` + σ_net=50/80 bps 兩 case 並列要求
3. §8.1 +15 bps gate power verification table 補完（σ_net=50: t=2.68 p=0.0044 / σ_net=80: t=1.68 p=0.0487 全 PASS marginal at upper bound）+ 中段 + 下界 verification
4. §8.3 sign-off path — v1.2 為 spec internal cleanup（不增 condition、不改 IMPL scope）→ MIT + QC 直接收 W2 IMPL，不需 D+1 PA + MIT 重 sign-off
5. §1 header status v1.1 → v1.2 + §9 risk row σ=30 bps 假設 mark closed + Reference MIT C-3 σ verify report path 補完 + §14 一句總結 update

**Lesson**: σ acceptance 不是「驗一個 σ 數字」是「定明哪一層 σ 對應哪一個 spec 用途」。raw market σ vs net edge σ 差 5-15× 的時候，混用 single-σ acceptance = 用 raw σ 算 power 全 false-PASS（t=29 vs t=1.68）。任何 spec acceptance 涉統計 power 必先 split 「price σ vs edge σ」兩層。

**Sign-off path**: QC C-2 已 sign-off（v1.1 5 conditions revised）；MIT C-3 σ verify 已交付；W2 IMPL 直接收 D+3 起派 C-IMPL-1..4 paper IMPL；不需 D+1 PA + MIT 重 sign-off。

**Report**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w2_a4c_spec_v1_2_dual_layer_sigma_revision.md`

---

## 2026-05-10 PA — ma_crossover BILLUSDT scope pre-verify (D+1 SOP §1.2 Tier 1 #5 預驗)

**Trigger**: PM N+0 sign-off draft 6h spot check 揭露 ma_crossover 6h post-restart 4 fill 全 BILLUSDT (demo 2 + live_demo 2) — 是否 scope drift / cluster transfer 自 grid_trading BILLUSDT n=11 avg=-49.67 bps frozen？

**Verdict**: **Case A** — ma_crossover scope 包 BILLUSDT 合法 (read-only audit 確認三 risk_config + freeze.json 對齊：ma_crossover ban 僅 NAORISUSDT/PENGUUSDT/FARTCOINUSDT/LABUSDT，**不含** BILLUSDT)；**非 bug**；**無需 P1/P2 ticket**；維持觀察。

**核心發現**：
- Frozen JSON 結構 = per-strategy independent cell（grid_trading config_family = strategy_params*.toml；ma_crossover config_family = risk_config*.toml:per_strategy.ma_crossover.blocked_symbols）— 兩者完全獨立，grid freeze 不傳遞至 ma
- ma_crossover BILLUSDT 全期 16 fill (10 demo + 6 live_demo, 4 day window 2026-05-07 至 2026-05-10)，組成 8 round-trip
- 8 round-trip aggregated: demo gross +0.45 / fee 0.53 → net **-0.075 USDT**（fee 吃光）；live_demo gross +0.48 / fee 0.13 → net **+0.346 USDT**（maker entry 費率低）；**combined net = +0.27 USDT**
- 6h post-restart 4 fill = 2 round-trip：demo Buy→Sell 3min DYNAMIC STOP -0.48 USDT；live_demo Buy→Sell 6min trailing +0.27 USDT；duplicate_position reject 0 in BILLUSDT 6h window（**非** P1-MA-CROSSOVER-DUPLICATE-INTENT hot loop pattern）
- **QC W6 RFC §3 cluster verdict 不可傳遞**：grid 走 mean-reversion / ma 走 trend-following，alpha source 不同；ma BILLUSDT trailing exit 1-3min hold 顯示 ma 對該 symbol 短期動量 capture 工作

**派生發現**：BILLUSDT ma_crossover 8 round-trip 中 3 個 (37.5%) phys_lock_gate4_giveback 平倉（高於 W6 整體 ~10-15%）— 可能 BILLUSDT 0.01 級價格 + bps noise 與 phys_lock gate 4 threshold 互動效應；**屬 phys_lock 算法 vs low-price symbol 互動，非 BILLUSDT scope 問題**；歸入 W-AUDIT-8a Phase B/C 觀察 (alpha surface 升級後重評) 或 W-AUDIT-9 stage stats

**承接機制**：W5 P1-DYNAMIC-UNBLOCK-CHECK-1 spec land 後，30d evaluation queue 自動承接 ma_crossover BILLUSDT（無需 manual P2）

**D+1 SOP update**: §1.2 Tier 1 #5 ma_crossover BILLUSDT scope verify 已 pre-verified，D+1 EOD spot check **drop**；改為 monitor 24h backfill 進來的 net_bps via `[40]` MLDE 平面 attribution，若 24h cumulative ma_crossover BILLUSDT avg_net_bps < -50 bps 才升 P2 freeze evaluation

**16 原則 + DOC-08 §12 + 硬邊界 5 項**：全 0 觸碰（純 read-only audit, 無 IMPL 改動）

**Report**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--ma_crossover_billusdt_scope_verify.md`

**Lesson**: 同 symbol 在不同 alpha source 策略間「freeze cluster verdict 不可傳遞」是 governance pattern — grid mean-reversion 在 BILLUSDT 失敗 ≠ ma trend-following 在 BILLUSDT 失敗；frozen JSON 設計成 per-strategy cell 正是此意。多策略治理 sign-off 必檢「cluster verdict scope = 哪策略」，避免錯誤套用導致過早 freeze 縮 trade-eligible universe（會與 W5 selection-bias unblock 機制反向衝突）。

## 2026-05-10 W7-4 5 策略 position sync post-W7-deploy systemic audit refresh

PA refresh of W7-4 systemic audit done **post-W7 chain land**：W7-3 `b42731f6` deployed (engine PID 1441249 baseline), W7-1 `c9fb0b8f` + W7-2 `22efd9de` + W7-5 `bb7cb293` PR ready (NOT DEPLOYED, pending sign-off restart). HEAD `94d688fb`. Audit framework = 4 audit point matrix per CC dispatch (entry query / on_fill / on_rejection 1-tick defense / bootstrap import).

### Post-IMPL coverage matrix
- **ma_crossover** = A (full coverage：W7-2 entry query @ strategy_impl.rs:253-266 + W7-3 on_rejection 1-tick defense @ :55-91 + W7-5 on_fill @ :131-148 + import_positions @ :159-175)
- **bb_reversion** = B (W7-2 entry query land @ mod.rs:500-512 + W7-5 on_fill+import 全 land；but **on_rejection W7-3 Option B 1-tick defense 缺**)
- **bb_breakout** = C (only W7-5 on_fill+import 包；**entry path 完全沒查 ctx.position_state** + **on_rejection 沒 W7-3 1-tick defense**)
- **grid_trading** = A (by-design alternative：inventory model + M-2 30s reject_cooldown 結構性護欄 + W7-5 on_fill 顯式 by-design no-op + import_positions sign convention preserved)
- **funding_arb** = A (RETIRED-LOW dormant ADR-0018 + 1h cooldown + 8h funding cycle 結構性護欄 + W7-5 defensive 寫入)

### Discovered tickets
- **P1-1** bb_reversion on_rejection 1-tick defense missing (~30 LOC mirror ma_crossover) — Sprint N+1 W5 if capacity
- **P1-2** bb_breakout on_rejection 1-tick defense missing (~35 LOC, oi_buffer interaction needs care) — Sprint N+2 W5
- **P2-1** bb_breakout entry path Option A query missing (~30 LOC, entry_price 不應 cross-strategy 同步) — Sprint N+2 paired with P1-2
- **P3** trait-level invariant strengthening (Option 1 doc / Option 2 helper / Option 3 trait method) — Sprint N+3 RFC

### 系統性結論
W7-3 Option B (on_rejection duplicate_position 1-tick defense) **未被傳播到 bb_reversion/bb_breakout**；W7-2 (entry path Option A) 被傳到 bb_reversion 但 **沒推到 bb_breakout**。W7 chain 是「partial systemic fix」— W7-2 entry-path Option A 跟 W7-3 on_rejection Option B 在 4 策略中只有 ma_crossover 同時擁有兩道防線。

### 治理盲點 finding
Strategy trait (`strategies/mod.rs`) 對 W7 pattern **不強制**：on_rejection / on_fill / import_positions 全是 default no-op，rely on 策略作者主動 override。W7-5 design 把 on_fill+import 的 callsite 拉到 trait（orchestrator 對所有策略 blind iterate），所以這兩點 100% uniform；但 entry-path Option A + on_rejection Option B 是 strategy-internal pattern，沒 trait-level 強制 → 未來 6th strategy 重蹈同樣 desync hot-loop 風險的 systemic gap 存在。

### 執行影響
- bb_reversion residual race window 估計 <10/day per cohort（W6 baseline 0 visible burst）— P1 修復 cost-benefit 高
- bb_breakout 0 historical occurrence（6-gate 自然限頻）— P1+P2 paired 修復對齊 ma_crossover gold standard，治理完備性
- 不阻 N+1 D+0 deploy；P1-1 + P1-2 + P2-1 進 dispatch v3.X §3.5 W5 list

### 16 原則 + DOC-08 §12 + 硬邊界
全 0 觸碰（純 read-only audit, 無 IMPL 改動）。

**Report**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w7_4_5_strategy_position_sync_systemic_audit.md`

**Lesson**: 「partial systemic fix」是 governance 失蹤 — 認識到 root-cause 結構是 systemic（W7-2 commit 訊息明確說「bb_reversion 同 pattern apply (per W7-4 §3 verdict HIGH risk)」）但 fix coverage 只覆蓋部分 surface（W7-3 沒有 propagation policy）。後續 systemic audit 必明文 verify「fix pattern 是否覆蓋全 surface 而不只 commit 訊息列出的 surface」，避免 W7 chain 這類 Option B 1-tick defense 三策略漏二的盲區。

---

## 2026-05-10 W6-1 RFC final verdict — PA sign-off (APPROVE-CONDITIONAL)

**性質**：D+1 W6-1 RFC final verdict draft PA 視角 cold review + sign-off。
**Verdict**: APPROVE-CONDITIONAL（4 verdict fidelity HIGH；2 push back fix-forward 同次 commit；Track A 由現資源吸收；Track B (e) gate 補完）

**4 verdict fidelity verify**：
- Verdict 1 (cost_gate hard rule 維持) — APPROVE，與 PA 原 RFC Q1 hold A 全 capture，反指 + 16 root principle 對照 + N+2 重提防線完整
- Verdict 2 (JS shrinkage 強收縮 grand_mean 是設計) — APPROVE，QC 視角主導但與 PA cost_gate 立場 consistent，N+2 重評觸發點 (W2 A4-C 或 W-AUDIT-8a Phase B/C/D) 明文
- Verdict 3 (cost_gate 放行 expected -14 bps) — APPROVE，Kelly/DSR 雙重否決邏輯加分，4 項 bias 修正成本 ≥1 sprint vs 已知 -14 bps ROI 計算正確
- Verdict 4 (scorer_trainer LightGBM regression confirm) — APPROVE，MIT W6-5 category error 完整 capture，Track A/B 拆分解 PA Q3 hold A vs MIT Q2 hold B 分歧

**V086 IMPL E1 finding 接收**：
- E1 §3.2 OR-filter 缺陷 + 推薦方案 A（accept + spec 註解修正）
- PA 立場：ACCEPT 方案 A — Guard C 兩次都 PASS、overlap_n=0、deterministic CASE WHEN 寫同值是 lossless idempotent；方案 B 不可行（驗證過 producer dual-write 後 AND 也會 trigger UPDATE）；方案 C 成本高收益低
- 修正 action：D+1 evening W6-3c E2 review 同次 commit V086 SQL §2 註解 wording 修正

**Track A immediate path 安排**：
- 由現有 W6-5 dispatch 吸收（不需新 wave）
- W6-5 sample_weight ratio sensitivity (1/100/1/170/1/300/1/500) 在 LightGBM regression `lgb.Dataset(weight=...)` 路徑上是 1-line config sweep，MIT 1 day 充裕
- 與 W6-2/W6-3c/W6-3d/W6-4/W6-6/W6-7/W6-9/W6-10 全部正交，可 D+3 起 MIT 並行跑

**3 push back（2 fix-forward + 1 informational）**：
1. **PB#1 (低 severity)**：W6-3c E2 review wave 同次 commit V086 SQL §2 註解 wording 修正（避免 D+1 evening engine restart 後 SQL 註解與 PG runtime 行為 inconsistency window）
2. **PB#2 (中 severity)**：補 Track B 4-gate 之 (e) gate「W6 N+1 期間每週 reject + close 各 enum sample 累積進度週報 healthcheck `[63]`」（為 N+2 spec phase 啟動 timing 提供 evidence stream）
3. **PB#3 (informational)**：AMD-2026-05-1X-W6-1 件加 cross-ref 4-agent loss audit 4 報告 evidence path

**N+2/N+3 Track B 啟動 dependency**（5 gate map）：
- (a) V086 land + 24h dual-write 0 NULL drift — N+1 D+2 14:30 UTC 後
- (b) multi-class 18+ enum 各 ≥ 200 row — N+2 mid-Sprint（4 reject ≥200, 4 close <200 待累，funding_arb 永不過 per ADR-0018）
- (c) classification trainer task 升級 spec — N+2 spec phase + N+3 IMPL phase
- (d) imbalance handling 試行報告 PASS — N+3 IMPL phase
- (e) [63] weekly sample 累積 healthcheck（PA 新加） — N+1 D+2 起 cron continuous

**Confidence**: HIGH（4 verdict fidelity HIGH + 2 push back fix-forward + Track A 現資源吸收 + Track B sequence 清晰）

**唯一不確定**：QC + MIT 視角 verify 結果未知（task spec 不跨範圍）；D+1 下午 1h 三角 sync 解決

**Sign-off Action Items (D+1 evening 同次 commit)**：
1. PM 升 draft 為 AMD-2026-05-1X-W6-1-rfc-verdict.md
2. AMD 件加 §11 cross-ref evidence chain
3. W6-3c E2 review wave 加 V086 SQL §2 註解 wording 修正
4. W6-9 wave 加 [63] healthcheck IMPL
5. dispatch v3.7 §3.0 + §6 cross-ref AMD
6. CLAUDE.md §三 W6 wave 一行總結 land
7. PA memory.md 追加 W6-1 verdict 摘要（即本條）

**Report**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_1_rfc_pa_signoff_verdict.md`

## 2026-05-10 AMD-2026-05-11-W6-1 Draft — 14 Push Back Absorb (PA APPROVE-DRAFT)

**性質**：W6-1 RFC final verdict draft 三角 sign-off 完成（PA + QC + MIT 全 APPROVE-CONDITIONAL）後，PA 起草 AMD 正式件 absorb 14 push back items 為 governance amendment。
**Verdict**: APPROVE-DRAFT（14/14 push back 全 capture HIGH fidelity；4/4 verdict fidelity HIGH；PA 對抗性自評 PASS；待 QC + MIT verify push back absorb fidelity + PM 統合 sign-off + Operator 拍板）

**14 push back 分類處理**：
- **5 條 doc/wording fix 立即 land**：PA PB#1 + QC PB#1 + MIT MUST 1 (V086 SQL §2 註解三方同源) + PA PB#3 (4-agent loss audit cross-ref) + MIT MUST 4 (CLAUDE.md §七 idempotency wording — operator 動)
- **5 條 quant/acceptance gate update**：QC PB#2 + MIT SHOULD 6 (Track B (b) per-class N + 核心 5 策略 ≥3 整合) + QC PB#3 (Track A pre-M3 era filter) + QC PB#4 ([40] LOW_SAMPLE flag) + PA PB#2 (Track B (e) gate weekly HC [63])
- **3 條 IMPL 已 land/IN FLIGHT**：MIT MUST 5 memory chain era-split ✅ DONE (commits 332a2f9c + 9159362c) / MIT SHOULD 7 chain integrity HC [65] ✅ DONE (commit db17e205) / MIT MUST 2 V091 schema mutex CHECK NOT VALID 🟢 IN FLIGHT (skeleton commit 50e75bff + sub-agent a254b07d 跑中)
- **1 條 IMPL 待 D+1+**：MIT MUST 3 W6-5 試行 5 ML pipeline metrics + purge+embargo CV (per-fold RMSE 95% CI / IS-OOS gap / cross-fold std/mean / PSI+KS / cost_gate decision distribution shift)

**4 verdict fidelity verify (三角 sign-off 結果)**：
- Verdict 1 cost_gate hard rule 維持: PA APPROVE / QC APPROVE FULL / MIT APPROVE — 16 root principles + Rust source + 數學否決鏈 + 反指 + N+2 防線 全保留
- Verdict 2 JS shrinkage signature: PA APPROVE / QC APPROVE FULL / MIT APPROVE — JS B 公式 + 4 cells std=1.04 bps + Unwind 唯一途徑 grand_mean 翻正 全保留
- Verdict 3 expected -14 bps 不需 counterfactual: PA APPROVE / QC APPROVE FULL / MIT APPROVE — 數學論據 + 4 bias 修正成本 + Kelly/DSR 雙重否決 全保留
- Verdict 4 scorer regression task type: PA APPROVE / QC APPROVE FULL / MIT APPROVE FULLY — MIT category error + sample_weight contribution weighting + QC PB#1 wording 修正 (移除 "cost_gate decision distribution" 誤導)

**整合 wording 設計** (QC PB#2 + MIT SHOULD 6 同源不同 wording)：
- MIT SHOULD 6 wording 主：「核心 5 策略中 ≥3 策略各 class sample ≥ 200」+ funding_arb 排除清單 hard-code per ADR-0018
- QC PB#2 wording 補強：對選定 ≥3 策略內，per-class N ≥ 60 for ≥80% enum (detect Δ=0.5 with α=0.05 Bonferroni 修正後 power ≈ 0.65) OR per-class N ≥ 240 全 enum
- 兩條件擇一滿足即 (b) gate PASS；解 funding_arb 永遠 blocking 風險 + per-class N quant 統計 power 要求兩維度

**Track B 5-gate 修訂** (原 4-gate + (e) gate per PA PB#2)：(a) V086 land + 24h dual-write 0 NULL drift / (b) 核心 5 策略中 ≥3 策略 + per-class N quant 標準 / (c) classification trainer task spec / (d) imbalance handling 試行 / (e) N+1 期間 weekly sample 累積 healthcheck [63]

**16/16 root principles compliance + 0 DOC-08 §12 不變量觸碰 + 0 §四 硬邊界觸碰** — 評級 A

**D+1 critical path** (per AMD §10)：
1. D+1 08:00 UTC: AMD draft commit + push
2. D+1 09:00 UTC: V091 sub-agent IMPL 完成 + commit + push
3. D+1 12:00 UTC: PA + QC + MIT verify 本 AMD push back absorb fidelity
4. D+1 20:00 UTC: engine restart_all --rebuild --keep-auth deploy V086 producer code
5. D+2 14:30 UTC: ALTER TABLE VALIDATE CONSTRAINT V091 ENFORCE

**E2 重點審查 3 點** (V086 SQL §2 註解 wording / V091 Guard A/B/C 完整性 / W6-9 [63] healthcheck SQL design)

**Confidence**: HIGH (14 push back 全 capture + 4 verdict fidelity HIGH + IMPL status transparent + PA 對抗性自評 PASS + 16 principles A 級 + 副作用 transparent)

**Open items**:
1. CLAUDE.md §七 idempotency wording 修正屬 operator 動作 (per MIT MUST 4)，時點不在 PA 控制
2. V091 sub-agent (a254b07d) IMPL 完成 timing 取決於 sub-agent runtime
3. (b) gate 4 close enum < 200 永不過 risk — N+2 spec phase work item

**Lesson** (與 W6 chain 5 round 教訓延續): AMD absorb 14 push back 整合處理「兩源 push back 同事項」(PA PB#1 + MIT MUST 1 V086 SQL 註解 / QC PB#2 + MIT SHOULD 6 Track B (b) gate) 必明標兩源並合併 acceptance criteria — 不可任一 push back 獨立 absorb 而把另一視為 redundant，三角 sign-off 各自立場必全保留。

**Reports**:
- AMD draft: `srv/docs/governance_dev/amendments/2026-05-11--AMD-2026-05-11-W6-1-rfc-final-verdict-absorb.md` (608 LOC)
- PA sign-off: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--amd_w6_1_draft_pa_signoff.md` (264 LOC)

---

## W-D MAG-083 Final Release Audit — PA View（2026-05-11）

**Verdict**: APPROVE WITH P1 FOLLOW-UP

**Subject**: W-D MAG-083 final release audit 三角第 2 角（PA 架構視角）；並行 QA（端到端）+ QC（統計/數學）。Pre-condition：W-C MAG-082 Stage 2 WINDOW_PASS sign-off `2026-05-11--w_c_window_pass_signoff.md` 已 sign（cloud@ncyu.me 2026-05-11）+ deploy commit `ccf7a4bc`。

**架構整合 sound**：
- Caveat 1+2 修復鏈字面對齊 PA spec § 1/2 + Option α + Migration A 三層設計
- 新增 callsite hot path SLA 安全（emit_entry_lineage +3-6μs / emit_fill_completion_lineage 10-20μs）
- mpsc channel 容量充裕（68 chain in-flight vs 7 chain/h avg）
- 硬邊界 5 項 0 觸碰 / DOC-08 §12 9 不變量 0 觸碰 / 16 原則 0 違反（#8 strengthened）

**0 P0 architectural gap**；**7 個 P1 follow-up + 3 個 P2**：
- P1-1 `stable_id` 算法字面複製 3 處（E5 D-1 P2 升 P1，silent id drift 風險）
- P1-2 Stage 3+ promotion 與真實 Decision Lease 9-state lifecycle 證據要求（W-C bypass 不可繼承）
- P1-3 `executor_canary_stage_log` (W-AUDIT-9) 與 `agent.decision_state_changes` (W-C) 跨 SM 對齊
- P1-4 AlphaSurface (W-AUDIT-8a) 與 spine writer alpha source tagging 接線（per-alpha-source live promotion gate R-4 隱性依賴）
- P1-5 PendingOrder.spine_verdict_id 保留位 N+2 前必須使用或移除
- P1-6 `[55]` healthcheck 24h transition window 不能成 silent FAIL 漂移源
- P1-7 commit `ccf7a4bc` 27 file 含 sibling W2 wave 結構性改動 — reviewer brief 必明文 W-C 純度

**PA self-review on Caveat 1+2 修復方案完整度**：
- 8/9 動作項 land 完整
- 3 IMPL Deviation（PendingOrder 4 欄位非 3 / Historical stub option c 非 a / R2 fix C-A.2）全部 PA 接受
- 1 spec ambiguity acknowledged：transition.object_id 應對既有 row 寫的 SM 不變式（spec § 1.3 表內未明確區分）
- 整體 A-（A 是 spec 0 ambiguity；A- 是 transition.object_id ambiguity 留教訓）

**架構教訓 1**：spec 寫 transition table 時必須明文「transition 描述既有 object 狀態變化，不在新建 object 自身上掛 from_state」— append-only event log 哲學的 SM 不變式表達需強化

**架構教訓 2**：升 P1（從 E5 D-1 P2）`stable_id` helper 抽出 — 跨檔字面複製 3 處是 sub-architectural silent drift 風險源；當改算法時漏改一處 = audit chain 沉默斷裂 = MAG-082 evidence 信任崩塌；30min effort 緊接 MAG-084 後 24-48h 內 fix

**架構教訓 3**：W-AUDIT-9 graduated canary 5-stage 與 W-C 兩條 SM log 是不同抽象層（cohort 級 vs chain 級）— 不需強制 cross-ref，但建議 W-AUDIT-9 T5 GUI surface spec 加 cross-table join query；同 commit 加 P2 schema cross-ref ticket

**架構教訓 4**：commit 純度政策補強 — sibling wave 結構性改動跟 W-C 同 commit `ccf7a4bc` 27 file 後，reviewer brief 必明文 W-C scope = 4 primary + 11 secondary file；sibling W2 wave separate wave authority；未來大 PR 同 commit policy 需強化「pre-existing baseline exception clause」配套說明

**Reports**:
- PA audit: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--w_d_mag083_pa_audit.md`
- W-C WINDOW_PASS sign-off: `srv/docs/governance_dev/2026-05-11--w_c_window_pass_signoff.md`
- PA Caveat 1+2 fix plan: `srv/docs/CCAgentWorkSpace/PA/2026-05-10--w_c_caveat_fix_plan.md`

---

## 2026-05-11 P1 V083 ipc_close_symbol entry_context_id 卡 buffer 設計

**問題**：engine restart 後 V083 chk_fills_close_has_entry_context_id_v083 constraint 每 2 秒拒寫 risk_close:ipc_close_symbol fill；22 min 518 INSERT 失敗、buffer 卡住、PnL 帳目漏接。

**Operator RCA 給的根因確認**：
- commands.rs:1108-1112 `unwrap_or("")` → 空字串 → V083 reject

**PA 親查新發現的閉環失效**：
1. **Writer 假 fail-soft**：trading_writer.rs:194-208 `should_clear_buffer` 是 chunk 級失敗→buf 不清→無限重試。V083 SQL line 39-41「writer-side WARN log fail-soft」設計只有 WARN log 落地，INSERT 路徑沒做 row-level fallback。單一違規 row 永久卡 buf 頭。
2. **Cron backfill SQL 約束破洞**：edge_label_backfill.py:435 `entry.strategy_name = c.strategy_name` 嚴格匹配。但 ipc_close_symbol 寫 strategy_name=`risk_close:ipc_close_symbol`、ipc_close_all 寫 `ipc_close_all`，與原 entry 的 strategy（`ma_crossover` 等）不一致 → cron 永遠 match 不到 → 無法後補。

**設計方案**：Option B + Option C 混合
- **Option B 第一波止血（≤1h）**：抽 `resolve_close_entry_context_id(symbol, ts_ms)` helper，paper_state 沒有時 fallback 為 `orphan_recovery_ctx:{symbol}:{ts_ms}` synthetic id。改 4-5 處 close call site（commands.rs:1108、945、1183、512、749）。~30 LOC，無 SQL 改動，無新依賴。
- **Option C 第二波永久防線**：trading_writer.rs row-level fail-soft + V088 sidecar table。下 sprint 處理。
- **Option A/D 否決**：A 違 H0 <1ms SLA；D 破 ML training 完整性。

**Cross-strategy 影響廣度**：所有 risk_close:* / ipc_close_* / orphan close 共用 bug；不是單點。

**架構教訓 1**：「fail-soft 設計」要驗證**真實 INSERT 路徑的 fail-soft**，不只 log 維度。V083 設計時 SQL 注釋寫了「WARN log fail-soft 不阻 INSERT」，但 writer 端沒實作 row-level fallback，整個 chunk 仍 fail → buffer 卡死。設計→落地 gap，IMPL 端未捕。

**架構教訓 2**：cron backfill SQL 約束（`entry.strategy_name = c.strategy_name`）vs producer 端 strategy_name 標籤（`risk_close:*` / `ipc_close_*`）不對齊 = 設計時未跨 path 對齊「strategy_name semantic」。M2 wave 設計時應強制：close path strategy_name 與 entry strategy_name 不同時，backfill SQL 必須有 fallback path。

**架構教訓 3**：synthetic id pattern 是好的「placeholder + 後補」設計範式 — `orphan_recovery_ctx:{symbol}:{ts_ms}` well-formed 可被 cron 識別。優於 silent NULL 或 silent drop。

**Reports**:
- 設計報告：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p1_v083_ipc_close_fix_design.md`
- 設計報告：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p1_rca1_f1_f2_emergency_fix_plan.md`

---

## 2026-05-11 P1-RCA-1 F1+F2 emergency fix dispatch plan（4-bug chain）

**背景**：E1 RCA `ed6b2619` 升級 W-D MAG-083 R-1 從 QA 原判 non-systemic → **SYSTEMIC**。Root cause = 4-bug chain：
- B1 P0: V083 NOT VALID CHECK × IPC close path empty entry_context_id × sqlx 多 row batch INSERT = 整 chunk reject 持續 retry 直至 engine shutdown buffer drop（3min 26s window trading.fills 0 row）
- B2 P1: trading_writer.rs:411-414 WARN「rows still INSERT (fail-soft)」誤導，實際整 chunk reject
- B3 P1: batch_insert.rs:run_chunks 無 bad-row isolation
- B4 P1: PostOnly partial vs Bybit Filled reconcile gap（loop_exchange.rs:357+）

**PA 派發決策**：
1. **F1 + F2 必同次 deploy**（4 並行 sub-agent ~4-6h workload）：
   - E1-F1 改 `commands.rs` 4 callsite（ipc_close_symbol exchange + paper / execute_position_close / ipc_close_all）用 fallback chain `paper_state.get_entry_context_id(symbol).map(...).unwrap_or_else(|| make_context_id(em, symbol, ts_ms))`；correct E1 RCA 文字（line 1108-1112 已用 get_entry_context_id 但 `unwrap_or("")` 退到空串）
   - E1-F2 改 `batch_insert.rs:run_chunks` 加 `binary_split_isolate` async helper（Box::pin recurse 防 infinite-size future）+ `BatchInsertOutcome.bad_rows` 新欄位
   - 兩 E1 並行 0 file 重疊
2. **緊急 mitigation verdict = 不 drop V083 CHECK**（Option B）：
   - 理由：F1+F2 4-6h workload 短；DROP + reapply 1-2h 反更破 W-AUDIT-4b-M2 設計；F1 fallback chain 已 fail-soft；F1 deploy 後 V083 violation 自動消除
   - Option A trigger gate：F1+F2 撞硬阻塞 ≥ 24h 才 escalate
3. **PA verdict synthetic context_id 用 make_context_id 格式**（不是 sentinel "unknown_context_id"）：保持下游 ML JOIN schema 一致；Telemetry-friendly identify
4. **F3 / F4 N+1 schedule**：F3 single E1 30min（trading_writer.rs:406-414 WARN→ERROR + 文案修正），F4 single E1 1h（OrderUpdate(Filled) 殘量 reconcile + bybit_reconcile_done idempotency flag）
5. **跨 wave 衝突檢查**：F1+F2 vs W2 IMPL `0e88b4a9` / E2 P1-1 review `a45f0978` / Phase 3 V091 deploy / W6/W7/W3/W4/W5 11 active wave **0 file 重疊**；可立即派發

**MAG-084 status update 建議**：§5 P1-RCA-1 升 BLOCKED；建議開新 **W-E wave**（不 reopen W-D），W-E-T1..T6 6 track 結構。最終 verdict 留 operator。

**架構新教訓 4**：E1 RCA `unwrap_or("")` 退 empty string 比「沒設」更隱蔽 — empty string 是 producer 端「我嘗試了但沒拿到」的 silent signal，不是 silent NULL；trading_writer 把 empty → NULL transform（line 486-490）只是 schema 上拿到 NULL，但 producer 端 TradingMsg::Fill 的 entry_context_id 字段是 String 不是 Option，empty 是「合法值」但語意上是「缺值」。**PA 設計準則**：任何 fallback 路徑必有 deterministic fill（不能 empty string），且必須在 producer 端就解決，不依賴 writer-side transform。

**架構新教訓 5**：F1+F2 必同次 deploy 是 **「fix chain 完整性」原則** — single deploy intermediate state 兩面都有風險：F1 alone 只修一個 close path（7 個 close path 仍可能漏）；F2 alone 不修源頭 → 持續 noise + telemetry pollution。**PA 設計準則**：root cause 是 chain 時，每個 link 都不可單 deploy，必同一 restart_all 生效。

**架構新教訓 6**：binary-split recurse 的 Rust async 限制 — async fn 直接遞迴 → infinite-size future compile error；必用 `Box::pin(async move {...})` 包裝 + `BoxFuture`。Test 必 verify recurse depth bounded by ceil(log2(chunk_rows))；MAX_CHUNK_ROWS = 10_000 → max depth 14，stack safe。

**Reports**:
- 設計報告：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p1_rca1_f1_f2_emergency_fix_plan.md`
- E1 RCA 對齊：`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p1_rca1_orphan_er_missed_fill.md`

---

## 2026-05-11 P0 22:08 deploy edge regression RCA — 3 commit 排除 + 真實 root cause

**性質**：Operator P0 RCA — 22:08 +0200 May 10 engine restart 後 edge 連續 9h 翻負；分析 6 個業務 [skip ci] commit 嫌疑（5de8df5f Wire decision lease / 8070f98d Route executor intents / ca5f4305 Centralize alpha source / 97658947 live candidate / fb7ac290 replay prepare / 2c258238 OpenClaw boundary）

**Verdict**：3 嫌疑 commit + 3 次嫌疑 commit **ALL CLEARED**；真實 root cause = 22:08 watchdog **Auto restart**（kind=Auto, NOT --rebuild deploy）後 paper_state reset 引發 grid_trading 大量 0-duration scalping

**關鍵發現 1（時序錯位）**：
- 22:08 engine boot log 顯示 `kind=Auto`，**不是 operator restart_all --rebuild**
- 22:08 binary = 15:48 binary（同一 build artifact），6 個 [skip ci] commit **不在內**
- Auto restart 不重編譯，operator 認知「22:08 是 deploy 引入 6 commit」**錯誤**

**關鍵發現 2（嫌疑全清）**：
- **5de8df5f Wire decision lease**：即使含此 commit，bypass mode = LeaseId::Bypass.release_lease() return Ok(()) NO-OP；channel = mpsc::unbounded 不阻塞；全 path 早退（is_primary 守衛）→ 0 影響
- **8070f98d Route executor intents**：真實 demo runtime 不走 ExecutorAgent.on_message（OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow），整個 commit 對交易 hot path 0 影響
- **ca5f4305 Centralize alpha source**：唯一語義變化 `AlphaSourceTag::CrossAsset` false → btc_lead_lag.is_some()，**只影響 dispatched_counter 統計**，不影響 strategy dispatching logic
- **97658947 / fb7ac290 / 2c258238**：純 Python 非熱路徑

**關鍵發現 3（真實 cause）**：
PG fills 直查證據：
- 18-19h（Sprint N+0 morning regime）：12 fills，gross $2.95，**avg $0.246/fill**，「Buy 跨 N 分鐘 Sell」（grid hold）
- 22h-23h（22:08 Auto restart 後）：20 fills，gross $0.031，**avg $0.0015/fill**，**「Sell + Buy 同 ts」instant scalp**
- 01-05h（持續）：124 fills，gross $1.18，avg $0.0095/fill，持續 instant scalp pattern

22:08 watchdog Auto restart 後 paper_state.positions seed count=0；grid_layout 重 rebuild 所有 grid level；EU evening 22h market liquidity 低 + grid scanner stale memory → grid layout 立即 fire instant scalp。fees 結構性 > gross。

**架構教訓 1**：**deploy verify 必先 check engine boot kind**（Manual=operator --rebuild / Auto=watchdog respawn）；前者才是 deploy event，後者不引入新代碼。Operator 認知「22:08 deploy 6 commit」未驗證 boot kind = 時序錯位 root error。

**架構教訓 2**：**watchdog Auto restart 對策略 hot path 是有害事件，不是無害事件**。paper_state reset → grid_trading 立即重建 layout → 0-duration scalp fee bleeding。grid_trading restart warmup 邏輯缺。

**架構教訓 3**：**5 textbook 策略結構性 alpha-deficient 結論進一步驗證**（與 Sprint N+0 closure memory 對齊）。grid_trading 沒真實 alpha，只賺 grid spread；paper_state reset = grid 重建 = fee bleeding 機制。

**架構教訓 4**：Cross-check Decision Lease 路徑覆蓋率時，**必看 LeaseId::Bypass return path**——所有 Bypass 路徑 release_lease return Ok(()) 是 NO-OP。runtime 在 W-C shadow mode 下整條 lease release 鏈條都是裝飾性的（只發 LeaseTransitionMsg + log），對交易行為 0 影響。

**架構教訓 5**：Mac PA cold review PG query 透過 ssh + PGPASSWORD 順利，但 fills schema 假設錯（ts_ms vs ts timestamp）trial-error 浪費 ~3min。Mac 端應在 RCA 啟動序列加 `psql \d trading.fills` schema verify。

**Operator action 推薦**：
1. **emergency disable grid_trading** 1h 觀察 bleed 是否止住（最快驗證）
2. 派 E1 design grid_trading restart warmup（engine boot 後 N min 內 grid 不發單，等 paper_state cohesion）
3. cost_gate 在 grid instant scalp（fill_qty same ts 內 Sell+Buy）的 fee check 加強

**Confidence**: HIGH for「3 commit 排除」「22:08 是 watchdog Auto」「root cause = paper_state reset + grid instant scalp」；MEDIUM-HIGH for「為什麼 morning 15:48 Manual restart 後沒爆量」（推測 EU morning liquidity 高 + scanner 30min cycle 起 warmup_delay 生效，未深查 grid_trading 源碼）

**16 原則 + Hard Boundary**: 0 觸碰；違反原則 #5（生存>利潤）+ #6（失敗默認收縮）— grid restart 後缺保守 warmup

**Report**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p0_22h08_deploy_edge_regression_rca.md`

---

## 2026-05-11 — P0 Option A SSoT Refactor push back（連續虧損 9h+ 救火）

**Operator 提的方案**：Option A 單一方案，消除 5 策略本地 `self.positions`，全 paper_state SSoT。

**PA push back**：65% NO-GO atomic Option A，理由 3 個 BLOCKER：
1. **grid_trading.net_inventory 是 grid-level 累積 qty**（-2/-1/0/+1/+2），不是 boolean；paper_state 無此資訊。直接搬走 → grid signal 邏輯破。
2. **bb_breakout.entry_price + trailing_stop 強耦合 position lifecycle**：trailing_stop ratchet math 需要本地 entry_price，paper_state 不存。
3. **on_external_close 對 strategy-internal state cleanup 必保留**（trailing_stop / squeeze / oi_buffer / grid level）。

**Option A-Lite（PA 推薦，85% GO）**：
- ma_crossover + bb_reversion + funding_arb：移除 self.positions（純 boolean direction marker），改查 ctx.position_state + owner_strategy gate
- bb_breakout：移除 BbBreakoutPerSymbolState.position 一個欄位；保留 entry_price/trailing_stop/squeeze_detected_ms/oi_buffer
- grid_trading：不動 net_inventory；加 cross_strategy_holds gate

**真正 root bug**：不是「策略本地持有 state」，而是「策略 exit gate 沒查 `paper_state.owner_strategy == self.name()`」。W7-2 entry-path 同步 self.positions=paper_state.is_long 反而把策略「升級」成「我擁有所有 cross-strategy 倉位」→ bb_reversion 寬 exit zone [0.2, 0.8] 觸發 mass close → emit_close_fill 取 paper_state 真實 owner (grid_trading) + close_tag (bb_mean_revert) → fills 表混合 row。

**緊急 hot-fix 推薦（不等 Option A-Lite，30 min ship）**：
1. bb_reversion exit zone [0.2, 0.8] 縮 [0.45, 0.55]（textbook 0.5 ± 0.05）TOML
2. bb_reversion on_tick exit 分支加 `ctx.position_state.owner_strategy == "bb_reversion"` gate（~10 LOC）
3. ssh restart_all --rebuild --keep-auth

**E1 IMPL spec**：5 並行（E1-A ma / E1-B bb_reversion / E1-C bb_breakout / E1-D grid / E1-E funding_arb dormant）+ E1-F merge wave；總工時 5-7h，~-280 LOC + 162 tests 改寫 + 30 W7-* tests 刪除。

**部署順序**：分 3 wave（funding_arb dormant smoke → bb_breakout+grid_trading → ma+bb_reversion atomic），每 wave 後 30 min 觀察 [40] avg_net + fills 混合 row 檢查。

**E2 重點審查 3 點**：
1. exit gate 必查 owner_strategy（grep `match.*position_state` 或 `Some(is_long)` exit branch 必含 owner check）
2. bb_breakout 保留 entry_price/trailing_stop/squeeze_detected_ms/oi_buffer 4 欄位（不能砍）
3. grid_trading net_inventory 不能砍（E1-D 只加 cross_strategy_holds gate）

**16 原則 + Hard Boundary**：0 觸碰；強化 #4（策略不繞風控 — exit owner check 是新加 gate）+ #5（生存>利潤 — Phase 0 立即止血）+ #6（失敗默認收縮 — cross-strategy 持倉時 strategy backoff）

**架構教訓 6**：「策略本地 state 全消除」這個 framing 太宏觀，真正 root bug 是「exit gate 缺 owner_strategy 判斷」。Operator 的 SSoT 直覺對，但實作必先做 5 策略 audit 確認 state 結構差異（boolean direction vs 累積 qty vs lifecycle 強耦合 math state）。

**Confidence**：HIGH for「Option A-Lite」可行；HIGH for「Phase 0 hot-fix 救火」；MEDIUM for「Wave 1-3 部署順序」（仍可選 atomic）；LOW for「operator 是否接受 Option A-Lite 而非堅持純 Option A」（推薦 fallback：paper_state +2 columns(grid_level, trailing_stop) 重設計 + 2-3d 工作量）

**Report**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p0_option_a_position_state_ssot_refactor.md`

---

## 2026-05-11 — F3/F4 Writer-Side Defense N+1 Dispatch Plan

**Scope**: P1-RCA-1 4-bug chain 剩餘 writer-side 永久防線 F3/F4 spec 加深 + Sprint N+1 W5 schedule + F4 option 拍板。F1+F2 emergency closed earlier today + B1 Option B `d4867676` producer-side land + W2 IMPL chain `a771226d` + Option A-Lite Wave 1 `ebbcc038` 全 closed。

**F3 Spec**: `trading_writer.rs:406-414` WARN→ERROR + 文案準確化（移除「rows still INSERT (fail-soft)」「cron backfill will reconcile」誤導字樣，加 cross-ref F1 + B1 producer-side defense）。30min IMPL + ~10 LOC + 1 unit test + 4 AC。Risk = TRIVIAL（純 log message + level，0 業務語意改）。grep target `fill-writer-entry-context-missing` 不變（contract）。

**F4 拍板 Option (a) refined = E1 RCA Option A**：
- 保留 fully_filled gate 0.999 語意全 path 不變
- 用 Bybit OrderUpdate(status="Filled") 為 authoritative trigger（CLAUDE.md §二 原則 9「交易所即真實」衍生）
- 殘量補一次 apply_confirmed_fill + emit_fill_completion_lineage（stub_report_id 加 `:bybit_reconcile` suffix 供 reviewer audit）
- idempotency = `state.pending_orders.remove(&order.order_link_id)` post-reconcile 自然 guard（**0 PendingOrder struct field 改動**，比原 §5.2 草案 `bybit_reconcile_done: bool` flag 更乾淨）
- 1h IMPL + ~50-60 LOC + 3 unit test + 1 manual demo Bybit verify + 6 AC

**reject 其他 option 理由**：
- (a) 對齊 epsilon 0.999→0.99 全 path 容忍 1% 殘量 = 模糊 fully_filled 邊界
- (b) 不問 gate 強制 emit = 跳過 W-C Caveat 2 partial-fill protection
- (c) 純 internal tolerance < 1 tick = 缺乏「Bybit Filled」authoritative 信號

**跨 wave 衝突**: F3+F4 vs Sprint N+1 W1-W7 全 9 wave + 隔壁 producer-side fix + V091 + MAG-085 全 **0 file 重疊**。

**Schedule**: **Sprint N+1 W5 backlog 第 12+13 ticket**，D+2~D+3 cycle。**不在 D+0 首日 deploy 窗口**（D+0 已派 9 wave 並行 + ops 擠 + F4 medium risk 需 manual demo verify 污染 baseline）。

**Deploy 順序建議**: **F3 + F4 同次** `restart_all --rebuild --keep-auth`（非拆 2 次）— 降 ops 成本 + W-E wave closure semantic + 0 sequencing constraint。E1-F3 + E1-F4 兩 sub-agent 完全並行 IMPL（2 file 0 重疊）2.5h workload 收口。

**Risk**: F3 = TRIVIAL（0 業務語意，純 log）；F4 = MEDIUM（reconciliation 觸 fill attribution rate per MAG-082 Caveat 2 SoT，可能微推 healthcheck [40] avg_net ≤±0.1 bps，已 mitigate AC-F4-5 manual demo verify + 24h passive watch）。

**16 原則 + DOC-08 §12 + 硬邊界 5 項 compliance**: **A 級** — 強化原則 5/6/8/12，0 硬邊界觸碰。

**MAG-085 sign-off**: F3+F4 同次 deploy + 24h verify PASS 後合併 W-E wave closure（W-E-T4/T5/T6 對齊 `2026-05-11--p1_rca1_f1_f2_emergency_fix_plan.md` §8.2）。

**架構教訓**：
1. **PA 拍板 F4 Option A** 的關鍵 = 「交易所即真實」原則（Bybit Filled = authoritative），不是純內部 epsilon 算法問題。CLAUDE.md §二 原則 9 災難保護衍生「相信 Bybit 終態 vs 相信 engine 內部 cum」是 trade-off 拍板點。
2. **idempotency 用「natural state guard」優於「explicit flag」**：原草案 `bybit_reconcile_done: bool` 屬 over-engineering；`pending_orders.remove` post-reconcile 等於同類效果，0 struct field 改動。E2 review 必確認 remove 在 emit 完成 **後** 才呼叫。
3. **stub_report_id suffix `:bybit_reconcile`** 是輕量 audit cross-ref pattern — 無 schema 改動 + reviewer 可區分。healthcheck `[55]` query 必順帶補認此 suffix（E1-F4 IMPL 包含 ~10 LOC `passive_wait_healthcheck.py` 改動）。

**Confidence**: HIGH for F3 spec + Risk 評估；HIGH for F4 option 拍板理由；HIGH for 跨 wave 衝突 verify；MEDIUM for Schedule W5 D+2~D+3（仍可由 operator override 排 D+0 或 D+1）；MEDIUM for F4 reconcile dust 對 [40] avg_net 統計實際影響估計（需 manual demo verify 真實樣本）

**Report**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--f3_f4_writer_defense_n1_dispatch_plan.md`


---

## 2026-05-11 P1-LG-DESIGN — PA tech plan for P0-LG-1 + P0-LG-2 + P0-LG-3

**Trigger**: PM Wave 1 D-prep / Sprint N+1。Post W-D MAG-084 closure，critical path 推進 P0-LG 三項。

**Key code state findings** (2026-05-11):

1. **H0 Gate already in production hot path**: `rust/openclaw_engine/src/tick_pipeline/on_tick/step_0_5_h0_gate.rs:41` 已調用 `pipeline.h0_gate.check()`，hard-block 路徑 `ControlFlow::Break` → stops only → 早退。
2. **Demo + LiveDemo TOML 已 `h0_shadow_mode=false`** (hard-block); paper `=true` (shadow only). Production hard-block 已生效多月。
3. **ctor `shadow_mode: true` (pipeline_ctor.rs:75-76)** RRC-1-A3 註釋「observe-only until proven stable」— 啟動瞬窗 1-3s shadow → TOML 覆蓋 hard-block；風險點但不破。
4. **Fee runtime complete**: AccountManager (903 LOC) + IntentProcessor::fee_rate_for_intent + spawn_fee_rate_tasks hourly refresh + last_fee_refresh_ms AtomicU64 + DEFAULT_TAKER_FEE 0.00055 / DEFAULT_MAKER_FEE 0.0002 fallback.
5. **Healthcheck `[45]` pricing_binding 已 DONE Sprint C R6-T7** (2026-05-05) — PG-side proxy via `MAX(ts) WHERE fee_rate IS NOT NULL` + source 推斷 (seed_default / bybit_v5 / cold_default) + 3 fail-closed rules.
6. **LG-3 supervised live SM 是 5 個元件 5 個 SoT 散落**: LiveAuthorization HMAC + EarnedTrustEngine T0-T3 (817 LOC) + LiveAuthWatcher 5s respawn (970 LOC) + drawdown_revoke (441 LOC) + Decision Lease (Sprint 3 Track H+I)；**未集中表達為 7-state SM**。

**LG-1 真正剩餘** (P0-LG-1):
- E2E mock blocked-intent Rust integration test (`tests/h0_blocking.rs`)
- Healthcheck `[59]` h0_block_acceptance (新 `checks_h0_block_acceptance.py`)
- Flip/rollback runbook + ctor 預設修正
- Operator verification SQL endpoint
- 24h passive observation 後 sign-off

**LG-2 真正剩餘** (P0-LG-2):
- Contract test pin Bybit fee response parse + TIF dispatch + fallback (新 `tests/lg3_contract.rs`)
- Startup assertion `wait_for_first_refresh_or_timeout(30s)` + 3 條件 (refresh_ms>0 / fee_rate_count>=25 / live!=seed_default)
- FeeSource enum 公開 API + healthcheck `[45]` dual-source 對賬
- RiskConfig `[pricing]` section + hot-reload ArcSwap RMW (4 TOML 加 section)
- ⚠️ Demo/LiveDemo 可接受 `seed_default`，Mainnet 不可（RFC §Pricing Sources）

**LG-3 真正剩餘** (P0-LG-3):
- SupervisedLiveStateMachine 集中表達 (Rust `supervised_live_sm/` + Python `supervised_live_state.py`)
- Approval RPC `/api/v1/live/supervised/approve` (LG-4 RFC 13 欄)
- Session-scoped risk_limits override (lease binding; `compute_effective_limits = min(P1, session_override, strategy_config)`)
- Kill switch dual-path (API + IPC) 集中
- Audit mirror table V09x__supervised_live_audit.sql (11 欄 append-only)
- E2E acceptance tests (LG-4 RFC 10 條件)
- GUI surface in live tab
- ⚠️ Spec phase 必先 (PA 1-1.5d) → 5 E1 並行 IMPL

**E1 並行能力**:
- LG-1: 4 並行 (T1 Rust test / T2 Python healthcheck / T3 docs+ctor / T4 Python route)
- LG-2: 3 序列推薦 (T4 RiskConfig 先 → T1+T3 並行 → T2 startup assertion 後)
- LG-3: 5 並行 (T1+T2+T4+T7 + (T3+T5 依 T1+T2) + T6 ship 後)

**Max Risk 排序**:
1. LG-3 SM bypass paths split-brain (極高) — external observer reconcile loop 是 critical defense
2. LG-3 Session override 變相突破 P1 (極高) — `min`-only compute_effective_limits + E2+QC+MIT 三角
3. LG-2 Startup assertion timing race (高) — fee_rate task 首次 refresh 之前 spawn live
4. LG-1 ctor `shadow_mode:true` 預設啟動瞬窗 (中)
5. LG-3 GUI kill button 誤操作 (高) — 5s countdown + A3

**Sprint N+1 capacity 估**:
- W3-W4: LG-1 (4 並行) + LG-2 (3 序列) + LG-3 spec phase = 7 E1-week (8 budget OK)
- W5-W6: LG-3 IMPL phase 4 並行 = 4 E1-week
- W7-W8: LG-3 序列 T3+T5+T6 + sign-off = 3 E1-week

**RFC v1 (2026-05-01) → 本 tech plan v1 (2026-05-11) 變化**:
- 本 tech plan 不重寫 RFC，**識別 RFC 與 production 之間的 gap**
- RFC 把 LG-2 描述為「verification 而非新建」→ 本 plan 確認 demo + live_demo TOML 已 hard-block，純驗證
- RFC LG-3 healthcheck T2 已 DONE Sprint C → 本 plan focus 在 contract test + startup assertion + FeeSource enum
- RFC LG-4 SM 是 spec only → 本 plan 拆 spec phase + 5 E1 IMPL phase

**Report**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_2_3_4_design_plan.md`

**Confidence**: HIGH for code state findings (1-6 全 grep verify);  HIGH for E1 任務拆分 (對齊 profile.md 動態 isolation 派工準則); HIGH for Risk 排序 (LG-3 SM split-brain 在 5 個 SoT 散落事實上明顯); MEDIUM for E1 capacity 估 (依 §0 Sprint Milestone Banner 推算，sprint mid 可能調整); MEDIUM for spec phase 工時 1-1.5d 估 (LG-3 SM 複雜度高，可能需 2d)

---

## 2026-05-11 LG-3 SupervisedLive SM Spec v1 — Wave 2.1 spec phase 完成

**Trigger**: PM Wave 2.1 self-task per D-prep §6.1。post W-D MAG-084 closure + Wave 1.6 P1-FILL-LINEAGE-DROP land (e17ead2b)，啟動 LG-3 IMPL 前的 spec phase。

**Deliverable**: 16 章節 spec doc `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v1.md` (~1700 行 spec doc)

**Spec 設計關鍵點**:

1. **7-state SM**：DRAFT → REGISTERED → ACTIVE_PRE_AUTH → ACTIVE_AUTHED → ACTIVE_TRADING → DRAWDOWN_PAUSE → CLOSED；16 條合法 transition + 6 個 illegal_transition_attempted test case；非法 transition fail-closed 留 src state（不 crash engine 破 stops）

2. **5 SoT reconciler 30s loop**：authority order = audit_table (SoT) > Rust SM > Python SM > authorization.json > lease_transitions。Disagree 連 2 cycle 才升 force_close（防 transient 1-cycle false-positive）。reconciler 在 Rust async task，非 hot path

3. **V094 audit 17 欄**：RFC 11 欄 + 6 補欄（session_id JOIN key / src_state+dst_state debug / alpha_source_id R-4 forward-compat / cohort_ref W-AUDIT-9 cross-ref / payload JSONB extra）；CHECK constraint 17 action enum；TimescaleDB hypertable + 4 hot-path indexes

4. **session_override 嚴格 min-only**：`effective = min(P1, session_override, strategy_config)`；12 TC 三角必審覆蓋 attack vector TC-3（override > P1）；E2 grep `\bmax\(.*p1` returns 0 強制；SessionOverrideLimits parsing 階段拒 NaN/負/零

5. **Approval RPC 6 Gate**：operator role + envelope HMAC + live_reserved mode + scope/limits validation + 5-gate live boundary + W-AUDIT-9 cohort awareness（informational）+ atomic transition + authorization.json write

6. **Kill switch dual-path**：API `/api/v1/live/supervised/kill` 走 5s countdown modal + IPC `trigger_kill_switch` Rust-local cancel；兩條都 idempotent + 同 audit event；GUI A3 review 必活（per W-AUDIT-7c precedent）

7. **R-4 forward-compat**：alpha_source_id NULLable + metadata.cohort_ref，N+7+ W-AUDIT-8g land 不破 V094

**LG3-T1..T7 IMPL-ready task breakdown**:
- T1 Rust SM core ~1700 LOC（4 file 拆 ≤800 警告線）
- T2 Python SM mirror ~500 LOC
- T3 Approval RPC route ~400 LOC（extend live_session_routes.py 734→984）
- T4 Audit V094 + writer ~780 LOC（含 SQL + Rust writer + 2 healthcheck）
- T5 Kill + session_override + intent_processor binding ~370 LOC
- T6 E2E test ~1000 LOC（LG-4 RFC 10 條件全 cover）
- T7 GUI ~550 LOC（5s countdown modal per W-AUDIT-7 precedent）
- Total ~5300 LOC（Rust ~3300 / Python ~1300 / SQL ~180 / Frontend ~550）

**Parallel capacity**: Phase 1 = 4 並行（T1/T2/T4/T7 獨立）→ Phase 2 = 2 並行（T3+T5 依 T1+T2）→ Phase 3 = 1（T6 依 T1-T5）

**Healthcheck 新增**: [59] supervised_live_sm_invariant / [60] approval_rpc_health / [61] audit_mirror_freshness（與既有 [33]/[40]/[45]/[55]/[56]/[58] 互補不重疊）

**Max Risk 排序（spec v1 更新）**:
1. (極高) SM 5-SoT split-brain → reconciler 30s + 連 2 cycle 防 transient + audit SoT 權威
2. (極高) session_override 變相突破 P1 → min-only formula + 12 TC + grep guard + E2+QC+MIT 三角
3. (高) GUI kill button 誤操作 → 5s countdown + A3 review + node --check sop
4. (中) outbox mpsc buffer 滿 SM 不 advance（fail-closed OK，control plane）
5. (中) Approval RPC 6 gate 序列繞過 attack
6. (中) Rust+Python SM IPC broadcast race（audit SoT 自動 reconcile）
7. (低) R-4 backward-compat 破壞（NULLable column 預留）

**Cross-wave 衝突**: 0 file 重疊 with LG-1 / LG-2 / W-AUDIT-8a / W-AUDIT-9 / W2 IMPL / F3+F4 / Wave 1.6（既 land）

**16 原則 + DOC-08 §12 + 硬邊界 compliance**: A 級 0 硬邊界觸碰；強化原則 #4/#5/#6/#7/#8

**spec phase status**: PA spec v1 ship；下步 PM 派 QC+BB+MIT parallel review (Wave 2.1.5, 1d)；PA spec v2 final 0.5d；PM 派 Wave 2.4 IMPL 7-8d

**架構教訓 7**：**reconciler 連 2 cycle 才升 force_close** 是 split-brain SM 的關鍵設計範式。1 cycle disagree 可能來自 transient IPC delay（Rust→Python broadcast 微秒級 race），1 cycle 就 force_close 會 false-positive 殺 valid session。但 2 cycle 60s window 仍 disagree = 真實 desync，必須 fail-closed。設計準則：multi-SoT reconciler 必加 N-cycle 確認窗，N≥2，cycle interval ≥ 最慢 broadcast 路徑的 2 倍。

**架構教訓 8**：**session_override 反 attack vector TC-3**（`override > P1` 必反成 effective=P1）是 spec phase 唯一要明示反例的 TC。普通 TC 證正常路徑 work；但 attack vector TC 必證 fail-closed 真實生效。E2 grep 為靜態防線，TC-3 為動態防線，缺一不可。Spec v2 收 QC review 反饋若有「TC-3 還不夠」，可加 TC-13 fuzz test（隨機 1000 個 override > P1 sample，全部 reject）。

**架構教訓 9**：**audit table 作 SoT 真值權威**（5 SoT 中 #5 為主，#1-#4 derived）是 multi-process SM 最乾淨的設計。理由：(a) PG append-only history 是不可變 truth；(b) reconciler 不打 PG 同步（30s 拉一次，非 hot path）；(c) 任何 SM crash 重啟可由 audit table 重建 state；(d) 跨 process audit 一致 (Rust + Python 寫同表)。對比方案「Rust SM 為 SoT」會破 audit 重啟可恢復性。


---

## 2026-05-11 LG-3 Spec v2 Final — Wave 2.2 incorporate 26 caveat

**Trigger**: PM Wave 2.2 self-task per D-prep §6.1。post Wave 2.1.5 三方 review 全 APPROVE（QC + MIT + BB；0 REQUEST CHANGES），25+ caveat 必 incorporate 進 spec v2 final。

**Deliverable**: spec v2 final doc `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v2_final.md` (1767 行, v1 1221 → +546 行 / < 2000 hard cap)

**26 Caveat 全 incorporated（無 deferred）**:

| Source | Total | All Incorporated |
|---|---|---|
| QC | 6 必補 + 4 SHOULD = 10 條 | ✅ 10/10 |
| MIT | 6 MUST + 3 SHOULD = 9 條 | ✅ 9/9 |
| BB | 5 spec 補章節 + 1 mainnet checklist + 1 meta pre-flight = 7 條 | ✅ 7/7 |
| **Total** | **26** | **✅ 26/26** |

**主要設計決策（v2 incorporate）**:

1. **session_override immutable for session lifetime**（QC CAVEAT 7 Option 1 採納，§3.5）
   - 杜絕 mid-session attack surface（operator 在 reconcile cycle 邊界改 override 可能誤觸 reconcile_force_close）
   - 簡化 audit table 不需新增 `session_override_updated` enum
   - 簡化 reconciler inverse map（§2.2A 維持 17 action 不擴）
   - 對齊 EarnedTrust authorization TTL 設計（一次性鎖定）
   - GUI 修改 session_override = kill + new approve

2. **§2.2A inverse map (17 action × 7 state) 完整表**（MIT MUST-6，§2.2A）
   - audit `action` → projected_state mapping 7 type cover 17 enum
   - Rust `audit_action_to_projected_state(action: &str) -> Option<SmState>` 完整 match
   - Python mirror `supervised_live_state.py` 必 1:1 對應同一 dict（IMPL phase E2 check 等價性）
   - 防 split-brain epidemic（Rust + Python 兩端解讀不一致 = SM mirror disagree）

3. **/kill cancel-all THEN close-position THEN revoke 順序**（BB caveat 4 + 2，§6.3 + §6.6）
   - 禁止：先 revoke → engine cancel_token → cancel-all 沒 fire → DCP fallback 救場
   - DCP 是 backup 而非 primary；operator 視 DCP fire 為「kill 沒做完整」應觸發 RCA
   - 序列化 batch_wait 0.3s per symbol（Order group 20 r/s × 0.3s safety margin）
   - 25 symbol × 0.3s = 7.5s + cancel/close ~3s = 完整 kill ≤ 10s
   - 6.7 r/s utilization 33% Order group cap，留 67% headroom

4. **Approval Gate 7 Bybit KYC tier cross-ref**（BB caveat 5，§3.3 Gate 7 + §3.7 + §7.4A）
   - REQUIRED_KYC_FOR_TRUST_TIER: T0 Tier 0+ / T1 Tier 1+ / T2-T3 Tier 2+
   - `query_bybit_kyc_tier_cached()` 5min cache（GET /v5/user/query-api permissions）
   - 失效時間：cache miss / TTL expire / 手動清 cache
   - Cache miss + Bybit unreachable → fail-closed reject（reason: `bybit_kyc_check_unreachable`）
   - 避免 retCode=10005 (PermissionDenied) lease + audit 浪費

5. **TC 從 12 升到 19**（QC CAVEAT 1/2/3/4/5/6 + TC-19 split-brain）
   - TC-13: Zero override at parse layer
   - TC-14: Lease re-acquire 不重設 override
   - TC-15: Sequential kill+approve scope-widen audit forensic
   - TC-16: Outbox PG retry exhaustion + in-memory recovery
   - TC-17: u32 saturating at boundary
   - TC-18: P1 per-intent vs aggregate semantic
   - TC-19: Split-brain reconcile clears override

6. **V094 schema 加 2 forward-compat column**（MIT SHOULD-2/3，§4.1）
   - `strategy_alpha_score FLOAT8`（R-4 alpha routing 評分依據）
   - `regime_tag TEXT`（R-2 Strategist reframe regime-aware 配套）
   - Backward-compat: N+1 ship 時全 NULL；W-AUDIT-8g land 時 UPDATE backfill 不破 V094

7. **§4.1 Guard A part 2 + ADD CONSTRAINT block**（MIT MUST-1/2，§4.1）
   - Part 2: supervised_live_audit own 21-column allowlist check（mirror V054 §155-188）
   - 4 CHECK constraint via ADD CONSTRAINT IF NOT EXISTS block：action / result / engine_mode / ts_ms > 0
   - idempotent: re-runs no RAISE

8. **PG retry exhaustion in-memory recovery**（QC CAVEAT 4，§4.4A）
   - PG retry 3 fail → engine graceful shutdown（cancel_token fire）
   - pending vec 內 audit row 永久遺失（accepted trade-off per `_REGISTER_IDEM_CACHE` 同精神）
   - engine 重啟後 reconciler 第一 cycle 觀察 disagree → 連 2 cycle 確認 → reconcile_force_close 自動清空
   - operator GUI 顯示 reason=`engine_crashed_pending_audit_lost` 必手動 acknowledge before 重 approve
   - 禁 pending vec 寫盤再 replay（破 audit append-only + 引入 disk write hot path）

9. **Linux PG dry-run dispatch SOP**（MIT MUST-3，§13.4.1）
   - E1 IMPL on Mac → Linux dry-run round 1（`psql -f V094` + INSERT test data 驗 CHECK） → round 2（idempotency verify no RAISE） → sqlx checksum verify（含 `bin/repair_migration_checksum` 處理） → E2 / E4 / A3 → sign-off
   - 禁 Mac mock pytest PASS = Linux PG runtime semantic PASS（V055 5-round loop 教訓）

10. **GUI Approval response panel submitted vs effective**（QC CAVEAT 10，§6.5A）
    - 表格 4 row: max_position / max_daily_loss / max_orders / max_leverage
    - Submitted / Effective / Reason 三 column
    - 對應 audit payload `submitted_override` + `effective_after_min` + `submitted_vs_effective_reason` JSONB subfield

11. **Non-training surface invariant**（MIT MUST-5，§4.4B + §4.1）
    - schema-level safety statement + E3 grep rule
    - allowlist 路徑：healthcheck + reconciler + writer
    - blocklist 路徑：program_code/**/{ml,training,learning,scorer,linucb,mlde,dream,optuna,thompson}/**
    - 對齊既有 CLAUDE.md §九 `replay.simulated_fills synthetic_replay` 防護 SOP
    - E3 IMPL after Wave 2.4 Phase 3：補 `helper_scripts/audit/e3_grep_non_training_surface.sh`

12. **Mainnet 解鎖前 BB mandatory 8 項 checklist**（BB caveat 6，§15.4）
    - M5-1 governance entry（KYC + 地理 + API permission + IP whitelist + ToS）
    - M5-2 IP whitelist preflight 工具 IMPL
    - mainnet API key（withdraw=false + IP whitelist 24h cool-down）
    - P0-OPS-4 首日 runbook
    - mainnet authorization.json env_allowed=['mainnet'] 分隔（既有 code handle）
    - 首日 limit T0 30min cap + 1 strategy + 1 symbol cohort
    - mainnet 切 LiveDemo restart 規程
    - broker partnership eligibility 例行驗（每月）

**v2 新章節 / sub-section 摘要**:
- §2.2A audit→state inverse map（17 action × 7 state）
- §3.5 immutability declaration + §3.5.1 Sequential kill+approve audit forensic
- §3.6 Renew clarification
- §3.7 Gate 7 KYC cross-ref（簡述）
- §4.1 Guard A part 2 + ADD CONSTRAINT block + SHOULD column
- §4.4A PG retry exhaustion in-memory recovery
- §4.4B Non-training surface invariant
- §5.1 fn body amendments（u32 saturating + P1 cap semantic comments）
- §5.3 TC-13~TC-19（7 new TC）
- §6.5A Approval response panel
- §6.6 Kill rate-limit batch_wait pattern
- §7.4A EarnedTrust × Bybit KYC tier cross-ref table
- §7.6 WS reconnect 不觸 SM
- §10 [59] baseline KS test + [60] 30d budget gate + KYC reject rate sub-check
- §11.9 Kill rate-limit competition risk
- §13.4.1 Linux PG dry-run dispatch SOP
- §13.4.2 Wave 2.4 IMPL pre-flight Bybit changelog check
- §15.4 Mainnet 解鎖前 BB mandatory 8 項 checklist
- §16 **Caveat Resolution Table**（26 caveat full audit trail）

**LOC 微調**:
- LG3-T4: 780 → 980 LOC（+200 加 Guard A part 2 + CHECK constraint + healthcheck sub-check + E3 grep script）
- LG3-T5: 370 → 420 LOC（+50 加 batch_wait pattern + u32 saturating）
- LG3-T6: 1000 → 1100 LOC（+100 加 5 new AC test）
- LG3-T7: 550 → 620 LOC（+70 加 Approval response panel）
- Total: ~5300 → ~5720 LOC

**Max Risk 排序（v2 更新後）**:
1. (極高) SM 5-SoT split-brain → 加 §2.2A inverse map IMPL 一致性
2. (極高) session_override 變相突破 P1 → 19 TC（從 12 升）+ immutable lifetime + grep guard
3. (高) GUI kill button 誤操作 → 5s countdown + A3 + 序列化 batch_wait + cancel-then-revoke + Approval response panel
4. (中) outbox mpsc buffer 滿 SM 不 advance → §4.4A PG retry exhaustion recovery
5. (中) Approval RPC 8-gate（v2 升）序列繞過 attack → Gate 7 KYC cross-ref + immutability + audit forensic
6. (中) Rust+Python SM IPC broadcast race → §2.2A inverse map 1:1 等價
7. (低) R-4 backward-compat 破壞 → 3 NULLable column 預留（v2 +2 SHOULD column）
8. (中) Kill 序列化 vs Bybit rate-limit 競爭（v2 new 11.9）→ 序列化 + 0.3s safety margin + DCP backup

**Cross-Wave 衝突**: unchanged from v1（0 file 重疊 with LG-1 / LG-2 / W-AUDIT-8a / W-AUDIT-9 / W2 IMPL / F3+F4 / Wave 1.6）

**16 原則 + DOC-08 §12 + 硬邊界 5 項 compliance**: **A 級** — 0 硬邊界觸碰；強化原則 #4/#5/#6/#7/#8（v2 加原則 #7 Non-training surface invariant 顯式 schema-level safety）。

**spec v2 final status**: ✅ ship；下步 PM 派 Wave 2.4 IMPL E1×7（per §8 task breakdown, 7-8d）；後續 Wave 2.5 sign-off。

**架構教訓 10（v2 新增）**：**26 caveat incorporate without redesign 的關鍵設計範式**：
- v1 spec 結構良好（16 章節 + 12 TC + 7-state SM）→ v2 不大改結構
- 各章節 inline amendment 加 reviewer ref → 維持 spec 連貫性
- 新章節按 reviewer 建議位置加 → 避免散亂
- §16 Caveat Resolution Table 給 reviewer 快查 + 0 deferred audit trail
- 對 reviewer 而言 = 完整看到他的 caveat 在哪裡被 incorporate；對 IMPL E1 而言 = 19 TC + 23 AC 全 explicit
- 重點：caveat 接納度 = 100%；但採納 != redesign，是「補強而非結構性 redesign」（per 3 reviewer 共識）

**架構教訓 11（v2 新增）**：**immutable session_override 是 5-SoT SM 必然選擇**：
- mutable override 必加新 audit action `session_override_updated`，破 §2.2A 17 action × 7 state 完整性
- mutable 引入 reconcile cycle 邊界 attack vector（QC §C 場景 X 真實存在）
- 對應 EarnedTrust authorization TTL 一次性鎖定 = 同設計範式
- 「不要在 active session 中動 config」是 multi-process SM 的健康原則
- 代價：operator 需 kill + new approve 才能改 override → 但 5s countdown + Approval form 完整 GUI 流程已 cover

**架構教訓 12（v2 新增）**：**Bybit KYC cross-ref Gate 7 是 spec 與真實交易所之間的必補橋樑**：
- spec 內部 EarnedTrust tier 是治理層概念；Bybit KYC tier 是交易所層真實 permission
- 缺 Gate 7：approval pass → live order create → retCode=10005 → lease + audit 浪費 + operator 困惑
- 加 Gate 7（5min cache + fail-closed unreachable）→ approval 階段就 reject，零 lease 浪費
- 對 supervised live operator → 「我的 KYC 配置不對」清楚知道（reason_codes 明示）
- 對其他 governance gate（W-AUDIT-9 cohort / EarnedTrust tier / lease）→ 同範式：spec 內部 gate vs 交易所層 permission 必明文 cross-ref，否則 production 撞牆

**Confidence**:
- HIGH for caveat 全 incorporate（26/26 line-by-line ref to §16 table）
- HIGH for 0 deferred / 0 不接納
- HIGH for 0 redesign（三方共識「補強而非結構性 redesign」）
- HIGH for §2.2A inverse map 完整性（17 action × 7 state 全 cover）
- HIGH for session_override immutable 設計選 Option 1 推薦理由（4 個獨立理由）
- HIGH for /kill cancel-then-revoke 順序明文 + DCP backup 角色定位
- HIGH for V094 Guard A part 2 + ADD CONSTRAINT idempotent
- MEDIUM for spec v2 LOC 控制（1767 行 / 2000 hard cap，~88% 空間）
- MEDIUM for Wave 2.4 IMPL 工期估（7-8d 仍適用，LOC 微升 ~5300→5720 不破 sprint budget）
- LOW for 26 caveat 全文 1767 行單檔閱讀負擔（reviewer 可走 §16 table 快查）

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v2_final.md`
**Mirror path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/Operator/2026-05-11--lg_3_spec_v2_final.md`

---

## 2026-05-15 Close-Maker-First Refactor — PA 技術驗證 + spec outline

**Trigger**: 主會話派工 — 3 輪第三方對抗審核 + DB / 代碼核驗收斂後，要 PA 對 close-maker-first refactor 做完整技術驗證 + 起草 spec outline。

**Deliverable**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--close_maker_first_pa_verdict.md` (~1000 行內，已含 13 章節 spec outline + state machine + whitelist + LOC 估算)

**核心 finding**:

1. **close 路徑寫 `None` 是治理決策，不是技術限制**：
   - `commands.rs:792-797` 註釋「Close path stays Market (EDGE-P2-3 Phase 1a entry-only scope)」白紙黑字標明是 Phase 1a scope-limiting
   - `OrderDispatchRequest` 結構已含 `order_type/limit_price/time_in_force/maker_timeout_ms` 4 個字段
   - 下游 `dispatch.rs:508-538` 已 typed `OrderType::Limit if eq_ignore_ascii_case("limit")`、tif/limit_price forward 完整、reduce_only=true 已加
   - `PendingOrder` 結構 mirror 4 字段（dispatch.rs:475-497）
   - `pending_sweep::classify_pending_sweep` 不分 is_close 只看 `time_in_force == PostOnly` + `maker_timeout_ms`（pending_sweep.rs:53-76）

2. **1B-4.2 完全無依賴**：`resting_orders.rs` MODULE_NOTE 行 4-23 明示是 paper-only infrastructure。Exchange close maker 走 dispatch.rs → Bybit REST → WS event，與 paper resting queue 正交。NOT BLOCKED-BY-1B-4.2。

3. **Whitelist 8 + keep market 7+**：
   - ✅ maker: grid_close_{short,long} / bb_mean_revert / ma_reverse_cross / pctb_revert / bw_squeeze / phys_lock_gate4_giveback / phys_lock_gate4_stale_roc_neg
   - ❌ keep market: risk_close:HARD STOP / TRAILING STOP / TIME STOP / fast_track* / halt_session* / cost_edge_ratio / DRAWDOWN + bb_breakout 內部 `trailing_stop`（與 risk envelope TRAILING STOP 同 keyword 但屬策略決策；建議仍 keep market — chandelier fire 時價已破線）

4. **compute_close_limit_price() 設計推薦 Option C**：反向 delegate `compute_post_only_price(!is_close_long, ...)` 重用 production-tested code（G7-09c Phase 1 已驗 rejection 100% → 0%）；per-reason buffer_ticks 容納變體（grid=1, phys_lock_g4=2, bw_squeeze=1）

5. **State machine 4 race 設計**：
   - pending close + 新 trigger → **fast-escalate**（cancel pending maker → market re-dispatch）
   - maker timeout → MakerTimeoutCancel 既有 + 新 PendingOrderEvent::CloseMakerTimeoutFallback → market re-dispatch
   - reject (PostOnlyCross) → 直接 market（不重 quote）
   - reject (TooManyPending) → 直接 market + 5min global maker pause

6. **reject_cooldown 跨 entry/close 污染**（**真實 bug**）：grid_trading/signal.rs:152-158 per-symbol cooldown 不分 entry/close side，entry reject 會凍住同 symbol close maker。spec 必拆 reject_cooldown_entry / reject_cooldown_close。

**Risk 評級**:
- HIGH ×2: dispatch 點白名單分類器、bb_breakout trailing_stop 歧義
- MEDIUM ×2: reject_cooldown cross-side 污染、rate-limit 競爭 (NEEDS-PROBE)
- MEDIUM ×1: state machine pending close fast-escalate
- LOW ×2: test assert 影響、1B-4.2 依賴（無）

**代碼影響 ~985 LOC**: Rust ~575 / TOML ~20 / Tests ~400 / Healthcheck ~120。3-5 E1 並行 7-9 E1-day。

**Verdict**: **READY-FOR-SPEC**（with 1 NEEDS-PROBE on rate-limit cancel; 0 BLOCKED-BY-1B-4.2）

**架構教訓 13**: **「entry-only scope」comment 是 governance signal，不是技術 ceiling**。Phase 1a 故意只開 entry 是 phased rollout 風險控制（先驗 maker plumbing 在開倉路徑 OK 再擴 close），不是 close path 缺技術能力。判讀類似 `// X-only scope` / `// stays Market` 一律先 grep 下游 plumbing 是否真斷，**事實上 dispatch.rs 與 pending_sweep 早就完整支援 maker close**，僅缺接電線。教訓：PA 必查上下游 IPC chain 而非只看頂層 hard-code。

**架構教訓 14**: **resting_orders.rs vs exchange path 是正交設計**，不是 layered。Paper-only 文件命名（`paper_state/resting_orders.rs`）+ MODULE_NOTE 明示「Paper-only infrastructure for PostOnly limit orders that must wait for a future tick」清楚 — exchange close maker 不經此模組，完全走 Bybit REST API + WS。判讀「Phase 1B-4.2 是否阻塞」一律先讀模組 MODULE_NOTE 邊界，不要先預設「同 Phase 編號 → 必同 dependency」。

**架構教訓 15**: **reason string 同 keyword 跨 source 歧義是真實設計陷阱**。bb_breakout 內 chandelier `trailing_stop`（mod.rs:910）vs risk envelope `risk_close:TRAILING STOP: ...`（risk_checks）共用同 word；前者策略決策、後者風控強平。白名單必須在 trigger_tag 完整 prefix 上 match，不能 substring 搜尋 keyword。E2 必加 grep guard：`trigger_tag.contains("trailing_stop") && !trigger_tag.starts_with("risk_close:")` 判定為策略 trailing_stop。

**Confidence**: HIGH for §1 已驗代碼事實 + §3 whitelist + §4 compute_close_limit_price 設計 + §6 1B-4.2 無依賴 + §7 spec outline；MEDIUM for rate-limit NEEDS-PROBE + state machine fast-escalate + bb_breakout trailing_stop 裁決；LOW for 0 unverified hypothesis（皆有 grep / 直讀代碼支撐）

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--close_maker_first_pa_verdict.md`

## 2026-05-15 F-FA-2 portfolio_var exposure SoT verify (Track A3 Wave 1)

**Context**: PM dispatched PA Wave 1 (Track A3) read-only verify of FA's #16 CONDITIONAL — close-maker-first PostOnly maker pending 期間 portfolio risk gate qty source。

**Key finding**: 
- NO `portfolio_var` 模塊；SoT = `intent_processor/mod.rs:761-805` `compute_exposure_pct` + `compute_correlated_exposure_pct`，兩者都只迭代 `paper_state.positions()` (PaperPosition.qty=filled)
- `paper_state.resting_orders` 完全沒被 portfolio gate 讀（entry-side resting maker Phase 1B-4.2 已 land，但同樣繼承此 gap）
- `risk_config.correlation.max_pairwise_r` 是 dead config (validated in schema, 0 callers)
- `is_reducing → check_order_allowed line 137 直接 allow` — close intent 自身根本不觸 portfolio gate
- FA framing 「under-estimate」方向部分反了：close pending 對 NEW open 是 OVER-estimate（仍 over-cap entry）
- Phase 1B-4 paper-only scope 無 partial cancel race；exchange path future scope 才需

**Verdict**: §二 #16 維持 CONDITIONAL，但 carve out scope — 推薦選項 A（CONDITIONAL → ACCEPTED-WITH-CARVE-OUT + 新開 P1-PORTFOLIO-RESTING-EXPOSURE-1 與 close-maker-first IMPL 平行）。

**架構 lesson**: 
- entry-side resting maker landing 時就應同步修 portfolio gate；當時的 systemic gap 沒被識別，是 Phase 1B-4.2 review 漏接
- close-maker-first IMPL 不是 regression source，是「系統性 gap 暴露面擴大」case
- bilateral CONDITIONAL（fix scope ≠ 觸發 ticket scope）建議用 carve-out 而非延後 IMPL

**Report**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--f_fa_2_portfolio_var_exposure_sot_verify.md`
**Estimate**: 1.5h actual (read-only + grep + 7 source file 抽讀；symbol grep 30+ 次)


## 2026-05-15 — Track E3 maker fill rate empirical baseline (read-only PG)

**Task**: PM Wave 1 第 5 並行 1h read-only — 從 Linux PG `trading.*` 算 entry maker fill rate empirical baseline，給 close-maker-first BB-SF-2 修正建議事實基礎。

**Key findings (7d window, demo + live_demo, entry-only PostOnly Limit)**:
- **Conditional on fill, ~94% maker** (demo 276/292, live_demo 195/209) — spec §1.2 假設 conditional 成立
- **Per submitted PostOnly, 27% fill rate** (demo grid 936→253; live_demo grid 703→190); 70% PostOnly self-cancel timeout
- **Cancel timeout = 45s** (p50/p90/p99 高度集中) — engine timer 觸發
- **Fill latency p50 6.6-8.1s, p90 ~35s, p99 ~45s** — p99 接近 timeout cutoff
- **Reject categories**: self_cancel 78.6%, PostOnly cross 20%, others <2%（無 TooManyPending）

**Spec §1.2 4.5 bps 修正**:
- Best case (fill-conditional): **3.31 bps** — overstate 1.2 bps (27%)
- Per submitted (no fallback): **0.95 bps** — overstate 4.5x
- Close-path conservative (預測 close 比 entry 更難 fill): **0.66 bps per attempt** — overstate 6.8x

**Schema gotchas (重要)**:
- `orders.intent_id` 100% NULL — writer 漏接 (P2-level finding，但本任務不修)
- `orders.status` 100% Working — 終態須從 `order_state_changes.to_status` 拿
- `orders.details` jsonb null — 沒 client metadata
- `fills.entry_context_id IS NULL` = entry; NOT NULL = close — 唯一可靠 entry/close 區分

**Per-strategy variance**:
- grid_trading fill rate 27% (demo + live_demo 一致)
- ma_crossover 47% (高，但 PO cross 也高 40%+，定價太貼)
- bb_breakout sample 4 (insufficient)
- bb_reversion / funding_arb 7d 無 entry

**Close path prediction (對 EDGE-P2-3 close-maker-first)**:
- 100% close fills 當前 = taker (272 demo / 192 live_demo)
- demo close avg slippage 2.26 bps, live_demo 4.20 bps
- close 結構性比 entry 更難 maker fill: trend-side liquidity 偏弱 + 45s timeout 對 exit 致命
- **強烈推薦 conservative discount 25-40%** + fallback to taker + 短 timeout (5-15s) + 14d pilot

**對 Track A1 PA 的傳球建議**:
- spec §1.2 patch 用 0.5-2.0 bps net per attempt
- 加 14d 30%+ close-maker fill rate gate 才 declare positive
- 加 fallback to taker 機制要求

**Report**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--maker_fill_rate_empirical_baseline.md`
**Estimate**: 1h actual (PG schema 摸清 15min + 5 round query 30min + 報告 15min)
**SOP wins**:
- SSH bridge 跑 PG 都需 `PYTHONPATH=. python3` 從 `~/BybitOpenClaw/srv` cwd
- psql 需密碼，改用 `db_pool.get_pg_conn()` (ContextManager) 走 secrets 自動 inject
- Single-quote nesting hell: 寫 helper 到 /tmp 比 inline -c 安全


---

## 2026-05-15 Wave 1 Track A1 — AMD v0.2 + spec v1.1 4-agent consolidated patch

**Trigger**: 主會話 PM 派 Wave 1 第 1 並行 worktree — 17 must-fix（4 consensus + 13 unique per QC/FA/BB/MIT）+ 14 should-fix consolidated 收口 patch。

**Deliverable**:
- AMD v0.2: `srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md` commit `53245ed0`
- Spec v1.1: `srv/docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md` commit `a5a5d74a`（sibling commit `43627d1c` 已 baked 大部分內容；my Edit-tool incremental commit 補完）
- PA verdict report: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--amd_v0_2_spec_v1_1_consolidated_patch.md`

**Key patches**:

1. **§1 framing 消歧（Consensus-MF-1）**：「alpha-bearing pathway」改 **「alpha-impact-adjacent execution-quality pathway」** — 消除 fee bleed 對 alpha 量測污染，本身不是 alpha source；不適用 W-AUDIT-9 5-stage canary gate，mirror Phase 1a 三段灰度即可。

2. **§4.1 V094 hybrid schema explicit（Consensus-MF-4 + MIT-SF-1/2）**：
   - `close_maker_attempt: BOOLEAN NOT NULL DEFAULT FALSE` + `close_maker_fallback_reason: TEXT NULL CHECK enum` → **new column on trading.fills**（high-frequency group-by + partial index）
   - `close_initial_limit_price` + `close_final_fill_price` + `close_maker_eligible_reason` → **trading.fills.details JSONB key**（單筆 audit 讀取）
   - enum allowlist 8 個 reason + safety path 2 個（不算 NULL）
   - V094 file naming `V094__fills_close_maker_audit.sql`，next-free slot
   - Linux PG dry-run × 2 round + sqlx checksum repair SOP（per V055/V083/V084 incident precedent）

3. **§5.1 multiple testing protocol（QC-MF-1）**：FDR 0.10 with Benjamini-Hochberg procedure，覆蓋 48 test points（8 reason × 2 env × 3 phase）累積測試。

4. **§5.4 dynamic backoff（BB-MF-2）**：取代 v1.0「全域 5min pause」（3000x Bybit rate-limit recovery overshoot）：
   - per-symbol exp backoff 1s → 60s 上限
   - 連續 ≥10 distinct symbol 1min window 同 backoff → conditional global pause 5min
   - in-memory state，engine restart 重置（accepted trade-off）
   - audit 標記 `details.rate_limit_scope = "global"` JSONB 子欄位區別

5. **§6 phys_lock_gate4_giveback timeout 30→15s + buffer 2→1（QC-MF-2）**：
   - gate4 fire 時 peak ATR 已 surrender，下一秒價格繼續 unfavourable 條件機率高於隨機 walk
   - maker pending 期 expected fill price 嚴格 worse than 立即 market
   - footnote 紀錄「fire 條件帶 unfavourable drift bias」

6. **§7 #7 non-training surface invariant（MIT-MF-1）**：close_maker_* 5 欄位是 ops audit metadata，禁餵 ML training pipeline；E3 grep guard rule 永久化（mirror replay.simulated_fills 'synthetic_replay' precedent）。

7. **§7.2 W-C Caveat 2 explicit carve-out（FA-MF-2）**：close path 不寫 spine lineage；新 audit 欄位走 fills.details + new column，不寫 agent_spine.* 任何 table；F-FA-3 對應 grep guard test。

8. **§8 IMPL prereq 4→6 條件（FA-MF-1 + BB-MF-3）**：
   - 5: F-FA-1（V094 spec finalize）+ F-FA-2（portfolio_var SoT 驗）+ F-FA-3（lineage guard tests）pre-IMPL
   - 6: reject_cooldown entry/close 拆分升 P0 priority pre-Phase 2a Demo enable 必 land

9. **§10.1 V094 backward-compat append-only clarify（FA-MF-3）**：純 ADD COLUMN + ADD CONSTRAINT，沒 ALTER existing；既有 SELECT/INSERT/UPDATE 0 影響；如果 IMPL 改 separate column → 必重評 + 重派 4-agent review。

10. **Spec §6.2 BB-MF-4 enum reuse**：原 v1.0 提議新建 `Self::CloseTooManyPending` / `Self::ClosePostOnlyCross` variant 是錯的；正確設計 = 復用既有 enum + `OrderSide flag`，避免 Bybit error code → Rust enum 1:1 mapping invariant 破壞。

11. **Spec §11 AC-1..AC-13 連續 + AC-14/15/16/17 新增**：
   - AC-5 fee 改善 +3 bps → +1.5 bps（per QC-SF-1 推導：3.5×0.70 - 0.30×6 ≈ +0.65 bps net 保守）
   - AC-11 Phase 3 +5 bps → +1.5 bps（同上修正）
   - AC-14 Wilson CI gate（Consensus-MF-2）
   - AC-15 reject sample healthcheck（BB-MF-5）
   - AC-16 NULL ladder 0.1%/1.0%（Consensus-MF-3）
   - AC-17 close_timeout_pre_stopout_rate ≤ 5%（FA round-1 #5）
   - +AC-10b Phase 2b fresh holdout（QC-SF-5）
   - AC-1 +WARN @ 65% threshold（QC-SF-3）

**Should-fix 14 條全 integrated**：
- QC-SF-1/2/3/4/5（推導 footnote / counterfactual evidence packet / WARN 65% / spread guard / fresh holdout）
- FA-SF-1/2/3（9 不變量 mini-table / rollout AC SoT 引用 / Stage 0R 消歧）
- BB-SF-1/2/3（healthcheck [64] / fee 4.5→3.5 bps 修正 / small-tick alt symbol carve-out）
- MIT-SF-1/2/3/4（Linux PG dry-run + sqlx repair SOP / V094 slot + idempotency × 2 round / min_samples_gate=30 normative AC / retention 評估注）

**特殊處理**：
- BB-MF-1 字典手冊更新：**僅 spec 引用 / 標 TODO**，留 Wave 3 BB1 實際更新（per main session 指示）
- 4 個 should-fix 字典手冊改動（BB-SF）：留 Wave 3 BB1

**Sibling commit race**：
- 開始 Edit AMD 後 push commit `53245ed0`
- 開始 Edit spec 期間 sibling commit `43627d1c`（Linux 端或 Mac 隔壁 session 處理 12-agent audit fix plan + WP-01 GUI work）也對 spec 文件做 v1.1 patch（+348 lines）
- 我的 spec commit `a5a5d74a` 因 file state 已被 sibling 覆蓋大部分；最終 commit 只 10 行 incremental
- **End state correct**：spec 799 lines，55 v1.1 keyword hits，all 17 must-fix + 14 should-fix 收口完整（grep 驗：spec 69 markers / AMD 50 markers）
- **教訓**：multi-session race 下，工作未必撞失敗 — sibling 可能恰好做相同工作（因為 PM consolidated review 是公開 SoT）；`git commit --only` 防 index 污染但不防 sibling 同檔同步寫；應接手前查 `git log --oneline -5` + `git fetch` 才動

**架構教訓 16**：**多 agent dispatch 時，consolidated review 是 SSOT 但不是 mutex**。當 PM 同時派 PA + sibling 處理同 patch，可能兩 session 都做相同收口工作。對 deterministic patch（17 must-fix mapping 唯一）→ 結果相同；對非 deterministic（subjective wording）→ 必須 sibling 之間先 fetch 再寫，或 PM 必須 sibling-aware dispatch。本次 race 是「無害撞單」，但暴露 dispatch SOP gap。

**Confidence**:
- HIGH for AMD v0.2 17 must-fix + 14 should-fix mapping 完整（54 keyword hits 驗證）
- HIGH for spec v1.1 同上（55 keyword hits 驗證）
- HIGH for V094 next-free slot（grep V09x 確認 V094 free）
- HIGH for Linux PG dry-run mandatory（per CLAUDE.md §七 + V055/V083/V084 incident precedent）
- HIGH for non-training surface invariant 永久化機制（E3 grep guard rule + mirror §五 'synthetic_replay' precedent）
- HIGH for W-C Caveat 2 carve-out（明文 audit 走 fills.details + new column 不走 agent_spine.*）
- MEDIUM for sibling commit race 教訓（無害撞單但暴露 SOP gap）

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--amd_v0_2_spec_v1_1_consolidated_patch.md`

---

## 2026-05-15 — Wave 1.5 spec v1.2 + AMD v0.3 consolidated patch (post-Wave 1 increment)

**Trigger**：PM Wave 1.5 dispatch — 把 Wave 1 Track A3（portfolio_var SoT verify）+ Track E3（maker fill empirical baseline）兩個 substantive new finding consolidated 進 spec v1.2 + AMD v0.3，並開新 P1 + P2 ticket。**避免直接派 4-agent re-review v0.2 後又 push back，浪費 capacity**。

**Land 4 commit chain**:
- `3059129f` — spec v1.2（+62/-7）
- `9f16c05d` — AMD v0.3（+25/-11）
- `280ad959` — TODO §11.5 status + 2 new ticket（+30/-19）
- `a8ec162b` — Wave 1.5 PA workspace report（+211）

**A3 finding 收口 mapping（6 finding）**:
1. NO `portfolio_var` 模塊；real SoT = `compute_correlated_exposure_pct + compute_exposure_pct`（`intent_processor/mod.rs:761-805`）
2. SoT = `PaperPosition.qty (filled only)`，完全不讀 `paper_state.resting_orders`
3. Close intent `is_reducing → return PositionCheck::allow()`（`risk_checks.rs:137`），close 自身根本不觸 portfolio gate
4. **FA framing 方向反了**：close pending 對「後續 NEW open intent」是 OVER-estimate（不是 under-estimate）；real under-estimate scenario 是 entry pending（Phase 1B-4.2 已存在 systemic gap）
5. `risk_config.correlation.max_pairwise_r` 是 dead config（schema 存在 + validate test，但 intent_processor 0 callers）
6. paper / exchange path consistency = YES

**A3 推薦 option A**（PM 預批）→ 已收口：
- §二 #16 CONDITIONAL → MAINTAIN（spec + AMD §7 同步）
- 新 P1 ticket `P1-PORTFOLIO-RESTING-EXPOSURE-1`（est. 3 person-day, 250 LOC）平行 close-maker-first IMPL
- close-maker-first IMPL 不阻 portfolio fix；portfolio fix 不阻 close-maker-first

**E3 finding 收口 mapping（6 finding + 三個意外發現）**:
1. fill-conditional ~94% maker rate（spec §1.2 假設條件性成立）
2. **spec §1.2「4.5 bps net per close」overstated** — 實際 0.5-3.3 bps per close attempt（最樂觀 3.31 / 中性 0.95 / 悲觀 0.66）
3. conservative `0.5-2.0 bps net` + 14d 30%+ close-maker fill rate gate
4. **`orders.intent_id` 100% NULL in 7d window** — writer 漏接，無法 intent→order link 算 Guardian-pass-rate（**P2 finding**）
5. **`orders.status` 100% Working** — fire-and-forget；終態須從 `order_state_changes.to_status` 拿
6. **無 fallback to taker 機制** — 70% PostOnly timeout 後 entry 直接放棄，不重發 Market；意味當前 maker-first 是「省錢但少 fill」trade-off

**E3 對 close path 預測** → 已收口：
- close 結構性比 entry 更難 maker fill（trend-side liquidity 差 + 45s timeout 對 exit alpha 致命）
- spec §10.1 Phase 2a 7d → 14d (7d primary + 7d extended observation)
- spec §11.7 NEW AC-19 14d ≥ 30%
- spec §5.5 NEW Race E **mandatory fallback to taker invariant**（防 entry path「直接放棄」behavior inherit close path = 違 §二 #5 生存 > 利潤）
- spec §11.7 NEW AC-18 fallback to taker rate ≥ 95% over 7d
- spec §12.1 NEW HIGH risk row + healthcheck [62] sub-check + 3 unit test gate

**Spec v1.2 主要改動**:
- §1.2 fee saving 3.5/+0.65 bps → 0.5-2.0 bps net per close attempt + 全年估 $160-$400 → $50-$200 + E3 三個意外發現
- §5.5 NEW Race E（規則 1-5 + IMPL gate + healthcheck sub-check + audit row enum invariant）
- §10.1 14d Phase 2a + 拉長理由 + AC-19 引用
- §11.7 NEW AC-18 + AC-19
- §12.1 NEW HIGH row「fallback 直接放棄 inherit entry-side gap」
- §15 NEW P1-PORTFOLIO-RESTING-EXPOSURE-1 + P2-ORDERS-INTENT-ID-WRITER-GAP-1 兩 row
- §17 v1.2 row + Sign-off Status updated

**AMD v0.3 主要改動**:
- §1 Executive Decision footnote「per Wave 1 Track E3 empirical baseline」
- §3 Phase 2a 7d → 14d + Phase 2b 啟動條件加 AC-18 + AC-19
- §7 #16 CONDITIONAL → MAINTAIN per A3 verify finding（close path is_reducing 不觸 portfolio gate；新 P1 ticket option A）
- §8 IMPL Prereq 5 partial-resolved（F-FA-2 ✅ + F-FA-3 ✅ + F-FA-1 留 Wave 2）
- §11.1 NEW Wave 1 Source Audits 5 commit 引用（A1/A3/A4/E1/E3）

**TODO 改動**:
- §11.5 Wave 1 Status block (5 track ✅ + Wave 1.5 IN PROGRESS) + dispatch table 加狀態欄 + dispatch order Wave 1+1.5+2+3 + Phase 2a 14d explicit
- §11 P1 NEW row `P1-PORTFOLIO-RESTING-EXPOSURE-1`（PA → E1，3 person-day，250 LOC，平行 Phase 1b）
- §12 P2 NEW row `P2-ORDERS-INTENT-ID-WRITER-GAP-1`（E1，1 person-day，N+2 backlog）

**Multi-session race 防範實踐**:
- 4 commit 全分離（spec / AMD / TODO / 本 report）
- 每個 commit 用 `git commit --only <file>` 隔絕 index race
- 0 使用 `git add -A`
- 全部 commit message 加 `[skip ci]`
- TODO commit 前 `git diff --stat` 驗證純 Wave 1.5 改動（30 insertions / 19 deletions 全屬本 task）

**Sibling commit detected**:
- patch 過程中 sibling commit `34aa7086 test(ma_crossover): add KAMA unavailable exit path regression tests (Wave 1.5 E4)` push 進 main；本 task 與 sibling 不同檔案，無 race
- patch 過程中另有 sibling commit `72692fe4 docs: Wave 1 sign-off — TODO §11.6 4/4 DONE + changelog + agent reports`；亦無檔案重疊

**自我驗證核對（self-verification checklist）**:
- ✅ 嚴禁事項全 GREEN（不重做 17+14 / 不修 Rust / 不動 V094 SQL / 不修字典）
- ✅ 來源文件對齊（A3 6 處 / E3 11 處 / A4 2 處 / Wave 1 commits 5 / AMD v0.2 + spec v1.1 各 1）
- ✅ 16 條根原則合規（§5.5 強化 #4/#5/#6/#8/#9）
- ✅ 硬邊界檢查（不觸 5 hard boundary + 9 安全不變量 + lease 授權 + H0 Gate）
- ✅ Multi-session race 防範核對（4 commit 分離 + commit --only + 無 add -A + skip ci + diff verify）

**架構教訓 17**：**incremental finding consolidation 比 4-agent re-review 高效**。post-Wave 1 收到 A3 + E3 兩個 substantive new finding，不應該回頭跑 4-agent re-review on v0.2；正確做法是 PA 純增量 patch 進 v1.2/v0.3，然後派 4-agent short re-review（Wave 3）核驗增量收口。**節省 capacity = 1 round QC+FA+BB+MIT 各 30min**。

**Confidence**:
- HIGH for A3 finding 收口 mapping 完整（6/6 finding 全處理）
- HIGH for E3 finding 收口 mapping 完整（6/6 finding + 三個意外發現全處理）
- HIGH for §5.5 mandatory fallback to taker invariant（規則 1-5 + IMPL gate + healthcheck sub-check + audit row enum invariant 全 cover）
- HIGH for `P1-PORTFOLIO-RESTING-EXPOSURE-1` ticket scope（A3 verify report §8 + spec §15 + AMD §7 同步）
- HIGH for `P2-ORDERS-INTENT-ID-WRITER-GAP-1` ticket scope（E3 finding 1 + spec §1.2 + spec §15 + TODO §12 同步）
- HIGH for fee saving 0.5-2.0 bps + 全年估 $50-$200 修正（per E3 empirical 0.66/0.95/3.31 三層解讀，evidence-based）
- HIGH for Phase 2a 14d (7d primary + 7d extended observation)（per E3 conservative discount + 樣本量穩定性需求）
- HIGH for AMD §7 #16 MAINTAIN（A3 verify 證實 close path is_reducing 不觸 portfolio gate）
- HIGH for AMD §8 IMPL Prereq 5 partial-resolved（F-FA-2 + F-FA-3 ✅ commit hash 引用 + F-FA-1 留 Wave 2）
- HIGH for next step recommendation（Wave 2 V094 spec + reject_cooldown / Wave 3 4-agent short re-review + BB1 字典 / Wave 4+ IMPL kickoff + P1 portfolio fix 平行 / N+2 P2 intent_id writer fix）

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--wave_1_5_spec_v1_2_amd_v0_3_consolidated.md`

---

## 2026-05-15 — Wave 2a Track A2: V094 hybrid schema migration spec finalize (F-FA-1 解)

**Trigger**：PM Wave 2 dispatch — Track A2 finalize V094 hybrid schema migration spec + 配套 trading_writer.rs writer upgrade spec + Linux PG dry-run protocol；解 IMPL Prereq 5 第 3 子條件（F-FA-1）。

**Land 4 commit chain**:
- `9b1117a0` — V094 spec (1176 LOC / 15 sections)
- `14a561ec` — PA verdict report (306 LOC)
- `c9234ecf` — AMD v0.3 → v0.3.1 patch (§8 + §12 changelog)
- `a9b3a792` — TODO §11 P1 row + §11.5 Wave 2/3 status block + dispatch order

**3 critical Linux PG empirical findings**:
1. **trading.fills.details JSONB 已存在 V003 line 284**：empirical `psql \d+ trading.fills` 確認 details column 已 ready；3 audit JSON keys 走 details extension = zero schema migration
2. **24h 98 fills 0% details present rate**：`SELECT COUNT(*), COUNT(details) FROM trading.fills WHERE ts > NOW() - INTERVAL '24h'` 返 98/0 (0.00%)；證實 trading_writer.rs:430 INSERT 23-column 漏 details writer gap
3. **Linux runtime applied max = V90**（不是 spec/AMD 寫的 V93）：`SELECT version FROM _sqlx_migrations ORDER BY version DESC` 返 80/82/83/84/85/86/87/88/89/90；V81/V91/V92/V93 source 在 git 但 PG 未 apply；spec/AMD wording drift caveat noted

**Hybrid schema 設計**（spec §1.2 + §2）:
- 2 new columns on trading.fills: `close_maker_attempt:bool NOT NULL DEFAULT FALSE` + `close_maker_fallback_reason:text NULL CHECK enum`
- 3 JSONB keys in trading.fills.details: `close_initial_limit_price:numeric` + `close_final_fill_price:numeric` + `close_maker_eligible_reason:text`
- 設計理由: MIT F-MIT-1 verified GIN index 100x slower than partial BTREE → hot-path filter 必走 column；low-cardinality audit-only → JSON-extension append-only Pareto 平衡

**enum allowlist 10 values（spec/AMD 8 + 本 spec 補 2 superset）**:
- spec/AMD 8 既有: timeout_taker / postonly_reject / cancel_grace_expired / ack_lost / rate_limit_pause / fast_escalate_safety_upgrade / not_attempted_safety_path / engine_shutdown_safety
- 本 spec 補 2 對應 spec §5.5 Race E + AMD §5.4 BB-MF-2 per-symbol: `rate_limit_backoff_per_symbol` + `fallback_to_taker_mandatory`
- safety path 3 enum (`fast_escalate_safety_upgrade` / `not_attempted_safety_path` / `engine_shutdown_safety`): healthcheck [63] NULL ladder 必 exclude（per Consensus-MF-3 + AC-6 + AC-16）

**trading_writer.rs upgrade spec**（spec §6）:
- INSERT 23-column → 26-column（+ details + close_maker_attempt + close_maker_fallback_reason）
- TradingMsg::Fill enum 21 fields → 24 fields
- 13 caller sites enumeration（6 production: unattributed_emit.rs:168 + pipeline_helpers.rs:232 + step_4_5_dispatch.rs:1179, 1462 + commands.rs:301, 618；7 test: trading_writer.rs:979/1113/1241/1274 + pending_registration_order_type_tests.rs:397 + unattributed_fill_tests.rs:106）
- E2 grep verify: `TradingMsg::Fill { ... }` 全 codebase 必出現 39 hit count（13 × 3 fields）；少於 39 即 PR reject
- SLA 影響: tick 主路徑 0 影響；DB INSERT +50 μs per fill（acceptable）；cross-language IPC 0 對等需求（PYO3-ELIMINATE-1 後 Python 無 TradingMsg::Fill 結構）

**Linux PG dry-run × 2 round protocol mandatory**（spec §4 per CLAUDE.md §七 + V055/V083/V084 incident precedent）:
- Round 1: empirical 驗 真實 schema runtime semantic（6 SELECT verify queries）+ 真 reject 非 enum 值 INSERT test + 真 accept enum 值 INSERT test
- Round 2: idempotency 驗（重跑 V094.sql 不 RAISE / 不 double-add column / 不 double-create index）
- Mac mock pytest 絕對不夠（V055 5-round loop + V028-V034 sqlx hash drift incident chain）

**sqlx checksum repair SOP**（spec §5 per project_2026_05_02_p0_sqlx_hash_drift incident）:
- V094 file 落地後又被 edit → DB checksum drift → engine restart 觸 sqlx migrate runtime panic
- 必跑 `cargo run --release --bin repair_migration_checksum -- --version 94`
- E2 / E4 review 必含「engine restart 實測 + sqlx migrate runtime 不 panic」driver evidence；cargo test PASS ≠ runtime sqlx migrate 驗證

**healthcheck [62][63][64][65] integration spec**（spec §7 per AMD §4.1 + AC-1/AC-15/Consensus-MF-2/-3）:
- [62] close_maker_fill_rate (Wilson 95% CI gate): PASS lower_bound >= 0.65 / WARN 0.60-0.65 / FAIL < 0.60 / NEUTRAL n<30
- [63] close_maker_audit_lineage_integrity (dual gate): Gate A W-C Caveat 2 close path 0 spine row + Gate B audit completeness ratio NULL ladder
- [64] close_maker_rate_limit_pause_duration: per-symbol backoff <= 100/24h + global pause = 0
- [65] close_maker_reject_sample_completeness: per env 7d 各 reject category sample >= 1（per AC-15 BB-MF-5）
- 新檔 helper_scripts/db/passive_wait_healthcheck/checks_close_maker_audit.py
- runner.py CHECKS list 註冊 + CLAUDE.md §七 healthcheck 計數同步 51 → 55

**IMPL plan + 估工時**（spec §8）:
- Total ~480 LOC / ~3.1 E1-day（含 Linux PG dry-run × 2 round 0.5d）
- E1 並行 2 worktree（A: V094 SQL ~80 LOC + B: writer + 13 callers ~235 LOC）+ 1 串行（C: 4 healthcheck ~220 LOC）
- IMPL kickoff 派工順序: PA spec → E1 worktree A+B 並行 → C 串行 → E2 review → E4 regression → ssh trade-core Linux PG dry-run × 2 → restart_all --rebuild → engine restart verify sqlx migrate + healthcheck PASS → QA Phase 2a 14d → PM sign-off

**Backward-compat append-only**（spec §9 per AMD §10.1）:
- V094 純粹 ADD COLUMN + ADD CONSTRAINT，沒 ALTER existing column type / DROP column / RENAME column
- 既有 SELECT/INSERT/UPDATE 0 影響；既有 healthcheck 0 影響
- mirror V083 NOT VALID precedent；既有 fills row close_maker_attempt = FALSE default
- IMPL 階段不可改設計（hybrid → separate column 必重評 + 重派 4-agent review per AMD §10.1）

**Rollback paths**（spec §10）:
- Phase 2a/2b/3 FAIL: TOML hot-reload `use_maker_close=false` → 1 tick 內回 market；V094 schema 不需 rollback
- IMPL 階段未 deploy: V094 schema rollback 通過 manual DROP COLUMN + DROP INDEX + DELETE _sqlx_migrations row
- Post-deploy emergency: operator-triggered kill-switch（cancel_token shutdown + force market）

**F-FA-1 解除條件 (a)(b)(c) 全完成**:
- (a) PA spec finalize V094 SQL ✅ — spec §2 schema + §3 Guard A/B/C + §10 rollback
- (b) trading_writer.rs INSERT 升級 details writer spec ✅ — spec §6 writer upgrade + 13 caller sites + TradingMsg::Fill enum
- (c) Linux PG empirical query 驗 schema ✅ — spec §1.2 + §4 dry-run × 2 round + §4.4 V93 vs V90 drift caveat

**IMPL Prereq 5 全 RESOLVED**:
- F-FA-1 ✅ Wave 2a Track A2 commit `9b1117a0`
- F-FA-2 ✅ Wave 1 Track A3 commit `96995b61`
- F-FA-3 ✅ Wave 1 Track A4 commit `a5a7107c`

**Multi-session race 防範實踐**:
- 4 commit 全分離（spec / PA verdict / AMD / TODO）
- 每個 commit 用 `git commit --only <file>` 隔絕 index race
- 0 使用 `git add -A`
- 全部 commit message 加 `[skip ci]`
- 接手前 fetch 確認 no sibling commits 衝突 V094 scope
- Sibling commits 7b0a8e8c (BB Wave 3a short re-review) + cabb2fcd (Wave 1 Round 2 真修) 期間 land；與 V094 scope 互不重疊

**架構教訓 18**：**多階段 PA spec 串行設計的 cascade 價值**。Wave 1 Track A4 (F-FA-3 PA report) §4 + §4.4 已給 V094 schema 雛形 + writer gap discovery + Linux PG mandatory；本 spec 主要是 finalize + enrich（補 enum 2 值 + 13 caller sites enumeration + healthcheck 4 個 spec + V93 vs V90 drift caveat）。**Wave 1 Track A4 design quality 直接決定 Wave 2 spec finalize 速度** — 早期 PA report 的「設計建議 + 雛形」段落是後續 spec finalize 的 force multiplier。

**架構教訓 19**：**spec/AMD wording drift 必須由 empirical Linux PG verify 揭露**。spec v1.2 §4.4 + AMD v0.3 §4.1 寫「current max applied V093」是 incorrect；事實 V90。Mac source files V091/V092/V093 在 git 但 PG 未 apply。**PA 派 sub-agent 前必先 ssh trade-core empirical query 驗 schema 真實狀態**，不能基於 spec 假設。本 spec §4.4 caveat 段是 source-of-truth 修正；spec/AMD 文字無需 patch（V094 仍 next-free numeric slot；deploy semantic 不變）。Pre-Wave 4 PA 補一輪 Linux V81/V91/V92/V93 backlog migration apply 檢查（per spec §4.4 caveat + TODO §11.5 Wave 3.5 row）。

**架構教訓 20**：**TradingMsg::Fill enum 升級 = caller sites enumeration 是 critical 防護**。Rust strong-type 保證 compile-time 不漏接（13 sites 必有一漏接即編譯錯），但 PR review 仍需 grep verify 39 hit count（13 × 3 fields）；遺漏一個 caller 會編譯錯，遺漏一個 default value 會語意錯（close_maker_attempt: None vs false）。E2 review 必跑此 grep 的具體命令在 spec §12.2 提供。

**Confidence**:
- HIGH for V094 hybrid schema design correctness（mirror V083 NOT VALID precedent + Linux PG empirical schema verify）
- HIGH for trading_writer.rs writer gap empirical（24h 98 fills 0% details rate confirmed）
- HIGH for 13 caller sites enumeration completeness（grep verified 全 codebase）
- HIGH for enum allowlist 10 values superset（spec/AMD 8 + 本 spec 補 2 對應 spec §5.5 Race E + AMD §5.4 per-symbol）
- HIGH for Linux PG dry-run × 2 round protocol（mirror V055/V083/V084 incident precedent）
- HIGH for sqlx checksum repair SOP（mirror project_2026_05_02_p0_sqlx_hash_drift incident chain）
- HIGH for healthcheck [62][63][64][65] integration spec（per spec §8.1 + AMD §4.1）
- HIGH for backward-compat append-only（V083 mirror + 0 ALTER existing column + 0 DROP + 0 RENAME）
- MEDIUM for V81/V91/V92/V93 backlog drift mitigation（caveat identified, Pre-Wave 4 backlog apply 工作未 land；TODO §11.5 Wave 3.5 row tracked）
- MEDIUM for spec/AMD wording drift（V93 → V90）— 本 spec 顯式修正，但 spec v1.2 + AMD v0.3 文字無修

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--v094_schema_migration_spec_pa_verdict.md`

---

## 2026-05-15 — Wave 1.5b: spec v1.3 + AMD v0.4 consolidated patch (Wave 3a 4-agent re-review consolidation)

**Trigger**：PM Wave 1.5b dispatch — Wave 3a 4-agent short re-review on AMD v0.3 + spec v1.2 verdict 4/4 APPROVED；QC 1 NEW MUST-FIX QC-MF-3 + 1 NEW SHOULD-FIX QC-SF-6 + FA 4 cosmetic + MIT 2 P3 advisory；本 patch 純 numerical / cosmetic 增量無新風險 → IMPL Prereq 條件 2 SATISFIED.

**Land 4 commit chain**：
- `c0d34fcb` — spec v1.2 → v1.3（19/-12 LOC）
- `2f55d053` — AMD v0.3.1 → v0.4（15/-5 LOC）
- `a436553f` — TODO §11.5 update（Wave 1.5b status + dispatch order Wave 1-11 final）
- 本 PA report

**5 patch items 全 land**：
1. **QC-MF-3 (CRITICAL)** — spec §11.1 AC-5「+1.5 bps」→「+0.5 bps for n≥50 cells / directional only (≥ 0) for n<30 cells」（per Wilson-CI mechanism per Consensus-MF-2）+ §11.3 AC-11「+1.5 bps」→「+0.5 bps」（對齊 §1.2 fee saving 0.5-2.0 bps net per close attempt 中性 0.95；原 +1.5 deterministic FAIL 修為對齊 conservative 下界）+ §11 開頭 v1.3 patch footnote
2. **QC-SF-6 (SHOULD)** — spec §11.7 AC-18 補 Wilson-CI sub-clause（per env 7d 樣本算 Wilson 95% CI lower vs 95%；CI lower < 90% → WARN；CI lower < 85% → FAIL；mirror AC-14 mechanism）+ §5.5 line 410-411 加 footnote 引用 IMPL phase healthcheck [62] sub-check SQL Wilson 計算
3. **FA #1 cosmetic** — AMD §3 rollout table footnote「AC-1..AC-16」→「AC-1..AC-19」（per FA-SF-2 SoT 引用避免 spec/AMD drift）
4. **FA #2 cosmetic** — AMD §10.1 V094 backward-compat 加 v0.4 IMPL kickoff 必含項：trading_writer.rs:430 details payload writer 升級 + TradingMsg::Fill enum 21→24 fields + 13 caller sites + 兩段式 schema invariant（per Wave 1 Track A4 §4.4 + Wave 2a Track A2 V094 spec §6 + empirical 24h 98 fills 0% details rate）
5. **FA #3 cosmetic** — AMD §2.3 negative whitelist 真風控行補 PA 識別變體 `risk_close:fast_track*` / `halt_session*`（spec §4.3 已列；AMD 同步以對齊 §三/§四 fail-closed semantic）
6. **FA #4 cosmetic** — AMD §7 16 原則表補 #3 / #11 / #13 / #15 4 行明列 PASS（治理 trace 完整度 7/12 → 11/12）：#3 close maker dispatch 仍走 OrderDispatchRequest 單通道 / #11 Whitelist + carve-out 不影響 Agent 自主決定 timing/symbol / #13 close-maker-first 純 execution-quality 不增 AI 調用 / #15 不變動 5-Agent 架構

**MIT 2 P3 advisory 處理**：
- MIT-AC-18-CI-NOTE — 與 QC-SF-6 重疊，已被 QC-SF-6 cover；無獨立 patch
- MIT-AC-19-Stratification-NOTE — per-strategy + per-symbol stratification 建議 OPTIONAL deferred IMPL phase healthcheck（不入 spec text，避免 over-spec；IMPL phase healthcheck [62]/[65] 加 stratification logic 由 PA Wave 4+ IMPL plan 涵蓋）

**A3 §12.2 framing 更新（QC §7 反問 5 衍生）**：
- spec §12.2 line 758「#16 組合風險 maker pending 期 portfolio under-estimate」（v1.1 留設）改「entry-side resting maker pending 期 portfolio under-estimate（既有 systemic gap，新 P1 ticket option A 平行解；per Wave 1 Track A3 verify finding，close path is_reducing→allow() 不觸 portfolio gate 不引入新 risk vector）」+ Mitigation 改 `P1-PORTFOLIO-RESTING-EXPOSURE-1` 平行 IMPL（A3 verify report §8 + §15 ticket scope）

**spec/AMD 內部一致性 cross-check（pass）**：
- Fee saving range：spec §1.2 0.5-2.0 bps net ↔ AMD §1 footnote `^v03_fee` 0.5-2.0 bps ✅
- AC-5 / AC-11 數值：spec +0.5 bps for n≥50 ↔ AMD §3 引用 AC-1..AC-19 不重述 ✅（per FA-SF-2 SoT 不重述）
- AC-18 Wilson-CI：spec §11.7 + §5.5 footnote ↔ AMD §3 列 AC-18 不重述機制 ✅
- Negative whitelist：spec §4.3 fast_track* / halt_session* 已列 ↔ AMD §2.3 v0.4 補對應 ✅
- 16 原則 #3/#11/#13/#15：spec §13.1 標「不觸」（execution-quality 不觸 governance core）↔ AMD §7 v0.4 補明列 PASS（治理 trace 視角必明列）✅
- §12.2 framing：spec line 758 entry-side framing ↔ AMD §7 #16 v0.3 MAINTAIN + ticket 引用 ✅
- trading_writer.rs:430 升級：spec §15 ticket P2-ORDERS-INTENT-ID-WRITER-GAP-1 + V094 spec §6 ↔ AMD §10.1 v0.4 IMPL kickoff 必含 ✅

**IMPL Prereq 條件 2 SATISFIED**：
- 4-agent re-review 4/4 APPROVED（QC + FA + BB + MIT）+ Wave 1.5b spec v1.3 + AMD v0.4 patch land 收口完整
- 17 must-fix + 14 should-fix + Wave 1.5 A3+E3 finding + Wave 1.5b QC-MF-3/QC-SF-6/FA 4 cosmetic 全 integrated
- 條件 1 ✅ + 條件 2 ✅ + 條件 5 ✅ + 條件 6 ✅ partial（E1+E4 land, E2 review pending）+ 條件 3 ⏳ 三閘 + 條件 4 ⏳ IMPL kickoff
- 6 條件中 4 條 ✅ / 1 條 ✅ partial / 2 條 ⏳

**Side-effects 分析**：
- Rust commands.rs / Python / TOML / V094 SQL：0 影響（本 patch 不動代碼）
- Healthcheck [62] sub-check SQL：future IMPL（per QC-SF-6 加 Wilson-CI 計算，PA Wave 4+ IMPL plan 涵蓋）
- Healthcheck [62]/[65] stratification：OPTIONAL future IMPL（per MIT-AC-19，IMPL phase 加 per-strategy + per-symbol logic）
- AC evaluation logic：future IMPL（AC-5 n≥50 vs n<30 階梯 + AC-18 Wilson-CI gate）
- Phase 2a 14d Demo PASS gate：v1.3 修 AC-5 / AC-11「deterministic FAIL」修為「對齊 conservative 下界可達成」；不放鬆 Phase 2a 嚴謹度
- 治理層：MAG-082 W-C lineage / Decision Lease / 9 安全不變量 = 0；16 原則合規強化（trace 7/12 → 11/12）

**Multi-session race 防範實踐**：
- 4 commit 全分離（spec / AMD / TODO / PA report）
- 每個 commit 用 `git commit --only <file>` 隔絕 index race
- 0 使用 `git add -A`
- 全部 commit message 加 `[skip ci]`
- Push 模式：`git push origin HEAD:main`（worktree branch HEAD → origin/main fast-forward）
- Sibling commits land 期間（28c571c7 BB1 字典 + 8321b4b7 E4 reject_cooldown regression + f31b6e8f WP-06/08/13）→ 全部 fast-forward push 成功，無 rebase / merge 操作
- 改動 file 範圍與 sibling 互不重疊：本 patch 動 spec / AMD / TODO / PA report；sibling 動 BB 字典 / E4 test / Python deepcopy 等

**架構教訓 21（Wave 1.5b 衍生）**：**incremental cosmetic patch 不需重派 4-agent re-review**。Wave 3a 4-agent re-review 識別 1 NEW MUST + 1 NEW SHOULD + 4 cosmetic + 2 P3 advisory，全部是 numerical / cosmetic / framing 增量無新風險 → PA 直接整合 spec v1.3 + AMD v0.4 patch land 即關閉條件 2，不需要再派 Wave 3c 4-agent re-review on v1.3/v0.4。**節省 capacity = 1 round QC+FA+BB+MIT 各 30min（同 Wave 1.5 教訓 17 一致）**。判斷準則：本次 patch 是否引入「新 risk vector / 新 schema / 新 IMPL scope / 新 governance gate」？四答都 NO → 純 patch land。

**架構教訓 22**：**spec/AMD 雙文一致性檢查 SOP**。本 Wave 1.5b 修 AC-5 / AC-11 / AC-18 數值 + framing 必須同時 cross-check spec §11 + AMD §3（FA-SF-2 SoT 不重述原則：AMD 引用 spec AC SoT，避免雙文 drift）。本次發現 AMD §3 footnote 「AC-1..AC-16」需更新為「AC-1..AC-19」就是雙文 drift 證據（FA-#1 cosmetic）。**未來：每 spec 改 AC 範圍/數值，必檢 AMD 對應引用是否同步**；patch 提交流程加「spec/AMD cross-ref 檢查」步驟。

**Confidence**:
- HIGH for QC-MF-3 fix（AC-5/AC-11 數值對齊 §1.2 0.5-2.0 bps 中性 0.95）
- HIGH for QC-SF-6 fix（Wilson-CI sub-clause mirror AC-14 mechanism）
- HIGH for FA 4 cosmetic（AC SoT 引用、trading_writer.rs:430 升級、negative whitelist 變體、16 原則 #3/#11/#13/#15 全 land）
- HIGH for §12.2 framing（line 758 entry-side framing 對齊 A3 verify report + AMD §7 #16 v0.3 MAINTAIN）
- HIGH for MIT P3 advisory 處理（重疊 → cover；stratification → OPTIONAL deferred）
- HIGH for race 防範（4 commit 分離 + commit --only + 0 add -A + skip ci + sibling 3 commit 期間全 fast-forward）
- HIGH for IMPL Prereq 條件 2 SATISFIED 結論

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--wave_1_5b_spec_v1_3_amd_v0_4_consolidated.md`


## 2026-05-16 — MIT-P0-2 cron reconcile (false finding verdict)

**Trigger**：PM 12-agent audit sign-off 第 2 條 reprioritization 強制 PA reconcile MIT-P0-2 「6/12 ML cron 未裝」vs TODO `P0-V3-CRON-NOT-INSTALLED` DONE 2026-05-09 before WP-08 dispatch。

**Verdict**：**MIT-P0-2 是 FALSE FINDING（definition drift）**。F-08 invariant 18 真實已 closed (2026-05-15 03:36:32 status=ok empirical verified)。MIT 用「helper_scripts/cron/*_cron.sh script files in directory vs in crontab」廣口徑誤判為「未裝 oversight」，但 6 個 deliberately-not-in-crontab cron 各有獨立 deliberate 不裝理由：

| Script | Deliberate 不裝理由 |
|---|---|
| `blocked_symbols_30d_unblock_check_cron.sh` | 30d unblock retry deliberate manual until LG-3 supervised-live |
| `edge_estimate_snapshots_cycle_cron.sh` | P0-EDGE-1 active 期 deliberately 不污染 stats |
| `outcome_backfiller_live_cron.sh` | live 未啟動 → 空轉浪費資源 |
| `panel_aggregator_health_cron.sh` | W1-1 BB WS-first refactor 後可能 redundant |
| `mlde_shadow_recommendations_retention_cron.sh` | V075 prune_old_plain_tables() 路徑 alternative |
| `replay_artifact_prune.py` / `replay_key_archive_cleanup.py` | REF-20 Sprint A-D 收口期 replay 體積不痛 |

**真實 inventory 對照表**（read-only Linux empirical 2026-05-16）：
- `helper_scripts/cron/` 14 個 distinct executable cron script
- Linux crontab 真實 10 active entries；其中 `helper_scripts/cron/` 命中 4：edge_label_backfill */30 / ref21_universe :20 hourly / ref21_microstructure 每分 / **ml_training_maintenance_cron.sh @ 17 3 * * *** (F-08 載體)
- `ml_training_maintenance.py` DEFAULT_JOBS 10 個 ML job（linucb/mlde_shadow_advisor/mlde_demo_applier/scorer_trainer/quantile_trainer + thompson/optuna/cpcv/dl3_foundation/weekly_report）跑在 1 個 cron entry → F-08「5 ML cron」TODO 文字稍有誤導（實際 5 F-08 + 5 legacy = 10 jobs in 1 wrapper）但 invariant 18 真實已 closed
- `/tmp/openclaw/logs/ml_training_maintenance_cron.log` 649KB + status_json `status: ok` 是 24h+ 真實 fire 證據

**MIT「12」數字推斷**：MIT 沒寫 raw audit md 列舉 12 個；PA 反推三種口徑（cron script files / ML-pipeline-related / job 數）最可能用「ML/learning 相關 12 script」口徑，去掉 4 已裝 + 1 手動 fire + 1 by-design = 6 deliberate 未裝。**6 不是 oversight**。

**PM dispatch recommendation**：
- WP-08 內移除 MIT-P0-2 行（false finding）
- Spawn `P2-CRON-DELIBERATE-NOT-INSTALLED-LIST` umbrella ticket 登記 6 個 deliberate 未裝（或 6 個獨立 P2 ticket）
- WP-08 P0 BLOCKER 可考慮降為 P1（MIT-P1-1 已 closed 2026-05-15 + MIT-P1-2/P1-3/DB-6 是 P1 + MIT-P0-1 PG tuning 是 operator manual action）
- TODO line 323 文字 hygiene patch optional（建議 wording：「F-08 `ml_training_maintenance_cron.sh @ 17 3 * * *` (含 5 F-08 + 5 legacy jobs) installed」）

**Side-effects 分析**：
- 對 RustEngine / IPC / API schema / asyncio / GovernanceHub / risk envelope / 5-Agent / 16 原則 / DOC-08 9 不變量 = 0
- 對 Sprint 1b / EDGE-P2-3 / W3 / W-AUDIT-8a/8b / true live promotion = 不阻塞
- F-08 invariant 18 / [55] lineage / [67] feature baseline / [27] intents freeze 都 ✅

**16 根原則合規評級**：A 級（16/16 + 硬邊界 0 觸碰）

**架構教訓 23**：**audit cross-finding reconciliation 必先做「definition 對齊」再做「verdict 對齊」**。MIT-P0-2 用「cron script in directory but not in crontab」口徑，TODO 用「F-08 specific 5 ML cron + invariant 18」精確口徑；同一物理事實在不同 framing 下出現「DONE vs not installed」表面矛盾。PA reconcile 第一步是把雙方口徑對齊 — 不是直接挑判勝負。本次發現 MIT 廣口徑下「6 個 deliberately not installed」是 P2 觀察決策池，TODO 精確口徑下「F-08 5 ML cron」已 closed；兩者並存無真實矛盾。

**架構教訓 24**：**Linux empirical query 是 reconcile 必跑步驟**。本次 ssh trade-core query 三證據（`crontab -l`、`tail -3 ml_training_maintenance_cron.log`、`ls /tmp/openclaw/status/ml_training_maintenance_status.json`）30 秒給出明確「invariant 18 真實 closed」結論。若只在 Mac source 層找 MIT raw audit md（不存在）會 stale 在「PA 該信誰」的死循環。CLAUDE.md §三 「§三 數據 vs runtime drift 防線」7-day 重驗 + healthcheck id 規則本次體現。

**Confidence**:
- HIGH for F-08 invariant 18 真實 closed empirical 結論（log + status_json + crontab 三證據）
- HIGH for 「MIT-P0-2 false finding」judgement（definition drift 而非 missing fix）
- HIGH for 6 個 deliberately-not-installed cron 各自 deliberate 理由分析（PA 反推；若 MIT 不同意請出 raw audit md）
- HIGH for WP-08 reframe recommendation（移除 MIT-P0-2 + spawn P2 umbrella ticket + P0 → P1 考慮）
- MEDIUM for 「MIT 12 數字真實口徑」inference（PA 反推三口徑，B 口徑最可能；若 MIT 後續 push back，PA 接受訂正）

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--mit_cron_reconcile.md`


## 2026-05-16 — Wave 3.5: Linux PG backlog migration apply audit (V081-V093)

**Trigger**：V094 spec §4.4 caveat + TODO §11.5 Wave 3.5 row；F-FA-1 PA verdict 2026-05-15 commit `9b1117a0` 接續工作。Pre-Wave 4 IMPL kickoff 必檢的 backlog migration apply 狀態 audit。

**Mode**：Read-only Linux PG empirical + source tree compare（不修改 migration / runtime / config）。

**Verdict**：**NEEDS-ACTION**（V094 IMPL kickoff NOT blocked / V094 deploy BLOCKED 直到 V091/V092/V093 backlog 處理乾淨）

**3 critical empirical findings**：
1. **V081 = dead slot**（合法跳號）— source tree 無 V081*.sql + `_sqlx_migrations` row 80→82 連跳；不是 backlog
2. **V091 / V093 = schema partial-applied + sqlx metadata 缺 row**（silent drift）—
   - V091 `chk_reason_code_mutually_exclusive` constraint DB convalidated=t 已存在；def 對齊 file spec
   - V093 三 enum constraint (outcome/evidence_tier/side) 都已 partial-apply 並對齊 file spec
   - 但 `_sqlx_migrations` 無 row → engine restart sqlx migrate run 將重 apply（idempotent design 應 PASS）
3. **V092 = real not-applied gap**（W1 sub-task 3 D+1+ deploy 漏執行）—
   - 0 matview / 0 continuous_aggregate
   - prereq tables (`panel.funding_rates_panel` + `panel.oi_delta_panel`) + timescaledb 2.26.1 全在 → ready to apply
   - file idempotent design OK（WITH NO DATA + IF NOT EXISTS / 8 guards）

**Runtime context**：
- engine 不在跑（systemctl + flag + pid 三證據）
- `OPENCLAW_AUTO_MIGRATE` env 未設 → engine restart 不會自動 sqlx migrate run
- 必走 `helper_scripts/linux_bootstrap_db.sh --apply` 或顯式設 flag

**Apply protocol（§5）**：
- §5.1 PA pre-apply：Mac file content + git log mtime verify
- §5.2 Step 1 V091 metadata 補登 (LOW risk 0.2h)
- §5.2 Step 2 V092 真 IMPL × 2 round dry-run (LOW-MED 1.0h)
- §5.2 Step 3 V093 metadata 補登 (LOW risk 0.2h)
- §5.2 Step 4 全 verify (LOW risk 0.3h)
- Total ~2h / operator + PM 合執

**sqlx checksum repair SOP**：若任 step 觸發 `migration X was previously applied but has been modified` → `cargo run --release --bin repair_migration_checksum -- --version <N>`（mirror project_2026_05_02_p0_sqlx_hash_drift incident）

**16 根原則合規**：A 級（16/16 + 硬邊界 0 觸碰；純 read-only audit + governance/SOP 補強）

**派發 Action 清單**：
- 本 PA report sign-off → PM
- §5 protocol 寫成 Wave 3.5 RUN PLAN (短 spec) → PA 或 PM
- TODO §11.5 Wave 3.5 row → IN_PROGRESS
- 執行 §5.2 Step 1-4 → operator + PM
- Wave 4 IMPL kickoff 不阻塞（V094 spec / writer / healthcheck design 已 Wave 2a closed）
- V094 deploy gate 必驗 V091/V092/V093/V094 全 `_sqlx_migrations`

**架構教訓 25**：sqlx_migrations metadata 與 DB physical schema 可能 silent drift。Discovery 靠 PA cross-section empirical query（constraint def + convalidated + matview existence vs `_sqlx_migrations` 表）。SOP 強化：嚴禁 sub-agent 直接 psql -f 跑 migration file；必走統一入口 `helper_scripts/linux_bootstrap_db.sh`；如必須 manual apply 必同 commit `INSERT INTO _sqlx_migrations` 維持 metadata 一致。E2 grep rule 加查 `psql.*-f.*sql/migrations/V[0-9]+` callsite。

**架構教訓 26**：dead slot (V081) 是合法 numbering 設計，不要 backfill「補洞」。判斷準則：missing version → 先查 source tree → 無 file = dead slot 0 gap；有 file 但 sqlx 缺 = real backlog gap。

**Confidence**:
- HIGH for V091/V093 schema drift identification（empirical convalidated=t / pg_get_constraintdef 對齊 file spec）
- HIGH for V092 not applied confirmation（0 matview + 0 continuous_aggregate）
- HIGH for V081 dead slot confirmation（source tree + sqlx 雙缺）
- HIGH for engine not running + AUTO_MIGRATE not set（runtime three-evidence）
- MEDIUM for V091/V093 file mtime 後 mutate possibility（必 git log verify §5.1 Step 2；目前推斷未 mutate）
- MEDIUM for V092 真 IMPL apply 期 matview build 工時（視 panel.* row 量；WITH NO DATA 0 boot 阻塞已 mitigate）

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--wave_3_5_linux_pg_backlog_migration_audit.md`

## 2026-05-16 — Wave 4-A: W-AUDIT-8b Funding Skew Stage 0R Run Plan（read-only design）

**Verdict**：tooling 1034 LOC commit `d9adf46b` 完成 ~70% spec v0.2 contract；**8 MUST-FIX + 8 SHOULD-FIX gaps** 識別給 E1（est ~16h / 1.5-2 E1-day）。Linux PG empirical（read-only ssh trade-core）：`panel.funding_rates_panel` 179126 rows × 25 sym × 5.3d span × `bybit_v5_ws_tickers` uniform；`panel.oi_delta_panel` 179871 rows × 25 sym × 5.3d × `bybit_v5_ws_open_interest`；overlap 25 sym；`learning.strategy_trial_ledger` 17335 rows / K_prior funding-related=9 / 全平台=69（MIT 必簽 SQL semantic）；28 distinct funding cycles 5.3d window；5m klines 4015 rows for 14d 完整。

**8 MUST-FIX**：(1) K_prior funding-comparable filter SQL；(2) bootstrap CI 8h funding-cycle 第二 block；(3) CSCV PBO purge + embargo；(4) source_mode `ws_current` vs `rest_settled` 區分；(5) adjacent-cell plateau check；(6) baseline lift vs no-funding/OI baseline；(7) settlement-window adverse-drag sensitivity；(8) bootstrap_lower 用 pooled CI 不是 cell-level。

**8 SHOULD-FIX**：passive_wait_healthcheck `[68]` 新增 / cohort_coverage field / maker_taker_split / per_symbol_summary / block_size unit clarify / `--seed` argument / smoke 加 K_prior 邏輯測試 / smoke 加 leak-free 反例測試。

**Wave 4-A 6 steps**：PA spec v0.3 patch (0.5d) → E1 MUST-FIX IMPL (1.5d) → E2+A3 對抗審 (0.5d 並行) → E4 regression (0.5d) → round 1 smoke (0.5d) → 4-agent review (0.5d 並行) → round 2 full grid (0.5d) → PA verdict (0.5d) → PM sign-off (0.5d) = total 5.5-6 worker-day / calendar 1-2 weeks。

**Expected verdict**：`eligible_for_demo_canary=false` 大概率（panel 5.3d 不夠以 hit n_eff 300 + 14 cycles + DSR 0.95 同時；K_total=4059 對應 sr_benchmark √(2 ln K) ≈ 4.07，DSR 0.95 對應 sr_hat ~5-6 大概不能達到）。Verdict=false 是 **design-pass 不是 strategy-fail**；packet 設計即包含「強濾網 + 顯式 K_total」。

**stop rules 10 個 + 11 個 runtime promotion floor checks 在 §4 列舉**；強制工作鏈 §5 PA→E1→E2+A3+E4→QA(QC+MIT+BB)→PM；JSON contract §6 21 fields skeleton 給 E1。

**Critical leak-free finding**：SQL 中 `signal_ts_ms = k.close_ts_ms` AND `prior_5m_return_bps = same bar return`，**契約是「signal fired at bar close, using closed bar's return」**。E2 + MIT 必簽 boundary semantics。fwd window 15m/30m/60m 都 `close_ts_ms >= signal_ts_ms + horizon`，leak-free。

**16 根原則合規 A 級**：16/16 + 硬邊界 0 觸碰 + DOC-08 9 不變量 N/A（不交易）；100% read-only design + tool patch；不觸 risk/sizing/config/auth/demo/live/paper enable。

**5 BLOCKING risks**：(B1 HIGH) panel 5.3d 可能不夠 single-cycle share > 25% gate；(B2 MED) K_prior SQL MIT 未簽；(B3 MED) K_total=4059 DSR 0.95 mathematical 強濾網；(B4 LOW) settlement-window adverse-drag 定義 spec 未明寫；(B5 LOW) `funding_arb` retired ledger 9 row 是否算 K_prior。

**架構教訓 27**：**1034 LOC 既有 tooling 看起來「已完成」但對照 spec v0.2 + PM Stop Rules 仍有 70% completion gap**。PA reconcile 必逐條 spec contract → tooling field 對應，**不能基於「tooling exists 數字」推斷 readiness**。本次 8 MUST-FIX 全部都需要 E1 額外 IMPL；E1 sign-off 前必先 PA spec patch + MIT K_prior SQL signed，否則 round 1 smoke 跑出來會被 QC/MIT push back 重跑。

**架構教訓 28**：**panel 數據窗 vs spec floor 必先 empirical 確認再設計**。本次 ssh trade-core query 30s 給出「panel 5.3d 不是 14d」結論，**才能正確估「round 1 預期 verdict false / round 2 是否需要 calendar 延後 3-5 天累積 panel」**。Mac source-only 設計會誤判 panel availability。

**Side-effects 分析（純設計，0 runtime/code change）**：
- 對 RustEngine / IPC / GovernanceHub / 5-Agent / 風控 = 0
- 對 Sprint 1b close-maker-first IMPL = 0（並行 lane，per archive §6 next-round scope）
- 對 W3-1/W3-2 / P0-EDGE-1 / W-AUDIT-8a C1 = 0（並行 alpha lane）
- 對 Mac/Linux runtime / paper / demo / live = 0
- 對 [55]/[27]/[67]/[40]/[66] healthcheck = 0

**Confidence**:
- HIGH for tooling 8 MUST-FIX gap identification（逐 spec field 對應）
- HIGH for Linux PG empirical 數字（read-only ssh trade-core query 30s）
- HIGH for `signal_ts_ms = k.close_ts_ms` leak-free boundary
- HIGH for Wave 4-A 6 step structure
- MEDIUM-HIGH for expected verdict false 推斷（DSR sr_benchmark math + n_eff 300 + 14 cycles 多 gate 同時）
- MEDIUM for round 2 grid 是否 zoom-in 還是 calendar 延後（需 round 1 cycle share 分布實證）

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_stage0r_run_plan.md`

## 2026-05-16 — W-AUDIT-8b Stage 0R RED RCA + Next Step（PA recommend Option A）

**Trigger**：W-AUDIT-8b Stage 0R replay packet 跑出 RED verdict (`eligible_for_demo_canary=false`)，5.72d 數據 vs 7d spec window。判定「sample insufficient vs signal failure」+ pivot 評估 + 3-gate 影響。

**Verdict**：RED **是 signal failure 主導 + sample 邊際次要**（65/35 混合，signal 占主導）。

**Critical empirical findings**（read-only Linux artifact `/tmp/openclaw/w_audit_8b_stage0r_20260516_pa.json`）：
1. Strategy primary `n=7, n_eff=1`（INJUSDT crowded_short_squeeze only）；`crowded_long_fade` 全 branch `n=0`
2. Baseline pooled `n=39,181, n_eff=6,530`（同 5.72d 同 25 sym）→ **baseline 採樣比 strategy 多 5,597 倍**
3. Strategy trigger rate = 7 / 411,840 candidate bars = **0.0017%** = self-imposed scarcity
4. Baseline avg_net_bps = **-16.91 bps**（負 edge 顯著）
5. K_prior=0（strict-funding-skew，funding_arb retired 不繼承）；K_total=4050；sr_benchmark=√(2 ln 4050)=4.07

**Sample 邊際 vs Signal 主導**：5.72d → 7d / 14d / 30d 都不會解 spec floor（`pooled n_eff >= 300`），因為 trigger gate 0.0017% rate × extra days = sub-linear grow。30d 預測 n_eff ≈ 6，遠不到 floor。

**3 Option 評估**：
- **Option A (PA 推薦)**: defer 1d 拿 7d window + spec v0.3 patch 加 trigger gate sensitivity sweep (z >= 1.0/1.2/1.5/2.0) + round 2 expanded grid + final verdict @ round 2；不破 AMD-02 §8 condition 3 wording
- **Option B**: tombstone 8b + pivot 8c/8a-D；但 8c 卡 C1 in-flight，8a Phase D 21-30 days，net 不加速 + 浪費 sibling land 1034 LOC + 4-agent hardening
- **Option C**: decouple Phase 1b from 3-gate（AMD §8 wording 修訂為 OR / 縮減）；違反原 priority discipline，需 PM + 4-agent 重 sign-off

**PA 推薦 Option A**：
1. Spec v0.2 還沒 sweep trigger gate sensitivity，不應 premature tombstone
2. Sibling 已 land tooling 1034 LOC + 4-agent hardening (sibling commits 已 incorporate)
3. 7-14 calendar days 延長可被 P0-EDGE-1 closure (亦 in-flight) absorb，不是 critical path 延長
4. 維持原 governance (三閘 strict AND) priority discipline 不破
5. Option C 觸 AMD §8 修訂連帶 4-agent 重 sign-off 成本不對等

**Sibling work check**：`git status` confirmed dirty files 來自並行 Wave 2-4 + Phase 1b + V094 + maker_rejection，無重疊。Sibling 兩個直接相關報告：
- `PM/.../2026-05-16--w_audit_8b_stage0r_gap_closure.md` (tooling gap closure smoke PASS k_total=555)
- `PM/.../2026-05-16--w_audit_8b_adversarial_hardening.md` (4-agent QC/E2/MIT/BB consolidated hardening smoke PASS k_total=4119)

兩件 sibling work 已 land 並完全 incorporate；本 PA 報告不要求 tooling 修補，純基於 PA 自己 run artifact 做 RED 性質判定。

**AMD-2026-05-15-02 §8 wording 結論**：暫不需修訂；Option A 不破 condition 3 wording；conditional amendment 觸發點 = Option A 走完 spec v0.3 + round 2 sensitivity sweep 後仍 RED → 屆時 PA 補新 RCA + 建議 wording 修訂。

**A4-C tombstone precedent 比較**：A4-C = feature shape root cause（BTC 1m + xcorr）被 RCA 證偽；8b RED = 信號 trigger gate 過嚴 + panel 短暫，gate parameter 還沒 sweep → **不能立即 tombstone**。

**Phase 1b deploy 阻塞性**：governance argument 是 systemic alpha-first priority discipline；不耦合 8b/8c 直接 alpha 進度。維持原 AMD §8 三閘 strict AND，Phase 1b 等三閘解時程被 P0-EDGE-1 closure 主導（不是 8b 主導）。

**架構教訓 29**：Stage 0R RED 判定要區分「sample insufficient」vs「signal failure」— 看 baseline 採樣是否同樣稀少。本次 baseline pooled n=39,181 vs strategy primary n=7 = 5,597 倍差，即可確認**strategy gate self-imposed scarcity 是主因**，panel grow 1-2d 不會解。

**架構教訓 30**：trigger gate 0.0017% rate 是 **alpha hypothesis design choice**，不是 panel data limitation；spec v0.3 patch 應允許 gate sensitivity sweep 探索 trade-off frontier（trigger rate vs power），不是 dogmatic stick to v0.2 fixed params。preregister sensitivity sweep K_new 累加 (K_total 增加 ~3-4 倍, sr_benchmark 仍 ≈ 4.1, 影響可忽略)。

**16 根原則合規 A 級**：read-only RCA + governance recommendation；不跑 strategy / 不改 spec/AMD / 不接 runtime / 不訂 WS topic / 不寫任何 production code。

**Confidence**:
- HIGH for RED 性質判定 (baseline n=39,181 vs primary n=7 對照硬數據)
- HIGH for trigger rate 0.0017% 計算 (411,840 candidate bars math)
- HIGH for panel grow 1-2d 不解 spec floor 推斷 (linear extrapolation)
- HIGH for sibling work incorporation (確認 dirty file 無重疊 + 2 sibling 報告引用)
- MEDIUM-HIGH for Option A 推薦 (governance discipline + cost-benefit)
- MEDIUM for trigger gate sweep 是否能找 n_eff>50 cell (取決於 funding skew alpha 真實 power，spec v0.3 round 2 才能 empirical 確認)

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_stage0r_red_rca_and_next_step.md`

## 2026-05-16 — Wave C-3: phys_lock Live Enable AMD DRAFT prep

**Trigger**：main session 派 Wave C-3 — 寫 phys_lock live enable AMD draft（risk_config_live.toml 加 `missing_edge_fallback_bps = 10.0` override 啟 phys_lock Gate 1 解除 fail-safe Hold）；對應 AMD-2026-05-15-02 v0.4 §4 DEFER 立場的後續 follow-up。

**Mode**：純 DRAFT，**不自動 land**；不修改任何 runtime / config / TOML；不入 SPECIFICATION_REGISTER；pending operator sign-off + Phase 2b LiveDemo PASS + QC counterfactual gate 三條件。

**核心關鍵事實**：
1. `risk_config_demo.toml:199` 已 override `missing_edge_fallback_bps = 10.0`（EDGE-DIAG-1 對照實驗）→ demo Gate 1 pass → 7d 86 fires
2. `risk_config_live.toml` 無 override → Rust default `-10.0` (`exit_features/v2.rs:174`) → `effective_edge=-10 < min_net_floor_bps=5.0` → live Gate 1 永久 Hold → 7d 0 fires（by design fail-safe）
3. 設計初衷：`feedback_demo_loose_live_strict_policy.md` demo 放寬不要連帶放寬 live；本 AMD 是 carve-out exception 路徑
4. AMD slot 編號：placeholder `2026-05-XX-XX` 留 operator 確認時補實；slot 邏輯 per `SPECIFICATION_REGISTER.md`（當前 max slot 2026-05-15-02）

**AMD draft 結構（10 sections）**：
- §1 Executive Decision：phys_lock = profit-protection（α_holding truncation policy，per QC §6 transaction cost economics framing），**非 risk-bypass 也非新 alpha source**
- §2 Scope：唯一改動 = `risk_config_live.toml [exit].missing_edge_fallback_bps = 10.0`；§2.2 enumerate 不改清單（13 項：min_net_floor / min_hold_secs / giveback_* / shadow_enabled / paper / close-maker-first whitelist / 8-gate 邏輯 / H1-H5 / Decision Lease / Guardian / StopManager / demo config / 不改 audit pathway）
- §3 Pre-enable Conditions 6-gate：(3.1) Phase 2b LiveDemo PASS / (3.2) QC counterfactual analysis demo 86 fires PASS / (3.3) operator 顯式 sign-off / (3.4) P0-EDGE-1 status PA+QC+FA 三方聲明 / (3.5) AMD-2026-05-15-02 v0.5 §4 patch / (3.6) AMD slot 編號實裝
- §4 Risk Assessment 5 items：one-flag-per-phase 違反 (MEDIUM) / P0-EDGE-1 alpha-deficient regime 鎖 noise (HIGH) / demo-loose-live-strict 政策履行 (LOW) / demo/live regime 行為對稱性假設 (MEDIUM) / ArcSwap 熱重載 (LOW)
- §5 Counterfactual Analysis（QC §6 mandate 核心）：5.1.1-5.1.5 evidence packet 條目；5.2 PASS/FAIL criteria（median(A-B) < -2bps + 95% one-sided CI 上限 < 0 + sensitivity sweep 穩健 + per-symbol 70%+ directional positive）；FAIL → 永久 REJECT
- §6 Rollback Path：6.1 hot rollback ArcSwap 1 tick / 6.2 5 triggering conditions / 6.3 無 schema migration
- §7 16 原則合規：16/16 PASS or PASS-with-mitigation；3 CONDITIONAL (#5 生存 / #6 失敗收縮 / #13 AI cost 感知) 由 §3 + §5 + §6 mitigate；0 BLOCKER
- §8 9 不變量：9/9 PASS；0 BLOCKER；本 AMD 不削弱任何 fail-closed 邊界
- §9 Approval chain：PA DRAFT ✅ / QC FA MIT BB ⏳ / PM ⏳ / Operator ⏳；不接受快速通道
- §10 變更歷史 v0.1 DRAFT 2026-05-16

**估算影響**：demo 86 fires / 7d / 25 symbols ≈ 0.49 fire/symbol/day → live 25 sym × 30d ≈ ~370 fires/月（注意：依賴 demo/live regime 行為對稱性假設，未必成立 per §4.4）

**Side-effects 分析（純 DRAFT，0 runtime/code change）**：
- 對 RustEngine / IPC / GovernanceHub / 5-Agent / 風控 = 0
- 對 close-maker-first AMD-2026-05-15-02 Phase 1b IMPL = 0（並行 follow-up lane；本 AMD 啟用後 phys_lock fires 自動進 close-maker-first 白名單 maker-first 路徑）
- 對 Mac/Linux runtime / paper / demo / live = 0
- 對 healthcheck = 0

**16 根原則合規（本 PA 工作）**：A 級（16/16 + 硬邊界 0 觸碰；純 draft governance 文件，0 runtime / config / TOML mutation）

**Confidence**:
- HIGH for §1-§3 governance framing（mirror AMD-2026-05-15-01 / AMD-2026-05-15-02 template + QC §6 + FA §6 立場合成）
- HIGH for §4 5 risk items（QC + FA round 識別後 PA 補風險評級）
- HIGH for §7-§8 16 原則 / 9 不變量逐條 mapping（標準 audit table 結構）
- MEDIUM-HIGH for §5 counterfactual analysis criteria（median < -2bps + 95% CI + sensitivity + per-symbol 70%+ 是 PA 提案值，待 QC review 確定終值）
- HIGH for §6 rollback path（純 TOML hot-reload + ArcSwap snapshot，已驗於 close-maker-first Phase 1a entry-side）

**架構教訓 29**：「one-flag-per-phase」principle 在 live surface 改變上特別嚴；本 AMD §3 Gate 3.1 強制 Phase 2b PASS 為前置 = 保證兩個 live surface 變更（close-maker-first + phys_lock）不重疊觀察窗，防止歸因混淆。新 surface change 設計時必先盤點當前 live in-flight 變更，必要時序列化 enable timing。

**架構教訓 30**：放寬 fail-safe（i.e. 改 missing_edge_fallback_bps 從負值到正值）必走 counterfactual evidence path，**不接受推理性論證**。即使 demo 觀察到 86 fires 是「pre-existing positive evidence」，counterfactual A-B 對比才能確認鎖利 net 改善 vs 反向（鎖 noise 反而劣化）。pre-enable Gate 不是 yes/no 設計，是 evidence-driven binary。

**Report path**: 本 PA 工作的 AMD draft 即 deliverable，位於 `/Users/ncyu/Projects/TradeBot/srv/docs/governance_dev/amendments/2026-05-XX-XX-phys-lock-live-enable-draft.md`；不寫額外 summary report（per system instruction「Do NOT Write report/summary/findings/analysis .md files. Return findings directly as your final assistant message」）。

## 2026-05-16 — W-AUDIT-8b spec v0.2 → v0.3 patch (sensitivity sweep) + Round 2 run plan

**Trigger**：main session 派 W-AUDIT-8b Option A — round 1 RED 後 spec v0.2 → v0.3 patch（加 trigger gate sensitivity sweep z=1.0/1.2/1.5/2.0 並排 4 cells）+ 規劃 round 2 Stage 0R rerun（panel grow naturally to ≥ 7d, calendar +1.02d defer）。

**Mode**：Phase 1 純 spec patch（land at write time）+ Phase 2 deferred run plan（panel 不夠不立即跑）。**不修** runtime / TOML / RiskConfig / engine env / authorization / AMD §8 wording。

**核心關鍵事實**：
1. Round 1 RED RCA 判 65% signal failure 主導 + 35% sample 邊際次要：5.72d 內 411,840 candidate 5m bar 只 7 個過 gate（trigger rate 0.0017%）；baseline pooled n_eff=6,530 揭示 -16.91 bps 負 edge
2. Panel current 5.98d span (2026-05-10 23:30Z → 2026-05-16 18:56:53Z)；funding 205,051 rows, OI 205,821 rows；25 sym uniform；grow rate ~34,300 rows/day
3. K_prior empirical：strict `funding_skew%` filter = 0; relaxed `funding%` filter = 9 (`funding_arb` retired ledger residue)
4. spec v0.3 patch：+306 行；K_new_min 4050 → 5400 (+33%)；z gate 從 v0.2 fixed 3 cells (1.5/2.0/2.5) 擴 v0.3 4 cells (1.0/1.2/1.5/2.0)
5. z_strict (2.0) cell-level n_eff floor stratified 30/15/75 作 diagnostic only；其餘 z cell 維持 v0.2 100/50/300
6. Wilson CI 95% per (z_cell, branch, symbol) cell；不強制進 eligibility floor，留 PA verdict round 3 zoom-in 評估

**Spec v0.3 structure（7 子節）**：
- 起源與動機（RED RCA 結論 cite）
- Sweep Methodology（4 z cells + 4-cell × 2-branch × per-symbol output matrix + pre-empirical assertion magnitude）
- K_total per-cell minimum（K_new_min 5400 + z-stratified n_eff floor）
- Output Format Spec（4 JSON blocks: sweep_per_z_cell / sweep_per_symbol / best_primary_cell_per_z_branch / sweep_cross_z_comparison）
- Wilson CI Computation（公式 + 用途 3 維）
- Pre-rerun Linux PG Empirical Query Template（5 SQL + 4 assertion gates）
- Output Storage Audit + 接受 / Reject 條件（ACCEPT / OPEN / REJECT 3 paths）

**Round 2 Wave 4-B Run Plan（8 steps, ~2-2.5 worker-days）**：
- Step 0 PA spec patch land ✅ DONE
- Step 1 PA Linux PG empirical assertion gate（panel ≥ 7d + sym=25 + K_prior strict=0 + cycles ≥ 21）
- Step 2 PA Mac/Linux source sync verify
- Step 3 E1 IMPL sweep logic patch（metrics.py + report.py + smoke.py + entry wrapper `--sweep` `--z-cells`）
- Step 3a E2 + A3 對抗審（Wilson CI 公式 + sweep loop + z stratification）
- Step 3b E4 regression
- Step 4 E1 跑 round 2 sweep
- Step 5 PA + QC + MIT + BB 並行 review
- Step 6 PA verdict report
- Step 7 PM sign-off

**Calendar ETA**：panel ≥ 7d 達成 2026-05-17 23:30Z（calendar +1.02d）；Phase 2 dispatch 觸發點 2026-05-18 00:30Z（+1.06d）。

**Predicted round 2 verdict**：HIGH probability RED（即使 z=1.0 ~10x trigger 升 70-100 signals 預期 pooled n_eff 仍 << 300 floor）；z_relaxed closest to marginal but pooled n_eff ~15-25 not enough。

**Decision tree**：
- ACCEPT → Stage 1 Demo micro-canary design Wave；AMD wording 不修
- OPEN → round 3 zoom-in vs archive tombstone；AMD 暫不動
- REJECT → PA 補 RCA + 建議 AMD §8 condition 3 wording 修訂為「W-AUDIT-8b Stage 0R passed OR a formal tombstone amendment archives W-AUDIT-8b after exhaustive sensitivity sweep」

**Side-effects 分析（Phase 1 純 spec patch）**：
- 對 RustEngine / IPC / GovernanceHub / 5-Agent / 風控 = 0
- 對 close-maker-first AMD-2026-05-15-02 Phase 1b IMPL = 0（並行 lane）
- 對 Mac/Linux runtime / paper / demo / live = 0
- 對 healthcheck = 0
- 對 panel.funding_rates_panel / panel.oi_delta_panel / learning.strategy_trial_ledger = read-only
- 對 sibling Wave 2-4 + WP-13 leftover IMPL = 完全與本 spec patch 無重疊

**16 根原則合規**：A 級（16/16 + 硬邊界 0 觸碰 + DOC-08 N/A + AMD §8 wording 不破）

**Confidence**:
- HIGH for §1 起源與動機（直接 cite round 1 empirical RCA）
- HIGH for §2 Sweep Methodology + §3 K_total（K_new_min 5400 公式直接 derive；z stratification 預留 z_strict 30/15/75 floor 是 PA 提案待 QC sign-off）
- HIGH for §4 Output Format（4 blocks JSON schema 完整定義）
- MEDIUM-HIGH for §5 Wilson CI（公式 / 用途 / promotion gate optional addition 是 PA 提案）
- HIGH for §6 Pre-rerun Linux PG empirical query template（已 PA solo 跑 verify）
- HIGH for §7 接受 Reject 條件（ACCEPT / OPEN / REJECT 3 paths 對齊 RCA §8 conditional amendment 觸發點）
- HIGH for Round 2 Run Plan 8 steps + decision tree（mirror round 1 run plan 結構）

**架構教訓 31**：spec patch 不接受「v0.2 失敗就 tombstone」結論，必先盤點失敗類型（signal failure / sample insufficient / parameter family unexplored）才決定下一步。8b round 1 RED 是 signal failure 主導 + parameter family unexplored → v0.3 sensitivity sweep 是合理升級而非 wasted effort；對比 A4-C tombstone（feature shape 被 RCA 證偽）的 root cause 不同。

**架構教訓 32**：Trigger gate sensitivity sweep 的 K_total 增加量必預先公式化（v0.3 K_new_min 5400 vs v0.2 4050）並 cite 對 DSR sr_benchmark = √(2 ln K) 變動極小（4.07 → 4.14）— 否則 sweep 看似擴大 multiple testing 風險，實質 sr_benchmark 不變因 ln 對 K 敏感度低。Adversarial review 必驗此 sanity check 不被 over-conservative interpretation 卡掉。

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_spec_v03_sensitivity_sweep_patch.md`

---

## 2026-05-16 phys_lock Live Enable AMD v0.2 Consolidated Patch

**任務**: AMD DRAFT v0.1 → v0.2 consolidation integrating 4-agent (QC+FA+MIT+BB) short re-review 2026-05-16 verdicts。23 items (11 must + 12 should + 3 NTH/cosmetic)。

**整合結果**:
- 11 must-fix 全收口 (QC-MF-1/2 / FA-MF-1 / MIT-MUST-A/B/C/D/E/F/G / BB-PL-1)
- 12 should-fix 全收口 (QC-SF-1..4 / FA-SF-1..4 / MIT-SH-H/I / BB-PL-2/3)
- 3 NTH/cosmetic 全收口 (QC-NTH-1/2 / FA-Cosmetic)
- 0 BLOCKER, 0 unresolved item

**最關鍵修正 (MIT-MUST-E)**: AMD 全篇 schema 命名 bug — `exit_features.physical_decision_logs` (此表不存在) → `learning.exit_features WHERE exit_trigger_rule LIKE 'phys_lock_%' OR exit_source='Physical'`。Linux PG empirical verify: V029 hypertable + V086 close_reason_code enum + Rust writer `database/exit_feature_writer.rs:123` INSERT INTO `learning.exit_features` 全證實 schema 命名正確；v0.1 文檔錯字若不修 = E1 IMPL 撈不到資料 + counterfactual evidence 不能跑。

**新增 §5.3 Phase 2c LiveDemo Counterfactual Verification (QC-SF-3 BLOCKER-level)**: enable 後 7d post-enable continuous observation；per-fire 即時 counterfactual replay against same-instant **live order book snapshot** (不是 demo replay)；累積 ≥30 fires after live enable 再判定 net positive；< 30 fires 延長至 14d 上限；PASS = 重跑 §5.2 6-criterion；FAIL = rollback + AMD 永久 REJECT。這是 QC round-2 §6 數學論證 + alpha-deficient regime risk 最後一道防線。

**結構升級**:
- §3 gate stack 6→7 (Gate 3.7 = Linux empirical + Mainnet 7 prereq cross-ref 合併新 gate + 子表)
- §5 evidence packet 5→7 條 (5.1.6 regime stability + 5.1.7 MDE/power)
- §5.2 PASS criteria 4→6 條 (Wilson CI lower bound + MDE/power + BH-FDR + per-symbol conditional)
- §6 加 §6.4 close-maker-first 互動 + §6.5 forensics row retention
- §1 framing 補 Sharpe 數學條件 σ_reduction × Sharpe_baseline > μ_reduction
- §4.4 split (BB-PL-2): 觸發層 LOW + close dispatch 層 MEDIUM (already covered)
- §4.6 future funding alpha hook (QC-NTH-1) future advisory
- §6.2 rolling 7d 偏離取代 2σ daily (QC-NTH-2)

**Sibling concurrent work**: Phase 1b E1 round 2 補 Worktree B (dirty Rust files 14 files modified)；本 v0.2 AMD patch 純文檔，0 Rust touch；commit isolation clean。

**架構教訓 33 (CRITICAL schema bug)**: AMD draft 引用 DB schema 必先 Linux PG empirical verify table name + column 存在；v0.1 4-agent review 通過 QC + FA + BB 三 agent，**唯有 MIT 因 DB schema audit 職能 catch 命名 bug**。多 agent adversarial review 確實能補單 agent 盲點 — MIT 不在 review chain = bug ship 至 IMPL。

**架構教訓 34 (Phase 2c BLOCKER-level)**: 放寬 live fail-safe 的 AMD 設計 = 對抗性 review 必問「demo PASS 是否充分代表 live regime」；QC-SF-3 (BLOCKER-level) Phase 2c 是 first-time-in-AMD live-side counterfactual gate；不是 pre-commit gate，是 post-enable observation gate；但結構上 BLOCKER-level 等同 pre-commit gate (FAIL → rollback + AMD 永久 REJECT)。Demo-loose-live-strict policy 履行的標準範式。

**Confidence**: HIGH for v0.2 結構 (4-agent 100% reflected, schema verified, gate stack mathematical consistency)；MEDIUM for Phase 2c 7d observation window 是否足夠 (sample size ≥30 fires 是統計 power 平衡 sample collection 速度的 PA judgment call)。

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--phys_lock_amd_v02_consolidated_patch.md`

---

## 2026-05-16 — W-AUDIT-8b Round 2 Tooling Prep (Phase A Design Packet)

**Task**：Phase A tooling prep for v0.3 sweep + Phase B scheduled rerun plan（panel ≥ 7d 啟動）
**Outcome**：PA DESIGN DONE — Phase A E1 派發 packet 設計完成 + 對抗審核 cover spec 完整 + Phase B 7-gate trigger ETA 2026-05-18 00:30 UTC

### 關鍵決策

1. **Push back operator instruction**：拒絕「PA 親自 IMPL」 reading of task prompt（PA 角色定位「不寫功能代碼」+ `feedback_impl_done_adversarial_review.md` 高風險 IMPL 必走 E1 IMPL + A3+E2 對抗審核）。建議走 PA design → E1 IMPL → A3+E2 並行對抗 → E4 regression → PA verdict 鏈
2. **架構抉擇 Option B**：將 `compute_stage0r(z_grid=)` 加 kwarg + 新加 `compute_stage0r_sweep()` wrapper（vs Option A 4× independent call 或 Option C deep refactor）；wrapper 隔離既有 round 1 行為（v0.2 reproducibility 保），sweep 在外層增量
3. **SQL 不動**：z 過濾在 Python 層做（funding_zscore_25sym SQL 已給 raw value）；3 Python 檔改動 +420~580 LOC，0 SQL / 0 schema / 0 config
4. **Pre-rerun assertion gate 不放 Python tooling 內**：由 PA Phase B Step 6 solo 跑 Linux PG empirical 5 queries 驗（per `feedback_workflow_audit_chain.md` PA 親驗 CRITICAL 條件）；tooling 純 read-only audit packet emitter
5. **Backward-compat critical**：sweep mode K_NEW_MIN_V03 = 5400 + STRATEGY_VARIANT v0.3 升級；non-sweep mode K_NEW_MIN = 4050 + STRATEGY_VARIANT v0.2 保留（round 1 reproducibility bit-identical regression test）

### Linux PG empirical 2026-05-16 19:18Z

- panel funding 205,526 rows / 25 sym / **5.823d span** (尚 <7d)
- panel OI 205,XXX rows / 25 sym (parity 已 met)
- K_prior strict funding_skew = 0 ✅
- distinct cycles = 31 ✅ (> 21 floor)
- Phase B trigger ETA = 2026-05-17 23:30 UTC + 1h margin = **2026-05-18 00:30 UTC**（+1.18d from now）

### 對抗審核 cover spec

- E2 7 軸（backward-compat / K_NEW_MIN / sweep schema / Wilson CI / leak-free / variant / CLI repro）
- A3 5 軸（Wilson CI formula / z-stratified n_eff / eligibility tree / pre-empirical magnitude / monotonic_drop）
- E4 5 regression（single-z PASS / sweep 4-z PASS / Wilson bench / JSON round-trip / z_grid backward-compat）

### 高風險警告 3 點

1. Wilson CI 公式 small-n numerical stability（n<5 + n_eff/n close to 0/1 → inner < 0 guard + clamp [0,1]）
2. K_NEW_MIN dynamic vs backward-compat（sweep=5400 / non-sweep=4050 不能誤合）
3. strategy_variant 升 v0_3 一致性（sweep packet override only / module-level constant 保 v0_2 / non-sweep packet 不誤升）

### 16-root + 硬邊界 compliance

A 級 — 16/16 完全合規 + 0 硬邊界觸碰 + DOC-08 N/A + AMD-2026-05-15-01/02 wording 不觸

### 架構教訓 33

PA 任務 prompt 字面 reading 可能誘導 PA 越界 IMPL；遵循 PA profile.md §"硬約束" + `feedback_impl_done_adversarial_review.md` 高風險 IMPL 必走 sub-agent 對抗審核鏈，是 PA 主動 push back 的正當理由。不採「task prompt 寫了就做」單方面 reading；採「task prompt 寫 + PA 角色定位約束 + governance feedback rules」三方對齊判定。

### 架構教訓 34

Sweep wrapper pattern 在 metrics 重型 monolithic function (1162 LOC `compute_stage0r`) 重構時是低風險選擇：既有 fn 加 1 kwarg + 新 wrapper 在外層 aggregate，避免 deep refactor 引入 regression risk。Trade-off：4× baseline 重算 (浪費 ~10% runtime) vs zero regression risk。Audit packet emitter 場景下 runtime cost 可接受。

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_round2_tooling_prep.md`

---

## 2026-05-18 — W-AUDIT-8c S0R-1 HIGH-2 boundary leak arbitration

**Trigger**: E2 round 1 review HIGH-2 指 PA design §2.3 line 261 (`>=`) 與 §8.1 line 653 (`quiet_window=0 special case`) 自相矛盾 + 具體 leak scenario：bucket_end_ts=12:34:00 整分鐘 + quiet=0 → entry_mid=(open+close)/2 含 60s post-event reversion → gross_bps systematic 低估。

**事實核查**:
- `market.klines.ts` = **bar open time** (V002:122)，no `market.klines_1m`（PA design 寫 phantom table，E1 已 catch deviation #2）
- 8b precedent 用 exact equality (`close_ts_ms = signal_ts_ms + 900000`) + close-to-close，不能直接 mirror 給 8c
- E1 follow PA 字面寫 `>=` + `(open+close)/2`，**E1 SQL 沒錯，PA design 有 leak 設計**

**裁決 = D** (而非 E2 列的 A/B/C/d-variant)：
- entry_mid + exit_mid 從 `(open+close)/2` 改 `open` only
- `>=` 維持（boundary case 用 bar.open ≈ event time price，無 leak）
- `quiet_window_sec=0` 維持合法 sweep cell（K_total 11_664 不變）
- 欄位名 `entry_mid`/`exit_mid` 保留（下游 Python contract 鎖定）

**為什麼 D 不是 B (改 `>`)**: B 在 boundary case 強制延後 1 根 bar → entry 漂到 event+60s，反而更糟；non-boundary case B 與 A 完全相同（兩者都選下一根）。

**為什麼 D 不是 C (強制 +1m)**: C 把 quiet=0 cell hard-fold 成 quiet>=60，sweep 失去信息。

**為什麼 D 不是 8b close-only**: 8b horizon 15-60m close-to-close gap 影響小；8c horizon 1-15m close-to-close 等同自動加 60s implicit quiet，破壞 sweep 設計。

**Lesson — PA design SOP**: 涉及 sub-bar event timing + bar price aggregation 時，design 階段必須走「event 假設落在 bar 開瞬間」boundary thought experiment。`(open+close)/2` 是 generic mid-price 慣例但在 1m bar + sub-minute event 邊界**會洩漏 60s post-event 價格進進場價** — 不是 lookahead bias 而是 entry-fill underestimation（systematic 保守誤差），對 cost_edge_ratio 接近 cost_bps 的 marginal cell 影響顯著。

**Lesson — PA design wording**: §8.1 line 653 「`MUST be ≥ ... quiet_window=0 special case test for boundary correctness`」過於精簡導致 E2 解讀為自相矛盾；設計意圖實為「`>=` 但要 review 邊界情況」。Future PA design 涉及 boundary semantic 必須完整句子描述意圖，不能依賴 reviewer 上下文推斷。

**正交 confirmation**: 此裁決與 CRIT-1 (notional_pct_floor gate 缺漏) / CRIT-2 (sibling consistency) / HIGH-1 (sentinel-split contract drift) 完全正交，E1 rework round 可一併處理。

**Report path**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--w_audit_8c_s0r_1_high_2_boundary_leak_arbitration.md`

---

## 2026-05-18 — Phase 1b Calibration Harness 3 SHOULD-FIX Decisions

**Context**: E2 review 907ab778 `APPROVE-CONDITIONAL` + E4 regression PASS 7/7 + merge `8d8a0123`，3 SHOULD-FIX 不阻 merge 但阻 sweep run 解讀。

**3 Decisions**:
- #1 Block 4 dedupe → **(b) Accept with PA-side dedupe SQL in cell selection report** (Block 1-3 baseline = Block 4 D=50 cells 3 對 duplicate)
- #2 maker_fill_rate denom drift → **(a) Spec amend v0.1 → v0.2** (expanded denom `n_attempts - sum(all n_skipped_*)`，反映真實 fillable population；spec drift 是審計鏈污染源必須補)
- #3 adverse_proxy=None fail-closed → **(c) Pure accept + selection-guide note** (PA 在 FAIL pool 用 SQL `WHERE adverse IS NULL` 分流 data_missing_FAIL vs cell_quality_FAIL)

**ETA**: 0 IMPL；~35 min total (spec patch 10 min + PA selection 報告額外 25 min)；sweep production run 可立即啟動。

**對比 fix-in-IMPL all 3**: ~0.75 pd turnaround (E1 ~120 LOC + re-E2 + re-E4 + re-merge)，sweep run 被阻 ~6 hr。**accept-with-caveat 救 6 hr window**。

**General lesson — Spec drift handling**:
- IMPL 比 spec 更語意正確（如 expanded denom 更反映 fillable population）→ **spec 反向 amend，不 IMPL revert**。spec is documentation authority，IMPL 升級 spec 比 spec 凍 IMPL 更乾淨。
- IMPL 過保守導致誤判（如 None adverse → FAIL）→ **PA review SOP 補 SQL，不 IMPL relax**。fail-closed 對齊 root principle §二 #6，下游 PA 手動 carve-out 比 IMPL 加 INDETERMINATE state 成本低。
- duplicate cells 是 spec design oversight → **下游 PA dedupe SQL，不 IMPL aggregate_summary 內加 dedupe**。raw output 保 baseline 完整 traceability，top-2 排序前 PA 套 DISTINCT ON 即可。

**Report path**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--phase_1b_calibration_should_fix_decisions.md`

## 2026-05-18 Phase 1b Calibration Sweep — SD-1/SD-2 Anomaly RCA

**Trigger**: PA cell selection report `2026-05-18--phase_1b_calibration_cell_selection_report.md` §5.2 / §5.3 留 2 anomaly 待 verify。

**SD-1 (A axis offset_bps dead variable) — VERIFIED dead, spec design intent**:
- 81 cells × 4 A axis values (0.5/1.0/2.0/3.0) 在所有 (B, C, D) combinations 下 identical 至 7 位小數 fill rate / fee_saving
- Python port `phase_1b_maker_price.py:104-152` `compute_post_only_price` line 117 注釋明文 `fallback_offset_bps` 不參與 price 計算
- Rust source `rust/openclaw_engine/src/strategies/common/maker_price.rs:155-356` 同樣 — `fallback_offset_bps` 只在 warn log 出現 (line 276/297/315/332/350)，0 個在 price formula (line 305-336)
- 真實 limit_price = BBO ± buffer_ticks × tick，strict-passive 設計，從不偏移 bps
- 將原 cell selection report §5.2 probability 60/25/15 修正為 100/0/0

**SD-2 (PS family 100% skip) — VERIFIED no-sample, data shortage**:
- 7 天 + post-restart seed pool 共 54 fills：grid_close_short 49 / phys_lock_gate4_giveback 4 / ma_reverse_cross 1 / **phys_lock_gate4_stale_roc_neg 0**
- `phase_1b_sweep_cells.py:49-60` FAMILY_EXIT_REASONS["phys_lock_stale_roc_neg"] = ["phys_lock_gate4_stale_roc_neg"] 唯一 element，whitelist routing 邏輯正確
- 26 cells × 54 attempts × 0 match = 100% family_mismatch skip 是 data shortage 自然結果，非 router bug
- phys_lock_gate4_stale_roc_neg 觸發條件嚴格（stale + roc_neg 雙 sub-gate），自然 distribution 罕

**Action**:
- 兩 anomaly 都 **不需 E1 IMPL fix**（0 個 IMPL bug）
- 只需 spec v0.3 amend note 記錄設計約束 + SD-2-future re-sweep trigger monitoring
- 24h pilot 不阻塞 — Cell A G-AB-01-C90 仍 valid

**Cognitive lessons**:
- **PA cell selection report 對 hypothesis probability 估計過鬆**（60/25/15 → 100/0/0）：未來 PA review SOP 應在 surface anomaly 時即補 call-path grep proof，避免下游 SD report 重做 evidence work；本次 ~5 min grep 就 confirm 真實 root cause
- **SQL evidence 必 ssh trade-core 用對的 .pgpass credentials**（trading_admin/trading_ai，password 在 `~/.pgpass`，DSN 用 `OPENCLAW_DATABASE_URL` env var 路徑 Mac 上不存在；Linux runtime 用 `~/.pgpass` peer auth）
- **strict-passive maker design 的 dead parameter**：Rust signature 對齊舊 spec but IMPL strict-skip 後 fallback_offset_bps 變 vestigial；calibration sweep 沒注意到這 IMPL detail → 設計 4-axis cartesian product 有 1 dead axis × 75% redundancy；spec 與 IMPL 之間需有 dead parameter audit pass

**Report path**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--phase_1b_calibration_sweep_anomalies_sd_report.md`
