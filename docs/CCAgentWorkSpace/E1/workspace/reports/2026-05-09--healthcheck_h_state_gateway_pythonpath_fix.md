# E1 報告 — healthcheck [20] h_state_gateway_freshness PYTHONPATH 修復

- **日期**：2026-05-09
- **Topic**：passive_wait healthcheck [20] FAIL "No module named 'program_code'" 修復
- **觸發**：operator 報 24h 持續 FAIL；cron 無誤但 `bash passive_wait_healthcheck.sh` 直跑 FAIL
- **commit**：`b186c6c2` (Mac SSOT)，已 `git push origin/main` + `ssh trade-core git pull --ff-only`
- **變動範圍**：1 檔，10 行 +

---

## 1. 任務摘要

24h healthcheck [20] 持續 FAIL 是 import path 配置 bug：`passive_wait_healthcheck.sh` wrapper 用絕對路徑 `exec "$PY" "$HEALTHCHECK_PY"` 跑 Python 入口時，Python 把 `sys.path[0]` 設為腳本所在目錄（`helper_scripts/db/`）而非 repo 根 BASE_DIR，導致 `checks_derived_h_state.py` 用 importlib 動態 import `program_code.exchange_connectors...h_state_invalidator` 時 `program_code` namespace package 不可見。

cron wrapper 因為先 `cd "$BASE_DIR"` + 跑相對路徑 `python3 helper_scripts/db/passive_wait_healthcheck.py`，而 `sys.path[0]=''=cwd=BASE_DIR`，意外靠這個 fallback 補上 → cron 一直 PASS（env=0 dormant by design），所以 24h cron log 不見此 bug；operator 直接 bash .sh 才暴露。

---

## 2. Root Cause

`/home/ncyu/BybitOpenClaw/srv/helper_scripts/db/passive_wait_healthcheck/checks_derived_h_state.py:178-180`：

```python
h_modules = (
    "program_code.exchange_connectors.bybit_connector."
    "control_api_v1.app.h_state_invalidator",
    ...
)
for mod_name in h_modules:
    importlib.import_module(mod_name)  # ← 失敗點
```

而 `passive_wait_healthcheck.sh` 第 86 行：

```bash
exec "$PY" "$HEALTHCHECK_PY" "$@"   # 絕對路徑
```

Python 對絕對路徑腳本：`sys.path[0] = os.path.dirname(script_abs_path)` = `helper_scripts/db/`，**不含** `program_code` 父目錄。

實證對比：

| 入口 | cwd | 入口 path | sys.path[0] | [20] |
|---|---|---|---|---|
| cron wrapper | BASE_DIR | 相對 `helper_scripts/db/...py` | `''` (cwd=BASE_DIR) | PASS env=0 |
| .sh wrapper | 任意 | 絕對路徑 | 腳本目錄 | **FAIL** |

---

## 3. 修改清單

只改 1 檔：`helper_scripts/db/passive_wait_healthcheck.sh`

## 4. 關鍵 diff

```diff
@@ Run check
     exit 2
 fi
 
+# ─── 1.5 將 BASE_DIR 加入 PYTHONPATH ──────────────────────────────────
+# 原因：[20] check_h_state_gateway_freshness 用 importlib 動態 import
+# `program_code....h_state_invalidator`；Python 起 .py 時 sys.path[0] 是腳本
+# 所在目錄（helper_scripts/db/），不含 BASE_DIR 根。cron wrapper 因為跑相對
+# 路徑 `python3 helper_scripts/db/...` 才意外靠 cwd 補上，但 .sh 用絕對路徑
+# `exec "$PY" "$HEALTHCHECK_PY"` 不享這個 fallback → 觸發
+# `No module named 'program_code'` FAIL。顯式 export PYTHONPATH 讓兩條入口
+# 一致且跨 Mac/Linux portable，不依賴呼叫端 cwd。
+export PYTHONPATH="$BASE_DIR${PYTHONPATH:+:$PYTHONPATH}"
+
 # ─── 2. Load Postgres env (mirrors restart_all.sh:212 + fresh_start.sh:188) ──
```

`${PYTHONPATH:+:$PYTHONPATH}` 是 POSIX 安全的「若 PYTHONPATH 已設則加 `:` 與舊值；否則啥都不加」— 避免覆蓋外部設定。

---

## 5. 治理對照（CLAUDE.md / memory）

| 規範 | 對照 |
|---|---|
| 跨平台兼容性 §七 | 用 `$BASE_DIR` 變量、不硬編碼 `/home/ncyu` 或 `/Users/...`；Mac dev 設 `OPENCLAW_BASE_DIR` 即 work |
| 注釋默認中文（2026-05-05） | 雙語區塊**僅中文**（feedback_chinese_only_comments） |
| commit-即-push | Mac commit b186c6c2 → push → Linux pull --ff-only ✅ |
| 中文 commit message | ✅ root cause + 修法 + 影響範圍均中文 |
| 範圍紀律 | 只動 .sh wrapper，不順手「改進」.py 或 cron；不擴大 PA 範圍 |
| singleton 表 | 無新 singleton |
| SQL Guard A/B/C | 不適用（無 migration） |
| 文件大小 | .sh 88→98 行，遠小於 800 警告線 |

---

## 6. 驗證證據

### 修前（reproduce）
```text
$ ssh trade-core "cd /tmp && bash ~/BybitOpenClaw/srv/helper_scripts/db/passive_wait_healthcheck.sh --quiet"
FAIL [20] h_state_gateway_freshness  module import failed: h_state_invalidator: No module named 'program_code'
```

### 修後（同 cwd）
```text
$ ssh trade-core "cd /tmp && bash ~/BybitOpenClaw/srv/helper_scripts/db/passive_wait_healthcheck.sh"
...
WARN [20] h_state_gateway_freshness  stub regressed from Phase 2 shape (version=0, h_states_keys=[], expected ⊇ {'h1','h3'}, missing=['h1', 'h3'], agent_states_keys=0) — H1/H3 producer regression? check Phase 2 wiring (commits 9120948 + f2ed286)
...
SUMMARY: FAIL — ≥1 healthcheck failed
PASS: 47   WARN: 11   FAIL: 1
唯一 FAIL = [40] realized_edge_acceptance（P0-EDGE-1，與本 task 無關）
```

### 鄰居影響
- `[19] observer_pipeline_alive`：PASS
- `[20] h_state_gateway_freshness`：**FAIL → WARN**（從 import error 變正當 invariant 3 regression detection）
- `[21] paper_state_dust_inventory`：PASS
- 整體 PASS=47 / WARN=11 / FAIL=1：no collateral damage

---

## 7. 不確定之處

1. **[20] 變 WARN 揭示 Phase 2 stub regression**（version=0 / h_states 空），這是修復 import 後**新揭露的次生信號**，不是本 task 引入的問題。`build_h_state_full_response()` 在 env=0 unset 時應該回 Phase 2 shape（含 {h1,h3}），目前回 Phase 1 stub shape — 可能 H1/H3 producer 在 runtime 沒接，或 build_h_state_full_response 邏輯漂移。**這不在本 task 範圍**，建議另開 P2 ticket 查 commits 9120948 + f2ed286 是否真有部署。
2. **`program_code/__init__.py` 不存在**（其下層也多無 `__init__.py`）— Python 3.3+ namespace package 機制讓 PYTHONPATH 一加即 work，沒問題；但若未來改成 explicit `regular package`（加 `__init__.py`），這個 PYTHONPATH 修法依然 work，沒副作用。
3. **是否該同樣加到 cron wrapper**？cron 目前不依賴 PYTHONPATH（靠 cd + 相對路徑），但若 someday 某 maintainer 把 cron 改成絕對路徑 / 不 cd，會撞同 bug。**未在本 task 改 cron**（最小影響原則），但可考慮 P3 hardening。

---

## 8. Operator 下一步

1. **無需 E2 大審**（10 行 sh，治理對照齊備，已 push）。如 operator 仍想 E2 review 可手動 dispatch。
2. **可選 P2 ticket**：查 [20] 新顯示的 WARN — `build_h_state_full_response()` 當前是 Phase 1 shape，與 §三 「OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow」+ Phase 2 H1/H3 已接（commits 9120948 + f2ed286, 2026-04-26）矛盾。如想此 WARN 也消，需查 producer 接線是否真在 runtime 跑。
3. **可選 P3 hardening**：把 `export PYTHONPATH=...` 也加到 `passive_wait_healthcheck_cron.sh`，讓 cron 不依賴 cwd fallback。

---

E1 IMPLEMENTATION DONE: 待 operator 決定是否需 E2 review；commit b186c6c2 已 push，Linux 已驗證 [20] FAIL → WARN。
