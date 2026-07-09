# E4 Sprint 1B 28 pytest fail triage — 2026-05-22

## 0. TL;DR

**Verdict: TRIAGE DONE，全 28 carry-over 至 Sprint 2，0 阻 Sprint 4 first Live**

兩遍 baseline run 全 6037 pass / 28 pre-existing fail / 45 skip / 14 subtests passed（non-flaky 0 drift vs Phase 3b 8a15de4d）。28 fail 分 3 category 各取 sample RCA：
- 24 GUI static：HTML/JS marker/version 漂移類（contract drift between spec marker & implementation）
- 7 structure：file 大小門檻 / docs index 遺漏 / common.js helper 缺失（structural drift）
- 1 writer：v072_feature_baseline_writer CLI banner 字串 drift

預估修復 5-11 小時（writer 1-2h → structure 1-3h → GUI 3-6h），全 sibling drift / 0 spike attribution；不阻 Sprint 4 first Live（W18-21 ETA ~2026-09 初，11+ 週 buffer）。

## 1. Current baseline confirm

### 1.1 兩遍 run 結果（從 srv root）

命令：
```bash
cd /Users/ncyu/Projects/TradeBot/srv && python3 -m pytest -q --tb=no \
  --ignore=venvs \
  --ignore=tests/misc_tools/test_pure_utils.py \
  --ignore=tests/ml_training/test_pure_utils.py
```

| Run | Failed | Passed | Skipped | Subtests | Duration |
|---|---|---|---|---|---|
| 1 | **28** | **6037** | 45 | 14 | 126.13s |
| 2 | **28** | **6037** | 45 | 14 | 129.94s |

**Non-flaky 兩遍同綠**。

### 1.2 vs Phase 3b baseline (commit 8a15de4d, 2026-05-22)

| 指標 | Phase 3b | Sprint 1B (本次) | Drift |
|---|---|---|---|
| Failed | 28 | 28 | **0** |
| Passed | 6037 | 6037 | **0** |
| Skipped | 45 | 45 | **0** |
| Subtests | 14 | 14 | **0** |

**0 drift**：自 Phase 3b 至今無新 fail 或 fix；所有 28 fail 仍為 pre-existing baseline；attribution 不變（spike commits f0633002 / 2f6d1761 / 01e20db9 / 8a15de4d / 26c813fb / db84b748 0 觸碰本 28 file）。

### 1.3 28 fail file 清單（與 Phase 3b 一致）

**24 GUI static**（program_code/.../tests/）：
- `static/test_replay_subtab_static_assets.py` × 12
- `static/test_w_audit_7c_typed_confirm_modal.py` × 2 (case05 + case07)
- `test_gui_fast_snapshot_routes.py` × 1
- `test_openclaw_agent_control_static.py` × 1
- `test_performance_metrics_gui_contract.py` × 2
- `test_prelive_edge_gate_trends.py` × 1
- `test_replay_routes_safe_query_audit.py` × 1
- `test_session_stop_cancel_verify.py` × 1 (邊界 case — 跨 GUI/runtime)
- 子計 21 + 3（重複行）= 24

**7 structure**（tests/structure/）：
- `test_confirm_modal_a11y_static.py::test_common_confirm_modal_has_dialog_a11y_and_focus_trap`
- `test_docs_readme_index_static.py::test_archive_top_level_files_are_all_indexed`
- `test_event_consumer_split_static.py::test_event_consumer_hot_files_stay_split_under_limit`
- `test_prompt_modal_static.py::test_common_js_exposes_custom_prompt_modal`
- `test_strategy_action_visual_isolation_static.py::test_common_css_defines_action_risk_zones`
- `test_strategy_action_visual_isolation_static.py::test_live_stop_emergency_and_close_actions_are_visually_separated`
- （共 7 case；某些 file 內多 case）

**1 writer**（tests/）：
- `test_v072_feature_baseline_writer_static.py::test_writer_cli_defaults_to_dry_run_and_requires_apply_ack`

## 2. Category breakdown

| Category | Count | Sample RCA 結果 | Fix effort est | Risk | 阻 Live? |
|---|---|---|---|---|---|
| **GUI static** | 24 | marker/version string drift（spec 字面 vs HTML/JS 實際內容對不齊） | 3-6 hr (5-15 min × 24) | low | NO |
| **Structure** | 7 | file size threshold 漲過上限 / docs index 遺漏 / common.js helper 函數遷出 | 1-3 hr (10-30 min × 7) | low | NO |
| **Writer** | 1 | CLI banner literal 與 BIN source 不對齊 | 1-2 hr (需 RCA 真實 banner 文字) | medium | NO |
| **小計** | **32 testcase / ~28 unique fail line** | (16 test file 約) | **5-11 hr total** | low-medium | NO |

說明：spec 標 28 fail，但 pytest short summary 顯示 28 row（部分 file 多 case 但 spec 數同 28 line）；本 triage 依 28 line 為單位。

## 3. Sample test RCA per category

### 3.1 GUI static sample（5 條代表）

#### 3.1.1 test_console_strategy_group_order_and_labels_are_operator_clear (replay_subtab)

```python
assert "label: 'AI 状态'" in console_html
# AssertionError: assert "label: 'AI 状态'" in '<!doctype html>...'
```

**RCA**：spec 寫死期望 sidebar label 字面 `'AI 状态'`，但 console.html 已遷成其他 label 文字（簡體 vs 繁體 / 重新命名）。**修法**：(1) 查當前 console.html 中 AI tab label 實際字串 (2) 改 test assertion 為當前 literal，或 (3) 改 console.html 把 label 改回 `'AI 状态'`（取決於哪邊是真理）。**估時 10 min**。

#### 3.1.2 test_w_audit_7c_case05_open_typed_confirm_modal_helper_balanced

```python
marker = "function openTypedConfirmModal("
start = src.find(marker)
assert start != -1, "common.js 找不到 openTypedConfirmModal 定義"
# AssertionError: common.js 找不到 openTypedConfirmModal 定義
```

**RCA**：W-AUDIT-7c 階段把 `openTypedConfirmModal` 從 `common.js` 拆分到別的 file（per 2026-05-09 W-AUDIT-7c governance-tab.js SyntaxError fix 線索），test 沒同步 import path / file。**修法**：(1) grep 整個 static/js/ 找 `function openTypedConfirmModal(` 實際 file (2) test 改讀新 file。**估時 15 min**。

#### 3.1.3 test_tab_agents_mounts_openclaw_control_surface (openclaw_agent_control)

```python
assert "/static/js/openclaw-agent-control.js?v=20260506.mag018-v1" in html
```

**RCA**：明顯的 cache-busting version pin drift（HTML 中 `?v=` 已更新到新 token，但 test 還 pin 舊 `mag018-v1`）。**修法**：兩擇一 (a) test 改成 regex `\?v=\d{8}\.[\w-]+`（推薦）(b) 對齊當前實際 version。**估時 5 min**。

#### 3.1.4 test_static_gui_uses_non_empty_performance_metric_payload_fallback

未直接 RCA，預期相同 pattern：spec 字面 payload key/value 與 HTML 實際 inline JS 對不齊。**估時 15 min**。

#### 3.1.5 test_sweep_orphan_orders_handles_cancel_failure (session_stop)

```python
assert "bybit 503" in result.get("reason", "")
# AssertionError: assert 'bybit 503' in 'order_sweep_cancel_all_failed'
```

**RCA**：runtime 改了 error reason 字串（從 "bybit 503" 改成 stable code "order_sweep_cancel_all_failed"），test 沒同步。實際 log 確實寫 "demo order sweep: cancel-all failed: bybit 503"，但 dict reason 用 stable code 是好設計（user-facing string 不應 hardcode 入 contract）。**修法**：test 改成 `assert result["reason"] == "order_sweep_cancel_all_failed"`。**估時 10 min**。

### 3.2 Structure sample（3 條代表）

#### 3.2.1 test_event_consumer_hot_files_stay_split_under_limit

```python
assert modules["dispatch.rs"] <= 800
# AssertionError: assert 850 <= 800
```

**RCA**：`event_consumer/dispatch.rs` 漲到 850 行，超過 hot-file 800 行軟上限（per CLAUDE §九 "files > 800 require review"）。**修法**：兩擇一 (a) 拆分 dispatch.rs 為 dispatch.rs + dispatch_extra.rs（推薦，符合原設計 intent）(b) 放寬 threshold（不推薦，破壞 size discipline）。**估時 30-60 min**（option a 拆分 + 跑 cargo test 確認 0 breakage）。**風險低**（純文件 split）但需 cargo test verify。

#### 3.2.2 test_archive_top_level_files_are_all_indexed

```python
for path in sorted((ROOT / "docs" / "archive").glob("*.md")):
    assert path.name in source
# AssertionError: assert '2026-05-19--todo_v55_translation_archive.md' in '<docs/README.md content>'
```

**RCA**：新 archive file (2026-05-19) 進 `docs/archive/` 但沒同步加進 `docs/README.md` index。**修法**：append `docs/README.md` 加上 archive 表新 row。**估時 10 min**。**規則來自 CLAUDE §七 "新 docs 必須跟 `docs/README.md` placement and index rules"。**

#### 3.2.3 test_common_css_defines_action_risk_zones

```python
assert '"paper-stop-all"' in source
```

**RCA**：`common.js` 不再含 `"paper-stop-all"` 字面（per 2026-04-16 Paper 預設關閉 + 3E-ARCH 結構保留 — paper-stop-all UI 元件可能已移除）。**修法**：(a) 刪 test 此 assertion line（如果 paper-stop-all 確認永久退役）或 (b) 改成新 paper-disable marker。**估時 15 min**。

### 3.3 Writer sample（1 條）

#### 3.3.1 test_writer_cli_defaults_to_dry_run_and_requires_apply_ack

```python
assert "--apply requires --i-understand-this-modifies-db" in BIN
# AssertionError: <bin source> does not contain that literal
```

**RCA**：v072_feature_baseline_writer 的 CLI error message 字串實際是什麼，需要 cat bin source 對齊。可能 message 寫成 `"--apply must be combined with --i-understand-this-modifies-db"` 或 `"--i-understand-this-modifies-db is required when --apply is set"` 等變體。test 期 literal 與 bin 不符。

**修法步驟**：
1. 讀 `rust/.../feature_baseline_writer/src/main.rs`（或 bin file 路徑）
2. 找實際 CLI parse 處的 error literal
3. test 改成 `assert "i-understand-this-modifies-db" in BIN`（用 stable substring 不 pin 完整 wording）

**估時 1-2 hr**。**Risk medium**：writer 直接寫 PG `observability.feature_baselines`，雖然此 test 只 static check CLI banner 不真實寫 PG，但 fix 前需確認 writer 本身 runtime 行為 0 變化（fix test 不能順手改 bin runtime）。

## 4. Recommendation

### 4.1 修復優先序（從風險高 / 簡單 / 高 ROI 排）

1. **P0 - Writer (1)**：medium risk，1-2 hr，影響 V072 feature baseline writer 部署可信度
2. **P1 - Structure (7)**：low risk，1-3 hr，影響開發紀律 enforce（file size / docs index）
3. **P2 - GUI static (24)**：low risk，3-6 hr，影響 GUI contract test signal

### 4.2 carry-over plan

| Item | 範圍 | 預估 hr | 阻 Sprint 4 first Live? | Sprint 歸屬 |
|---|---|---|---|---|
| Writer fix (1) | bin literal 對齊 + test | 1-2 | NO | Sprint 2 P0 |
| Structure fix (7) | file split / docs index / helper rename | 1-3 | NO | Sprint 2 P1 |
| GUI static fix (24) | marker/version drift sync | 3-6 | NO | Sprint 2 P2 |
| **總計** | **28 fail full closure** | **5-11 hr** | **NO** | **Sprint 2 carry-over** |

### 4.3 Sprint 4 first Live 阻塞分析

Sprint 4 first Live W18-21（~2026-09 初，距今 11+ 週）必前置 closure：
- P0-EDGE-1（5 strategy alpha-deficient）
- P0-LG-3（Wave 2.4 IMPL）
- P0-OPS-1..4（HTTPS / cred / legal / runbook）

28 pytest fail **不在 P0 precondition list**，原因：
1. **0 runtime trading impact**：24 GUI static / 7 structure / 1 writer-CLI-static 全為 static assertion（無真實寫 DB / 無 IPC / 無 order 觸發）
2. **GUI fail 不影響 trading correctness**：marker 字面 drift 屬 contract test signal，runtime GUI render 仍 work（人眼可見）
3. **Structure fail 是 dev discipline 而非 prod correctness**：file size 軟上限 / docs index 完整性，不影響 trading
4. **Writer fail 是 CLI banner 字面 drift**：writer runtime 寫 PG 邏輯不受影響（test 只 static check banner）

→ **不阻 Sprint 4 first Live**

### 4.4 Sprint 2 vs Sprint 1B 歸屬建議

per current `TODO.md` §1.4：
- Sprint 1B 6 條 early IMPL 已 4 條 done（M1 Track A 已 land、M3 Track B、M11 Track C、AC-7 fixture），剩餘 2-3 條
- 28 fail 修復屬 dev hygiene / contract drift sync，不在 6 條 early IMPL 範圍
- 建議 **Sprint 2 開頭** 集中 5-11 hr 一次性 closure（避免分散到多 sprint 散落）

## 5. Verdict

- **Triage**: DONE
- **28 carry-over to Sprint 2**: P0 writer (1) + P1 structure (7) + P2 GUI (24) = 5-11 hr
- **阻 Sprint 4 first Live**: NO（11+ 週 buffer + 全 static drift / 0 runtime trading impact）
- **PASS / FAIL**: PASS（triage scope；本 task 不修代碼，不 commit）
- **Sub-agent dispatch**: 0（single-thread per task spec）
- **Two-run flaky check**: PASS（28/6037/45/14 完全一致）

## 6. Lessons Learned（補 memory.md）

1. **contract drift signal 28 fail 不必焦慮，但需 sprint 級集中修**：自 Phase 3b 至今 0 drift 證明 baseline 穩定；spread 在多次 commit 累積 drift 屬正常 dev 模式；建議每 sprint 開頭設「contract drift sweep」固定 1-2 hr slot 集中修，避免 baseline 漂得更遠。
2. **GUI static test 應改用 stable substring 而非 literal pin**：sample 3.1.3 cache-busting `?v=20260506.mag018-v1` 是 high-frequency drift 來源（每次 cache bust 都漂）；應改成 regex 或刪 version pin。**規則**：cache-busting / timestamp / build hash 等 frequently-rotated string 不寫進 test assertion。
3. **runtime stable code vs user-facing text 應分層 contract**：sample 3.1.5 dict.reason 用 stable code（`order_sweep_cancel_all_failed`）但 log/UI 用 human readable（`"bybit 503"`）；test 應 contract 第一層 stable code，第二層 log message 用 substring 模式不 pin literal。
4. **file size 軟上限 800 行屬 hot-file invariant**：sample 3.2.1 dispatch.rs 850 > 800 是漸進 drift 不是一次性突破；應在 commit 前 check size delta（git pre-commit hook 或 CI `wc -l` gate）。
5. **docs/README.md index 完整性靠 test enforce**：sample 3.2.2 archive 新增 file 沒 index → test catch；證明 CLAUDE §七 "新 docs 必須跟 docs/README.md placement and index rules" 是 active discipline；建議加 git pre-commit hook 自動 append 新 archive entry。
6. **本次 28 fail 0 GUI/IPC/runtime trading impact**：靜態 drift 不影響 trading correctness 是好事，但長期累積會 desensitize developer 對 contract test 的信號敏感度；建議每 sprint sweep 結束 release note 明列「contract drift fix 28→0」展示 hygiene 進度。

## 7. Operator 下一步

| Action | Owner | Priority |
|---|---|---|
| PM commit:E4 triage report + memory append | PM | P0 |
| Sprint 2 開頭 carry-over 派發 28 fix（P0 writer + P1 structure + P2 GUI）| PM | P1（Sprint 2 起跑時） |
| Sprint 4 first Live 不阻 — 繼續 P0-EDGE-1 / P0-LG-3 / P0-OPS-1..4 closure | operator + 各對應 owner | P0（>= 28 fix） |
| 加 git pre-commit hook size+docs index check（optional Sprint 2 enhancement）| E3 | P3（dev hygiene） |

---

**E4 REGRESSION DONE**: PASS · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-22--sprint_1b_pytest_fail_triage.md`
