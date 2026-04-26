# Wave 3 G2-06 — bb_breakout 永久 disable 落地

**日期**：2026-04-26
**Agent**：E1
**前置**：PA RFC `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g2_06_bb_breakout_disposal_rfc.md` 推 C 永久 disable + PM approve
**範圍**：4 子任務串行落地（PM 指示「同 session 串行」）

---

## 1. 任務摘要

PM 派發 Wave 3 G2-06 bb_breakout 永久 disable 落地，依 PA RFC §5 落地計劃 + §6 回滾路徑執行 4 子任務（E1a → E1b → E1c → E1d）：
1. **E1a TOML 三環境 disable** — `[bb_breakout].active = true → false`（demo / paper / live）+ 雙語 disable comment
2. **E1b healthcheck [12] 改判 + [18] disabled inventory** — `passive_wait_healthcheck.py` 加 `_read_bb_breakout_active_from_toml()` + 修改 `check_bb_breakout_post_deadlock_fix()` active=false → PASS skip + 新增 `check_disabled_strategy_inventory()` (CLAUDE.md §三 G6-04 drift 防線) + main wiring
3. **E1c CLAUDE.md §三 + TODO 同步** — 更新 P1-11 條目為「G2-06 永久 disable 結案」+ 加 2026-04-26 「已完成里程碑索引」條目 + TODO G2-06 ✅完成 + Wave 3 完成標準 [x] + healthcheck 表加 [18] + 過期 L133 行更新
4. **E1d BbBreakoutProfile + sweep tool 保留物 deferred 註解** — `params.rs` 在 `pub enum BbBreakoutProfile` 上方加雙語 comment + `bb_breakout_threshold_sweep.py` 在檔頂加雙語 comment（皆 per PA RFC §6 重啟條件 6 個月保留為 future investment；**不**加 `#[deprecated]`）

完成狀態：4/4 ✅，Mac 本地 grep + Python 3.12 驗測通過。E1 不直接 commit，等 E2 → E4 → PM 統一 commit + push。

---

## 2. 修改清單

| 檔案 | 類型 | 行數變化 | 一句話說明 |
|---|---|---|---|
| `srv/settings/strategy_params_demo.toml` | 修改 | +5 (comment) / 1 字 (true→false) | bb_breakout active=false + 雙語 disable comment |
| `srv/settings/strategy_params_paper.toml` | 修改 | +5 (comment) / 1 字 (true→false) | 同上（三環境同方向）|
| `srv/settings/strategy_params_live.toml` | 修改 | +5 (comment) / 1 字 (true→false) | 同上 |
| `srv/helper_scripts/db/passive_wait_healthcheck.py` | 修改 | +148 / -3 | 加 `_read_bb_breakout_active_from_toml()` helper + `check_disabled_strategy_inventory()` [18] check + 修改 [12] 加 disable skip 路徑 + main wiring + module docstring 索引更新 |
| `srv/CLAUDE.md` | 修改 | +1 line / 修 1 line | §三 P1-11 條目改 G2-06 disable 結案 + 加 2026-04-26 里程碑索引條目 |
| `srv/TODO.md` | 修改 | 修 4 lines | G2-06 條目 ✅完成 + Wave 3 完成標準 [x] + L133 過期描述更新 + healthcheck 表 [12]/[18] 條目 |
| `srv/rust/openclaw_engine/src/strategies/bb_breakout/params.rs` | 修改 | +5 (comment block) | `pub enum BbBreakoutProfile` 上方加雙語 G2-06 deferred 註解 |
| `srv/helper_scripts/research/bb_breakout_threshold_sweep.py` | 修改 | +5 (header comment) | 檔頂加雙語 G2-06 deferred 註解 |

**統計**：8 檔修改 / 0 新檔 / 0 刪除 / 0 重構業務代碼 / 0 改 SQL / 0 改 cargo test 邏輯。純 disable + observability + doc 同步。

---

## 3. 關鍵 diff

### 3.1 TOML disable comment（demo/paper/live 三檔同模板）

```toml
[bb_breakout]
# G2-06 (2026-04-26): permanently disabled — 7d 0 fills + 1m bandwidth mis-scale
# confirmed (P1-11 F1). Re-enable requires PA RFC + 5m timeframe upgrade.
# G2-06 (2026-04-26): 永久停用 — 7d 0 fills + 1m bandwidth 結構性錯配
# 確認（P1-11 F1）。重啟需 PA RFC + 升 5m timeframe。
active = false
cooldown_ms = 600000
```

三 TOML（demo/paper/live）皆同方向 active=false（per `feedback_env_config_independence` 故意分開但本次同方向 disable）。

### 3.2 healthcheck [12] disable skip 路徑（fail-soft）

```python
def check_bb_breakout_post_deadlock_fix(cur) -> tuple[str, str]:
    """[12] bb_breakout post-FIX-26-DEADLOCK-1 fill rate — P1-11 (1) Phase 1.

    G2-06 (2026-04-26): If `[bb_breakout].active=false` in
    `settings/strategy_params_demo.toml` (per PA RFC `2026-04-26 G2-06`
    permanent disable), this check returns PASS (skip) immediately —
    silencing the FAIL noise so other dormancy checks remain visible.
    Re-enabling the strategy (active=true) restores the original 3-state
    triage logic without further code changes.
    ...
    """
    # G2-06 (2026-04-26): TOML-driven disable skip — PA RFC permanent disable.
    # Read demo strategy_params TOML; if [bb_breakout].active=false, skip.
    # Fail-soft: any TOML read error falls through to original triage logic.
    # G2-06：讀 demo TOML，active=false 則跳過；TOML 讀失敗 fail-soft 走原邏輯。
    bb_active, _diag = _read_bb_breakout_active_from_toml()
    if bb_active is False:
        return (
            "PASS",
            "[12] bb_breakout disabled by G2-06 (active=false in TOML); fill check skipped",
        )

    try:
        n_7d = _scalar(cur, ...)  # 原邏輯保留
    except Exception as e:
        return ("WARN", f"bb_breakout 7d query failed: {e}")
    # ... 三態 triage 不變
```

**關鍵設計**：
- TOML 讀失敗（檔不存在 / parse error / key 缺）→ `_read_bb_breakout_active_from_toml()` fail-soft 回 `None` → check 走原 triage（不因 TOML race 整 pipeline 紅）
- `_read_bb_breakout_active_from_toml()` 形狀 mirror 既有 `_read_shadow_enabled_from_toml()`（INFRA-PREBUILD-1 L2-5 同模式）
- 用 `tomllib` (Python 3.11+) — codebase 既有使用
- StubCur 驗證 active=false 時 SQL 不執行（早 return PASS）

### 3.3 [18] disabled_strategy_inventory 永遠 PASS 設計

```python
def check_disabled_strategy_inventory() -> tuple[str, str]:
    """[18] disabled-strategy inventory — pure observability, never FAIL.

    G2-06 (2026-04-26): CLAUDE.md §三 drift 防線 (G6-04). When a strategy is
    disabled at TOML level (`active=false`), we want it to remain visible
    in healthcheck output so future audits can't "forget" disabled
    strategies. This check parses `settings/strategy_params_demo.toml`,
    walks every `[<strategy>]` section, and lists those with
    ``active=false``. Always returns PASS — purely informational.
    ...
    """
    # 讀 TOML → 列舉所有 `[<strategy>].active=true|false` → 顯示 disabled + active 兩組
    if not disabled:
        return ("PASS", f"no disabled strategies (active count={len(active)}: ...)")
    return (
        "PASS",
        f"disabled strategies: {', '.join(sorted(disabled))} "
        f"(active count={len(active)}: {', '.join(sorted(active)) or '(none)'})",
    )
```

**驗測輸出**（Mac local + Python 3.12）：
```
[18] check_disabled_strategy_inventory: PASS disabled strategies: bb_breakout, funding_arb (active count=3: bb_reversion, grid_trading, ma_crossover)
```

順帶觀察到 funding_arb 也 active=false（先前 G-2 結案 disable 留下），inventory 正確列出 — 符合 G6-04 drift 防線意圖（disabled 策略不可被遺忘）。

### 3.4 BbBreakoutProfile deferred 註解（params.rs）

```rust
/// - `Aggressive`：最鬆 squeeze + 窄 gap + 最低 volume + 最短 persistence，信號多
///   但信心低；建議搭配 `DonchianMode::Score` 作 dormant 策略救援組合。
//
// G2-06 (2026-04-26): strategy permanently disabled at TOML level (active=false).
// BbBreakoutProfile retained for future 5m timeframe RFC if PA approves.
// G2-06（2026-04-26）：策略已於 TOML 層永久 disable（active=false）。
// BbBreakoutProfile 保留為日後若 PA approve 升 5m timeframe 時可用。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum BbBreakoutProfile {
```

**為什麼不用 `#[deprecated]`**（per PA RFC §6 + memory 教訓）：`#[deprecated]` 會觸 build warning + 暗示「將來會刪」；G2-06 RFC §6 明寫 BbBreakoutProfile 保留為 future investment（重啟條件 6 個月內可達），語意是「非 deprecated，僅 dormant」。普通 `//` comment block 在 `///` doc-comments 與 `#[derive]` 之間屬合法 orphan comment，不破壞 doc-attribute attachment 到 `pub enum`。

---

## 4. 治理對照

### 4.1 涉及的 DOC/SM/EX/P0 編號

| 編號 | 對照 | 符合 / 違反 |
|---|---|---|
| **DOC-01 §5.6 失敗默認收縮** | bb_breakout dormant 不 disable 是反例（噪音 FAIL 蓋過真 alarm） | ✅ 符合 — disable 是收縮 |
| **CLAUDE.md §七 跨平台兼容性** | `OPENCLAW_BASE_DIR` env var 解析 path | ✅ 符合（與 `_read_shadow_enabled_from_toml` 同模式） |
| **CLAUDE.md §七 雙語注釋強制** | TOML / Python / Rust 註解 | ✅ 符合（每個 G2-06 註解皆中英對照）|
| **CLAUDE.md §七 被動等待 TODO 必附 healthcheck** | G2-06 不是被動等待類條目（即時完成）| n/a |
| **CLAUDE.md §三 drift 防線 G6-04** | 採集時間 + healthcheck id + disabled 不可被遺忘 | ✅ 符合（[18] disabled inventory 正是 drift 防線）|
| **memory `feedback_env_config_independence`** | 三環境 risk_config TOML 故意分開 | ✅ 符合 — 「故意分開但本次同方向」明確記錄 |
| **memory `feedback_no_dead_params`** | 可調參數禁假功能 | ✅ 符合 — disable 是顯式停用，不是「假可調」 |
| **memory `feedback_subagent_first`** | sub-agent 卸載 | n/a — 4 子任務串行同 session（PM 指示）|

### 4.2 強制工作鏈位置

```
PA RFC ✅ (g2_06_bb_breakout_disposal_rfc.md, 2026-04-26)
   ↓
PM Sign-off ✅ (approve C)
   ↓
@E1 (本任務 — 4 子任務串行 ✅)
   ↓
@E2 代碼審查（待）— 必查：(1) TOML 三環境同方向 (2) [12] 改判邏輯不擴張 (3) [18] 純 observability 永遠 PASS (4) Rust comment block 不影響 #[derive] attachment (5) E1 跨平台兼容 OPENCLAW_BASE_DIR 路徑解析
   ↓
@E4 回歸測試（待）— 必驗：(a) `cargo test --release -p openclaw_engine --lib` baseline 1980 不變（C 路徑不動 Rust 邏輯，必綠）(b) Linux Python 3.12 跑 `passive_wait_healthcheck.py` [12] PASS (skip) + [18] 列 bb_breakout, funding_arb (c) demo restart 後 5min 內 0 個 bb_breakout 進 on_tick log
   ↓
@QA healthcheck full sweep
   ↓
PM Sign-off + commit + push（Mac → origin → ssh trade-core git pull --ff-only → operator --rebuild）
```

---

## 5. 不確定之處

1. **funding_arb active=false 是預期狀態嗎**：[18] inventory 顯示 funding_arb 也 disabled — 我推測這是先前 G-2 結案 disable 留下的（per memory `project_g2_funding_arb_monitor` 2026-04-18 結案 NEGATIVE），符合 G6-04 drift 防線意圖（disabled 策略不可被遺忘）。**但若 funding_arb 應該重啟而我沒注意到 → push back 給 PM**。檢查路徑：`grep funding_arb settings/strategy_params_*.toml` 確認三環境是否一致 disable，以及對應 PA RFC 是否仍視為「結案 disable」。我**沒**改 funding_arb（不擴大 PA 給定的 G2-06 範圍）。

2. **healthcheck [18] 預期跨平台行為**：`tomllib` Python 3.11+ 才有；Mac local Python 3.10 環境 `[18]` 會回 `PASS tomllib unavailable (Python <3.11?), inventory unavailable`（fail-soft）。Linux production 是 Python 3.12，會走真路徑。E2 / E4 在 Linux 端跑 cron 6h 才能驗 inventory 真實顯示 bb_breakout, funding_arb（Mac 端因 Python 3.10 不行）。如果 PM 要求 Mac 端也要驗，需強制用 `/opt/homebrew/bin/python3.12 helper_scripts/db/passive_wait_healthcheck.py`（已驗 OK）。

3. **CLAUDE.md §三 「進行中/阻塞」P1-11 條目改寫**：原條目寫 dormant 處置中，我改成「G2-06 永久 disable 結案」狀態。**判斷邊界**：P1-11 是大條目（含 (2)+(3) DonchianMode + BbBreakoutProfile + (1) Phase 1 sweep），(2)+(3) 已完成，(1) 走 G2-06 disable 路徑也算結案；整條 P1-11 結案 ✓。但若 PM 認為 P1-11 還有 reversion 一支沒處理（"BB-BREAKOUT/REVERSION-DORMANT-1" 名稱含 reversion）→ 標題不應只說 G2-06，需保留 reversion 的進度。我**沒看到** TODO 中 bb_reversion 對應的 dormant 處置條目（grep 不到 active reversion-dormant TODO）→ 推測 reversion 未在當前 G 工作組範疇 / 已別處結案。E2 review 時可確認。

4. **deferred 註解放在哪**：我選 BbBreakoutProfile **enum 上方**而非 mod.rs 檔頂，因為 PA RFC 明寫「BbBreakoutProfile 保留為 future investment」— enum 級註解更精確。但 `mod.rs` 還有大量 bb_breakout 業務代碼 + 47236 行 + tests，沒被 deprecate / 沒加 G2-06 註解。**判斷**：active=false 已是顯式 disable signal，registry.rs 不會 instantiate bbb 進 on_tick，業務代碼變 dormant 自然 — 不需在所有檔加標記。如果 E2 認為 mod.rs 也需要 file-level G2-06 提示，可一行追加。

5. **跨平台註腳**：所有 path 解析皆用 `OPENCLAW_BASE_DIR` env var，Mac default `Path.home() / "BybitOpenClaw/srv"` 是 fallback —— 與 codebase 已有 `_read_shadow_enabled_from_toml()` 同模式。如果 Mac operator 有 repo 在不同位置（per memory `feedback_cross_platform`），需手動 export `OPENCLAW_BASE_DIR`。**我沒檢查 LM Studio config 是否會被影響** — 但本任務不觸 LLM，與 LM Studio 無關。

6. **engine_mode='demo' 過濾邏輯**：[18] disabled inventory 只讀 `strategy_params_demo.toml` 而非三環境合併 — 因為 healthcheck 是針對 demo runtime（`engine_mode='demo'` 過濾在 [12] SQL 中），與 [18] 一致。如果 PM 想看 paper / live 各別 disabled 狀態，需另加 [19] / [20] —— 不在 G2-06 範疇，未做。

---

## 6. Operator 下一步

### 6.1 E2 審查重點（必看 5 點）

1. **TOML 三環境同方向**（避免某環境漏改 → 該環境仍跑 dormant 策略）
   ```bash
   grep -A 6 '^\[bb_breakout\]' settings/strategy_params_demo.toml \
                                 settings/strategy_params_paper.toml \
                                 settings/strategy_params_live.toml
   ```
   應全部顯示 `active = false` + 雙語 G2-06 comment 同模板。

2. **healthcheck [12] 改判邏輯不擴張**（per PA RFC §5 「不能改 PASS 條件以外的部分」）
   ```bash
   grep -A 30 'def check_bb_breakout_post_deadlock_fix' helper_scripts/db/passive_wait_healthcheck.py | head -45
   ```
   確認原 3 態 triage（FAIL/WARN/PASS）邏輯保留，只在最前面加 `if bb_active is False: return ("PASS", "...skip")` 早 return；不順手鬆綁其他 dormancy check。

3. **[18] 純 observability 永遠 PASS**（任何 TOML 異常都 fail-soft 不 FAIL，per drift 防線設計意圖）
   ```bash
   grep -A 50 'def check_disabled_strategy_inventory' helper_scripts/db/passive_wait_healthcheck.py
   ```
   確認所有 return path 都是 PASS（tomllib 不可用 / TOML 不存在 / parse error / 沒 disabled / 有 disabled 五種狀況皆 PASS）。

4. **Rust comment block 不影響 doc-attribute attachment**
   ```bash
   grep -B 2 -A 8 'pub enum BbBreakoutProfile' rust/openclaw_engine/src/strategies/bb_breakout/params.rs
   ```
   確認 `///` doc-comments 仍 attached to enum；G2-06 `//` plain comments 為合法 orphan；`#[derive]` attribute 仍 attached to enum；無 build warning。

5. **CLAUDE.md §三 drift 規則 G6-04**（per CLAUDE.md §七）：
   - P1-11 條目註明 G2-06 結案日期（2026-04-26）+ PA RFC 引用 ✓
   - 已完成里程碑索引表加 2026-04-26 條目 ✓
   - 過期描述（TODO L133）已更新 ✓

### 6.2 E4 回歸測試重點（必驗 3 點，per PA RFC §5 部署後 E4 測試）

1. **Rust baseline 不破**：`cargo test --release -p openclaw_engine --lib` baseline 1980 / 0 failed 不變
   - 因 C 路徑只加 Rust comment block，無業務 / 無新邏輯 → 必綠
   - Mac 端可用 `ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib 2>&1 | tail -3"` 驗（per memory `project_ssh_bridge_workflow`）

2. **Linux passive_wait_healthcheck 全跑**：
   ```bash
   ssh trade-core "cd ~/BybitOpenClaw/srv && python3 helper_scripts/db/passive_wait_healthcheck.py 2>&1 | grep -E '\[12\]|\[18\]'"
   ```
   - [12] 應顯示 `PASS [12] bb_breakout_post_deadlock_fix      [12] bb_breakout disabled by G2-06 (active=false in TOML); fill check skipped`
   - [18] 應顯示 `PASS [18] disabled_strategy_inventory       disabled strategies: bb_breakout, funding_arb (active count=3: bb_reversion, grid_trading, ma_crossover)`

3. **demo restart 後 0 個 bb_breakout 進 on_tick**：operator `--rebuild` deploy 後 5min 觀察 engine log
   ```bash
   ssh trade-core "tail -200 /tmp/openclaw/engine.log | grep 'strategy=bb_breakout'"
   ```
   應只剩 `set_active(false)` 的啟動 log，無 on_tick / signal evaluation log。

### 6.3 已完成驗證（Mac local + ssh）

| 驗測 | 路徑 | 結果 |
|---|---|---|
| Python parse OK | `/opt/homebrew/bin/python3.12 -c "import ast; ast.parse(open('helper_scripts/db/passive_wait_healthcheck.py').read())"` | ✅ syntax OK |
| Python parse OK | sweep tool 同樣 | ✅ syntax OK |
| `_read_bb_breakout_active_from_toml()` 讀 demo TOML | Python 3.12 importlib 直跑 | ✅ value=False diag=ok |
| `[18]` 列舉 disabled | 同上 | ✅ `disabled strategies: bb_breakout, funding_arb (active count=3: bb_reversion, grid_trading, ma_crossover)` |
| `[12]` active=false skip | StubCur 驗 SQL 不執行 | ✅ `PASS [12] bb_breakout disabled by G2-06 (active=false in TOML); fill check skipped` |
| TOML 三環境 grep | Mac local | ✅ 三檔皆 active=false + 雙語 comment 同模板 |
| Rust comment block 位置 | params.rs L80-84 | ✅ 在 `///` doc 與 `#[derive]` 之間（合法 orphan）|

### 6.4 PM commit 路徑（per CLAUDE.md §七 強制鏈 + memory `feedback_git_commit_only_for_metadoc`）

不直接 commit。順序：
1. E2 審查通過 → E4 跑 cargo test 1980 / passive_wait_healthcheck 全綠 → QA full sweep
2. PM 統一 commit + push：
   - **CLAUDE.md / TODO.md 走 `git commit --only`**（meta-doc 隔絕 multi-session index race，per memory `feedback_git_commit_only_for_metadoc`）
   - 業務碼（TOML × 3 / passive_wait_healthcheck.py / params.rs / sweep tool）正常 `git add + commit`
   - 建議 split 兩 commit：(a) 業務 disable + healthcheck (b) meta-doc + report
3. PM push origin/main + ssh trade-core git pull --ff-only
4. operator manual `--rebuild`（per PA RFC §5 「不部署」+ PM 任務指令「操作員手動 --rebuild」）

### 6.5 不需要 operator 親自動手的步驟

無 high-risk per-case 授權項；本任務 0 業務邏輯改動 / 0 觸 live API / 0 secret / 0 schema 變更。operator 唯一動作 = 手動 `--rebuild`（PM 指示已知，不在 E1 範疇）。

---

## 7. 完成宣告

**E1 IMPLEMENTATION DONE**：4 子任務（G2-06-E1a/b/c/d）全部完成，Mac 本地驗證通過。

- 修改檔案：8 檔（3 TOML / 1 healthcheck / 1 CLAUDE.md / 1 TODO / 1 Rust params / 1 sweep tool）
- 0 業務邏輯改動 / 0 cargo build 必要 / 0 SQL migration / 0 fixture 變更
- 純 disable + observability + doc 同步
- 跨平台兼容（OPENCLAW_BASE_DIR fallback / tomllib 3.11+ fail-soft）
- 雙語注釋全覆蓋（每個 G2-06 註解皆中英對照）
- 不擴大 PA 給定範圍（funding_arb 順帶在 [18] 顯示但**沒**改 funding_arb 配置）

待 E2 審查 → E4 回歸 → QA → PM Sign-off + commit + push。

---

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-26--g2_06_bb_breakout_disable_landing.md`
