# FA 業務鏈核實 — v5.7 12 條 CRITICAL prefix 全部完成 verdict

**日期**：2026-05-21
**verdict**：**APPROVE-WITH-CAVEAT**
**FA 業務 verdict**：12 條 prefix 業務鏈端到端通過 ~83%；4 條 hard caveat 須 PM 仲裁/operator 拍板後 Sprint 1A 才能正式派發；其中 1 條（C3 V### 命名）為 D-1 prerequisite 級 BLOCKER，2 條（C8 §4 finalize / C10 工時 reconcile）為派發前 finalize，1 條（C5 OpenClaw key 發行日）為 operator 5-min query。

**任務背景**：12 條 prefix（v57-C1 ~ v57-C12）2026-05-21 由 5 個並行 sub-agent + PM hands-on 完成；準備派 Sprint 1A。PM 派 FA 在 PM 簽收前對抗審計，確認業務鏈完整、acceptance criteria 達成、跨 spec/ADR 業務語意一致、無 gap。

---

## §1 12 條 prefix acceptance criteria 達成表

| ID | 業務 verdict | 摘要理由 |
|---|---|---|
| **C1** v5.7 主檔 + git rename | ✅ APPROVE | docs/execution_plan/2026-05-20--execution-plan-v5.7.md 已 land；docs/README.md §強制規則符合；PM hands-on git status -R detected |
| **C2** 4 ADR draft 0030-0033 | ✅ APPROVE | 4 ADR 結構完整（Context / Decision / Alternatives / Consequences / 16 原則 / Cross-Ref / Sign-off）；ADR-0033 為 ADR-0006 amendment 範圍正確（Bybit primary + Binance MD approved + Binance trading defer Y2 + DEX/Hyperliquid NOT approved + D12 + ToS）；ADR-0030/0031/0032 cross-ref 完整覆蓋 v5.7 §11 §12 提案範圍；所有 ADR Status=Proposed-pending-commit；16 原則合規 ADR-0033 13/13 / ADR-0032 完整 / ADR-0031 完整 / ADR-0030 完整 |
| **C3** V103/V104 schema spec | ⚠️ **APPROVE-WITH-CAVEAT**（schema 內容對；但 V### 編號錯）| schema 4 表 DDL + Guard A/B/C + index + engine_mode CHECK 4 值 + Row 量級估算齊全；spec §1.2 V101 consolidation 仲裁路徑 A vs B 明示；**但 C9 dry-run §5 證實 V101/V102 尚未 land（empirical DB head=V096）**，C3 §1.3 採「情境 1：V101 已 land」**前提錯誤**；PA C9 推薦 option A 重編 V099/V100=Track v3 / V101/V102=Earn schema；C3 內容只需 search/replace V### number 0.5h churn 即解 |
| **C4** Bybit Earn API endpoint | ✅ APPROVE | BB verdict (a) API exists；12 endpoint 完整（`/v5/earn/flexible/*` + `/v5/earn/fixed/*`），首次 launch 2025-02-20，最近更新 2026-05-07；推翻 v57 audit Risk 1 + Earn endpoint「未驗」claim；§4 工時 18-25 hr 合理 |
| **C5** Earn API key scope | ⚠️ APPROVE-WITH-CAVEAT | BB verdict (a) dedicated `Earn` scope sufficient（非 withdraw）；不違 D1d Hard Boundary；**但 operator 須查 OpenClaw 既有 key 發行日**（< 2026-04-09 須重發 key 加 `Earn` permission）；Sprint 1A read-only first 不阻塞 |
| **C6** liquidation writer 30k+ rows | ✅ APPROVE-STRONG | BB PG empirical query 31,473 rows 2026-05-17→2026-05-21 3.7d 持續流入；writer production；推翻 v57 audit Risk 1 BLOCKED claim（**stale 5 day**）；§6 healthcheck/extend 路徑成立 |
| **C7** Sprint 1B C10 reframe Stage 0R+Demo | ✅ APPROVE | Sprint 1B 改 Stage 0R replay preflight + Stage 1 Demo Micro-Canary（1×1×Demo×7d，$200-500 cap）；不寫 mainnet live $2,000；Stage 4 真實 live 落 Sprint 3-4 待 P0-EDGE-1/LG-3/OPS-1..4 全 closed；AMD-2026-05-15-01 cross-ref 寫入；符合 v5.6 §12 Stage gate + QA D1 + FA G2 §4.1 |
| **C8** Earn governance spec | ⚠️ **APPROVE-WITH-CAVEAT**（spec 完整；§4 待 finalize）| 5-gate 全套（Operator role auth / authorization.json HMAC + env_allowed `earn-write` / Decision Lease lease_type=earn_stake/earn_redeem TTL 60s / Guardian Risk Envelope 5 子檢查含 margin <30% auto-redeem floor / audit log INSERT placeholder 再 API call 順序）；fail-closed 全套（不重試 / 不降級 paper / 連續 3 失敗 disable）；Daily reconciliation $0.01/$1.00/連續 3d mismatch 三階梯；16 原則 15/16 + 9 不變量 8/9（#13 由另 spec / #6 待 §4 verdict 後 finalize）；**但 §4 OPENCLAW_ALLOW_MAINNET 三條件分支待 BB C4 verdict 後 finalize** — BB C4 verdict 已為 (a) API exists，§4.2 條件 A 採納即可（Earn demo + live 兩環境 OPENCLAW_ALLOW_MAINNET demo 不適用 / live 強制） |
| **C9** V103/V104 PG empirical dry-run | ✅ **APPROVE-STRONG**（內容對；揭重大發現）| **重大發現**：DB head=V096，V101/V102 spec 尚未 land；trading.fills.track column 不存在；strategy_track ENUM 不存在；**v5.7 §3 V103/V104 命名假設 + spec C3 §1.3「情境 1 V101 已 land」前提錯誤**；PA option A 推薦（V097/V098 catch-up → V099/V100 = Track v3 → V101/V102 = Earn schema）；race-aware sequencing SOP 5-day cycle；同時揭：派工 prompt 假設 `psql -d openclaw -U openclaw` 在所有 future audit script 全錯（real = `trading_admin / trading_ai`） |
| **C10** Sprint 1A 工時 + §9 sub-agent mandate | ⚠️ **APPROVE-WITH-CAVEAT**（工時數字內部衝突）| §9 並行 sub-agent mandate 50-60% workload + 5 並行 track + LLM API cost $365-565/yr 列入完整；**但 Sprint 1A 工時 90-130 hr 與 BB C6 後實 65-85 hr 顯著衝突** — BB C6 verdict 推翻 v57 audit Risk 1 後 §6 工時 +30~50 hr 反估**完全撤回**，真實 Sprint 1A 65-85 hr；dispatch packet §2 仍寫 90-130 hr 未 reconcile |
| **C11** Apple Silicon CI tuple 條款 | ✅ APPROVE | `cargo check --target aarch64-apple-darwin --release` + `--tests` + `cargo clippy` + PyO3 features；PA sub-agent prompt 注入規範；E3 unsafe/FFI review 加 ARM64 verify；E2 review checklist 加 target check step |
| **C12** Chinese-only + SCRIPT_INDEX + MODULE_NOTE | ✅ APPROVE | per 2026-05-05 mandate；保留原文（identifier / API endpoint / SHA / git ref）；既有 bilingual 不主動清；E2 review `rg -L 'MODULE_NOTE\|模塊用途' <new-files>` = 0 hit PASS；SCRIPT_INDEX.md enforce script 完整 |

**統計**：✅ APPROVE 8 / ⚠️ APPROVE-WITH-CAVEAT 4 / ❌ REJECT 0；總體 ~83% 業務鏈閉合

---

## §2 業務鏈完整性 verdict — Decision Lease + 5-gate + audit coverage

### 2.1 Decision Lease lineage 覆蓋 Earn intent — ✅ PASS

- strategist → guardian → executor → execution_report：Earn 路徑改 `IntentProcessor.submit_intent(intent_type='earn_stake'/'earn_redeem')` → `acquire_lease(lease_type='earn_stake'/'earn_redeem')` → Guardian envelope 5 子檢查 → Bybit Earn API call → `learning.earn_movement_log` INSERT + `governance.audit_log` 鏡像；不繞 IntentProcessor 也不新建 `EarnIntentProcessor`
- lease_type 擴展不新建 facade；ADR-0032 retrofit 新增 `unstake_pending` state（Earn product 鎖定期內）；retrofit 工作量 ~8-10 hr

### 2.2 5-gate boundary 涵蓋 16 原則 — ✅ PASS

#1 單一寫入口 / #3 AI 輸出 ≠ 命令 / #4 策略不繞風控 / #5 生存>收益 / #6 失敗默認收縮 / #8 交易可解釋 / #9 雙重防線 全覆蓋（per Earn governance spec §2 / §3 / §5 / §6）。

### 2.3 audit log coverage — ✅ PASS

`learning.earn_movement_log` 主表 + `governance.audit_log` 鏡像；寫入順序 Lease → DB INSERT placeholder → API call → DB UPDATE outcome；healthcheck `[earn-1]`~`[earn-5]` 5 條覆蓋。

### 2.4 5 textbook 策略 acceptance criteria — ⚠️ PARTIAL

FA G2 已完整 C10 + Unlock SHORT + Pairs + C13 + Funding short-only AC；C10 在 Sprint 1B 派發前 land，其餘各 Sprint 派發前 land；進度與計劃匹配。

---

## §3 跨 spec / ADR 語意一致性 verdict

### 3.1 4 ADR cross-ref 覆蓋 v5.7 §11 §12 — ✅ PASS

| v5.7 §12 提案 | 新 ADR | Cross-ref 完整度 |
|---|---|---|
| ADR-0028 順移 → ADR-0030 Copy Trading evidence-gated | ADR-0030 | ✅ Y1 末 4-Gate evaluation framework / Y1 期間 4 禁制 / Y2 enable 條件 |
| ADR-0029 順移 → ADR-0031 Framework expansion | ADR-0031 | ✅ Earn dynamic APR + Macro counterfactual-only Y1 + On-chain counterfactual-only Y1 |
| ADR-0030 順移 → ADR-0032 Earn asset movement Guardian | ADR-0032 | ✅ 5-gate adapter + Decision Lease retrofit + Audit log schema + Manual 3 months 紀律 |
| ADR-0033 NEW（ADR-0006 amendment）| ADR-0033 | ✅ Bybit primary + Binance MD Y1 / trading defer Y2 / DEX-Hyperliquid NOT approved Y1+Y2 baseline + D12 80% cap + ToS posture |

### 3.2 ADR-0033 範圍對 ADR-0006 amendment 正確性 — ✅ PASS

- ADR-0006 thesis「Bybit is the sole execution venue」**不變**；ADR-0033 only amend「Binance retained only as a hypothetical long-term option」表述
- Decision 1: Binance market data approved Y1：market-data-only WS / 禁 trading endpoint / `market.binance_*` 獨立 namespace
- Decision 2: Binance trading defer Y2：4 條件全部 PASS 才 enable
- Decision 3: DEX/Hyperliquid NOT approved Y1+Y2：proactive lock-down
- Decision 4: D12 cap 80% + ToS posture：Bybit total exposure (trading + Earn) 對 80% cap 成立

**FA caveat**：ADR-0032 §Gate 2 與 ADR-0033 D12 在第三方 issuer Earn 場景**有解釋空隙** — P3 nit 不阻 Sprint 1A。

### 3.3 V103/V104 schema spec §3.2 vs Earn governance spec §3.2 — ⚠️ PARTIAL

**FA finding**：V103 `earn_movement_log` schema 缺 4-5 個 audit field：
- `lease_id`（cross-ref）— earn_governance_spec §2.5 列為 audit field，V103 schema 漏掉
- `approval_id` 或 `authz_id` — V103 schema 無對應 column
- `actor_id` — V103 schema 無對應 column
- `bybit_request_payload` — V103 schema 只列 `bybit_response_payload`，漏 request
- `rationale` — earn_governance_spec §3.2 列 GUI 必填，V103 schema 無對應 column
- `bybit_reported_apr_at_execution` — spec RISK-5 預埋 actual vs expected，V103 schema 無 actual column

**G6 派發前 must-fix**：5-8 hr，PA + MIT 補 column + Guard C 條目。

### 3.4 C9 V### re-number vs v5.7 §3 — ⚠️ PARTIAL → PM 仲裁

| 維度 | v5.7 §3 plan | C9 PA option A | 衝突 |
|---|---|---|---|
| Track schema | V101, V102 | V099, V100 | ⚠️ 編號順延 2 |
| Earn schema | V103, V104 | V101, V102 | ⚠️ 編號順延 2 |

**FA verdict**：option A 是乾淨路徑；30-60 min churn；**PM 仲裁項**。

---

## §4 業務 gap / 矛盾 矩陣（5 critical findings）

| ID | Finding | Verdict | 影響 | 緩解 |
|---|---|---|---|---|
| **G1** | BB C6 PROOF PASS 31,473 rows 推翻 v57 audit Risk 1 | ✅ ACCEPT | §6 工時 +30~50 hr 反估**完全撤回**；engineering save -15~20 hr | 字典 §1.10 / W-AUDIT-8a-C1 plan 標 PASS-by-empirical-evidence |
| **G2** | C3 V101 spec v3 vs v5.7 字段集 60% 不重疊 | 🟡 PM 仲裁 | spec §1.2 路徑 A vs B 明示；v5.7 brief 涵蓋更廣 | **FA 推薦路徑 A**；1 min PM 拍板 |
| **G3** | C10 工時 90-130 hr 與 BB §6 後實 65-85 hr 衝突 | 🟡 PM 仲裁 | dispatch packet §2 未 reconcile | **FA 推薦 (B) 90-130 hr 保留 buffer** — 14 agent 11/14 認為 60-80 hr 系統性低估 |
| **G4** | C5 OpenClaw key 發行日 unknown | 🟡 operator 5-min query | Sprint 1B stake/redeem 派發前必驗 | operator 在 Bybit API mgmt 查 Last edited；< 2026-04-09 須重發 |
| **G5** | C9 V### re-number 對 Sprint 1A V101/V102 dispatch 影響 | 🟡 **D-1 BLOCKER** | E1 IMPL 派發 brief 用錯 V### 號 = head 撞號 | **FA 推薦 option A**；operator 拍板後 PA search/replace |
| **G6** | V103 earn_movement_log schema 缺 4-5 audit field | 🟡 派發前 must-fix | spec MIT vs CC cross-ref 不完整 | **5-8 hr PA + MIT 補**；派 V### IMPL 前 must-fix |

---

## §5 Sprint 1A 派發 readiness verdict

**verdict**：**APPROVE-WITH-CAVEAT + NEEDS-OPERATOR-DECISION（4 項）**

### NEEDS-OPERATOR-DECISION 清單

1. G5 V### re-number 拍板（PM 仲裁，30 sec）— option A vs B；**FA 推薦 A**
2. G3 Sprint 1A 工時收口（PM 仲裁，30 sec）— (A) 65-85 / (B) 90-130；**FA 推薦 (B)**
3. G4 OpenClaw key 發行日（operator query，5 min）
4. G7 C8 §4 finalize（PM 簽核，1 min）— BB C4 verdict (a)，§4.2 條件 A 採納

### Sprint 1A 派發前 must-fix（不需 operator）

1. G6 V103 earn_movement_log schema 補 audit field（5-8 hr）
2. C9 派工 prompt PG connection 範例 land（TW 30 min）
3. C8 五角色 cross-ref（FA + E3 + QA + MIT 預 2026-05-22）

---

## §6 PM 仲裁項 + operator 拍板項

### PM 仲裁項（3 條，1 輪簽核）

1. G5 V### re-number — **FA 推薦 A**（V097/V098 catch-up → V099/V100 = Track v3 → V101/V102 = Earn schema）
2. G3 Sprint 1A 工時 — **FA 推薦 (B)** 保留 90-130 hr buffer
3. G2 V101 字段集 — **FA 推薦路徑 A**（v5.7 brief 字段集）

### operator 拍板項（1 條，5 min）

1. G4 OpenClaw key 發行日 — Bybit Web → API management 查 read_only + trading key Last edited date

---

## §7 結論

- **12 條 acceptance**：8 ✅ / 4 ⚠️ CAVEAT / 0 REJECT
- **業務鏈 critical gap**：5 命中（G1 ACCEPT / G2 PM 仲裁 / G3 工時衝突 / G4 operator query / G5 V### BLOCKER）+ G6 audit field 補
- **PM 仲裁項**：3 條
- **operator 決議項**：1 條（5 min query）
- **FA verdict**：**APPROVE-WITH-CAVEAT**；4 caveat 中 G5 D-1 prerequisite 級 BLOCKER；24 hr 內可清 12/12 派發 ready
- **業務 verdict**：v5.7 12 條 CRITICAL prefix 業務鏈核心通過 ~83%；4 條 caveat 為 governance / cross-spec / V### 編號層次，**無一條挑戰 v5.7 thesis 或 6 reviewer fix**。Sprint 1A 派發 GO-WITH-CONDITIONS

---

**FA AUDIT DONE**: 12-prefix business chain verify
