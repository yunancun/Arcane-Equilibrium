# 2026-05-09 W-AUDIT-1..7 已 verified-closed 內容歸檔

**歸檔目的**：把 12 verification agent 對抗性核實後**真 closed**的 finding + 過時的 W-AUDIT 計畫細節從 active TODO 移出，避免主 TODO.md 膨脹。

**歸檔範圍**：來自 2026-05-08 PA fix plan §6 W-AUDIT-1..7 的細節 + 對應 verification agent 標 ✅ FIXED 的 finding。

**未歸檔（仍在 active TODO）**：
- ❌ NOT-FIXED finding（120 條）→ 仍 active 等修
- ⚠️ PARTIAL finding（66 條）→ 仍 active 等收尾
- 🔄 REGRESSED finding（6 條）→ 升級為 active P0/P1
- 🆕 NEW-ISSUE（53 條）→ 加進 active TODO 為新條目

---

## §1 W-AUDIT-1 — Docs Sync + Governance Compliance（✅ Verified Partial-Close）

**TODO 自報**：DONE 2026-05-09 / commit `d90f3d10`
**R4 verdict**：CRITICAL × 5 真 closed 2/5（C1 + C5 確認）+ 結構修但實質缺漏（C4 LG-X 編號錯位 + 缺 LG-X-05；C2/C3 完全沒做）

### ✅ 已 verified closed 細節

| Sub-task | Verification Source | Evidence |
|---|---|---|
| CLAUDE.md §三 lease flag default OFF → ON sync | CC §2 + FA C-1 | grep `default OFF` = 0 命中；§三 line 69 `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` |
| CLAUDE.md §三 stale checkpoint `98ce3d00` → `b91487f2` | CC §2 + FA C-1 | grep stale checkpoint = 0 命中 |
| CLAUDE.md §五「Python 唯一 production caller」改 lease 路徑 A | CC §2 | grep 0 命中 |
| §三 5 stale 數字加 healthcheck id + 時間戳 | CC §2 (`P0-DECISION-AUDIT-3` close) | 每行 runtime 數字附 22:09 UTC + healthcheck id [55]/[33]/[40]/[42b]/[51] |
| AMD-2026-05-02-01 §5.4.1 補件 + W-C operator authorization 文件 | CC §1 + §2 (`P0-DECISION-AUDIT-1` close) | `docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md:133-161` + `docs/governance_dev/2026-05-08--w_c_lease_router_authorized.md`（67 行 6 章節）|
| dual-write fallback `RUST_HOT_PATH_PRE_AMENDMENT_2026-05-02` 字串常量在生產代碼 0 出現 | CC §2 + FA H-11 | grep 全 repo = 0 in code（rust/ + program_code/）|
| ADR-0015..0019 五份新 ADR 全 commit | CC §2 + R4 H1 | 5 個檔存在；遵循 Context/Decision/Consequences 三段 |
| docs/README.md 補 multi_agent_rework 14 文件 | R4 C1 | line 179-193 列 14 條完整 |
| SPECIFICATION_REGISTER SM-03 → Active / EX-03 / ARCH-02/03 / AUDIT-13 | R4 C5 | 全 ✅ Active |
| CONTEXT.md 補 LG-X / REF-19/21 / Agent Decision Spine / 3-Config / feature flag | R4 H4 + FA H-11 | 6 詞條完整含定義 |
| docs/CCAgentWorkSpace/Operator/ 加 README.md | R4 L3 | line 1-22 內容完整 |
| AMD-2026-05-09-01 SM-05 polling design draft | CC NEW-VIOLATION V-1 | `docs/governance_dev/amendments/2026-05-09--SM-05_executor_shadow_mode_polling_design.md` 標 Status: Draft / BLOCKED by P0-DECISION-AUDIT-2 |

### ❌ Verified NOT closed（移到 P1-AUDIT-DOCS-1b 新條目）

- C2 docs/README.md 補 docs/agents/ 整章
- C3 docs/README.md 補 helper_scripts/SCRIPT_INDEX.md 入口
- C4 SPECIFICATION_REGISTER LG-X 編號錯位 + 缺 LG-X-05（4 條 LG-5 RFC 全未登記）
- H3 docs/README.md 補 archive/ 缺漏 44 條
- H5 docs/README.md CCAgentWorkSpace 表補 MIT / BB（line 727 仍寫「17 個 Agent」）
- M5 MIT/BB workspace/README.md（位置補錯到 dir 根）

---

## §2 W-AUDIT-2 — Security IMPL（🔄 Source-only Close）

**TODO 自報**：DONE 2026-05-09 / commit `b052a10e`
**E3 + FA verdict**：source 真改 / runtime 未驗 / NEW-VULN-2 lease audit 0 emit

### ✅ 已 verified closed（source level）

| Sub-task | Verification Source | Evidence |
|---|---|---|
| F-24 phase4_routes.py:822/832 +actor +require_scope_and_operator | E3 §2 | grep require_scope_and_operator + actor: Depends |
| F-25 scout_routes.py:325/431 +require_operator | E3 §2 | grep 同 |
| F-23 restart_all.sh:489 + clean_restart.sh:390 + fresh_start.sh + deploy/README `--host 0.0.0.0` → `${OPENCLAW_BIND_HOST:-127.0.0.1}` | E3 §2 | source diff 確證；ss -tlnp 應驗 runtime |
| ai_service_listener.py:149 chmod 0o600 | E3 §2 | source diff |
| F-03 lease audit channel writer wire `spawn_lease_transition_pipeline` 接到 main.rs:657 | E3 + FA | grep main.rs:657 確證 |

### ⚠️ Verified PARTIAL（source close / runtime 未驗）

- 整個 W-AUDIT-2 必須 runtime restart 後重驗，並且 lease_transitions row count 必 > 0；當前 0 row（E3 NEW-VULN-2）

### 🆕 引入 NEW-VULN-2（HIGH）

E3 NEW-VULN-2：lease audit runtime 0 emit（source 接好但未 restart 落地）→ 改為 active P0 條目

---

## §3 W-AUDIT-3 — ExecutorAgent fake-live（⚠️ True PARTIAL）

**TODO 自報**：PARTIAL 2026-05-09 / commit `da2dba25`
**FA verdict**：F-17 真改 / F-15 e2e DB row coverage opt-in 默認 early-return / F-01 0% 修

### ✅ 已 verified closed

| Sub-task | Verification | Evidence |
|---|---|---|
| F-17 tab-settings.html:393 改 dynamic 從 `/api/v1/governance/lease-router/status` 讀 | A3 + FA | tab-settings.html:393 + JS:587-595 + 644 確證；fallback 'unknown' 黃色防 stale |

### ⚠️ Verified PARTIAL

- F-15 lease flip→writer→DB row e2e regression test：test 文件存在（`rust/openclaw_engine/tests/lease_flag_flip_e2e.rs`）但 DB row coverage 是 opt-in `OPENCLAW_TEST_PG`（默認 early-return）

### ❌ Verified NOT closed（卡 PENDING-OPERATOR）

- F-01 ExecutorAgent shadow_mode `lambda: True` fallback：executor_agent.py:224 仍存；3 TOML 仍 `shadow_mode = true`；卡 P0-DECISION-AUDIT-2

---

## §4 W-AUDIT-4 — ML 基座 + Dead Schema（❌ Verified DOWNGRADED）

**TODO 自報**：ACTIVE 2026-05-09
**FA + MIT verdict**：**全線降級假修**。V068/V070/V071 改成 reclassification guard（COMMENT only），row count 仍 0；F-08 cron not installed

### 🔄 PA 計畫降級為 metadata-only（不算真 fix）

| Sub-task | PA 計畫 | 實際落地 | Verdict |
|---|---|---|---|
| V068-V071 drop dead schema | 4 條 destructive DROP | 全改 COMMENT ON TABLE 'reclassified retained'；0 destructive | ❌ 降級 |
| F-08 5 ML 腳本 cron | crontab 啟動 | helper_scripts/cron/ml_training_maintenance_cron.sh 寫了但 cron not installed；且 5 個 path 與原 finding 5 個（thompson/optuna/cpcv/dl3/weekly）不對應 | ❌ 假修 |
| V075 retention policies 9 表 | add_retention_policy | 部分加但 V077 columnstore CHECK 撞 Timescale OSS 限制 → hotfix `49ceeb61` | ⚠️ 部分 |

### 真實 closed

- V076 retrofit Guard A for V062/V063/V065（FA M12 14% 覆蓋）
- F-29 trading.fills.engine_mode CHECK constraint（commit `09afc92c`）
- V072 feature_baselines contract guard（commit `2567b973`）

### attribution_chain_ok 24h 真實值

- 5/8 audit: 0.013%
- 5/9 verification: 0.0188%（**仍 catastrophic**）

---

## §5 W-AUDIT-5 — 性能/結構/CI（⚠️ Real Progress + Critical Mismatch）

**TODO 自報**：ACTIVE 2026-05-09
**E5 verdict**：F-21 strip ✅ / F-26 CI ✅ / F-27 字典 ✅ / **F-12 runner.rs 2467 UNCHANGED**（commit 改的是 bin/replay_runner.rs）

### ✅ Verified closed

| Sub-task | Commit | Evidence |
|---|---|---|
| F-21 Cargo.toml [profile.release] strip="symbols" | `d21444d6` | binary 25 MB → 20.6 MB（-4.4 MB）|
| F-26 .github/workflows/ci.yml cargo check aarch64-apple-darwin + linux-gnu | `97aea4b0` | matrix 真實 active |
| F-27 Bybit 字典 4 drift L5-1..L5-4 + G9-02 章節 | `f2b22fc1` | docs/references/2026-04-04--bybit_api_reference.md 補 |
| test_h_state_query_handler.py 2641 拆 | `c819758a` | shim + 4 split |
| W-AUDIT-5b orjson / deepcopy / ai_budget RwLock / event_consumer split | `e00985da` `a20dd1ce` `8d6646c2` `a44672e5` `3cff1005` | source 真改 |

### ❌ Verified NOT closed（E5 push back）

- F-12 runner.rs 2467 LOC hard violation：commit `3372eb18 refactor: split replay runner binary` 改的是 `bin/replay_runner.rs`（1599→626），不是原 finding 的 `runner.rs` 2467 行檔。**原 file 仍違反 governance 2000 cap**。需 PM/PA 對齊真實 file path。

---

## §6 W-AUDIT-6 — 策略 + 量化（⏸ Verified UNTOUCHED）

**TODO 自報**：NEW 2026-05-08
**QC verdict**：**0/20 量化問題修**；卡 P0-DECISION-AUDIT-4

### 真實狀態

完全未動。`b91487f2` (scanner) 與 `2567b973` (feature_baselines guard) 兩個 commit 與 QC 5/8 audit 的 20 量化問題完全無關。

### QC stand-alone 建議（不需 operator 拍板可立即動）

1. funding_arb schema 4 TOML 完全清除（1h）
2. Kelly tier 8/6/4 → RiskConfig.kelly.{young/mature/established}_fraction（3h）
3. bb_breakout cooldown 600k vs 300k 統一（0.3h）
4. DSR/PBO production caller 加進 promotion_pipeline.py demo gate（advisory，8h）
5. CLAUDE.md §三 -26.44 加掛 healthcheck id（0.5h）

---

## §7 W-AUDIT-7 — AI + GUI/UX（✅ Real GUI Progress + 🆕 Functional Regression）

**TODO 自報**：ACTIVE 2026-05-09 / commits `0f2a8809` `95364596` `7fccad06`
**A3 verdict**：4/5 critical close（7.4 → 8.1）+ 引入 NEW-ISSUE-1 LiveDemo 停

### ✅ Verified closed

| Sub-task | Commit | Evidence |
|---|---|---|
| F-30 governance 4 prompt() + learning 2 prompt() → custom modal | `0f2a8809` | grep prompt() = 0；5 個 modal 完整替換 |
| F-system-mode-confirm tab-system.html:243-252 live_reserved 5s countdown + 1.2s hold-to-confirm | `95364596` | 業界最高標準 |
| F-strategy-confirm tab-strategy/live/paper Stop/Pause/Delete 視覺隔離 | `7fccad06` | oc-action-cluster-destructive + dashed border + data-danger-zone |
| F-17 tab-settings.html Decision Lease dynamic（mounts W-AUDIT-3）| `da2dba25` 同 chain | dynamic from /api/v1/governance/lease-router/status |

### ❌ Verified NOT closed

- API Key 「清除」仍用 native confirm（tab-ai.html:652）— A3 push back #4
- Settings 8 種性質塞 1 tab — 完全沒拆
- mode-tag tag-green hard-coded — 完全沒 dynamic
- iframe 子頁無 mode chip
- live 14 sub-section 過載 / risk 雙層 sub-tab / system mode 5 button 仍純 grid
- F-07 operator GUI ANTHROPIC_API_KEY + Layer2 trigger remaining
- F-cea-env CostEdgeAdvisor env remaining
- F-strategist-cap RiskConfig strategist max_param_delta_pct 30→50 remaining
- F-28 ContextDistiller IMPL remaining（推遲到 LG-2 IMPL 之後）
- Layer2 autonomous loop hourly L1 triage cron remaining

### 🆕 引入 NEW-ISSUE-1 LiveDemo pipeline 停（CRITICAL）

`.codex/WORKLOG.md:332`：「live authorization file is missing」；W-AUDIT-7 階段 V077 hotfix engine-only restart with `--keep-auth` 過程 auth file 遺失。LiveDemo 從 5/8 真實 fills 流量 → 5/9 變 0。

---

## §8 PA Fix Plan §6 88 finding 與 verification 對齊摘要

| Finding 類別 | 5/8 PA 識別 | 5/9 verification |
|---|---|---|
| ✅ Verified-FIXED | 88 預期 | 74 真修（23%）|
| ⚠️ PARTIAL/source-only | -- | 66（21%）|
| ❌ NOT-FIXED | -- | 120（38%）|
| 🔄 REGRESSED | -- | 6（2%）|
| 🆕 NEW-ISSUE | -- | 53（17%）|
| **Total verification points** | 88 | **319** |

**結論**：12 audit + PA fix plan + 12 verification 三輪後，74 條真實 closed；剩餘 251 條（含 NEW）回流 active TODO 持續處理。

---

**歸檔者**：PM · 2026-05-09 UTC · 對應 active TODO v15 patch（移除已 verified-closed 細節 + 加 NEW-ISSUE）
