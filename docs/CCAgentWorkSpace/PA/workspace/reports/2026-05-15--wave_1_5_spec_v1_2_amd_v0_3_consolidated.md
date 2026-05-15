# PA · Wave 1.5 spec v1.2 + AMD v0.3 consolidated patch

**Date**：2026-05-15
**Author**：PA (Wave 1.5 patch chain)
**Scope**：純增量 patch — 把 Wave 1 Track A3 + Track E3 substantive new finding consolidated 進 spec v1.2 + AMD v0.3，並開新 P1 + P2 ticket
**Triggered by**：Operator dispatch / EDGE-P2-3 Phase 1b 4-agent review post-Wave 1 increment（避免直接派 4-agent re-review v0.2 後又 push back，浪費 capacity）
**Source verdicts read**：
- A3 verify report：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--f_fa_2_portfolio_var_exposure_sot_verify.md`
- E3 baseline report：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--maker_fill_rate_empirical_baseline.md`
- A4 guard tests report：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--f_fa_3_w_c_caveat_2_guard_tests_design.md`
- AMD v0.2：`srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md`（land at `53245ed0`，patched in this chain）
- Spec v1.1：`srv/docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md`（land at `a5a5d74a`，patched in this chain）
- TODO §11.5：`srv/TODO.md`

**Hard constraints honored**：純增量 patch · 不重做 17 must-fix + 14 should-fix · 不修 Rust / Python 業務代碼 · 不動 V094 SQL 實檔（Wave 2）· 不修字典手冊（Wave 3 BB1）· 每寫 1 檔即 commit + push（不批次）。

---

## §1 A3 finding 收口 mapping

### A3 substantive finding（commit `96995b61`）

| # | A3 finding | Spec v1.2 收口 | AMD v0.3 收口 | TODO 收口 |
|---|---|---|---|---|
| 1 | NO `portfolio_var` 模塊；real SoT = `compute_correlated_exposure_pct` + `compute_exposure_pct`（`intent_processor/mod.rs:761-805`） | §15 NEW P1 ticket scope（spec §15 row）| §7 #16 改寫 + §11.1 NEW Wave 1 引用 + §12 v0.3 row | §11 P1 NEW row `P1-PORTFOLIO-RESTING-EXPOSURE-1` |
| 2 | SoT = `PaperPosition.qty (filled only)`，完全不讀 `paper_state.resting_orders` | 同上 | 同上 | 同上 |
| 3 | Close intent `is_reducing → return PositionCheck::allow()`（`risk_checks.rs:137`），close 自身不觸 portfolio gate | §17 v1.2 row + §15 ticket scope | §7 #16 explicit「close path is_reducing 不觸 portfolio gate」 | §11 P1 row 描述 |
| 4 | FA framing 方向反了：close pending 對「後續 NEW open intent」是 OVER-estimate，real under-estimate scenario 是 entry pending | §17 v1.2 row | §7 #16「原 v0.2 framing 由 A3 verify 證實方向反了」 | §11.5 status block 引用 A3 |
| 5 | `risk_config.correlation.max_pairwise_r` 是 dead config（schema 存在 + validate test，但 intent_processor 0 callers）| 不修 spec / AMD（A3 §3 finding，scope 留 P1 ticket 處理）| 不修 | 不修（建議併入 P1 ticket scope） |
| 6 | paper / exchange path consistency = YES（兩 caller `router.rs:438-450` + `router.rs:904-916` 共用同函數）| §17 v1.2 row 隱含（不引入新 risk vector）| §7 #16「不引入新 portfolio risk vector」 | n/a |

### A3 推薦 option A 處置（PM 預批）

- ✅ §二 #16 CONDITIONAL → MAINTAIN（spec + AMD §7 同步）
- ✅ 開新 P1 ticket `P1-PORTFOLIO-RESTING-EXPOSURE-1`（est. 3 person-day, 250 LOC）平行 close-maker-first IMPL
- ✅ close-maker-first IMPL 不阻 portfolio fix；portfolio fix 不阻 close-maker-first（spec §15 + AMD §8 IMPL Prereq 5 partial-resolved）

### A3 fix scope summary（per ticket scope）

詳見 A3 verify report §8。摘要：

```
影響檔案 5 個 / ~250 LOC（含 tests + healthcheck）
- intent_processor/mod.rs:761-805 — 修 compute_exposure_pct + compute_correlated_exposure_pct
- intent_processor/mod.rs — 新 helper compute_effective_long_short_notional()
- intent_processor/tests.rs — 4 新 test
- paper_state/accessor.rs — 可能新 resting_orders_iter()
- helper_scripts/db/passive_wait_healthcheck.py — 新 [58] portfolio_resting_exposure_lineage

副作用 LOW（fn 是 private + 不觸 API schema + 不觸 IPC）
```

---

## §2 E3 finding 收口 mapping

### E3 substantive finding（commit `b98706d5`）

| # | E3 finding | Spec v1.2 收口 | AMD v0.3 收口 | TODO 收口 |
|---|---|---|---|---|
| 1 | fill-conditional ~94% maker rate（spec §1.2 假設條件性成立）| §1.2 引用 + 三層解讀 | §1 footnote | n/a |
| 2 | spec §1.2「4.5 bps net per close」**overstated** — 實際 0.5-3.3 bps per close attempt（最樂觀 3.31 / 中性 0.95 / 悲觀 0.66）| §1.2 改 0.5-2.0 bps + 全年估 $50-$200 + §17 v1.2 row | §1 footnote 「fee saving revised 4.5 → 0.5-2.0 bps」+ 全年估 $50-$200 + §12 v0.3 row | §11.5 status 引用 E3 |
| 3 | conservative `0.5-2.0 bps net` + 14d 30%+ close-maker fill rate gate | §1.2 改 0.5-2.0 + §10.1 14d Phase 2a + §11.7 NEW AC-19 14d ≥ 30% | §3 Phase 2a 14d + 啟動條件加 AC-18+AC-19 + §12 v0.3 row | §11.5 IMPL kickoff 引用 14d |
| 4 | `orders.intent_id` 100% NULL in 7d window — writer 漏接（P2 finding）| §1.2 explicit + §15 NEW P2 ticket row | §1 footnote 不引（spec 引）| §12 P2 NEW row `P2-ORDERS-INTENT-ID-WRITER-GAP-1` |
| 5 | `orders.status` 100% Working — fire-and-forget；終態須從 `order_state_changes.to_status` 拿 | §1.2 explicit | 不修 | n/a |
| 6 | **無 fallback to taker 機制** — 70% PostOnly timeout 後 entry 直接放棄；意味當前 maker-first 是「省錢但少 fill」trade-off | §1.2 explicit + §5.5 NEW Race E mandatory fallback to taker invariant + §11.7 NEW AC-18 ≥ 95% + §12.1 NEW HIGH risk row + §17 v1.2 row | §3 Phase 2b 啟動條件加 AC-18 + §12 v0.3 row | §11.5 status 引用 E3 |

### E3 對 close path 的 prediction 收口

| Prediction | Spec v1.2 收口 | AMD v0.3 收口 |
|---|---|---|
| close 結構性比 entry 更難 maker fill（trend-side liquidity 差 + 45s timeout 對 exit alpha 致命）| §10.1 14d Phase 2a observation period + AC-19 ≥ 30% | §3 Phase 2a 14d + 啟動條件加 AC-19 |
| 25-40% conservative discount on savings | §1.2 0.5-2.0 bps net 已含 conservative discount + §1.2 explicit「close vs entry behavior 結構性差異」| §1 footnote 引用「per Wave 1 Track E3 empirical baseline」 |
| 必 fallback to taker 機制（不能像 entry 那樣 70% 直接放棄）| §5.5 NEW Race E mandatory fallback invariant + 3 unit test + healthcheck [62] sub-check + AC-18 | §3 Phase 2b 啟動條件 AC-18 |
| 縮短 timeout 到 5-15s | spec v1.1 §4.2 已對 `phys_lock_gate4_giveback` 改為 15s（QC-MF-2）；本 patch 不再縮其他策略 timeout（保 30s 對應信號性質，per spec §4.2 + AMD §6 表）| 不修（v0.2 已收口）|
| 14d pilot observation period | §10.1 14d Phase 2a + §11.7 AC-19 ≥ 30% | §3 Phase 2a 14d |

---

## §3 spec v1.2 + AMD v0.3 diff summary

### Spec v1.1 → v1.2 改動清單

| § | 改動 | LOC delta |
|---|---|---|
| Header | Author + Status 加 v1.2 + Wave 1.5 patch 描述 | +2 |
| §1.2 | fee saving 3.5/+0.65 bps → 0.5-2.0 bps net per close attempt + 全年估 $160-$400 → $50-$200 + 引用 E3 report path + E3 三個意外發現 + per submitted vs fill-conditional 區分 | +18 |
| §5.5 | NEW Race E：Fallback to taker mandatory（規則 1-5 + IMPL gate + healthcheck sub-check + audit row enum invariant） | +29 |
| §10.1 | Phase 2a 7d → 14d (7d primary + 7d extended observation) + 拉長理由 + AC-19 引用 | +8 |
| §11.7 | NEW AC-18 fallback ≥ 95% + AC-19 14d fill ≥ 30% | +5 |
| §12.1 | NEW HIGH row「Close maker fallback 直接放棄 inherit entry-side gap」 | +1 |
| §15 | NEW P1-PORTFOLIO-RESTING-EXPOSURE-1 + P2-ORDERS-INTENT-ID-WRITER-GAP-1 兩 row | +2 |
| §17 | v1.2 row + Sign-off Status updated + 下一步 updated | +5 |
| **Total** | | **+62 / -7** |

### AMD v0.2 → v0.3 改動清單

| § | 改動 | LOC delta |
|---|---|---|
| Header | Author + Status 加 v0.3 + Wave 1.5 patch 描述 | +2 |
| §1 Executive Decision | 加 footnote「per Wave 1 Track E3 empirical baseline，fee saving revised 4.5 → 0.5-2.0 bps，全年估 $50-$200」| +2 |
| §3 Rollout Posture | Phase 2a 7d → 14d + Phase 2b 啟動條件加 AC-18 + AC-19 | +2 |
| §7 #16 | CONDITIONAL → MAINTAIN per A3 verify finding（close path is_reducing 不觸 portfolio gate；新 P1 ticket option A）+ v0.2 framing 修正 | +3（複雜文字 expansion）|
| §8 IMPL Prereq 5 | partial-resolved（F-FA-2 ✅ + F-FA-3 ✅ + F-FA-1 留 Wave 2）| +3 |
| §11.1 | NEW Wave 1 Source Audits 5 commit 引用（A1/A3/A4/E1/E3）| +9 |
| §12 | v0.3 row + 下一步 updated | +2 |
| **Total** | | **+25 / -11** |

### TODO 改動清單

| § | 改動 | LOC delta |
|---|---|---|
| §11 P1 backlog | NEW `P1-PORTFOLIO-RESTING-EXPOSURE-1` row | +1 |
| §11.5 dispatch | Status block (Wave 1 ✅ summary) + dispatch table 加狀態欄 + dispatch order Wave 1+1.5+2+3 + Phase 2a 14d explicit | +30 / -19 |
| §12 P2 backlog | NEW `P2-ORDERS-INTENT-ID-WRITER-GAP-1` row | +1 |
| **Total** | | **+30 / -19** |

---

## §4 Self-verification checklist

### A. 嚴禁事項核對

| 嚴禁事項 | 核對 |
|---|---|
| 不重做 17 must-fix + 14 should-fix（v1.1/v0.2 已收口，純增量）| ✅ 純增量；v1.1 §11 AC-1..AC-17 全保留，v1.2 加 AC-18+AC-19；v0.2 §7 11 row 全保留，v0.3 改 #16 一行 |
| 不修 Rust / Python 業務代碼 | ✅ 0 改動 |
| 不動 V094 SQL 實檔（Wave 2）| ✅ 0 改動 |
| 不修字典手冊（Wave 3 BB1）| ✅ 0 改動 |

### B. 來源文件對齊核對

| 來源文件 | 引用點 | 核對 |
|---|---|---|
| A3 verify report `2026-05-15--f_fa_2_portfolio_var_exposure_sot_verify.md` | spec §15 + AMD §7 #16 + AMD §8 + AMD §11.1 + TODO §11 P1 + TODO §11.5 | ✅ 6 處引用 |
| E3 baseline report `2026-05-15--maker_fill_rate_empirical_baseline.md` | spec §1.2 + spec §5.5 + spec §10.1 + spec §11.7 + spec §12.1 + spec §15 + AMD §1 footnote + AMD §3 + AMD §11.1 + TODO §12 P2 + TODO §11.5 | ✅ 11 處引用 |
| A4 guard tests report `2026-05-15--f_fa_3_w_c_caveat_2_guard_tests_design.md` | AMD §8 IMPL Prereq 5 + AMD §11.1 | ✅ 2 處引用 |
| AMD v0.2 commit `53245ed0` | AMD v0.3 變更歷史 + §11.1 | ✅ 2 處引用 |
| Spec v1.1 commit `a5a5d74a` | spec v1.2 變更歷史 | ✅ 1 處引用 |
| Wave 1 commits `2e7a1b2f / 96995b61 / b98706d5 / a5a7107c / 9df44183` | AMD §11.1 + TODO §11.5 | ✅ 5 commit 全引用 |

### C. 16 條根原則合規（Wave 1.5 patch 無新觸碰）

| # | 原則 | Wave 1.5 影響 |
|---|---|---|
| 4 | 策略不繞風控 | §5.5 強化此原則（mandatory fallback to taker invariant；engine 不應讓 close intent silent dropping）|
| 5 | 生存 > 利潤 | §5.5 explicit「close = 必須減 exposure；放棄 = 持有不利倉位 = 違 §二 #5」 |
| 6 | 失敗默認收縮 | §5.5「engine cancel_token / authorization 失效」走 market；fail-closed 強化 |
| 8 | 交易可解釋 | §5.5 audit row enum invariant + healthcheck [62] sub-check |
| 9 | 災難保護 | §5.5「engine cancel_token / authorization 失效 → cancel pending + 後續 close 走 market」明文 |
| 11 | Agent 最大自主權 | 不影響 P0/P1 硬邊界 |
| 16 | 組合級風險意識 | §7 #16 MAINTAIN + 新 P1 ticket 平行解 entry-side resting maker gap |

### D. 硬邊界檢查（CLAUDE.md §四）

- ❌ 不觸 `live_execution_allowed` / `max_retries` / `OPENCLAW_ALLOW_MAINNET` / `live_reserved` / `authorization.json`
- ❌ 不觸 lease 授權邏輯
- ❌ 不觸 H0 Gate 主路徑
- ❌ 不觸 9 條安全不變量

**全 GREEN**。

### E. Multi-session race 防範核對

| 規範 | 核對 |
|---|---|
| 每寫 1 檔即 commit + push（不批次）| ✅ 4 commit 分離（spec / AMD / TODO / 本 report）|
| `git commit --only <file>` | ✅ 每個 commit 用 `--only` 隔絕 |
| 不 `git add -A` | ✅ 0 使用 |
| Commit message 加 `[skip ci]` | ✅ 4 commit 全加 |
| Diff verify 無吸收非 Wave 1.5 改動 | ✅ TODO diff 確認純 Wave 1.5（Bash 命令確認 30 insertions / 19 deletions 全屬本 task）|

---

## §5 Commit hash + push 確認

| Commit | 描述 | Status |
|---|---|---|
| `3059129f` | docs: edge-p2-3 phase 1b spec v1.2 — wave 1.5 a3+e3 consolidated patch [skip ci] | ✅ pushed origin/main |
| `9f16c05d` | docs: amd-2026-05-15-02 v0.3 — wave 1.5 a3+e3+a4+e1 consolidated patch [skip ci] | ✅ pushed origin/main |
| `280ad959` | docs(todo): wave 1.5 §11.5 status + 2 new ticket [skip ci] | ✅ pushed origin/main |
| 本 report 待 commit | docs(pa): wave 1.5 spec v1.2 + amd v0.3 consolidated [skip ci] | 🔄 進行中 |

**Linux ssh trade-core 同步驗證**：本 task 為純 docs patch（無 runtime 改動），不需 ssh trade-core 觸發 runtime 動作；origin/main push 後 Linux runtime 可隨時 `git pull --ff-only` 同步。

---

## §6 Next step：建議 PM 派遣

### Wave 2（並行派）

1. **A2 V094 migration spec**（PA）：spec v1.2 §4.4 schema 段已定（hot column 2 + JSON extension 3 hybrid + writer gap explicit per A4 finding）；可直接 finalize V094 SQL spec；Linux PG dry-run × 2 round；mirror V083 NOT VALID precedent；對應 IMPL Prereq 5 剩餘 F-FA-1 解
2. **E1 reject_cooldown entry/close 拆分**（E1）：BB-MF-3 P0；pre-Phase 2a Demo 必 land；對應 IMPL Prereq 6 解

### Wave 3（並行派，A2 + E1 finalize 後或並行）

1. **4-agent short re-review on AMD v0.3 + spec v1.2**（QC + FA + BB + MIT 各 30min 並行）：核驗 Wave 1.5 patch 收口完整性（§5.5 fallback invariant + AC-18+AC-19 + #16 MAINTAIN + 14d Phase 2a + V094 hybrid + writer gap + 2 new ticket open）；無新 finding → AMD v0.4 sign-off；如新 finding → Wave 1.5b
2. **BB1 字典手冊 6 處更新**（BB）

### Wave 4+

- IMPL kickoff（3-gate 解後）：PA finalize IMPL plan → E1 並行 5 worktree → E2 → E4 → QA → PM
- 平行：`P1-PORTFOLIO-RESTING-EXPOSURE-1`（PA → E1，3 person-day，獨立 worktree，250 LOC，不阻 close-maker-first IMPL）

### N+2 backlog

- `P2-ORDERS-INTENT-ID-WRITER-GAP-1`（E1，1 person-day）

---

**PA DESIGN DONE**：report path：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--wave_1_5_spec_v1_2_amd_v0_3_consolidated.md`
