# P0-LG-3 Spec Verify + TODO Patch Draft

**Date**: 2026-05-27
**Owner**: PA
**Trigger**: Operator audit — TODO §1 行 46 / §6 P1-LG-3-AC-CORRECTION / §15 #1 三處 drift 仍掛在 TODO；2026-05-26 PA workspace 已 land 兩份 spec（v2 amendment + V104 scaffold 378 LOC）但 TODO 表面文字尚未完全反映 CLOSED 結果。任務 = verify 既有 spec 是否完整解決 3 drift；出 TODO patch 草稿。
**Status**: VERIFY DONE — 3/3 drift FULLY COVERED；TODO patch ready；IMPL DISPATCH gated by 2 external item only。

---

## §1 既有 spec 對 3 drift 的覆蓋率

| Drift | TODO 既有描述 | Spec 對策 land 位置 | 覆蓋率 |
|---|---|---|---|
| **(a)** §2.4A "fee_source tick-time consumer" NOT-FOUND | TODO §1 行 46 「§2.4A 'fee_source tick-time consumer' 全 docs grep 0 hit 為 wording drift 移除」 | spec v2 amendment line 1796「移除此 AC claim」+ PA report §1.1 A1 amendment + QA 2026-05-21 verify confirm fee_source = startup assertion + IPC contract by-design per §2.4，非 tick-time consumer | ✅ **FULLY COVERED** |
| **(b)** V099 / V100 已被占用 | TODO §1 行 46「V099 已被 autonomy_level_config 預留 + V100 已 land m4_hypothesis_base_table」 | spec v2 amendment A1（line 1775-1786 V### renumber 表）+ V104 scaffold 378 LOC + PA report §1.2 / §3.2 / §4 V099/V100 不再使用 + LG-3 取 V104 | ✅ **FULLY COVERED** |
| **(c)** §15 #1 LG-3 ↔ funding_arb FALSE dep | TODO §15 line 377 「REFRAMED 2026-05-26 per PA verify + AMD-2026-05-26-01 land — LG-3 supervised live SM 是所有策略 (4 textbook + C10；funding_arb retired) supervised live activation gate；funding_arb V2 Retired closed 不影響 LG-3 IMPL 需求」 | spec v2 §0.2 Non-Scope 確認 LG-3 不依賴策略；PA report §3.4 + memory.md log；AMD-2026-05-26-01 已 land = funding_arb deprecated → 衝突源消失 | ✅ **FULLY COVERED**（但 §15 #1 line 377 文字保留 strikethrough + reframe 可進一步刪除/壓縮） |

**結論**：3/3 drift FULLY COVERED；spec land 完整；TODO 文字尚需 cosmetic 收斂（patch §4 提供）。

---

## §2 Spec 內 V### 號最終決定

### 2.1 sql/migrations/ 實體驗證（2026-05-27）

```bash
ls /Users/ncyu/Projects/TradeBot/srv/sql/migrations/ | grep -E '^V(09[5-9]|1[0-2][0-9])'
# Output:
# V095 / V096 / V097 / V098 / V100 / V101 / V102 / V103 / V106 / V107 / V109 / V112
```

| V### | 實體狀態 | 占用 | LG-3 可用 |
|---|---|---|---|
| V099 | ❌ NOT in sql/migrations/ | spec-only reservation（`docs/execution_plan/specs/2026-05-22--v099-autonomy-level-config.md` 568 LOC）— autonomy_level_config Wave 5 prerequisite | ❌ 預留禁用 |
| V100 | ✅ land | `m4_hypothesis_base_table` | ❌ 已占 |
| V101 | ✅ land | `track_v3_attribution_column` | ❌ 已占 |
| V102 | ✅ land | `track_v3_indexes_not_null` | ❌ 已占 |
| V103 | ✅ land | `extend_m4_hypothesis_columns` | ❌ 已占 |
| **V104** | ❌ NOT in sql/migrations/（spec scaffold-only） | LG-3 supervised_live_audit（本 spec 預留） | ✅ **FREE & ASSIGNED** |
| V105 | ❌ NOT in sql/migrations/ | — | 🟡 free for future |
| V106 | ✅ land | `health_observations` | ❌ 已占 |
| V107 | ✅ land | `replay_divergence_log` | ❌ 已占 |
| V108 | ❌ NOT in sql/migrations/ | — | 🟡 free for future |
| V109 | ✅ land | `m8_anomaly_events_hypertable` | ❌ 已占 |
| V110 / V111 | ❌ NOT in sql/migrations/ | — | 🟡 free for future |
| V112 | ✅ land | `decision_lease_lal_tiers` | ❌ 已占 |

### 2.2 V104 最終 decision

**LG-3 audit migration 取號 = V104** （CONFIRMED）

- 檔名：`srv/sql/migrations/V104__supervised_live_audit.sql`
- 物理存在：尚未 land（spec scaffold-only）— MIT 走 4-step empirical dry-run + E1 IMPL 後才寫實體
- V104 空隙位於 V103（已 land）與 V106（已 land）之間 — sqlx forward-only 連續性 OK（V104 land 後 V105 仍 free 給 future spec，無 hole 風險，因為 V105 沒 land 也合法）
- spec v2 §4.1 / §4.2 / AC-T4-1~10 內所有 V094 字眼 → IMPL 階段 1:1 替換為 V104（per spec v2 amendment A1 + V104 scaffold §7.1）

**反向 sanity check**：V104 不會撞 V099 預留 + V100/V106/V107/V109/V112 已占 — V104 是 V104-V112 range 唯一未被預定的號（V105/V108/V110/V111 為 silent free，可挪用但 V104 已 PA 指定）。

---

## §3 §15 #1 FALSE dep 撤回語句

當前 line 377 已 strikethrough + REFRAMED；不需新增撤回行；保留現有 reframe 文字並可進一步收斂為單行（patch §4.3 提供）：

> **§15 #1 撤回語句（直接可貼）**：
> `LG-3 IMPL DISPATCH ↔ P0-FUNDING-ARB-DECISION-FORCE` 衝突已於 2026-05-26 reframed 為 FALSE dependency（LG-3 為所有策略 supervised live SM gate，與 funding_arb retired/active 無關）。真衝突為 V### 號占用（V099/V100 occupied → V104 assigned）+ v56 P0 Layer B 7d observation 視窗（~2026-05-29 啟動）。ref `P1-LG-3-AC-CORRECTION` (§6 line 157 ✅ CLOSED) + V104 spec `srv/docs/execution_plan/specs/2026-05-26--v104-lg3-supervised-live-audit-migration.md`。

---

## §4 TODO Patch 草稿（diff 形式給主會話照貼）

### 4.1 §1 行 46（P0-LG-3 row）— minor cosmetic 收斂

當前 line 46 已含完整 reframe 文字；可選 patch（壓縮 + 對應 sql/migrations/ empirical 加 1 句）：

```diff
- | **P0-LG-3** | ⚠️ PA AC correction + V104 scaffold ✅ DONE 2026-05-26 / **IMPL DISPATCH READY post-amendment** / 2 external gate pending | PA ✅ → MIT V104 dry-run → E1×7 IMPL | **AMENDED 2026-05-26**：spec v2 §4.1/§4.2/AC-T4-1~10 內所有 V094 字眼 IMPL 階段 1:1 替換為 V104（V099/V100 與 LG-3 無關 — V099 已被 autonomy_level_config 預留 + V100 已 land m4_hypothesis_base_table；§2.4A "fee_source tick-time consumer" 全 docs grep 0 hit 為 wording drift 移除）；新真實 dispatch precondition = (1) V104 audit migration spec scaffold ship ✅ (2) v56 P0 Layer B 7d observation gate ~2026-05-29 啟動 + 24h ⏳ (3) MIT 走 V104 spec §4 4-step Linux PG empirical dry-run 9/9 PASS ⏳ (4) race-aware Option B dispatch 確認；§15 #1 LG-3↔funding_arb FALSE dep 已 reframed | LG-3 Wave 2.4.A 最早 dispatch date ~2026-05-30 UTC；ref V104 spec `srv/docs/execution_plan/specs/2026-05-26--v104-lg3-supervised-live-audit-migration.md` (378 行) + spec v2 amendment `2026-05-11--lg_3_spec_v2_final.md` line 1771-1851 |
+ | **P0-LG-3** | ⚠️ PA AC correction + V104 scaffold ✅ DONE 2026-05-26 / **IMPL DISPATCH READY** / 2 external gate pending（per 2026-05-27 PA verify: 3/3 drift FULLY COVERED） | PA ✅ → MIT V104 dry-run → E1×N IMPL | **AMENDED 2026-05-26**：spec v2 §4.1/§4.2/AC-T4-1~10 V094 字眼 IMPL 階段 1:1 替換 V104（V099 autonomy_level_config 預留 + V100 m4_hypothesis_base_table 已 land；§2.4A "fee_source tick-time consumer" wording drift 移除 per QA 2026-05-21 by-design caveat）；2026-05-27 empirical `ls sql/migrations/` 確認 V104 FREE（V099/V100/V101/V102/V103/V106/V107/V109/V112 占；V104/V105/V108/V110/V111 未 land）；real dispatch precondition = (1) V104 spec scaffold ship ✅ (2) v56 P0 Layer B + 24h ⏳ ~2026-05-30 (3) MIT 4-step dry-run 9/9 PASS ⏳ (4) Option B race-aware dispatch；§15 #1 FALSE dep reframed | LG-3 Wave 2.4.A earliest ~2026-05-30 UTC；ref V104 spec `srv/docs/execution_plan/specs/2026-05-26--v104-lg3-supervised-live-audit-migration.md` + amendment `2026-05-11--lg_3_spec_v2_final.md` L1771-1851 + verify report `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-27--p0_lg3_spec_verify_and_todo_patch.md` |
```

### 4.2 §6 line 157（P1-LG-3-AC-CORRECTION row）— add 2026-05-27 verify hint

```diff
- | `P1-LG-3-AC-CORRECTION` | – | ✅ **CLOSED 2026-05-26** — PA delivered (1) spec v2 amendment 83 行 at line 1771-1851 (V094→V104 1:1 replace + V099/V100 移除 + §2.4A wording drift 移除) (2) V104 migration spec scaffold 378 行 `srv/docs/execution_plan/specs/2026-05-26--v104-lg3-supervised-live-audit-migration.md` (10 章 + 21 col + 4 CHECK + hypertable + Guard A/B/C + 4-step PG dry-run + V094 replacement rule) (3) TODO §1 行 48 reframe text applied；2 external gate pending = v56 P0 Layer B + 24h (~2026-05-30) + MIT V104 4-step empirical dry-run 9/9 PASS；ref `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-26--p0_lg3_ac_correction_and_v104_scaffold.md` |
+ | `P1-LG-3-AC-CORRECTION` | – | ✅ **CLOSED 2026-05-26 / VERIFIED 2026-05-27** — PA delivered (1) spec v2 amendment 83 行 L1771-1851 (V094→V104 1:1 + V099/V100 移除 + §2.4A wording drift 移除) (2) V104 scaffold 378 行 `srv/docs/execution_plan/specs/2026-05-26--v104-lg3-supervised-live-audit-migration.md` (10 章 + 21 col + 4 CHECK + hypertable + Guard A/B/C + 4-step PG dry-run + V094→V104 replacement rule) (3) TODO §1 row reframe applied；**2026-05-27 PA verify pass**：3/3 drift FULLY COVERED + sql/migrations/ empirical V104 FREE；2 external gate remain = v56 P0 Layer B + 24h (~2026-05-30) + MIT V104 4-step empirical dry-run 9/9 PASS；ref close report `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-26--p0_lg3_ac_correction_and_v104_scaffold.md` + verify report `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-27--p0_lg3_spec_verify_and_todo_patch.md` |
```

### 4.3 §15 line 377（#1 row）— 收斂 strikethrough block 為單行清晰判決

```diff
- | 1 | ~~LG-3 IMPL DISPATCH ↔ P0-FUNDING-ARB-DECISION-FORCE~~ | ❌ **REFRAMED 2026-05-26 per PA verify + AMD-2026-05-26-01 land** — LG-3 supervised live SM 是所有策略 (**4 textbook + C10**；funding_arb retired per AMD-2026-05-26-01) supervised live activation gate；funding_arb V2 Retired closed 不影響 LG-3 IMPL 需求；真衝突 = **V### 號占用 conflict**（V099/V100 已被 autonomy_level_config + m4_hypothesis_base_table 占）+ **v56 P0 Layer B 7d observation 視窗 ~2026-05-29**；ref `P1-LG-3-AC-CORRECTION` |
+ | 1 | ~~LG-3 IMPL DISPATCH ↔ P0-FUNDING-ARB-DECISION-FORCE~~ | ❌ **WITHDRAWN 2026-05-26 / VERIFIED 2026-05-27** — FALSE dep（LG-3 supervised live SM 為所有策略 supervised live activation gate，與 funding_arb retired/active 解耦 per AMD-2026-05-26-01）。真衝突 = V### 號占用（V099 autonomy_level_config 預留 + V100 m4_hypothesis_base 已 land → LG-3 取 V104 FREE per 2026-05-27 empirical）+ v56 P0 Layer B + 24h gate ~2026-05-30。ref `P1-LG-3-AC-CORRECTION` (§6 ✅ CLOSED) + V104 spec scaffold |
```

---

## §5 IMPL Dispatch Readiness（E1 × N 並行任務分解 + 估時）

per spec v2 §8 + dispatch refresh 2026-05-19 §3.3 Option B（race-aware）— **本任務不重新發明分解**，只 verify 既有計劃可立即執行。

### 5.1 Wave 2.4 任務分解（per dispatch refresh §3.3 Option B）

| Wave | Task | 並發 | 依賴 | E1 數 | 估時 |
|---|---|---|---|---|---|
| **Wave 2.4.A** | **T1（Rust SM core）** + **T4（V104 audit writer + migration + healthcheck + grep guard）** | 2 並行 | 無（檔案零 overlap） | 2 E1 + 1 MIT（T4 PG dry-run） | T1 ~2d IMPL + T4 ~1.5d IMPL + 1d review = ~4d wall |
| Wave 2.4.B | T2（Python SM mirror） | 單 | T1 land | 1 E1 | ~2d wall |
| Wave 2.4.C | T3（Approval RPC route） | 單 | T2 land | 1 E1 | ~2d wall |
| Wave 2.4.D | T5（Kill + session_override + lease） | 單 | T1+T2+T3 land | 1 E1 | ~2.5d wall |
| Wave 2.4.E | T7（GUI surface） | 單 | T5 land | 1 E1（高風險 A3+E2 並行強制 per 2026-05-09 lesson） | ~2.5d wall |
| Wave 2.4.F | T6（E2E acceptance） | 單 | T1..T5+T7 land | 1 E1 + QA | ~4d wall |

**Total**：~12-13d wallclock（per 2026-05-19 dispatch refresh §3.4 estimate）；earliest start ~2026-05-30；earliest closure ~2026-06-10~12。

### 5.2 Critical overlap warning（per dispatch refresh §3.1）

- **`live_session_routes.py`** 被 T3 (+250) / T5 (+100) / T7 (+50) 同時 EXTEND → 嚴格 sequential 順序 T3 → T5 → T7；每 task 必 `git pull origin main` 確認 upstream 含前 task 改動才 IMPL
- **`intent_processor/mod.rs`** 被 T5 (+120) EXTEND → T1 land 前 T5 不可開動

### 5.3 Wave 2.4.A E1×2 + MIT dispatch packet（PM 直接照用）

**E1-T1（Rust SM core）prompt 必含**：
- spec v2 §1 + §2 + §3 + §5 + §6.3 (kill 順序) + §7
- 文件清單：`supervised_live_sm/mod.rs` / `state.rs` / `transition.rs` / `reconciler.rs` / `tests.rs`（純 NEW，零 EXTEND）
- LOC budget: ~1700
- AC: spec v2 §8 AC-T1-1~9
- Worktree: `git worktree add ../wt-lg3-t1 -b feature/lg3-t1`
- Race rule: 不碰 main tree；不看 T4 worktree

**E1-T4（V104 audit migration + writer）prompt 必含**：
- spec v2 §2.2A inverse map + §4 全 + V104 spec scaffold 全
- 文件清單：`V104__supervised_live_audit.sql` / `supervised_live_audit_writer.rs` / `checks_supervised_live_audit.py` / `e3_grep_non_training_surface.sh`（純 NEW，零 EXTEND）
- LOC budget: ~980
- AC: spec v2 §8 AC-T4-1~10（V094 → V104 1:1 替換 + grep gate）
- **V### replacement rule**: 所有 V094 字眼 → V104；完工前 `grep -n 'V094\|V099' <touched>` 0 match
- MIT 先走 V104 spec §4 4-step Linux PG empirical dry-run 9/9 PASS → 出 `MIT/workspace/reports/<DATE>--v104_lg3_supervised_live_audit_pg_dryrun.md` → E1 才寫 SQL + writer
- Worktree: `git worktree add ../wt-lg3-t4 -b feature/lg3-t4`

### 5.4 Dispatch gate（2 external）

| Gate | 條件 | ETA |
|---|---|---|
| External Gate 1 | v56 P0 Layer B deploy + 24h watch（per `P0-ENGINE-HALTSESSION-STUCK-FIX` cycle status） | ~2026-05-30 UTC |
| External Gate 2 | MIT V104 spec scaffold §4 4-step Linux PG empirical dry-run 9/9 PASS sign-off | ~2-4h MIT work，在 Gate 1 滿足前可並行進行（dry-run DB 可立刻測） |

**No additional spec work blocking** — IMPL dispatch readiness 100% ready post 2 external gate。

---

## §6 風險識別 + 緩解

| 風險 | 等級 | 緩解 |
|---|---|---|
| MIT dry-run 9/9 出 FAIL | 中 | V104 spec scaffold §9 已列；FAIL → PA amendment patch；不阻 spec scaffold 本體 |
| v56 P0 Layer B 7d observation 期內出 alarm | 中 | dispatch refresh §4.2 candidate (c) fallback；推遲 ~2026-06-03~06 |
| LG-3 Wave 2.4.A T1+T4 並行 race | 低 | dispatch refresh §3.1 verified 文件零 overlap；worktree 隔離 |
| TODO patch 與 multi-session 撞 | 低 | 主會話用 `git commit --only TODO.md` per CLAUDE.md `Git And Sync` |

---

## §7 16 root principles compliance

A 級 16/16；§1 / §3 / §4 / §6 / §8 / §11 directly relevant（per PA report 2026-05-26 §5 內容繼承）。

無硬邊界觸碰；無 P0/P1/P2 風控降級；live_reserved / max_retries / system_mode / live_execution_allowed / OPENCLAW_ALLOW_MAINNET 0 變動。

---

## §8 不擴 scope 之保證

本 verify + patch report **嚴格限定**：
- 只 verify 既有 spec 覆蓋率 + 出 TODO patch 草稿
- 不重寫 spec v2（避免破壞 3-review APPROVE baseline）
- 不修改 V099 autonomy_level_config 預留範圍
- 不動 main tree
- 不 dispatch IMPL（PM 在 2 external gate 滿足後派）
- 不發 IPC / 不 restart engine

---

PA P0-LG-3 SPEC VERIFY + TODO PATCH DRAFT DONE: report path: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-27--p0_lg3_spec_verify_and_todo_patch.md`

Next:
- Main session apply §4 TODO patch（§1 line 46 + §6 line 157 + §15 line 377）— 3 row edit；用 `git commit --only TODO.md`
- v56 P0 Layer B + 24h gate（~2026-05-30）→ PM 派 Wave 2.4.A E1-T1 + E1-T4 + MIT 三並行 dispatch
- MIT 在 Gate 1 滿足前可預先進行 V104 4-step dry-run（dry-run DB 不撞 production）
