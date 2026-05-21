# v5.7 Dispatch-Safe Patch 執行性審核 — MIT 視角

**日期**：2026-05-21
**Verdict**：GO-WITH-CONDITIONS
**One-line summary**：v5.7 修正 v5.6 6 個工程精度漂移正確，但 §3 schema spec 過於抽象（V103/V104 字段/index/Guard 全 placeholder）+ 缺 PG dry-run 強制條款，Sprint 1A 派 PA 前必補 schema spec 細節與 hr 估算重做。

---

## 0. Schema / Migration 完整度

| 項目 | 狀態 | 證據 |
|---|---|---|
| V103 (hypotheses + hypothesis_preregistration) | **SPEC MISSING（placeholder only）** | v5.7 §3 line 121「V103: NEW v5.7 schema」+ 「PA dispatch confirms final numbers」；無 column list / type / index / Guard 設計；無 SPEC doc 在 `docs/execution_plan/` |
| V104 (trading.fills.track ADD column) | **SPEC PARTIAL（subset of V101 work）** | v5.7 §3 line 122「subset of V101 work; PA may consolidate」；v101_v102 spec line 18 已含 trading.fills + track column；v5.7 沒講與 V101 衝突／合併規則 |
| PG dry-run mandatory | **MISSING** | v5.7 全文 0 處提 Linux PG empirical dry-run；feedback_v_migration_pg_dry_run.md（V055 5-round loop 教訓）未在 v5.7 §3 / §8 引用；Sprint 1A engineering 60-80 hr 未含 dry-run 時數 |
| Guard A/B/C 套用承諾 | **MISSING** | v5.7 §3 0 處提 Guard；CLAUDE.md §七 強制規範未在 v5.7 載明套用 |
| `learning.earn_movement_log` schema | **MISSING (only mentioned by name)** | v5.7 §4 line 158 提表名 + 字段「amount, direction, APR at time, governance approval」，但無 column type / hypertable 判斷 / Guard / index 設計 |
| counterfactual_log schema | **MISSING** | v5.7 §5 macro/on-chain counterfactual logger 提概念，0 schema spec |
| **Pre-existing fact check** | V097/V098 **已存在於 repo**（V097 attribution healthcheck indexes / V098 audit_log halt event types） | v5.7 §3 line 117「V097, V098: catch-up on Linux DB」用詞正確（Linux 仍 head=V096）但需明示 repo head 與 Linux head drift |
| **市場 schema fact check** | `market.liquidations` 表 + writer 確實存在 | V002 line 214 CREATE TABLE / V005 line 63 index / V006 line 35 compression policy / `market_writer.rs:flush_liquidations` line 462；v5.7 §6 reviewer §3 fix 描述完全正確 |

## 0.5 ML pipeline maturity（5 階段 評級）

對 v5.7 新增 ML/data component 評級（**設計階段**評，不是 runtime 評）：

| Component | Writer 設計? | Consumer 設計? | Row 累積規劃? | Decision impact? | Stage（v5.7 設計後預期）|
|---|---|---|---|---|---|
| Counterfactual logger (macro) | Vague (§5「counterfactual logger」無 schema) | Y1 末 A/B framework 待 spec | spec missing | Y1 NOT 影響真實決策（明確） | **Foundation only** — 規劃對但 schema 缺 |
| Counterfactual logger (on-chain) | 同上 | 同上 | spec missing | Y1 NOT 影響真實決策 | **Foundation only** |
| `earn_movement_log` | §4 提字段名單 | Daily reconciliation 提概念 | 預期低（per stake/redeem event）| Guardian 走 Decision Lease（架構級對） | **Skeleton-ready spec needed**（Guardian/Lease 路徑已 land in REF-20 Sprint 3 Track H）|
| Macro feed | NEW Sprint 1A | overlay Y2 才整合 | daily-ish events（FOMC×8 + CPI×12 + halving×1 + listings + unlocks） | counterfactual only Y1 | **Foundation** |
| On-chain signals | NEW Sprint 2 | overlay Y2 才整合 | rate-limited free tier | counterfactual only Y1 | **Foundation** |
| Bybit Earn APR recorder | NEW Sprint 1A read-only | Earn governance Sprint 1B | low (per rebalance) | manual rebalance first 3mo | **Foundation→Skeleton 1A→1B** |
| Alpha Tournament dataset | Sprint 1B prep / Sprint 2 build | rank → Sprint 3 build top-1 | one-shot analysis | drives build order | **Skeleton (pre-registration)** |
| Cointegration Pairs analysis | Sprint 2 | Sprint 4-7 pairs strategy build | rolling 15m/1h | drives pairs trade | **Shadow-ready spec**（v5.6 §7 提，v5.7 §8 1B 未提具體 CV 設計）|

---

## 1. Top 3 執行性風險（排序）

### Risk 1：V103/V104 schema spec 為 placeholder，Sprint 1A 派 PA 後仍需現場補設計

- 嚴重度：**CRITICAL**
- 位置：v5.7 §3 整段
- 描述：v5.7 §3 反覆強調「PA dispatch confirms final numbers」「v5.7 spec uses V103/V104 placeholder」 — 但完整 schema spec（column name / type / index / Guard A/B/C / hypertable 判斷 / retention / engine_mode CHECK）整段空白。PA 收到 dispatch brief 後將被迫現場補設計，這正是 V055 5-round loop（feedback_v_migration_pg_dry_run.md）的同類風險。
- 為何屬「執行性」（非邏輯）：v5.6 已決策 thesis（hypotheses + preregistration + track column），v5.7 也接受該決策；風險不在「該不該做」而在「dispatch 收到 brief 後 PA 是否能直接 IMPL 而不被卡」。
- Must-fix 建議：
  1. v5.7 §3 增補 V103 完整 column inventory（hypotheses 表：hypothesis_id PK / strategy_name / pre_reg_ts / pre_reg_hash / status enum / expected_sharpe / expected_dd / capacity_estimate / 等）+ Guard A 套用承諾
  2. 增補 V104：明確與 V101 (track schema 12 表) 的 trading.fills.track 是「同一 column」還是「不同 column」；若同，明確 V104 = V101 子集 → 等 V101 land 後 V104 變 no-op；若不同，column 命名衝突風險高
  3. 增補 `docs/execution_plan/2026-05-21--v103_v104_schema_spec.md`（仿 v101_v102 spec 範式）作為 Sprint 1A 派 PA 的 hard precondition

### Risk 2：PG dry-run mandatory 規範未在 v5.7 §3 / §8 寫入

- 嚴重度：**HIGH**
- 位置：v5.7 §3、§8 Sprint 1A
- 描述：MIT memory `feedback_v_migration_pg_dry_run.md`（V055 retrofit 5-round 教訓）明示「Before E1 dispatch for any V### migration: PM (or PA) must do Linux PG dry-run」— v5.7 §3 / §8 全文 0 處引用此規範。Sprint 1A engineering 60-80 hr 不含 PG dry-run 時數（V103 + V104 + V097/V098 catch-up 共 4 migrations）。歷史教訓：每個 V### 若沒 dry-run 平均多花 3-5 round（每 round ~4-8 hr）= 12-40 hr/migration 浪費。
- 為何屬「執行性」：規範本身已存在 governance memory（不需新邏輯討論）；缺的是 v5.7 把它寫入 Sprint 1A dispatch brief。
- Must-fix 建議：
  1. v5.7 §3 末段增補一段「PG dry-run mandatory before E1 IMPL」，引用 feedback_v_migration_pg_dry_run.md + CLAUDE.md §七 Data Migrations And Validation 條款
  2. Sprint 1A engineering hours 增加 8-12 hr buffer（4 migrations × 2-3 hr empirical query + design review）
  3. PA dispatch brief 增 4 條 ssh PG query：列 `information_schema.columns` for `trading.fills` / `learning.*hypotheses*` / `governance.audit_log`；列 `_sqlx_migrations` head；列 reflection function output（如 v55 教訓的 `pg_get_function_identity_arguments`）

### Risk 3：counterfactual logger schema 完全 missing，Sprint 2 70-95 hr 估算缺結構性依據

- 嚴重度：**HIGH**
- 位置：v5.7 §5（macro/on-chain counterfactual）+ §9 Sprint 2 工時
- 描述：v5.7 §5 line 196-200 列「Macro feed + counterfactual logger: 25-35 hr / On-chain feed + counterfactual logger: 30-40 hr / A/B evaluation framework: 15-20 hr」共 70-95 hr。但 counterfactual logger 表的：(a) row 量級評估（macro 8 FOMC + 12 CPI + 4 halving-related × 25 symbol × 5 strategy ≈ 3000 row/yr；on-chain free tier rate-limited 1 req/min × per signal ≈ 1.5M/yr）→ 需不需要 hypertable？(b) feature engineering 防 leakage：macro event timestamp 是 announcement_ts 還是 settlement_ts？跨 timezone 嗎？(c) counterfactual A/B framework 是 walk-forward / Purged k-fold / CSCV？— v5.7 全無 schema spec 也無 CV 方法論。
- 為何屬「執行性」：v5.7 同意「Y1 counterfactual only」（thesis 正確），但 70-95 hr 估算沒有對應 schema 設計依據 → IMPL 期 PA 又會踩 V055 同類坑。
- Must-fix 建議：
  1. Sprint 2 dispatch brief 補 counterfactual_log 最小 schema spec（columns: log_ts / event_type enum / event_ts / strategy_name / symbol / signal_value / actual_decision / counterfactual_decision / outcome_ts / outcome_pnl / engine_mode CHECK）
  2. CV 方法論引用：look-ahead 防範必引 `feature-engineering-protocol`（macro event 用 announcement_ts 不用 settlement_ts；on-chain block_ts 必 UTC）
  3. Sprint 2 工時若加 schema spec + CV design + Guard A 套用 → 預計 +10-15 hr buffer

---

## 2. Hours sanity check（schema / ML pipeline 工時 vs estimate）

| Sprint | v5.7 estimate | MIT 估 | 差距 RCA |
|---|---|---|---|
| 1A schema (V097/V098 catch-up + V103/V104 + 4 sensor recorders) | 60-80 hr | **75-100 hr** | 4 migrations × 2-3 hr PG dry-run = +8-12 hr / V103/V104 spec 補設計 = +4-6 hr / Bybit Earn APR recorder 是新表（v5.7 line 280 未估）= +5-8 hr |
| 1B C10 live + Earn governance | 50-70 hr | **55-75 hr** | Earn governance（Guardian + Decision Lease）已有架構（REF-20 Sprint 3 Track H dbcf845b）→ 整合估算 OK；C10 minimal viable 估算合理 |
| 2 Alpha Tournament + Microstructure + On-chain counterfactual setup | 110-150 hr | **130-180 hr** | Pairs trading cointegration 需 walk-forward CV + purge + embargo（time-series-cv-protocol）spec missing = +10-15 hr / On-chain free tier rate-limit feature pipeline 設計 = +5-10 hr / counterfactual_log schema spec = +5-8 hr |
| 全期 39 週 | 1,190-1,590 hr | **1,250-1,650 hr** | +5% scaling 主要在 schema spec + dry-run buffer |

---

## 3. 未識別的依賴 / 阻塞

1. **`learning.earn_movement_log` 與 governance.audit_log 的關係**：v5.7 §4 line 158「Daily reconciliation with Bybit account balance」— 但 audit_log 已被 V098 改 constraint，earn movement 是新 event_type 還是用既有？未明示。
2. **Bybit Earn API rate limit / authentication 路徑**：Earn API 屬於 Bybit account-level API；OpenClaw 既有 Bybit client（rust trading_client）是否支援？或需新 client？工時 15 hr 似乎太低（若需新 OAuth scope / API key permission expansion）。
3. **Macro calendar feed 資料來源**：v5.7 §5 提「FOMC/CPI/halving」但沒指定 vendor（FRED API? Investing.com? trading economics?）；vendor 選擇影響 schema + rate limit + 訂閱費（D6 / D8 sunk life expense 是否含？）。
4. **On-chain free tier 容量規劃**：Glassnode free tier ~10 req/day per metric；DeFiLlama 公開無 auth；Etherscan free tier 5 req/sec / 100k req/day。v5.7 沒列具體 metric list × api call budget；feature pipeline 設計時可能發現 free tier 不足 → 觸發 D11 修訂或 paid upgrade（v5.7 §11 提 paid upgrade gate 但無觸發條件 spec）。
5. **PG 容量規劃（4-8GB 限制 + 新 4-5 hypertable）**：
   - market.liquidations 已 90d retention（V006 line 63）
   - 新 macro_events / on_chain_signals / counterfactual_log / earn_movement_log / hypotheses 5 表
   - 若 counterfactual_log on-chain 部分 1.5M row/yr × 17 column ≈ 200MB/yr 不需 hypertable
   - macro_events 3k row/yr 不需 hypertable
   - **結論**：新表大都 small, regular table OK；但 v5.7 §3 沒明示 → Sprint 1A 派 PA 易誤建 hypertable 浪費 chunk overhead
6. **Sprint 1 split (1A + 1B) 之間的 gate 條件未指定**：v5.7 §8 line 290「Total Sprint 1 (1A + 1B): 110-150 hr over 3 weeks」— 但 1A → 1B 過渡 gate（V103/V104 sign-off? Earn API 接通驗證? 沒 spec）。

---

## 4. 對 PA+FA 匯總的必收 top 3

1. **V103/V104 完整 schema spec doc**（建議 `docs/execution_plan/2026-05-21--v103_v104_schema_spec.md`）— 完整 column list / type / Guard A/B/C / hypertable 判斷 / engine_mode CHECK / index plan / idempotency；類比 v101_v102 spec 範式。
2. **PG dry-run mandatory 寫入 Sprint 1A dispatch brief**（引用 feedback_v_migration_pg_dry_run.md + CLAUDE.md §七）+ PA dispatch 前 4 條 ssh PG query 結果附入 brief。
3. **counterfactual_log 最小 schema spec + CV 方法論引用**（Sprint 2 macro/on-chain），明示 walk-forward 或 Purged k-fold / 防 look-ahead / engine_mode column 套用。

---

## 5. Sprint 1A 派發前 must-fix（schema spec + PG dry-run）

1. **新增 `docs/execution_plan/2026-05-21--v103_v104_schema_spec.md`** — 仿 v101_v102 spec 範式；含 column inventory + Guard A/B/C + hypertable 判斷 + idempotency test + engine_mode CHECK + retention
2. **v5.7 §3 增段「PG dry-run mandatory」** — 引用 feedback memory + CLAUDE.md §七，列 4 條 ssh PG query template
3. **v5.7 §3 明確 V103/V104 與 V101 trading.fills.track column 是否同一**（衝突／合併規則）
4. **Sprint 1A engineering 60-80 hr → 75-100 hr**（含 dry-run buffer + spec 補設計 + Earn APR recorder schema）
5. **earn_movement_log 最小 schema spec**（v5.7 §4 line 158 字段名單 → column/type/index/Guard）
6. **Sprint 1A → 1B gate 條件**（V103/V104 land + Linux _sqlx_migrations head=V104 + healthcheck 12 個 check 全 PASS + Earn APR recorder 24h 真有 row）

## 6. Sprint 1B-3 should-fix

1. **counterfactual_log schema spec**（Sprint 2 派 PA 前）
2. **Pairs trading cointegration CV 方法論**（Sprint 2 派 PA 前；walk-forward + purge + embargo size 規範；引用 time-series-cv-protocol）
3. **Macro / On-chain feature engineering leakage 防範**（announcement_ts vs settlement_ts / timezone / shift(1) 規範；引用 feature-engineering-protocol）
4. **On-chain free tier rate limit budget**（per-metric req/day quota + fallback policy if exceeded）
5. **Sprint 9 Advisory Allocator multi-component reward function 數學 spec**（v5.7 §7 提「multi-component」但 0 spec；建議拉 QC review）

## 7. 可優化 / 拆分 / 並行

1. **V097/V098 catch-up 可與 V103/V104 解耦並行**：v5.7 §3 暗示串行；實際 V097/V098 已存在 repo（Linux drift = 2）可 Sprint 1A Week 0 第一天 land，V103/V104 設計可並行（不需等 V097/V098 結果）
2. **Bybit Earn APR recorder（read-only）可移到 Sprint 1A 前**：純讀取 API 無 schema 風險；移前 = Earn governance Sprint 1B 拿到 7-14 day APR 真實樣本，governance 決策更穩
3. **Counterfactual logger schema 設計可前置到 Sprint 1A**：v5.7 §5 計入 Sprint 2 70-95 hr，但 schema 設計本身 ~5-8 hr 可前置；Sprint 2 只需做 writer/consumer 接線
4. **Alpha Tournament cointegration analysis 可拆分**：Pairs（cointegration）vs 其他 4 strategy 分析方法論不同；建議派 QC + MIT 並行（QC alpha 顯著性 + MIT CV 嚴謹性）
5. **earn_movement_log 與 governance.audit_log 整合 vs 獨立 表**：建議獨立（Earn 與 trading audit 語義不同），但用 governance.audit_log 既有 actor_id / event_ts pattern 命名一致

---

## 結論

**Verdict**：**GO-WITH-CONDITIONS**

v5.7 dispatch-safe patch 在 thesis / framework / reviewer §1-6 corrections **全部正確**：
- §3 V101 migration 號碼衝突修正 ✓（用 V103/V104 placeholder）
- §4 Earn APR dynamic + governance ✓（Guardian + Decision Lease 接 REF-20 Sprint 3 Track H 既有架構）
- §5 macro/on-chain counterfactual only Y1 ✓（counted as $0 income 誠實）
- §6 liquidation writer existing not NEW ✓（market_writer.rs:462 + V002 + V005 + V006 grep 驗證）
- §7 Auto-Allocator defer to Y2 ✓（advisory 6mo runway 合理）
- §8 Sprint 1 split 1A/1B ✓（loading 緩解）

**但執行性 3 個 critical/high risk 必先處理**：
1. V103/V104 schema spec 為 placeholder，需獨立 spec doc（仿 v101_v102 spec 範式）
2. PG dry-run mandatory 必寫入 Sprint 1A dispatch brief（feedback memory + CLAUDE.md §七 規範）
3. counterfactual_log schema + CV 方法論 spec 必補（Sprint 2 派 PA 前）

修完上述 3 條 + 工時 +5% 修正後，Sprint 1A 可派 PA dispatch。

**MIT AUDIT DONE: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-21--v57_executability_audit.md**
