# v5.7 Dispatch-Safe Patch 執行性審核 — E2 視角

**日期**：2026-05-21
**Verdict**：HOLD（GO-WITH-CONDITIONS，2 個 must-fix + 5 個 should-fix）
**One-line summary**：v5.6→v5.7 6 修復 4 PASS / 1 PARTIAL / 1 NOT-VERIFIABLE；§3 V103/V104 placeholder 無 DDL 即派 PA 違反「路線敲定前不啟動」TODO precondition；Sprint 1A 60-80 hr 含 4 個 zero-baseline NEW + Earn governance + 3 個 NEW sensor，工時嚴重低估 30-50%。

---

## 0. v5.6 → v5.7 6 個修復逐條核實

| # | claim | verdict | 證據 |
|---|---|---|---|
| 1 | V101→V103/V104 placeholder | **PARTIAL** | V101/V102 Track schema spec 存在於 `docs/execution_plan/2026-05-20--v101_v102_track_attribution_migration_spec.md`（grep 確認）。但 V103/V104 自身**無任何 DDL spec 檔**（grep `V103\|V104` 無命中 schema 檔）。v5.7 §3 寫「v5.7 spec uses V103/V104 placeholder; PA dispatch finalizes」— 但 hypotheses / hypothesis_preregistration / trading.fills.track 三表的 schema 細節（欄位定義 / Guard A/B/C / index）全部缺。PA dispatch 收到後若沒新 schema spec 檔，等同要求 PA 邊定 V### 邊寫 schema，與既有 V101/V102 spec-first dispatch pattern 不符。 |
| 2 | Earn APR dynamic API | **NOT-VERIFIABLE / SCOPE-MISMATCH** | grep `Bybit Earn\|/v5/earn\|earn_redeem\|earn_stake` 全部 zero hit；Bybit Earn API 對 codebase 是 **complete green field**。v5.7 §4 寫「Earn API integration: ~15 hr」— 該數字未驗證（沒人查過 Bybit Earn API 文件 surface area / auth model / staking endpoints / redemption endpoints / tiered APR query endpoint 是否真存在於 v5 REST）。`docs/references/2026-04-04--bybit_api_reference.md` 應該被 BB 查證更新，但 v5.7 沒提及此前置。 |
| 3 | Liquidation writer healthcheck not new | **PASS** | grep 全證實 — `rust/openclaw_engine/src/database/market_writer.rs:333-477` 有 `flush_liquidations` + `INSERT INTO market.liquidations`；`multi_interval_topics.rs:131` `allLiquidation.{symbol}` 拓撲（C1-proved）；`panel_aggregator/liquidation_pulse.rs` 消費端；`main_ws.rs:62` WS 路由 `topic.starts_with("allLiquidation.")`。Healthcheck 路徑明確，~15-20 hr engineering save claim 合理。 |
| 4 | Auto-Allocator Y2 defer | **PASS** | §7 顯式寫 4-6 個月 advisory + ≥80% approval 才升 Auto；Sprint 9 仍 Advisory only。governance compliance OK。 |
| 5 | Macro/on-chain counterfactual only Y1 | **PASS-WITH-CAVEAT** | §5 寫「NOT applied to actual strategy triggers in Y1 production」+ 「Counted as ZERO income」。但 §1 income 表把 macro overlay $63 + on-chain $36 從 v5.6 移除，符合 claim。**Caveat**：§5 §3 vs §8 Sprint 1A 不一致 — §5 寫「Macro feed + counterfactual logger: 25-35 hr」+ 「On-chain: 30-40 hr」共 ~55-75 hr，但 §8 Sprint 1A 只列「Macro calendar feed NEW」沒明列 on-chain；Sprint 2 也只列「On-chain counterfactual setup」。實際 on-chain logger + A/B framework 工時是否在 Sprint 1A / 2 / 3 之間正確分配，spec 不明。 |
| 6 | Earn deposits Guardian-checked policy | **PARTIAL** | §4 段 2 寫「Each stake operation = asset write, requires authorization / Guardian-checked / Decision Lease pattern」— 概念正確（DecisionLease + Guardian 在 Rust 引擎已有 17 處 reference + Guardian 至少 5 個檔案）。但**沒寫 ADR-0030 草稿位置 / earn_movement_log schema DDL / stake intent IPC schema / auto-redeem trigger 的數學定義**（margin headroom < 30% 怎麼算？unrealized_pnl 算不算？isolated vs cross margin？）。Sprint 1A 「Bybit Earn API APR recorder (read-only, no stake yet)」+ Sprint 1B「Earn governance policy + first small manual stake」— governance integration ~20 hr 估算同樣未驗證 Guardian/Lease 接線真實成本。 |

**綜合**：4 PASS（含 caveat）/ 1 PARTIAL（#1 schema 缺）/ 1 NOT-VERIFIABLE（#2 Earn API）/ 1 PARTIAL（#6 governance schema 缺）。

---

## 1. Top 3 執行性風險（排序）

### Risk 1：V103/V104 placeholder 派 PA = spec-first pattern 破壞 + V101/V102 衝突重生

- **嚴重度**：CRITICAL
- **位置**：v5.7 §3 + §8 Sprint 1A
- **描述**：v5.7 §3 結尾寫「v5.7 spec uses V103/V104 placeholder; PA dispatch finalizes」。但既有 V101/V102 Track schema spec（檔頭已寫「real V### 號碼 PA dispatch 時 final 鎖定，預期 V101 / V102 但若 LG-3 與 W-AUDIT-8a 殘留 reserve V099/V100，可能順延 V103/V104」）— **意味著 V103/V104 號碼也有被 V101/V102 占用的可能**。如果 PA dispatch 兩個 spec 同時，會撞號。更嚴重的是 v5.7 沒附 hypotheses / hypothesis_preregistration / trading.fills.track 三表的 DDL（欄位、type、constraint、index、Guard A/B/C），等於要求 PA 在 dispatch 階段邊定號碼邊定 schema，違反既有「spec-first → PA dispatch only finalizes number」流程。
- **為何屬「執行性」**：不是邏輯錯誤（reviewer §1 思路正確：避免重用 V101），是 **dispatch artifact 不完整** — PA 收到任務缺 DDL spec 就無法派 E1 IMPL。
- **Must-fix 建議**：在 dispatch PA 前，先派 PA 寫 V103/V104 schema spec 草稿（學 V101/V102 spec 格式），含三表 DDL + Guard A/B/C + idempotency 測試方案 + 與 V099/V100/V101/V102 號碼衝突解析。**或者** 把 schema spec 起草納入 Sprint 1A 的 sub-task（並把 60-80 hr 上調 15-20 hr）。

### Risk 2：Sprint 1A 60-80 hr 工時嚴重低估（30-50% gap）

- **嚴重度**：HIGH
- **位置**：v5.7 §8 + §9
- **描述**：Sprint 1A list 10 個工作項：ADR-0006 amend + V097/V098 + V103/V104 + 既有 liquidation writer healthcheck + Bybit options chain recorder NEW + Tokenomist NEW + Macro calendar feed NEW + Binance perp WS NEW + Bybit Earn API APR recorder（read-only）+ 三個 sensor NEW。**真實工時 sanity check**：
  - V097/V098 Linux DB catch-up 含低寫入窗口 + healthcheck：~4-6 hr
  - V103/V104 schema spec 起草 + E1 IMPL + Guard 測試：~15-20 hr（如 Risk 1 must-fix 採納）
  - Bybit options chain recorder NEW（grep 確認 zero baseline / 沒有 options REST client / 沒有 IV/OI/Greek 結構）：~25-35 hr 起跳
  - Tokenomist NEW（zero baseline，需 API 評估 + auth + rate limit + DB writer + cron）：~10-15 hr
  - Macro calendar feed NEW（zero baseline，FOMC/CPI/halving 三源整合）：~12-18 hr
  - Binance perp WS NEW（zero hit 在 codebase / 全新 WS client + parser + writer + topic 路由）：~30-40 hr 起跳（參考 Bybit WS 既有 LOC）
  - Bybit Earn API APR recorder（zero baseline + 未驗證 endpoint surface）：~10-15 hr
  - 既有 liquidation writer healthcheck：~3-5 hr
  - **真實估計總和**：~110-155 hr，不是 60-80 hr。**Gap 50-90%**。
- **為何屬「執行性」**：reviewer 沒 grep 驗證 Bybit Earn / options / Tokenomist / Binance / Macro 的現有 baseline；v5.6 vs v5.7 §9 total 1180→1190 hr **只 +10 hr**，但 v5.6 100-130 hr Sprint 1 vs v5.7 110-150 hr Sprint 1A+1B — 增加 10-20 hr 卻同時新增 V103/V104 schema 起草 + Earn governance + 三新 sensor，數學不平。
- **Must-fix 建議**：Sprint 1A 上調至 100-130 hr 或 1B 上調至 70-90 hr，總計 1A+1B 拉到 170-220 hr；同步 §9 total 拉到 1310-1740 hr。否則 dispatch 後 E1 一定 over-budget，触發 v5.6 既有 50-100% workhour anti-pattern。

### Risk 3：「路線敲定前不啟動」TODO precondition vs 「Sprint 1A dispatch ready」claim 衝突

- **嚴重度**：HIGH
- **位置**：v5.7 §11 §12 + TODO.md L42 / L103 / L195 / §10
- **描述**：TODO.md L42 明確寫「**Hard precondition**：路線敲定前不啟動任何 V101 / V102 / Track A/B / dispatch wave。當前 in-flight active 工作見 §3 / §10 / §11.3 / §12」。同檔 L103 「Live deploy hard precondition：P0-EDGE-1 + P0-LG-3 (Wave 2.4 IMPL) + P0-OPS-1..4 全清」。同檔 §10 P0 ACTIVE 還有 EDGE-1 + LG-3 + OPS-1..4 + P3-SPINE-BENCH **未 closed**。v5.7 §11 寫「Sprint 1A ready for PA dispatch upon operator final approval」+ §12 「Sprint 1A ready for PA dispatch」。**operator final approval 沒 ledger 化在 TODO** — TODO §-0 路線變更區是「空白，待 operator 重填」。
- **為何屬「執行性」**：reviewer 15 輪都聚焦 v5.6→v5.7 spec 內部一致性，**沒有檢查 v5.7 與 TODO active state 的契合**。v5.7 dispatch 前必要先把 TODO §-0 / §1 重填（記錄 operator approve v5.7 + Sprint 1A 路線決定），否則違反 CLAUDE.md「TODO.md 是 active state authority」原則。
- **Must-fix 建議**：dispatch PA 前，由 PM 派一個 TODO maintenance task 補填 §-0 路線變更區（記錄 v5.7 approved + Sprint 1A 啟動）+ §10 加 ACTIVE 任務 ID（v5.7-S1A-GOVERNANCE / v5.7-S1A-MIGRATION / etc）+ 在 §1 ledger v5.7 文件路徑 + foundation 結論。

---

## 2. Hours sanity check（5-10x 規律）

operator 5-10x 規律 = reviewer 估算 × 5-10x = 真實工時上界。但 v5.7 自己已是 reviewer-corrected 版本，所以本節對 v5.7 §9 數字做雙重檢查：

| Sprint | v5.7 estim | 真實估計（含 Risk 2 修正） | 比率 |
|---|---|---|---|
| 1A | 60-80 | 110-155 | 1.5-1.9x |
| 1B | 50-70 | 60-85（含 C10 strategy 模組） | 1.1-1.2x |
| 2 | 110-150 | 140-200（含 on-chain integrate） | 1.2-1.3x |
| 3 | 130-160 | 130-180 | 1.0-1.1x |
| 4 | 160-210 | 200-260（含 options stack 1） | 1.2-1.3x |
| 5-10 | 各 sprint | 與 v5.7 接近 | ~1.0x |
| **Total** | **1190-1590** | **~1450-1900** | **1.2-1.2x** |

**結論**：v5.7 已非 5-10x reviewer estimate（reviewer 是直接審 v5.7），但 vs 真實 zero-baseline 工時仍低估 ~20-25%。**符合 operator 既有教訓「LLM estim × 1.2-2x 是真實值」**。

**重點**：Sprint 1A 的 1.5-1.9x 是分布最差的 sprint，是「path 0」啟動點，最不能低估。

---

## 3. 未識別的依賴 / 阻塞

| # | 依賴 / 阻塞 | 嚴重度 | 描述 |
|---|---|---|---|
| 1 | P0-EDGE-1 / LG-3 / OPS-1..4 未 closed | CRITICAL | v5.7 寫 Sprint 1A 含 C10 minimal viable on 主帳 $2,000，但 C10 是 live trading（主帳 = mainnet）。Live deploy hard precondition 還沒清。v5.7 §8 Sprint 1B 「C10 minimal viable on 主帳 $2,000」與「五門 live precondition」直接衝突。是否 Sprint 1B 的 C10 是 LiveDemo only？spec 沒明寫。 |
| 2 | Bybit Earn API surface 未經 BB review | HIGH | v5.7 §4 寫 15 hr engineering 但沒人驗證 Bybit Earn v5 REST 是否提供 staking / redemption / tiered APR query；如果 Bybit 只在 web UI 提供（非 API），Earn governance 完全不能 automate；該 risk 完全沒被 reviewer 15 輪覆蓋。 |
| 3 | Tokenomist trial 是否仍 active | MEDIUM | v5.7 §8 Sprint 1A 「Tokenomist unlock calendar NEW」假設 Tokenomist trial 可訪問；G-2 funding_arb 結論 V2 棄策略（2026-05-02）裡 Tokenomist 有 trial 限制；trial 是否續用 + paid tier 是否 operator 已批 = unknown。 |
| 4 | Binance perp WS = market data only ADR-0006 amend pending | HIGH | v5.7 §11 「ADR-0006 amendment」+ §12 列為 proposed (-0006 amend / -0028 / -0029 / -0030)；4 個 ADR 同時 propose + amend；governance velocity 風險（同時 4 個 ADR draft 需 CC + FA + PM 並行）。 |
| 5 | Counterfactual A/B framework 規格未定 | MEDIUM | §5 寫「A/B evaluation framework: 15-20 hr」+ 「Y1 末 evaluate counterfactual evidence」+ 「If overlay真 alpha (counterfactual shows +2%+ on strategies) → Y2 enable」。但「+2%」怎麼算 / 樣本怎收 / null hypothesis 怎設 / 顯著性 threshold（t-stat / DSR / Wilson）= 都沒寫；Y1 末 evaluate 時必跑 QC + MIT，工時也未列。 |
| 6 | 5 策略並行的 mutex / 鎖競爭 | MEDIUM | v5.7 描述 5 策略全部共用 $7,500 主帳 capital；多策略並發進出 spot+perp 對同 symbol（C10 BTC + Pairs BTC/ETH）會撞 capital allocation lock + margin sharing；v5.7 沒提 capital reservation IPC + per-strategy margin envelope；既有 fast_track.rs / position_risk_evaluator.rs 是否有 multi-strategy concurrency primitive = 沒 grep 證明。 |
| 7 | 共用 helper / decision_lease 容量 | MEDIUM | DecisionLease 表現有 17 個 Rust caller；v5.7 新增 Earn movement Lease + 5 策略 trading Lease + Allocator Advisory Lease → Lease 表 writer rate 4-5x 提升；lease_id_to_idx HashMap leak 已是 `P1-LEASE-1`（TODO §11.3 ACTIVE，且依賴 LG-3 IMPL 後才能修）→ v5.7 啟動會放大 LEASE-1 影響。 |
| 8 | options chain recorder = 全新 8000+ LOC 估計 | HIGH | grep 「options」在 Rust src 只 5 處 trivial reference；options REST client / options WS / Greeks 結構 / IV/OI/DTE 持久化 / strike chain time series 等等全部 zero。v5.7 §8 Sprint 1A 把「Bybit options chain recorder NEW」當 60-80 hr 共享項，不切實際。Sprint 4 §7 「Options Stack 1」+「~600 LOC Rust + 250 LOC Python」也偏低（C13 spec 過去評過要 1500-2000 LOC）。 |

---

## 4. 對 PA+FA 匯總的必收 top 3

1. **V103/V104 schema spec 先寫**（PA owner）— hypotheses + hypothesis_preregistration + trading.fills.track 三表 DDL + Guard A/B/C + V### 號碼衝突解析（V099/V100/V101/V102/V103/V104 排序）+ 與既有 V101/V102 Track schema spec 對接點（trading.fills 兩個 spec 都 ALTER 同表，需協調）。
2. **Bybit Earn API surface BB pre-review**（BB owner）— 證實 v5 REST 是否真提供 stake/redeem/tiered-APR-query；如果無，§4 「Earn movement = governance asset write」變成 web UI manual operation，governance 概念不適用，必須回退到 v5.6「~10 hr」估算 + 純 read-only APR recorder。
3. **C10 live vs LiveDemo 釐清**（PA + FA owner）— Sprint 1B 「C10 minimal viable on 主帳 $2,000」必明確：(a) 走 LiveDemo（Demo endpoint + live-grade 風控，符合 CLAUDE.md 五門 + LG-3 IMPL 後啟用）or (b) 真 mainnet（需 P0-EDGE-1 / LG-3 / OPS-1..4 全 closed + operator 五門 approve）。spec 默認應走 (a)。

---

## 5. Sprint 1A 派發前 must-fix

1. **TODO §-0 / §1 補填 v5.7 路線決定**（PM owner，~30 min）— operator 簽核 v5.7 + Sprint 1A 啟動 + §10 加 v5.7-S1A-* task ID + 鏈到 v5.7 文件路徑。
2. **V103/V104 schema spec 起草**（PA owner，~6-10 hr）— 三表 DDL + Guard + 與 V101/V102 對接點。可在 dispatch PA 第一輪 deliverable 內，但 E1 IMPL dispatch 前必須 land。
3. **Bybit Earn API surface BB review verdict**（BB owner，~2-4 hr）— 給出 「(a) API exists, ~15 hr estim 合理」/「(b) web UI only, 改 read-only APR scrape」/「(c) partial API, scope 重定」三選一。
4. **Sprint 1A 工時上調至 100-130 hr**（PM owner）— 同步 §9 total + Sprint 1B 評估是否也需上調。
5. **Sprint 1B 的 C10 明確標 LiveDemo or mainnet**（PA + FA owner）— spec drift fail-closed。

---

## 6. Sprint 1B-3 should-fix

1. **counterfactual A/B framework 規格**（QC + MIT owner，Sprint 2 內）— +2% alpha 判定標準 / 顯著性 threshold / 樣本量 / null hypothesis。
2. **multi-strategy capital reservation IPC spec**（FA + E1 owner，Sprint 2-3 內）— 5 策略並發進出對主帳 $7,500 的鎖協議；per-strategy margin envelope；異常時 fail-closed 順序。
3. **options stack Sprint 4 LOC re-estim**（PA + E1 owner，Sprint 3 末）— v5.7 「~600 LOC Rust」對比 C13 過往 spec 1500-2000 LOC 預期；要拆 phase 1 / phase 2 明確 scope。
4. **on-chain counterfactual logger 工時分配明確化**（PA owner，Sprint 1B 末）— Sprint 1A / 2 / 3 / 4 各承擔多少 hr，目前 v5.7 §5 70-95 hr 沒 mapped。
5. **Tokenomist + Glassnode subscription 商務確認**（operator owner，Sprint 2 之前）— trial / paid / free tier 路徑明確；v5.7 §8 默認 trial 但沒列備選。

---

## 7. 可優化 / 拆分 / 並行（並行 dispatch 機會）

Sprint 1A 內並行 dispatch（PA 設定後）：

- **wave A（ADR + governance + TODO 更新）**：CC + FA + PM 並行；序列無依賴
- **wave B（V097/V098 catch-up）**：E1 + E3 序列，低寫入窗口；blocking subsequent V### apply
- **wave C（V103/V104 schema spec + IMPL）**：PA spec → E1 IMPL → E2 review → E4，序列；wave B 完成後可啟
- **wave D（既有 liquidation writer healthcheck）**：E5 owner，獨立並行 wave B/C
- **wave E（NEW sensor — Bybit options chain recorder）**：E1 + BB review；獨立並行，但 LOC 大佔工時最多
- **wave F（NEW sensor — Tokenomist + Macro feed + Binance perp WS）**：E1 三個並行 sub-task；BB review Binance WS topic
- **wave G（Bybit Earn API APR recorder read-only）**：blocked by BB review verdict (Must-fix 3)；驗證後派 E1

並行最大化後，Sprint 1A 真實 wall-clock 約 1.5-2 週（vs 工時 100-130 hr 折算單 E1 約 2.5-3 週）— 並行 3-4 個 E1 可壓回 1.5 週。**Sprint 1A 的「Week 0-1.5」時程是 OK 的，但要求 ≥3 個 E1 並行**。

---

## 8. 結論

**Verdict: HOLD（GO-WITH-CONDITIONS）**

v5.7 thesis 對；reviewer §1-6 6 修復 4 PASS / 2 PARTIAL。但 dispatch readiness 有 5 個 must-fix（§5）+ 7 個 should-fix（§6）。

**派 PA 前必先做**：
1. TODO §-0 / §1 補填 + v5.7 path-of-record 確認
2. V103/V104 schema spec PA 起草任務 dispatch
3. Bybit Earn API surface BB review
4. Sprint 1A 工時上調至 100-130 hr（同步 §9 total）
5. Sprint 1B C10 LiveDemo or mainnet 明確標註

完成上述 5 項後，v5.7 變 GO；不完成則 dispatch 後 E1 over-budget + spec drift + 違反 TODO active state 三角風險。

**E2 不寫業務代碼**：本報告純 reviewer 視角；所有 fix 推回 PA / PM / BB / FA owner。

---

**E2 REVIEW DONE: HOLD · report path: srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-21--v57_executability_audit.md**
