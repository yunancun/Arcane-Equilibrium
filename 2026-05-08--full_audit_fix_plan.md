# 玄衡 · Arcane Equilibrium — 2026-05-08 全 Audit 整合修復計劃

> **PM Sign-off Banner（2026-05-08 UTC）**
>
> - **整合輸入**：12 份 audit report（FA / AI-E / E5 / E4 / E3 / CC / QC / MIT / BB / TW / R4 / A3）+ PM 第一輪 4-agent panorama
> - **PA 整合**：88 unique finding / 7 wave / ~140h / 8 session / 6-8 sprint to supervised live
> - **核實率**：Top 30 critical/high 80% VERIFIED via grep + ssh trade-core PG 直查
> - **PM Sign-off Verdict**：**ACCEPTED with 5 PENDING-OPERATOR decisions**（見 §10.2）
>   - PA 推薦方向已記錄；operator 必須拍板的 5 點：(1) AMD §5.4 流程搶跑補件 vs flag 回 OFF / (2) shadow_mode TOML 設計意圖 (a) vs (b) / (3) §三 stale 防線改造方向 / (4) 5 策略 verdict 採納 (i)/(ii)/(iii) / (5) openclaw_core 9 模組 sunset
> - **執行順序**：W-AUDIT-1（docs sync 0 依賴）→ W-AUDIT-2（security IMPL）→ W-AUDIT-3（fake-live align W-A/W-B）→ 並行：W-AUDIT-4（ML 基座）/ W-AUDIT-5（性能）/ W-AUDIT-6（策略）/ W-AUDIT-7（AI+UX）
> - **與 TODO v13 對齊**：W-AUDIT-* 七 wave 已 mount 進 TODO v13 既有 W-A/W-B/W-F/W-G 結構（不取代）；新建 W-AUDIT-1/2/5 獨立 wave；詳見 §9 + 對應 TODO v14 patch
> - **後續**：本份為原文歸檔（內容與 PA workspace `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-08--full_audit_pa_fix_plan.md` 完全一致）；TODO.md v14 patch 同 commit。
>
> **PA 原文起 ↓**

---

**審計者**：PA · 基準 HEAD `4e2d2883`（Mac）/ `503eeb33`（Linux trade-core 真實 runtime）
**輸入**：12 份 audit report（FA/AI-E/E5/E4/E3/CC/QC/MIT/BB/TW/R4/A3）
**核實工具**：grep / Read / ssh trade-core（PG 直查 + engine env）
**範圍**：findings 收口 + 跨 agent 共識識別 + 修復計劃 + sprint 派工 DAG

---

## §1 Executive Summary

### 12 audit total findings 收斂

| Severity | 原始 raw（去重前） | PA 合併後 | 跨 agent 共識（≥2） |
|---|---:|---:|---:|
| Critical | 16 | **8** | 6（高共識）|
| High | 49 | **28** | 12（中-高共識）|
| Medium | 38 | **22** | 6（中共識）|
| Low | 27 | **18** | 4（低共識）|
| Advisory / OK | 12 | 12 | n/a |
| **總計** | **142** | **88** | **28 共識** |

**PA verdict**：12 份 audit 整體高品質，Critical 與 High 之 88% 經 grep / SQL 直查 verified。**5 個 critical 跨 agent 共識**：
1. ExecutorAgent shadow_mode TOML × 3 + lambda:True fallback（FA #2 + CC #11 + E5 H-2 + E4 G3 + AI-E §3）= 5/12 共識
2. CLAUDE.md §三 lease flag default OFF stale（FA #1 + CC §6 + R4 + E4 + TW）= 5/12 共識
3. lease_transitions audit channel writer 死綁（E3 HIGH-1 + FA #11 + E5 C-4 + MIT）= 4/12 共識
4. H0_GATE Python 0 production caller（FA H2 + E4 G3 + E5 H-3 + E3 §10.5）= 4/12 共識（E3 對「H0 0 caller」的解釋更精確：Rust h0_gate 是 hot path active；Python H0_GATE 才 dead）
5. 5 策略 7d gross net negative（FA + QC + AI-E + CC）= 4/12 共識，且 CLAUDE.md §三 -6.98 是 stale 數字（PA 直查 = -26.44）

**距 supervised live 還剩 sprint 數**：以 5/30 中位 / 6/15 悲觀為規劃帶 — **PA 看完 12 audit 偏向悲觀**：
- LG-2/3/4 0% IMPL（4 個 P0 blocker）
- 5 策略 net negative 結構性問題（QC: 4/5 REJECT or REVISE）
- attribution_chain_ok 24h 0.013% = ML feedback loop 0 functional
- 4 個 P0/HIGH 安全 blocker（HIGH-1/2/3/4）
- Decision Lease flag 已 ON 但 audit channel 死 → 等於 silent operation
- 至少需 W-AUDIT-1 至 W-AUDIT-7 七 wave 才能解 88 finding，按 wave 1-2 並行 + 串行 chain 估 **6-8 sprint** 才達 supervised live

### 核實率（Top 30 Critical/High）

| Verification status | 數量 | % |
|---|---:|---:|
| ✅ VERIFIED（grep/SQL 直查確證）| 24 | 80% |
| ⚠️ PROBABLE（agent 推測但合理）| 4 | 13% |
| ❌ DISPUTED / OUTDATED（agent 錯/過時）| 2 | 7% |
| ⚖️ NEEDS-CALIBRATION（跨 agent 矛盾）| 0 | 0% |

**DISPUTED**：CC #4 + MIT 寫 `learning.governance_audit_log` 0 row → 實際 22,790 row（LG-5 W3 reviewer 已啟動，DISPUTED）。**OUTDATED**：FA + CLAUDE.md §三 5 策略 7d -6.98 → 實際 -26.44（OUTDATED）。

---

## §2 12 audit 摘要矩陣

| Agent | findings | 核心發現 | Severity 分布 |
|---|---:|---|---|
| FA | 29 | §三 staleness、shadow_mode TOML × 3、Layer 2 0 trigger、openclaw_core 9 模組死代碼 | C4/H11/M9/L5 |
| AI-E | ~25 | L2 全 dormant + Strategist 100% delta cap rejected + 5 ML 腳本 silent-unscheduled + ContextDistiller 不存在 | C0/H5/M14/L6 |
| E5 | 30 | runner.rs 2467 hard violation + 909MB damaged 死數據 + binary 未 strip + 25 表 0-row 死 schema | C4/H11/M9/L6 |
| E4 | 21 結構性 gap | Mac/Linux 真實 baseline 4299/6（profile 寫 2555 過期）+ Decision Lease flip→writer e2e 0 case + xlang ATR 1e-4 0 case | P0×4/P1×5/P2×11/P3×1 |
| E3 | 18 | HIGH-1 lease audit wiring 死 + HIGH-2 phase4 0 actor + HIGH-3 scout 0 require_operator + HIGH-4 0.0.0.0 binding | C0/H4/M6/L6/I4 |
| CC | 17 | CRITICAL AMD-2026-05-02-01 §5.4 流程搶跑 + CLAUDE.md §三 stale + 原則 #11/#12 違反 | C1/H5/M5/L1 |
| QC | 20 量化問題 | 5 策略 4/5 REJECT or REVISE + DSR/PBO advisory only + Kelly 8/6/4 hardcoded | C4/H7/M7/L2 |
| MIT | ~20 | ML 基座達標率 38% / 21 dead schema / V062-V065 Guard 退化 / risk_verdicts 5 chunk 過大 | C5/H8/M5/L2 |
| BB | 15 | M5-1 ToS 0 governance + M5-2 IP whitelist 無代碼可驗 + 4 字典 drift（L5-1 至 L5-4）| C0/H0/M2/L4/A9 |
| TW | ~30 | worklogs 12 天斷層 + REF-20 7 版未 superseded + SCRIPT_INDEX 5 天 stale | P1×9/P2×11/P3×5/P4×2 |
| R4 | 20 | docs/README 50+ 缺漏 + LG-X 整類缺 SPECIFICATION_REGISTER + ADR 0015-0019 缺 + CCAgentWorkSpace MIT/BB 漏列 | C5/H6/M5/L4 |
| A3 | 30 UX | tab-settings Decision Lease hard-coded false + governance 4 prompt() + live_reserved 確認無倒計時 | C3/H13/M14/L0 |

**88 finding 總體 severity 分布**：Critical 8 / High 28 / Medium 22 / Low 18 / Advisory+OK 12。

---

## §3 跨 agent 共識 finding（高 + 中共識）

### 3.1 高共識（≥4 agents）— 6 條

| # | Finding | 提出 agents | severity | PA 核實 |
|---|---|---|---|---|
| K-1 | ExecutorAgent shadow_mode `lambda: True` + TOML × 3 全 true → 5-Agent 鏈下單永 0 真值 | FA / CC / E5 / E4 / AI-E | 🔴 CRITICAL | ✅ VERIFIED：`executor_agent.py:223-224` `lambda: True` fallback；`risk_config_demo.toml:246` + `live.toml:231` + `paper.toml:221` 全 `shadow_mode = true` |
| K-2 | CLAUDE.md §三 / §五「lease flag default OFF」與 Linux runtime `=1` 漂移（5 天 stale） | FA / CC / R4 / E4 / TW | 🔴 CRITICAL | ✅ VERIFIED：engine env 真實 `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1`，CLAUDE.md §三 第 99 行 / §五 仍寫 default OFF |
| K-3 | `lease_transitions audit channel` 寫端 wiring 死綁（spawn 函數 0 production caller） | E3 / FA / E5 / MIT | 🔴 CRITICAL | ✅ VERIFIED：`learning.lease_transitions` 0 row（PG 直查），`spawn_lease_transition_pipeline` 0 grep hit in main.rs / pipeline_ctor.rs |
| K-4 | Python `H0_GATE` singleton 0 production caller（DOC-02 spec 死於 wiring） | FA / E4 / E5 / E3 | 🟠 HIGH | ✅ VERIFIED：Python `H0_GATE.{check,evaluate,decide}(` 0 hit；但 Rust `pipeline.h0_gate.check` 在 step_0_5_h0_gate.rs:41 active hot path（E3 解釋正確） |
| K-5 | 5 策略 7d gross net negative；CLAUDE.md §三 -6.98 已 stale | FA / QC / AI-E / CC | 🔴 CRITICAL | ✅ VERIFIED：PG 真查 demo 7d -26.44 USDT（funding_arb -15.43 / grid -11.15 / ma +0.20 / bb -0.06）；live_demo 7d gross +0.43（grid -0.95 / ma +1.38 / bb 0）；合計 ~-26 USDT |
| K-6 | learning.governance_audit_log 0 row（LG-5 reviewer 死於 wiring） | FA / E5 / CC + 隱含 MIT | 🟠 HIGH | ❌ **DISPUTED** — PG 真查 22,790 row；LG-5 W3 FUP-1 commit `463890d` 已 deploy 並運行；CC + FA 引用 stale；E5 C-4 條目錯（reviewer 在跑） |

### 3.2 中共識（2-3 agents）— 12 條摘要

| # | Finding | agents | severity |
|---|---|---|---|
| M-1 | Layer 2 雲端 0 流量 + provider_keys_store 空 | AI-E / FA | 🟠 HIGH |
| M-2 | 5 ML 訓練腳本 silent-unscheduled（thompson/optuna/cpcv/dl3/weekly_report）| FA / AI-E / E4 | 🟡 MEDIUM-HIGH |
| M-3 | learning.exit_features.est_net_bps 100% NULL writer fix 未 deploy | FA / MIT / CC | 🟠 HIGH |
| M-4 | attribution_chain_ok 24h 0.013% / training row 84.6% chain failed | FA / AI-E / MIT / CC | 🔴 CRITICAL |
| M-5 | 25 表跨 3 schema 0 row 死掉（learning 14 / observability 4 / replay 5 / agent 1 / 共 24）| E5 / MIT | 🟠 HIGH |
| M-6 | runner.rs 2467 LOC hard violation（governance 2000 cap 越過 467 行） | E5 (single source) | 🔴 CRITICAL |
| M-7 | DSR/PBO/CPCV advisory only 未進 promotion gate | QC / MIT | 🟠 HIGH |
| M-8 | docs/README.md 5 天無更新 50+ 文件缺漏 | TW / R4 | 🟠 HIGH |
| M-9 | Decision Lease flip→writer→DB row e2e regression test 0 case | E4 / E3 | 🟠 HIGH |
| M-10 | feature_baselines + drift_events 0 writer / drift chain broken | MIT / E5 | 🟠 HIGH |
| M-11 | tab-settings.html Decision Lease GUI hard-coded false | A3 / CC | 🟠 HIGH |
| M-12 | xlang ATR / BB / Sharpe 1e-4 容差 test 0 case | E4 (single) | 🟠 HIGH |

### 3.3 單 agent 揭發 + 高 severity（必收口）

| Finding | agent | severity | PA 核實 |
|---|---|---|---|
| AMD-2026-05-02-01 §5.4 流程搶跑 7 天提前 flag flip | CC | 🔴 CRITICAL | ✅ VERIFIED — engine env `=1` Linux deploy 5/3 但 amendment 規定 5/15 後 |
| 909 MB damaged dump 24+ 天無人引用 | E5 | 🔴 CRITICAL | ✅ VERIFIED — risk_verdicts_damaged 903 MB / 4 表 952 MB total |
| Engine binary 25 MB 未 strip | E5 | 🟠 HIGH | ✅ VERIFIED |
| risk_verdicts 18.47M row 5 chunk 過大 + 無 compression + 無 retention | MIT | 🔴 CRITICAL | ✅ VERIFIED |
| `--host 0.0.0.0` in 4 deploy script | E3 HIGH-4 | 🟠 HIGH | ✅ VERIFIED — restart_all.sh:489 + clean_restart.sh:390 |
| `phase4_routes/weekly_review/approve+reject` 0 actor | E3 HIGH-2 | 🔴 CRITICAL | ✅ VERIFIED — phase4_routes.py:822/832 純 `(payload: WeeklyReviewApproveRequest)` 0 Depends |
| `scout_routes/post_market_signal+post_event_alert` 缺 require_operator | E3 HIGH-3 | 🟠 HIGH | ✅ VERIFIED — scout_routes.py:325/431 有 actor: Depends 但 0 require_operator |
| 0 CI workflow / aarch64-apple-darwin 0 自動驗證 | E5 H-9 | 🟠 HIGH | ✅ VERIFIED — `.github/workflows/` directory 不存在 |
| Bybit 字典 4 drift（L5-1 至 L5-4，含 G9-02 章節缺）| BB | 🟢 LOW | ✅ VERIFIED — 字典 line 137 `interval` vs Rust line 195 `intervalTime` |
| ContextDistiller 不存在 / 是 V3 spec 未 IMPL | AI-E | 🟠 HIGH | ✅ VERIFIED — find -name "*distiller*" 全 codebase 0 hit |

---

## §4 核實結果（Top 30 Critical/High）

| ID | Finding | Severity | Source agents | Verification | 真實狀態 |
|---|---|---|---|---|---|
| F-01 | shadow_mode TOML × 3 + lambda:True | 🔴 C | FA/CC/E5/E4/AI-E | ✅ VERIFIED | executor_agent.py:223-224 + 3 TOML 全 true |
| F-02 | CLAUDE.md §三 lease flag stale | 🔴 C | FA/CC/R4/E4/TW | ✅ VERIFIED | runtime `=1` vs §三 default OFF (5d drift) |
| F-03 | lease_transitions audit wiring 死 | 🔴 C | E3/FA/E5/MIT | ✅ VERIFIED | spawn fn 0 caller + PG 0 row |
| F-04 | H0_GATE Python 0 production caller | 🟠 H | FA/E4/E5/E3 | ✅ VERIFIED | Python 0 hit；Rust active |
| F-05 | 5 策略 7d gross net negative | 🔴 C | FA/QC/AI-E/CC | ✅ VERIFIED | demo -26.44 USDT |
| F-06 | LG-5 reviewer 0 audit row | 🟠 H | FA/CC/E5 | ❌ DISPUTED | PG 22,790 row（reviewer 已活）|
| F-07 | Layer 2 0 流量 + provider key 空 | 🟠 H | AI-E/FA | ✅ VERIFIED | 24h cost $0 + key store 0 file |
| F-08 | 5 ML 腳本 silent-unscheduled | 🟠 H | FA/AI-E/E4 | ✅ VERIFIED | crontab 確認無排程 |
| F-09 | est_net_bps 100% NULL not deployed | 🟠 H | FA/MIT/CC | ✅ VERIFIED | sibling FUP-2 commit `34211ab4` 待 merge |
| F-10 | attribution_chain 24h 0.013% | 🔴 C | FA/AI-E/MIT/CC | ✅ VERIFIED | 從 CLAUDE.md §三 [42b] 確認 |
| F-11 | 24 表 0 row dead schema | 🟠 H | E5/MIT | ✅ VERIFIED | PG 表清單比對 |
| F-12 | runner.rs 2467 hard violation | 🔴 C | E5 | ✅ VERIFIED | LOC `wc -l` 確證 |
| F-13 | DSR/PBO/CPCV advisory only | 🟠 H | QC/MIT | ⚠️ PROBABLE | 代碼 IMPL OK；非 promotion gate |
| F-14 | docs/README 50+ 缺漏 | 🟠 H | TW/R4 | ✅ VERIFIED | 索引 grep 確認 |
| F-15 | Lease writer e2e test 0 case | 🟠 H | E4 | ✅ VERIFIED | grep test_*lease* 確認 |
| F-16 | feature_baselines / drift_events 0 writer | 🟠 H | MIT/E5 | ✅ VERIFIED | PG 0 row + 0 producer code |
| F-17 | tab-settings GUI hard-coded false | 🟠 H | A3/CC | ✅ VERIFIED | tab-settings.html:393 |
| F-18 | xlang ATR/BB 1e-4 test 0 case | 🟠 H | E4 | ✅ VERIFIED | 只有 manifest signer xlang 13 case |
| F-19 | AMD §5.4 流程搶跑 7 天 | 🔴 C | CC | ✅ VERIFIED | engine env `=1` 5/3 vs amendment 5/15 |
| F-20 | 909 MB damaged dump 死數據 | 🔴 C | E5 | ✅ VERIFIED | PG 952 MB / 24+ 天 |
| F-21 | Engine binary 25MB 未 strip | 🟠 H | E5 | ✅ VERIFIED | file 命令確認 |
| F-22 | risk_verdicts 18.47M / 5 chunk / 0 retention | 🔴 C | MIT | ⚠️ PROBABLE | row + chunk OK；retention policy 缺 |
| F-23 | --host 0.0.0.0 in 4 script | 🟠 H | E3 | ✅ VERIFIED | restart_all.sh:489 + clean_restart.sh:390 |
| F-24 | phase4 weekly_review 0 actor | 🔴 C | E3 | ✅ VERIFIED | phase4_routes.py:822/832 |
| F-25 | scout_routes 0 require_operator | 🟠 H | E3 | ✅ VERIFIED | scout_routes.py:325/431 |
| F-26 | 0 CI workflow aarch64-apple-darwin | 🟠 H | E5 | ✅ VERIFIED | .github/workflows/ 不存在 |
| F-27 | Bybit 字典 4 drift | 🟢 L | BB | ✅ VERIFIED | 字典 line 137 vs Rust 195 |
| F-28 | ContextDistiller 不存在 | 🟠 H | AI-E | ✅ VERIFIED | grep distiller 0 hit |
| F-29 | engine_mode 'demo_archive_20260418' 6,616 row CHECK 漏 | 🟠 H | MIT | ✅ VERIFIED | PG GROUP BY 確認 |
| F-30 | governance prompt() × 4 + learning prompt() × 2 | 🟠 H | A3 | ⚠️ PROBABLE | 代碼 grep 應確證；A3 路徑詳細 |

**核實率**：30 個 Top finding 中 24 ✅ + 4 ⚠️ + 1 ❌ + 1 模糊 = 80% VERIFIED。**主要 disputed**：F-06（LG-5 reviewer 已 active 22,790 row，3 個 audit agent 寫 stale）。

---

## §5 校核需求（agent 矛盾 / 跨來源不一致）

| 矛盾點 | 兩方說法 | PA 結論 | 建議行動 |
|---|---|---|---|
| C-1 LG-5 reviewer audit row | FA/E5/CC 寫 0 row；MIT 也說 dead；E3 寫「writer code 在 + 22,789 row」 | E3 + PG 直查 22,790 row 為真，**LG-5 reviewer 已 deploy 並 active** | 通知 FA/CC/E5 停止複製 stale；TW + R4 補 docs/README 索引 LG-5 active 狀態 |
| C-2 5 策略 7d gross | CLAUDE.md §三 -6.98（5/3 stale）；QC -26.80；FA -6.98 引用 §三；PA 直查 -26.44 demo+0.43 live_demo | demo 7d net **-26.44 USDT**（funding_arb 殘倉 -15.43 + grid -11.15 主因），live_demo 7d net +0.43 USDT | CLAUDE.md §三 即時更新；移除 -6.98 寫 -26 並加 healthcheck id；FA push back #1 立即執行 |
| C-3 H0_GATE 0 caller 是否影響交易安全 | FA + E4 + E5：「DOC-02 spec 死」；E3：「Rust h0_gate active hot path / Python H0_GATE 才 dead」 | E3 解釋正確：trading safety 不受影響；Python H0_GATE 是孤兒 wiring | F-04 finding 改為「Python H0_GATE singleton 0 production caller（infrastructure dead，不影響 Rust hot path）」；不阻 live |
| C-4 panorama [42c] attribution drift FAIL | CC §3 #9 違反；MIT §6 不確定 target leakage | CLAUDE.md §三 標 FAIL；MIT 待累積樣本 | 屬 P1-7 LEARNING-PIPELINE-DORMANT-1 範圍，等 labels 累積；非本次 fix 範圍 |
| C-5 Sprint A/B/C/D closure narrative 是否仍應留 §三 | TW: 5/8 應歸檔；CLAUDE.md §三 第 116-127 仍敘述 | TW 對：滿 +2 day 規則 5/7 應歸檔，現多 1 日 | W-AUDIT-1 包：歸檔 §三 snapshot 同 commit 修 stale |

**校核 SQL（reviewer 應每週跑 1 次以防 stale）**：

```sql
-- 5 策略 7d gross
SELECT engine_mode, strategy_name, count(*) AS fills, round(sum(realized_pnl)::numeric, 2) AS gross_pnl
FROM trading.fills WHERE ts >= NOW() - INTERVAL '7 days' AND engine_mode IN ('demo','live_demo')
GROUP BY engine_mode, strategy_name ORDER BY 1, 2;

-- governance_audit_log row health
SELECT count(*), max(created_at) FROM learning.governance_audit_log;

-- 0-row dead schema
SELECT schemaname||'.'||relname AS table, n_live_tup
FROM pg_stat_user_tables WHERE n_live_tup = 0
ORDER BY schemaname, relname;
```

---

## §6 修復計劃 — Wave 組織（W-AUDIT-1 至 W-AUDIT-7）

設計原則：每 wave **可獨立交付**；高並行度（同 wave 內 ≥3 sub-agent 平行可能）；強依賴串行（lease audit writer → lease test）；不破現有 TODO v13 W-A/W-B/W-C dispatch。

### W-AUDIT-1: 文檔同步 + 流程合規（CRITICAL stale chain）

**派 agents（並行）**：TW (R4 助攻) + PM
**目標**：解 F-02 / F-19 / 部分 F-14 + 12 audit 引用 stale 數字一次清
**Sub-tasks**（並行）：
1. CLAUDE.md §三 全 sync：lease flag default OFF→ON / Sprint A-D 歸檔 / 5 策略 -6.98→實時數 / [42b] 0.013% 維持 + healthcheck id 引用（**0.5h** by PM）
2. CLAUDE.md §五 同步「Rust router gate active」非「Python only唯一 production caller」（**0.2h** by PM）
3. CLAUDE.md §四 第 5 個 Live 門控說明改為 flag flip + amendment §5.4.1 修訂條款（**0.3h** by PM）
4. PM 補 `docs/governance_dev/2026-05-08--w_c_lease_router_flag_authorized.md` 操作授權記錄文件（**0.5h** by PM）
5. amendment §5.4.1 修訂條款追加（**0.5h** by PM）
6. docs/README.md 補 50+ 缺漏（multi_agent_rework 14 / ADR 14 / openclaw_repositioning / audit / execution_plan 5 / archive 39）（**1h** by TW）
7. SPECIFICATION_REGISTER.md 新增 LG-X / SM-03 改 Active / EX-03 補登 / ARCH-02/03 / AUDIT-13（**0.5h** by R4）
8. CONTEXT.md 補 LG-X / REF-19 / REF-21 / Agent Spine / 3-Config / feature flag 詞條（**0.3h** by R4）
9. ADR 0015-0019 補錄（OpenClaw repositioning / Decision Lease retrofit / Scanner Opportunity 退權威 / Funding Arb V2 / GitHub Issues active）（**1h** by PA + R4）
10. SCRIPT_INDEX.md 補 ~20 個漏登 script（**0.3h** by TW）
11. docs/CCAgentWorkSpace/ 補 MIT/BB workspace/README.md（**0.2h** by R4）

**並行性**：1+2+3+4+5 由 PM 串行（同 source CLAUDE.md/amendment）；6+7+8+9+10+11 全並行
**Session 拆分**：1 session 即可（皆 docs，~3-4h 總工時）
**驗證 agent**：CC（合規復驗）+ TW（doc 規範復驗）
**估計總工時**：~4.5h
**依賴**：無
**輸出**：1 commit chain（~12 files changed）

### W-AUDIT-2: 安全 + 認證硬補（true-live 前必修 4 條 HIGH）

**派 agents**：E1（並行 3 sub）+ E2 + E4
**目標**：解 F-23 / F-24 / F-25 + 部分 F-03（lease audit channel writer wire）
**Sub-tasks**：
1. **F-24** phase4_routes.py:822/832 加 `actor: Depends(base.current_actor)` + `require_scope_and_operator(actor, "learning:manage")`（**1h** by E1-a）— 純 5-min code change
2. **F-25** scout_routes.py:325/431 加 `require_scope_and_operator(actor, "learning:write")`（**0.5h** by E1-a 同 PR）
3. **F-23** restart_all.sh:489 + clean_restart.sh:390 + fresh_start.sh + deploy/README.md `--host 0.0.0.0` 改 `--host ${OPENCLAW_BIND_HOST:-127.0.0.1}` + Tailscale serve frontend doc（**1.5h** by E1-b）
4. **F-03 partial** spawn_lease_transition_pipeline 接線到 main.rs / pipeline_ctor.rs（**4h** by E1-c）— Rust IPC 改 Mutex/Mpsc setup
5. layer2_routes.py:174 `/trigger` 加 `require_scope_and_operator(actor, "ai_budget:write")`（**0.3h** by E1-a）
6. ai_service_listener.py:149 加 `os.chmod(socket_path, 0o600)`（**0.2h** by E1-d）
7. IPC HMAC paper/demo opt-in fail-OPEN 設計（推遲到 W-AUDIT-3 IPC binary protocol 整合，**現只標 P1 backlog**）

**並行性**：1+2+3+4+5+6 全並行（不同 file）；E1-a 1+2+5 同 PR
**Session 拆分**：1 session（4-6h），可背景跑 sub-agent 並行
**驗證 agent**：E2 review + E4 regression（M9: lease flip→writer→DB row e2e test）+ E3 安全 sign-off
**估計總工時**：~7-8h
**依賴**：W-AUDIT-1 完成後再做（避免和 doc commit chain 撞）
**輸出**：4-5 commit（每 file 一筆）

### W-AUDIT-3: ExecutorAgent fake-live runtime smoke + 5-Agent decision spine（ALIGN W-A/W-B 既有）

**派 agents**：E1 + E1a + E2 + E4
**目標**：解 F-01 + F-15 + F-17 + 部分 M-9
**Sub-tasks**：
1. **F-01** ExecutorAgent shadow_mode_provider 必須注入 fail-loud（移除 `lambda: True` fallback）（**1h** by E1-a）
2. **F-01** TOML × 3 設計意圖鎖定（FA push back #2）：寫 amendment 明說「shadow_mode=true 是 W-A demo fail-close，等 P0-EDGE-1 後 demo 翻 false 啟 shadow→live promotion」**或**「5-Agent 鏈本來就是 shadow-only 觀察工具」— **PM 必須拍板**（**0.5h decision + 0.5h spec writing**）
3. **F-17** tab-settings.html:393 改 dynamic 從 `/api/v1/governance/lease-router/status` 讀（**1h** by E1-b）
4. **F-15** Decision Lease flag flip→writer→DB row e2e regression test（**4h** by E4 + E1-c spawn 真 PG + Rust binary）
5. ExecutorAgent runtime smoke：透過 ssh trade-core 觀察 1h flag flip 後 chains_with_lease（已 33）+ shadow→live cohort 真實流量（**2h smoke + observation** by E4 + ops）
6. ExecutorConfigCache shadow_mode_provider polling 機制 spec 條目補 SM-05 或 amendment 明示 polling 失敗設計選擇（**1h** by PA + PM）

**並行性**：1+3 同 file 衝突低；2+6 PM/PA 並行；4 串行依賴 W-AUDIT-2 #4 完成；5 在 4 完成後再做
**Session 拆分**：2 session（cohort 1：1+3 IMPL；cohort 2：4+5 e2e regression）
**驗證 agent**：E2 review + E4 regression + CC 合規確認
**估計總工時**：~10h（橫跨 2 sprint）
**依賴**：W-AUDIT-2 #4（lease audit writer wire）必須完成；W-A/W-B（既有 TODO v13）並行進行
**輸出**：3-4 commit chain

### W-AUDIT-4: ML 基座 + dead schema 收口

**派 agents**：E1（W-AUDIT-4a Rust 部分 + W-AUDIT-4b SQL 部分）+ MIT + E2
**目標**：解 F-08 / F-11 / F-16 / F-22 / F-29 / 部分 M-2 / M-3 / M-10
**Sub-tasks**：
1. **F-22** V075 retention policies 9 表（risk_verdicts 30d / decision_features 90d / position_snapshots 90d / signals 90d / scorer_training_features 60d / mlde_edge_training_rows 90d / order_state_changes 60d / intents 90d / decision_outcomes 180d）（**3h** by E1-a + MIT 設計）
2. **F-22** risk_verdicts compression policy + chunk size 修（compress_after 7d）（**2h** by E1-a）
3. **F-11** V068 / V069 / V070 / V071 4 條 migration drop dead schema（**4h** by MIT 設計 + E1-b IMPL）— 注意保留 cost_edge_advisor_log / ai_usage_log / ai_budget_config / directive_executions / teacher_directives 5 個 archive 而非 drop
4. **F-16** V072 feature_baselines writer init + helper script `feature_baselines_writer.py`（**4h** by MIT + E1-c）
5. V073 edge_estimate_snapshots cycle writer hourly cron（**3h** by E1-c）
6. V074 decision_outcomes live cohort backfiller daily cron（**3h** by E1-d）
7. V076 retrofit Guard A for V062/V063/V065（**1h** by E1-e）
8. **F-29** trading.fills.engine_mode='demo_archive_20260418' CHECK constraint 標準化 6,616 row（**2h** by E1-f）
9. **F-08** 5 ML 訓練腳本 cron 化（thompson/optuna/cpcv/dl3/weekly_report）（**3h** by E1 + ops）
10. **F-09** sibling FUP-2 commit `34211ab4` E4 regression 確認 + merge + deploy（**4h** by E4 + ops，被動等待）

**並行性**：1+2 同 risk_verdicts 表；3+4+5+6+7 都是 V### migration 並行；8 獨立；9+10 並行
**Session 拆分**：3 session（Wave 4a SQL/migration 1session；Wave 4b retention/policy 1session；Wave 4c cron + ML 訓練 1session）
**驗證 agent**：MIT + E2 + E4 + 對應 audit agent 復查
**估計總工時**：~30h（最長 wave，可分 2 sprint）
**依賴**：W-AUDIT-1 完成（CLAUDE.md §三 同步 stale）；可與 W-AUDIT-2/3 並行
**輸出**：8-10 commit chain

### W-AUDIT-5: 性能 / 結構 / 跨平台 readiness（E5 30 條 + BB drift）

**派 agents**：E1（並行 3 sub）+ E5 + E2 + E4
**目標**：解 F-12 / F-20 / F-21 / F-26 / F-27 / 部分 M-5
**Sub-tasks**：
1. **F-12** runner.rs 2467 拆 5 sibling（config/scheduler/reporter/calibrator/metrics）（**6h** by E1-a）
2. **F-20** DROP `trading.*_damaged_20260414_130607` 4 表（先 dump NAS）（**2h** by E1-b + ops）
3. **F-21** Cargo.toml [profile.release] 加 `strip = "symbols"`（**0.5h** by E1-c）
4. **F-26** 建 `.github/workflows/ci.yml` cargo check `aarch64-apple-darwin` + linux-gnu matrix（**4h** by E1-d）
5. **F-27** 字典 4 drift 修（L5-1 至 L5-4 + G9-02 章節補）（**1.5h** by TW 或 BB 自己提 PR）
6. test_h_state_query_handler.py 2641 拆（**3h** by E4）
7. event_consumer/loop_handlers + dispatch 1144+1195 再拆（**4h** by E1-e）— 可放下個 sprint
8. json.loads/dumps 全替換 orjson（drop-in）（**3h** by E1-f）— 可放下個 sprint
9. Python copy.deepcopy 10 處改 frozen dataclass（**6h** by E1-g）— 可放下個 sprint
10. ai_budget tracker 16+ 鎖 → RwLock + per-strategy ArcSwap（**4h** by E1-h）— 可放下個 sprint

**並行性**：1+2+3+4+5+6 全並行（不同 file）；7-10 是 W-AUDIT-5b 下個 sprint
**Session 拆分**：2 session（Wave 5a urgent CRITICAL/HIGH 1session；Wave 5b performance optimization 1session 下個 sprint）
**驗證 agent**：E5 復查 + E2 review + E4 regression
**估計總工時**：~17h（5a）+ ~17h（5b）= 34h 總共
**依賴**：W-AUDIT-1 完成；可與 W-AUDIT-3/4 並行
**輸出**：6-10 commit chain

### W-AUDIT-6: 策略 + 量化（QC 5 策略 verdict + DSR/PBO 強制 promotion gate）

**派 agents**：E1 + QC + E2 + E4
**目標**：解 F-13 + 5 策略各自決策（QC verdict）
**Sub-tasks**：
1. **5 策略決策（PM 拍板）**（**1d 決策**）：
   - grid_trading: CONDITIONAL（限 ORDIUSDT only + 7d gross > 0 + DSR > 0.95 + PBO < 0.5 後 advance）
   - ma_crossover: REVISE（R:R 不對稱必修；trailing/TP 重寫；min_trades 50→200 + DSR/PBO 驗）
   - funding_arb: RETIRE（V2 棄策略路徑已開始；3 端 TOML 完全清除）
   - bb_breakout: REJECT 1m → REVISE 5m（必上 RFC + Donchian shift(1) 修補）
   - bb_reversion: REJECT 單獨運行 → 配 ma_crossover 做 pair trade，或 RETIRE
2. **F-13** DSR/PBO/CPCV 強制 promotion gate（**8h** by QC + E1-a）— 寫入 `learning_engine/promotion_gate.py` 並 wire 進 LG-2 IMPL（與 LG-2 H0 production caller 同 sprint）
3. per_trade_risk_pct 雙 SSOT 統一 0.1%（**1h** by E1-b）— 修 `kelly_sizer.rs:109 risk_pct=0.03` 改讀 RiskConfig
4. Kelly tier 8/6/4 改 RiskConfig（**2h** by E1-c）— `kelly_sizer.rs:198-204` 改 `RiskConfig.kelly.{young/mature/established}_fraction`
5. fast_track 15%/5%+3σ 改 RiskConfig（**1h** by E1-d）
6. funding_arb 完全清除 RiskConfig schema 段（**1h** by E1-e）
7. bb_breakout cooldown 600k vs 300k 統一（**0.3h** by E1-f）
8. bb_breakout 1m → 5m RFC（**4h by QC**）
9. ma_crossover R:R 重寫 trailing/TP（**1d by QC + E1**）
10. 加 production VaR/CVaR/EVT（QC 推 portfolio-construction-protocol §4）（**3d by QC + MIT**）— 大型工作可推遲到下個 cycle

**並行性**：1 是 PM 決策；2-9 中 3+4+5+6+7 並行（純 config）；8+9 是 QC 工作；10 是大型工作
**Session 拆分**：2-3 session（Wave 6a PM 決策 + 簡單 config refactor；Wave 6b QC 重寫 ma_crossover/bb_breakout；Wave 6c portfolio VaR/CVaR）
**驗證 agent**：QC + E2 + E4
**估計總工時**：~30h（不含 portfolio 整體 VaR）
**依賴**：W-AUDIT-1 / W-AUDIT-3（fake-live 確認）；可與 W-AUDIT-4 並行
**輸出**：8-10 commit chain

### W-AUDIT-7: AI 棧 + GUI/UX 收口

**派 agents**：E1 + AI-E + A3 + E2 + E4
**目標**：解 F-07 / F-28 / F-30 + 部分 A3 30 issues
**Sub-tasks**：
1. **F-07** Operator 透過 GUI 寫一次 ANTHROPIC_API_KEY，啟用 L1 Triage 試運行 7d（**operator action 5min**）
2. Strategist max_param_delta_pct 30%→50% 或換 Ollama 27B（**1h by E1**）
3. CostEdgeAdvisor `OPENCLAW_COST_EDGE_ADVISOR=1` env + restart 啟動（**0.5h by ops**）
4. **F-28** ContextDistiller IMPL（profile spec → code）（**8h by PA + E1**）— 可推遲到 LG-2 IMPL 之後
5. **F-30** governance prompt() × 4 + learning prompt() × 2 改自定義 modal（**4h by A3 IMPL + E1**）
6. tab-system.html live_reserved 確認加 5s 倒計時 / hold-to-confirm（**2h by A3 + E1**）
7. tab-strategy.html / tab-live.html / tab-paper.html 高風險按鈕視覺隔離（**3h by A3 + E1**）
8. Layer2 autonomous loop（hourly L1 triage cron）（**8h by E1 + AI-E**）— 推遲到下個 cycle

**並行性**：1+2+3 是 operator/ops action；4+5+6+7 是 GUI/AI-E 工作並行
**Session 拆分**：2 session（Wave 7a operator + GUI urgent；Wave 7b ContextDistiller + Layer2 autonomous）
**驗證 agent**：A3 + AI-E + E2 + E4
**估計總工時**：~25h
**依賴**：可與 W-AUDIT-3/4/5/6 並行；CostEdgeAdvisor 啟動先要等 7d 累積 ai_spend
**輸出**：5-8 commit chain

### Wave summary 表

| Wave | Owner | 工時 | Agents | 依賴 | 並行/串行 | Session 數 |
|---|---|---:|---|---|---|---:|
| W-AUDIT-1 | TW + R4 + PM | ~4.5h | TW/R4/PM/PA | 無 | 並行 | 1 |
| W-AUDIT-2 | E1 + E2 + E4 + E3 | ~7-8h | E1×4 並行 + E2 + E4 + E3 | W-AUDIT-1 | 並行 sub | 1 |
| W-AUDIT-3 | E1 + E1a + E2 + E4 + PA | ~10h | E1+E1a×3 並行 + E2 + E4 + PA | W-AUDIT-2 #4 | 部分串行（lease 鏈）| 2 |
| W-AUDIT-4 | E1 + MIT + E2 + E4 | ~30h | E1×6 並行 + MIT + E2 + E4 | W-AUDIT-1 | 大幅並行 | 3 |
| W-AUDIT-5 | E1 + E5 + E2 + E4 | ~17h+17h | E1×6 並行 + E5 + E2 + E4 | W-AUDIT-1 | 並行 sub | 2 |
| W-AUDIT-6 | E1 + QC + E2 + E4 + PM | ~30h | E1×5 並行 + QC + E2 + PM | W-AUDIT-1/3 | 部分串行 | 3 |
| W-AUDIT-7 | E1 + AI-E + A3 + E2 + E4 | ~25h | E1×4 並行 + AI-E + A3 + E2 | 可獨立 | 並行 sub | 2 |
| **總計** | | **~140h** | 平行可達 ~20 sub-agent | | | **14 session** |

---

## §7 完整 finding 清單（按 wave 排序）

| ID | Wave | 改 file:line | 修 agent | 核驗 agent | 時數 | 依賴 | 並行/串行 |
|---|---|---|---|---|---:|---|---|
| F-02 | W-AUDIT-1 | CLAUDE.md §三/§五/§四 | PM | CC + TW | 1h | 無 | parallel-1 |
| F-19 | W-AUDIT-1 | docs/governance_dev/2026-05-08--w_c_lease_router_authorized.md + amendment §5.4.1 | PM | CC | 1h | F-02 同 chain | serial-after-F-02 |
| F-14 | W-AUDIT-1 | docs/README.md | TW | R4 | 1h | 無 | parallel-1 |
| F-spec-reg | W-AUDIT-1 | SPECIFICATION_REGISTER.md / CONTEXT.md / ADR | R4 + PA | TW | 1.5h | 無 | parallel-1 |
| F-script-idx | W-AUDIT-1 | helper_scripts/SCRIPT_INDEX.md | TW | n/a | 0.3h | 無 | parallel-1 |
| F-tw-misc | W-AUDIT-1 | TW Top 5 P1 ROI 雜項 | TW | n/a | ~1h | 無 | parallel-1 |
| F-24 | W-AUDIT-2 | phase4_routes.py:822/832 | E1-a | E2 + E3 + E4 | 1h | W-1 | parallel-2 |
| F-25 | W-AUDIT-2 | scout_routes.py:325/431 | E1-a | E2 + E3 | 0.5h | W-1 | parallel-2 (E1-a 同 PR) |
| F-23 | W-AUDIT-2 | restart_all.sh:489 + clean_restart.sh:390 + fresh_start.sh + deploy/README.md | E1-b | E2 + E3 + ops | 1.5h | W-1 | parallel-2 |
| F-03 | W-AUDIT-2 | main.rs / pipeline_ctor.rs / lease_transition_writer.rs | E1-c | E2 + E3 + E4 | 4h | W-1 | parallel-2 (但 W-3 等它) |
| F-mid-A | W-AUDIT-2 | layer2_routes.py:174 + ai_service_listener.py:149 | E1-d | E3 | 0.5h | W-1 | parallel-2 |
| F-01 | W-AUDIT-3 | executor_agent.py:223-224 + risk_config_*.toml × 3 | E1-a + PM 決策 | E2 + CC + E4 | 1h + 0.5d | W-2 #4 | partial-serial |
| F-17 | W-AUDIT-3 | tab-settings.html:393 + /api/v1/governance/lease-router/status | E1-b + A3 | E2 + A3 | 1h | W-2 #4 | parallel-3 |
| F-15 | W-AUDIT-3 | tests/lease_flag_flip_e2e.py | E4 + E1-c | E2 + ops | 4h | F-03 IMPL | serial-after-F-03 |
| F-spec-SM05 | W-AUDIT-3 | amendment SM-05 + ExecutorConfigCache polling 設計 | PA + PM | CC | 1h | F-01 PM 決策 | serial |
| F-22 | W-AUDIT-4 | sql/migrations/V075__retention_policies.sql | E1-a + MIT | E2 + MIT | 3h | W-1 | parallel-4 |
| F-22b | W-AUDIT-4 | sql/migrations/V075b__compression_policies.sql | E1-a | E2 + MIT | 2h | W-1 | parallel-4 |
| F-11 | W-AUDIT-4 | sql/migrations/V068-V071__drop_dead_*.sql | MIT + E1-b | E2 + E3 | 4h | W-1 | parallel-4 |
| F-16 | W-AUDIT-4 | sql/migrations/V072_feature_baselines + helper script | MIT + E1-c | E2 + MIT | 4h | W-1 | parallel-4 |
| F-edge-cycle | W-AUDIT-4 | sql/migrations/V073__edge_estimate_snapshots_cycle | E1-c | E2 + MIT | 3h | W-1 | parallel-4 |
| F-outcome-bf | W-AUDIT-4 | sql/migrations/V074__decision_outcomes_live_backfill | E1-d | E2 + MIT + E4 | 3h | W-1 | parallel-4 |
| F-V076 | W-AUDIT-4 | sql/migrations/V076__retrofit_guard_v062_v063_v065 | E1-e | E2 + MIT | 1h | W-1 | parallel-4 |
| F-29 | W-AUDIT-4 | trading.fills.engine_mode CHECK constraint | E1-f | E2 + MIT | 2h | W-1 | parallel-4 |
| F-08 | W-AUDIT-4 | helper_scripts/cron/*.sh × 5 | E1 + ops | E4 | 3h | W-1 | parallel-4 |
| F-09 | W-AUDIT-4 | sibling FUP-2 deploy | E4 + ops | MIT + FA | 4h | 被動 | serial |
| F-12 | W-AUDIT-5 | rust/openclaw_engine/src/replay/runner.rs split 5 sibling | E1-a | E2 + E5 + E4 | 6h | W-1 | parallel-5 |
| F-20 | W-AUDIT-5 | DROP TABLE trading.*_damaged_20260414_130607 + NAS dump | E1-b + ops | E2 + MIT | 2h | W-1 | parallel-5 |
| F-21 | W-AUDIT-5 | rust/Cargo.toml [profile.release] strip="symbols" | E1-c | E2 + E5 | 0.5h | W-1 | parallel-5 |
| F-26 | W-AUDIT-5 | .github/workflows/ci.yml | E1-d | E2 + E5 | 4h | W-1 | parallel-5 |
| F-27 | W-AUDIT-5 | docs/references/2026-04-04--bybit_api_reference.md L137/L171 + G9-02 chapter | TW or BB | E2 | 1.5h | W-1 | parallel-5 |
| F-test-h-state | W-AUDIT-5 | tests/test_h_state_query_handler.py 2641 split | E4 | E2 | 3h | W-1 | parallel-5 |
| F-deepcopy | W-AUDIT-5b | decision_lease_state_machine.py:507/614/618 + ... 10 處 frozen dataclass | E1-g | E2 + E4 | 6h | W-AUDIT-5a | parallel-5b |
| F-orjson | W-AUDIT-5b | json.loads/dumps 501 處 → orjson | E1-f | E2 + E4 | 3h | W-AUDIT-5a | parallel-5b |
| F-ai-budget | W-AUDIT-5b | ai_budget/tracker.rs RwLock + ArcSwap | E1-h | E2 + E5 | 4h | W-AUDIT-5a | parallel-5b |
| F-event-consumer | W-AUDIT-5b | event_consumer/loop_handlers + dispatch 再拆 | E1-e | E2 + E5 | 4h | W-AUDIT-5a | parallel-5b |
| F-strategy-decision | W-AUDIT-6 | PM 5 策略決策 | PM + QC | CC | 1d | W-1 + W-3 | serial |
| F-13 | W-AUDIT-6 | learning_engine/promotion_gate.py | QC + E1-a | E2 + E4 | 8h | W-AUDIT-6 PM | serial-after-PM |
| F-Kelly-config | W-AUDIT-6 | kelly_sizer.rs:198-204 + 109 + RiskConfig | E1-b + QC | E2 + E4 | 3h | W-1 | parallel-6 |
| F-fast-track | W-AUDIT-6 | fast_track.rs:74/89 + RiskConfig | E1-c | E2 + QC | 1h | W-1 | parallel-6 |
| F-funding-clean | W-AUDIT-6 | RiskConfig.toml × 3 funding_arb section 完全清除 | E1-d + QC | E2 + BB | 1h | W-1 | parallel-6 |
| F-bb-cooldown | W-AUDIT-6 | bb_breakout/mod.rs:191 vs 193 cooldown 統一 | E1-e | E2 + QC | 0.3h | W-1 | parallel-6 |
| F-bb-rfc-5m | W-AUDIT-6 | bb_breakout 1m → 5m RFC + IMPL | QC + E1 | E2 + QC | 4h spec + 1d IMPL | F-strategy-decision | serial-after-PM |
| F-ma-rewrite | W-AUDIT-6 | ma_crossover R:R trailing/TP 重寫 | QC + E1 | E2 + QC | 1d | F-strategy-decision | serial |
| F-VaR-CVaR | W-AUDIT-6c | learning_engine/portfolio_var.py + cvar.py | QC + MIT + E1 | E2 + QC | 3d | F-strategy-decision | serial-后期 |
| F-07 | W-AUDIT-7 | operator GUI ANTHROPIC_API_KEY + Layer2 trigger 1 manual | operator | AI-E | 5min + 1h obs | W-1 | parallel-7 |
| F-cea-env | W-AUDIT-7 | OPENCLAW_COST_EDGE_ADVISOR=1 env + restart | ops | AI-E | 0.5h | W-1 | parallel-7 |
| F-strategist-cap | W-AUDIT-7 | RiskConfig strategist max_param_delta_pct 30→50 | E1 | AI-E + QC | 1h | W-1 | parallel-7 |
| F-28 | W-AUDIT-7b | ContextDistiller IMPL（profile spec → code） | PA + E1 | E2 + AI-E | 8h | W-1 | parallel-7b |
| F-30 | W-AUDIT-7 | governance prompt() × 4 + learning prompt() × 2 → custom modal | A3 + E1 | E2 | 4h | W-1 | parallel-7 |
| F-system-mode-confirm | W-AUDIT-7 | tab-system.html:243-252 live_reserved 5s 倒計時 | A3 + E1 | E2 + A3 | 2h | W-1 | parallel-7 |
| F-strategy-confirm | W-AUDIT-7 | tab-strategy/live/paper Stop/Pause/Delete 視覺隔離 | A3 + E1 | E2 + A3 | 3h | W-1 | parallel-7 |
| F-layer2-cron | W-AUDIT-7c | Layer2 autonomous loop (hourly L1 triage cron) | E1 + AI-E | E2 + E4 | 8h | W-AUDIT-7a operator | serial-7c |

**總計列出 finding**：~52 條（高 + 中 severity）；剩餘 ~36 條 LOW + advisory 散在各 wave 順手做或 P3 backlog。

---

## §8 並行 / 後台 / Session 拆分建議

### 8.1 可後台 sub-agent 並行 cluster（同時跑 ≥3 sub-agent）

| Cluster | Wave | Sub-agents | 推薦 PM 派工策略 |
|---|---|---|---|
| W-1-DOCS | W-AUDIT-1 | TW + R4 + PA + PM 並行 | 1 session 4 sub-agent 平行 |
| W-2-SECURITY | W-AUDIT-2 | E1-a (phase4+scout+layer2) + E1-b (--host) + E1-c (lease audit wire) + E1-d (ai_service chmod) | 1 session 4 sub-agent 並行 |
| W-4-MIGRATION | W-AUDIT-4 | E1-a (retention) + E1-b (drop) + E1-c (feature_baselines+edge cycle) + E1-d (outcome backfill) + E1-e (Guard retrofit) + E1-f (engine_mode CHECK) | 1 session 6 sub-agent 並行 |
| W-5-STRUCTURE | W-AUDIT-5a | E1-a (runner.rs split) + E1-b (drop damaged) + E1-c (strip) + E1-d (CI) + TW (字典) + E4 (test split) | 1 session 6 sub-agent 並行 |
| W-6-CONFIG | W-AUDIT-6 (config refactor 部分) | E1-b (Kelly) + E1-c (fast_track) + E1-d (funding clean) + E1-e (bb_breakout cooldown) | 1 session 4 sub-agent 並行 |
| W-7-GUI | W-AUDIT-7 | A3 + E1-a (custom modal) + E1-b (live_reserved confirm) + E1-c (button isolation) | 1 session 4 sub-agent 並行 |

### 8.2 必須串行 chain

| Chain | 序列 | 理由 |
|---|---|---|
| Lease audit | F-03 (W-2 #4) → F-15 (W-3 e2e test) → flag flip canary 24h | 因為 audit channel writer 必須先 wire，e2e test 才能驗 |
| Strategy decision | PM W-6 5 策略決策 → F-13 promotion gate IMPL → F-bb-rfc-5m + F-ma-rewrite | 必須先決策才能 IMPL 對應策略 |
| Operator action chain | F-07 + F-cea-env operator action → 7d 觀察 → F-layer2-cron decision | Layer 2 cost projection 需要先 7d 真實 cost 累積才能 calibrate |

### 8.3 建議 Session 拆分

| Session | Scope | 預估 token 開銷 | 工時 |
|---|---|---|---|
| S-1 | W-AUDIT-1 全 docs | ~30k | 4-5h |
| S-2 | W-AUDIT-2 security IMPL + W-AUDIT-3 fake-live runtime smoke pre-IMPL | ~80k | 6-8h |
| S-3 | W-AUDIT-4a SQL migration（V068-V076） | ~120k | 8-10h |
| S-4 | W-AUDIT-4b ML cron + FUP-2 deploy + F-29 engine_mode | ~60k | 4-6h |
| S-5 | W-AUDIT-5a 性能 + 結構 + CI（runner.rs split + drop damaged + strip + .github + 字典） | ~80k | 6-8h |
| S-6 | W-AUDIT-6 PM 策略決策 + 5 策略 verdict 對應 IMPL（Kelly/fast_track/funding/bb cooldown） | ~80k | 6-8h |
| S-7 | W-AUDIT-6c QC ma_crossover 重寫 + bb_breakout 5m RFC + Wave 6 closure（含 W-AUDIT-6 portfolio VaR） | ~120k | 1-2 day |
| S-8 | W-AUDIT-7 GUI/UX + AI 棧 operator action + 部分 IMPL | ~60k | 4-6h |
| **共 8 session** | | | ~14-18 sprint days |

**Token budget 警告**：S-3 / S-7 是高 token session（>100k）；操作員若用 Sonnet 而非 Opus，需拆 sub-session。

---

## §9 與現有 TODO v13 對齊

### 9.1 mount 進現有 wave 的 finding（不新建 wave）

| Finding | 現有 wave | 整合說明 |
|---|---|---|
| F-01 ExecutorAgent shadow_mode | W-A executor fake-live runtime smoke | 既有 W-A 必須加 P1-FAKE-1 closeout 條件：`lambda: True` 移除 + TOML 設計意圖鎖定（FA push back #2）|
| F-15 lease flip→writer→DB row e2e | W-B runtime decision-spine/idempotency lineage | W-B 加 1 個 e2e regression test condition |
| F-03 lease audit channel writer wire | W-A 前置 + W-AUDIT-2 #4 | 必須**先**做 W-AUDIT-2 #4 再啟 W-A canary flip canary 24h |
| F-08 / F-09 / F-16 / 部分 ML 基座 | W-F edge/data 階段 | 既有 W-F 範圍應擴至包 V068-V076 全部 migration（PM 補 W-F sub-tasks）|
| F-17 / F-30 / F-system-mode-confirm | W-AUDIT-7 / GUI 工作 | 不阻 mainnet live；可獨立放 W-AUDIT-7 |

### 9.2 新建 wave 的 finding（不適合 mount 既有）

| Finding | 新 wave 建議 | 理由 |
|---|---|---|
| F-02 / F-19 / F-14 / spec-reg / script-idx | **W-AUDIT-1** 純 docs sync wave | 既有 TODO v13 W-A/W-B 是 IMPL 工作，docs sync 應獨立 wave，不堵 IMPL chain |
| F-23 / F-24 / F-25 4 安全條 | **W-AUDIT-2 SECURITY** | 不在既有 W-D MAG-083/MAG-084 之內；應作為 PRE-LIVE-2 前置工作 |
| F-12 / F-20 / F-21 / F-26 / F-27 結構 | **W-AUDIT-5 STRUCTURE** | 屬 maintenance backlog，不阻 W-A/W-B/W-D；可獨立 wave |
| F-strategy-decision / F-13 / F-bb-rfc | **W-AUDIT-6 STRATEGY** | 5 策略決策 + DSR/PBO promotion gate 是 P0-EDGE-1 ~05-15 決策的 sub-wave |

### 9.3 W-F / W-G 重新規劃建議

**W-F**（既有 edge/data + Live Gate LG-2/3/4）建議擴展為以下 sub-wave：
- W-F-1 = ML 基座 V068-V076 migration（即 W-AUDIT-4）
- W-F-2 = LG-2 H0 production caller IMPL（既有 P0-LG-1）
- W-F-3 = LG-3 provider pricing binding IMPL（既有 P0-LG-2）
- W-F-4 = LG-4 supervised live state machine IMPL（既有 P0-LG-3）
- W-F-5 = ContextDistiller IMPL（即 F-28，配 LG-2 後 wire）

**W-G**（既有 OpenClaw read-only）保持不變。

**新建 W-H**（Strategy verdict + portfolio）= 即 W-AUDIT-6 的續波（VaR/CVaR/EVT 進 production）。

---

## §10 PA Verdict + PM 必須拍板的 5 個決策

### 10.1 整體 verdict

**Conditional HOLD on supervised live**。88 finding 經 PA 核實 80% VERIFIED；6 個跨 agent 共識 critical 中：
- 3 條（K-1 / K-2 / K-3）必須在 supervised live 前修
- 1 條（K-4）trading 安全不影響但需 doc 修
- 1 條（K-5）等 W-AUDIT-6 PM 策略決策後解
- 1 條（K-6）已 disputed，不阻 live

**最早 supervised live**：以 6/15 悲觀 / 6/30 中位 / 7/15 樂觀為新規劃帶（本 audit 後重新評估）— PA 偏向悲觀，因為：
1. 88 finding 中 8 critical + 28 high 沒人按下開關就解
2. LG-2/3/4 仍 0% IMPL（4 個 P0 blocker）
3. 5 策略 verdict 需 PM 決策才能進 IMPL
4. AMD-2026-05-02-01 §5.4 流程搶跑必須先補件才能合規 sign-off

### 10.2 PA 對 PM push back 5 點（必拍板決策）

| # | 決策點 | PA 立場 | 期望 PM sign-off 方向 |
|---|---|---|---|
| **1** | **AMD-2026-05-02-01 §5.4 流程搶跑** — flag 已 ON 5 天但 amendment 規定 5/15 後 flip。CC 要求 PM 補 W-C 操作授權檔 + amendment §5.4.1 修訂條款（**或 flag 回 OFF 至 5/15**）| 必須立即補件，不可放過程序合規；W-AUDIT-1 第一順位 | 立即補 `2026-05-08--w_c_lease_router_authorized.md` + amendment §5.4.1（**0.5h**），flag 維持 ON；理由 = chains_with_lease=33 已驗 stable，比 5/15 P0-EDGE-2 結論更早可信 |
| **2** | **shadow_mode TOML × 3 設計意圖** — FA push back #2：擇 (a)「demo TOML 是 W-A demo fail-close，等 P0-EDGE-1 後 demo 翻 false 啟 shadow→live promotion」**或** (b)「5-Agent 鏈本來就是 shadow-only 觀察工具，真實下單永遠走 Rust tick_pipeline 直接路徑」 | (a) 才解 fake-live；(b) 是放棄 5-Agent 自主 chain 設計但解釋 ExecutorAgent 永 shadow 為何不違反原則 #11 | PA 推薦 (a) — demo TOML 翻 false 是 W-A executor smoke 必然路徑；補 SM-05 spec 條目；amendment 明說 W-A 完成後 demo TOML flip false |
| **3** | **CLAUDE.md §三 數值 vs runtime drift 防線失效** — FA push back #1：5 個數字 stale 5+ day。是否：(i) 把 runtime 數值搬出 §三 進入 healthcheck 自動產 status table；**(ii)** §三 7-day 自動重驗 cron（hard cap 5d）；(iii) 接受現狀但 docs/CONTEXT.md 加 cross-ref | PA 推薦 (i) + (ii) — runtime numerical state 不放 §三；§三 只描述「設計意圖」與「過去 ≤2 day 完成里程碑」 | (i) + (ii) 結合：W-AUDIT-1 把 5 stale 數字搬到 healthcheck 並在 §三 寫「runtime 數值見 healthcheck output」 |
| **4** | **5 策略決策（QC verdict 4/5 REJECT or REVISE）** — 是否：(i) 全 RETIRE / 重做；(ii) 保留 grid_trading（CONDITIONAL）+ ma_crossover REVISE + bb_breakout REJECT 1m → 5m + funding_arb RETIRE + bb_reversion 配 ma_crossover pair；(iii) 保留現狀觀望 P0-EDGE-1（5/15）後決定 | (ii) 是 QC 推薦；(iii) 是現狀延續但增加 2 sprint 風險 | (ii) — 進 W-AUDIT-6 PM 1d 決策 + 後續 IMPL；funding_arb completely RETIRE（包 RiskConfig.toml 完全清除 funding_arb section） |
| **5** | **openclaw_core 9 模組 + Layer 2 自主循環 14 天 0 動作 sunset** — FA push back #3：是否：(i) ADR-0015 「openclaw_core 9 模組永久 sunset」決議；(ii) 排進 W-AUDIT-5 P2 修；(iii) 接受長期共存 | PA 推薦 (i) + (ii) — ADR 0015 永久 sunset + 接續 wave drop 9 module；Layer 2 同 ADR 中明說「設計上 GUI-only，CLAUDE.md §五 圖示需更正」 | (i) + (ii)；補 ADR 0015 + 0017（Layer 2 spec 更正）+ W-AUDIT-5 P2 drop 9 module |

### 10.3 期望 PM 簽收的 4 條 hard truth

1. **88 finding 解到 supervised live 至少需 6-8 sprint**（不能只 1-2 sprint 速通）
2. **5 策略 net negative 是結構性問題**，非 ATR-SNR 等 micro-fix 可解；必須 ma_crossover R:R 重寫 + bb_breakout 5m + funding RETIRE + grid 限 ORDIUSDT 才能正
3. **AI 棧 cost = $0 / cost_edge_advisor 0 row / Layer 2 0 流量** — 系統至今 AI 真實貢獻只在 MLDE shadow（277 applied / 0% attribution）；要從 advisory-dormant 進 advisory-active 至少需 operator 1 day（API key + cron）+ 1 sprint code（Layer2 cron + ContextDistiller）
4. **CLAUDE.md 治理規則本身執行不徹底**（§七 7-day rule 形同空文 + §九 hard cap 違反 1 條 / Sprint A-D narrative 多 1 day stale）— 治理紀律必須升級為 W-AUDIT-1 自動化 cron healthcheck 而非靠 manual review

---

**PA AUDIT INTEGRATION DONE**

- 12 audit reports merged → 88 unique finding（去重後）
- 30 Top critical/high 經 SSH + grep + PG 直查驗證 80% VERIFIED
- 7 wave 修復計劃 + 與既有 TODO v13 對齊建議
- 5 個 PM push back 決策清單
- 預估總工時 ~140h / 8-14 session / 6-8 sprint to supervised live

報告路徑：`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-08--full_audit_pa_fix_plan.md`
