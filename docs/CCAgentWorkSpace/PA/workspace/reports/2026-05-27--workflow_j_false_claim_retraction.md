# Workflow J — PA spec「liquidation_pulse deleted」FALSE CLAIM 撤回 patch report

- 日期：2026-05-27
- 觸發：drift audit `docs/audits/2026-05-25--v1_to_v58_full_consolidation_drift.md` §11.3 J / §11.7 #4 / §13 P2
- BB push back：3 條（J + L25 + basis observation/execution）— 本 report 限 §1-§2 處理 J；§4 盤點其他 2 條
- 估時：1-2 hr（drift audit TODO §8.1 J）
- 實時：~25 min
- 是否變更 TODO：**否**（TODO patch 由主會話執行）

---

## §1 影響檔案清單

只搜出 1 份檔案存在「liquidation_pulse + (deleted|removed)」明確 false claim：

| # | 路徑 | 行號 | 原文 snippet | 性質 |
|---|---|---|---|---|
| 1 | `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md` | L243 | `pub liquidation_pulse: Option<&'a LiquidationPulse>,    // requires_revival flag — handler 已 4 weeks ago deleted（見 BB v3 NEW-6）` | FALSE CLAIM (inline 注釋) |
| 2 | 同上 | L259 | `**`liquidation_pulse` 復活前置條件**（BB v3 NEW-6）：OpenClaw 於 2026-04-06 已刪除 `allLiquidation` WS handler（字典手冊 line 990 證明）。... 必須**先付 +1 sprint 重接 WS handler + 重啟 writer**，期間此 alpha source 必須以 `requires_revival: true` flag 標記為 dormant ...` | FALSE CLAIM (段落) |

### 1.1 候選但未列入撤回的關連檔（仍存在「liquidation_pulse」字眼但語境不同）

| 路徑 | 行號 | 語境 | 是否撤回 |
|---|---|---|---|
| `2026-05-18--w_audit_8a_phase_b_c_d_worktree_decomposition.md` | L31, L56, L310-320 | 描述 C1-LIQ-WRITER 待 land；commit `0e8a8ae8` 已記錄 production WS revival CONFIRMED；spec 為 provider IMPL spec | **否** — 此 spec 為 J workflow 的 evidence 來源，描述 IMPL plan 而非錯誤 deletion claim |
| `2026-05-11--p0_replay_engine_counterfactual_fix_design.md` | L317 | 「Phase C Tier 3 microstructure：orderflow / liquidation_pulse」 — 純引用 alpha source 名 | 否 — 中性引用 |
| `2026-05-09--full_dispatch_engineering_plan.md` | L66, L186, L391 | 描述 W-AUDIT-8a Phase C 工作項目（含 `allLiquidation` parser revert）；當時為 backlog plan | **否** — 描述未來 IMPL plan 而非 deletion claim；此 plan 對應 W-AUDIT-8a Phase C 即 C1-LIQ-WRITER `0e8a8ae8`，現已 DONE（屬 stale 但非 false） |
| `2026-05-16--w_audit_8c_spec_pa_verdict.md` | L45 | 「`AlphaSurface.liquidation_pulse` already exist」 | 否 — 中性技術描述（已 exist 為正確） |
| `2026-05-18--w_audit_8c_spec_v0_3_field_shape_drift_fix.md` | L123, L126 | 「liquidation_pulse remains None for any strategy until W-AUDIT-8c IMPL lands」/「fail-closed missing/stale」 | 否 — 描述 W-AUDIT-8c 策略消費前的中性 gate 行為 |
| `2026-05-18--w_audit_8c_stage_0r_packet_design.md` | L124, L541, L696 | 「healthcheck [67] liquidation_pulse_freshness LANDED `d8938a78`」/「liquidation pulse provider IMPL (Wave 1 MERGED): `liquidation_pulse.rs`」 | 否 — 此 doc 已正確記錄 LANDED 狀態 |

**ZERO-IMPACT secondary file count：6**（不含主 patch 檔）。

---

## §2 撤回 patch 內容

### 2.1 Patch on `2026-05-09--full_loss_architectural_root_cause_redesign.md` L243（inline 注釋）

**Before**：
```rust
pub liquidation_pulse: Option<&'a LiquidationPulse>,    // requires_revival flag — handler 已 4 weeks ago deleted（見 BB v3 NEW-6）
```

**After**（原文保留 + 撤回標記）：
```rust
pub liquidation_pulse: Option<&'a LiquidationPulse>,    // requires_revival flag — handler 已 4 weeks ago deleted（見 BB v3 NEW-6）
// > **CORRECTION 2026-05-27**: 上一行 inline 注釋為 FALSE CLAIM，retract — `allLiquidation` WS handler + `liquidation_pulse.rs` 已於 2026-05-18 commit `0e8a8ae8` (W-AUDIT-8a C1-LIQ-WRITER) ACTIVE revive；`requires_revival` flag 不再需要，`liquidation_pulse` 為現役 alpha source（不再 dormant）。原文保留作 audit trail，禁止 IMPL 引用「4 weeks ago deleted」措辭。Source: drift audit `docs/audits/2026-05-25--v1_to_v58_full_consolidation_drift.md` §11.3 J + §11.7 #4。
```

### 2.2 Patch on `2026-05-09--full_loss_architectural_root_cause_redesign.md` L259 段落

**Before**：
```
**`liquidation_pulse` 復活前置條件**（BB v3 NEW-6）：OpenClaw 於 2026-04-06 已刪除 `allLiquidation` WS handler（字典手冊 line 990 證明）。`market.liquidations` 表雖 reserved 保留，但 R-1 IMPL 必須**先付 +1 sprint 重接 WS handler + 重啟 writer**，期間此 alpha source 必須以 `requires_revival: true` flag 標記為 dormant；策略 ctor 階段 declare `LiquidationCascade` 的，在 handler 復活前 surface 永遠 `None`，而不是 stub mock 數據。
```

**After**（原文保留 + 撤回 callout block 緊隨其後）：
```
**`liquidation_pulse` 復活前置條件**（BB v3 NEW-6）：OpenClaw 於 2026-04-06 已刪除 `allLiquidation` WS handler（字典手冊 line 990 證明）。`market.liquidations` 表雖 reserved 保留，但 R-1 IMPL 必須**先付 +1 sprint 重接 WS handler + 重啟 writer**，期間此 alpha source 必須以 `requires_revival: true` flag 標記為 dormant；策略 ctor 階段 declare `LiquidationCascade` 的，在 handler 復活前 surface 永遠 `None`，而不是 stub mock 數據。

> **CORRECTION 2026-05-27**: 上段「2026-04-06 已刪除 `allLiquidation` WS handler」為 FALSE CLAIM，retract — W-AUDIT-8a C1-LIQ-WRITER 2026-05-18 commit `0e8a8ae8` 已 land `rust/openclaw_engine/src/panel_aggregator/liquidation_pulse.rs` provider + 接線 `tick_pipeline/on_tick/step_4_5_dispatch.rs` + `AlphaSurface.liquidation_pulse` wire + healthcheck `helper_scripts/canary/healthchecks/80_liquidation_pulse_freshness.py` (canary rename [67]→[80] in drift audit §11.5)。`requires_revival: true` flag + 「+1 sprint 重接 WS handler」前置條件已不適用，`liquidation_pulse` 現為 ACTIVE alpha source；策略 ctor declare `LiquidationCascade` 的 surface 應由 freshness + topic age + parser-error rate gate 控制（W-AUDIT-8a Wave 1 已 MERGE），非 `requires_revival` flag。原文保留作 audit trail。Source: drift audit `docs/audits/2026-05-25--v1_to_v58_full_consolidation_drift.md` §11.3 J + §11.7 #4 + BB push back evidence in `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--w_audit_8a_phase_b_c_d_worktree_decomposition.md` line 31/56。
```

### 2.3 Patch 設計理由

- **不刪原文**：CLAUDE.md §Git 規則「Never revert changes you did not make」+ audit trail 原則；後來人需看到歷史脈絡（為何 R-1 spec 當時假設 handler dormant）
- **inline 而非檔頭 banner**：高密度技術 spec 文件，讀者跳讀某段時若只看 banner 易漏；inline callout 緊跟錯誤段保證任何引用該段的人立刻見撤回
- **evidence 帶 commit SHA + healthcheck 檔名**：未來再 audit 時可直接 grep `0e8a8ae8` / `80_liquidation_pulse_freshness.py` 重建 trail
- **明文禁措辭**：「禁止 IMPL 引用『4 weeks ago deleted』措辭」防後續 sub-agent 引此 spec 重犯

---

## §3 Cross-ref evidence

### 3.1 drift audit §11.3 J 原文

```
| J | PA spec「liquidation_pulse deleted」FALSE CLAIM | **liquidation_pulse.rs CONFIRMED ACTIVE** — W-AUDIT-8a C1-LIQ-WRITER 2026-05-18 commit `0e8a8ae8`;PA spec 該條為 FALSE CLAIM 應撤回 | PA 撤回該描述 (待派) |
```

### 3.2 drift audit §11.7 #4 原文

```
4. **J workflow**: PA 撤回「liquidation_pulse deleted」FALSE CLAIM spec 描述
```

### 3.3 W-AUDIT-8a C1-LIQ-WRITER evidence chain

| Evidence | Path / SHA | 內容 |
|---|---|---|
| Commit | `0e8a8ae8` (2026-05-18) | C1-LIQ-WRITER `liquidation_pulse.rs` provider land |
| Provider | `srv/rust/openclaw_engine/src/panel_aggregator/liquidation_pulse.rs` | ACTIVE Rust file |
| Healthcheck (renamed) | `srv/helper_scripts/canary/healthchecks/80_liquidation_pulse_freshness.py` | drift audit §11.5 rename [67]→[80] 16 tests PASS |
| PA spec evidence | `2026-05-18--w_audit_8a_phase_b_c_d_worktree_decomposition.md` L31 | 「production WS subscription IS now wired (`0e8a8ae8`)」 |
| PA spec evidence | 同上 L56 | 「production WS revival (DONE `0e8a8ae8`)」 |
| Spec wave 1 MERGED | `2026-05-18--w_audit_8c_stage_0r_packet_design.md` L696 | 「liquidation pulse provider IMPL (Wave 1 MERGED)」 |

證據鏈完整：commit ACTIVE → Rust file ACTIVE → healthcheck ACTIVE → 兩份後續 PA spec 已 ACK status。`2026-05-09` doc 為 stale doc（撰寫日早於 W-AUDIT-8a IMPL），撤回標記補上即可。

---

## §4 BB push back 其他 2 條狀態盤點

drift audit BB push back 3 條中除 J 外另 2 條：

### 4.1 L25（drift audit §11.3 I）

| 維度 | 狀態 |
|---|---|
| BB push back 內容 | Bybit V5 真實 depth levels = `1/50/200/1000`，無 L25；spec/IMPL/migration/healthcheck 禁「L25」字眼 |
| 在 PA workspace 出現位置 | `2026-05-09--full_loss_architectural_root_cause_redesign.md` L257（BB v3 NEW-5）+ `2026-05-03--ref20_sprint2_track_e_decision_lease_retrofit_design.md` 含 "lease_id" 字串非 "L25" 字眼（grep `-E "L25"` match 為 false positive） |
| L257 性質 | **正確記述（非 false claim）** — 該段本身就是「禁 L25」規則的描述 |
| 是否需撤回 | **否** — L257 是 BB push back 的 IMPL 規則記載，現役 spec 規則 |
| drift audit §11.3 I 結論 | SKILLS_TODO:66 L25/L84 是 walk-forward skill 行號 reference，非 WS depth tier；R4 audit confused；**Investigation DONE, no fix needed** |
| 動作 | **NO ACTION** — 既無 false claim 也無 audit 要求改 |

### 4.2 basis observation vs execution（drift audit §11.3 B）

| 維度 | 狀態 |
|---|---|
| BB push back 內容 | `basis_curve` (perp - spot) 在 Bybit demo 環境僅支援 observation；R-1 spec 需明文「basis = observation-only signal until mainnet」；demo 環境吃 `Basis` tag 策略 fail-closed |
| 在 PA workspace 出現位置 | `2026-05-09--full_loss_architectural_root_cause_redesign.md` L261（BB v3 NEW-8）+ `2026-05-09--full_dispatch_engineering_plan.md`（隱含 funding_arb 路徑） |
| L261 性質 | **正確記述（非 false claim）** — 該段是 BB push back 內容的 IMPL 規則記載 |
| 是否需撤回 | **否** — basis observation-only 為現役規則，BB APPROVE 候選 ADR-0046 將正式 formalize |
| drift audit §11.3 B 結論 | **BB APPROVE 候選 ADR-0046 basis-observation-execution-split**；scope 限 funding_arb；24-30 hr IMPL；Sprint 1A-δ/ε 平行 land |
| 動作 | **NO RETRACTION** — 但需 forward link：ADR-0046 land 後此 L261 段落應 amend 引用 ADR-0046 SSOT；屬 forward debt 非 retraction |
| 未來 follow-up | ADR-0046 IMPL 完成（drift audit §13 P1 B workflow，24-30 hr）後派 sub-agent 加 forward-link callout：「post-2026-05-2X: 該段 superseded by ADR-0046 §X.Y — basis observation/execution split formalized」 |

### 4.3 BB 3 條 push back 整體 status 表

| BB push back | Item | 動作 | 期限 |
|---|---|---|---|
| J liquidation_pulse deleted | FALSE CLAIM | **本 report 撤回**（§2 patch 2 處 land） | DONE 2026-05-27 |
| I L25 字眼 | 既無 false 也無 BB 撤回要求 | NO ACTION | N/A |
| B basis observation vs execution | 候選 ADR-0046 BB APPROVE | NO RETRACTION + ADR-0046 land 後 forward-link 補 | Sprint 1A-δ/ε（drift audit §13 P1） |

---

## §5 16 根原則 / 硬邊界檢核

| 原則 / 邊界 | 本 patch 是否觸碰 | 評估 |
|---|---|---|
| 原則 1 單一寫入口 | 否 | doc-only edit |
| 原則 2 讀寫分離 | 否 | doc-only |
| 原則 3 AI ≠ 命令 | 否 | doc-only |
| 原則 4 策略不繞風控 | 否 | doc-only |
| 原則 7 學習 ≠ 改寫 Live | 否 | doc-only |
| 原則 8 交易可解釋 | **+** | 撤回 false claim 提升歷史描述準確性 → audit trail 更可信 |
| 原則 10 認知誠實 | **+** | false claim retraction 是該原則的直接執行 |
| Hard Boundaries | 否 | 無 `live_execution_allowed` / `max_retries` / `OPENCLAW_ALLOW_MAINNET` / `authorization.json` 觸碰 |
| Mac/Linux 跨平台 | 否 | doc-only，無路徑硬編碼 |
| Rust-first | 否 | doc-only |

**評級**：A — 16/16 合規，0 hard boundary 觸碰，認知誠實 + 可解釋性正面強化。

---

## §6 AC 檢核

| AC | 狀態 | 證據 |
|---|---|---|
| 影響檔案 ≥ 1 | ✅ | 1 primary file `2026-05-09--full_loss_architectural_root_cause_redesign.md` 2 處 patch |
| 撤回標記語意明確 + 帶 evidence + 不刪原文 | ✅ | §2.1 + §2.2；inline callout 含 commit SHA `0e8a8ae8` + healthcheck 檔名 + drift audit cross-ref；原文 1:1 保留 |
| grep 結果 = 0 → ZERO-IMPACT closure | N/A | grep ≥ 1，已完成 patch |
| BB 3 條 push back 盤點 | ✅ | §4 完整盤點 J/I/B 三條 status + 動作 + 期限 |
| 不修改 TODO | ✅ | TODO patch 主會話執行（PA 不動 TODO） |

---

## §7 後續建議

1. **主會話 TODO patch**：drift audit §8.1 Workflow J 項目可 mark DONE，本 report 為 evidence
2. **Forward link debt**：ADR-0046 land 後（drift audit §13 P1 B workflow 完成），派 sub-agent 加 L261 forward-link callout（§4.2 動作項）
3. **反模式 memory**：建議 PA memory 加一條 lesson — 「IMPL plan spec 寫的「handler deleted」斷言必須帶 commit SHA + 日期 evidence；當 W-AUDIT 後續 commit 已 revive 時，spec 撰寫日 stale 是 false claim 的最大源頭」

---

PA DESIGN DONE: report path: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-27--workflow_j_false_claim_retraction.md`
