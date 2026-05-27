# AMD-2026-05-26-01 — funding_arb V2 Deprecation Closure

Date: 2026-05-26
Status: **Proposed-pending-operator-confirm**
Operator Sign-off: 2026-05-26 directive — 對 `P0-FUNDING-ARB-DECISION-FORCE` 選 (D) 3C TOML deprecation closure
PM Sign-off: 本 draft；批准前 cascade 不執行

Supersedes:
- `docs/adr/0018-funding-arb-v2-deprecation-watch.md` §Decision「retire from active strategy set」**狀態升格**為「retired closed per code-level `#[deprecated]` marker + runtime fail-closed guard + AMD-level closure governance」；ADR-0018 §Decision rewording 走 §11 cascade（不另立新 ADR）
- TODO `§1 P0-FUNDING-ARB-DECISION-FORCE` (已 ✅ CLOSED 2026-05-26) + TODO `§6 P1-EDGE-2 (funding_arb)` — 由本 AMD 落地 cascade 後永久 archive

Related:
- ADR-0018 (status 升格 Retired)
- ADR-0046 (Proposed) `funding_arb.rs IMPL + V117 migration spec`（future redesign slot 保留；本 AMD **不** retire ADR-0046）
- AMD-2026-05-09-02 (W-AUDIT-6 strategy verdict — funding_arb retire 路線終結點)
- AMD-2026-05-09-03 (graduated canary default；Stage 0R replay preflight 範式)
- AMD-2026-05-15-01 (Stage 0R replay preflight + Stage 1 Demo micro-canary — revive 必走路線)
- Memory `project_funding_arb_v2_deprecation_path` (1B+2A+3C operator 決策 lineage)
- Memory `project_g2_funding_arb_monitor` (G-2 v2 NEGATIVE n=13 結案)
- Commit `a19797d` (2026-05-02 risk_config_demo base_ratio 0.4→0.25 + funding_arb 3% override 已 land)
- PA Spec `docs/execution_plan/specs/2026-05-26--funding-arb-deprecation-cascade.md` (Workflow F Phase 1)
- Helper script `helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.py` (n=18 dormant 證據)

---

## 1. Status

**Proposed-pending-operator-confirm**

本 AMD 為 operator 2026-05-26 對 `P0-FUNDING-ARB-DECISION-FORCE` 選 (D) 3C TOML deprecation closure 的正式 governance 化。22 天 dormant cycle（2026-05-03 三端 active=false 後）n=18 不再累積，audit 路徑沒有 closure；operator 選 (D) 在 22 天 deadlock 後將 V2 顯式 retire — 程式碼層加 `#[deprecated]` marker、runtime 加 fail-closed guard、TOML 三端硬鎖 active=false（已 land）、docs/spec cascade 全鏈標 retired、ADR-0018 status 從 "retire from active strategy set" 升格為 "Retired closed"。

ADR-0046 future redesign slot 並存保留；revive 須走 AMD amendment + ADR-0046 Accepted + 5-gate + Stage 0R replay preflight。

---

## 2. Context

### 2.1 22 天 dormant lineage（為何 (D) 是終結路徑）

| Stage | Trigger | Outcome |
|---|---|---|
| 2026-04-18 | G-2 v2 audit n=13 0/13 勝率 -36.76 bps NEGATIVE EDGE | demo `funding_arb.active=false` |
| 2026-05-02 | BUSDT demo -10.12 USDT (1 fill 6.29% notional) post 3C re-enable 範式 | operator 1B+2A+3C 三路：1B demo active=true 收 EDGE-DIAG-2 樣本 / 2A 中期棄策略 / 3C TOML 緊 SL → 已 land commit `a19797d` |
| 2026-05-03 | 三端統一 disable | paper/demo/live `[funding_arb].active = false` |
| 2026-05-09 | ADR-0018 Accepted | retire from active strategy set + W-AUDIT-6 cleanup pending |
| 2026-05-16 | `helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.py` n=18 dormant 確認 | n 不再累積；P1-EDGE-2 升 `P0-FUNDING-ARB-DECISION-FORCE` deadlock |
| 2026-05-25 | QC EA-3 升 P1 hot-fix（6.29% 違 5% SL gate claim） | PA overturn — 6.29% 是 demo dyn_stop floor 6.25% + 0.04pp 設計範圍內，非 bug；建議 reclassify P3 documentation-only carry-over |
| **2026-05-26** | **operator chose (D) 3C TOML deprecation closure** | **本 AMD Phase 2** |

### 2.2 QC EA-3 verdict — V2 在 Bybit 結構性無法 break-even

QC EA-3 verdict（per PA overturn report `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-25--h2_ea2_final_sop_refine.md` 引用 EA-3 數學）：

- **數學不成立**：V2 delta-neutral 設計依賴 spot 持倉收 funding 同時 perp short 對沖 directional 風險；Bybit demo 無 spot lending，無法構成 delta-neutral leg
- **Cost vs funding mean**：total_cost_bps = 34 / funding mean = 1.5 bps → break-even 需 7.6 day 持倉
- **Hold 時長 vs market beta**：7.6 day 暴露在 funding rate noise + crypto market beta noise → directional 風險吃光 funding edge
- **n=13 v2 + n=18 dormant 雙重證據**：13 fills 0/13 win + 22d dormant 0 新增 fill = 樣本層 + governance 層雙重結構性結論

**結論**：V2 是 architecturally infeasible 在當前 venue（Bybit demo + Bybit mainnet 都不行）。不是「參數沒調對」可以 R-02 Strategist 重評救活；是 design 層面 stuck。Revive 需 ADR-0046 重設計，不是本 AMD 範疇。

### 2.3 4 alternatives operator 拒絕原因

| 選項 | 拒因 |
|---|---|
| (A) 繼續觀察 | 22 天 dormant + n 不累積 = deadlock；無 closure 路徑；operator 不接受 indefinite watch |
| (B) R-02 Strategist 重設計 V3 | 既有 V2 在 Bybit demo 結構性無法 break-even；重設計屬 ADR-0046 future redesign slot 範疇，不是 V2 closure；ADR-0046 (Proposed) 已預留此 slot |
| (C) 純 docs-only mark deprecated | TOML active 仍是「dormant pending re-eval」語意，governance 模糊；不終結；無法回答「W-AUDIT-6 cleanup 何時 land」 |
| **(D) 3C TOML deprecation closure** | **明確 retire + cleanup + 公開封存；ADR-0018 status 升格；ADR-0046 future redesign slot 並存；governance gap 補完** |

### 2.4 v4.4 D7 constraint 在 execution-plan 文本提及未 AMD 化

ADR-0018 §Decision 的 wording「retire from active strategy set」+「W-AUDIT-6 may implement active RiskConfig cleanup after targeted source/test cleanup」是 condition-pending 語意；本 AMD 將其升格為 "Retired closed"，補完 ADR → AMD 的 lifecycle 缺口。

---

## 3. Decision 1 — Strategy Code 程式碼層 `#[deprecated]` Marker

**範圍**：`srv/rust/openclaw_engine/src/strategies/funding_arb.rs` (1203 行 / 72 unit tests) + `strategies/registry.rs:240-250` (factory caller) + `strategies/params.rs` (FundingArbParams) + `strategies/mod.rs:22-23`（pub mod funding_arb 註冊）

### 3.1 keep with `#[deprecated]` marker（為何不選 hard-delete / archive）

| 方案 | 拒因 | 採納理由 |
|---|---|---|
| (a) Hard-delete `funding_arb.rs` + 移除 registry/params/mod.rs 註冊 | (i) ADR-0046 (Proposed) 明示 `funding_arb.rs IMPL` 為 future redesign slot；(ii) SQL V031/V034/V084/V086/V090/V101 6 migration enum/case 含 `'funding_arb'` 硬編碼 — 程式碼刪除後 historical row 仍 query；(iii) 72 unit tests 是 dormant 結構驗，刪除損失測試覆蓋；(iv) Rust mod tree + factory 拔除屬高風險 + 編譯破壞風險 | – |
| (b) Move to `archive/funding_arb_v2/` | (i) Rust mod path 不能跨 crate 引用 archive subdir，需大規模重組；(ii) registry.rs 仍需 stub；(iii) git history 已是 ARCHIVE 等效 | – |
| **(c) Keep with `#[deprecated]` + runtime active=false hard guard** | – | **(i)** 與 ADR-0018「retain auditability」一致；**(ii)** ADR-0046 future redesign slot pattern；**(iii)** SQL enum 不破；**(iv)** compiler warning IDE 立即可見；**(v)** registry `set_active(p.funding_arb.active)` 路徑 + TOML active=false 雙保險 fail-closed；**(vi)** 0 編譯 break + 0 test loss |

### 3.2 IMPL Specification（E1 Phase 3 後續派工依據）

**注意**：本 AMD 不執行 IMPL；以下為 E1 D+7 dispatch spec。

#### 3.2.1 `funding_arb.rs` mod doc + item-level `#[deprecated]`

```rust
//! 資金費率套利策略 V2 — 方向性資金費率捕獲（dormant per ADR-0018 / AMD-2026-05-09-02）。
//!
//! **DEPRECATED 2026-05-26 per AMD-2026-05-26-01**（operator (D) 3C TOML deprecation closure）。
//! Bybit demo 無 spot lending + cost 34 bps / funding mean 1.5 bps → break-even 7.6 day
//! 結構性無法 close gap。本模組保留作為 ADR-0046 future redesign slot；運行時硬鎖
//! `[funding_arb].active = false` 三端統一；任何 IPC `update_params(active=true)` 須先解 AMD。

// Rust mod-level #![deprecated] 不支援 — 改用 item-level marker
#[deprecated(
    since = "2026-05-26",
    note = "funding_arb V2 retired per AMD-2026-05-26-01 + ADR-0018. \
            Slot reserved for ADR-0046 redesign. Do not re-enable without AMD amendment."
)]
pub struct FundingArb { /* ... */ }
```

同樣 `#[deprecated]` 套用至 `pub fn new()` / `pub fn update_params()` 兩個公開 entry。

#### 3.2.2 runtime fail-closed guard（防 fat-finger 解 deprecation）

`FundingArb::update_params()`（line 156-177）加 hard guard：

```rust
pub fn update_params(&mut self, params: FundingArbUpdateParams) -> Result<(), String> {
    // 不變量：V2 已 retired，IPC active=true 一律 fail-closed，防 TOML 誤改或 IPC 注入
    if params.active {
        return Err(
            "funding_arb V2 deprecated per AMD-2026-05-26-01 + ADR-0018; \
             active=true rejected. ADR-0046 future redesign required.".into()
        );
    }
    params.validate()?;
    self.active = false;  // 強制 false，忽略 params.active
    // 既有邏輯不動
    Ok(())
}
```

#### 3.2.3 registry.rs factory 標記（line 240-250）

```rust
// FundingArb V2 dormant per ADR-0018 + DEPRECATED per AMD-2026-05-26-01.
// Slot reserved for ADR-0046 future redesign. set_active forced false.
#[allow(deprecated)]
let mut fa = funding_arb::FundingArb::new();
fa.set_active(false);  // 不再讀 p.funding_arb.active；強制 false
// 其餘 fa.xxx = p.funding_arb.xxx 仍保留（為 future ADR-0046 redesign slot 提供 param 載入 path）
```

#### 3.2.4 72 tests retention（dormant 結構驗）

72 個 unit tests 全部保留為 dormant 結構驗（per memory `cross_strategy_attribution_integrity` 模式）。`mod tests` 開頭加註：

```rust
#[cfg(test)]
#[allow(deprecated)]  // dormant 結構驗 per ADR-0018 + AMD-2026-05-26-01
mod tests {
    // 既有 72 個測試不動
}
```

### 3.3 對 5 textbook strategy roster 的影響（4 textbook reframe）

| 既有 5 textbook | 處置 |
|---|---|
| ma_crossover | 不動 |
| bb_breakout | 不動 |
| bb_reversion | 不動 |
| grid_trading | 不動 |
| **funding_arb** | **roster 移除**；新 roster = **4 textbook** |

**對應 doc / spec / SQL 更新**（cascade scope per §11）：
- TODO `§6 P1-EDGE-2 (funding_arb)` archive 結案
- TODO `§1 P0-EDGE-1` AC「5 textbook ≥3」改「4 textbook ≥3」
- `docs/execution_plan/2026-05-20--execution-plan-v5.8.md` 5 textbook roster → 4 textbook
- SQL V090 line 505 註釋追加 AMD-26-01 cross-ref（不改 enum）
- MIT MIN_SAMPLES gating（per memory `project_2026_05_09_ml_training_cron_weekly` 4/5 策略不過）→ 4/4 reframing

---

## 4. Decision 2 — TOML active=false 終結（已 land）

### 4.1 三端 TOML 現況（PA 親讀 2026-05-26）

| TOML | active | base_ratio (dynamic_stop) | 備註 |
|---|---|---|---|
| `settings/strategy_params_paper.toml:134-141` | `active = false` | (n/a paper) | G2-FUP 2026-04-26 三端統一 disable |
| `settings/strategy_params_demo.toml:165-172` | `active = false` | (per risk_config_demo) | 2026-05-03 三端統一停 |
| `settings/strategy_params_live.toml:136-143` | `active = false` | (n/a live) | OC-5 三端統一關閉 |
| `settings/risk_control_rules/risk_config_demo.toml:196` | – | `base_ratio = 0.25` (3C commit `a19797d`) | 全 demo 策略 dyn_stop floor 收緊 |
| `settings/risk_control_rules/risk_config_paper.toml:169` | – | `base_ratio = 0.30` | env-isolation 保留 |
| `settings/risk_control_rules/risk_config_live.toml:179` | – | `base_ratio = 0.5` | env-isolation 保留 |
| `settings/risk_control_rules/risk_config_demo.toml:97` | – | – | `per_strategy.funding_short_v2.stop_loss_max_pct_override=3.0` (1B 3% tight SL 範式 cross-ref funding_arb) |

**結論**：TOML 100% 已 inactive，commit `a19797d` 已 land 全部必要改動；本 AMD **不要求新 TOML 數值改動**（避免 scope creep）。

### 4.2 三端 TOML `[funding_arb]` 區段註釋追加 AMD cross-ref

per Phase 2 TW cascade：三個 `strategy_params_*.toml` 的 `[funding_arb]` 區段註釋追加 AMD-2026-05-26-01 cross-ref；保留 `[funding_arb]` 區段 + active=false（**不可刪除**，否則破壞 `FundingArbParams` deserialize 與 registry.rs 引用）。

---

## 5. Decision 3 — Future Redesign Slot Preservation（ADR-0046）

ADR-0046 (Proposed) `funding_arb.rs IMPL + V117 migration spec` 為 future redesign slot 保留；**本 AMD 不 retire ADR-0046；只 retire V2**。

Re-enable 須走完整 chain：
1. AMD amendment 立（super-cedes 本 AMD）+ V3 design rationale + cost-edge re-analysis + venue support proof
2. ADR-0046 Accepted（`funding_arb.rs` V3 IMPL + V117 migration spec 全 land）
3. 5-gate + Stage 0R replay preflight PASS（per AMD-2026-05-15-01）
4. Stage 1 Demo micro-canary 7d evidence
5. 三端 TOML `[funding_arb].active = false → true`（per V3 demo 觀察 + Stage 0R verdict）

revive 程式碼步驟詳 §7 Rollback Plan。

---

## 6. Decision 4 — Cleanup 三階段排程 (D+0 / D+7 / D+30)

### 6.1 D+0（2026-05-26 spec land 當天）

| Owner | Action | 估時 |
|---|---|---|
| PA (Phase 1 ✅) | spec land | 1 hr ✅ |
| PM | Operator confirm AMD draft | 5 min |
| **TW (Phase 2)** | **5 cascade target update (per §11)** | **1-1.5 hr** |
| R4 (Phase 2 並行) | docs grep + cross-ref audit | 1-1.5 hr |
| PA (Phase 1 follow-up) | TODO §1 ✅ CLOSED + §6 P1 entry + §9 Workflow F NEW row | 5 min ✅ |

**D+0 結束 AC**：
- AMD draft commit + operator sign-off
- TW 5 cascade target merged
- R4 cross-ref grep clean

### 6.2 D+7（2026-06-02）

| Owner | Action |
|---|---|
| E1 | `#[deprecated]` marker + runtime fail-closed guard IMPL (per §3.2) + cargo test + clippy clean |
| E2 | review IMPL（重點：registry.rs `#[allow(deprecated)]` scope 最小 + `update_params` fail-closed test 覆蓋） |
| E4 | regression — funding_arb cargo test 72/72 PASS + 跨 strategy registry 反向掛載 test PASS |
| MIT | helper_scripts/db/audit retire `2026-05-16_funding_arb_14d_audit.py` cron schedule |

**D+7 結束 AC**：
- Rust 程式碼層 `#[deprecated]` 全部 land
- runtime fail-closed guard verified
- 72/72 cargo test PASS
- audit script cron 自然停 fire

### 6.3 D+30（2026-06-25）

| Owner | Action |
|---|---|
| MIT | PG `risk_verdicts` / `position_snapshots` / `signals` / `order_state_changes` / `intents` 5 hypertable funding_arb 歷史 row 自然 V075 30d retention drop（**不執行手動 DELETE**） |
| QC | 30d post-deprecation observation — confirm 三端 0 funding_arb fill / 0 IPC active=true attempt / 0 runtime warn emit |
| PA | 30d follow-up report — confirm ADR-0046 future redesign slot 是否仍 actively referenced 或可同步 retire |

**D+30 結束 AC**：
- PG 歷史 row 30d 自然清空
- 30d 0 incident
- ADR-0046 slot 仍 active 或 retire 決策

---

## 7. Decision 5 — PG 歷史 Row 自然 retention（不手動 DELETE）

per V075 retention 30d + compression 7d：
- 5 hypertable（`risk_verdicts` / `position_snapshots` / `signals` / `order_state_changes` / `intents`）的 funding_arb 歷史 row 自然 30 天後 drop
- **不執行手動 DELETE**（避免破壞 attribution lineage + audit traceability）
- audit 用 helper script 仍可 query 30d 內歷史 sample

**理由**：手動 DELETE 會破壞跨 strategy attribution chain（per memory `project_decision_outcomes_not_dead` + ADR-0025 v3 track）；自然 retention 走是唯一 governance-clean 路徑。

---

## 8. Alternatives Considered（整合 §2.3 + §3.1）

| Alternative | 棄因 |
|---|---|
| 繼續觀察 (A) | 22d dormant + n 不累積 = deadlock |
| R-02 Strategist 重設計 V3 (B) | V2 在 Bybit 結構性無法 break-even；屬 ADR-0046 範疇非本 AMD scope |
| 純 docs-only mark deprecated (C) | TOML active 仍模糊；governance 不終結 |
| Hard-delete strategy code | ADR-0046 future slot 衝突 + SQL enum 不可破 + 72 test 損失 |
| Move to archive/ | Rust mod path 跨 crate 引用問題 + git history 等效 |
| 新立 ADR 而非 AMD | strategy retire 是 strategy-level directive 非 architecture decision；AMD 是正確 governance level |
| ADR-0018 升格而非新 ADR | ✅ **採納** — 沿用 ADR-0018 lineage 避免 ADR 爆炸 |

---

## 9. Consequences

### 9.1 Positive

- **Governance gap 補完**：ADR-0018 從 "retire from active set + W-AUDIT-6 cleanup pending" 升格 "Retired closed"；W-AUDIT-6 cleanup 路線終結
- **5 textbook roster → 4 textbook reframing**：TODO §1 P0-EDGE-1 AC + execution-plan v5.8 + MIT MIN_SAMPLES gating 同步收斂
- **MIT MIN_SAMPLES gating 計算減一個 dormant case**：per memory `project_2026_05_09_ml_training_cron_weekly` 4/5 策略不過，移除 funding_arb 後 4/4 baseline 更清晰
- **PA memory dormant audit 不再扣 audit budget**：22d dormant cycle 結束 + audit script cron retire
- **ADR-0018 status 從 "retire active set" 升格 "Retired closed"**：governance lifecycle 補完

### 9.2 Negative / Risk

- **ADR-0046 future redesign slot 仍占 mental space**：mitigation = D+30 PA follow-up 決定是否同步 retire ADR-0046
- **72 unit tests 持續維護成本**：dormant 結構驗值得保留，但 cargo test build time +N s；mitigation = 若 ADR-0046 retire，本 AMD amendment chain 觸發 hard-delete cascade
- **revive 路徑門檻高**：3 hard gate（AMD amendment + ADR-0046 Accepted + 5-gate Stage 0R）= 心理上 V2 不會回來；mitigation = operator 接受此 trade-off（per 2026-05-26 directive）

### 9.3 與既存設計協作

| 既存元素 | 與本 AMD 關係 |
|---|---|
| ADR-0018 funding_arb V2 dormant | **核心升格** — Status: Accepted → Retired |
| ADR-0046 (Proposed) future redesign slot | **並存保留**；本 AMD 不 retire；revive 必經 path |
| AMD-2026-05-09-02 W-AUDIT-6 strategy verdict | **終結點** — 09-02 提到「W-AUDIT-6 may implement RiskConfig cleanup」，本 AMD 是其 closure |
| AMD-2026-05-15-01 Stage 0R replay preflight | **revive gate** — 任何 V3 都需 Stage 0R PASS |
| AMD-2026-05-09-03 graduated canary | **revive gate** — 任何 V3 走 graduated canary |
| ADR-0025 v3 Track-Based Strategy Attribution | **不衝突** — historical row 自然 30d retention drop；attribution lineage 保留 |
| C10 funding_harvest（不同 strategy）| **不衝突** — C10 是 delta-neutral spot+perp matched notional，與 V2 directional 設計完全分離 |
| Earn Wave C governance | **不衝突** — Earn governance 屬 ADR-0031/0032 範疇，與 V2 retire 無交集 |
| funding_short_v2 (alpha candidate spec) | **不衝突** — funding_short_v2 是窄 short-only carve-out + 高 gate（per `2026-05-25--alpha_candidate_1_funding_short_v2_spec.md`），與 V2 directional bi-side 完全不同設計 |

---

## 10. Sign-off

| Role | Status | Date | Note |
|---|---|---|---|
| Operator | DIRECTIVE GIVEN | 2026-05-26 | (D) 3C TOML deprecation closure |
| PM | PENDING | — | Pending operator confirm before commit + cascade |
| CC | PENDING | — | 16 root principles compliance（特別 #4 strategies not bypass risk + #6 fail-closed + #8 reconstructable） |
| R4 | PENDING | — | docs/README + SPECIFICATION_REGISTER + ADR cross-ref cascade |
| TW | PENDING | — | TODO + KNOWN_ISSUES + SQL 註釋 + TOML 註釋 cascade |
| E1 (D+7) | PENDING | — | `#[deprecated]` marker + runtime fail-closed guard IMPL |
| E4 (D+7) | PENDING | — | 72 cargo test + cross-strategy regression |
| QC (D+30) | PENDING | — | 30d post-deprecation observation |
| MIT (D+30) | PENDING | — | PG retention drop verify + audit script cron retire |

---

## 11. Cascade Patch Checklist

待 operator confirm 後執行（per PA spec `2026-05-26--funding-arb-deprecation-cascade.md` §5 + §6）：

### 11.1 TW Primary cascade（5 個最關鍵 target）

1. `docs/README.md` § amendments table — 加 AMD-2026-05-26-01 row；ADR-0018 entry 加 "(Retired per AMD-26-01)"
2. `docs/governance_dev/SPECIFICATION_REGISTER.md` — ADR-0018 row Status → Retired；Lineage 加 AMD-26-01；Active AMD count +1
3. `docs/adr/0018-funding-arb-v2-deprecation-watch.md` — §Decision 升格 wording；Status 改 Retired；§Consequences 加 W-AUDIT-6 cleanup completion
4. `docs/KNOWN_ISSUES.md` line 480 — 5 textbook → 4 textbook (funding_arb retired per AMD-26-01)
5. `docs/execution_plan/2026-05-20--execution-plan-v5.8.md` — 5 textbook roster → 4 textbook；M7 strategy decay roster 對齊

### 11.2 TW Secondary cascade

- 3 個 `settings/strategy_params_{paper,demo,live}.toml` `[funding_arb]` 區段註釋追加 AMD-26-01 cross-ref
- 4 個 ADR cross-ref（0021 / 0025 / 0038 / 0039）行內 funding_arb 提及處追加「retired per AMD-26-01」
- 3 個 execution_plan dispatch packet（sprint_1a / sprint_2_business / alpha_candidate_1_funding_short_v2）cross-ref
- 6 個 SQL migration（V031 / V034 / V084 / V086 / V090 / V101）header comment 追加「funding_arb enum/case = historical-only post AMD-26-01；retain for backfill query」
- TODO `§1 P0-EDGE-1` AC cohort 改 4 textbook；`§6 P1-EDGE-2 (funding_arb)` → §-1 archive；標 P1-FUNDING-ARB-DEPRECATION-CASCADE IMPL DONE

### 11.3 R4 並行 cross-ref grep audit

- `srv/docs/` (排除 archive + CCAgentWorkSpace) grep `funding_arb|FundingArb|ADR-0018|funding-arb` ~40+ hit
- `srv/rust/openclaw_engine/src/` grep `funding_arb|FundingArb` 5 file
- `srv/sql/migrations/` grep `funding_arb` 6 file
- `srv/settings/` grep `funding_arb` 4 file
- `srv/helper_scripts/db/audit/` grep `funding_arb` 3 file
- 0 dangling reference 確認

### 11.4 不更新（保留歷史 lineage）

- 所有 `docs/audits/` — 歷史 audit 證據，加 superseded note 反而破壞 audit traceability
- `docs/CCAgentWorkSpace/*/workspace/reports/` — agent 歷史報告
- `docs/archive/*` — 已歸檔
- SQL `V031/V034/V084/V086/V090/V101` migration **content** — schema 已 land；只追加 header comment
- 5 hypertable historical row — 自然 30d 後 drop per V075 retention

---

**END AMD-2026-05-26-01**

Author: PA Workflow F Phase 1 spec + 主會話 TW Phase 2 起草（per operator 2026-05-26 directive）
Co-Authored-By: Claude Opus 4.7 (1M context)
