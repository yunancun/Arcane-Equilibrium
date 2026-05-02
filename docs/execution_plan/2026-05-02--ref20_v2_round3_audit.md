# REF-20 V2 第三輪 7-Agent 冷酷審核總結

**日期：** 2026-05-02
**狀態：** Audit 結果文件，與 V2 並列存放，**不直接修改 V2**
**審核對象：** `docs/execution_plan/2026-05-02--ref20_paper_replay_lab_dev_plan_v2.md`
**前置參照：** `docs/execution_plan/2026-05-02--ref20_paper_replay_lab_dev_plan_draft_v0.1.md` / `..._v1.md` / `..._v1_round2_audit.md`
**Owner：** PM
**派出 agent：** CC / PA / FA / QC / MIT / A3 / E3 並行（獨立、無口徑協調）

---

## 0. TL;DR — 7-Agent 第三輪投票

| Agent | Round 1 | Round 2 | **Round 3** | 變化 |
|---|---|---|---|---|
| **CC** | B-（Conditional） | B（Conditional） | **B（Conditional Approve）** | ↔️ 持平，3 MUST + 3 SHOULD-FIX |
| **PA** | 🔴 阻塞 | Conditional | **Conditional Approve** | ↔️ 持平，5 條件全補才 APPROVE |
| **FA** | Conditional | Conditional | **Conditional Approve** | ↔️ 持平，3 必補 / 4 可延 |
| **QC** | 🔴 REJECT | P0-P2 通 / P3+ block | **P0-P2 通 / P3a 仍 block / P3b/P4/P6 解除（V2.1 補丁）** | ⬆️ 大幅 unblock，僅 P3a schema 升級擋 |
| **MIT** | 🔴 阻塞 | 🔴 **強 REJECT**（4 BLOCKER） | **Conditional Approve → V2.1**（4 BLOCKER 全解，6 條件） | ⬆️⬆️ **判定大轉**，4 BLOCKER 全閉合 |
| **A3** | C 5.5 | REJECT P1 | **REJECT V2 進入 P1 / Conditional P0 commit** | ↔️ 持平，UX subdoc 仍須 dedicated |
| **E3** | 🔴 CRIT × 3 | Conditional P0 | **Conditional Approve P0 commit** | ⬆️ 6/9 closed，1 HIGH 仍開（HIGH-04 quota） |

**整合判定**：V2 達到「**距 P0 commit 一步之遙**」狀態。**5/7 agent 同意 V2 進 P0 commit（Conditional）**，僅 A3 拒絕進 P1（不擋 P0）+ MIT 要求 V2.1 minor patches 先過。Round 2 → Round 3 進步幅度遠大於 V1 → V2，主因是 PM 把工程細節（HMAC 完整參數 / DDL CHECK / 5 數值閾值 / regime detector / bootstrap CI）全部補進 V2。

**剩餘阻塞集中在 6 個共識點**（≥3 agent 同源），全部是「V2 文字方向對但工程細節不足」，可在 V2.1 minor patch 修補（估 ≤1 sprint）。

---

## 1. 共識 V2.1 必補（≥3 agent 同源，擋 P0 commit）

| # | Finding | 來源 agent | 修法 |
|---|---|---|---|
| **R3-1** | **manifest_jsonb 內欄位必須拉成物理 column**（calibration_train_window / oos_label_window / candidate_window / total_candidates_K）：runtime validator 只能 parse JSONB 不能 SQL `EXCLUDE USING gist (tstzrange OVERLAPS)` 拒重疊；race condition 下重疊會漏 → P3a hard-block 未實質解 | QC #2 + MIT #3 + PA #五 + FA #2 | §3.1 `replay.experiments` 加 6 物理 timestamp/int column；validator 改 SQL EXCLUDE constraint |
| **R3-2** | **既有 `mlde_shadow_recommendations` row retrofit SQL 缺**：V2 §3.2 寫 retrofit 三步原則但未列具體 backfill SQL；NULL constraint 加上去就崩 | PA #四 + MIT #2 + CC N-1 | V2.1 §3.2 加：`UPDATE learning.mlde_shadow_recommendations SET evidence_source_tier='real_outcome' WHERE source IN ('dream_engine','ml_shadow','opportunity_tracker',...);` 完整 producer allowlist + ambiguous rule + migration_report 表 + owner 指派 |
| **R3-3** | **§3.1 schema 缺 4 個關鍵物理欄位**：`parent_experiment_id`（baseline vs candidate trace 必要，CSCV/DSR 回溯靠它）/ `intent_id`（FK to IntentProcessor 產出）/ `decision_lease_id`（即使 isolated 也應 echo metadata）/ `engine_binary_sha` nullable 行為（Mac smoke 沒 deployed binary） | PA #五 + MIT #3 + QC #1 | §3.1 `replay.experiments` 加 `parent_experiment_id`；`replay.simulated_fills` 加 `intent_id` + `decision_lease_id` + `idempotency_key`；明示 `engine_binary_sha` Mac smoke 寫 NULL 或 'mac-smoke-{git_sha}' |
| **R3-4** | **DB 寫權限收斂未硬化**（PostgreSQL `REVOKE INSERT FROM PUBLIC` + role-based GRANT）：V2 §3.2「Direct ad hoc INSERT to replay-derived evidence is not an accepted path」是 application-level rule 不是 DB enforcement；違反原則 #1 單一寫入口 | CC §3.2 + E3 GAP-01 + MIT §2 | `REVOKE INSERT ON learning.mlde_shadow_recommendations FROM PUBLIC; GRANT EXECUTE ON FUNCTION verify_replay_evidence_and_insert TO replay_runner_role;` 寫進 V2.1 §3.2 |
| **R3-5** | **§1 #4 V### 治理「實作時連續分配」站不住**：2026-05-02 P0 sqlx hash drift incident 教訓 + multi-wave 並行（lease retrofit / FUP-2 / replay）必有 race；治理層解非文字硬編 | MIT #4 + CC N-1 + PA | V2.1 §1 #4 加 PM 集中分配 V### + commit gate（PR 描述列「reserved V###」）+ §3.1 三表 DDL 段強制引用 Guard A/B/C template（CLAUDE.md §七強制） |
| **R3-6** | **P2 啟動前 5 策略 indicator leak-free sweep 為前置 gate**：V2 §1 點 1 反對 round2 C-3 「不禁 IntentProcessor」邏輯成立，但 IntentProcessor 內部 indicator computation 是否全部 leak-free shift(1) 未驗證；bb_breakout F3 RETRACT 教訓在案，其他 4 策略未 sweep；**P2 baseline vs candidate 帶 lookahead bias → 整段方法論失效** | MIT #8（重大盲點） + QC O2 + CC | V2.1 §1 點 1 加前置條件：「P2 啟動前完成 5 策略 indicator leak-free sweep」；audit 產出 `indicator × shift(1) compliance` 表；任 1 策略發現 leak → 全 RETRACT |

---

## 2. PM 反對 round2 三條的論證評估

| Round 2 finding | PM V2 反對 / 改寫 | 第三輪評估 |
|---|---|---|
| **C-3** P2/P2b 不應禁止 IntentProcessor / link Rust 熱路徑 | §6.1 改 isolated no-write replay profile + 5 acceptance proof | **半站得住**（CC + PA + E3 + MIT 共識）：方向對但 acceptance 是事後驗（runtime probe）非編譯期 enforcement；要求 V2.1 加 `IntentProcessor` 內 `replay_profile=isolated` 編譯期 panic 或 runtime fail-closed assert（PA：`#[cfg(feature="replay_isolated")]` cfg gate 設計工作量未列為 P2a 子任務）+ `nm/objdump` symbol grep 補入 P2b acceptance（E3 GAP-05） |
| **NEW-01** Mac smoke 不應全面禁止 S2 public data | §6.1 Mac policy 允許 S2 public + S3 synthetic，禁讀 S0/S1 私有 + 私有 fills | **E3 認為仍站不住**：S2 public klines 開放對，但 Mac 端產生 simulated_fills 帶 Mac 端 strategy_config_sha256 ≠ Linux production deployed sha → 「合法但不可重現」manifest 污染 reproducibility 黃金線；要求 V2.1 加環境變數 `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA=1` + Mac 跑時拒寫 `learning.replay_runs` 只允 dry-run console |
| **C-4** P3+ 不強制新建 crate，可 binary / crate / 獨立 process target | §6.2 三選一「PA/E1 設計決策」 | **PA 認為三選一決定影響 P2a IntentProcessor cfg gate 設計**：必須在 P0 commit **前**定（不是延到 P3 開工）；推薦新 binary `replay_runner`（完全隔離 IPC/DSN/lease），反對獨立 process target（runtime 誤觸主進程 lease 路徑風險） |

---

## 3. Round 2 共識 MUST-FIX（C-1 ~ C-6）解決狀態

| # | Round 2 finding | V2 處置 | 第三輪狀態 |
|---|---|---|---|
| **C-1** | evidence_source_tier DDL CHECK + retrofit 3 步 | §3.2 完整補上 4 enum CHECK + retrofit 3 步 + 3 healthcheck + 寫權限收斂（文字） | ✅ **基本解**（DB role grant 仍須 V2.1 補硬化 → R3-4） |
| **C-2 / M-1** | attribution `≥ 0.7 AND n ≥ 30` | §7.1 `attribution_chain_ok_ratio >= 0.70` + `n >= 200/strategy-window` + `n >= 30/cell` | ✅ **完整解** |
| **C-3** | P2 不 link Rust 熱路徑 | §6.1 isolated no-write profile + 5 acceptance proof | ⚠️ **半解**（PM 反對原句站得住但須補 cfg gate enforcement） |
| **C-4** | P3+ 新建 `replay_engine` crate | §6.2 三選一（new binary / crate / 獨立 process） | ⚠️ **半解**（必須 P0 commit 前定，PA 推新 binary） |
| **C-5 / M-4** | PBO < 0.5 + DSR(K) > 0.95 拆兩 gate | §7.3 兩 gate 完整 + 禁 equivalent + insufficient power → defer_data | ✅ **完整解** |
| **C-6** | manifest signature 算法 / key / rotation / fail-mode 寫死 | §4 完整補：HMAC-SHA256 / 獨立 key path / 90d rotation / server-side / verify order / 4 fail mode | ✅ **完整解**（key retention 上限未定 → E3 GAP-04） |

**結算**：C-1 / C-2 / C-5 / C-6 完整解（4 ✅），C-3 / C-4 半解（2 ⚠️ 須 V2.1 補硬化）。

---

## 4. Round 2 MIT 4 BLOCKER 解決狀態

| # | BLOCKER | V2 處置 | 第三輪狀態 |
|---|---|---|---|
| **M-1** | attribution 鎖 0.7 | §7.1 採納 | ✅ |
| **M-2** | engine_mode='synthetic' / `replay.simulated_fills` 選邊 | §3.1 加 `replay.simulated_fills` 14 欄（路徑 b） | ✅ |
| **M-3** | manifest timeframe enum | §3.1 manifest schema CHECK IN ('1m','3m','5m','15m','1h','4h','1d','tick') | ✅ |
| **M-4** | PBO vs DSR 拆 | §7.3 PBO<0.5 + DSR(K)>0.95 兩 gate + 禁 equivalent fallback | ✅ |

**結算**：MIT 4 BLOCKER **100% 解決**。Round 2 強 REJECT 升 Conditional Approve。

---

## 5. QC P3+ Hard-block 進階要求解決狀態

| # | Round 2 進階要求 | V2 處置 | 第三輪狀態 |
|---|---|---|---|
| 1 | §7 7 條 gate 全給數值閾值 | 5/7 解（attribution / n / stale / embargo / shrinkage / DSR / PBO） | ⚠️ **5/7**（OOS embargo「>=7d minimum」站不住，須改 `max(7d, 2× signal half_life)`；shrinkage 三選一未鎖 decision tree） |
| 2 | §4.1 manifest schema 加 4 欄位 + runtime validator | jsonb 內欄位列出但未拉成物理 column → SQL EXCLUDE 拒重疊不可能 | ⚠️ **未升級**（→ R3-1） |
| 3 | §7.X regime shift detector | §7.4 補 CUSUM ±3σ / Kupiec POF 250 fills / PSR(0)<0.95 | ⚠️ **3 細節未鎖**（freeze 對象 = handoff 還是 calibration / N 窗未寫 / Kupiec 樣本歸屬未指 / negative-edge regime warmup phase） |
| 4 | q10/q50/q90 block bootstrap 1000 iter | §7.2 完整補上 Politis-Romano + 95% CI + n<30 fallback blocked from handoff | ✅ **完整解** |

**判定**：P3a 仍 hard-block（R3-1 物理 column 必補），P3b / P4 / P6 解除 hard-block 但 V2.1 ~5 處 wording patches。

---

## 6. A3 三前置解決狀態

| # | Round 2 前置 | V2 處置 | 第三輪狀態 |
|---|---|---|---|
| (a) | dedicated `ref20_ux_subdoc_v1.md` | §8 點 0 二選一「dedicated subdoc or PR section」，subdoc 未實際附 | ⚠️ **形式解**：A3 拒絕「PR section 等價」（不可獨立反審 / 散在各 PR / 5-Agent MVP 教訓） |
| (b) | Paper submit/cancel 處理決策 | §8 點 2「if retained stay only in Session」 | ⚠️ **半解**：「if retained」留模糊偏向保留，違反 §10 `paper_replay_lab_no_order_submit` |
| (c) | P5 Agents Monitor「collision risk lower」量化 | §9 P5 Entry「LG-2/3/4 frontend merged + 7d frontend stable」 | ✅ **完整解** |

**A3 V2.1 必補**：
1. **dedicated UX subdoc** `ref20_ux_subdoc_v1.md` 必生成（拒絕 PR section 等價路徑）
2. §8 點 2「if retained」改明文「Session 工作區 submitOrder/cancelOrder 必須移除（同 2026-04-24 fake button 清單）」
3. 補 disabled UI mode 三選一 spec / Mode badges 4 維 cognitive overload spec / typed confirm 容錯 4 細節 / Compare 12 指標 viewport spec / Agents Monitor 12-Tab vs sidebar IA 決策 / 術語中文對照表 / `execution_confidence=none` 顯示防認知欺詐

---

## 7. E3 5 GAP 與 1 HIGH 仍開

| # | Finding | 嚴重度 | V2.1 修法 |
|---|---|---|---|
| **HIGH-04 仍開** | manifest TTL / per-actor max active / global storage cap **完全缺**：100 actor × 10/min × 24h = 144 萬 row/天，DoS by manifest spam | HIGH | manifest TTL 30d auto-prune + per-actor max active=20 + global storage cap |
| **GAP-01** | §3.2「ad hoc INSERT not accepted path」是文字規則，無 DB role REVOKE/GRANT enforcement | HIGH | 同 R3-4 |
| **GAP-02** | 同 HIGH-04 | HIGH | 同上 |
| **GAP-03** | §6.1 「TickPipeline 跑 IntentProcessor 不 acquire_lease」假設 IntentProcessor 有 conditional path，但 V2 無 `#[cfg(feature="replay")]` / runtime flag 工程要求 | MEDIUM | 同 PA #二 + MIT C-3 補 cfg gate |
| **GAP-04** | §4「old keys may verify archived manifests until retention expires」「retention」未定 → 永久保留 = rotation 名存實亡 | MEDIUM | retention=180d 硬上限 |
| **GAP-05** | NEW-04 「binary-level enforcement」V2 為 cargo test + runtime probe，非 `nm openclaw_replay_runner | grep acquire_lease` 應為空 | LOW | `nm/objdump` symbol grep 補入 P2b acceptance |

---

## 8. FA §10 17 條 Acceptance 可測性重新分類

| 分類 | 數量 | 條目 |
|---|---|---|
| **可直接寫 SQL probe** | 5 | `replay_signature_verify` / `replay_no_decision_lease_acquire` / `baseline_candidate_disjoint`（待 R3-1 升級後）/ `sample_size>=200` / `stale<=72h` |
| **部分可測（需新表 / 物理欄位）** | 7 | `replay_regime_shift_gate` / `attribution_chain_ok_ratio>=0.7`（OOS window 物理欄位缺 → R3-1）/ cell n>=30 / embargo>=7d / 3 條 verdict gate |
| **不可測（純描述）** | 5 | UX badge / Compare 8 指標 / mode distinction / advisory framing / actionable handoff disabled |

**結論**：17 條僅 ~30% 可寫 healthcheck，未達 round 2 要求「6 條改 SQL probe」。R3-1（物理 column 升級）執行後可從 5 → 12 條可測。

---

## 9. V2 新發現問題（third-round 引入）

### CC 5 條
- N-1：§1 點 4 拒絕硬編 V### → migration 號段 race 風險（→ R3-5）
- N-2：§6.1 P2 baseline = demo snapshot @ experiment_start_ts，Mac vs Linux 跨環境 snapshot 通道未定義
- N-3：§6.2 P3+ 「share IntentProcessor code 但不寫 trading.fills」邏輯路徑 vs 寫入路徑分離未證；違原則 #1 邊界模糊
- N-4：§6.1 forbidden 清單**失敗時行為**未寫（abort? degrade? log only?）→ 違原則 #6 fail-closed
- N-5：原則 #13 cost_edge_ratio ≥ 0.8 完全缺席；Replay/P3+ runner 跑 LLM/ML cost 累積無 gate

### PA 4 條
- 1：`replay.simulated_fills` 缺 `intent_id` / `decision_lease_id` / `idempotency_key`
- 2：`replay.experiments` 缺 `parent_experiment_id`
- 3：`engine_binary_sha` nullable 行為未定
- 4：§4 manifest 三 window 只在 jsonb，runtime validator SQL 查不到（→ R3-1）

### FA 5 條
- 1：§6.1 baseline ambiguity（runtime snapshot 範圍 / Mac vs Linux / disjoint 規則）
- 2：calibration OOS label window 物理 schema 缺
- 3：happy path 業務 flow 6-7 步未寫（E1 接手寫不出端到端業務鏈）
- 4：baseline disjoint 規則未涵蓋
- 5：§9 各 phase Exit 業務驗收缺（缺「demo edge net 改善 X」「N 個 demo handoff 出 verdict」業務指標）

### QC 5 條
- 1：manifest_jsonb 物理欄位 gap（→ R3-1）
- 2：5 策略 negative-edge regime CUSUM 永久 frozen 風險（須加 first 500 fills warmup phase）
- 3：`replay.simulated_fills` row-level CI 欄位 vs aggregate 層次未明
- 4：Kupiec POF 與 PBO sample 重疊（cell-level 樣本不足時競爭）
- 5：embargo 7d 與 demo 21d 衝突（若 V2.1 改 embargo=14d → 須延 demo 累積期至 35d）

### MIT 6 條
- 1：§3.2 retrofit policy 4 點不完整（producer allowlist / ambiguous rule / migration_report 表 / owner）
- 2-5：schema 4 物理欄位（同 R3-3）
- 6：§3.1 缺 Guard A/B/C template 引用
- 7：§10 缺 `replay_routes_use_safe_query_pattern`
- 8：§9 缺 ML maturity 4×5 評級表（P6 deploy = Shadow 不是 Production，避免誤讀）
- 9：5 策略 indicator leak-free sweep 為 P2 前置（→ R3-6）

### A3 5 條
- 1：execution_confidence=none 顯示認知欺詐風險（純文字「無」不夠）
- 2：術語中文對照表全缺
- 3：Mode badge 4 維 cognitive overload spec 空
- 4：Compare 12 指標 viewport spec 空
- 5：Handoff 5 字段 modal layout spec 空

### E3 5 條
- GAP-01 至 GAP-05（§7）

---

## 10. P0 Commit 必補硬清單（V2 → V2.1）

依 7 agent 共識，V2 → V2.1 minor patch 後即可進 P0 commit。必補 12 條：

### 10.1 Schema / DB 層（4 條）
1. **R3-1** §3.1 `replay.experiments` 加 6 物理 column：`calibration_train_window_start/end` + `oos_label_window_start/end` + `candidate_window_start/end` + `total_candidates_K`；validator 改 SQL EXCLUDE constraint
2. **R3-3** §3.1 加 `parent_experiment_id` / `intent_id` / `decision_lease_id` / `idempotency_key` / `engine_binary_sha` nullable 行為
3. **R3-4** §3.2 加 `REVOKE INSERT FROM PUBLIC; GRANT EXECUTE ON FUNCTION verify_replay_evidence_and_insert TO replay_runner_role;` DB role 硬化
4. **R3-2** §3.2 加 `mlde_shadow_recommendations` retrofit backfill SQL 完整 producer allowlist + ambiguous rule + migration_report 表 + owner 指派

### 10.2 治理層（2 條）
5. **R3-5** §1 #4 加 PM 集中分配 V### + commit gate + Guard A/B/C template 強制引用
6. **R3-6** §1 點 1 加前置：「P2 啟動前完成 5 策略 indicator leak-free sweep」audit gate

### 10.3 工程細節（4 條）
7. **PA 三選一決定**：§6.2 P3+ 推薦寫死「new binary `replay_runner`」（PA 推薦），不留三選一空白
8. **PA IntentProcessor cfg gate**：§6.1 P2 加 `replay_profile: ReplayProfile` enum + 5 處 `#[cfg(feature="replay_isolated")]` cfg gate 設計工作量列為 P2a 子任務
9. **CC N-4** §6.1 forbidden 清單失敗時 fail-closed 行為（建議：立即 abort + log）
10. **E3 HIGH-04** §5 加 manifest TTL 30d auto-prune + per-actor max active=20 + global storage cap

### 10.4 UX 層（1 條）
11. **A3 dedicated UX subdoc**：land `docs/execution_plan/2026-05-02--ref20_ux_subdoc_v1.md`，拒絕 PR section 等價路徑；同時補 §8 點 2 改明文「Session 工作區 submitOrder/cancelOrder 必須移除」

### 10.5 安全層（1 條）
12. **E3 NEW-01 補完** Mac env var `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA=1` + Mac 跑時拒寫 `learning.replay_runs` 只允 dry-run console

---

## 11. P0 Commit 後可延 V2.2（不擋 P0）

- **CC** SHOULD-FIX：原則 #4 Guardian gate e2e + 原則 #13 cost_edge_ratio ≥ 0.8 e2e check
- **FA** 業務層：12-Tab nav schema / advisory mlde 路徑明文 / §8 8 條 UX 改業務驗收 / §9 phase exit 加業務指標 / `live_candidate_research_only` 路徑（OPEN QUESTION）
- **QC** 進階：OOS embargo 改 `max(7d, 2× half_life)` + per-strategy override / shrinkage decision tree（n<30 → JS / cross-strategy → HB / small-K → EB）/ regime detector 3 細節（freeze 對象 / N 窗 / Kupiec 歸屬 / warmup phase）
- **MIT** ML maturity 4×5 評級表 + §10 `replay_routes_use_safe_query_pattern` + §3.2 retrofit policy 4 點具體化
- **E3** GAP-04 retention 180d 上限 / GAP-05 `nm` symbol grep / GAP-03 cfg gate（與 PA #8 同源）

---

## 12. 路徑建議

```
2026-05-02 [今日] V2 land + 第三輪 7-agent audit 完成
                            ↓
2026-05-?? operator review 本 audit 文件，標記接受/拒絕的 finding
                            ↓
2026-05-?? PM 起草 V2.1（12 條 P0 必補 minor patch）
                            ↓
2026-05-?? V2.1 short confirm（同 7 agent 跑一輪 ≤300 字快速確認）
                            ↓
              [P0 amendment commit] REF-19 v2 + REF-20 v2 + V2.1 + UX subdoc v1
                            ↓
2026-05-?? ← P-5 5 策略 indicator leak-free sweep（QC 主審 + E3 副審，R3-6 阻塞）
                            ↓
2026-05-?? P1 IA 重組（純 frontend，須 UX subdoc land）
                            ↓
2026-05-?? P2a Registry / Auth / Manifest（schema 物理 column + DB role grant + Guard A/B/C）
                            ↓
2026-05-?? P2b Read-Only S2/S3 Smoke（IntentProcessor cfg gate enforcement + binary-level grep）
                            ↓
              ← FUP-2 attribution writer（P3a 前置）
              ← AMD-2026-05-02-01 lease retrofit（不擋 P2 但 P3+ advisory wiring 前必到）
                            ↓
2026-06-?? P3a Global Calibration（V2.2 OOS embargo per-strategy override）
                            ↓
2026-06-?? P3b Cell-Level Calibration / P4 MLDE / Dream Advisory
                            ↓
              ← LG-2/3/4 IMPL deploy + 7d stable
                            ↓
2026-07-?? P5 Agents Monitor → 12-Tab
                            ↓
2026-08-?? P6 Bounded Demo A/B Handoff
```

---

## 13. 三輪 Audit 進步軌跡

| 維度 | v0.1 → V1 | V1 → V2 | V2 → V2.1（待補） |
|---|---|---|---|
| **解決率** | 28% ✅ + 44% ⚠️ + 20% ❌ + 8% 🆕 | ~70% ✅ / ~25% ⚠️ / ~5% ❌ | 預期 ~95% ✅（V2.1 minor patch） |
| **MIT BLOCKER** | 4 | **0**（全解） | 0 |
| **致命安全 CRIT** | 3 | 1 半解（CRIT-01 DB grant） | 0 |
| **量化方法論 REJECT** | F1/F2/F3 全 REJECT | P0/P1/P2 通；P3+ V2.1 補丁 | 0 |
| **UX subdoc** | 缺 | 缺（PR section 等價） | dedicated subdoc 必 land |
| **總體 7-agent 投票** | 全 REJECT/阻塞 | 5/7 Conditional Approve；2/7 阻塞 | 預期 7/7 APPROVE P0 |

---

## 14. 修訂歷史

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| Round 3 v0.1 | 2026-05-02 | PM（主會話） | V2 第三輪 7-agent 冷酷審查；MIT 4 BLOCKER 全解、QC P3+ 大幅 unblock；剩 12 條 V2.1 minor patch 後可進 P0 commit；A3 UX subdoc 仍須 dedicated；E3 HIGH-04 quota 仍開 |

---

## 附錄 A — 7-Agent 第三輪完整判定一覽

| Agent | 第三輪判定 | 必補項計數 | 關鍵阻塞 |
|---|---|---|---|
| CC | Conditional Approve (B) | 3 MUST + 3 SHOULD-FIX | N-1 V### / N-4 fail-mode / §3.2 DB grant；#13 cost gate / N-2 cross-env baseline / C-3 cfg gate |
| PA | Conditional Approve | 5 條件 | P2a IntentProcessor cfg gate / P3 三選一寫死 new binary / schema backfill SQL / 4 物理 column / baseline snapshot 取法 |
| FA | Conditional Approve | 3 P0 必補 + 4 V1.1 | baseline ambiguity / OOS schema / happy path flow |
| QC | P0-P2 Approve / P3a hard-block / P3b/P4/P6 V2.1 補丁 | R3-1 物理 column + 5 wording patches | manifest_jsonb 升級為物理 column |
| MIT | Conditional Approve → V2.1 | 6 V2.1 必補 | V### 治理 / Guard A/B/C / schema 5 column / retrofit policy / ML maturity / safe_query / indicator leak-free sweep |
| A3 | REJECT P1 / Conditional P0 | 1 dedicated subdoc + 8 spec 補完 | UX subdoc 必 land / §8 點 2 明文砍 fake button |
| E3 | Conditional Approve P0 commit | 2 P0-blocking + 3 P2b 必補 | DB role grant + manifest quota + Mac env var |

## 附錄 B — agent 原始 finding 路徑

完整原始發現（含每個 finding 的具體段落引用、修法、SQL probe 等）保留在主會話 transcript（2026-05-02 第三輪 7-agent dispatch）。本 audit 文件已綜合去重。若 V2.1 修訂需更細粒度，可重派同 7 agent 跑 short confirm（≤300 字快速確認）。
