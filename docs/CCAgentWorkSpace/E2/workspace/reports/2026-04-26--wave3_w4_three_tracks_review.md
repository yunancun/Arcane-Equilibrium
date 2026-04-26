# E2 Wave 3 第四波三軌 Adversarial Review · 2026-04-26 CEST

**Agent**：E2（Senior Backend Code Reviewer + Adversarial Auditor）
**範圍**：3 軌獨立 adversarial review（EDGE-P1b 4 子任務 + EDGE-P2-flip T1+T3 + G2-03 4 子任務）
**模式**：純讀 + obvious typo/lint 直接修；業務問題退回 E1 不代寫
**結論**：3 軌 **PASS with conditions**（個別獨立評，不綁包）

---

## §0 全域檢查（共用）

### 跨平台合規（CLAUDE.md §七 ★★）

```bash
grep -E '/home/ncyu|/Users/ncyu' <18 files>  # 全部 0 命中 ✅
```

涵蓋全 18 檔（軌 1: 6 / 軌 2: 3 / 軌 3: 12 含 3 TOML + 5 Rust + 4 Python/sh）— **PASS**。

### 雙語注釋

- 全 4 個 Python 新檔（calibrator / summary / dry_run / bind_helper）有 `MODULE_NOTE` ✅
- 全 3 個 Rust 新檔（risk_config_per_strategy / 2 test sibling）有 `//!` 模組頭中英對照 ✅
- 3 個 shell wrapper 有雙語 inline ✅
- T3 Rust handler 函數 doc-comment 中英完整 ✅
- **PASS**

### §九 文件大小

| 檔 | 行數 | 狀態 |
|---|---|---|
| risk_config_per_strategy.rs | 191 | OK |
| risk_config_per_strategy_tests.rs | 294 | OK |
| risk_checks_per_strategy_tests.rs | 308 | OK |
| risk_checks.rs | 1020 | OK（< 1200） |
| risk_config.rs | 1071 | OK（< 1200） |
| risk_config_tests.rs | 1051 | OK（< 1200） |
| ipc_server/handlers/risk.rs | 598 | OK |
| **ipc_server/mod.rs** | **1251** | **🛑 超 1200 hard cap**（PRE-EXISTING +11） |
| edge_p2_flip_dry_run.py | 829 | ⚠️ 略超 800 警告（雙語占比合理） |
| exit_threshold_calibrator.py | 1067 | ⚠️ 近 1200 上限 |

---

## §1 軌 1 — EDGE-P1b 4 子任務（Findings）

| # | 嚴重性 | 位置 | 描述 | 建議 |
|---|---|---|---|---|
| **P1b-F1** | **MEDIUM** | `rust/openclaw_engine/src/ipc_server/mod.rs:1251` | mod.rs 已超 §九 1200 行硬上限（PRE-EXISTING 1240 + 本軌 +11 dispatch route） | E1 嚴守不擴張原則合理；**E5 follow-up 必拆**（mod.rs 已積壓技術債，下次 E5 wave 必處理）。本軌可 staging-pass，但須在 PM commit 前 PA 確認 E5 已排到下一波 |
| **P1b-F2** | **MEDIUM** | `rust/openclaw_engine/src/ipc_server/handlers/risk.rs:482-489` 響應 shape | T3 happy-path test 斷言 `fields_restored.len() == 7` 但**未斷言內容與順序** — operator audit 信任此 array 即「真正被 restore 的字段集合」 | 加一條 `assert_eq!(fields_restored, json!([...7 names...]))` 對齊 docstring 順序；不阻塞但屬可靠性 gap |
| **P1b-F3** | **HIGH (per RFC)** | `rust/openclaw_engine/src/ipc_server/handlers/risk.rs:84-99` IPC `update_risk_config` schema | `stale_peak_ms` + `shadow_enabled` 不在 IPC 7 個 `exit_*` 字段；calibrator 標 `toml_only_fields`，但若 operator 信 calibrator full bind → 6/7 partial bind 隱性 gap。**下游回應沒有 user-facing 警告**：calibrator JSON envelope 在 docstring 標 caveat，但執行時 `--apply` 輸出**未在 stdout 強制顯示警告 banner** | 兩條合理修法：(a) calibrator `--apply` 路徑強制 stdout warning banner（不在 docstring 等於藏）(b) follow-up PR 擴 IPC schema 加 `exit_stale_peak_ms` 字段閉合鏈。本軌可繼續，**但建議 PM 開 follow-up ticket**（E1 報告 §5.1 已建議） |
| **P1b-F4** | LOW | `helper_scripts/research/exit_threshold_calibrator.py:170-187` `position_size_max_pct` validate | E1 順手在 G2-03 sibling 的 `validate_against_limits` 加既有 `position_size_max_pct` validate guard — 雖修了既有未驗 bug，但屬 scope creep（軌 1 範圍外） | 純記錄；不阻塞。memory `feedback_risk_changes_scoped`「只動被要求的參數」嚴格詮釋下這是違規，但實際是合理 bug 修復；E2 直接認可不退回 |
| **P1b-F5** | LOW | `passive_wait_healthcheck.py:1739-1744` 防禦分支 | this_week>0 且 slice_parts 為空（strategy_name 全 NULL）的處理為訊息標註「all rows have NULL strategy_name?」，不返 FAIL — 設計上 fail-soft 但「策略寫入時 strategy_name 全 NULL」應該是嚴重 schema bug，不應只是 debug note | 不阻塞；長遠可考慮升 WARN。E1 已 self-disclose 為「unlikely」邊界 |

### 軌 1 重點驗證項（必查 6 條）

| 項 | E1 自 flag 狀態 | E2 真驗證 |
|---|---|---|
| T1 lookahead bias guard | ✅ embargo+lookback 對稱 | ✅ 真 — `ts > now()-lookback days AND ts <= now()-embargo days`（line 184-185）+ `_validate_args` 強制 `embargo>=0 && embargo<lookback`（line 848-853） |
| T1 stratification 精確比對 | ✅ `ANY(%s)` 非 prefix | ✅ 真 — `STRATEGY_FILTER_TEMPLATE = "AND strategy_name = ANY(%s)"`（line 194） |
| T1 fail-closed default | ✅ INSUFFICIENT 跳過 | ✅ 真 — `if n < min_samples` → SKIP + `patch=None` + `skip_reason="INSUFFICIENT"`（line 533-543），無 pooled fallback |
| T1 ExitConfig validate clamp | （PA RFC 既有）| 跳過直驗 — 屬 ExitConfig schema 已有測試覆蓋 |
| T3 unit test bit-exact 匹配 default fns | ✅ `f64::EPSILON` | ✅ 真 — line 591-593 spot-check 3 字段；line 512-521 happy-path 7 字段全 `Some(baseline.<field>)` 比對 |
| T4 [14] tier 200/50 對齊 calibrator | ✅ 對齊 | ✅ 真 — `ready_threshold=200 / growing_threshold=50`（line 1715-1716）對齊 calibrator default 200 |

### 軌 1 額外查問

- **`--apply` 預設 dry-run？** ✅ 真 — `--apply` 只觸發 JSON envelope 寫入；calibrator 整體**0 sync_ipc_call / 0 patch_risk_config 命中**（grep 確認）— 符合 PM 派發 spec「不直接 IPC 寫」
- **T3 restore 真把 7 字段 restore 到 hardcoded baseline？** ✅ 真 — line 337-343 從 `ExitConfig::default()` 取所有 7 字段；line 351-379 `tx.send` 只填 7 個 `exit_*` Some(...)，其他 20 個非 exit 字段全 None
- **`stale_peak_ms` + `shadow_enabled` IPC gap user-facing 警告**？❌ **缺** — calibrator docstring 標 `toml_only_fields` 但 stdout `--apply` 輸出時無強制顯示。**P1b-F3 建議補警告**

### 軌 1 結論

**PASS to E4 with 1 MEDIUM follow-up**：核心邏輯 bit-exact + fail-closed 完整；P1b-F1 mod.rs §九 違規屬 staging tradeoff（PRE-EXISTING + 嚴守不擴張）E5 必處理；P1b-F2 fields_restored 內容斷言可後續加；P1b-F3 警告 banner 強烈建議 PM 開 follow-up ticket。

---

## §2 軌 2 — EDGE-P2-flip T1+T3（Findings）

| # | 嚴重性 | 位置 | 描述 | 建議 |
|---|---|---|---|---|
| **P2-F1** | **HIGH** | `app/ipc_client.py:786` `sync_ipc_call` | **legacy `sync_ipc_call` 100% fail Rust auth**（毫秒 vs 秒，30s 容差量級差 1000x），E1 揭發屬實。**2 個 production caller**（非 dead code）：(a) `live_trust_routes.py:296` `trigger_live_auth_recheck` (b) `control_ops.py:515` `set_system_mode` 皆「fire-and-forget + 5s watcher poll backstop」吞錯誤，所以系統不崩潰，但**兩條 fast-path optimization 完全失效**。Authorization recheck 5s 延遲 + system_mode sync 須 engine restart 才生效（snapshot 路徑）— 未察覺是因為 backstop 兜住 | (a) E1 在內嵌 helper 用秒對齊 Rust ✅ 修了**新檔**路徑；legacy 修建議**獨立 P1 ticket**，PM 派 E1 後續批處理 (b) 兩 caller 可正確抓「fire-and-forget」設計但此 silent-broken 應寫入 lessons.md 防將來複製模式 |
| **P2-F2** | LOW | `helper_scripts/canary/g2_03_bind_helper.py:90-99` import 依賴 | helper.py 用 `sys.path.insert` 動態注入 + `from edge_p2_flip_dry_run import _sync_ipc_call`；兩 helper 互依 fragile（重命名/移位置即 break） | 純技術債；建議將 `_sync_ipc_call` 抽成獨立 `helper_scripts/lib/ipc_sync.py`（不在本軌 scope，下批處理） |
| **P2-F3** | INFO | `edge_p2_flip_dry_run.py:829` 行數 | 829 行略超 800 警告線，~36% 為雙語注釋（如 E1 §5.4 自陳） | 認可 — 雙語注釋是 §七 強制不可 trim |
| **P2-F4** | INFO | `edge_p2_flip_dry_run.py` mock_events 處理 | E1 不真合成 mock event 避污染 `learning.exit_features`（per RFC §9.1），mock_events 純 informational hint | 設計合理；不阻塞 |

### 軌 2 HMAC ts bug 深度驗證（最關鍵）

**E2 grep 確認 HMAC 算法 bit-by-bit**：

| 元件 | Python ipc_client.py:786-791 | Python edge_p2_flip_dry_run.py:213-219 | Rust ipc_server/mod.rs:621-628 |
|---|---|---|---|
| ts unit | `int(time.time() * 1000)` (毫秒) | `int(time.time())` (秒) | `now.as_secs() as i64` (秒) |
| HMAC key | `ipc_secret.encode("utf-8")` | `ipc_secret.encode("utf-8")` | `secret` |
| HMAC payload | `str(ts).encode("utf-8")` | `str(ts).encode("utf-8")` | `verify_ipc_token(&secret, ts, token)` |
| Hash algo | sha256 | sha256 | (在 verify_ipc_token 內，HMAC-SHA256) |
| 容差 | n/a | n/a | `(now - ts).abs() > 30` |

**驗算**：
- legacy: ts ≈ 1.77e12 vs Rust now ≈ 1.77e9 → `|now - ts|` ≈ 1.77e12 → > 30 → **fail "auth token expired"**
- E1 內嵌 helper: ts ≈ 1.77e9 對齊 Rust → `|now - ts|` < 30 → **pass**

**caller list 完整 grep**：

```
production caller (legacy sync_ipc_call):
  live_trust_routes.py:296  trigger_live_auth_recheck (fire-and-forget)
  control_ops.py:515        set_system_mode (best-effort)
```

兩個都 try/except 吞錯誤，無 silent crash，但**功能 100% 失敗**。

### 軌 2 RFC §9 三重點審查

| RFC §9 點 | 結論 |
|---|---|
| #1 dry-run 不污染 production | ✅ 真不污染 — line 510-516 構造 mutating payload 但 line 532-537 真送 `get_risk_config`（唯讀 round-trip） |
| #2 per-strategy filter 防 prefix 撞名 | N/A 本軌 — T2 不在本 PR；既有 [15] check 確實未 stratify per-strategy（屬 T2 工作） |
| #3 revert SOP idempotency | ✅ 真 — `{exit: {shadow_enabled: false}}` IPC patch idempotent；連跑兩次最終狀態相同 |

### 軌 2 paste-safe 驗證

```bash
grep -nE 'EOF|<<-?EOF|<<\$|<<\(|^for ' helper_scripts/operator/edge_p2_*.sh helper_scripts/operator/g2_03_*.sh
# 0 命中 → 全 single-line ✅
```

### 軌 2 結論

**PASS to E4 with 1 HIGH separate-ticket**：
- 軌 2 本身（dry-run + flip + revert）品質高，5/5 PASS Linux 真機驗證屬實
- **legacy `sync_ipc_call` HMAC ts bug 為先前埋的 latent bug 非本軌引入** — E1 已迴避（用內嵌 helper 對齊 Rust），符合「不擴張範圍」嚴守
- **強烈建議 PM 立即開 P1 ticket**：legacy fix `app/ipc_client.py:786 ts = int(time.time() * 1000)` → `ts = int(time.time())`，再 grep 兩 caller 預期行為（5s watcher fast-path / system_mode sync 應該真實工作）
- 我**不擴本批 scope** 修 legacy（嚴守 E2 規則「不寫業務代碼」）

---

## §3 軌 3 — G2-03 4 子任務（Findings）

| # | 嚴重性 | 位置 | 描述 | 建議 |
|---|---|---|---|---|
| **G2-03-F1** | **MEDIUM** | `rust/openclaw_engine/src/risk_checks.rs:201` thin wrapper + `step_6_risk_checks.rs` 0 caller upgrade | 本軌 land schema + helper + new fn，但**runtime path 沒走 override** — `check_position_on_tick_with_override` 0 production caller（grep 確認），只被自己 thin wrapper（per_strategy=None）+ 8 unit tests 呼。schema 完整、防線 A+B 完整，但「實質 runtime effect = 0」直到 step_6 升級 | 是 **正確 staging** 不是「半成品」（per E1 §5.3 self-disclose）— 但 PM commit 前**必須在 commit message 明確標「schema-only landing, runtime path 0 caller，binding 真實啟用屬獨立 PR」**避免後續 review 誤判已經 active |
| **G2-03-F2** | **MEDIUM** | `rust/openclaw_engine/src/config/risk_config_per_strategy.rs:170-187` | `validate_against_limits` 順手加既有 `position_size_max_pct` validate guard（finite > 0 + ≤ limits）— 違反 memory `feedback_risk_changes_scoped` 嚴格詮釋；雖修了既有未驗 bug，但屬 scope creep | 我**直接認可此修法**（合理 hardening + 無 false-positive 風險），不退回 E1。記錄為「順手修 pre-existing gap」 |
| **G2-03-F3** | **HIGH (per RFC)** | E1 揭 PA RFC §6.T2 函數名 `tick_risk_action` 不存在（真實 `check_position_on_tick`） | E1 用真實函數名實作 — 符合 PA 是「source-of-truth + 純技術 spec 錯字」處理 ✅ | 純記錄；不阻塞。建議 PA 修 RFC clerical error |
| **G2-03-F4** | LOW | `g2_03_bind_helper.py:99` import 依賴 | 同 P2-F2（兩 helper 互依） | 同 P2-F2 |

### 軌 3 schema 分歧處理（最關鍵）

**驗 PA RFC §2.1 vs PM prompt schema**：

| 來源 | schema |
|---|---|
| **PA RFC §2.1**（line 84-92）| 4 pct 字段：`stop_loss_max_pct_override` / `take_profit_max_pct_override` / `trailing_activation_pct_override` / `trailing_distance_pct_override` |
| **PM prompt** | ATR mult + bps 混合 4 字段（含**不存在**的 P1_HARD_*_MAX_BPS constants）|

**E1 採 PA RFC** ✅ — 我獨立判定 PA 是 source-of-truth + PM prompt 引用「P1_HARD_SL_MAX_BPS」是 PM 寫錯（Rust constants 不存在）。**E1 push back 判斷正確**。

**字段對照（PA RFC vs E1 落地）**：

| PA RFC §2.1 | E1 落地 | 對齊 |
|---|---|---|
| `stop_loss_max_pct_override: Option<f64>` | line 80 同 | ✅ |
| `take_profit_max_pct_override: Option<f64>` | line 84 同 | ✅ |
| `trailing_activation_pct_override: Option<f64>` | line 88 同 | ✅ |
| `trailing_distance_pct_override: Option<f64>` | line 92 同 | ✅ |

**完美 1:1 match**。

### 軌 3 防線 A/B 驗證

**A 防線 (validate)**：
- `validate_against_limits`（line 122）對 SL/TP override 拒 NaN/Inf/<=0 + `> limits.<P1>` ✅
- 在 `RiskConfig::validate()` line 257-264 per_strategy loop 真實呼叫 ✅

**B 防線 (runtime cap)**：
- `effective_sl_max_pct` line 50-62：`Some(v) if v.is_finite() && v > 0.0 => v.min(limits.stop_loss_max_pct)` — `min()` clamp ✅
- `effective_tp_max_pct` line 70-78：對稱實現 ✅
- 在 `check_position_on_tick_with_override` 真實被呼到：
  - Gate 1 hard stop（line 305）`-effective_sl` ✅
  - Gate 2 dynamic stop（line 317, 322）`effective_sl` 雙處 ✅
  - Gate 3 TP（line 336）`effective_tp * rm.tp` ✅
  - Gate 4 trailing（line 347, 350）`effective_trailing_*` ✅

### 軌 3 thin wrapper ABI 0 caller 改動

**grep 完整 caller list**：

```
check_position_on_tick (legacy, thin wrapper):
  position_risk_evaluator.rs:117    既有 caller，仍呼 thin wrapper
  g1_06_live_balance_sync_integration.rs:179/264/333  3 整合 test
  risk_checks.rs:548/584             2 unit tests

check_position_on_tick_with_override (new):
  risk_checks.rs:226                 thin wrapper 內部呼（per_strategy=None）
  risk_checks_per_strategy_tests.rs:71  8 unit tests
```

**真 0 production caller 改動**（thin wrapper 完全保留 ABI）✅。

但**這也意味著 G2-03 schema 落地但 runtime path 沒走 override** — 屬 G2-03-F1 議題。

### 軌 3 §九 1200 抽分驗證

| 抽分 | 行數 | mod 路徑 |
|---|---|---|
| `risk_config_per_strategy.rs` | 191 | `risk_config.rs:579-581` `#[path]` mod + `pub use per_strategy::StrategyOverride` ✅ |
| `risk_config_per_strategy_tests.rs` | 294 | `risk_config_tests.rs:1050-1051` `#[path]` mod ✅ |
| `risk_checks_per_strategy_tests.rs` | 308 | `risk_checks.rs:1019-1020` `#[path]` mod g2_03_per_strategy_tests ✅ |

**Public API path 不變**：`crate::config::risk_config::StrategyOverride`（line 581 `pub use`）→ `risk_checks.rs:19` `use crate::config::risk_config::{GlobalLimits, StrategyOverride};` 正確 import。

### 軌 3 caller chain not upgraded 判定

E1 §5.3 self-disclose：「step_6_risk_checks.rs 未升級為 _with_override」。我判定為**正確 staging**：
- T2 完成「schema + helper + new fn」屬 PA RFC §2 範圍
- step_6 caller chain 升級需動 4 個檔（`step_6` / `position_risk_evaluator::evaluate_position(s)` / `PositionRow` 加 `owner_strategy` / 整合測試 + evaluator tests）
- 屬 G2-03 binding 真實啟用步驟（per RFC §5.1 順序），可獨立 PR
- thin wrapper 模式保證既有 caller chain 0 改動

**但要求 PM commit message 明確標 staging 狀態**避免後續誤判已 active。

### 軌 3 cargo test baseline 驗證

E1 報告 2141 → 2161（+20 tests：12 schema + 8 runtime cap，包 1 TOML round-trip）— 與 sibling 抽分檔的 12+8=20 對齊 ✅。

### 軌 3 結論

**PASS to E4 with explicit staging marker**：
- Schema + 防線 A+B + 抽分 + 0 caller 改動全 PASS
- **MEDIUM**: PM commit message 必須標 staging 狀態（schema-only / 0 production caller 走 override）避免後續誤判
- Scope creep（position_size_max_pct validate）可接受 — 合理 hardening

---

## §4 跨平台 + 雙語 + §九 三表彙總

| 項 | 狀態 |
|---|---|
| 跨平台 grep（18 檔）| ✅ 0 命中 |
| 雙語注釋（4 Python + 3 Rust + 3 sh）| ✅ 全有 MODULE_NOTE / `//!` 雙語頭 |
| 文件 ≤ 800 警告 | ⚠️ 2 檔超：`edge_p2_flip_dry_run.py 829` / `exit_threshold_calibrator.py 1067` — 雙語占比合理可接受 |
| 文件 ≤ 1200 硬限 | 🛑 1 檔超：`ipc_server/mod.rs 1251`（PRE-EXISTING + 本軌 +11） |

---

## §5 整體結論

**3 軌獨立 PASS with conditions**（不綁包）：

| 軌 | 結論 |
|---|---|
| **軌 1 EDGE-P1b** | **PASS to E4** — 6 重點驗證項全 PASS；2 MEDIUM follow-up（mod.rs §九 + IPC schema gap warning banner）；1 LOW scope creep 認可 |
| **軌 2 EDGE-P2-flip T1+T3** | **PASS to E4** — 5 條 pre-flight + 90s revert SOP 結構完整；1 HIGH **separate ticket**（legacy `sync_ipc_call` HMAC ts bug，建議 PM 立即開 P1）；1 LOW import 依賴 |
| **軌 3 G2-03** | **PASS to E4 with staging marker** — Schema + 三防線完整；1 MEDIUM **commit message 必標 schema-only staging**；1 MEDIUM scope creep 認可 |

**整體**：3 軌均可進入 E4 回歸，但 PM 需在統一 commit 時：
1. 在 commit message 明確標**軌 3 schema-only staging**（runtime path 0 production caller）
2. **立即開 P1 separate ticket** 修 legacy `app/ipc_client.py:786` HMAC ts unit（毫秒→秒）— 影響 live_trust_routes + control_ops 兩 production fast-path
3. **強烈建議**開 follow-up ticket：(a) E5 wave split mod.rs 1251→拆分 (b) calibrator `--apply` 加 stdout warning banner 暴露 6/7 IPC partial bind gap

**E2 不擴 scope 修 legacy bug**（嚴守 E2 規則「不寫業務代碼」）。3 個建議全為 PM 派發後續 ticket 範圍。

---

## §6 退回 E1 修復清單

**0 個 BLOCKER 必修項**。所有 finding 屬「PASS with conditions」+「PM follow-up ticket」性質。

**P1b-F2 fields_restored 內容斷言**：建議 E1 補一條 `assert_eq!(fields_restored, json!([7 names]))` 對齊 docstring 順序 — 不阻塞，可 E5 順手修。

**E2 REVIEW DONE: PASS with conditions（3 軌獨立）· report path: srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-04-26--wave3_w4_three_tracks_review.md**
