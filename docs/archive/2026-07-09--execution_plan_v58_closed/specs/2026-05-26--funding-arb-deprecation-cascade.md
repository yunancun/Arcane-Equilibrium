# PA Spec — funding_arb V2 Deprecation Cascade

**Date**: 2026-05-26
**Author**: PA (Project Architect)
**Status**: SPEC-FINAL / IMPL-PENDING（待 PM dispatch Phase 2 TW + R4）
**Workflow**: F (T2 waterfall+parallel) · Phase 1 PA spec only
**Severity**: P1（governance closure；無 P0 hard boundary）
**Reads**:
- TODO `srv/TODO.md` §1 第四列 `P0-FUNDING-ARB-DECISION-FORCE` (✅ CLOSED operator (D)) + §6 `P1-FUNDING-ARB-DEPRECATION-CASCADE` + §9 Workflow F NEW row + §15 #1/#5
- ADR `srv/docs/adr/0018-funding-arb-v2-deprecation-watch.md`（Accepted - retire from active strategy set）
- AMD 樣板 `srv/docs/governance_dev/amendments/2026-05-25--AMD-2026-05-25-01-commercialization-exchange-native-only.md` + `2026-05-25--AMD-2026-05-25-02-v55-bot-positioning-capital-structure-formalization.md`
- Memory `project_funding_arb_v2_deprecation_path` / `project_g2_funding_arb_monitor` / `feedback_env_config_independence`
- 既有 PA 報告 `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-25--h2_ea2_final_sop_refine.md`（EA-3 overturn 0 P1 hot-fix 結論延伸）
- Commit `a19797d`（2026-05-02 risk_config_demo base_ratio 0.4→0.25 + funding_arb 3% override，已 land）
- Rust strategy code `srv/rust/openclaw_engine/src/strategies/funding_arb.rs` (1203 行 / 72 unit tests) + `strategies/registry.rs:240-250`（單一 factory caller）+ `strategies/params.rs` (FundingArbParams) + `strategies/mod.rs:22-23`（pub mod funding_arb 註冊）
- 4 TOML `settings/strategy_params_{paper,demo,live}.toml` 全 `[funding_arb].active = false` + `settings/risk_control_rules/risk_config_demo.toml:196` base_ratio = 0.25（3C TOML）
- SQL `V031/V034/V084/V086/V090/V101` 6 migration 含 `funding_arb` enum / case branch（不可破壞 historical row）

---

## TL;DR — 3 字一句

**「Strategy 程式碼 keep with `#[deprecated]` marker（不刪、不 archive）；TOML 三端 active=false 已對齊（commit `7be1f9b` 起）；Cascade = AMD 立 + docs/README + ADR-0018 status 升格 retired + 5 個 SQL migration comment 標記 historical-only + 4 ADR cross-ref；Cleanup 三階段（D+0/D+7/D+30）；Rollback 路徑保留供 ADR-0046 future redesign slot 用。」**

---

## 0. Decision Lineage（為何 (D) 3C TOML deprecation 是終結路徑）

### 0.1 Operator 2026-05-26 (D) decision

| Stage | Trigger | Outcome |
|---|---|---|
| 2026-04-18 | G-2 v2 audit n=13 0/13 勝率 -36.76 bps NEGATIVE EDGE | demo `funding_arb.active=false` |
| 2026-05-02 | BUSDT demo -10.12 USDT (1 fill 6.29% notional) post 3C re-enable 範式 | operator 1B+2A+3C 三路：1B demo active=true 收 EDGE-DIAG-2 樣本 / 2A 中期棄策略 / 3C TOML 緊 SL → 已 land commit `a19797d` |
| 2026-05-03 | 三端統一 disable | paper/demo/live `[funding_arb].active = false` |
| 2026-05-09 | ADR-0018 Accepted | retire from active strategy set + W-AUDIT-6 cleanup pending |
| 2026-05-16 | `helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.py` n=18 dormant 確認 | n 不再累積；P1-EDGE-2 升 P0-FUNDING-ARB-DECISION-FORCE deadlock |
| 2026-05-25 | QC EA-3 升 P1 hot-fix（6.29% 違 5% SL gate claim） | PA overturn — 6.29% 是 demo dyn_stop floor 6.25% + 0.04pp 設計範圍內，非 bug；建議 reclassify P3 documentation-only carry-over |
| **2026-05-26** | **operator chose (D) 3C TOML deprecation closure** | **本 spec Phase 1** |

### 0.2 QC EA-3 verdict 衍生條件（仍 active）

QC EA-3 verdict（per PA overturn report）：funding_arb V2 delta-neutral 數學不成立 + Bybit demo 無 spot lending → V2 在 Bybit demo + Bybit mainnet 都無法 break-even（cost 34 bps / funding mean 1.5 bps → break-even 7.6 day too costly）。

**結論**：V2 是 architecturally infeasible 在當前 venue（Bybit）。V2 不是「參數沒調對」可以 R-02 Strategist 重評救活；是 design 層面 stuck。

### 0.3 4 alternatives operator 拒絕原因

| 選項 | 拒因 |
|---|---|
| (A) 繼續觀察 | 22 天 dormant + n 不累積 = deadlock；無 closure 路徑 |
| (B) R-02 Strategist 重設計 V3 | 既有 V2 在 Bybit demo 結構性無法 break-even；重設計屬 ADR-0046 future redesign slot 範疇，不是 V2 closure |
| (C) 純 docs-only mark deprecated | TOML active 仍是「dormant pending re-eval」語意，governance 模糊；不終結 |
| **(D) 3C TOML deprecation closure** | **明確 retire + cleanup + 公開封存；ADR-0018 status 升格；ADR-0046 future redesign slot 並存** |

---

## 1. Code Path Deprecation — 推薦 (c) keep with `#[deprecated]` marker

### 1.1 三個 alternatives 比較

| 方案 | 推薦 | 理由 |
|---|---|---|
| (a) Hard-delete `funding_arb.rs` + 移除 registry/params/mod.rs 註冊 | ❌ | (i) ADR-0046 (Proposed) 明示 `funding_arb.rs IMPL` 為 future redesign slot（TODO §9）；(ii) SQL V031/V034/V084/V086/V090/V101 6 migration enum/case 含 `'funding_arb'` 硬編碼 — 程式碼刪除後 historical row 仍 query；(iii) 72 unit tests 是 dormant 結構驗（per memory `cross_strategy_attribution_integrity:22`），刪除損失測試覆蓋；(iv) Rust mod tree + factory 拔除屬高風險 + 編譯破壞風險 |
| (b) Move to `archive/funding_arb_v2/` | ❌ | (i) Rust mod path 不能跨 crate 引用 archive subdir，需大規模重組；(ii) registry.rs 仍需 stub；(iii) git history 已是 ARCHIVE 等效，沒 add value；(iv) PA memory `project_funding_arb_v2_deprecation_path` 5489 行 `保留 funding_arb.rs 為 R-02 重設計 slot marker` 既定路線 |
| **(c) Keep with `#[deprecated]` marker + runtime active=false hard guard** | ✅ | (i) 與 ADR-0018 「retain auditability」一致；(ii) ADR-0046 future redesign slot pattern；(iii) SQL enum 不破；(iv) compiler warning IDE 立即可見；(v) registry 既有 `set_active(p.funding_arb.active)` 路徑 + TOML active=false 雙保險 fail-closed；(vi) 0 編譯 break + 0 test loss |

### 1.2 (c) IMPL 細節（PA design，E1 Phase 2 後續派工）

**Phase 1 spec only — 本 spec 不執行；下列為 E1 dispatch 指南。**

#### 1.2.1 `funding_arb.rs` mod-level deprecation marker

```rust
//! 資金費率套利策略 V2 — 方向性資金費率捕獲（dormant per ADR-0018 / AMD-2026-05-09-02）。
//!
//! **DEPRECATED 2026-05-26 per AMD-2026-05-26-01**（operator (D) 3C TOML deprecation closure）。
//! Bybit demo 無 spot lending + cost 34 bps / funding mean 1.5 bps → break-even 7.6 day
//! 結構性無法 close gap。本模組保留作為 ADR-0046 future redesign slot；運行時硬鎖
//! `[funding_arb].active = false` 三端統一；任何 IPC `update_params(active=true)` 須先解 AMD。
//! ...

#![deprecated(
    since = "2026-05-26",
    note = "funding_arb V2 retired per AMD-2026-05-26-01 + ADR-0018. Slot reserved for ADR-0046 redesign. Do not re-enable without AMD amendment."
)]
```

**注意**：Rust mod-level `#![deprecated]` 不支援；改為 mod doc `//!` 註記 + 對 `pub struct FundingArb` / `pub fn new()` / `pub fn update_params()` 加 item-level `#[deprecated]`。registry.rs 用 `#[allow(deprecated)]` 包住 factory 段落（line 240-250），同時加 `tracing::warn!` 在 `FundingArb::new()` 首次 instantiate 時 emit deprecation lineage 提醒。

#### 1.2.2 runtime fail-closed guard

`FundingArb::update_params()`（line 156-177）加 hard guard：

```rust
pub fn update_params(&mut self, params: FundingArbUpdateParams) -> Result<(), String> {
    if params.active {
        return Err(
            "funding_arb V2 deprecated per AMD-2026-05-26-01 + ADR-0018; \
             active=true rejected. ADR-0046 future redesign required.".into()
        );
    }
    // 既有邏輯不動
    params.validate()?;
    self.active = false;  // 強制 false，忽略 params.active
    ...
}
```

**安全不變量**：即使 TOML 被誤改 active=true 或 IPC 注入 active=true，runtime layer fail-closed 拒絕；防 fat-finger 解 deprecation。

#### 1.2.3 registry.rs factory 標記

`strategies/registry.rs:240` 加註：

```rust
// FundingArb V2 dormant per ADR-0018 + DEPRECATED per AMD-2026-05-26-01.
// Slot reserved for ADR-0046 future redesign. set_active forced false.
#[allow(deprecated)]
let mut fa = funding_arb::FundingArb::new();
fa.set_active(false);  // 不再讀 p.funding_arb.active；強制 false
// ...其餘 fa.xxx = p.funding_arb.xxx 仍保留（為 future ADR-0046 redesign slot 提供 param 載入 path）
```

#### 1.2.4 72 tests retention

72 個 unit tests 全部保留為 dormant 結構驗（per memory `cross_strategy_attribution_integrity` 模式）。`mod tests` 開頭加註：

```rust
#[cfg(test)]
#[allow(deprecated)]  // dormant 結構驗 per ADR-0018 + AMD-2026-05-26-01
mod tests {
    ...
}
```

### 1.3 對 5 textbook strategy roster 的影響

| 既有 5 textbook | 處置 |
|---|---|
| ma_crossover | 不動 |
| bb_breakout | 不動 |
| bb_reversion | 不動 |
| grid_trading | 不動 |
| **funding_arb** | **roster 移除**；新 roster = **4 textbook** |

**對應 doc / spec / SQL 更新**（屬 R4 cascade scope，本 spec §6 列）：
- TODO `§6 P1-EDGE-2 (funding_arb)` 結案
- TODO §1 P0-EDGE-1 AC 描述「5/5 textbook」→「4/4 textbook（funding_arb retired）」
- v5.8 execution-plan textbook list update
- SQL V090__governance_unblock_candidates 註釋 line 505 `'ma_crossover, bb_breakout, bb_reversion, funding_arb (post-ADR-0018 retired).'` → 加 AMD-26-01 cross-ref（不改 enum）
- MIT MIN_SAMPLES gating（per memory `project_2026_05_09_ml_training_cron_weekly` 4/5 策略不過）→ 4/4 reframing

---

## 2. Config Deprecation

### 2.1 三端 TOML 現況（PA 親讀 2026-05-26）

| TOML | active | base_ratio (dynamic_stop) | 備註 |
|---|---|---|---|
| `strategy_params_paper.toml:134-141` | `active = false` | (n/a paper) | G2-FUP 2026-04-26 三端統一 disable 記註存 |
| `strategy_params_demo.toml:165-172` | `active = false` | (per risk_config_demo) | 2026-05-03 三端統一停 |
| `strategy_params_live.toml:136-143` | `active = false` | (n/a live) | OC-5 三端統一關閉 |
| `risk_config_demo.toml:196` | – | `base_ratio = 0.25` (3C commit `a19797d`) | 全 demo 策略 dyn_stop floor 收緊 |
| `risk_config_paper.toml:169` | – | `base_ratio = 0.30` | env-isolation principle preserved |
| `risk_config_live.toml:179` | – | `base_ratio = 0.5` | env-isolation principle preserved |
| `risk_config_demo.toml:97` | – | – | `per_strategy.funding_short_v2.stop_loss_max_pct_override=3.0` (1B 3% tight SL 範式 cross-ref funding_arb) |

**結論**：TOML 100% 已 inactive，commit `a19797d` 已 land 全部必要改動；本 spec **不要求新 TOML 改動**（避免 scope creep）。

### 2.2 註釋更新（Phase 2 TW scope）

paper/demo/live 三個 `strategy_params_*.toml` 的 `[funding_arb]` 區段註釋追加 AMD-2026-05-26-01 cross-ref：

```toml
# 2026-05-26 DEPRECATED per AMD-2026-05-26-01 + ADR-0018:
# operator (D) 3C TOML deprecation closure post 22d dormant since 2026-05-03.
# V2 結構性無法 break-even (Bybit demo 無 spot lending + 34 bps cost / 1.5 bps funding mean).
# 程式碼層 #[deprecated] marker + runtime fail-closed active=false hard guard.
# Slot reserved for ADR-0046 future redesign.
[funding_arb]
active = false  # 三端硬鎖；prog-layer 拒絕 IPC active=true
...
```

**TW 不可刪除 `[funding_arb]` 區段**：刪除會破壞 `FundingArbParams` deserialize（registry.rs 仍引用）；只追加註釋。

---

## 3. AMD Draft 大綱 — **AMD-2026-05-26-01 funding-arb-deprecation**

### 3.1 編號建議

下一個 AMD 序號 = `AMD-2026-05-26-01`（25 號最後是 `-02`，26 號 0 篇）。

### 3.2 骨架

```markdown
# AMD-2026-05-26-01 — funding_arb V2 Deprecation Closure

Date: 2026-05-26
Status: **Proposed-pending-operator-confirm**
Operator Sign-off: 2026-05-26 directive — 對 P0-FUNDING-ARB-DECISION-FORCE 選 (D) 3C TOML deprecation closure
PM Sign-off: 本 draft；批准前 cascade 不執行

Supersedes:
- `docs/adr/0018-funding-arb-v2-deprecation-watch.md` §Decision「retire from active strategy set」**狀態升格**
  為「retired with code-level deprecation marker + AMD-level closure governance」；ADR-0018 §Decision
  rewording per §9 cascade（不另立新 ADR）

Related:
- ADR-0018 (status 升格)
- ADR-0046 (Proposed) `funding_arb.rs IMPL + V117 migration spec`（future redesign slot 保留）
- AMD-2026-05-09-02 (W-AUDIT-6 strategy verdict 對應 cleanup 終結點)
- AMD-2026-05-09-03 (graduated canary default；Stage 0R replay preflight 範式)
- Memory `project_funding_arb_v2_deprecation_path` (1B+2A+3C operator 決策 lineage)
- Commit `a19797d` (2026-05-02 TOML 改動已 land)
- Helper script `helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.py` (n=18 dormant 確認證據)
- TODO `P0-FUNDING-ARB-DECISION-FORCE` (CLOSED 2026-05-26) + `P1-FUNDING-ARB-DEPRECATION-CASCADE`

---

## 1. Status

**Proposed-pending-operator-confirm**

本 AMD 為 operator 2026-05-26 對 `P0-FUNDING-ARB-DECISION-FORCE` 選 (D) 3C TOML deprecation closure
的正式 governance 化。

## 2. Context

### 2.1 22 天 dormant lineage

(摘 §0 decision lineage 表 + 22d dormant 自 2026-05-03 三端 active=false)

### 2.2 QC EA-3 verdict architectural rationale

(摘 QC EA-3：V2 delta-neutral 數學不成立 + Bybit demo 無 spot lending + 34 bps cost / 1.5 bps
funding mean / 7.6 day break-even infeasible)

### 2.3 4 alternatives 拒因

(摘 §0.3 表)

## 3. Decision 1 — Strategy Code 程式碼層 `#[deprecated]` marker

(摘 §1.2 IMPL 設計細節)

## 4. Decision 2 — TOML active=false 終結

(摘 §2 三端 TOML 現況 + commit `a19797d` 已 land + 註釋追加 AMD cross-ref)

## 5. Decision 3 — Future Redesign Slot Preservation

ADR-0046 (Proposed) `funding_arb.rs IMPL + V117 migration spec` 為 future redesign slot 保留；
本 AMD **不** retire ADR-0046；只 retire V2。Re-enable 須走 AMD amendment chain + ADR-0046
land + 5-gate + Stage 0R replay preflight + 全新 governance review。

## 6. Decision 4 — Cleanup 三階段 (D+0 / D+7 / D+30)

(摘 §7 cleanup 排程)

## 7. Decision 5 — PG 殘留 Historical Row 保留

(per V075 retention 30d + compression 7d) `risk_verdicts` / `position_snapshots` / `signals` /
`order_state_changes` / `intents` 5 hypertable 之 funding_arb 歷史 row 自然 30d 後 drop；
**不執行手動 DELETE**（避免破壞 attribution lineage）；audit 用 helper script 仍可 query。

## 8. Alternatives Considered

(摘 §0.3 + §1.1)

## 9. Consequences

### 9.1 Positive
- governance gap 補完
- 5 textbook roster → 4 textbook reframing
- MIT MIN_SAMPLES gating 計算減一個 dormant case
- PA memory dormant audit 不再扣 audit budget
- ADR-0018 status 從 "retire active set" 升格 "retired closed"

### 9.2 Negative / Risk
- ADR-0046 future redesign slot 仍占 mental space
- 72 unit tests 持續維護成本（dormant 結構驗值得，但 cargo test build time +N s）
- mitigation = 若 ADR-0046 retire，本 AMD amendment chain 觸發 hard-delete cascade

### 9.3 與既存設計協作
(摘 §1.3 + §6 R4 cross-ref 列)

## 10. Sign-off

| Role | Status | Date | Note |
|---|---|---|---|
| Operator | DIRECTIVE GIVEN | 2026-05-26 | (D) 3C TOML deprecation closure |
| PM | DRAFT | 2026-05-26 | Pending operator confirm before commit + cascade |
| CC | PENDING | — | 16 root principles compliance（特別 #4 strategies not bypass risk + #6 fail-closed） |
| R4 | PENDING | — | docs/README + SPECIFICATION_REGISTER cascade |
| TW | PENDING | — | TODO/KNOWN_ISSUES/SQL註釋 cascade |

## 11. Cascade Patch Checklist

(對應本 spec §5 TW cascade + §6 R4 cross-ref 列；待 operator confirm 後執行)

---

**END AMD-2026-05-26-01**
```

### 3.3 與既存 ADR/AMD 對齊原則

- **不新增 governance class**（per PA constraint）：升格 ADR-0018 §Decision wording，不立新 ADR
- **AMD-level governance**（不是 ADR-level）：strategy retire 屬 strategy-level directive 非 architecture decision
- **與 AMD-2026-05-09-02 chain 接續**：09-02 W-AUDIT-6 strategy verdict 提到「W-AUDIT-6 may implement active RiskConfig cleanup」；本 AMD 是其終結點

---

## 4. R4 Cross-ref 清單

### 4.1 必驗 grep target（5 sources）

| Source | Grep pattern | 預期 hit |
|---|---|---|
| `srv/docs/` (排除 archive + CCAgentWorkSpace) | `funding_arb\|FundingArb\|ADR-0018\|funding-arb` | ~40+ hit 跨 README + KNOWN_ISSUES + 4 ADR (0018/0021/0025/0038/0039) + 7+ execution_plan + audit + reference 共 ~26 file |
| `srv/rust/openclaw_engine/src/` | `funding_arb\|FundingArb` | 5 file（funding_arb.rs / mod.rs / params.rs / registry.rs / cross_strategy_attribution_integrity.rs / strategy_params.rs / ws_client/parsers.rs / edge_predictor/feature_builder.rs） |
| `srv/sql/migrations/` | `funding_arb` | 6 file（V031/V034/V084/V086/V090/V101 case branch + enum；不可破壞） |
| `srv/settings/` | `funding_arb` | 4 file（3 strategy_params + 1 risk_config_demo 註釋 ref） |
| `srv/helper_scripts/db/audit/` | `funding_arb` | 3 file（2 audit script + 1 test） |

### 4.2 必更新 file（cross-ref graph）

```
AMD-2026-05-26-01 (NEW)
 │
 ├── ADR-0018 §Decision 升格 wording (R4 in-place update; 不新立 ADR)
 │   └── ADR-0046 (Proposed) keep — future redesign slot reference
 │
 ├── docs/README.md
 │   ├── line 498 E1 report ref (keep historical link)
 │   └── line 782 ADR-0018 entry (status: retired + AMD-26-01 cross-ref)
 │
 ├── docs/governance_dev/SPECIFICATION_REGISTER.md
 │   ├── ADR-0018 entry 升 Status="Retired"（既有 lineage AMD-2026-05-09-02 + 加 AMD-2026-05-26-01）
 │   └── Active AMD count +1
 │
 ├── docs/KNOWN_ISSUES.md
 │   └── line 480 「5 textbook strategies funding_arb」→ 「4 textbook (funding_arb retired per AMD-26-01)」
 │
 ├── docs/adr/0021-alpha-source-architecture-upgrade.md
 │   └── grep funding_arb 行追加「retired per AMD-26-01」
 │
 ├── docs/adr/0025-track-based-strategy-attribution.md
 │   └── 同上
 │
 ├── docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md
 │   └── 同上
 │
 ├── docs/adr/0039-m12-order-router-trait-and-maker-fill-rate-metric.md
 │   └── 同上
 │
 ├── docs/execution_plan/2026-05-20--execution-plan-v5.8.md
 │   └── 5 textbook roster → 4 textbook + funding_arb retired note
 │
 ├── docs/execution_plan/2026-05-21--sprint_1a_dispatch_packet.md
 │   └── grep funding_arb 行加 retired note
 │
 ├── docs/execution_plan/2026-05-25--sprint_2_business_dispatch_packet.md
 │   └── 同上
 │
 └── docs/execution_plan/2026-05-25--alpha_candidate_1_funding_short_v2_spec.md
     └── funding_arb V2 (ADR-0018 dormant) cross-ref 加 AMD-26-01
```

### 4.3 不更新（保留歷史 lineage）

- 所有 `docs/audits/` — 是歷史 audit 證據，加 superseded note 反而破壞 audit traceability
- `docs/CCAgentWorkSpace/*/workspace/reports/` — agent 歷史報告
- `docs/archive/*` — 已歸檔
- SQL `V031/V034/V084/V086/V090/V101` migration content — 是 schema 物理 land；只追加 SQL comment header（per §5 TW cascade）
- 5 hypertable historical row — 自然 30d 後 drop per V075 retention

---

## 5. TW Cascade 清單（5 個最關鍵 update target）

| Priority | Target | Update | Owner |
|---:|---|---|---|
| **1** | `docs/README.md` § amendments table | 加 AMD-2026-05-26-01 row；line 782 ADR-0018 entry 加 "(Retired per AMD-26-01)" | TW |
| **2** | `docs/governance_dev/SPECIFICATION_REGISTER.md` | (i) ADR-0018 row Status 改 `Retired`；Lineage 加 `AMD-2026-05-26-01`；(ii) Active AMD count +1；(iii) 加 AMD-2026-05-26-01 row | TW |
| **3** | `docs/adr/0018-funding-arb-v2-deprecation-watch.md` | §Decision 升格 wording「Retired closed per AMD-2026-05-26-01 + code-level `#[deprecated]` marker + runtime fail-closed guard」；§Consequences 加「W-AUDIT-6 cleanup completion = Workflow F (2026-05-26)」 | TW |
| **4** | `docs/KNOWN_ISSUES.md` line 480 | 「5 textbook strategies」→「4 textbook strategies (funding_arb retired per AMD-26-01)」；P0-EDGE-1 cohort 描述同步 | TW |
| **5** | `docs/execution_plan/2026-05-20--execution-plan-v5.8.md` | 5 textbook roster → 4 textbook；M7 strategy decay roster 對齊；textbook count 全文 grep 修正 | TW |

**次優先**（TW 同 wave 一併處理）：
- 三個 strategy_params TOML 註釋（per §2.2）
- 4 ADR cross-ref（0021 / 0025 / 0038 / 0039）
- 3 execution_plan dispatch packet cross-ref
- 6 SQL migration file header comment 加「funding_arb enum/case = historical-only post AMD-26-01；retain for backfill query」
- TODO `§1 P0-EDGE-1` AC wording cohort 改 4 textbook + §6 `P1-EDGE-2 (funding_arb)` 結案 → `§-1 archive`

---

## 6. Cleanup 三階段排程

### 6.1 D+0（2026-05-26 spec land 當天）

| Owner | Action | 估時 |
|---|---|---|
| PA (Phase 1 ✅) | 本 spec land | 1 hr ✅ |
| PM | Operator confirm AMD-2026-05-26-01 draft | 5 min |
| TW (Phase 2 dispatch) | 5 cascade target update (per §5) | 1-1.5 hr |
| R4 (Phase 2 dispatch) | docs grep + cross-ref audit (per §4) | 1-1.5 hr |
| PA (Phase 1 follow-up) | TODO §1 第四列 ✅ CLOSED 已記 / §6 P1 entry 已 NEW；§9 Workflow F NEW row 已記；驗 §15 #1 reframing OK ✅ | 5 min |

**D+0 結束 AC**：
- AMD draft commit + operator sign-off
- TW 5 cascade target merged
- R4 cross-ref grep clean

### 6.2 D+7（2026-06-02）

| Owner | Action |
|---|---|
| E1 | `#[deprecated]` marker + runtime fail-closed guard IMPL（per §1.2）+ cargo test + clippy clean |
| E2 | review IMPL（重點：registry.rs `#[allow(deprecated)]` 範圍最小 + `update_params` fail-closed test 加） |
| E4 | regression — funding_arb cargo test 72/72 PASS + 跨 strategy registry 反向掛載 test PASS |
| MIT | helper_scripts/db/audit retire `2026-05-16_funding_arb_14d_audit.py` cron schedule（per `project_2026_05_09_ml_training_cron_weekly` schedule 表） |

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

## 7. Rollback Plan

### 7.1 為何需要 rollback path（safety net）

雖然 (D) 是 operator 終結決策，但 ADR-0046 future redesign slot 仍 (Proposed)；若未來 ADR-0046 land 重設計 V3（per memory `cross_strategy_attribution_integrity` future redesign slot pattern），需明確 revive 路徑。

### 7.2 Rollback 三條件（hard gate）

1. **AMD amendment 立**：新 AMD「funding_arb V3 re-enable」super-cedes AMD-2026-05-26-01；含 V3 design rationale + cost-edge re-analysis + venue support proof
2. **ADR-0046 Accepted**：funding_arb.rs IMPL + V117 migration spec 全 land
3. **5-gate + Stage 0R replay preflight**：per AMD-2026-05-15-01 三端 Stage 0R replay PASS + Stage 1 Demo

### 7.3 程式碼層 revive 步驟

1. AMD-2026-05-26-01 §Decision 1 wording 改「retired → conditional revive per ADR-0046」
2. `funding_arb.rs` mod doc 註解 update；`#[deprecated]` marker 移除（或 #[deprecated(note="V3 deployment in progress")]）
3. `update_params()` fail-closed guard 條件改：`if params.active && !env::var("FUNDING_ARB_V3_AMD_REVIVED").is_ok() { return Err(...) }`（防意外）
4. registry.rs `#[allow(deprecated)]` 移除；`set_active` 改回讀 TOML
5. 三端 TOML `[funding_arb].active = false → true`（per V3 demo 觀察 + Stage 0R verdict）

### 7.4 資料完整性保證

- 6 SQL migration `funding_arb` enum/case 從未刪除 → 直接 re-deploy 後 fills/decision_features 寫入無需 schema 改動
- 72 unit tests 從未刪除 → revive 後 cargo test 直接覆蓋
- PG historical row 30d 後 drop 對 revive 無影響（V3 重新累積 sample 不依賴 V2 歷史）

---

## 8. Acceptance Criteria（Phase 1 spec sign-off）

| AC | 描述 | 驗證方式 |
|---|---|---|
| **(a)** | Strategy code path frozen | Phase 2 後 `grep #\[deprecated\] funding_arb.rs` returns ≥3 hit；`update_params` runtime fail-closed test PASS |
| **(b)** | TOML 100% inactive | `grep active.*=.*false` 三端 `[funding_arb]` 全 hit；`a19797d` commit `git log` 可查 |
| **(c)** | AMD + cascade docs 全 land | AMD-2026-05-26-01 commit；§5 5 cascade target merged；§4 R4 cross-ref clean |
| **(d)** | Strategy roster 4 textbook reduced | docs grep「5 textbook」應 ≤ 1 hit（保留 audit lineage）；其餘改「4 textbook」 |
| **(e)** | 不影響其他 4 textbook + C10 funding_harvest + Earn Wave C runtime | 30d observation 0 regression；4 textbook + C10 + Earn 三 PG runtime healthy |

---

## 9. Phase 2 Dispatch Readiness（TW + R4 並行）

### 9.1 Phase 2 派工建議

| Agent | Task | Input | Output | 估時 | 依賴 |
|---|---|---|---|---:|---|
| TW | §5 5 cascade target update + 次優先（3 TOML 註釋 / 4 ADR cross-ref / 3 dispatch packet / 6 SQL header comment / TODO §1 + §6） | 本 spec §4 + §5 + AMD-2026-05-26-01 draft（per §3.2 骨架） | TW cascade report；commit chain；merged PR | 1.5-2 hr | 本 spec land + AMD draft commit |
| R4 | §4 cross-ref grep audit + cross-ref graph verify | 本 spec §4.1 grep target + §4.2 cross-ref graph | R4 audit report；0 dangling reference 確認 | 1-1.5 hr | TW cascade ≥80% merged |
| PM | Operator AMD-2026-05-26-01 sign-off | AMD draft（per §3.2） | sign-off commit | 5 min | 本 spec land |

### 9.2 並行依賴關係

```
本 spec land (PA Phase 1) ──┬─→ AMD draft + PM operator sign-off ──┬─→ TW cascade (1.5-2 hr)
                            │                                       │
                            └──→ TW + R4 並行可啟動 ─────────────────┴─→ R4 cross-ref audit (1-1.5 hr)
                                                                          │
                                                                          └──→ Workflow F closure
```

### 9.3 Phase 2 後 (E1 D+7) follow-up dispatch readiness

- E1 dispatch packet：`funding_arb.rs` `#[deprecated]` IMPL + runtime fail-closed guard + registry.rs `#[allow(deprecated)]` (per §1.2 設計)
- E2 review focus：(i) `#[allow(deprecated)]` scope 最小（只包 factory line 240-250）(ii) `update_params` fail-closed test 覆蓋 (iii) `cross_strategy_attribution_integrity` dormant 結構驗 72 test 全 PASS
- E4 regression：cargo test + clippy clean + 跨 strategy registry roundtrip 反向掛載 test

---

## 10. Risk Register

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | TW cascade 漏改 file 致 docs grep dangling | MED | R4 並行 cross-ref grep audit；§4.1 grep target 列明 |
| R2 | E1 IMPL Phase 改 registry.rs 觸發 cargo build cascade 影響其他 strategy | MED | E2 review 強制重點 `#[allow(deprecated)]` scope 最小；E4 跨 strategy 反向掛載 test |
| R3 | SQL 6 migration enum 含 'funding_arb' 未來 backfill query break | LOW | enum 保留；historical row 自然 V075 30d 後 drop；audit script 不需重寫 |
| R4 | ADR-0046 future redesign slot 變成「dead code with marker」 | LOW | D+30 PA follow-up 決定是否同步 retire ADR-0046 |
| R5 | operator 未來改主意想 revive | LOW | §7 Rollback Plan 完整覆蓋 3 hard gate |
| R6 | 72 dormant unit tests 持續 build time 成本 | LOW | 計算可承受（per memory `cross_strategy_attribution_integrity` 已先例） |

---

## 11. PA Hard Constraints Verify

| Constraint | 驗證 |
|---|---|
| Spec-only, 不改 Rust strategy code 也不改 TOML | ✅ 本 spec 0 Rust edit + 0 TOML edit |
| 不執行任何 deployment | ✅ Phase 1 純文件設計 |
| 引用既有 ADR / AMD format，不新增 governance class | ✅ AMD-2026-05-26-01 沿用 AMD-25-01/25-02 樣板；ADR-0018 升格而非新立 |
| Chinese-first per memory `feedback_chinese_only_comments` | ✅ 中文為主，技術名詞 / commit / 代碼保留英文 |
| 不擴 scope（只做 funding_arb，不碰 C10 funding_harvest / Earn Wave C） | ✅ §1.3 + AC (e) + §4.2 cross-ref 全部排除 C10 / Earn |

---

## 12. PA Sign-off

| Role | Status | Date |
|---|---|---|
| PA | SPEC-FINAL | 2026-05-26 |
| PM | PENDING | — |
| Operator | DIRECTIVE GIVEN (D) 2026-05-26 | — (AMD-2026-05-26-01 confirm pending) |

**END PA Spec — Workflow F Phase 1**
