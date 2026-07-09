# PM Sign-off (Partial) — Wave F (Engine deploy + SINGLETON sibling fix)

**Date**: 2026-04-28 CEST 深夜
**PM**: 主會話（Conductor mode）
**Wave**: (2) engine `--rebuild` deploy + (3) SINGLETON-POLLUTION sibling fix (executor_shadow_toggle + strategist_promote)
**Status**: ⚠️ **PARTIAL — (3) APPROVED & MERGED, (2) REBUILD DONE / FLAG FLIP AWAITING OPERATOR AUTH**
**Pre-conditions**: Wave E Sign-off (`739af3c`)

---

## §1. Wave F 全圖

| 階段 | Track | Agent | Commit | Status |
|---|---|---|---|---|
| (3) Wave F-3 impl | SINGLETON sibling fix (PA+E1 合一) | PA worktree → 主 repo | `cff6959` | ✅ 35→0 fail / 0 production diff |
| (3) Wave F-3 E2 | retroactive review | E2 ssh + Mac | inline | ✅ PASS_WITH_NITS (1 LOW informational) |
| (2) Wave F-2 | Linux git pull + rebuild + restart | PM ssh trade-core | (no commit) | ✅ engine PID 3579476 / binary 04:13 |
| (2) Wave F-2 | TOML flip cost_edge.enabled=true + env=1 | — | — | ⏸ **awaiting operator authorization** |
| Wave F docs | partial Sign-off + memory | PM | (this commit) | 🔜 |

**origin/main**: `739af3c..cff6959`（1 commit Wave F-3） + pending memory + Sign-off commit

---

## §2. (3) Wave F-3 SINGLETON-POLLUTION sibling fix 變動摘要

### 2.1 Root cause finding (NOVEL)
Wave E SINGLETON fix (commit `b579dae`) 解了 35 fail in `test_h_state_query_handler.py`，PA 揭剩 38 baseline fail 全 sibling-pollution family。本 wave 解 17+18=35 fail in `test_executor_shadow_toggle_api.py` + `test_strategist_promote_api.py`。

**Root cause**：**同 polluter, 不同下游機制**：
- 同 polluter：`test_api_contract.py::build_client::importlib.reload(main_legacy)` 觸發 `base.current_actor` 變新 fn obj
- **W3 + h_state SINGLETON 機制**：CPython `from PKG import SUB` attribute precedence — Option B `sys.modules.get` 解
- **Wave F-3 機制**：FastAPI `Depends(base.current_actor)` 是 **route-build-time frozen callable**，reload 後 router 內 Depends 仍 frozen 舊 fn obj → `dependency_overrides[current_actor=新]` 對不上 → 401 unauthorized → 35 fail
- **Option B 不適用**：Depends freeze 是 FastAPI framework 設計語意，沒有 sys.modules.get 等價解；改 production 會破 dependency injection introspection

### 2.2 Fix (Option A only)
```python
def _make_app():
    importlib.reload(main_legacy)
    importlib.reload(executor_routes)         # ← Wave F-3 新加
    importlib.reload(strategist_promote_routes)  # ← Wave F-3 新加
    app = main_legacy.app  # router 內 Depends 已 freeze 到新 fn obj
```

### 2.3 驗證
| 維度 | Mac | Linux |
|---|---|---|
| 53/53 forward (executor + promote + api_contract) | ✅ | ✅ |
| 53/53 reverse order | ✅ | ✅ |
| 151/151 W1+W2+W3+SINGLETON regression | ✅ | ✅ |
| 全 control_api_v1 baseline | 3 fail / 3112 pass (3 phase2 Mac-only out-of-scope) | **0 fail / 3098 pass** |
| 5 sibling test file co-resident polluter | 89/89 ✅ | (推 Linux 同) |

**Linux 比 Mac 還乾淨**（phase2_routes 3 fail 是 Mac-only）。

E2 retroactive PASS_WITH_NITS（1 LOW informational：建 memory rule —已寫 `memory/feedback_fastapi_depends_reload_freeze.md`）。

---

## §3. (2) Wave F-2 Engine deploy 進度

### 3.1 已完成
- ✅ Linux `git pull --ff-only origin main` `00aa18a..739af3c`（8 commits）
- ✅ `bash helper_scripts/restart_all.sh --rebuild` 成功
  - engine PID **3579476**（前 PID 多次輪替）
  - API uvicorn PID **3579532**（4 workers）
  - binary mtime **2026-04-28 04:13**（含 Wave A+B+E 全工 + V026 hotfix + cost_edge_advisor_boot split + SINGLETON fix）
  - paper / demo / live 三引擎全 alive (snapshot 7-12s fresh)
- ✅ tick pipeline live (ticks=83 / fills=5)
- ✅ healthcheck `[30] cost_edge_advisor_status` PASS dormant by design (`OPENCLAW_COST_EDGE_ADVISOR=unset` ≠ '1')

### 3.2 ⏸ 等 operator 授權（Phase B observation 啟動 = 2 動作 per memory `feedback_ssh_bridge_workflow`「改 risk_config TOML」需 per-case 授權）

**3 env risk_config TOML 當前狀態**：
```
risk_config_paper.toml: cost_edge.enabled = false / trigger_threshold = -0.5
risk_config_demo.toml:  cost_edge.enabled = false / trigger_threshold = -0.5
risk_config_live.toml:  cost_edge.enabled = false / trigger_threshold = -0.3 (更保守)
```

**啟動 Phase B observation 需**：
1. **Set env var**：systemd unit / engine launch 加 `OPENCLAW_COST_EDGE_ADVISOR=1`（engine restart 套用）
2. **Flip TOML flag**：`cost_edge.enabled = false → true` 三 env（IPC patch_risk_config 熱重載 / 60s rollback SOP per Phase B RFC）

**Operator 抉擇**：
- **(A) 一次三 env 同時啟用** → 立即三 env 同時 launch（advisory only / 0 trade impact，理論可行）
- **(B) 分階段啟用**（risk-aware）→ paper 6h → demo 24h → live last
- **(C) 暫不啟用** → 等 G3-09 Phase C Wave 1 impl 一起 deploy

---

## §4. 測試基準（Wave F partial）

| 維度 | Pre-Wave F | Post-Wave F | Δ |
|---|---|---|---|
| Mac control_api_v1 fail | 38 | **3** (phase2 Mac-only) | -35 |
| Linux control_api_v1 fail | 35 | **0** | -35 |
| Mac/Linux Rust cargo lib | 2299 / 0 | 2299 / 0 | 0 |
| Mac/Linux daemon test | 11 / 0 | 11 / 0 | 0 |
| Mac/Linux persistence test | 2 / 0 | 2 / 0 | 0 |
| Linux engine binary mtime | 2026-04-28 03:58 | **2026-04-28 04:13** | +15min (Wave A+B+E loaded into runtime) |
| Linux engine alive | true (PID prev) | **true (PID 3579476)** | restart, paper/demo/live 三 alive |
| Linux healthcheck [30] | PASS dormant | **PASS dormant** (env=0 by design) | unchanged |

**0 P0 / P1 regression**

---

## §5. Hard boundary 驗證（CLAUDE.md §四 9 不變量）

| 不變量 | 本 wave 觸碰 |
|---|---|
| `live_execution_allowed` / `decision_lease_emitted` / `max_retries` / `OPENCLAW_ALLOW_MAINNET` / `system_mode` / `live_reserved` / `authorization.json` / `secret slot` / `engine trading_mode` | 全 ❌ 0 |

(2) Engine `--rebuild` 是 binary swap，不觸 trade authority 不變量。
(3) SINGLETON sibling fix 是純 test fixture，0 production diff。

---

## §6. FUP Backlog 狀態

**已結案**（本 wave）：
- ✅ SINGLETON-POLLUTION-EXECUTOR-SHADOW-TOGGLE-API P3（commit `cff6959`）
- ✅ SINGLETON-POLLUTION-STRATEGIST-PROMOTE-API P3（commit `cff6959`）

**未結案**（從上 wave 延續，Wave F 不處理）：
- SINGLETON-POLLUTION-PHASE2-ROUTES P4（Mac-only 3 fail；Linux 已 0 fail，事實上 Linux 已解；Mac 環境性問題）
- MAIN-RS-PRE-EXISTING-CLEANUP P2
- CLAUDE-MD-SECTION-9-HARD-CAP-EXCEPTION-CLAUSE P3
- G8-01-FUP-REGRET-DREAM-DEFERRED P3
- G3-08-FUP-MAF-SPLIT-CLEANUP P3 / G3-09-DAEMON-TEST-SPLIT P3 / G3-09-FUP-CASE-D-H5-WAIT P3 / G3-09-PA-DOCSTRING-CLARIFY P4 / G8-01-W2-FILESIZE-WATCH P4

---

## §7. 教訓（cross-cutting）

1. **同 polluter 可有不同下游機制 — 對抗審查不可假設 fix pattern 通用**：Wave E h_state SINGLETON 用 Option B+A combined（sys.modules.get），Wave F-3 executor + promote 同 polluter 但機制是 FastAPI Depends freeze（沒有 sys.modules.get 等價解），只能 Option A reload。**Lesson**：每個 fail family 必獨立 bisect root cause，不能類比上次 fix
2. **Linux 比 Mac 環境更乾淨 (有時)**：Wave F-3 後 Linux 0 fail / Mac 仍 3 fail (phase2)。Mac fastapi gap / dev_disabled secret slot 等環境差異可能掩飾真 production bug，但也可能放大 Mac-only flake。**Lesson**：Linux regression 永遠是 ground truth；Mac 是 dev tool 不是 acceptance baseline
3. **memory feedback rule for FastAPI Depends**：寫 `memory/feedback_fastapi_depends_reload_freeze.md` 防未來新測 file 重蹈覆轍。E2 LOW 建議落地
4. **Engine deploy 分兩步「rebuild」+「flag flip」乾淨分權**：rebuild 是 binary swap（autonomous OK，0 trade impact），flag flip 是 risk_config TOML 改（需 operator per-case auth per ssh-bridge memory rule）。**Lesson**：未來 deploy 都按此分權，rebuild 完先驗 healthcheck dormant，再 ask operator flag flip

---

## §8. 1-line summary

> **PARTIAL APPROVED**：Wave F-3 SINGLETON sibling fix (commit `cff6959`) 35→0 fail / 0 production diff / Linux 0 fail 全 baseline 乾淨；Wave F-2 engine `--rebuild` 完成 (PID 3579476, binary 04:13, paper/demo/live alive, [30] dormant by design)；**等 operator 授權 cost_edge.enabled=true (3 env TOML) + OPENCLAW_COST_EDGE_ADVISOR=1 env 啟動 Phase B observation period**。

---

**End of Partial Sign-off**
