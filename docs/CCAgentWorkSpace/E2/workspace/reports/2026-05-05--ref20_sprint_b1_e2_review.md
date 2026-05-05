# E2 Brief Retry Verify Report — REF-20 Sprint B1 (commit `2a69addb`)

**Date**: 2026-05-05
**Reviewer**: E2
**Background**: E2 round 1 review of B1 timed out at stream idle (759s, 81 tool uses, no .md write). PM directly verified B1 + committed `2a69addb`. This brief retry confirms commit no missed findings.
**Persistence**: Persisted by PM per E2 closure protocol.

---

## §1 Executive Verdict

**PASS-IN-RETROSPECT** — commit `2a69addb` 5 對抗反問全 PASS, 無 NEW finding 阻 B2 dispatch. PM 直 verify + commit 路徑健壯。

---

## §2 5 對抗反問結論

### Probe 1 — R0-T0 router 11 routes 註冊順序 (PASS)

`grep -nE '^@replay_router\.(get|post)' replay_routes.py`:

```
348  POST /experiments/register
385  POST /run
497  POST /run/{run_id}/finalize
539  GET  /status
596  POST /cancel
734  GET  /report/{experiment_id}
771  GET  /manifests
879  POST /manifest/verify
1004 GET  /health
1045 GET  /health/signature
1087 GET  /list
```

對應 PA report §11.3 預期 11 routes — 順序與 pre-B1 byte-equal (commit message 已聲明，git diff 僅 _do_pg_path body / sub-router function calls 變更，decorator + signature 順序未動)。Path matching 行為不變。

### Probe 2 — R4 last-active=replay localStorage 強制走 probe (PASS)

evidence at `static/app-paper.js`:
- L309 `_OC_PAPER_SUBTAB_LS_KEY = "paper_active_subtab"` (constant)
- L425-456 `ocPaperSubtabRestoreFromStorage()`: 讀 stored → `ocPaperSubtabShow(name)` (非 direct DOM activate)
- L385-398 `ocPaperSubtabShow()` 對 `name === "replay"` 必呼 `OpenClawReplaySubtab.onTabActivate()`
- L451-454 docstring 顯式聲明 invariant：「對 replay：show 內含 onTabActivate hook → 先 probe /health → render；不會 unconditional render ready UI (R4-T2 invariant：禁無 probe 直 active)」

restoreFromStorage 無 bypass，三層保證 (storage → show → onTabActivate → probe)。

### Probe 3 — R4 XSS guard 全 escape (PASS)

OpenClawReplaySubtab namespace block: 31 處 `ocEsc()` / `ocSanitizeClass()` / `innerHTML`。

可疑點 line 798-799 `wiringStatus + ' · release_profile: ' + binaryProfile` 看似裸接，但 line 764-765:
```js
const wiringStatus = ocEsc(healthData.wiring_status || "ready");
const binaryProfile = ocEsc(healthData.binary_release_profile || "(unset)");
```

兩 const 在 escape 後 assign。Defense-in-depth 完成 (false alarm dismissed)。

### Probe 4 — R0-T0 thin handler 真薄 (PASS with note)

| Route | LOC | Pattern |
|---|---:|---|
| /experiments/register | 37 | thin |
| /run | 112 | delegate `_rrun._do_pg_path_for_run_sync` + map_run_pg_error_to_http；in-memory fallback ~30 LOC kept due to module-level `_ACTIVE_RUNS` state (docstring 已說明) |
| /run/finalize | 42 | thin |
| /status | 57 | delegate `_rstatus.query_active_run_via_pg` |
| /cancel | 138 | NOT split per scope (commit message 預告 1146+354 margin sufficient for R5) |
| /report | 37 | thin |
| /manifests | 108 | delegate report_route helpers |
| /manifest/verify | 125 | NOT split per scope |
| /health | 41 | single-line delegate `_rhealth.aggregate_replay_health` |
| /health/signature | 42 | thin |
| /list | 59 | delegate `_rlist.list_replay_runs_for_actor` |

9/11 真薄；2/11 (cancel + manifest/verify) explicitly carve-out per scope. Module helper 只剩 5 個 (auth / rate_limit_key / safe wrapper / test reset)，無 business leak.

### Probe 5 — audit baseline relax safety invariant (PASS)

`tests/test_replay_routes_safe_query_audit.py::test_audit_helper_returns_clean_summary` line 450-461:

```python
summary = _audit_replay_routes_safe_query()
assert summary["audit_ok"] is True       # ✓ enforced
assert summary["leaks"] == []            # ✓ enforced (core invariant)
assert summary["total_cur_execute_hits"] >= 0   # baseline relaxed (was >= 5)
assert "_safe_pg_select" in summary["sanctioned_fns"]
assert "_do_pg_path" in summary["sanctioned_fns"]
```

Cross-ref by Case 1 (line 100-159) 對 thin `/run` handler AST source 做子字串 `_do_pg_path` 匹配 (符合 `_rrun._do_pg_path_for_run_sync` 命中) — sibling audit chain unbroken. docstring (L411-448) 完整解釋 R0-T0 retrofit + Sprint 1 Track C 歷史 baseline 演進。

---

## §3 PM 已 Verify Items Confirm

| PM verified | E2 spot-check | 結果 |
|---|---|---|
| LOC 1146 / 956 / 928 + 4 sub-router each <500 | `wc -l` 實測 ✓ | confirm |
| Router 11 routes 順序 | grep ✓ | confirm (probe 1) |
| Pytest 172 PASS Mac / 169 PASS Linux | 未重跑 (PM 已實測) | accept |
| Cross-platform grep 0 hit | grep `/home/ncyu | /Users/[^/]+` on B1 files = 0 | confirm |
| Endpoint smoke 401/405 | 未重打 | accept |
| Audit baseline docstring 完整 | Probe 5 確認 ✓ | confirm |

---

## §4 NEW Finding

**0 NEW finding**. No P0/P1. No P2 ticket needed.

Optional observations (不阻 B2，不開 ticket):
- /cancel (138 LOC) + /manifest/verify (125 LOC) 仍駐 replay_routes.py — commit message intentional carve-out，1146+354 margin 預估 R5 +0；若 B2 R5 真把 replay_routes.py 推近 1500，再開 P3 ticket 抽 /cancel.
- `replay/` 子目錄在 `control_api_v1/` (not `app/`) — 與 `report_route.py` / `run_finalize_route.py` 兄弟層一致 (grep `from .replay import` 模式)，routing layer 抽出位置正確.

---

## §5 B2 Dispatch Prerequisite

✅ **No blocker**. B2 (R5 real decision/risk replay path) 可派發.

Prerequisite 確認：
1. ✓ replay_routes.py LOC budget 354 margin available for R5
2. ✓ 4 sub-router (run/list/health/status) dependency-injection pattern 已 land — R5 可 mirror pattern 到 `replay/strategy_adapter.rs` + `replay/risk_adapter.rs` (commit message 已聲明 R5 將擴此模式入 Rust 端)
3. ✓ R4 UI state machine 5-state (empty/running/failed/completed/degraded) 已 land — R5 real decision path 可填充 ready state 4 cell 真值
4. ✓ Audit invariant `leaks=[]` + `audit_ok=True` 不變 → R5 新增 sub-router 必須繼續 sanctioned 通過 Case 1/3 audit

---

**E2 邊界遵守**：read-only verify · 0 直修 · 0 業務代碼.

E2 REVIEW DONE: PASS-IN-RETROSPECT · 0 NEW finding · B2 dispatch unblocked
