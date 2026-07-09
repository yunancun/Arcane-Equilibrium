# E1 — Wave 3 EDGE-P2-flip T1 + T3 Landing

**Date**: 2026-04-26 CEST
**Author**: E1 (Backend Developer)
**Scope**: PA RFC `2026-04-26--edge_p2_flip_sop_rfc.md` 子任務 P2-flip-T1 + P2-flip-T3（**不**含 T2）
**Status**: 待 E2 review → E4 regression → PM Sign-off

---

## 1. 任務摘要

PA RFC 推第三波 E1 派發 EDGE-P2-flip（Combine Layer `RiskConfig.exit.shadow_enabled` Phase 1a → Phase 2 翻轉）。PM 派發 T1 + T3，**T2 因與 EDGE-P1b T4 同檔（healthcheck.py [15] per-strategy stratification）衝突留下批處理**。

### T1: flip 前 dry-run smoke test
- **新檔**：`srv/helper_scripts/canary/edge_p2_flip_dry_run.py`（**829 行**，含雙語注釋）
- **功能**：5 條 pre-flight check（per RFC §3.1），不修改任何 production 狀態
- **輸出**：stdout markdown report + `$OPENCLAW_DATA_DIR/edge_p2_flip_dry_run.json` structured artifact
- **Exit codes**：0 = 全 PASS / 1 = 任一 FAIL / 2 = engine socket 缺失
- **Linux 真機驗證**：exit=0，5/5 PASS（real engine PID 1836245，shadow_enabled=False, ExitConfig schema 完整，IPC channel live）

### T3: manual flip + revert SOP shell wrappers
- **新檔 a**：`srv/helper_scripts/operator/edge_p2_flip.sh`（**283 行**）
  - 5 step：dry-run → confirm → IPC patch → verify → healthcheck [8]+[15]
  - operator 必須輸入 `yes` 才繼續（除非 `--skip-confirm`）
  - log 寫 `$OPENCLAW_DATA_DIR/edge_p2_flip.log`
- **新檔 b**：`srv/helper_scripts/operator/edge_p2_revert.sh`（**208 行**）
  - 3 step：IPC patch revert → verify → RCA pointer
  - **無**確認提示（緊急回滾必須立即發生）
  - log 寫 `$OPENCLAW_DATA_DIR/edge_p2_revert.log`
- **shell paste-safe**：純 single-line / 無 heredoc / 無多行 for；複雜 IPC 邏輯走 inline `python3 -c ...` 委派 Python helper

---

## 2. 修改清單

| Path | 動作 | 行數 | 說明 |
|---|---|---|---|
| `srv/helper_scripts/canary/edge_p2_flip_dry_run.py` | **新檔** | 829 | 5 條 pre-flight check + IPC sync helper（自帶 HMAC auth）+ markdown / JSON 雙輸出 |
| `srv/helper_scripts/operator/edge_p2_flip.sh` | **新檔** | 283 | 5 step flip SOP wrapper（dry-run → confirm → patch → verify → healthcheck）|
| `srv/helper_scripts/operator/edge_p2_revert.sh` | **新檔** | 208 | 3 step 90s 緊急回滾 wrapper（無 confirm；緊急回滾必須立即）|
| `srv/helper_scripts/operator/` | **新目錄** | — | per RFC §7 推薦路徑；operator-runnable SOP 檔的歸屬 |

**未動之檔**：所有 production code (Rust / Python business logic) **零變更**；僅新增 helper scripts。

---

## 3. 關鍵 Diff（pre-flight 5 check 摘要）

dry-run script 的 5 條 pre-flight 結構（每個 check 回 `(status, message, details)` tuple）：

```python
# (a) exit_features writer 24h cumulative > 0
def check_a_exit_features_writer(engine_mode):
    # SQL: SELECT COUNT(*) FROM learning.exit_features
    #      WHERE ts > now() - interval '24 hours' AND engine_mode = ...
    # live_demo 同時匹配 IN ('live', 'live_demo') per CLAUDE.md §三 engine_mode upgrade
    ...

# (b) decision_shadow_exits table exists
def check_b_decision_shadow_exits_table():
    # SQL: SELECT to_regclass('learning.decision_shadow_exits') IS NOT NULL
    ...

# (c) Combine Layer mock-inference path wired via ExitConfig schema
def check_c_combine_layer_schema(engine_mode):
    # IPC: get_risk_config → verify all 9 ExitConfig fields present
    #      (incl. shadow_enabled, missing_edge_fallback_bps, giveback_*)
    ...

# (d) IPC patch_risk_config deep-merge path live (DRY — no mutation)
def check_d_ipc_patch_path_dry(engine_mode, mock_events):
    # Construct EXACT flip payload {exit: {shadow_enabled: true}}
    # Validate JSON serialise; round-trip read-only get_risk_config (no mutation)
    ...

# (e) Reverse patch path constructible
def check_e_revert_path_constructible(engine_mode):
    # Construct revert payload {exit: {shadow_enabled: false}}
    # Symmetric structure check (flip and revert payloads must have
    # identical shape modulo bool flip)
    ...
```

關鍵設計：(d) **絕不**真送 mutating patch — 只跑唯讀 round-trip 證 channel + auth + response shape。真實 flip 只能透過 `edge_p2_flip.sh` 在 dry-run PASS + operator confirm 後執行。

---

## 4. 治理對照

### 4.1 PA RFC 對齊
| RFC 章節 | E1 落地 |
|---|---|
| §3.1 Pre-flight 5 條 | dry-run script 1:1 實作 |
| §3.2 IPC patch 翻轉路徑 | flip.sh STEP 3 inline `python3 -c` 走 `_sync_ipc_call("patch_risk_config", ...)` |
| §3.4 flip 後立即驗證 | flip.sh STEP 4 (5s wait + verify shadow_enabled==true) + STEP 5 (60s wait + healthcheck [8][15]) |
| §4.2 Manual 90s revert SOP | revert.sh 全文（3 step，**無** confirm，緊急路徑）|
| §6.1 EX-04 物理隔離 | 本 PR 純 helper script，**不**碰 reconciler 邏輯 |
| §6.2 SM-02 物理隔離 | 本 PR **不**經 ExecutorAgent / SubmitOrder 路徑 |
| §7 子任務 T1/T3 isolation | 主樹編輯，0 worktree（per §8 isolation 評估）|

### 4.2 CLAUDE.md / memory 對齊
| 規則 | 落地 |
|---|---|
| §七 雙語注釋強制 | 3 檔全有 MODULE_NOTE 雙語頭 + 每 fn docstring 雙語 + inline 中英對照 |
| §七 跨平台合規（路徑不硬編碼） | grep `/home/ncyu` `/Users/ncyu` = 0 命中（驗證後） |
| §七 OPENCLAW_DATA_DIR / OPENCLAW_SECRETS_ROOT 環境變數 | 3 檔全用 env var fallback，無 user-home 字面值 |
| §九 文件大小 | dry-run 829 / flip 283 / revert 208，全在 1200 硬上限內（dry-run 略超 800 警告，~36% 為雙語 docstring 必要）|
| memory `feedback_shell_paste_safety` | 兩 shell wrapper 全 single-line / 無 heredoc / 複雜邏輯委派 Python inline `-c` |
| memory `feedback_risk_changes_scoped` | 只動 `exit.shadow_enabled` 一字段，不連帶碰其他 ExitConfig 欄位 |

### 4.3 P0/P1 硬邊界
- **不碰** max_retries=0 / live_execution_allowed / execution_authority / system_mode（per E1 profile 硬約束）
- **不修** `OPENCLAW_ALLOW_MAINNET=1` env / authorization.json / live secret slot
- 本 PR 0 業務代碼 / 0 SQL migration / 0 RiskConfig schema 變更

---

## 5. 不確定 / Edge case / 邊界

### 5.1 IPC HMAC ts unit 不一致（**新發現**）
**驗證過程中發現**：`app/ipc_client.py:786` 的 `sync_ipc_call` helper 用 `int(time.time() * 1000)`（毫秒）做 HMAC ts，但 Rust verifier `ipc_server/mod.rs:621-628` 對 `ts` 做 `now.as_secs() as i64` 比對 30s 容差 — 數量級差 1000，**legacy sync_ipc_call 應該每次都 fail auth**（但因該 helper 只在 STORE mutator 場景被低頻呼叫，未被察覺）。

**E1 處理**：dry-run script 內嵌 `_sync_ipc_call` 用 **秒** ts 對齊 Rust verifier（已在程式內加雙語 comment 標明刻意分歧）。**未修** legacy sync_ipc_call（不擴張範圍 per E1 profile）。建議 E2 / E5 後續 audit 是否要修 legacy helper。

### 5.2 IPC 認證 OPENCLAW_IPC_SECRET 來源
**真實位置**：`$HOME/BybitOpenClaw/secrets/environment_files/ipc_secret.txt`（由 `restart_all.sh:31, 196` 載入，env name 為 `OPENCLAW_SECRETS_ROOT` 預設 `$HOME/BybitOpenClaw/secrets`）。

**先前路徑誤判**：第一輪實作用 `$SRV_ROOT/settings`（錯）→ 第二輪查 restart_all.sh 確認真實位置 → 改為 `${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}`。

flip.sh / revert.sh 的 source env 邏輯已對齊 restart_all.sh 範式（idempotent — operator 已 export 不影響）。

### 5.3 Mac dev 跑 dry-run 預期 exit 2
Mac 端 engine 不跑（per memory `project_dev_runtime_split`），dry-run 偵測 socket 缺失立即 exit 2 並輸出 minimal markdown / JSON。**已驗證** Mac 上 exit=2 工作正確。

### 5.4 dry-run script 行數 829（略超 800 警告線）
**選擇保留**：~36% 行數為雙語 MODULE_NOTE / docstring / inline 注釋（CLAUDE.md §七 強制），精煉會削弱可讀性違反規範。1200 硬上限內。

### 5.5 「mock_events」參數
spec 說「100 預設，純資訊性」— dry-run 不真合成事件，因為 (i) 真合成 mock event 會污染 `learning.exit_features` 表（per RFC §9.1 警示），(ii) Rust pipeline mock injection 需修 production code 違反 0 業務代碼變更。`mock_events_target` 純記錄到 JSON artifact，操作員可用做 capacity hint。

---

## 6. Operator 下一步

### 6.1 E2 review focus
- (a) 雙語 注釋完整性 — 每新 fn 是否中英對照 + MODULE_NOTE 是否完整
- (b) 跨平台 grep 已 0 命中（路徑不硬編碼）
- (c) E2 RFC §9 重點審查 3 條：
  - **#1 dry-run 不污染 production data** ✓（dry-run check (d) 從不送 mutating patch；mock_events 是純資訊）
  - **#2 per-strategy filter SQL 防 prefix 撞名** — N/A（本 PR T1+T3 不含 T2 healthcheck filter；T2 留下批）
  - **#3 revert SOP idempotency** ✓（IPC patch idempotent；revert.sh 多次執行最終狀態相同）
- (d) IPC HMAC ts unit 不一致（5.1）— 是否要在本 PR 順手修 legacy sync_ipc_call？E1 判決**不**修（不擴張範圍），E2 拍板

### 6.2 E4 regression 驗證
**E1 已驗證**：
- bash syntax (3 檔) ✓
- Python syntax (1 檔) ✓
- Cross-platform grep ✓
- Mac dry-run exit=2 ✓
- Linux dry-run exit=0 + 5/5 PASS（real engine PID 1836245，artifact 寫入 `/tmp/openclaw/edge_p2_flip_dry_run.json`）✓

**E4 需進一步驗證**：
- flip.sh / revert.sh **本身**未在 Linux runtime 真跑（dry-run only — operator 指示 shell wrapper 寫好但不跑）
- E4 可考慮在 Linux 跑 `bash -x edge_p2_flip.sh --skip-confirm --skip-dry-run --engine-mode paper`（**paper engine** 風險低）做端到端 dry verification

### 6.3 PM Sign-off prerequisites
- E2 PASS（含 §9 三點 + 雙語注釋驗證）
- E4 regression 通過
- 本 PR 純 helper script，0 業務 / 0 SQL — Wave 3 主軸風險低

### 6.4 真實 flip 執行序（**不在本 PR 範圍**）
PM Sign-off 後 operator 真正 flip 序列：
```bash
# Linux trade-core context (systemd or sourced env)
ssh trade-core 'bash $HOME/BybitOpenClaw/srv/helper_scripts/operator/edge_p2_flip.sh --engine-mode demo'
# operator 收到 confirm prompt → 輸入 "yes" 即翻轉
# 24h 觀察 healthcheck [15] agreement ≥95% → ⇒ Phase 2 起航
# 任何時點不滿意：
#   ssh trade-core 'bash $HOME/BybitOpenClaw/srv/helper_scripts/operator/edge_p2_revert.sh'
#   90s 內回 Phase 1a dormant
```

---

## 7. 不直接 commit（per CLAUDE.md §七 強制鏈）

E1→E2→E4→QA→PM 鏈執行。E1 工作完成；等：
- E2 對抗性 review（雙語注釋 / 跨平台 / RFC §9 三點 / IPC ts unit 處置）
- E4 regression（grep + syntax 已 E1 自驗，端到端 shell wrapper 真跑由 E4 補）
- PM 統一 commit + push

**E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-26--edge_p2_flip_t1_t3_landing.md`）**
