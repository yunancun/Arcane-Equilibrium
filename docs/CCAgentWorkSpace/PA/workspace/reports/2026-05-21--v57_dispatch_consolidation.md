# v5.7 Dispatch-Safe Patch — PA 技術開發方案匯總
**日期**：2026-05-21
**Verdict**：**DISPATCH-NEEDS-FIX**（必須先補 D-1 prerequisite check list 才能 Sprint 1A 派發）
**One-line summary**：v5.7 thesis + 6 reviewer corrections 邏輯端 14/14 agent verified；但執行性層面 12 GO-WITH-CONDITIONS + 2 HOLD (E2/R4) 共識挖出 9 個 CRITICAL 缺口（V103/V104 schema spec / Bybit Earn API endpoint 存在性 / ADR 編號衝突 / TODO Hard precondition / liquidation writer 字典衝突 / Sprint 1B C10 跳 Stage gate / Sprint 1A 工時 30-50% 低估 / GUI 工時 104-151 hr 完全缺席 / PG dry-run mandatory 未寫入），Sprint 1A 派發前必補 12 項 must-fix（72-96 hr 前置工作量），修補後預期 3-5 天內可正式 dispatch。

---

## 0. 14 份 sub-agent verdict 聚合

### 0.1 Verdict 分布

| Verdict | 數 | Agents |
|---|---|---|
| GO-WITH-CONDITIONS | 12 | A3 / AI-E / BB / CC / E3 / E4 / E5 / FA / MIT / QA / QC / TW |
| HOLD | 2 | E2 / R4 |
| NO-GO | 0 | — |

### 0.2 共同 verdict pattern（14 agent 重合度 ≥ 3）

| Pattern | 重合 agent | 出現次數 |
|---|---|---|
| Sprint 1A 60-80 hr 工時系統性低估（修正幅度 1.5-3x） | E2/E3/E4/E5/MIT/QA/QC/TW + A3 GUI 缺 | **9** |
| V103/V104 schema spec 完全 placeholder / 缺 DDL | E2/CC/MIT/E4/FA/QA/TW | **7** |
| PG empirical dry-run mandatory 未寫入 Sprint 1A | E4/MIT/CC/E2/QA | **5** |
| §4 Earn governance 規格層面缺細節（5-gate / IntentProcessor / fail-closed） | CC/QA/E3/FA/E2/MIT | **6** |
| ADR 編號 0028/0029 衝突 + ADR-0006 amendment 缺檔 | R4/TW/CC | **3** |
| TODO Hard precondition 與 v5.7 dispatch-ready 衝突 | E2/R4 | **2**（兩個 HOLD 都標）|
| Bybit Earn API endpoint 存在性未驗 | BB/E2/E3/QC/CC | **5** |
| Counterfactual logger schema / A/B threshold 缺 | MIT/CC/QA/AI-E/QC | **5** |
| Sprint 1B C10 跳 Stage 1-3 Demo 灰度直 live $2,000 | QA/E2/QC | **3** |
| GUI / TW / AI 工時 0 列 | A3/TW/AI-E | **3**（各自不同領域同 pattern） |

### 0.3 兩個 HOLD (E2, R4) 是否阻塞 dispatch

**結論**：HOLD 是 conditional HOLD，不是 NO-GO；阻塞點皆可在 Sprint 1A 派發前 72-96 hr 內補完。

- **E2 HOLD 阻塞點**：V103/V104 schema 缺 DDL + Sprint 1A 工時 30-50% 低估 + TODO §-0 Hard precondition 未解除 + Bybit Earn API 未驗 + C10 LiveDemo vs mainnet 未明
- **R4 HOLD 阻塞點**：ADR-0028/0029 編號被佔用 + ADR-0006 amendment 無對應檔 + AMD 編號漂移 + v5.7 主檔未進 git tree + docs/README.md 缺 v5.x 全系列 index + V104 與 V101 spec 重複

**判定**：上述 13 個 HOLD-blocker 全部屬於 dispatch packet 內容 / governance 編號 / 文件落地 / 路線確認類別，**邏輯無誤、僅 doc/編號漂移**，補完後 HOLD → GO。

---

## 1. Sprint 1A 派發前 must-fix 合併清單（按優先級）

### CRITICAL（缺一不派 Sprint 1A）

| # | 項目 | 來源 agent | 估時 | Owner |
|---|---|---|---|---|
| **C1** | **operator 在 TODO §-0 填入 v5.7 為當前路線 + 解除 V101/V102 Hard precondition + v5.7 主檔搬 `docs/execution_plan/2026-05-20--execution-plan-v5.7.md` + 進 git tree** | E2 R4 | 30 min | PM / operator |
| **C2** | **ADR 編號順移 0028/0029/0030 → 0030/0031/0032**（避開已用編號）+ ADR-0033 新建（ADR-0006 Binance amendment） | R4 TW CC | 12-18 hr（3 ADR 並行 sub-agent draft + ADR-0033 自寫） | TW + CC |
| **C3** | **V103/V104 schema spec 起草**：新建 `docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`，含 hypotheses + hypothesis_preregistration + trading.fills.track + earn_movement_log 四表完整 DDL + Guard A/B/C + idempotency + engine_mode CHECK + retention + index plan + 與 V101 spec consolidation 判斷（V104 是否退號） | MIT E2 CC FA TW | 8-12 hr | PA + MIT |
| **C4** | **Bybit Earn API endpoint 存在性 BB review verdict**：curl + Bybit V5 doc grep + 必要時 Bybit BD 詢問；三選一結論：(a) API exists 15 hr 合理 / (b) web UI only，§4 降級 read-only APR scrape / (c) partial API，scope 重定 | BB E2 E3 QC | 2-4 hr | BB |
| **C5** | **Bybit Earn stake/redeem API key scope 驗證**：必須非 withdraw 才可 programmatic；若需 withdraw → §4 改 manual Web UI only（不違 D1d Hard Boundary） | BB CC E3 | 1-2 hr | BB + E3 |
| **C6** | **liquidation writer 30k+ rows claim factual 核對**：等 W-AUDIT-8a-C1 24h proof verdict（已於 2026-05-15 19:53 啟動）+ MIT schema mapping sign-off；若 PROOF FAIL，§6 整段 fallback 設計 | BB E2 | 2-3 hr | BB + MIT |
| **C7** | **Sprint 1B C10 改為 Stage 0R replay preflight + Stage 1 Demo micro-canary 啟動**（不寫 mainnet live $2,000）— Stage 4 真實 live 落 Sprint 3-4；另：明文 C10 是 LiveDemo 還是真 mainnet（默認 LiveDemo + 等 P0-EDGE-1/LG-3/OPS-1..4 全 closed） | QA E2 FA QC | 1 hr spec 改寫 | PA + FA |
| **C8** | **Earn governance spec 明文 5-gate boundary**：新建 `docs/execution_plan/2026-05-21--earn_governance_spec.md` 明文 (a) Earn stake 復用 `IntentProcessor.submit_intent(intent_type='earn_stake')` 不新建寫入口 (b) Decision Lease 新增 `lease_type=earn_stake/earn_redeem` (c) Bybit Earn API retCode != 0 fail-closed 不重試 (d) Daily reconciliation 失敗自動 disable Earn until manual review (e) 9 安全不變量 #2/#5/#7/#8/#9 全適用 (f) `OPENCLAW_ALLOW_MAINNET` 對 Earn API 適用性（Bybit demo 是否支援 Earn 結論後決定） | CC QA E3 FA MIT | 6-10 hr | CC + FA |
| **C9** | **V103/V104 派發前 Linux PG empirical dry-run**：`ssh trade-core "psql -c 'SELECT max(version), array_agg(version) FROM _sqlx_migrations ORDER BY version DESC LIMIT 10'"` + 列 `information_schema.columns` for `trading.fills` / `learning.*hypotheses*` / `governance.audit_log`；確認 V101/V102 Track schema 是否 in-flight；race-aware sequencing SOP land | E4 MIT QA E2 CC | 1-2 hr | PA |
| **C10** | **Sprint 1A 工時上修 60-80 → 90-130 hr（含 buffer），1B 上修 50-70 → 65-85 hr**；§9 39 週 total 上修為 1,295-1,740 hr（保守 ~1.2x v5.7 估）；同步註明 50-60% workload 必須走並行 sub-agent dispatch 否則 calendar 不可達 | E2 E3 E4 E5 MIT TW QC | 30 min | PM |
| **C11** | **Sprint 1A acceptance criteria 加 Apple Silicon CI tuple 條款**：所有新 Rust crate 必過 `cargo check --target aarch64-apple-darwin`；PA sub-agent prompt 注入；E3 review checklist 加 step | E5 | 30 min | PA |
| **C12** | **派 sub-agent brief 明示「注釋默認只寫中文」**（per 2026-05-05 mandate） + Sprint 1A SCRIPT_INDEX.md 同步 enforce（E2 review 加 `rg -L 'MODULE_NOTE\|模塊用途' <new-files>` = 0 hit PASS） | TW | 30 min | PA |

**CRITICAL 合計**：~36-58 hr（C2 12-18 hr + C3 8-12 hr + C8 6-10 hr 為大頭，其他多為 0.5-4 hr 確認類）；可派 3+ 並行 sub-agent 壓 wall-clock 至 2-3 天。

### HIGH（Sprint 1A 派發後可並行補；Sprint 1B 前 land）

| # | 項目 | 來源 agent |
|---|---|---|
| H1 | A3 GUI 工時表補位：§9 加 GUI 列；Sprint 1A 加 Earn APR readonly viewer 8-12 hr；Sprint 1B 加 Earn stake/redeem UI 16-24 hr；總計 ~104-151 hr | A3 |
| H2 | Console tab 歸屬決策：Earn → `governance` sub-section / Allocator → `agents` sub-section / Counterfactual → `learning` sub-section；不擴張 16 個 tab | A3 |
| H3 | 4 NEW sensor external API key 隔離 policy：`$OPENCLAW_SECRETS_DIR/external/<vendor>/api_key` slot + TTL + fail-closed default + outbound 域名白名單寫進 RiskConfig | E3 |
| H4 | Counterfactual A/B evaluation threshold spec：t-stat ≥ 1.5 + min sample 30+ macro events / 60+ on-chain signals + p-value < 0.05 + decision rule（IF avg_uplift_bps > X AND p < 0.05 across ≥3 strategies → Y2 enable）；Sprint 2 派 QC 並行起草 | CC MIT QC AI-E QA |
| H5 | C10 + Pairs + Funding short-only acceptance criteria 明文化（最小 5 條：入場/size/平倉/rebalance/異常退出）；Sprint 1B 派發前 C10 必先 land | FA |
| H6 | Earn governance runbook：`docs/runbooks/earn_governance_manual_stake_sop.md` 草稿 Sprint 1B 末 land；step-by-step stake intent / Guardian 流程 / audit 字段 / 回滾 | TW |
| H7 | AI-E LLM budget 列入 §9 工時表：Y1 ~$365-565 LLM API cost 明示；§5 macro/on-chain counterfactual logger 對 ContextDistiller 影響評估（700-900 token vs 520）；Layer 1 自動 vs Layer 2 manual 釐清 | AI-E |
| H8 | E4 §測試規劃強制章節：每 sub-task 列 unit/integration/property/concurrency/SLA/cross-language 6 類測試 + baseline 鎖點 (2555 passed / 17 failed 不退) + owner | E4 |
| H9 | E5 baseline profiling task（Sprint 1A 前置）：H0/tick/IPC P50/P95/P99 + RAM/CPU/PG buffer baseline；每 sensor merge 跑 differential benchmark；Sprint 4 入口加 hot path budget check fail-fast gate | E5 |
| H10 | E5 PG buffer footprint 評估：V103/V104 dry-run 加 `pg_total_relation_size` baseline + 預測 6mo size growth | E5 |
| H11 | docs/README.md 補 v5.0/v5.2-v5.7 全系列 + V101/V102 spec + V103/V104 spec + 4 ADR + 2 runbook 索引 | R4 TW |
| H12 | TODO §-0 / §10 補 v5.7-S1A-* task ID + 鏈到 v5.7 文件路徑 + §1 ledger v5.7 foundation 結論 | E2 R4 |
| H13 | v5.7 §11 「14 hard problems」改「6 hard problems from reviewer round 15」或補 round 12-14 audit log path | R4 |
| H14 | v5.7 §13 AMD-01..05 → AMD-2026-05-20-01..05 規範化 + 標 AMD-2026-05-20-05 retract | R4 |
| H15 | Tokenomist trial onboarding + ToS confirm（programmatic scrape 是否允；rate limit；trial 後付費門檻）；BB advisory 確認 trial >= 3 個月覆蓋 Sprint 2 alpha tournament | BB QC |
| H16 | Y1/Y2 income range single source of truth（QC Risk 1）：§2 唯一 anchor，§1 / §10 cite §2；建議 Y2 honest no-overlay $850-1,050 median $935 / overlay verified $1,040-1,100 median $1,070 | QC |
| H17 | Bybit Earn tier 10% promotional rate sustained 驗證：若 introductory only → Y1 Earn $26 → $12 | QC |
| H18 | C10 demo Stage 1-3 不可行解決方案明示：Bybit demo 無 spot lending → 替代路徑（paper spot leg / live small canary / extended Stage 0R replay 三選一） | QC |
| H19 | counterfactual logger payload 訪問控制：log schema 不含 strategy decision payload；GUI viewer 角色禁讀；Copy Trading export pipeline reject `learning.counterfactual_*` join | E3 |
| H20 | Macro Y1 counterfactual-only vs v5.6 §6 Sprint 3 macro overlay activation 內部矛盾收口：Sprint 3 改「Macro counterfactual logger activation」（不接 strategy trigger） | FA |

### MEDIUM/LOW（Sprint 1B-3 should-fix）

- M1 Pairs trading cointegration walk-forward CV + purge + embargo spec（Sprint 2 派 PA 前；MIT）
- M2 Macro/On-chain feature engineering leakage 防範（announcement_ts vs settlement_ts / timezone / shift(1)；Sprint 2 派 PA 前；MIT）
- M3 On-chain free tier rate limit budget per-metric quota + fallback policy（Sprint 1A 末 ping test；CC E3 MIT）
- M4 Allocator monthly proposal viewer 防 rubber-stamp 設計（modal 強制 reward delta 顯示 + 打字確認；A3）
- M5 5 策略並行 capital reservation IPC spec（Sprint 2-3；FA E1）
- M6 Bybit options Sprint 6 timing：6-9 mo 歷史數據 prerequisite → Sprint 1A 開始收集，Sprint 5 W17-19 完成 IV-RV empirical distribution evaluation（QC）
- M7 Sprint 4 C13 Options Stack Phase 1 600 LOC Rust 拆 4 module（< 200 LOC per file；E5）
- M8 Sprint 9 Auto-Allocator Y2 gate 失敗時 advisory 暫停規則（E3）
- M9 Binance WS client 依賴選型固化（tungstenite，避免引新 crate；E3）
- M10 Glassnode free tier rate limit budget 模型 per strategy per fill（E3）
- M11 Master Trader subaccount API key 完全獨立 slot（Sprint 7-9；E3 BB）
- M12 worklogs 自動化模板 + CHANGELOG 同步維護（TW）
- M13 Sprint 8 預埋 counterfactual 4 週滾動快照 narrative report 減 Sprint 10 末 LLM burst（AI-E）

---

## 2. Sprint 1A 內部任務拆分（可並行 dispatch）

Sprint 1A 真實工時 90-130 hr / wall-clock 1.5-2 週需 3+ 並行 sub-agent dispatch。建議拆 5 並行 track：

### Track 1A-gov（governance + spec drafting）— PM + CC + FA + TW
- **工時**：25-30 hr
- **依賴**：無（spec draft 純文，與 code 並行）
- **Deliverable**：
  - C1 TODO §-0 / §1 補填 + v5.7 主檔搬遷 + git tree
  - C2 ADR 0030/0031/0032 + ADR-0033 (ADR-0006 amendment) draft land
  - C8 Earn governance spec land
  - H11/H12/H13/H14 docs/README.md + TODO + AMD 規範化
- **主執行 agent**：TW（ADR 並行 sub-agent×3）+ CC（governance spec）+ FA（cross-ref）+ R4（編號 + index）

### Track 1A-schema（V103/V104 PG dry-run + schema lock）— MIT + PA + E1
- **工時**：15-25 hr
- **依賴**：1A-gov C1 完成（TODO §-0 解除 Hard precondition）+ C9 Linux PG dry-run query 結果
- **Deliverable**：
  - C3 V103/V104 schema spec land（4 表完整 DDL + Guard A/B/C + index）
  - C9 Linux PG empirical query 結果附入 spec
  - V097/V098 catch-up Linux DB（Phase 0）
  - V103/V104 E1 IMPL + Guard 測試 + idempotency 雙跑
- **主執行 agent**：MIT（spec）+ PA（dispatch finalize）+ E1（IMPL）+ E2（review）+ E4（migration test）

### Track 1A-sensor（4 NEW sensor 並行）— BB + E1×4 + E2×2
- **工時**：50-70 hr（最重 track）
- **依賴**：1A-gov C2 ADR-0033 (ADR-0006 amendment) land（含 Binance market data approved + 4 sensor 範圍）
- **Deliverable**：
  - 既有 market.liquidations writer healthcheck（wait 8a-C1 verdict per C6；若 FAIL fallback design）
  - Bybit options chain recorder NEW（25-35 hr 起跳）
  - Binance market-data-only WebSocket NEW（25-35 hr 起跳，tungstenite）
  - Tokenomist unlock calendar NEW（15-25 hr，trial 確認 per H15）
  - Macro calendar feed NEW（12-18 hr，vendor 決策）
  - funding rate aggregator extend + Binance polling
- **主執行 agent**：BB（4 sensor pre-review API + scope）+ E1×4 並行 + E2×2 review + E5（baseline profiling per H9）

### Track 1A-earn（Earn API recorder read-only）— BB + E1 + E3
- **工時**：12-18 hr
- **依賴**：C4 BB Earn API endpoint verdict + C5 scope 驗證
- **Deliverable**：
  - Bybit Earn API APR recorder (read-only, no stake)
  - external sensor credentials policy 落地（H3）
  - APR readonly viewer GUI 8-12 hr（A3 H1 Sprint 1A 部分）
  - earn_movement_log schema spec（V103 子部分 per C3）
- **主執行 agent**：BB（endpoint + scope verdict）+ E1（read-only API client）+ E3（secret slot infra）+ E1a（A3 dispatch GUI）

### Track 1A-gui（GUI 工時補位）— A3 + E1a
- **工時**：8-12 hr（Sprint 1A 部分）
- **依賴**：H2 tab 歸屬決策（與 1A-gov 並行；A3 + PA + operator）
- **Deliverable**：
  - Earn APR readonly viewer mockup + tab 歸屬決策 + ADR-0030 UI 條款補入
  - 16 個 tab 不擴張原則 land
  - Sprint 1B Earn stake/redeem UI 16-24 hr 預埋（Sprint 1A 末 spec land）
- **主執行 agent**：A3（UX checklist）+ E1a（前端 JS）+ PA（dispatch design）

### 並行依賴圖（簡化）

```
[D-1 prerequisite check 完成]
  ↓
[1A-gov C1] TODO Hard precondition 解除
  ↓
  ├─→ [1A-gov C2 ADR draft × 4 並行] ──┬─→ [1A-sensor 5 並行]
  ├─→ [1A-gov C8 Earn spec]            │
  ├─→ [1A-schema C9 PG dry-run]        │
  │     ↓                              │
  │   [1A-schema C3 V103/V104 spec]    │
  │     ↓                              │
  │   [1A-schema IMPL + test]           │
  │                                    │
  └─→ [1A-earn C4/C5 BB verdict]      │
        ↓                              │
      [1A-earn 整合]                   │
                                       │
[1A-gui 並行]──────────────────────────┘
```

5 track 並行最大化後，Sprint 1A wall-clock 約 1.5-2 週（vs 工時 90-130 hr 折算單 E1 約 2.5-3 週）。

---

## 3. 工時 sanity 上修共識

### 3.1 14 agent 工時觀點聚合

| Sprint | v5.7 §9 估 | 14 agent 觀點 | PA 建議 |
|---|---|---|---|
| 1A | 60-80 hr | E2 110-155 / E3 70-90 / E4 75-100 / E5 120-180 / MIT 75-100 / QA +30-45 / QC 80-100 / TW +30 / BB 90-130 / A3 +8-12 GUI | **90-130 hr**（含 1.5x 修正 buffer） |
| 1B | 50-70 hr | E2 60-85 / E3 +5 / E4 60-85 / QA 80-120 / QC 50-70 / TW +15 / MIT 55-75 / A3 +16-24 GUI | **65-85 hr** |
| 2 | 110-150 hr | E2 140-200 / E4 130-180 / E5 330-450 (3x) / MIT 130-180 / QA +20-30 / TW +15 / AI-E +60-90 LLM | **140-200 hr** |
| 3 | 130-160 hr | E2 130-180 / E4 145-180 / E5 390-480 (3x) | **145-180 hr** |
| 4 | 160-210 hr | E2 200-260 / E4 185-245 / E5 480-630 (3x) | **185-245 hr** |
| 5-10 合計 | 580-790 hr | E4 +90-120 / E5 ~1.0x | **660-880 hr** |
| **Total** | **1,190-1,590 hr** | E2 1,450-1,900 / E4 1,295-1,740 / E5 3,570-4,770 (3x) / MIT 1,250-1,650 / TW +68-95 / A3 +104-151 GUI / AI-E +$365-565 LLM | **1,295-1,740 hr**（保守 ~1.2x；不含 LLM API cost；含 GUI/TW；E5 3x 視為「若無 sub-agent 並行」上界） |

### 3.2 PA 建議（聚合判斷）

- **Sprint 1A 60-80 → 90-130 hr**（共識最高，9/14 agent 提；含 PG dry-run buffer + ADR draft + spec land + Earn 60-pre-review + GUI 8-12 hr）
- **Sprint 1B 50-70 → 65-85 hr**（含 Earn governance e2e + C10 Stage 0R 而非 mainnet live）
- **Y1 total 1,190-1,590 → 1,295-1,740 hr**（保守 ~1.2x，含 GUI 104-151 + TW 68-95 + Apple CI buffer + counterfactual A/B; **不含** LLM API cost ~$365-565）
- **calendar 39 週硬約束**：必須承諾 50-60% workload 走並行 sub-agent dispatch，否則不可達
- **E5 3x/7x estimate 視為「single-thread」上界，不採用作 baseline**（與 operator 5-10x 規律一致但不等於 calendar fail）

---

## 4. 技術依賴 / 阻塞清單

### 4.1 外部依賴（必須在 Sprint 1A 派發前 driver 確認）

| 依賴 | 狀態 | Driver | 阻塞 Sprint |
|---|---|---|---|
| **Bybit Earn API endpoint 存在性** | UNKNOWN（字典 0 entries） | BB + operator | 1A C4 |
| **Bybit Earn stake/redeem API key scope** | UNKNOWN（需驗 transfer vs withdraw） | BB + E3 | 1A C5 |
| **Bybit demo endpoint Earn 支援** | 推測不支援（per memory funding_arb_v2 教訓） | BB | 1B Earn first stake |
| **Bybit Earn first tier 10% promotional rate sustained** | UNKNOWN | BB + QC | 1A H17 |
| **Tokenomist trial credentials TTL + ToS + rate limit** | UNKNOWN | operator + BB | 1A + 2 alpha tournament |
| **Glassnode / Etherscan / DeFiLlama free tier rate limit** | partial known（GN 60 req/day per metric） | E3 + AI-E | 2 on-chain counterfactual |
| **Macro calendar feed vendor 選型**（FRED / trading economics / investing.com） | UNKNOWN | MIT + BB | 1A macro feed NEW |
| **W-AUDIT-8a-C1 24h proof verdict**（2026-05-15 19:53 啟動） | PROOF RUNNING | BB + MIT | 1A C6（liquidation writer healthcheck） |
| **Bybit Cadet tier subaccount 90d 連續 P&L** | Y2 之後 | BB + operator | Sprint 9-10 Copy Trading |
| **Binance market data ToS**（內部分析 + counterfactual OK；對外展示 wait Y2 review） | known | BB | 4-7 Top-N |
| **AMD-2026-05-15-01 active 狀態 + Stage gate verbose 條款** | EXISTS（per R4） | FA + CC | 全期 Stage transition |

### 4.2 內部依賴

| 依賴 | 狀態 | 阻塞 |
|---|---|---|
| **P0-EDGE-1 / P0-LG-3 / P0-OPS-1..4 closure**（TODO L103 Live deploy hard precondition） | ACTIVE | Sprint 1B C10 live deploy（per C7 改為 LiveDemo） |
| **AI-E E.1 writer path 修復**（ai_invocations 寫 Strategist L1 9B 流量） | OPEN | counterfactual logger LLM cost KPI 可量測 |
| **DecisionLease lease_id_to_idx HashMap leak P1-LEASE-1** | ACTIVE，依賴 LG-3 IMPL | Earn movement Lease 放大影響面 |
| **AMD-2026-05-09-02 §4 Layer2 永久 manual-only** | ACTIVE | counterfactual logger Layer 1 自動 vs Layer 2 manual 衝突 |

---

## 5. GUI 工時補完方案（per A3）

### 5.1 §9 工時表加 GUI 列（PA 建議）

| Sprint | v5.7 §9 估 | GUI 工時補位 | 用途 |
|---|---|---|---|
| 1A | 60-80 hr | **+8-12 hr** | Earn APR readonly viewer + tab 歸屬決策 |
| 1B | 50-70 hr | **+16-24 hr** | Earn stake/redeem manual UI + 二次確認 modal + audit log viewer |
| 4 | 160-210 hr | **+10-15 hr** | Top-1 live 策略卡片 + macro overlay status badge |
| 5-6 | 290-380 hr 合 | **+25-35 hr** | Multi-strategy aggregate dashboard（5 strategy traffic-light grid） |
| 7 | 110-150 hr | **+20-30 hr** | Allocator monthly proposal viewer + diff view + approve/reject form + 防 rubber-stamp |
| 8 | 110-150 hr | **+15-20 hr** | Counterfactual A/B viewer + decay detector alert |
| 10 | 70-100 hr | **+10-15 hr** | Y1 review aggregator + copy trading evidence gate dashboard |
| **總計** | — | **~104-151 hr** | **約 v5.7 總工時 8-10%** |

### 5.2 Console tab 結構決策（不擴張 16 個 tab）

| 功能 | 落點 | 理由 |
|---|---|---|
| Earn stake/redeem UI | `governance` tab → `Asset Movement (Earn)` sub-section | governance 是 Decision Lease 列表；Earn = asset write 同性質 |
| Allocator monthly proposal | `agents` tab → `Allocator Proposals` sub-section | agents 已有 proposal relay 基礎 |
| Counterfactual A/B viewer | `learning` tab → `Counterfactual Evidence` sub-section | learning 是學習指標 |
| 5-strategy aggregate dashboard | `system` tab 既有總覽升級 | 不新增 tab |
| Macro overlay state badge | `live` tab 持倉卡片右上角 | inline badge 不擴展 |

### 5.3 防 rubber-stamp（per A3）

- Allocator approve modal 強制顯示「上月 reward 實際 vs predicted Δ」+ operator 打字「reviewed reward breakdown」短語
- Y2 auto-activation gate「>80% approval rate」附副指標（modal 停留時間 + 改 weight 比例）
- 純 click-through approval 不計入 gate 通過

---

## 6. ADR 編號衝突修法（per R4）

### 6.1 現況

| ADR | 已佔用 | 來源 |
|---|---|---|
| ADR-0028 | close-maker-fallback-reason-dead-enum-reservation | 2026-05-21 Accepted-pending-commit（TODO §12.4 C 批 closure；FA SPEC-1） |
| ADR-0029 | market.public_trades + market.orderbook_l2_snapshot Storage Policy | 2026-05-21 Proposed（FA EVID-1） |
| ADR-0030 | （NUMBER FREE） | — |

### 6.2 修法

| v5.7 §11 / §12 提案 | 新編號 | 內容 |
|---|---|---|
| ADR-0028 (proposed) Copy Trading evidence-gated | **ADR-0030** | Y1 末 4-gate evaluation + Y2 enable 條件 |
| ADR-0029 (proposed) Framework expansion | **ADR-0031** | Earn governance + macro counterfactual + on-chain counterfactual |
| ADR-0030 (proposed) Bybit Earn Guardian policy | **ADR-0032** | Earn asset movement Guardian + 5-gate adapter + Decision Lease + audit log |
| ADR-0006 amendment（無對應檔） | **ADR-0033** | ADR-0006 Binance market data approved + Binance trading defer Y2 + DEX/Hyperliquid NOT approved + D12 + ToS |

### 6.3 ADR / AMD 命名規範化

- v5.7 §12「ADR-0024-lite」→ 統一改 `ADR-0024`（或於該 ADR 補 "lite" 命名 amendment）
- v5.7 §13 「AMD-01 through AMD-05」→ **`AMD-2026-05-20-01..05`** 全名 + 標 AMD-2026-05-20-05 retract
- v5.7 §11 「14 hard problems from reviewer rounds 12-15」→ 改「6 hard problems from reviewer round 15」（若 round 12-14 audit log 不存在）

### 6.4 docs/README.md index 補

- v5.0 / v5.2 / v5.3 / v5.4 / v5.5 / v5.6 / v5.7 全系列
- V101/V102 spec + V103/V104 spec
- ADR-0028 (close-maker) / 0029 (trade tape) / 0030 / 0031 / 0032 / 0033

---

## 7. V103/V104 schema spec 草案要求（per MIT + E4 + CC）

### 7.1 文檔路徑

`docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`（仿 V101/V102 spec 範式）

### 7.2 字段定義（4 表完整 DDL）

#### Table 1: `learning.hypotheses`
- `hypothesis_id` PK BIGSERIAL
- `strategy_name` TEXT NOT NULL
- `pre_reg_ts` TIMESTAMPTZ NOT NULL
- `pre_reg_hash` TEXT NOT NULL（git-style content hash）
- `status` ENUM ('draft', 'preregistered', 'shadow', 'stage_0r', 'stage_1', 'stage_2', 'stage_3', 'stage_4', 'live', 'retired', 'killed')
- `expected_sharpe` REAL
- `expected_dd` REAL
- `capacity_estimate_usdt` BIGINT
- `t_stat_min` REAL（pre-registration 預期）
- `min_sample_size` INTEGER
- `engine_mode` TEXT CHECK (engine_mode IN ('paper','demo','live','live_demo'))
- `created_at` TIMESTAMPTZ DEFAULT NOW()
- `updated_at` TIMESTAMPTZ
- index: (strategy_name, status), (pre_reg_ts DESC)

#### Table 2: `learning.hypothesis_preregistration`
- `preregistration_id` PK BIGSERIAL
- `hypothesis_id` FK → hypotheses
- `payload_json` JSONB NOT NULL（pre-registration content）
- `payload_hash` TEXT NOT NULL
- `operator_signature` TEXT
- `signed_at` TIMESTAMPTZ
- `engine_mode` TEXT CHECK
- index: (hypothesis_id, signed_at DESC)

#### Table 3: `trading.fills.track` (ADD COLUMN)
- `track` TEXT NULL（track A/B/C/D/E per V101 spec scope）
- **CONSOLIDATION**：若 V101 spec 已 ALTER trading.fills.track，**V104 退號**（per R4 + MIT 建議）；PA dispatch 時 final 判定

#### Table 4: `learning.earn_movement_log`
- `movement_id` PK BIGSERIAL
- `event_ts` TIMESTAMPTZ NOT NULL
- `direction` ENUM ('stake', 'redeem')
- `amount_usdt` NUMERIC(18,8) NOT NULL
- `apr_at_time` REAL
- `governance_approval_id` BIGINT FK → governance.audit_log
- `bybit_response_payload` JSONB
- `engine_mode` TEXT CHECK
- `api_scope_used` TEXT（per BB H1）
- `reconciliation_status` ENUM ('pending', 'matched', 'mismatch')
- index: (event_ts DESC), (governance_approval_id)

### 7.3 Guard A/B/C 適用

- Guard A: `CREATE TABLE IF NOT EXISTS` for hypotheses + hypothesis_preregistration + earn_movement_log
- Guard B: type-sensitive ADD COLUMN for trading.fills.track（若 V104 不退號）
- Guard C: hot-path index for hypotheses (strategy_name, status)

### 7.4 TimescaleDB hypertable 判斷

- `hypotheses`：regular table（low row count, no time partition needed）
- `hypothesis_preregistration`：regular table
- `trading.fills.track`：既有 hypertable，不變動
- `earn_movement_log`：regular table（per stake/redeem event，預期 < 10/yr）

### 7.5 PG dry-run mandatory steps（per C9）

```bash
ssh trade-core "psql -c 'SELECT max(version), array_agg(version) FROM _sqlx_migrations ORDER BY version DESC LIMIT 10'"
ssh trade-core "psql -c \"SELECT table_schema, table_name, column_name, data_type FROM information_schema.columns WHERE table_schema IN ('learning', 'trading') AND (table_name LIKE '%hypothes%' OR column_name = 'track') ORDER BY table_schema, table_name\""
ssh trade-core "psql -c \"SELECT pg_total_relation_size(schemaname || '.' || tablename) / 1024 / 1024 AS mb, schemaname, tablename FROM pg_tables WHERE schemaname IN ('learning','trading','governance') ORDER BY mb DESC LIMIT 20\""
```

### 7.6 與 V101/V102 spec consolidation 判斷

- V101 spec v3 §1 已 ALTER 12 表加 `track` column；V104 之 `trading.fills.track` **直接退號**（V104 → no-op）
- 若 V101 spec 在 Sprint 1A in-flight 未完，V103 獨立 land；V104 等 V101 closure 後決定（retract or 重編）

---

## 8. 安全 / Bybit / 合規硬要求（per E3 + BB + CC）

### 8.1 Earn 5-gate 邊界明示（per C8 spec）

```
Earn stake/redeem 必經：
(a) Operator role auth (Python live_reserved + role check)
(b) signed authorization.json (env_allowed includes 'earn-write')
(c) Decision Lease (lease_type='earn_stake' or 'earn_redeem')
(d) Guardian Risk Envelope check (same as trading)
(e) audit log 同步寫 learning.earn_movement_log

5-gate 中 OPENCLAW_ALLOW_MAINNET：
- 若 Bybit demo 支援 Earn → demo/live 兩環境都需 mainnet=1 only for live
- 若 Bybit demo 不支援 Earn → live env 必需 mainnet=1（嚴於 trading）

OPENCLAW_ALLOW_MAINNET=1 + secret slot 4-gate 全強制（無例外）。
```

### 8.2 Earn API retCode != 0 fail-closed（per 9 不變量 #7 延伸）

- Bybit Earn API 超時 → fail-closed，不重試
- retCode != 0 → fail-closed，audit log 寫 governance event_type='earn_api_failure'
- 連續 3 次失敗 → 自動 disable Earn until manual review（不降級 paper，因 paper not active）

### 8.3 Daily reconciliation 失敗降級邏輯

- `learning.earn_movement_log.reconciliation_status` = 'mismatch' → 自動 disable next stake/redeem
- diff > 0.01 USDT → alert + operator review required
- 連續 3 天 mismatch → halt strategy（per kill criteria）

### 8.4 9 安全不變量對 Earn 路徑明示

| # | 不變量 | Earn 適用 |
|---|---|---|
| 1 | Pre-trade audit/replay 必開 | Earn = asset write event，audit log 強制 |
| 2 | Lease 必在執行前 acquired | `lease_type='earn_stake/earn_redeem'` 復用 lease 框架 |
| 3 | 執行回報必落 fills 表 | Earn 走 `learning.earn_movement_log`（不是 trading.fills）|
| 4 | 風控降級 → engine 自動止血 | margin < 30% auto-redeem + global kill criteria |
| 5 | Authorization 過期/失效 → cancel_token shutdown | Earn 操作走同一 cancel_token 路徑 |
| 6 | Mainnet 無 OPENCLAW_ALLOW_MAINNET → spawn 拒絕 | Earn 路徑也適用（per C8） |
| 7 | Bybit retCode != 0 → fail-closed | per 8.2 |
| 8 | Reconciler 對賬差異 → 降級 | per 8.3（Earn 走 "disable until manual review" 非 "降級 paper"） |
| 9 | Operator 角色 + live_reserved 缺一即拒 | Earn 路徑強制（per C8 gate a） |

### 8.5 4 NEW sensor external API key 隔離（per H3）

- 路徑：`$OPENCLAW_SECRETS_DIR/external/<vendor>/api_key`
- vendor list：glassnode / etherscan / defillama / tokenomist
- 禁 .env / config TOML embed
- Trial credentials TTL 寫 `learning.external_credential_expiry`，到期前 14d audit warning
- Fail-closed default（外部 API 不通 → sensor degraded mode, feature emit NULL）
- Outbound 域名白名單寫 `RiskConfig.external_sensor_whitelist`

---

## 9. 給 operator 的最終 dispatch verdict

### 9.1 Sprint 1A 派發 readiness：**DISPATCH-NEEDS-FIX**

**判定理由**：
- 14 agent 邏輯端 14/14 verified
- 但 12 個 CRITICAL must-fix（§1）需在 Sprint 1A 派發前 land
- 修補後預期 3-5 天內可正式 dispatch
- HOLD 兩個 agent (E2/R4) 的阻塞點皆屬 dispatch packet / 編號 / 文件落地類，**邏輯無誤**

### 9.2 修補後預期可派發時間：**D+3 ~ D+5**（72-120 hr 內）

並行 dispatch 最大化：
- Day 0：operator C1 簽核 + ADR 順移簽核 + 派 5 並行 sub-agent task
- Day 1-2：1A-gov（3 ADR + Earn spec + ADR-0033）+ 1A-schema spec land + BB Earn endpoint verdict
- Day 3：cross-review + V103/V104 IMPL spec finalize + Linux PG dry-run + 8a-C1 verdict 收口
- Day 4-5：Sprint 1A 正式 dispatch

### 9.3 派發 prerequisite check list（D-1 prerequisite）

| # | Check | 狀態 |
|---|---|---|
| 1 | operator 在 TODO §-0 填入 v5.7 為當前路線 + 解除 V101/V102 Hard precondition | □ |
| 2 | v5.7 主檔搬 `docs/execution_plan/2026-05-20--execution-plan-v5.7.md` + 進 git tree | □ |
| 3 | ADR 編號順移 0028/0029/0030 → 0030/0031/0032 + ADR-0033 新建（共 4 ADR draft land） | □ |
| 4 | V103/V104 schema spec land（含 4 表 DDL + Guard A/B/C） | □ |
| 5 | Bybit Earn API endpoint 存在性 BB verdict（三選一結論明示） | □ |
| 6 | Bybit Earn stake/redeem API key scope 驗證（非 withdraw 確認） | □ |
| 7 | W-AUDIT-8a-C1 24h proof verdict 收口 + liquidation writer 30k+ rows claim 核對 | □ |
| 8 | Sprint 1B C10 改 Stage 0R + Stage 1 Demo（不寫 mainnet live） | □ |
| 9 | Earn governance spec land（5-gate + IntentProcessor 復用 + fail-closed） | □ |
| 10 | Linux PG empirical dry-run query 結果附 V103/V104 spec | □ |
| 11 | Sprint 1A 工時上修 60-80 → 90-130 hr + §9 total 1,295-1,740 hr | □ |
| 12 | Apple Silicon CI tuple 條款 + 中文注釋 mandate 寫入 dispatch brief | □ |

### 9.4 Sprint 1A dispatch packet 草案結構

```
srv/docs/execution_plan/
├── 2026-05-20--execution-plan-v5.7.md          [v5.7 主檔，搬遷後]
├── 2026-05-21--v103_v104_earn_hypotheses_schema_spec.md  [C3]
├── 2026-05-21--earn_governance_spec.md         [C8]
└── 2026-05-21--sprint_1a_dispatch_packet.md    [本派發 packet]

srv/docs/adr/
├── 0030-copy-trading-evidence-gated.md         [draft]
├── 0031-framework-expansion-earn-macro-onchain.md  [draft]
├── 0032-bybit-earn-asset-movement-guardian.md  [draft]
└── 0033-adr-0006-bybit-binance-amendment.md    [新建]

srv/docs/runbooks/
└── earn_governance_manual_stake_sop.md         [Sprint 1B 末 land，但 spec 預埋]
```

派發 packet 內容大綱：
1. v5.7 reference + 5 reviewer condition met confirmation
2. Sprint 1A 5 track 並行任務矩陣（per §2）
3. 每 track owner + deliverable + acceptance criteria
4. 工時上修 + LLM budget 明示
5. Apple Silicon CI tuple + 中文注釋 mandate
6. 12 個 D-1 prerequisite check list
7. Sprint 1A → 1B gate 條件（V103/V104 land + Linux _sqlx_migrations head=V104 + Earn APR recorder 24h 真有 row + healthcheck 12 個 check 全 PASS）

---

## 10. 下一步具體行動

### 10.1 operator 立即確認（D+0 ~ D+0.5）

1. **批准 12 個 CRITICAL must-fix 為 Sprint 1A 派發前置條件**（§1 CRITICAL）
2. **批准 ADR 編號順移 0030/0031/0032 + ADR-0033**（§6）
3. **批准 Sprint 1A 工時上修 60-80 → 90-130 hr + §9 total 1,295-1,740 hr**（§3）
4. **批准 Sprint 1B C10 改 Stage 0R/Stage 1 Demo**（不寫 mainnet live；§1 C7）
5. **批准 GUI 工時補位 ~104-151 hr 寫入 §9**（§5）
6. **TODO §-0 填入 v5.7 為當前路線 + 解除 V101/V102 Hard precondition**

### 10.2 PM 立即派發（D+0 ~ D+1）

1. **派 TW + 3 並行 sub-agent draft ADR 0030/0031/0032**（C2，12-18 hr）
2. **派 CC + FA draft Earn governance spec**（C8，6-10 hr）
3. **派 MIT + PA + E1 draft V103/V104 schema spec**（C3，8-12 hr）
4. **派 BB driver Bybit Earn API endpoint verdict + scope 驗證**（C4 + C5，3-6 hr）
5. **派 BB + MIT 收 W-AUDIT-8a-C1 verdict**（C6，2-3 hr）
6. **派 R4 + TW 補 docs/README.md index + AMD 規範化**（H11 + H13 + H14，3-5 hr）
7. **派 A3 + PA + operator 完成 tab 歸屬決策**（H2，1-2 hr）

### 10.3 PA 並行（D+1 ~ D+3）

1. **dispatch packet 草案 finalize**（§9.4）
2. **Linux PG empirical dry-run + V103/V104 spec finalize**（C9 + C3）
3. **Sprint 1A 5 track 派發 brief 寫定**（§2）
4. **E5 baseline profiling task land**（H9）

### 10.4 D+5 正式派發

1. Sprint 1A 5 track 並行 dispatch（3+ sub-agent 同時）
2. 每 track owner 簽 deliverable acceptance
3. Sprint 1A → 1B gate 條件 watch
4. 持續 watch H-level should-fix（Sprint 1A 進行中並行補）

---

## 11. PA 結論

v5.7 thesis 與 6 個 reviewer corrections **邏輯端完全正確且 14/14 agent verified**。

**問題集中在執行性層面**：
1. dispatch packet 完整度不足（V103/V104 schema spec + Earn governance spec + ADR draft 全缺）
2. 編號 / 文件落地漂移（ADR-0028/0029 衝突 + ADR-0006 amendment 缺檔 + v5.7 主檔未進 git tree）
3. 工時系統性低估（Sprint 1A 30-50% / Y1 total ~10% / GUI 104-151 hr / TW 68-95 hr / LLM ~$365-565 全未列入）
4. 外部依賴未驗（Bybit Earn API endpoint 存在性 + scope + demo 支援 + Tokenomist trial + Bybit Earn 10% promotional sustained）
5. 安全規格不足（Earn 5-gate / 9 不變量 #7 延伸 / counterfactual log access control）

**修補建議**：72-120 hr 內完成 12 個 CRITICAL must-fix（並行 sub-agent dispatch 最大化），D+5 正式 Sprint 1A 派發。

**DISPATCH-NEEDS-FIX**（不是 NO-GO，不是 ready-to-go）。

---

**PA DESIGN DONE: report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v57_dispatch_consolidation.md**
