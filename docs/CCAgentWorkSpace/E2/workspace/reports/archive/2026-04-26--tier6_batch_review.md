# E2 Tier 6 Batch Review — 2026-04-26

## Scope

4 commits (`306b549..56104de`) covering 3 PM-dispatched parallel tasks (Tier 5 sign-off `f4c5bad` 後 follow-up wave):

| # | Commit | Task | Owner | Type |
|---|---|---|---|---|
| 1 | `306b549` | PA G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN A/B/C decision design (Track 2) | PA | docs only (+529 / -0) |
| 2 | `dd4d64a` | PA Tier 6 Track 3 PAPER-STATE-DUST-RESTORE-AUDIT design (recommend Option B) | PA | docs only (+442 / -0) |
| 3 | `d8385e6` | Tier 6 Track 1 4 LOW follow-ups quick-wins (G3-08-PHASE-1C-FUP-CHECK20-SYNC + EDGE-P1b-FUP-NEGATIVE-GUARD + TIER4-OBSERVER-LOW-1 + G3-07-FUP-PYTEST-MARK) | E1 | code (+407 / -60) |
| 4 | `56104de` | E1 memory append for Track 1 lessons | E1 | docs only (+35 / -0) |

Time-order verified: 306b549 (Track 2) 16:39 → dd4d64a (Track 3) 16:41 → d8385e6 (Track 1) 16:42 → 56104de (E1 memory) 16:46. Tracks dispatched in parallel; commits serialized. Tracks are **independent** (Track 1 = code polish, Track 2 = design RFC, Track 3 = design audit) — NOT cohesive.

## 8-Axis Audit Result

| Axis | Status | Notes |
|---|---|---|
| **A** 跨平台 (`/home/ncyu` / `/Users/[^/]+`) | **PASS** | 4/4 commits 0 hit (production + docs) |
| **B** 雙語注釋 (MODULE_NOTE / docstring / 中英對照) | **PASS** | T1 6/6 modified files 中英對照 + Tier 6 Track 1 marker / T2 PA RFC 中英 schema docstring / T3 PA design 中英 12 §; E1 memory.md 6 教訓條中英對照 |
| **C** 範圍嚴守 (PA design plan ↔ E1 changes) | **PASS** | T1 4 sub-tasks 邊界清晰（無互相干擾、無業務碼擴張）/ T2 純 PA design 不寫實作（PA 自我聲明「沒寫 Rust types.rs / tests.rs 任何實作代碼」）/ T3 純 PA audit 不動 paper_state/*.rs（PA 自我聲明 §10）|
| **D** SQL Guard (V### migration) | **PASS** | 0 new V### migration in batch (T3 推 Option B 純 SQL SELECT 無 mutation; T1 unchanged schema) |
| **E** Hot-path & architecture | **PASS** | T1 `update_risk_config` 加 negative-value guard 純 fail-fast in-process / T1 cron wrapper exit code 語意保留 / T1 [20] healthcheck 純讀無 IPC roundtrip / T2 全 design plan / T3 全 design audit |
| **F** Test coverage | **PASS** | T1 +6 unit tests `test_ipc_client_update_risk_config_unit.py`（負值 -1 / -1M / 邊界 0 / 正值 forward / omitted no-inject / error-message contract）E1 自驗 0.04s 全綠 / T1 conftest pytest_configure 註冊雙 marker 消除 PytestUnknownMarkWarning / T2/T3 純 design 不增 test |
| **G** PA design plan 對齊 | **PASS** | T1 4 ticket 與 TODO Backlog 描述對齊 / T2 PA RFC 結論對齊 Tier 5 T5.3-MED-1 finding（Option B Rust rename 對齊 Python SSOT）/ T3 PA audit 對齊 MIT §6 follow-up #1（restore 不重建倉位 + Bybit REST 邊角 vs runtime accumulation 區分）|
| **H** Pivot 對抗驗證 | **PASS** | T1 兩個 sub-task pivot 經獨立 source 驗證合理（見 §Pivot Validation）/ T3 PA push back MIT §6 #1 經 4 重 SSOT 驗證 100% 站得住腳（見 §Track 3 Push-back Validation）|

## Per-Task Audit

### Task 1: Track 1 4 LOW Follow-ups (`d8385e6` + `56104de`) — **PASS-with-LOW**

**Diff stats**: 6 files / +407 / -60 (code) + 1 file / +35 / -0 (E1 memory).

**Sub-task 1.1: G3-08-PHASE-1C-FUP-CHECK20-SYNC (helper_scripts/db/passive_wait_healthcheck/checks_derived.py +172 / -60)**:
- MODULE_NOTE 補 Phase 1C → Phase 2 沿革說明（commits 9120948 + f2ed286 引用）
- `check_h_state_gateway_freshness` docstring 重寫雙語含 Phase 2 invariant（version=1 + h_states ⊇ {h1, h3}）
- PASS-skip msg 從「Phase 1 dormant」改「env=0 dormant」對齊新語意（env=0 是設計上 dormant，與 phase 數字解耦）
- WARN 邏輯：原 `version != 0 or h_states or agent_states` → 改 `version != 1 or {'h1','h3'} - h_states.keys()` 用 set diff 顯示 missing；agent_states + extra h_states keys 視為 additive 成長 = PASS（Phase 3-4 friendly）
- **Set logic verified**：line 832-852 expected `{"h1","h3"}` - actual = missing；missing != {} 觸發 WARN；正確
- **Pre-existing 817 → 869 lines**（+52）— **800 警告區內 +52 屬技術債漸增**，但 < 1200 hard cap；對齊 Tier 5 T5.1-LOW-1 helpers.rs 1315 ACCEPT-with-FOLLOWUP 慣例

**Sub-task 1.2: EDGE-P1b-FUP-NEGATIVE-GUARD (program_code/.../app/ipc_client.py +24 / -0 + tests/test_ipc_client_update_risk_config_unit.py +194 NEW)**:
- `update_risk_config` 內 `exit_stale_peak_ms is not None` 區段前加 `if exit_stale_peak_ms < 0: raise ValueError(...)`
- 雙語 inline comment 解釋 fail-fast 動機（Rust serde error 不透明 vs Python 直接給 actionable 錯誤）+ Tier 6 Track 1 marker
- 6 unit tests 涵蓋：-1（基礎拒絕 + IPC call 不被觸發）/ -1_000_000（量級無關）/ 0（邊界接受）/ positive forward（5_000）/ omitted no-inject / error-message contract（含 "must be >= 0" / "got -42" / "Rust" 字眼）
- **Pre-existing 875 → 899 lines**（+24）— **800 警告區內 +24 屬技術債漸增**，但 < 1200 hard cap；同 ACCEPT-with-FOLLOWUP

**Sub-task 1.3: TIER4-OBSERVER-LOW-1 (helper_scripts/cron_observer_cycle.sh +17)**:
- L91-96 加雙路 echo log：observer 失敗時與成功時 都印 `Cron exit aggregation: OBSERVER_RC=$X BRIDGE_RC=$Y → exit $Z`
- cron exit code 語意嚴格不變（OBSERVER ≠ 0 → exit OBSERVER_RC；OBSERVER = 0 → exit BRIDGE_RC）
- 雙語 comment 強調「semantics unchanged but log surfaces full RC pair」+ Tier 6 Track 1 marker
- 96 lines, 文件大小無風險

**Sub-task 1.4: G3-07-FUP-PYTEST-MARK (tests/conftest.py +43 + tests/test_layer2_tools.py +17)**:
- conftest.py 加 `pytest_configure(config)` hook 註冊 `slow` + `e2e` markers，含 CI 用法範例（`-m "not slow and not e2e"` deselect）
- test_layer2_tools.py `TestCheckDerivativesE2E` 加 `@pytest.mark.e2e` decorator + 雙語 docstring 含 marker 註冊位置
- conftest 524 lines / test_layer2_tools 629 lines — 都 < 800 警告區

**Findings**:
- **LOW (T6.1-LOW-1)**: 兩檔 (`checks_derived.py` 869 / `ipc_client.py` 899) 都進 §九 800 警告區，pre-existing 817/875 + Tier 6 增 52/24。**ACCEPT-with-FOLLOWUP** 對齊 Tier 5 T5.1-LOW-1 helpers.rs 1315 + Tier 3 G9-02-MED-1 ws_client.rs 1227 慣例（hot-path/typed-wrapper surgical change，sibling pattern 可延 G5 refactor wave 帶走）。建議 PM 開 `T6-FUP-WARN-ZONE-FILES-SPLIT`（~1d，Wave 4 G5 refactor，含 checks_derived.py + ipc_client.py 兩檔對齊既有 sibling pattern）。
- **PASS** on cross-platform / 雙語 / SQL Guard / Test coverage / cron 語意保留 / set 邏輯正確。

### Task 2: Track 2 PA G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN Decision (`306b549`) — **PASS**

**Diff stats**: 2 files / +529 / -0 (PA memory.md +18 + workspace report +511).

**8-section design audit**：
1. **§1 背景** — 引用 Tier 5 T5.3-MED-1 finding 完整對齊（Python 10 keys vs Rust 7 fields 0/7 對齊 / Phase 3 silent regression latent）
2. **§2 現況對照表** — Side-by-side schema mismatch 表 + 字面差異本質拆 A 命名 drift（cosmetic）+ B 缺欄（語意）+ Test 阻力盤點（30+ assertion 直引）
3. **§3-§5 Option A/B/C 各 5 維度評估** — 影響範圍 / 語意正確性 / Phase 3 affordability / Backward compat / 執行工時
4. **§6 Recommend Option B** — Rust rename + 加 3 field 對齊 Python，附決策矩陣 5/5 vs 1/5 / 3/5
5. **§7 執行 prompt template** — 完整 ready-to-deploy 給下次 session E1（含 cargo test 驗證命令）
6. **§8 Phase 3 dependency check** — 強依賴/弱依賴/強依賴三檔對應 Phase 3 sub-task A/B/C
7. **§9 治理對照** — CLAUDE.md §二 16 根原則 + §四 5 項 live 硬邊界
8. **§11 教訓備忘** — 5 條 PA 草稿 schema technical debt / Phase 1 stub fetcher 隱藏 schema bug / 等

**Schema mismatch 獨立驗證**：
- Rust `H3RouteStats` (`h_state_cache/types.rs:75-92`) 確認 7 fields：`l1_9b / l1_27b / l1_5 / l2 / cache_size / cache_hit / cache_expired` ✅ PA 對齊
- Python `_routing_stats` (`model_router.py:114-124`) 確認 9 keys：`total_routes / l1_9b_count / l1_27b_count / l1_5_count / l2_count / budget_denied_count / l2_cache_hit / l2_cache_expired / l2_cache_stored` + `cache_size` (live snapshot at line 471) = 10 keys total ✅ PA 對齊
- 0/7 alignment ✅ confirmed
- StrategistAgent 共用 `l2_cache_hit/expired/stored` keys (`strategist_agent.py:206-208`) ✅ confirmed (Option A 牽連改 StrategistAgent stats dict 是真實風險)
- Rust `H3RouteStats` 0 hot-path consumer ✅ confirmed (`grep -rn` in `rust/openclaw_engine/src/` 排除 `tests`/`types.rs`/`mod.rs` = 0 result，PA Option B 「improvement window」claim 站得住腳)

**Option B 真實 trade-off**：Rust ~25 LOC 內部 vs Python ~50+ LOC ecosystem break vs C 永久 dual-vocab maintenance — PA 推 B 理由完整且每選項有具體依據。**Cross-env 安全性 + backward compat + Phase 3 affordability** 三軸 B 全勝。

**Findings**: 0 BLOCKER / 0 HIGH / 0 MEDIUM / 0 LOW. Pure design RFC 純設計判斷，依 hard rule 「不退回 cosmetic / 設計 trade-off 差異」E2 不評選項 A/B/C 之間哪個更好（PA design judgment）。Recommend B 與 5/5 評分矩陣對齊；E2 接受 Option B 為 PM 推進路徑。

### Task 3: Track 3 PA PAPER-STATE-DUST-RESTORE-AUDIT (`dd4d64a`) — **PASS**

**Diff stats**: 1 file / +442 / -0 (workspace report only; PA memory append 在 dd4d64a 之外缺，作為 LOW finding 提及見下).

**12-section audit 結構**：
1. §1 背景 + MIT §6 follow-up #1 重述 + 與 EXIT-FEATURES-WRITER-BUG-1-FIX 關係
2. §2 現況路徑分析（restore 流程 7-step trace + 為何 0.1 dust 沒被 evict 的 root cause 鏈）
3. §3-§5 Option A/B/C 各 modular 評估
4. §6 Recommend Option B + cross-env 安全性矩陣 + 殘留風險
5. §7 執行 prompt template + healthcheck [19] SQL spec
6. §8 不確定 / 追加 audit follow-up（5 點）
7. §9 治理對照 + §10 沒做的事 + §11 教訓備忘 + §12 報告索引

**Track 3 Push-back Validation**（最關鍵）：

PA 對 MIT §6 follow-up #1 的 push back 共 3 個關鍵 claims，**全部獨立驗證 100% 站得住腳**：

| Claim | PA 來源 | E2 獨立驗證 |
|---|---|---|
| `restore_from_db` **不重建倉位** | §2.1 step 1-3 + 「關鍵事實」 | `fill_engine.rs:220-243` 確認只 SELECT 3 SCALAR counters（`SUM(fee)/SUM(realized_pnl)/COUNT(*)`），呼 `apply_restored_counters(row.0, row.1, row.2)` 不觸 `self.positions` ✅ |
| `paper_state_checkpoint` 表 **schema 只 4 scalar 欄無倉位欄** | §2.1 step 3 | `sql/migrations/V018__paper_state_checkpoint.sql:30-39` 確認 4 columns: `engine_mode (PK) / peak_balance / session_start_ts / updated_at` — 無 positions / qty / entry_price 等欄 ✅ |
| `import_positions` 才是**倉位唯一來源** | §2.1 step 4 | `fill_engine.rs:44-75` 確認首行 `self.positions_clear()` + 從 seed_positions tuple loop insert（line 48 guard `entry_price <= 0.0 continue` 對齊 PA 邊角分析）✅ |
| `reduce_position` 0.1 dust **不會被刪** | §2.2 root cause #1 | `fill_engine.rs:366-387` 確認 line 377 `if pos.qty < 1e-12` 才 remove；0.1 >> 1e-12 故 dust 持續累積 ✅ |
| Real-strategy owner **不進 retriage** | §5.2 cross-env 安全性 (C 風險) | `owner_attribution.rs:112` 確認 `if !SYNTHETIC_OWNER_LABELS.iter().any(|l| *l == current_label) → fast-path NoOp` ✅；Option C 必須主動 flip 才能讓 dust 進 retriage = PA 引入的真實 risk |

**Cross-env 安全性矩陣**：A FAIL on live（誤刪 user 真實小單 0.5 USD ATM 對沖 / scalper micro position）/ B 0 risk all envs / C MEDIUM live（卡 frozen + ownership flip）— PA 對 Operator hard requirement「不可建議任何會誤刪 live user 真實小單的方案」反應正確 + 對 Option C 風險（real-strategy owner_strategy flip → DUST_FROZEN 後即使 qty/price 上升回 above min_notional 也不會升級回原 owner，strategy 歸因失真）分析具體可信。

**Healthcheck [19] SQL 正確性**：
- SQL 區分 `gate1_fired_count = COUNT FILTER realized_pnl=0`（純 dust spiral fill）vs `partial_reduce_real_count = COUNT FILTER realized_pnl != 0`（partial reduce 有真實 PnL）
- EXIT-FEATURES-FIX `af48ee1` 後 fast_track Gate 1 skip **不寫 fill**（Gate 1 整個 skip）→ 預期 `gate1_fired_count = 0` 是健康基準
- 所以 `gate1_fired_count > 0` 即異常 alarm，靈敏度高 + 跨 env 安全（純 SELECT，0 mutation，fail-soft on PG unavail）
- `engine_mode IN ('demo','live','live_demo')` 對齊 CLAUDE.md `engine_mode 標籤 live_demo 升級` memory + paper 排除（per `feedback_demo_over_paper_for_edge`）
- Threshold 設定（0=PASS / 1-10=WARN / >10 OR distinct_dust_symbols >= 3=FAIL）合理；建議 PA 在 §7.4 ticket scope 內加「first 5 min grace period 防 false WARN」（PA §6.2 (4) 自承的 caveat 已寫入 follow-up）

**Findings**:
- **LOW (T6.3-LOW-1)**: PA memory.md 在 dd4d64a 內**未追加** Tier 6 Track 3 報告索引（對照 Track 2 `306b549` 同 commit 內 PA memory +18 行登記索引）。應在後續 PA wave 補上對齊 §12 「報告索引追加」表格條目「2026-04-26 PAPER-STATE-DUST-RESTORE-AUDIT design audit | workspace/reports/2026-04-26--paper_state_dust_restore_audit.md」。**ACCEPT-with-FOLLOWUP**（不退回 PA）— 純記錄性質，建議 PM 開 `T6-FUP-PA-MEMORY-INDEX-SYNC`（5min，下次 PA wave 順手補）。

## Pivot Validation（Track 1 兩個 sub-task pivot 對抗審驗）

### Pivot 1: TIER4-OBSERVER-LOW-1 「保留 BRIDGE_RC 在 final log」 vs Tier 4 finding L-1 描述

**Tier 4 finding L-1 原文**（`tier4_batch_review.md:309`）：
> OBSERVER_RC ≠ 0 時 `exit OBSERVER_RC` 直接 return，BRIDGE_RC 細節不在 wrapper exit code（log 行有資訊）

**TODO Backlog 描述**（`TODO.md:484`）：
> `cron_observer_cycle.sh:76-79` BRIDGE_RC overshadow at exit 是 cosmetic（不影響 cron exit code propagation 正確性）

**E1 pivot 描述**（commit msg + memory.md 教訓 1）：
> PA prompt 提到「BRIDGE_RC overshadow at exit」是 cosmetic，但實際讀檔發現原邏輯（OBSERVER_RC ≠ 0 → exit OBSERVER_RC, else exit BRIDGE_RC）是**功能正確**的；真正的「cosmetic gap」是雙段都失敗時 BRIDGE_RC 從 final log 中遺失。Pivot 為「保留 BRIDGE_RC 在 final log」而非「修不存在的 overshadow bug」。

**Adversarial 反問**：
- Q1：原 cron_observer_cycle.sh 的 L62-67 中 `[$TS] Auto-bridge complete (exit=$BRIDGE_RC)` / `Auto-bridge FAILED (exit=$BRIDGE_RC)` 已經在 log 中，BRIDGE_RC 真的「從 log 中遺失」嗎？
  - **A**：嚴格來說 BRIDGE_RC log 行 L62-66 確實會印；但 **postmortem triage 在 OBSERVER 也失敗時 grep `Cron exit aggregation` final 行只看到 OBSERVER_RC**，需 grep 不同字串才能對齊 BRIDGE_RC。E1 修法把兩 RC 合到 **同一 final aggregation line** 給 postmortem 一目了然，是真實 UX 改善。
- Q2：cron 看到的 exit code 還是只有一個 RC（OBSERVER 失敗時 propagate OBSERVER_RC，OBSERVER 成功時 propagate BRIDGE_RC），E1 修法真有解決 root cause 嗎？
  - **A**：E1 明示「cron exit code 語意不變」，且 Tier 4 L-1 自己也說「P3 cosmetic — cron 看到 wrapper non-zero 已足，BRIDGE 細節可從 log 找」。所以 root cause 本就是 **postmortem readability 而非 cron alerting**；E1 修法直接解 readability，不擾動 cron 語意。

**結論**：Pivot 是更精準的 fix surface 描述，**不是修錯 bug**。E1 main commit msg + memory.md 教訓 1 的 pivot 描述準確（「PA prompt 為 hint 而非 authoritative」教訓對 multi-agent workflow 有累積價值）。**ACCEPT pivot**.

### Pivot 2: EDGE-P1b-FUP-NEGATIVE-GUARD 「補首個 Python-side guard」 vs PA 提「鏡射既有 7 guard」

**TODO Backlog 描述**（`TODO.md:463`）：
> Python `ipc_client.py` patch_risk_config wrapper 缺 `exit_stale_peak_ms` negative value guard（**既有 design pattern**）

**E1 pivot 描述**（commit msg + memory.md 教訓 2）：
> PA prompt 「7 個 exit_* 欄位都有 negative-value guard」實證為誤：實際 grep 顯示 ipc_client.py 只有 `exit_stale_peak_ms`（第 8 個）暴露在 typed wrapper，前 7 個 percentile 欄位走 raw `self.call("update_risk_config", params=raw_dict)` 無 Python 端 guard。Pivot 為「為 `exit_stale_peak_ms` 補上首個 Python-side guard」。

**Adversarial 反問**：
- Q1：PA prompt 的「既有 design pattern」claim 真的錯了嗎？
  - **A**：grep `ipc_client.py:467-487` 確認 typed wrapper 只暴露 `exit_stale_peak_ms`（第 8 個），且 doc comment 明示「the 7 `exit_*` percentile fields wired in Rust IPC since EDGE-DIAG-1-FUP-IPC are NOT exposed on this typed wrapper」。所以 ipc_client.py 中**真的沒有「既有 7 guard pattern」**可鏡射。
- Q2：那 7 個 percentile 欄位有沒有任何「producer-side guard」？
  - **A**：grep `helper_scripts/research/exit_threshold_calibrator.py` 確認在 `compute_exit_thresholds()` 中 percentile 計算後**有 producer-side clamping**（如 line 349-358 `floor at 0` / line 376 `clamped to >=0 per validate()` 等），所以 calibrator 端產生的 percentile 永遠 >= 0，從不會 hit IPC 帶負值。但這是 **producer-side defense**，不是 ipc_client 端 guard。E1 為新典型 (typed wrapper exit_*) 補的 Python-side guard 是 ipc_client 端**第一個** — pivot 描述「補首個 Python-side guard」精確。
- Q3：未來若 7 個 percentile 也搬到 typed wrapper，會跟著本 pattern 加 guard 嗎？
  - **A**：E1 memory.md 教訓 2 自己說「未來 percentile 欄位走 typed wrapper 可鏡射本 pattern」— 已留下 pattern 模板。E2 接受 forward-looking design。

**結論**：Pivot 是對 PA prompt 細節漂移的精準修正，**不是修錯需求**。E1 grep + 讀 doc comment 主動驗證 PA 的「既有 design pattern」claim，發現 PA 描述漂移（「既有 7 guard」實際 = 「7 個 producer-side clamping」+「typed wrapper 0 guard」），並 pivot 到正確 fix surface。**ACCEPT pivot**. 6 unit tests 設計嚴謹（涵蓋邊界 0、量級無關、IPC call 不觸發、forward 正確、omitted 不注入、error message 含 actionable 字眼）。

## Summary Table

| Task | Verdict | LOW | MEDIUM | HIGH | CRITICAL | Action |
|---|---|---|---|---|---|---|
| **T6.1 Track 1 (4 LOW + memory)** (d8385e6+56104de) | **PASS-with-LOW** | 1 (T6.1-LOW-1 兩檔進 800 警告區漸增) | 0 | 0 | 0 | PASS to E4 / QA / PM Sign-off |
| **T6.2 Track 2 (H3 schema design)** (306b549) | **PASS** | 0 | 0 | 0 | 0 | PASS to PM 採納 → 派 next-session E1 落地 |
| **T6.3 Track 3 (dust audit design)** (dd4d64a) | **PASS** | 1 (T6.3-LOW-1 PA memory.md 索引未同步追加) | 0 | 0 | 0 | PASS to PM 採納 + open T6-FUP-PA-MEMORY-INDEX-SYNC |
| **Total** | 4 commits | **2 LOW** | 0 MEDIUM | 0 HIGH | 0 CRITICAL | — |

## E2 自行修補（直接修，不退回 E1/PA）

僅明顯 lint / typo / 既有 dead import — 本批次 E2 未直接修任何代碼。

## 退回 E1/PA 修復清單（無）

無 RETURN — 0 BLOCKER / 0 HIGH / 0 MEDIUM finding。所有 LOW 屬技術債漸增 / 純 PA 記錄性遺漏，全 ACCEPT-with-FOLLOWUP。

## ACCEPT-with-FOLLOWUP（PM 開新 ticket，不退回原 owner）

1. **T6.1-LOW-1 兩檔 800 警告區漸增** — `checks_derived.py` 869 (pre-existing 817+52) + `ipc_client.py` 899 (pre-existing 875+24)。對齊 Tier 5 T5.1-LOW-1 helpers.rs 1315 + Tier 3 G9-02-MED-1 ws_client.rs 1227 慣例。建議 PM 開 `T6-FUP-WARN-ZONE-FILES-SPLIT`（~1d，Wave 4 G5 refactor 收尾，含兩檔 sibling pattern 對齊）。
2. **T6.3-LOW-1 PA memory.md 索引未同步追加** — `dd4d64a` 內未含 PA memory append（對照 Track 2 `306b549` 同 commit 內 +18 行登記索引）。建議 PM 開 `T6-FUP-PA-MEMORY-INDEX-SYNC`（~5min，下次 PA wave 順手補）。

## 最終推薦

- **Track 1 (4 LOW + memory)** — **PASS to E4 / QA / PM Sign-off**. 兩個 sub-task pivot 經獨立 source 驗證合理（pivot 1 = postmortem readability 真改善 / pivot 2 = 「既有 7 guard pattern」實證為誤後補首個 typed-wrapper guard），6 unit tests 嚴謹，cron exit code 語意保留，[20] healthcheck set-based invariant 設計 robust（Phase 3-4 friendly）。**LOW 屬 pre-existing 警告區漸增**, 不退回 E1。
- **Track 2 (H3 schema design)** — **PASS to PM 採納 + 派 next-session E1 落地**. PA RFC 8-section 結構完整，3-option 5-dim 評估各有具體依據，Option B 推薦理由 + 決策矩陣 5/5 vs 1/5/3/5 對齊，schema mismatch 0/7 alignment 經 4 點 SSOT (model_router.py / strategist_agent.py / types.rs / hot-path grep) 獨立確認。**§7 ready-to-deploy E1 prompt template** 可直接用於下次 session（30min ETA + cargo test 命令具體）。
- **Track 3 (dust audit design)** — **PASS to PM 採納 (Option B + healthcheck [19]) + open T6-FUP-PA-MEMORY-INDEX-SYNC**. PA push back MIT §6 follow-up #1 經 5 重 SSOT (fill_engine.rs:220-243 + V018 schema + fill_engine.rs:44-75 import_positions + fill_engine.rs:366-387 reduce_position + owner_attribution.rs:112) 100% 驗證站得住腳；cross-env 安全性矩陣（A FAIL live / B 0 risk / C MEDIUM live）+ Operator hard requirement 對齊正確；§7 healthcheck [19] SQL spec 跨 env 安全 + 靈敏度高（gate1_fired_count > 0 即 alarm）。

**E2 推薦 PM 採選項 B**（accept + follow-up tickets）— 理由：
- 0 BLOCKER / 0 HIGH / 0 MEDIUM finding；2 LOW 屬技術債漸增 + 純 PA 記錄性遺漏，全 ACCEPT-with-FOLLOWUP
- 對齊既往 Tier 3 G9-02-MED-1 / Tier 4 OBSERVER / Tier 5 T5.3 ACCEPT-with-FOLLOWUP 慣例
- 重派 review cycle 開銷 > 後續 wave 帶走 + memory.md 索引補追的成本
- Track 2 PA Option B 推薦邏輯完整 + Track 3 PA push back 完整證據鏈，PM 直接採納可加速 Phase 3 派發 (Track 2) + 落地 healthcheck [19] (Track 3)

**3 個 task 全綠 PASS to QA**（with 2 follow-up tickets for PM backlog）.

## Verification Commands Run

```bash
# §A 跨平台 grep (4 commits)
git -C /Users/ncyu/Projects/TradeBot/srv show 306b549 dd4d64a d8385e6 56104de | grep -E '(/home/ncyu|/Users/[^/]+)'
  → 0 hit (clean)

# §C QA dir 隔離
git -C ... show <each commit> --stat | grep -i "QA\|docs/CCAgentWorkSpace/QA"
  → 4/4 commits 0 hit

# Track 1 pivot 1 verify (TIER4-OBSERVER)
Read tier4_batch_review.md L309 → "OBSERVER_RC ≠ 0 時 exit OBSERVER_RC 直接 return，BRIDGE_RC 細節不在 wrapper exit code（log 行有資訊）"
Read TODO.md L484 → "cosmetic（不影響 cron exit code propagation 正確性）"
Read cron_observer_cycle.sh post-d8385e6 → exit code 語意不變 (L91-93 OBSERVER 失敗 exit OBSERVER_RC, L96 OBSERVER 成功 exit BRIDGE_RC)
  → pivot accepts: postmortem readability 改善 ≠ 修不存在的 bug

# Track 1 pivot 2 verify (EDGE-P1b-FUP-NEGATIVE-GUARD)
grep "exit_" ipc_client.py → only `exit_stale_peak_ms` typed-wrapper exposed; 7 percentile NOT exposed (per L474 doc comment)
grep "validate\|< 0\|>= 0\|raise" exit_threshold_calibrator.py → producer-side clamping in compute_exit_thresholds (L349-467)
  → pivot accepts: ipc_client.py 真的無「既有 7 guard pattern」可鏡射, exit_stale_peak_ms 是 typed-wrapper 第一個

# Track 2 PA RFC schema mismatch verify
grep -A 25 "pub struct H3RouteStats" types.rs → 7 fields confirmed (l1_9b/l1_27b/l1_5/l2/cache_size/cache_hit/cache_expired)
Read model_router.py L114-124 → 9 routing_stats keys + cache_size live snapshot = 10 total confirmed
grep -rn "H3RouteStats|h3\.l1_9b" rust/openclaw_engine/src/ excluding tests/types.rs/mod.rs → 0 hot-path consumer (Option B "improvement window" claim CONFIRMED)
grep "_routing_stats\|l2_cache_hit" strategist_agent.py:206-208 → confirmed StrategistAgent uses same L2 cache key names (Option A scope 風險 CONFIRMED)

# Track 3 PA push back 5-axis verify
Read fill_engine.rs:220-243 restore_from_db → only 3 SCALAR counter restore (PA claim 不重建倉位 CONFIRMED)
Read sql/migrations/V018__paper_state_checkpoint.sql:30-39 → 4 columns no positions (PA claim 4 欄無倉位 CONFIRMED)
Read fill_engine.rs:44-75 import_positions → first line `positions_clear()` then loop insert (PA claim 倉位唯一來源 CONFIRMED)
Read fill_engine.rs:366-387 reduce_position → L377 `if pos.qty < 1e-12` only removes near-zero (PA claim 0.1 dust 不刪 CONFIRMED)
Read owner_attribution.rs:112 → `if !SYNTHETIC_OWNER_LABELS.iter().any → fast-path NoOp` (PA Option C 風險 real-strategy owner_strategy flip CONFIRMED)

# §九 file size
wc -l 6 modified files
  → checks_derived.py 869 (>800 警告, pre-existing 817+52, T6.1-LOW-1)
  → ipc_client.py 899 (>800 警告, pre-existing 875+24, T6.1-LOW-1)
  → cron_observer_cycle.sh 96 (safe)
  → conftest.py 524 (safe)
  → test_layer2_tools.py 629 (safe)
  → test_ipc_client_update_risk_config_unit.py 194 (safe)

# Cargo / pytest baseline (no engine code changed)
4 commits 觸 0 Rust file → cargo lib baseline 2161 unchanged (verified by `git show --stat | grep -E "^\s+rust/|\.rs\s+\|"` = 0 result)
T1 pytest baseline: E1 自驗 6 new unit tests 0.04s 全綠 + 3 既有 ipc_client_hmac_ts_unit tests 不破 (memory.md 自陳)

# §B 雙語注釋
grep -c '中\|MODULE_NOTE\|Tier 6 Track' on each modified file
  → 6/6 modified Track 1 files have multiple bilingual markers + Track 6 marker
  → Track 2/3 PA workspace reports have full bilingual section structure
```

## End-of-Review Statement

`PASS to E4 / QA / PM Sign-off` for all 3 tracks (Track 1 + Track 2 + Track 3). E2 推薦 PM 採選項 B (accept + 2 follow-up tickets in backlog). 0 BLOCKER / 0 HIGH / 0 MEDIUM; 2 LOW are technical-debt-incremental + PA memory append omission, both ACCEPT-with-FOLLOWUP per established Tier 3-5 慣例.
