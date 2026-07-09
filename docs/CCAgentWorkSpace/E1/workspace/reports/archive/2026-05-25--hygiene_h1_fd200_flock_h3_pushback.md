# E1 — Hygiene H-1 IMPL + H-3 Push Back

**Date**: 2026-05-25
**Sprint**: Sprint 2 Day -1 hygiene
**Source**: PA dispatch (per E5 audit `2026-05-25--runtime_hygiene_audit_pre_sprint_2.md`)
**Commit**: `5e8302f7`
**Branch**: `main`（已 push origin）

## 任務摘要

| ID | Status | Action |
|---|---|---|
| H-1 FD 200 flock leak | DONE | restart_all.sh:535 加 `0<&- 200<&-` |
| H-3 edge_estimates.json path mismatch | PUSH BACK | E5 report root cause 實證不成立；待 PM 確認 |

## H-1 IMPL — FD 200 flock leak fix（CRITICAL，阻 Sprint 2 deploy）

### 修改清單

- `srv/helper_scripts/restart_all.sh:535`（LOC = 1，加 `0<&- 200<&-`）

### Diff

```diff
--- a/helper_scripts/restart_all.sh
+++ b/helper_scripts/restart_all.sh
@@ -532,7 +532,7 @@ restart_engine() {
         ANTHROPIC_API_KEY="${anthropic_api_key}" \
         OPENAI_API_KEY="${openai_api_key}" \
         DEEPSEEK_API_KEY="${deepseek_api_key}" \
-        nohup rust/target/release/openclaw-engine > "$DATA_DIR/engine.log" 2>&1 &
+        nohup rust/target/release/openclaw-engine > "$DATA_DIR/engine.log" 2>&1 0<&- 200<&- &
     echo "    PID: $!"
 }
```

### Root cause 連鎖

1. `build_then_restart_atomic.sh:68` `exec 200>"$LOCK_FILE"` 開 FD 200（治理用 flock）
2. atomic script 子環境 exec `restart_all.sh` → engine spawn 從 atomic 父環境繼承 FD 200
3. atomic script exit 但 lock fd 在 engine inode 上仍持有 → kernel refcount >0 → lock 不釋
4. 下次跑 atomic → `flock -n 200` 立即 fail → exit 1

### Runtime evidence（E5 audit 提供，2026-05-25 02:30 UTC）

```
$ fuser /tmp/openclaw/build_window.lock
/tmp/openclaw/build_window.lock: 374287

$ ls -la /proc/374287/fd/200
l-wx------ ... 200 -> /tmp/openclaw/build_window.lock
```

current engine PID 374287（自 Action 3 OPENCLAW_ALLOW_MAINNET 設置以來）仍持鎖。

### 為什麼此修法

- engine 是 service-mode daemon，從不讀 stdin → close `0<&-` 安全
- engine 不參與治理 flock，FD 200 對 engine 純垃圾 → close `200<&-` 安全
- nohup 已 close stdin 的常見模式（per shell best practice），但本 script 原寫法漏掉

### 治理對照

- `srv/CLAUDE.md` §六：「Mac 是開發機；Linux trade-core 是 runtime；Real engine ... deploy checks belong on Linux」→ 本 fix 只 Mac syntax check，**不在 trade-core deploy**（per PA 指示 + PM Day -1 收口 SOP）
- `srv/CLAUDE.md` §九 + 操作風格 §3「Surgical changes」→ LOC = 1，無 adjacent cleanup
- M-4「禁 ssh trade-core 跑 cargo test --release」→ 嚴守，未 ssh

### Verify

- Mac `bash -n srv/helper_scripts/restart_all.sh` → OK pass
- 真實 lock 釋放只能在下次 atomic restart 驗（PM Day -1 收口統一驗）

## H-3 PUSH BACK — edge_estimates.json path mismatch（claim 不成立）

### E5 report claim

- cron 寫入：`srv/settings/edge_estimates.json`
- healthcheck [7] 讀：`/tmp/openclaw/edge_estimates.json`（不存在）
- 推薦 Option A：「path constant 替換 → `srv/settings/edge_estimates.json`」

### 我的實證

| Check | File:line | Path |
|---|---|---|
| [7] `check_edge_estimates_freshness` | `checks_ipc_edge.py:250` | `base = OPENCLAW_BASE_DIR or ~/BybitOpenClaw/srv` → `settings/edge_estimates.json` |
| [13] `check_edge_estimator_scheduler_fresh` | `checks_strategy.py:196` | 同上完全一致 |

**兩 check 讀同一 file 同一 mtime**，path 本來就對齊。

### 真實 root cause（待 PM/PA 復查）

- [7] threshold = 90 min（嚴格 hourly cadence）→ mtime 124 min ago → FAIL
- [13] threshold = 6h（G1-01 recovery target）→ mtime 124 min ago → PASS
- 不是 path bug；是 **dual-layer 警報設計**：
  - [7] = quick miss alarm（scheduler 漏 1 個 hourly cycle）
  - [13] = G1-01 recovery target alarm（>6h 才 FAIL）

### PA 指示的 line range 對不上

PA 寫「`checks_ipc_edge.py:353-444`」，實際該範圍是 `check_decision_shadow_exits` 與 edge_estimates 完全無關。

### 推回建議

PM/PA 復查後三選一：
1. **接受 dual-layer 設計**（[7]/[13] 不矛盾，是兩層警報）→ healthcheck reporter 改 UI 顯示「[7] 短期警報 vs [13] 中期目標」避免 PM 誤判
2. **放寬 [7] threshold**（90 min → 6h 對齊 [13]）→ 變相棄 quick miss 偵測
3. **不改**，PM/sub-agent 認知到 [7]/[13] 一同 dispatch 結論一致才視為 estimator 死

我**不執行**任何 path 替換，理由：path 已對齊，改了沒效。

## 治理對照

- 操作風格 §1「Think before coding：state assumptions ... push back when there is a simpler path」→ H-3 push back
- 操作風格 §8「Read before writing：exports, direct callers, shared helpers」→ H-3 path 實證 grep 全 healthcheck 目錄
- `srv/CLAUDE.md` 主動 push back：「operator 錯了/含糊時必須直接指出+提替代方案」→ 對 PA 指示

## 不確定之處

- E5 audit 是否其他 finding 也有類似實證 gap？（H-1 已驗，H-2 / M-1 / M-3 不在本任務範圍）
- 真正 ground truth 是否 healthcheck **runtime 環境**真有 `OPENCLAW_BASE_DIR=/tmp/openclaw` 誤設（理論可能但 grep 沒命中）？需要 ssh trade-core 跑 `env | grep OPENCLAW` 才能 100% 排除（但 M-4 禁 ssh 治本決策 + 本任務範圍）

## Operator 下一步

1. **H-1 等待 PM Day -1 收口**：所有 Day -1 fix 完一次 atomic restart 驗 `fuser /tmp/openclaw/build_window.lock` 應在 atomic exit 後無 PID hold
2. **H-3 push back**：PM/PA 收到本 report 後決定 dual-layer 接受 / threshold 調 / 棄 [7]
3. **memory.md** 已記教訓
EOF
