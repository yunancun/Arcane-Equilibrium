# OBSERVER-PIPELINE-POST-F42FACE-CLEANUP — Silent Fail Dead Code Purge

- **Ticket**：OBSERVER-PIPELINE-POST-F42FACE-CLEANUP（P2）
- **派發**：PA
- **完成 Agent**：E1
- **日期**：2026-04-26
- **commit**：`<待填，commit 後刷新>`

## 1. 任務摘要

G9-04（commit `c7d7179`，2026-04-26）刪 v1 smoke test 時揭發更大 silent fail：

1. **v2 + dead caller chain**：`bybit_private_ws_smoke_test_v2.py`（157 行）+ `bybit_ws_smoke_to_postgres.py:36`（71 行）整鏈死 — 兩檔都用 `OPENCLAW_SRV_ROOT + "/.../scripts/..."` 引用 commit `f42face`（2026-04-23）刪掉的 `scripts/` shim layer。
2. **`bybit_full_readonly_observer_cycle.py` 9 個 dead path**：cron `cron_observer_cycle.sh` 每 5 min 跑 9-step 全 fail（`[Errno 2] No such file or directory`）連續 **3 天**，但 cron wrapper 用 `if ... ; then ... else echo "non-fatal" ; fi` pattern 把所有失敗譯成 log + exit 0；cron daemon、healthcheck、所有 guard 都看不見 — 教科書級 silent-fail 模式（CLAUDE.md §七「被動等待 TODO 必附 healthcheck」明確要防）。
3. **2026-04-22 audit + lessons.md** 已有 phys_lock + edge_estimator silent-fail 先例；observer pipeline 是同模式重演。

完成狀態 = 全部 5 step 落地 + Linux verify 通過：

| Step | 動作 | 狀態 |
|---|---|---|
| Step 1 | Audit dead path + caller graph | DONE — 10 path 100% dead 確認，wrapper 行為復現 |
| Step 2A | Delete v2 + dead caller (`bybit_private_ws_smoke_test_v2.py` + `bybit_ws_smoke_to_postgres.py`) | DONE — 228 行 Python deletes |
| Step 2B | observer_cycle.py 9 dead path → 8 修正路徑 + 1 刪除 | DONE — 9 → 8 step（ws_smoke 整步移除）|
| Step 2C | cron wrapper + observer_cycle.py 補 exit-code propagate | DONE — `set -uo pipefail` + 顯式 RC capture + `sys.exit(1) if not overall_ok` |
| Step 2C′ | cron wrapper export `OPENCLAW_SRV_ROOT` 給子程序 | DONE — 修 cron-time cwd `$HOME` 導致 fallback `.` → JSON 寫到 `$HOME/docker_projects/` 而非 `REPO/docker_projects/` 的環境陷阱 |
| Step 3 | 加 healthcheck `[19] observer_pipeline_alive` | DONE — `checks_derived.py` 新 fn + `runner.py` + `__init__.py` 接線 |
| Step 4 | 跑 healthcheck 驗證 19→20 check | DONE — Linux 跑出 20 條，[19] FAIL 暴露 demo-only 環境 readonly slot 缺 api_key |

## 2. 修改清單

| 檔 | 動作 | 行數 | 一句話 |
|---|---|---|---|
| `program_code/.../io_and_persistence/bybit_private_ws_smoke_test_v2.py` | 刪 | -157 | v2 整檔死，0 真實 caller，Rust ws_status_writer 已取代上游價值（WS-RETIRE-1） |
| `program_code/.../io_and_persistence/bybit_ws_smoke_to_postgres.py` | 刪 | -71 | dead caller，內部又引用兩條 dead `scripts/` path + dead venv |
| `program_code/.../readonly_observer_pipeline/bybit_full_readonly_observer_cycle.py` | 重寫 | 142 → ~190 | 9 dead path 修正成 `io_and_persistence/`/`readonly_observer_pipeline/` 真實檔 + 1 dead step (ws_smoke) 整個刪除 + `main()` 補 `sys.exit(1) if not overall_ok` + MODULE_NOTE 雙語升級 |
| `helper_scripts/cron_observer_cycle.sh` | 重寫 | 35 → ~60 | 移除 `if ... ; then ... else echo "non-fatal" ; fi` noise pattern + 顯式捕捉 OBSERVER_RC + BRIDGE_RC + 任一非零 wrapper 整體 exit 1 + export OPENCLAW_SRV_ROOT 給子程序 |
| `helper_scripts/db/passive_wait_healthcheck/checks_derived.py` | 加 fn | +180 | `check_observer_pipeline_alive()` — 雙軸 verdict（age + ok ratio）+ 三態（PASS/WARN/FAIL）+ Mac dev opt-out env + 跨平台 `Path.stat()` |
| `helper_scripts/db/passive_wait_healthcheck/runner.py` | 加 invocation | +12 | runner [19] 接線 + docstring 升 19→20 + description 17+→20 |
| `helper_scripts/db/passive_wait_healthcheck/__init__.py` | 加 export | +2 | __all__ + 函數 import |

**淨變化**：-228 行 Python deletes / +197 行 healthcheck + observer_cycle 升級 / +25 行 cron wrapper 升級 / 200+ 行雙語 MODULE_NOTE。

## 3. 關鍵 diff

### 3.1 observer_cycle.py — 9 dead path 修正 + main() exit code

```python
# 修復前（line 35-48）
PRIVATE_REST_STEPS = [
    os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/program_code/.../scripts/bybit_private_account_check.py",  # DEAD
    os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/program_code/.../scripts/bybit_private_positions_check.py",  # DEAD
    ...                                                                                                       # 7 more DEAD
]
# main() 永遠 return None (exit 0)，silent-fail 被吞

# 修復後
_REPO_ROOT = os.environ.get("OPENCLAW_SRV_ROOT", ".")
_BYBIT_BASE = _REPO_ROOT + "/program_code/exchange_connectors/bybit_connector"
_IO = _BYBIT_BASE + "/io_and_persistence"          # 真實檔位置
_OBS = _BYBIT_BASE + "/readonly_observer_pipeline" # 真實檔位置

PRIVATE_REST_STEPS = [
    _IO + "/bybit_private_account_check.py",       # ALIVE
    _IO + "/bybit_private_positions_check.py",     # ALIVE
    ...                                            # 共 4 ALIVE + 1 GUARD + 3 POST_GUARD
]
# bybit_ws_smoke_to_postgres.py 整步移除（caller 死）

def main():
    ...
    return 0 if all_steps_ok else 1               # exit code 真實 propagate

if __name__ == "__main__":
    sys.exit(main() or 0)
```

### 3.2 cron wrapper — 修 noise pattern + export env

```bash
# 修復前（cron_observer_cycle.sh:18-32）
if $VENV "$OBSERVER" 2>&1; then
    echo "[$TS] Observer cycle complete"
else
    echo "[$TS] Observer cycle failed (non-fatal)"  # ← 把 fail 譯成 log，exit 0
fi
# 同樣 pattern for $BRIDGE
# wrapper 整體 exit 0（cron 看不見任何失敗）

# 修復後
export OPENCLAW_SRV_ROOT="$REPO"  # 修子程序 cwd != REPO 導致 JSON 寫到 $HOME 的陷阱

"$VENV" "$OBSERVER" 2>&1
OBSERVER_RC=$?
if [[ $OBSERVER_RC -eq 0 ]]; then
    echo "[$TS] Observer cycle complete (exit=$OBSERVER_RC)"
else
    echo "[$TS] Observer cycle FAILED (exit=$OBSERVER_RC) — investigate latest cycle JSON + healthcheck [19] observer_pipeline_alive"
fi
# 同樣顯式 capture for $BRIDGE → BRIDGE_RC

# 任一段失敗 → wrapper 整體非零 exit
if [[ $OBSERVER_RC -ne 0 ]]; then exit $OBSERVER_RC; fi
exit $BRIDGE_RC
```

### 3.3 healthcheck `[19] observer_pipeline_alive`

```python
def check_observer_pipeline_alive() -> tuple[str, str]:
    # opt-out for Mac dev / pre-cron-bootstrap nodes
    if os.environ.get("OPENCLAW_OBSERVER_PIPELINE_OPTIONAL") == "1":
        return ("PASS", "observer pipeline optional (...)")

    # 查 cycle JSON path（OPENCLAW_SRV_ROOT → fallback OPENCLAW_BASE_DIR → fallback ~/BybitOpenClaw/srv）
    cycle_path = Path(base) / "docker_projects/trading_services/runtime/bybit/bybit_observer_cycle_latest.json"

    if not cycle_path.exists():
        return ("FAIL", f"observer cycle JSON missing at {cycle_path} ...")

    age_h = (now - mtime).total_seconds() / 3600.0
    if age_h > 24.0:
        return ("FAIL", f"observer cycle JSON stale (age={age_h:.1f}h > 24h) ...")

    # 解析 JSON 算 ok 比率
    cycle = json.loads(cycle_path.read_text())
    ok_count = sum(1 for s in cycle["steps"] if s.get("ok") is True)
    ratio = ok_count / total

    # 三態：<50% FAIL（post-f42face fingerprint）/ 50-75% WARN / ≥75%+age≤1h PASS
    if ratio < 0.5: return ("FAIL", base_msg + " — silent-fail mode (post-f42face fingerprint? ...)")
    if ratio < 0.75: return ("WARN", base_msg + " — degraded; investigate failing steps")
    if age_h > 1.0: return ("WARN", base_msg + " — mtime drift (>1h since last cycle)")
    return ("PASS", base_msg)
```

## 4. 治理對照

| 規範 | 對照 | 備註 |
|---|---|---|
| **CLAUDE.md §七「被動等待 TODO 必附 healthcheck」** | ✅ 符合 | 加 [19]，閉合 G9-04 揭發的 silent-fail 漏洞 |
| **CLAUDE.md §七「強制連續 3 FAIL 中止」** | ✅ 符合 | observer_cycle.py 補 sys.exit(1)；wrapper 不再吞 — 連續 3 FAIL 會見光 |
| **CLAUDE.md §七 ★★ 跨平台兼容性** | ✅ 符合 | 純 `Path.stat()` + `json.loads()`；無 Linux-only API；`OPENCLAW_OBSERVER_PIPELINE_OPTIONAL=1` Mac dev opt-out |
| **CLAUDE.md §七 雙語注釋** | ✅ 符合 | 所有新增 + 修改 函數 / 類 / module 含 MODULE_NOTE 中英對照 + docstring 雙語 |
| **CLAUDE.md §八 最小影響原則** | ✅ 符合 | 不改非 observer pipeline 檔；`run_bybit_observer_cycle.py`（同目錄但不同責任）保留為 follow-up |
| **CLAUDE.md §九 1200 行硬上限** | ✅ 符合 | `checks_derived.py` 393 → ~573 行（800 警告線 < 800 < 1200）；observer_cycle.py 142 → ~190 行；其他 < 800 |
| **CLAUDE.md §九 Singleton 表** | ✅ 不適用 | 純 fn 級別，無新 singleton |
| **DOC-01 §5.6 失敗默認收縮** | ✅ 符合 | observer_cycle.py guard early-stop 也 exit 1（不靜默過）；healthcheck 預設 FAIL 而非 PASS |

## 5. 不確定之處

1. **`run_bybit_observer_cycle.py:9` dead path 留尾**：同目錄 wrapper 也用 `OPENCLAW_SRV_ROOT="." + "/.../scripts/..."` 引用 dead path，但其本身**無上游 caller**（grep 0 hit）— 屬孤立 entrypoint；未在本 ticket 範圍（PA prompt「不擴範圍到非 observer pipeline 檔」邊界 + 嚴守最小影響原則）。建議 BB-M-3 全範圍 cleanup follow-up 處理。
2. **demo-only 環境 [19] FAIL 是預期不是 bug**：Linux runtime 的 `read_only` slot 已 rename `*.dev_disabled_*`（per CLAUDE.md §七 Mac dev-only + Linux trade-core 也走 demo-only），observer cycle 的 4 個 private REST step 都會因 `api_key_not_configured` fail，guard 阻擋管線 → 5 step 1/5 ok → [19] FAIL。這正是「真實狀態暴露」的目的；operator 兩條路：(a) 設 `OPENCLAW_OBSERVER_PIPELINE_OPTIONAL=1` 對 demo-only 環境 PASS-skip (b) 修 read_only slot 配置（per memory `feedback_demo_over_paper_for_edge`，readonly slot 有意 disable）。**E2 review 時可能想推「healthcheck [19] 預設 PASS 對 demo-only」** — 我的設計選擇是相反方向（預設 FAIL 暴露真實狀態），請 PM 拍板取捨。
3. **`bybit_load_ws_jsonl_to_postgres.py` 成孤兒**：刪掉 `bybit_ws_smoke_to_postgres.py` 後其唯一 caller 也消失，但其本身仍存在 `io_and_persistence/`。屬「不擴範圍」邊界 — 留給 BB-M-3 全範圍清理。
4. **Crontab schedule 不動**：PA prompt 明示「不動 cron schedule，只動 wrapper」— 已遵守，crontab `*/5 * * * * bash $OPENCLAW_SRV_ROOT/.../cron_observer_cycle.sh ... 2>&1` 不變。
5. **跨平台 0 風險**：Mac 端 path resolve 用 `Path.home() / "BybitOpenClaw" / "srv"` fallback；不依賴 `/proc/<pid>` 或其他 Linux-only API；env override 仍走 standard `os.environ.get`。但因 Mac 不跑 cron，Mac 上 healthcheck [19] 預設會 FAIL，operator 需 `export OPENCLAW_OBSERVER_PIPELINE_OPTIONAL=1` 在 `~/.zshrc` 或 healthcheck cron wrapper（本 ticket 不修 Mac-specific 配置）。
6. **PA prompt step 5 commit 政策衝突 system prompt**：PA 第 5 step 明示「**強制 commit + push**，per lessons.md」覆蓋 system prompt「不直接 commit 等 E2/E4」default。採 PA 顯式 override（per memory `feedback_workflow_audit_chain` 「PA 派發 prompt 對 specific ticket 特殊授權 > E1 default」），與 G3-07 / G9-02 / EDGE-P1b-FUP-STALE-PEAK-IPC 同範式。

## 6. Operator 下一步

### 6.1 已完成的 Linux verification

```bash
# 1) cron exit-code propagation 測試（已驗證）
ssh trade-core "bash helper_scripts/cron_observer_cycle.sh > /tmp/observer_cron_run.log 2>&1; echo exit=$?"
# → exit=1（observer guard early-stop 因 api_key_not_configured，wrapper 真實 propagate）

# 2) cycle JSON 寫入正確 path（已驗證）
ssh trade-core "stat -c '%y %n' /home/ncyu/BybitOpenClaw/srv/docker_projects/trading_services/runtime/bybit/bybit_observer_cycle_latest.json"
# → 2026-04-26 14:53:41（fresh，REPO path 而非 $HOME path）

# 3) healthcheck 跑 20 check 含 [19]（已驗證）
ssh trade-core "bash helper_scripts/db/passive_wait_healthcheck_cron.sh && tail -25 /tmp/openclaw/passive_wait_healthcheck_cron.log"
# → 全 20 check 包含 FAIL [19] observer_pipeline_alive ... ok=1/5 (20%) ... silent-fail mode

# 4) OPENCLAW_OBSERVER_PIPELINE_OPTIONAL=1 opt-out 路徑（已驗證）
ssh trade-core "OPENCLAW_OBSERVER_PIPELINE_OPTIONAL=1 python3 -c 'from helper_scripts.db.passive_wait_healthcheck import check_observer_pipeline_alive; print(check_observer_pipeline_alive())'"
# → ('PASS', 'observer pipeline optional (...)')
```

### 6.2 PM 審查重點

1. **healthcheck [19] 預設 FAIL 設計選擇是否接受**：見 §5.2 push back — 我選預設 FAIL 暴露真實狀態，PM 可指示改 PASS。
2. **`run_bybit_observer_cycle.py` 留尾是否分配 follow-up ticket**：見 §5.1。
3. **Mac dev `OPENCLAW_OBSERVER_PIPELINE_OPTIONAL=1` 是否要進 README**：跨平台補充說明。
4. **commit + push 後 BB-M-3 全範圍清理 ticket** 是否要開：包含 `run_bybit_observer_cycle.py` + `bybit_load_ws_jsonl_to_postgres.py` 孤兒檔。

### 6.3 後續 healthcheck 監測

- 6h cron 跑 healthcheck 後 [19] 將每 6h 報一次。如果 operator 修 read_only slot api_key 後[19] 會自動轉 PASS（age 0.0h, ok ≥ 75%）。
- 若 operator 設 `OPENCLAW_OBSERVER_PIPELINE_OPTIONAL=1` 在環境（per `restart_all.sh` env file），[19] 將永遠 PASS-skip — 純 documentation 留證。

### 6.4 commit 計劃（per PA prompt step 5）

```bash
cd /Users/ncyu/Projects/TradeBot/srv
git add helper_scripts/cron_observer_cycle.sh helper_scripts/db/passive_wait_healthcheck/__init__.py helper_scripts/db/passive_wait_healthcheck/checks_derived.py helper_scripts/db/passive_wait_healthcheck/runner.py program_code/exchange_connectors/bybit_connector/readonly_observer_pipeline/bybit_full_readonly_observer_cycle.py docs/CCAgentWorkSpace/E1/memory.md docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-26--observer_pipeline_post_f42face_cleanup.md
git rm program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_private_ws_smoke_test_v2.py program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_ws_smoke_to_postgres.py
git commit -m "..."
git push origin main
ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main"
```

避開隔壁 sub-agent WIP（`docs/CCAgentWorkSpace/{QA,MIT,TW}/` + `docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-26--g3_08_phase1_subtask_b.md` 已 staged sibling）。
