# REF-20 V1 第二輪 7-Agent 冷酷審核總結

**日期：** 2026-05-02
**狀態：** Audit 結果文件，與 V1 並列存放，**不直接修改 V1**
**審核對象：** `docs/execution_plan/2026-05-02--ref20_paper_replay_lab_dev_plan_v1.md`
**第一輪參照：** `docs/execution_plan/2026-05-02--ref20_paper_replay_lab_dev_plan_draft_v0.1.md`
**Owner：** PM
**派出 agent：** CC / PA / FA / QC / MIT / A3 / E3 並行（獨立、無口徑協調）

---

## 0. TL;DR — 7-agent 投票結果

| Agent | 第一輪判定 | 第二輪判定 | 判定變化 |
|---|---|---|---|
| **CC** | B-（Conditional Approve） | **B（Conditional Approve）** | ⬆️ 升一級，2 MUST-FIX |
| **PA** | 🔴 阻塞（HOLD P2） | **Conditional Approve** | ⬆️ unblock 部分，6 MUST-FIX |
| **FA** | Conditional Approve | **Conditional Approve** | ↔️ 持平，3 MUST-FIX 進 P0 前 |
| **QC** | 🔴 REJECT | **Conditional Approve（P0/P1/P2）+ P3a/b/P4/P6 hard-block** | ⬆️ P2 unblock，下游仍 block |
| **MIT** | 🔴 阻塞 | 🔴 **REJECT（強拒）** | ⏬ **判定加重**，4 BLOCKER |
| **A3** | C（5.5/10） | **REJECT V1 進入 P1** / Conditional Approve V1 進入 P0 | ↔️ 持平，UX 子文件全缺 |
| **E3** | 🔴 CRIT × 3 | **Conditional Approve for P0 amendment（非 implementation）** | ⬆️ 5/9 closed，4 仍開 + 4 NEW |

**整合判定**：V1 **不能直接進入 P0 amendment commit**，必須先補完下列 12 條 MUST-FIX。其中 **MIT 4 BLOCKER + A3 UX 子文件**是最強硬阻塞。整體質量比 v0.1 大幅提升，PM 對「過度阻塞」的拒絕（解綁 P2 與 lease retrofit / Mac smoke 留出口）多數 agent 站得住，但條件是 P2/P2b 的「import-level isolation invariant」必須寫死。

---

## 1. 共識 MUST-FIX（≥3 agent 同 finding，不可繞過）

| # | Finding | 來源 agent | 修法 | 阻塞 phase |
|---|---|---|---|---|
| **C-1** | **§4.2 `evidence_source_tier` 缺 DB 層 `CHECK constraint`**：靠 applier code 自律 = V023 silent-noop 同模式；攻擊者繞 applier 直接 INSERT 仍可帶 fake `'real_outcome'` | CC #5 / MIT R2+B2 / E3 CRIT-01 | DDL `CHECK (evidence_source_tier IN (...))` + retrofit 3 步 migration（ADD COLUMN nullable → backfill conservative `'real_outcome'` only WHERE source 可推斷 → ALTER NOT NULL + ADD CHECK）+ healthcheck `check_evidence_source_tier_completeness` + 寫權限 GRANT 收斂到 replay runner role | P2a |
| **C-2** | **§7 attribution gate「sufficient for the selected strategy/window」未寫死閾值**：留洞 = `cognitive_honesty` 違反，可被讀成「我覺得 50% 就 sufficient」；84.6% 真實 false 環境下需明確紅線 | PA Q4 / FA #5 / QC F1 / MIT R3 | 寫死 `attribution_chain_ok_ratio ≥ 0.7 over calibration_oos_label_window` AND per-cell n ≥ 30 為 P3 entry gate（block 而非 warning） | P3a / P3b |
| **C-3** | **§6 P2 / P2b 不禁 IntentProcessor / DecisionLease 路徑**：邊界寫「無 mutation/no advisory/no handoff」但未寫「不 import / link Rust 熱路徑 symbol」；P2b smoke compare 仍可能 instantiate IntentProcessor 觸 lease | CC Q2/Q3 / PA Q2/Q3 / E3 NEW-04 | §6 加 import-level invariant：「P2/P2b 不 instantiate `IntentProcessor` / `DecisionLease` 任何 struct，不 link Rust trade engine binary 任何 symbol」+ §10 加 grep 自動化 acceptance check | P2 |
| **C-4** | **§6 P3+ 「canonical replay runner OR isolated process 二選一」含糊**：把 v0.1 的 B1（Rust replay mode 非 production-grade）問題搬家到 P3+ 而未給 spec | CC #10 / PA Q3 / QC O2 | §6 改寫死「P3+ 須新建 `replay_engine` crate（或獨立 process），**不 reuse** P2 Rust replay mode；canonical runner 必有獨立 strategy registration、IPC handoff、無 canary_mode 翻轉、CanaryRecord 升級為完整 fill record」 | P3a |
| **C-5** | **§7 PBO / DSR / equivalent gate 含糊**：「equivalent」可變「我覺得 q50>0 就算 controlled」；DSR 與 PBO 不等價（DSR 衡量 single-strategy Sharpe inflation，PBO 衡量 multi-candidate selection overfitting） | QC F3 / MIT B4 / FA acceptance | §7 拆兩個 gate 各自寫死閾值：(a) `PBO < 0.5`（CSCV N≥16）強制 K candidates ≥10 必跑；(b) `DSR(K) > 0.95` 強制 single-strategy；不允許 fallback to「equivalent」 | P4 / P6 |
| **C-6** | **manifest signature 算法 / key source / rotation / fail-mode 全空**：§5「server-side only」對但工程細節缺 | CC Q2 / E3 CRIT-02 / MIT B1 | algorithm = HMAC-SHA256（對齊 `authorization.json`）；key = 獨立 `$OPENCLAW_SECRETS_DIR/<env>/replay_signing_key`（**不重用** `auth_signing_key` 防權限混淆）；rotation 90d；簽名失敗 fail-closed = run reject | P2a |

---

## 2. MIT 4 BLOCKER（強拒 V1，必須先補）

| # | Finding | 修法 |
|---|---|---|
| **M-1** | **R3 attribution 必須鎖 0.7**（與 C-2 同源，但 MIT 視為 BLOCKER 非 SHOULD-FIX） | 同 C-2 |
| **M-2** | **Y3 engine_mode 'synthetic' / `replay.simulated_fills` 路徑必須選邊**：replay simulated fill 寫哪？(a) 不寫 trading.fills（V1 已宣示）；(b) 新建 `replay.simulated_fills` 表（V1 §4.1 未列）；(c) 走 paper engine_mode（**絕禁**會污染 paper 統計） | V1 必選 (b) 新增 `replay.simulated_fills` table 進 P2b deliverable，或 engine_mode CHECK 加第 5 值 `'synthetic'` 並另開 partition；P0 amendment 必明確選邊 |
| **M-3** | **Y2 manifest timeframe enum 缺**：`decision_outcomes` timeframe `'1' vs '1m'` bug 已知會傳染 manifest | §4.1 manifest schema 加 `timeframe VARCHAR(8) CHECK (timeframe IN ('1m','3m','5m','15m','1h','4h','1d'))` + P2a healthcheck `replay_manifest_contract` 加 enum verify |
| **M-4** | **B4 PBO 與 DSR 必須拆開**（同 C-5） | 同 C-5 |

---

## 3. PA 6 條 MUST-FIX 補完（與 C-* 部分重複）

1. §6 P2 加「禁呼 IntentProcessor / 不寫 intents 表」一行 → **C-3**
2. §6 P3 改「canonical replay_engine 新建，不 reuse Rust replay mode」 → **C-4**
3. §7 寫死 `attribution_completeness ≥ 0.7 AND n ≥ 30` → **C-2 / M-1**
4. §9 P2a 加 health_check + GUI `P2B_PENDING` warning（避免 P2a→P2b 過渡空窗 manifest 表 0 row 變成「靜默正常」）
5. §1 #4 排 V### 順序 + 既有 row backfill SQL：建議 V037（replay manifest/registry/auth）→ V038（evidence_source_tier 加欄 + backfill）→ V039-V040（lease retrofit）
6. 補 H5 per-cell sample power 下限：建議 n ≥ 30/cell

---

## 4. FA 3 條 MUST-FIX（P0 前必補）

1. **§6 P2 baseline 顯式定義**：「baseline vs candidate」沒寫 baseline 是 current deployed config snapshot / 上一 demo_applier batch / git tag / 用戶手選 → V1.1 §6 P2 顯式：`baseline = current active demo config snapshot at experiment_start_ts`
2. **§7 三閾值硬數字**：sample_size ≥ 200 fills/strategy-window + stale ≤ 72h + OOS embargo = 7d 三組
3. **§9 P5 加 LG-2/3/4 前置 gate**：「after collision risk lower」改寫死「LG-2/3/4 frontend merged + 7 天 stable」

可延後到 V1.1（不擋 P0）：
- (d) `live_candidate_research_only` advisory 路徑重提（PM 收斂單路徑站得住，但研究產物不能寫 GovernanceHub review-only directive 是設計缺口，建議 OPEN QUESTION）
- (e) §8 11→12-Tab nav schema
- (f) §10 6 條不可測 acceptance 改 SQL probe

---

## 5. QC P3+ Hard-block（直至 V1.1 amendment）

QC 接受 P0/P1/P2 進入，但 P3a / P3b / P4 / P6 必須 hard-block 直至：

1. **§7 7 條 gate 全給數值閾值**：n ≥ 30 / PBO < 0.5 / DSR(K) > 0.95 / embargo ≥ 2× signal half-life / shrinkage method 鎖定（James-Stein 用於 cell n<30，hierarchical Bayes 用於 cross-strategy pooling，禁 ad-hoc）
2. **§4.1 manifest schema 加 4 欄位 + runtime validator**：`calibration_oos_label_window: [start, end]` + `calibration_train_window: [start, end]`（必與 OOS disjoint，runtime check）+ `selection_bias_correction: {method, K, alpha_corrected}` + `regime_shift_status: {cusum_value, last_refit_ts}`
3. **新增 §7.X regime shift detector**：CUSUM on realized edge per cell（±3σ → freeze calibration）+ Kupiec POF backtest（每 250 fills rebench）+ PSR(0) < 0.95 持續 N 窗 → auto-trigger refit + alert PM
4. **q10/q50/q90 計算法寫死**：Block bootstrap（Politis-Romano，preserve autocorr，crypto 必用）1000 iter；n<30 fall back parametric + 標 `low_confidence`

---

## 6. A3 P1 阻塞 — UX 子文件 3 前置

A3 **REJECT V1 進入 P1 IA 啟動**（CONDITIONAL APPROVE V1 進入 P0 amendment 規劃）。理由：V1 是合格的後端契約 + phase gate 文件，但 UX layer 子文件完全缺席。P1 一旦在當前 spec 啟動，必複製 5-Agent MVP「界面看似完整實際空」陷阱。

**前置條件（P1 啟動前必先 land）**：

1. **`docs/execution_plan/2026-05-02--ref20_ux_subdoc_v1.md`**（新文件）：sub-tab 實作模式（HTML tab / vanilla JS show-hide / Vue route 三選一）/ disabled UI mode（grey card + banner / 鎖頭 tooltip / 完全隱藏）/ typed confirm 容錯（confirm 字串、typo 處理、cooldown ≥30s、雙 actor 政策）/ Compare 排版（≥10 指標 sub-section / collapse / tabs 三選一）/ Learning 7 區塊 accordion（單頁 ≤7 紅線）/ 術語中文對照表（`evidence_source_tier`, `manifest_signature`, `execution_confidence`, `attribution_chain_ok`, `data_tier S0-S4`, `PBO/DSR`, `q10/q50/q90`）/ mode badge 規則（Paper Replay Lab 用什麼色？execution_confidence 與 mode badge 衝突）/ 錯誤狀態 4 表（5min budget 超時 / cancel 失敗 / signature mismatch / max_concurrent=1 被佔用）
2. **Paper Tab 既有 submitOrder/cancelOrder 處理決策**（一句話 by PM）：保留 in Session / 完全砍 / 移到別處
3. **P5 Agents Monitor「collision risk lower」exit metric 量化**：如 LG-2/3/4 三個前端 component 通過 E4 回歸

---

## 7. E3 4 NEW 攻擊面（V1 引入）

| # | Finding | 嚴重 | 修法 |
|---|---|---|---|
| **NEW-01** | **Mac smoke 路徑資料外洩**：§1 #3 + §4.1 `runtime_environment='mac_dev_smoke_test_only'`；若 P2b S2 klines / S3 synthetic 是真實 demo / live_demo 歷史 fills 衍生（calibration training source），Mac dev box pull 時即洩 production fills | HIGH | Mac smoke 只允 S3 synthetic（不允 S2 真實 klines）+ 強制環境變數 `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA=1` + Mac 端禁讀 `learning.exit_features` / `trading.fills` |
| **NEW-02** | **hash vs signature 雙重 enforcement 順序未定**：§4.1 `manifest_signature` + §4.2 `manifest_hash` 兩欄；攻擊者偽造 hash 對得上 manifest_jsonb 但 signature key rotate 後驗不過時 applier 行為？ | MEDIUM | 「先驗 sig 再驗 hash」+ fail-closed default；hash 失配與 signature 失配兩種 reject reason 各自記 audit |
| **NEW-03** | **replay process scaling 未限**：§5「Active runs per actor are capped」但 cap 數值未寫；100 actor × N concurrent = 系統耗盡；max concurrent=1 是 per actor 還是 global 含糊 | HIGH | 寫死 global max concurrent = 1（or 2），per actor cap = 1；超出 429 |
| **NEW-04** | **P2b lease bypass 未證**：§1 #2 PM 主張 P2b「無 mutation 無 advisory 無 handoff」即不需 lease；但 §6 P2 仍呼 Rust `--replay-mode` binary，是否真完全隔絕 Decision Lease emit 路徑？ | MEDIUM | 與 C-3 同：binary-level grep 證明 + import-level invariant + acceptance check |

---

## 8. PM 拒絕點是否站得住？

| PM 拒絕 / 修訂 | 7-agent 投票 | 條件 |
|---|---|---|
| **§1 #2 拒絕「P2 等 lease retrofit」** | **3 站得住（CC/PA/E3 條件性） / 1 邊界（QC 接受 P2 進入） / 0 反對** | **條件**：§6 必加 import-level invariant（C-3）；P2 完全 Python-only 不 link Rust trade engine；無 IntentProcessor / DecisionLease symbol；acceptance check `replay_no_intent_processor_link` 加進 §10 |
| **§1 #3 Mac smoke + Linux 重跑** | **2 站得住（PA H3 / CC）/ 1 條件（E3 NEW-01）** | **條件**：Mac 端禁讀真實 fills；只允 S3 synthetic |
| **§1 #4 `evidence_source_tier` 名稱分離** | **3 接受（CC #5 / MIT R2 / PA H4）** | **條件**：必補 DDL CHECK constraint（C-1） |
| **§1 #5 P2 可用 S2 + S3** | **2 接受（PA / QC）/ 1 條件（E3 NEW-01）** | **條件**：S2 必標 `execution_confidence=none`（V1 已寫）+ Mac 禁 S2 |
| **拒絕 7-agent 為 sign-off** | **PM 對，整 7 agent 沒異議** | review input only ✅ |

---

## 9. V1 vs draft v0.1：解決率統計

跨 7 agent 第一輪總計 ~50 條 finding，V1 對應狀態：

- ✅ **完全解決**：~14 條（28%）— 主要是 schema land / route 拆分 / file size / Mac drift / sub-tab 命名 / typed confirm 寫入 / report_uri 白名單 / textContent rendering
- ⚠️ **部分解決**：~22 條（44%）— 寫了原則但缺數值 / 缺 enforcement layer / 缺 schema enforcement
- ❌ **未解決**：~10 條（20%）— attribution 0.7 閾值未鎖 / DDL CHECK 缺 / engine_mode 'synthetic' / live_candidate_research_only / Paper Tab fake button / IA navigation
- 🆕 **V1 新引入**：~4 條（8%）— P3+ canonical 含糊 / Mac smoke 洩漏 / hash vs sig 順序 / replay scaling

整體：V1 大方向對，工程細節缺；不該直接進 P0 commit，但 V1.1 amendment 可在 1-2 sprint 內補完。

---

## 10. P0 Amendment 必補硬清單（13 條）

進入 P0 amendment commit 前必補：

1. **C-1** §4.2 `evidence_source_tier` DDL CHECK + retrofit 3 步 + healthcheck + GRANT 收斂
2. **C-2 / M-1** §7 attribution `≥ 0.7 AND n ≥ 30`（hard-block，非 warning）
3. **C-3** §6 P2 import-level invariant（不 link Rust trade engine binary）+ §10 grep acceptance
4. **C-4** §6 P3+ 寫死「新建 `replay_engine` crate，不 reuse P2 Rust replay mode」
5. **C-5 / M-4** §7 PBO < 0.5 + DSR(K) > 0.95 兩 gate 拆分，禁 equivalent
6. **C-6** manifest signature 算法 / key source / rotation / fail-mode 寫死
7. **M-2** engine_mode 'synthetic' / `replay.simulated_fills` 選邊（建議新表）
8. **M-3** manifest schema timeframe enum
9. **PA-4** §9 P2a→P2b health gate + GUI `P2B_PENDING` 標
10. **PA-5** V### 編號排序 + 既有 row backfill SQL
11. **FA-1** §6 P2 baseline 顯式定義
12. **FA-3** §9 P5 加 LG-2/3/4 deploy + 7d stable 前置 gate
13. **A3 前置 (a)(b)(c)** UX 子文件 + Paper Tab fake button 決策 + P5 collision metric 量化

QC 進階要求（**P3+ hard-block**，非 P0 必補但寫進 V1.1 計劃）：
- §7 7 條 gate 數值化（5 條閾值）
- §4.1 manifest schema 加 4 欄位 + runtime validator
- §7.X regime shift detector（CUSUM + Kupiec + PSR）
- q10/q50/q90 計算法寫死 block bootstrap

E3 進階要求（NEW-01-04 補硬條款）：
- Mac smoke S3-only + 環境變數 + 禁讀真實 fills
- hash vs sig 驗證順序 + fail-closed
- replay max concurrent global=1 + per actor=1
- P2b lease bypass binary-level grep 證明

---

## 11. 路徑建議

```
2026-05-02 [今日] V1 land + 第二輪 7-agent audit 完成
                            ↓
2026-05-?? operator review 本 audit 文件，標記接受/拒絕的 finding
                            ↓
2026-05-?? PM 起草 V1.1（13 條 P0 必補 + QC/E3 進階要求）
                            ↓
2026-05-?? V1.1 二輪 audit（同 7 agent 跑一輪 short 確認）
                            ↓
              [P0 amendment commit] REF-19 v2 + REF-20 v2 + V1.1
                            ↓
2026-05-?? ← REF-20-UX 子文件 land + Paper Tab fake button 決策（A3 前置）
                            ↓
2026-05-?? P1 IA 重組（純 frontend）
                            ↓
2026-05-?? P2a Registry / Auth / Manifest（M-1/M-2/M-3 schema land）
                            ↓
2026-05-?? P2b Read-Only S2/S3 Smoke（C-3 import-level invariant 驗證）
                            ↓
              ← AMD-2026-05-02-01 lease retrofit deploy（不再 hard block P2，但仍是 P3+ 前置）
                            ↓
              ← FUP-2 attribution writer + decision_outcomes timeframe 修
                            ↓
2026-06-?? P3a Global Calibration（QC 數值化 + regime detector + bootstrap CI）
                            ↓
2026-06-?? P4 MLDE / Dream Advisory（PBO + DSR 拆 gate）
                            ↓
              ← LG-2/3/4 IMPL deploy + 7d stable
                            ↓
2026-07-?? P5 5-Agent → 12-Tab Agents Monitor
                            ↓
2026-07-?? P3b Cell-Level Calibration
                            ↓
2026-08-?? P6 Bounded Demo A/B Handoff
```

---

## 12. 修訂歷史

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| Round 2 v0.1 | 2026-05-02 | PM（主會話） | 7-agent 第二輪冷酷審查回收後初稿；V1 整體方向 OK，13 條 MUST-FIX 必補進 V1.1；MIT 4 BLOCKER + A3 P1 前置 3 子任務 + QC P3+ hard-block + E3 4 NEW |

---

## 附錄 A — 7-Agent 完整判定一覽

| Agent | 第二輪判定 | 必補項計數 | 關鍵阻塞 |
|---|---|---|---|
| CC | Conditional Approve (B) | 2 MUST + 1 SHOULD | C-1 / C-3 / 16 原則 #4 #13 e2e |
| PA | Conditional Approve | 6 MUST | C-3 / C-4 / C-2 / P2a→P2b 過渡 / V### 排序 / sample power |
| FA | Conditional Approve | 3 MUST | FA-1 baseline / FA-2 三閾值 / FA-3 P5 LG gate |
| QC | P0/P1/P2 Approve, P3+ hard-block | 4 P3+ 必補 | §7 數值化 / manifest 4 欄 / regime detector / bootstrap CI |
| MIT | **REJECT 強拒** | 4 BLOCKER + 4 V1.1 amendment | M-1 / M-2 / M-3 / M-4 |
| A3 | REJECT P1, Approve P0 amendment | 3 前置 | UX 子文件 / Paper Tab fake button / P5 collision metric |
| E3 | Conditional Approve P0 amendment（非 implementation） | 6 硬條款 + 4 NEW | C-1 升 DB trigger / C-6 sig 細節 / Mac 洩漏 / scaling cap |

## 附錄 B — agent 原始 finding 路徑

完整原始發現（含每個 finding 的具體段落引用、修法、SQL probe 等）保留在主會話 transcript（2026-05-02 第二輪 7-agent dispatch）。本 audit 文件已綜合去重。若 V1.1 修訂需更細粒度，可重派同 7 agent 跑 short confirm。
