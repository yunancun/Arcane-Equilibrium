# v5.7 Dispatch-Safe Patch 執行性審核 — QA 視角

**日期**：2026-05-21
**審核人**：QA (Quality Assurance)
**Verdict**：**GO-WITH-CONDITIONS**
**One-line summary**：v5.7 thesis 與 6 個 reviewer correction 都做對了，但執行性層面缺 Stage transition 驗收條件具體化、灰度 7d 0 CRITICAL 規劃缺、Earn governance 與 5 hard gate boundary 一致性未明確；Sprint 1A 派發前必修 3 項。

---

## 0. Stage transition 驗收條件清晰度

對照 v5.6 §12 8 個 Stage（DRAFT → PREREGISTERED → SHADOW → STAGE_0R → STAGE_1 DEMO → STAGE_2 → STAGE_3 → STAGE_4 LIVE_PENDING → LIVE），逐項清晰度評估：

| Stage | 驗收條件清晰度 | 理由 |
|---|---|---|
| DRAFT | CLEAR | 「pre-registration locked」明確；§3 V103 hypothesis_preregistration table 已落地 |
| PREREGISTERED | PARTIAL | 「operator + Cowork hypothesis review」缺具體 review checklist（誰簽、什麼通過標準）|
| SHADOW | **MISSING** | v5.6 §12 「evidence quality check, NOT Sharpe gate」— 但**沒定義什麼是 quality check**；只說「not Sharpe」沒說 IS 什麼；§5 counterfactual logger 沒對應 SHADOW gate 出口條件 |
| STAGE_0R replay preflight | PARTIAL | 引用 AMD-2026-05-15-01 「per existing canary」— 但 v5.7 沒驗證 canary 對 5 個策略 + 4 個 sensor 都覆蓋；options chain / token unlock / macro feed / on-chain signal **是否有 replay 路徑**未明確 |
| STAGE_1 Demo micro canary | PARTIAL | 「1 strategy × 1 symbol × 7d, REAL fills, Demo env」明確，但 v5.7 §4 Earn stake 操作的 Stage 1 等價物**沒定義**（Earn 不是 strategy，但是 asset write） |
| STAGE_2 Demo extended | CLEAR | 14d，繼承 Stage 1 條件 |
| STAGE_3 Demo full | CLEAR | 21d |
| STAGE_4 Live pending | PARTIAL | 「operator approval + 5-gate boundary」引用 CLAUDE §四，但 v5.7 §4 Earn governance**沒對應 5-gate 哪一條**（live_reserved 對 Earn 適用嗎？authorization.json env_allowed 對 Earn API 適用嗎？）|
| LIVE | CLEAR | 引用既有 mainnet 路徑 |

**核心缺**：SHADOW gate 出口條件 + counterfactual logger 對 Stage transition 的角色 + Earn 與 Stage transition 的對應。

---

## 0.5 灰度 7 天 0 CRITICAL（每個策略）

v5.7 沒明確 7d 灰度規劃。對照 5 個策略 + 4 個 sensor，QA 視角缺失列表：

| 標的 | 7d 灰度規劃 | 狀態 |
|---|---|---|
| C10 funding harvest | Sprint 1B「minimal viable on 主帳 $2,000」直接 live，沒寫 demo 7d 灰度 | **MISSING** |
| Unlock SHORT | Sprint 4「Stage 1 Demo micro-canary 7d → Stage 2 14d」對齊 v5.6 §12 | CLEAR |
| Pairs trading | Sprint 5 同 Unlock 模式 | CLEAR |
| C13 options VRP | Sprint 6 同模式 | CLEAR |
| Funding short-only | Sprint 6 同模式 | CLEAR |
| Earn stake $200-400 | Sprint 1B「first small manual stake」沒寫 demo 灰度 7d | **MISSING** |
| Bybit options chain recorder (NEW) | 沒寫 sensor 7d 觀察期 | **MISSING** |
| Tokenomist unlock calendar (NEW) | 沒寫 7d 觀察期 | **MISSING** |
| Macro calendar feed (NEW) | 沒寫 7d 觀察期 | **MISSING** |
| Binance market data WS (NEW) | 沒寫 7d 觀察期 | **MISSING** |

**Sprint 1B C10 直接 live $2,000 是 v5.7 最大執行性風險**：違反 v5.6 §12 Stage 1→2→3→4 漸進路徑。即便 C10 是 minimal viable，也必須走 Stage 1 Demo 7d。

---

## 1. Top 3 執行性風險（排序）

### Risk 1：Sprint 1B C10 跳過 Stage 1-3 Demo 灰度直 live $2,000

- **嚴重度**：CRITICAL
- **位置**：v5.7 §8 Sprint 1B；§9 「C10 minimal viable on 主帳 $2,000」
- **描述**：v5.7 §8 寫「Sprint 1B (W1.5-3): C10 minimal viable on 主帳 $2,000」。v5.6 §12 Strategy lifecycle 規定 DRAFT → PREREGISTERED → SHADOW → STAGE_0R → STAGE_1 DEMO 7d → STAGE_2 14d → STAGE_3 21d → STAGE_4 LIVE_PENDING → LIVE。3 週內走完 8 個 Stage 在數學上不可能（光 Stage 1+2+3 就是 42 天）。
- **為何屬「執行性」（非邏輯）**：thesis 同意走 Stage gate，但 Sprint 1B 工時表（50-70 hr W1.5-3）沒分配 demo 灰度時間，operator 真按 v5.7 派發會直接違反 v5.6 §12 governance。
- **Must-fix 建議**：
  1. Sprint 1B 改「C10 Stage 0R replay preflight + Stage 1 Demo micro-canary 7d 啟動」，不寫 live
  2. C10 Stage 4 Live 真實時間落在 Sprint 3-4（W8-15）
  3. 或明確 operator override + 寫入 ADR

### Risk 2：Earn governance 對 5 hard gate 邊界不一致

- **嚴重度**：HIGH
- **位置**：v5.7 §4 Bybit Earn governance policy
- **描述**：v5.7 §4 寫「Each stake operation = asset write, requires authorization」「Guardian-checked」「Decision Lease pattern」— 但對應 CLAUDE §四 5 hard gate 哪幾條適用沒寫：
  - `live_reserved` global mode 對 Earn stake 適用嗎？
  - Operator role auth 適用嗎？
  - `OPENCLAW_ALLOW_MAINNET=1` 對 Earn API 適用嗎？
  - secret slot api_key/api_secret 是否同 trading 共用？
  - `authorization.json` HMAC + env_allowed 對 Earn endpoint 適用嗎？
- **為何屬「執行性」（非邏輯）**：thesis 同意 Earn 要 governance，但工程不知道是「複用 trading 5-gate」還是「Earn 專用 lite-gate」；E1 IMPL 階段會撞牆。
- **Must-fix 建議**：Sprint 1A 派 PA 前明確「Earn 沿用 5-gate 全部，無例外」或「Earn 用 reduced gate {gate 2, gate 4}」，並更新 CLAUDE §四 Hard Boundaries。建議前者（簡單；asset write 性質相同）。

### Risk 3：SHADOW stage 出口條件未定義 + counterfactual logger 不接 Stage transition

- **嚴重度**：HIGH
- **位置**：v5.6 §12 SHADOW 行 + v5.7 §5 counterfactual logger
- **描述**：v5.6 §12 SHADOW gate 寫「evidence quality check, NOT Sharpe gate」— 但**沒定義 quality check 是什麼**。v5.7 §5 macro + on-chain counterfactual logger 在 Y1 全程跑，但**不接 Stage transition** — 即 counterfactual A/B 數據怎麼判斷「prove alpha」用於 Y2 啟用門檻沒定。
- **為何屬「執行性」（非邏輯）**：thesis 同意「Y1 末 evaluate」，但「+2%+ on strategies」這個 threshold 是怎麼算的（average across strategies？per-strategy？counterfactual p-value < ?）沒定，Sprint 10 Y1 review 無法執行。
- **Must-fix 建議**：v5.7 §5 加 acceptance threshold 具體公式 + p-value/effect size 標準 + decision rule（「IF avg_counterfactual_uplift_bps > X AND p < 0.05 across ≥3 strategies → Y2 enable」）。Sprint 2 派 QC 並行起草。

---

## 2. Hours sanity check（QA acceptance 工時 vs estimate）

v5.7 §9 工時表 1,190-1,590 hr 對 QA acceptance 工時的覆蓋度檢核：

| Sprint | v5.7 工時 | QA acceptance 隱含工時 | 是否覆蓋 |
|---|---|---|---|
| 1A (60-80hr) | governance + migration + sensors | 5 sensor 各 7d demo 灰度觀察 + 4 new sensor healthcheck = ~40 hr | **NO** — Sprint 1A 沒留 QA acceptance 時間 |
| 1B (50-70hr) | C10 + Earn live + tournament prep | C10 Stage 1-3 Demo 灰度 = 42 day calendar；Earn governance 5-gate adapt = ~20 hr | **NO** — calendar 不夠 |
| 2 (110-150hr) | Tournament + microstructure + on-chain counterfactual setup | Counterfactual A/B logger end-to-end acceptance = ~30 hr | PARTIAL |
| 3 (130-160hr) | Top-1 build + Stage 0 shadow | Stage 0R replay preflight (existing canary 對 unlock SHORT) = ~20 hr | CLEAR |
| 4 (160-210hr) | Top-1 live + Top-2 + Options Stack 1 | Stage 1+2+3 Demo 42d 灰度 + 雙進程 E2E (Python+Rust) = ~50 hr | **PARTIAL** — peak 週工時 + calendar tight |
| 7 (110-150hr) | Top-5 + Advisory Allocator + Live promos | Allocator advisory mode acceptance (proposal → operator approve → Decision Lease 路徑驗收) = ~25 hr | PARTIAL |

**QA 結論**：v5.7 §9 沒分配 QA acceptance 工時 buffer。每 sprint 應加 10-15% QA acceptance overhead（即 ~120-160 hr 共計）。

---

## 3. 未識別的依賴 / 阻塞

### 3.1 雙進程 E2E（Python + Rust）對 5 strategy + 4 sensor 的同步測試
- v5.7 沒提雙進程 E2E acceptance plan
- 4 new sensor（options chain / Tokenomist / macro / Binance WS）的 Rust writer 是新代碼，必須驗：Python 影子進程 vs Rust Engine tick 輸出 < 1e-4 容差
- Bybit Earn API 整合是 Python-only 還是 Rust-side？v5.7 §4 沒明確 — 若 Rust-side，Python ↔ Rust IPC schema 需新增 stake intent message type，影響 Sprint 1A 工時

### 3.2 V101/V102 vs V103/V104 dispatch sequencing race
- v5.7 §3 寫「PA dispatch confirms final numbers based on: Linux DB head at dispatch time + other in-flight migration work + race-aware sequencing」— 但**沒給 race-aware sequencing SOP**
- 若 Sprint 1A 派發時 V101/V102 Track schema 還在 in-flight，V103/V104 可能被搶占
- 必須在 dispatch 前 ssh trade-core 跑 `psql -c "SELECT max(version) FROM _sqlx_migrations"` 確認 head

### 3.3 healthcheck 既有 writer 的「extend」與「rebuild」邊界
- v5.7 §6 寫 market.liquidations writer「HEALTHCHECK existing, NOT new」
- 但「extend existing Bybit perp WS」+「add Binance perp WS NEW」的差別是**新 client 還是同 client 加 subscription**沒明確
- 影響：Rust binary mtime 變動範圍 + IPC schema 是否新增 message type

### 3.4 GUI 寫入面對應的 acceptance 缺
- v5.7 §4 Earn stake operation 是 GUI 寫入面（operator console 觸發）還是 CLI 觸發？沒寫
- 若 GUI，必須走 `feedback_gui_node_check_sop` + 對應 GUI write surfaces 28 endpoint 規範
- Sprint 1A engineering 60-80 hr 沒留 GUI 工時

### 3.5 Alpha Tournament dataset readiness check 的 source-of-truth
- Sprint 1B「Alpha Tournament dataset readiness check」用什麼判定 ready？
- v5.7 §3 寫 V103/V104 hypothesis tables — 但表結構（columns）spec 沒落地，影響 Sprint 2 派 QC 工時

---

## 4. 對 PA+FA 匯總的必收 top 3

1. **Sprint 1B C10 live $2,000 在工時 calendar 內不可能合規完成 Stage 1-3 Demo 灰度** — 必收為 PA dispatch hard constraint：Sprint 1B 改 C10 Stage 1 啟動，不寫 live；live 真實時間落 Sprint 3-4
2. **Earn governance 與 5 hard gate boundary 必須明確化** — 必收為 ADR-0030 prerequisite：建議「Earn 沿用全部 5-gate，無例外」，避免出現「Earn 是 asset write 但繞過 live_reserved」漏洞
3. **SHADOW stage 出口條件 + counterfactual A/B acceptance threshold 必須具體公式化** — 必收為 Sprint 2 QC 並行起草任務：Y1 末 review 不能等到 Sprint 10 才討論「+2%」是怎麼算

---

## 5. Sprint 1A 派發前 must-fix

1. **(Risk 2) Earn governance 5-gate boundary 明確化**
   - 修改：v5.7 §4 加「Earn stake/redeem 沿用 CLAUDE §四 5-gate 全部」段落
   - 影響：Sprint 1A 工時 +5-10 hr（governance docs update + ADR-0030 起草）
   - Owner：CC + FA

2. **(依賴 3.2) V103/V104 dispatch 前 Linux PG empirical query**
   - 操作：`ssh trade-core "psql -c 'SELECT max(version), array_agg(version) FROM _sqlx_migrations ORDER BY version DESC LIMIT 10'"`
   - 確認 V101/V102 Track schema 是否 in-flight；若 in-flight，協調 dispatch order
   - Owner：PA + E3

3. **(依賴 3.3) 既有 writer healthcheck SOP 明確化**
   - 修改：v5.7 §6 列出每個「extend existing」對應的具體 healthcheck 命令 + acceptance criteria
   - 範例：market.liquidations writer healthcheck = `passive_wait_healthcheck.py check_liquidation_writer`（如未存在，加入 Sprint 1A scope）
   - Owner：PA + QA

---

## 6. Sprint 1B-3 should-fix

1. **(Risk 1) Sprint 1B C10 改為 Stage 1 Demo 啟動，live 真實落 Sprint 3-4**
2. **Sprint 2 派 QC 起草 counterfactual A/B acceptance threshold spec**（Risk 3 對應）— spec 在 Sprint 10 用，但 Sprint 2 落地，給 6 sprint 累積數據
3. **Sprint 2 派 E1 落地 hypothesis tables column spec**（依賴 3.5）
4. **Sprint 3 雙進程 E2E acceptance plan**（依賴 3.1）— top-1 strategy shadow run 必驗 Python ↔ Rust 1e-4 容差
5. **Sprint 1A 加 4 new sensor 7d 觀察期 calendar**（§0.5 MISSING 列）— 即 sensor 上線後 7d observation window before integration into strategies

---

## 7. 可優化 / 拆分 / 並行

1. **Sprint 1A 拆出「governance + migration」與「sensors」並行**
   - governance + migration (ADR-0006/0029/0030 + V103/V104) ~25 hr，序列依賴 dispatch
   - sensors (4 NEW + 2 healthcheck) ~45 hr，可並行派 E1×2 sub-agents
   - 並行能 Sprint 1A 時間從 W0-1.5 壓到 W0-1（拿回半週 buffer）

2. **counterfactual logger 在 Sprint 1A 就 land schema skeleton**
   - v5.7 §5 工時 70-95 hr 集中 Sprint 2，但 schema (learning.macro_event_log + learning.onchain_signal_log) 可在 Sprint 1A V103 同批落地
   - 拆出 ~10 hr schema land 到 Sprint 1A，Sprint 2 專注 logger 邏輯

3. **Earn governance + Decision Lease 整合可與 trading strategies 共用 helper**
   - v5.7 §4 工時 45 hr 看起來可拆：API integration 15 hr + governance integration 20 hr + audit log 10 hr
   - governance integration 20 hr 若複用 existing Decision Lease pattern（Track H retrofit dbcf845b 既有）可降到 10 hr
   - 拆給 E1 對應 PA 確認 Track H pattern 是否可直接複用

4. **Sprint 2 Alpha Tournament 5 候選並行分析**
   - v5.7 §8 工時 110-150 hr 較密集
   - Unlock / Pairs / C13 / Funding short / C10 enhancement 並行派 QC×5 sub-agents 評估，每個獨立 24 hr
   - 主執行 QC + 4 並行 sub-agent，calendar 從 4w 壓到 2-3w

5. **Sprint 9-10 Y1 review 提前在 Sprint 8 開始 counterfactual evidence 累計**
   - v5.7 §5 寫「Y1 末 evaluate counterfactual evidence」
   - Sprint 8 開始派 QC 跑滾動 counterfactual A/B significance test，Sprint 10 review 可直接拿結果，不需從 0 開始

---

## QA Verdict Summary

**Verdict**：GO-WITH-CONDITIONS

**3 個 must-fix Sprint 1A 派發前完成**：
- Earn governance 5-gate boundary 明確化
- V103/V104 dispatch 前 Linux PG empirical query
- 既有 writer healthcheck SOP 明確化

**1 個 critical Sprint 1B 必修**：C10 改 Stage 1 啟動，不寫 live

**1 個 high Sprint 2 起草**：SHADOW stage 出口 + counterfactual A/B threshold

**派發 OK if 以上 5 項 + 派發前 PA 確認 dependency 3.1/3.2/3.3**。

v5.7 thesis 與 6 reviewer correction 都做對了，這份 audit 不挑戰邏輯，只挑執行性。Sprint 1A 派發前的 must-fix 是「executability ≠ thesis correctness」，所以 GO-WITH-CONDITIONS 而非 NO-GO。

---

**END QA Executability Audit**
