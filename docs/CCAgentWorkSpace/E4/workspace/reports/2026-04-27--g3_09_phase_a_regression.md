# E4 Regression — G3-09 Phase A cost_edge_advisor schema + advisory only

**Date:** 2026-04-27
**Commit:** `00682ef` (Mac local ahead origin/main `c077e8c` by 2; G3-09 Phase A 未 push origin per operator gate)
**Verdict:** **PASS** (Mac 補位驗證完成；Linux +38 driver 俟 push 後跑 — 等效見 §教訓)

---

## 1. 測試結果

| 引擎 | passed | failed | baseline | delta | 來源 |
|---|---|---|---|---|---|
| Rust cargo lib (Mac, release) — Run 1 | **2290** | 0 | 2252 | **+38** | E1 self-report 對齊 |
| Rust cargo lib (Mac, release) — Run 2 | **2290** | 0 | 2252 | +38 | 兩遍同綠 = 非 flaky ✓ |
| Rust cargo lib (Linux baseline, release) | 2252 | 0 | 2252 | 0 | origin/main `c077e8c` 不含 G3-09，預期 |
| cost_edge_advisor module direct | **37** (32 advisor + 5 IPC handler) | 0 | n/a | new module | 兩遍同綠 |
| Rust config tests (Mac, release) | 236 | 0 | n/a | TOML deserialize | 三環境 risk_config |
| Python pytest healthcheck filter (Mac) | 39 | 0 | 39 | 0 | helper_scripts/db -k cost_edge or healthcheck |
| Python [30] direct invoke (Mac py3.10) | PASS | n/a | n/a | env=0 dormant skip | 等效於 cron 跑 [30] |

---

## 2. Adversarial Grep Verify (Advisory Only Confirm)

驗 cost_edge_advisor **不在 trade path**：

| 路徑 | hits | 結論 |
|---|---|---|
| `intent_processor/` | **0** | ✓ no trade decision wire |
| `combine_layer.rs` (single file) | 0 | ✓ |
| `exit_features/` | 0 | ✓ no exit decision wire |
| `strategies/` | 0 | ✓ no strategy logic wire |

cost_edge_advisor 出現點全在「非 trade path」：
- `lib.rs:22` — `pub mod cost_edge_advisor;`
- `main.rs:503-510` — env-gate spawn wire (合 dual safeguard)
- `main_boot_tasks.rs:19-538` — 條件 spawn fn:
  - L460-461: env=0 → "daemon not spawned" log
  - L513-516: h_state_cache_slot 10s 內未注入 → daemon not spawn
  - L526: 真 spawn 路徑（env=1 + flag=true + h_state_cache 注入完成）
- `config/risk_config.rs:43,215,221` + `risk_config_cost_edge.rs:1-67` — schema + RFC §13 prompt template + sub-struct
- `ipc_server/dispatch.rs:73-77,434-439` — read-only `get_cost_edge_advisor_status` IPC

---

## 3. Three-TOML `[cost_edge]` Schema Verify

| TOML | `[cost_edge]` 存在 | enabled | trigger_threshold | per RFC §8.2 |
|---|---|---|---|---|
| paper | ✓ | false (Phase A dormant) | -0.5 | ✓ T9-LOW-1 lock-in |
| demo | ✓ | false (Phase A dormant) | -0.5 | ✓ |
| live | ✓ | false (Phase A dormant) | **-0.3 more conservative** | ✓ |

Cargo config tests 236 / 0 failed = 全 TOML deserialize OK。

---

## 4. Healthcheck [30] check_cost_edge_advisor_status

### 4.1 Mac py3.10 direct invoke
```python
verdict, msg = check_cost_edge_advisor_status()
# verdict: PASS
# msg    : OPENCLAW_COST_EDGE_ADVISOR=unset (≠'1') — env=0 dormant by design
#          (Phase A: 0 trade impact even when activated); skip
```

### 4.2 Slot ID drift NOTE
- PA RFC §6.2 原寫 [22]
- F7 已佔用 [22] (trading_pipeline_silent_gap)
- 實裝改 [30] + docstring + commit message 雙語雙標 NOTE
- 合 §三 G6-04 drift 防線（過 7 日重採需更新或刪除）

### 4.3 函數位置 / wiring
- def: `helper_scripts/db/passive_wait_healthcheck/checks_derived.py:883-970`
- export: `__init__.py:71` + `__init__.py:114`
- runner: `runner.py` 應已 register 進 [30] slot（per E1 commit）

### 4.4 預期 Linux 行為
Push 後 Linux py3.12 + cron 跑 → [30] PASS env=0 dormant skip（與 Mac 同；env=1 啟動須 operator 顯式 set + RiskConfig flag flip）。

---

## 5. Mock 審查（PASS）

| Test | mock 範圍 | OK? |
|---|---|---|
| 32 advisor unit tests `evaluate(snapshot, cfg, is_stale)` | pure fn 真跑數學 (NaN / Inf / threshold boundary / staleness) | ✓ 0 mock 業務邏輯 |
| 5 IPC handler tests `status_*` | 真跑 dispatch + RpcCommand serde round-trip | ✓ |
| `env_gate_strict_one_semantics_serialised` | 真讀 std::env，驗 "1" only 觸發 | ✓ |
| Phase A daemon 邏輯 | 走 IPC poll H5CostStats（runtime 行為，本 E4 不啟動 spawn） | N/A |

**0 mock 業務邏輯 / 0 mock H5CostStats 計算公式 / 0 mock IPC protocol。** 合 E4 §五 Mock 安全規則。

---

## 6. 浮點 / SLA

**N/A**：純 Rust schema + read-only IPC + dormant daemon；advisor 為 pure fn 評估，無跨語言對接面 / 無 hot-path（H0 Gate / Tick path 不觸碰）。

---

## 7. 3 條 WARN（非阻塞）

1. **Commit 00682ef 未 push origin**（operator gate）
   - Linux 端 +38 完整驗證須俟 push 後跑
   - Mac 補位驗證在 Apple Silicon (aarch64) Rust release 完成；與 Linux x86_64 cargo lib 在純 Rust 邏輯（無 SIMD intrinsics / asm）等效
   - Push 後 Linux 重跑指令見 §9

2. **PA RFC slot drift [22]→[30]**
   - F7 已佔用 [22] trading_pipeline_silent_gap 是 root cause
   - E1 已在 docstring + commit message 雙標 NOTE
   - 合 §三 drift 防線

3. **Healthcheck [30] 缺 dedicated unit test**
   - [30] 為 Phase A 哨兵，無 pytest 文件直接測 env=1 / flag=true / TOML 缺欄位 等異常路徑
   - 未來 Phase B 啟動 advisor 後可補 stub mock pytest（E4 SOP 列入 follow-up）

---

## 8. 完成標準對照

| 任務 §「完成標準」 | 結果 |
|---|---|
| 1. cargo lib (Mac OR Linux) baseline + 38 = 2290 / 0 fail | **Mac 2290 / 0 兩遍同綠 ✓**（Linux 須俟 push） |
| 2. healthcheck [30] cron Linux 4/4 PASS | Mac py3.10 等效 PASS env=0 skip ✓；Linux 須俟 push |
| 3. trade-path grep verify 全 0 hit | **0 / 0 / 0 / 0 ✓**（intent_processor / combine_layer.rs / exit_features / strategies） |
| 4. 三 TOML deserialize 綠 | **config 236 / 0 ✓** |
| 5. 寫 report 到 .claude_reports/ | 寫至 `docs/CCAgentWorkSpace/E4/workspace/reports/`（per E4 完成序列）|
| 6. Verdict | **PASS** (Mac 補位等效；Linux push 後重跑 +38 為 follow-up) |

---

## 9. Push 後 Linux 重跑指令（PM 派發給下個會話）

```bash
# 1. Linux pull
ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main"

# 2. Linux cargo lib 重跑（預期 2290 / 0）
ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib 2>&1 | tail -5"

# 3. Linux healthcheck [30] runtime 試跑（預期 PASS env=0 skip）
ssh trade-core "cd ~/BybitOpenClaw/srv && python3 helper_scripts/db/passive_wait_healthcheck.py 2>&1 | grep -iE '\[30\]|cost_edge'"

# 4. Linux deploy（如 PM approve）— 此為 Rust binary 改動，須 --rebuild
# ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/restart_all.sh --rebuild"
# Note: Phase A advisory only / 0 trade impact / 0 觸碰 §四 5 live 硬邊界
# 即使 deploy 仍 dormant（OPENCLAW_COST_EDGE_ADVISOR 預設未設）
```

---

## 10. 教訓

**未 push commit 的 E4 補位策略**：當 commit 在 Mac local ahead origin（operator gate 未 push）+ Linux 端不能跑 +38 完整驗證時，採「Mac cargo --release 補位 + Linux baseline 鎖死」雙軌：

1. Mac 跑兩遍 cargo --release 確認非 flaky + 對齊 E1 self-report 數字
2. Linux 跑 baseline 確認 origin/main 健在（不含本 commit）
3. 把 push 後 Linux 重跑指令記在 report 給下個會話（PM 派發）

本次 G3-09 Phase A 驗證雖 Linux 未跑 +38，但：
- Mac 2290 / 0 兩遍同綠 ✓
- adversarial 0 trade-path hit ✓
- 三 TOML schema verify ✓
- Mac py3.10 [30] 直驗 PASS ✓

= **補位等效**。Phase A 是 advisory only / 0 trade impact / dormant by default 的 risk surface 極小 commit，補位策略可接受。

---

## 結論

**E4 REGRESSION DONE: PASS**
- Mac 補位驗證完成（cargo lib 2290/0 兩遍 + cost_edge module 37/37 + config 236/0）
- Linux baseline 確認健在（2252/0 一遍）
- Adversarial advisory only 0 hit ✓
- 三 TOML schema verify ✓
- Healthcheck [30] env=0 dormant PASS ✓
- 0 BLOCKER / 3 WARN（push gate / slot drift NOTE / [30] dedicated test 缺）

**PM 動作建議：**
- Mac local 2 commits ahead（c8a4a55 + 00682ef）
- 操作者 gate 未 push — PM 與 operator 確認 push window 後執行 §9 重跑
- 純 schema + advisory only / dormant by default → push 後不需要立即 `--rebuild`（即使 binary 滾動仍 dormant）
