# E2 Tier 8 Track 4 Adversarial Review — `d1a2252` (Sub-task 3-3 H5)

- **Date**: 2026-04-26
- **Reviewer**: E2 (Senior Backend + Adversarial Auditor)
- **Scope**: PM Tier 8 Track 4 — single-commit `d1a2252` (Phase 3 COMPLETE / G3-09 unblock)
- **Pre-state**: Tier 8 batch review (`84da817`) landed at 19:00:25 covering Tracks 1-3 (8cd257e/cf39415/71faf4c/79a808a). Track 4 (`d1a2252`) landed 76 seconds later at 19:01:41 — out of batch scope, hence this focused single-commit review.

---

## §0 Executive Summary

| Track | Verdict | Findings | Action |
|---|---|---|---|
| **Track 4** (Sub-task 3-3 H5 cost_logging, `d1a2252`) | ✅ **PASS-with-LOW** to E4 | 1 LOW (T8T4-LOW-1 §九 layer2_cost_tracker.py 930 LOC warning zone +130) | ACCEPT-with-FOLLOWUP — `G3-08-PHASE-4-COST-TRACKER-SPLIT` (LOW, plan ahead with Strategist split) |

**Recommendation**: **Accept Track 4 + 1 follow-up ticket** for Phase 4 RFC scope (cost_tracker split alongside Strategist split per Tier 8 batch precedent).

**Phase 3 milestone**: Sub-task 3-3 closes Phase 3 — all 5 H buckets (H1+H2+H3+H4+H5) live; **G3-09 cost_edge_ratio unblocked** (Rust hot-path can pull `cost_edge_ratio` via DashMap shard lookup ≤1ms p99).

**No commit needs to be returned to E1**.

---

## §1 Verification Methodology

8-axis pattern (Tier 7/8 batch review template carried forward) + Track 4-specific adversarial points per PM prompt:

1. Diff stats + commit msg vs actual changes
2. Cross-platform `/home/ncyu` / `/Users/<name>` grep
3. Bilingual MODULE_NOTE / docstring presence
4. §九 file size limit (800 / 1200)
5. SQL Guard / Migration A/B/C (n/a — no V### migration)
6. Hot-path safety + asyncio/threading boundary
7. Test coverage + Mac pytest baseline + Linux baseline (per commit msg)
8. Track-specific 7 adversarial points per PM prompt

**Independent SSOT verification**:
- Independent `wc -l` verified `layer2_cost_tracker.py` = exactly 930 LOC (commit msg ✅)
- Independent grep verified Rust H5CostStats schema = 4 fields (ai_spend_7d_usd / paper_pnl_7d_usd / cost_edge_ratio: Option<f64> / data_days: u32) at `rust/openclaw_engine/src/h_state_cache/types.rs:167-178`
- Independent Mac pytest = **196/196 PASS** (test_layer2 82 + test_h_state_query_handler 52 + test_h_state_invalidator 21 + test_strategist_agent 41) — exactly matches commit msg claim ✅
- Independent grep verified `_adaptive` atomic replacement under `self._lock` at line 588+636 — supports docstring lockless-read claim
- Independent diff inspection of MODULE_NOTE upgrade: Phase 3 COMPLETE narrative + 5 H buckets explicit + G3-09 unblock claim + Phase 4 prelim notes ✅

---

## §2 Track 4 — H5 cost_logging Integration (`d1a2252`)

### 2.1 Diff Stats vs Commit msg

```
5 files changed, 813 insertions(+), 101 deletions(-)
- docs/CCAgentWorkSpace/E1/memory.md (+42)
- program_code/.../app/h_state_query_handler.py (+230 / -101)
- program_code/.../app/layer2_cost_tracker.py (+129)
- program_code/.../tests/test_h_state_query_handler.py (+318)
- program_code/.../tests/test_layer2.py (+195)
```

Commit msg claim "+8 H5 cases + 2 collateral updates" in test_layer2 + "+7 H5 cases + 1 upgraded test" in test_h_state_query_handler — **independently verified by diff inspection**. ✅

### 2.2 8-Axis Audit

| # | Axis | Status | Note |
|---|---|---|---|
| A | Cross-platform | ✅ PASS | 0 hits `/home/ncyu` or `/Users/<name>` in changed files |
| B | Bilingual | ✅ PASS | Module note 雙段保留並升級 Phase 3 COMPLETE narrative; `get_h5_snapshot()` 中英對照 docstring (38 行 thread-safety + metadata drop + SSOT lens 三節分析); 2 inline 雙語 invalidate hint comments (record_claude_cost / record_search_cost) |
| C | Scope | ✅ PASS | 5 files exactly per PA §6; `git commit --only` 隔離 PA WIP + E2 batch review report (per commit msg multi-track collab note) |
| D | SQL Guard | n/a | No DDL |
| E | Hot-path safety | ✅ PASS | Two invalidate hints (h2 + h5) at record_claude_cost end; one (h5) at record_search_cost end. All daemon-thread fire-and-forget; env=0 strict no-op. Lock contract correct (see §2.3 點 C 詳審) |
| F | Test coverage | ✅ PASS | +15 unit tests (8 layer2_cost_tracker H5 + 7 h_state_query_handler H5) + 2 collateral amendments + 1 rename. **Mac pytest 196/196 PASS** (independently re-run by E2 ✅) |
| G | §九 size | ⚠️ LOW (T8T4-LOW-1) | layer2_cost_tracker.py = exactly **930 LOC** (warning zone +130 over §七 800; 270 lines headroom under §九 1200 hard cap); h_state_query_handler.py = 636 (well under 800) |
| H | Track-specific 7 adversarial points | ✅ PASS (with G LOW) | All 7 verified — see §2.3 |

### 2.3 Track 4 對抗驗證點 (PM prompt 7 點)

#### **A. H5 snapshot 4 fields 對齊 Rust H5CostStats**

- Read `rust/openclaw_engine/src/h_state_cache/types.rs:167-178`:
  ```rust
  pub struct H5CostStats {
      pub ai_spend_7d_usd: f64,        // line 169
      pub paper_pnl_7d_usd: f64,       // line 171
      pub cost_edge_ratio: Option<f64>,// line 175 (with serde(default))
      pub data_days: u32,              // line 177
  }
  ```
- Read `layer2_cost_tracker.py:get_h5_snapshot()`:
  ```python
  return {
      "ai_spend_7d_usd": float(full.get("ai_spend_7d_usd", 0.0)),
      "paper_pnl_7d_usd": float(full.get("paper_pnl_7d_usd", 0.0)),
      "cost_edge_ratio": full.get("cost_edge_ratio"),  # Optional[float]
      "data_days": int(full.get("data_days", 0)),
  }
  ```
- ✅ **4 fields 1:1 aligned + types match (f64 ↔ float / u32 ↔ int / Option<f64> ↔ Optional[float] via serde JSON null) + key names byte-identical**

#### **B. Dual invalidate hook race-window (record_claude_cost 末尾雙 hint)**

- Read `record_claude_cost()` line 410-427:
  ```python
  _invalidate_h_state_async("h2.budget_consumed")  # line 410 (Sub-task 3-1)
  ...comment block...
  _invalidate_h_state_async("h5.claude_cost_recorded")  # line 427 (Sub-task 3-3)
  return cost
  ```
- Both hints fire **outside** `with self._lock:` block (lock released after line 396 budget recording). Each call enters `h_state_invalidator.invalidate_async()` which spawns own daemon thread fire-and-forget.
- **Race-window analysis**: 兩 hint 在 ~µs 內依序發出。Rust 端 cache poller 收 hint 即觸發 ad-hoc poll；若兩 hint 太接近 Rust 可能 dedup 為一次 poll，這完全 OK — Rust 一次 `query_h_state_full` 取 H1+H2+H3+H4+H5 5 buckets，兩個 hint 各自獨立 trigger 都是去拉同一個 snapshot。**Order doesn't matter** because:
  1. 兩 hint 無 happens-before contract — Rust handler 對 reason 字串純 logging，不依排序
  2. 即使 hint 完全丟失，Rust poller (10s default) 兜底
  3. test `test_record_claude_cost_fires_h2_and_h5_invalidate` 用 set comparison（unordered）正確反映 contract: `assert emitted_reasons == {"h2.budget_consumed", "h5.claude_cost_recorded"}`
- E1 sub-agent self-report「order 不重要 by design (set check)」**獨立驗證為合理**：set comparison 是正確的測試形式，因為 production 對 hint 順序無依賴
- ✅ **Dual hook race-window safe**: thread-safe by daemon-thread fire-and-forget infra; order-independent by Rust handler design + dedup behavior + poll fallback

#### **C. H5 SSOT = same Layer2CostTracker as H2 (cost_tracker None race 同時掉)**

- Read `_collect_h_snapshots()` h_state_query_handler.py:359 + 383:
  ```python
  if include_h2:
      h2_dict = _safe_snapshot(strategist, "cost_tracker", "get_h2_snapshot")
  ...
  if include_h5:
      h5_dict = _safe_snapshot(strategist, "cost_tracker", "get_h5_snapshot")
  ```
- 兩個 lookup 都從 `strategist.cost_tracker` 拉。若 `cost_tracker is None` (Layer2CostTracker init failed)，`_safe_snapshot` 返 None for both → H2+H5 同時掉，**by design**
- Test `test_h5_dropped_when_cost_tracker_none` 顯式驗證此 contract（line 1059-1086）：
  ```python
  cost_tracker=None
  → assertNotIn("h2", result["h_states"])
  → assertNotIn("h5", result["h_states"])
  → assertIn("h1", result["h_states"]) + h3 + h4 unaffected
  ```
- E1 docstring 在 `_collect_h_snapshots` line 363-364 + `include_h5` block line 380-388 顯式描述此 SSOT 共享行為 + degradation contract
- ✅ **Design choice correct**: 共享 cost_tracker singleton 是 H2/H5 為同一 Layer2CostTracker 兩個 lens 的自然推論。Sub-task 3-1 已建立此 degradation 合約（H2 無 fallback path），Sub-task 3-3 sym 復用無新風險

#### **D. `_FakeCostTracker` opt-in `with_h5=False` 預設**

- Read `_FakeCostTracker.__init__()` test fixture line 130-165:
  ```python
  def __init__(self, snapshot=None, raises=None, with_h5=False, h5_snapshot=None, h5_raises=None):
      ...
      if with_h5:  # opt-in only
          def _get_h5(_self=self):
              ...
          self.get_h5_snapshot = _get_h5
  ```
- 對齊 Track 1 H2 default-off pattern (`include_h2=False`) 和 Track 2 H4 default-off pattern (`with_h4=False`)
- 三層共識: 默認 off 設計
  1. 保留 Sub-task 3-1 部署但 3-3 未 land 的 silent skip 路徑可測 (test_h5_dropped_when_get_h5_snapshot_method_missing line 1118-1145)
  2. 不破壞 Sub-task 3-1 / 3-2 既有測試（fixture 默認不綁 get_h5_snapshot → silent skip 不擾原 H2/H4 test 預期）
  3. opt-in + 顯式 binding via `def _get_h5(_self=self):` 避免類別污染 — 只有真正 opt-in 的 instance 才有 method
- ✅ **Pattern consistency confirmed** — 3 sub-task 三 default-off 一致

#### **E. `get_h5_snapshot` metadata-drop**

- Read `get_h5_snapshot()` line 380-385:
  ```python
  full = self.get_cost_edge_ratio()  # 6 keys
  return {
      "ai_spend_7d_usd": float(full.get("ai_spend_7d_usd", 0.0)),
      "paper_pnl_7d_usd": float(full.get("paper_pnl_7d_usd", 0.0)),
      "cost_edge_ratio": full.get("cost_edge_ratio"),
      "data_days": int(full.get("data_days", 0)),
  }
  # Drops: "roi_basis", "roi_disclaimer"
  ```
- E1 docstring (line 320-336) 三節分析: (1) Rust serde(default) forward-compat 容忍 unknown key (2) Python 端 pre-filter 是設計選擇 trade-off (3) wire payload 窄 + schema contract 清晰，對齊 H2 snapshot 「窄投影」模式
- **Adversarial concern (PM prompt)**: 「H5 metadata drop 是否破壞下游 audit / debug」
  - **驗證**: `get_cost_edge_ratio()` (line 860-901) 仍是 SSOT，roi_basis/roi_disclaimer 在它的回傳中保留（test `test_get_h5_snapshot_drops_metadata_keys_from_get_cost_edge_ratio` line 421-440 sanity check ✅）
  - **下游 audit / debug 路徑**: 任何要看 roi_basis/roi_disclaimer 的 caller 仍走 `get_cost_edge_ratio()` 直接呼叫（Cost Summary API 用），`get_h5_snapshot()` 只是 hot-path 投影
  - **無下游破壞**: H5 hot-path 預期 caller = Rust h_state_cache poller（Phase 3 唯一 consumer）+ G3-09 cost_edge_ratio Rust hot-path（後續解阻使用）。兩者都不需要 metadata strings
- ✅ **Metadata drop safe**: 不破壞 audit/debug，因為 metadata 仍在 `get_cost_edge_ratio()` 出口；H5 snapshot 是窄 hot-path 投影，符合 PA RFC §6 spec

#### **F. `get_search_cost` invalidate hook 加在哪**

- PA RFC §6 spec: `record_search_cost()` 末尾加 `_invalidate_h_state_async("h5.search_cost_recorded")`
- 實作位置 (line 432-457): hook 加在 `record_search_cost()` body 末尾 (line 457)，在 `with self._lock:` 釋放後
- E1 commit msg + inline comment 顯式說明 Sub-task 3-1 「刻意未在此加 H2 hook」(因 H2 contract per-call hint bandwidth 限縮在 record_claude_cost)
- Test `test_record_search_cost_fires_h5_invalidate` (line 522-539) 驗證 exactly 1 call + reason = "h5.search_cost_recorded"
- Test `test_record_search_cost_does_not_fire_h2_invalidate` (line 380-401) **amended**: count==0 → count==1 with assertion `all(not r.startswith("h2.") for r in emitted_reasons)` — Sub-task 3-1 contract 保留
- ✅ **Hook position correct + scope discipline maintained** (記憶 Sub-task 3-1 H2 contract 不擴張)

#### **G. `test_both_raise_drops_both_keys_version_zero` rename → `test_all_raise_drops_all_keys_version_zero`**

- Diff: 既有 test (line 494-538) `test_both_raise_...` rename 為 `test_all_raise_drops_all_keys_version_zero`，並擴 5 桶皆 raise
- New test setup:
  ```python
  cost_tracker=_FakeCostTracker(
      raises=RuntimeError("h2 boom"),
      with_h5=True,
      h5_raises=RuntimeError("h5 boom"),
  ),
  h4_raises=RuntimeError("h4 boom"),
  ```
  + H1 raises + H3 raises = 5 桶皆 raise
- Invariant 升級正確: 「全 raise → empty h_states + version stays at 0」原 Phase 2 為 H1+H3 兩桶；Phase 3 完成需 5 桶皆 raise 才回 fallback shape
- ✅ **Invariant upgrade correct** — 對齊 Phase 3 5-bucket coverage

### 2.4 §九 LOC 累積分析（重要）

| 檔 | Tier 8 完工後 LOC | §七 800 警告 | §九 1200 硬上限 |
|---|---|---|---|
| `strategist_agent.py` | **1200** (Tier 8 Track 2 後 exactly hard cap) | ✅ 超 | ⚠️ exact-touch (T8-MED-1, ACCEPT-with-FOLLOWUP `G3-08-PHASE-4-STRATEGIST-SPLIT`) |
| `layer2_cost_tracker.py` | **930** (Tier 8 Track 4 後 +130) | ⚠️ 超 130 | 270 lines headroom |
| `h_state_query_handler.py` | 636 (Tier 8 Track 4 後) | ✅ 安全 (-164) | ✅ 安全 |

**Tier 8 batch review 已開 follow-up `G3-08-PHASE-4-STRATEGIST-SPLIT`** (T8-MED-1 PM prompt 引述). Track 4 評估：

- **layer2_cost_tracker.py 930 LOC**：超警告線 130 行，在硬上限 1200 下還有 270 lines headroom
- **Phase 4 5-Agent state events** 預期會：
  - 加 5 個 `get_<agent>_snapshot()` method (在 各自 agent class，不在 cost_tracker)
  - **不直接** 觸 cost_tracker — Phase 4 範圍 ≠ 加 cost-related state
- **但** Phase 4 RFC 應 plan ahead：`Layer2CostTracker` 已多年累積 (sessions / pricing / adaptive / cost_edge / 4 record method / IPC sync / 7d rollup / H2 + H5 snapshot 兩 lens)，職責繁雜
- **建議**: 開 follow-up `G3-08-PHASE-4-COST-TRACKER-SPLIT` (LOW) — Phase 4 RFC 應 plan 是否 split layer2_cost_tracker.py 為:
  - `layer2_cost_tracker_core.py` (cost recording + sessions)
  - `layer2_adaptive.py` (adaptive budget logic + recalculate)
  - `layer2_h_state_snapshots.py` (get_h2_snapshot / get_h5_snapshot 兩 lens)
- **嚴重性 LOW 不 MEDIUM**：(a) 距 1200 still 270 lines (b) Phase 4 已有 strategist_agent.py 拆 ticket，cost_tracker 同 wave 處理 ROI 高 (c) Track 4 不引入 split 需求，純承載已存在的職責 grow

### 2.5 Findings

**T8T4-LOW-1 (LOW)** — `layer2_cost_tracker.py` 930 LOC (warning zone +130, headroom 270)
- **Severity**: LOW (warning line breach but well under hard cap)
- **Location**: `layer2_cost_tracker.py` (whole file)
- **Why LOW not MEDIUM**: 270 lines headroom 至 1200; Phase 4 5-Agent state events 不直接觸此檔；Track 4 docstring 設計合理（thread-safety + metadata + SSOT lens 三節分析對 maintainer context 有實質價值，trim 風險高 readability 損）
- **Why not no-finding**: §七 800 warning line 是 PM 應感知的 LOC 累積信號 — 不開 follow-up = 下次 commit 又加 docstring 累積到 1100+ 才警 = 類似 strategist_agent.py 1200 hard cap touch 故事重演
- **Action**: ACCEPT-with-FOLLOWUP — PM 開 `G3-08-PHASE-4-COST-TRACKER-SPLIT` (LOW, plan ahead with `G3-08-PHASE-4-STRATEGIST-SPLIT` 並行考慮)。建議 split 方案：`layer2_cost_tracker_core.py` + `layer2_adaptive.py` + `layer2_h_state_snapshots.py`。**不阻塞 Track 4 merge / E4**

### 2.6 Verdict

✅ **PASS-with-LOW to E4** — accept; T8T4-LOW-1 follow-up ticket recommended.

**Phase 3 milestone**: Closes Phase 3 → unblocks G3-09 cost_edge_ratio + Phase 4 5-Agent state events (per RFC §9.1/§9.2 dependency graph).

---

## §3 Cross-Track Verification

### 3.1 Off-limits paths verification

| Path | Touched? |
|---|---|
| `docs/CCAgentWorkSpace/QA/` | ❌ NOT touched (verified via `git --no-pager show d1a2252 --stat`) |
| `docs/CCAgentWorkSpace/Operator/` | ❌ NOT touched |
| `docs/CCAgentWorkSpace/Operator/2026-04-26--strkusdt_dust_spiral_rca.md` | ❌ NOT touched (per commit msg multi-track collab note) |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--strkusdt_dust_spiral_rca.md` | ❌ NOT touched (PA WIP 隔壁 session) |
| `docs/CCAgentWorkSpace/PA/memory.md` | ❌ NOT touched (commit msg confirms `git commit --only` isolation) |
| `.claude/agents/` / `.claude/skills/` | ❌ NOT touched |

✅ All off-limits paths respected.

### 3.2 Commit msg vs actual changes alignment

| Stat | Commit msg | Actual | Aligned? |
|---|---|---|---|
| files | 5 | 5 | ✅ |
| insertions | "+813" | 813 | ✅ |
| deletions | "-101" | 101 | ✅ |
| pytest 196/196 | claim | independently re-run ✅ | ✅ |
| layer2_cost_tracker.py 930 LOC | claim | wc -l = 930 ✅ | ✅ |
| Mac smoke env=0/env=1 | claim | not re-verified (E2 trust commit msg) | ✅ trust |
| Linux cargo lib 2212/0 | claim | not re-verified (E2 trust commit msg, Sub-task 3-3 是 0 Rust 改動) | ✅ trust |

### 3.3 Multi-track absorb pattern integrity (Track 1+2 → Track 4)

驗證 Track 4 沒覆蓋 / 漏掉 Track 1+2 的 H2/H4 改動:

- `_collect_h_snapshots()` 簽名: `(include_h1, include_h3, include_h2, include_h4, include_h5)` — 5 Track 1+2+4 flag 全在 ✅
- 5-tuple return: `(h1_dict, h3_dict, h2_dict, h4_dict, h5_dict)` — Phase 2 positional contract 保留 (h1+h3 在前)，Track 1 (h2) + Track 2 (h4) + Track 4 (h5) 末位附加 ✅
- `build_h_state_full_response()` include flag computation:
  ```python
  if include is None:
      include_h1 = True; include_h3 = True; include_h2 = True; include_h4 = True; include_h5 = True
  ```
  5 flag 全在 ✅
- `_FakeCostTracker.__init__()`: 既有 `snapshot=None` (H2 Track 1) + `raises=None` (H2 Track 1) + 新 `with_h5/h5_snapshot/h5_raises` (H5 Track 4)，Track 1 default-off pattern 保留 ✅
- `_FakeStrategist.__init__()`: 既有 `with_h4/h4_snapshot/h4_raises` (Track 2) 保留不動 ✅
- `test_all_raise_drops_all_keys_version_zero` (rename + 升級): 5 桶皆 raise 才回 empty + version=0 — 含 Track 1 (h2) + Track 2 (h4) + Track 4 (h5) raise infra ✅

✅ **Multi-track collab absorb 完整保留 Tracks 1+2 contract** — 沒 regression、沒 missing field

---

## §4 8 §九 checklist Result

| # | Item | 狀態 | 備註 |
|---|---|---|---|
| 1 | 改動範圍與 PA 方案一致 | ✅ | All 5 files within PA RFC §6 scope |
| 2 | 沒有 except:pass | ✅ | 0 hits in changed files |
| 3 | 日誌使用 %s 格式 | ✅ | 無新增 logger call (Track 4 純 snapshot/hook 無 log path) |
| 4 | 新 API 端點有 _require_operator_role() | n/a | No new API endpoints |
| 5 | except HTTPException raise | n/a | No HTTPException handling |
| 6 | detail=str(e) 已改 | ✅ | 0 hits in changed files |
| 7 | asyncio 路由無 blocking threading.Lock | ✅ | invalidate_async daemon-thread fire-and-forget; existing self._lock pattern (RLock) under recording methods |
| 8 | 沒有私有屬性穿透 | ✅ (本批不引入) | Track 4 0 cross-class private attr 穿透 (test fixture 用 `cost_tracker._adaptive.xxx` 是 test-only intrusion，acceptable per E2 慣例) |

---

## §5 Adversarial 反問 Summary

| 問題 | 答 | E2 評估 |
|---|---|---|
| 「H5 snapshot 4-field 對齊 Rust H5CostStats」 | 讀 types.rs:167-178 4 fields vs Python get_h5_snapshot 4 keys 完全 byte-identical + types match | ✅ TRUE |
| 「Dual hook race-window 是否真 thread-safe」 | 兩 hint 在 lock release 後依序發出 daemon-thread fire-and-forget；Rust handler 對 reason 字串純 logging 無 ordering contract；test set comparison 正確 | ✅ Safe by design |
| 「H5 SSOT cost_tracker None race 同時掉 H2+H5」 | 共享 strategist.cost_tracker singleton lookup；test_h5_dropped_when_cost_tracker_none 顯式驗證 H2+H5 同 drop / H1+H3+H4 unaffected | ✅ By design (Sub-task 3-1 contract 復用) |
| 「`_FakeCostTracker with_h5=False` 默認 vs Track 1 / Track 2 default-off pattern 一致」 | Track 1 H2 `include_h2=False` + Track 2 H4 `with_h4=False` + Track 4 H5 `with_h5=False` 三層一致；opt-in 顯式 method binding 不污染類 | ✅ Consistent |
| 「H5 metadata drop 是否破壞下游 audit / debug」 | metadata 仍在 `get_cost_edge_ratio()` 出口（test sanity check 證實）；H5 hot-path 預期 caller (Rust poller + G3-09 hot-path) 都不需 metadata；下游 audit/debug 路徑走 get_cost_edge_ratio() 不受影響 | ✅ Safe metadata projection |
| 「`get_search_cost` invalidate hook 加在哪 + scope discipline」 | record_search_cost() body 末尾 (line 457)，lock release 後；H2 不 fire (Sub-task 3-1 contract 保留) 由 `test_record_search_cost_does_not_fire_h2_invalidate` 升級驗證 | ✅ Correct position + scope-disciplined |
| 「`test_both_raise_drops_both_keys_version_zero` rename → `test_all_raise_drops_all_keys_version_zero`」 | 5 桶皆 raise 才回 empty + version=0 invariant 升級；Track 1 (h2) + Track 2 (h4) + Track 4 (h5) raise infra 全在 | ✅ Invariant upgrade correct |
| 「§九 layer2_cost_tracker.py 930 LOC 趨勢」 | 超警告線 130；Phase 4 5-Agent 不直接觸此檔；270 lines headroom 至 1200；建議 PM 開 follow-up `G3-08-PHASE-4-COST-TRACKER-SPLIT` LOW 與 Strategist split 並行 plan | ⚠️ T8T4-LOW-1 ACCEPT-with-FOLLOWUP |
| 「不動 QA / Operator / 隔壁 session WIP」 | git show d1a2252 --stat 5 files all in scope; Operator strkusdt + PA strkusdt + PA memory 三處 WIP 未被觸 | ✅ ALL respected |

---

## §6 Findings Summary Table

| Severity | ID | Track | Location | Description | Action |
|---|---|---|---|---|---|
| LOW | T8T4-LOW-1 | Track 4 | `layer2_cost_tracker.py` | 930 LOC (超 §七 800 warning line +130; headroom 270 至 §九 1200) | ACCEPT-with-FOLLOWUP — PM open `G3-08-PHASE-4-COST-TRACKER-SPLIT` (LOW, plan ahead with Strategist split per Tier 8 batch precedent) |

**0 CRITICAL / 0 HIGH / 0 MEDIUM / 1 LOW**

---

## §7 Recommendations to PM

### **選項 — accept Track 4 + 1 follow-up ticket**

**Rationale**:
- Track 4 (Sub-task 3-3 H5) closes Phase 3 → 全 5 H buckets live + G3-09 cost_edge_ratio unblocked + Phase 4 5-Agent state events template scalable confirmed
- 7 PM-prompted adversarial points 全 verified PASS (4 fields aligned / dual hook race safe / SSOT shared correctly / default off consistent / metadata drop safe / search hook position correct / rename invariant upgraded)
- Mac pytest 196/196 PASS (independently re-run ✅)
- Multi-track absorb pattern (Track 1+2 → Track 4) 完整保留 — 5-tuple return / 5 include flags / 3 fake fixture default-off 三層 consistent
- 唯一 finding = LOW §七 800 warning zone breach (930 LOC, 270 headroom 至 1200)，**不阻塞 merge / E4**

**Follow-up ticket推薦**:
- **G3-08-PHASE-4-COST-TRACKER-SPLIT** (LOW, ~0.5d, **PA-led design**): Phase 4 RFC 應 plan ahead 是否 split `layer2_cost_tracker.py` 為:
  - `layer2_cost_tracker_core.py` (cost recording + sessions)
  - `layer2_adaptive.py` (adaptive budget logic + recalculate)
  - `layer2_h_state_snapshots.py` (get_h2_snapshot / get_h5_snapshot 兩 lens)
  - **同 wave 處理**：與 Tier 8 batch review 開的 `G3-08-PHASE-4-STRATEGIST-SPLIT` (MEDIUM) 並行考慮，ROI 高
  - **非硬阻塞**：Phase 4 5-Agent 不直接觸此檔；split 是 plan-ahead 衛生工作 (避免 Phase 5+ 後再多 grow 2 lens 後超 1200)

**Phase 3 progression status**:
- ✅ Sub-task 3-1 (H2 commit 8cd257e) landed
- ✅ Sub-task 3-2 (H4 commit 71faf4c) landed + silent gap fixed
- ✅ Sub-task 3-3 (H5 commit d1a2252, this review) landed → **Phase 3 COMPLETE**
- → Phase 4 (5-Agent state events) unblocked
- → G3-09 cost_edge_ratio unblocked

---

## §8 8-Axis Verification Matrix

| Axis | Track 4 (H5 cost_logging) | Result |
|---|---|---|
| A 跨平台 | ✅ 0 hits | PASS |
| B 雙語 | ✅ Module note + docstring 38 行三節 + 2 inline 雙語 | PASS |
| C 範圍 | ✅ 5 files within PA §6 scope | PASS |
| D SQL Guard | n/a | n/a |
| E Hot-path | ✅ daemon-thread fire-and-forget; lock contract correct | PASS |
| F Test | ✅ Mac 196/196 PASS independently re-run; +15 unit tests + 2 collateral + 1 rename | PASS |
| G §九 size | ⚠️ layer2_cost_tracker.py 930 (T8T4-LOW-1) / h_state_query_handler.py 636 ✅ | 1 LOW |
| H Track-specific 7 點 | ✅ 7/7 verified | PASS |

---

## §9 結論

**最終裁決**：Track 4 PASS-with-LOW / 0 RETURN

| Track | Verdict | Action |
|---|---|---|
| Track 4 (`d1a2252`) | ✅ PASS-with-LOW to E4 | T8T4-LOW-1 → `G3-08-PHASE-4-COST-TRACKER-SPLIT` (PM open with `G3-08-PHASE-4-STRATEGIST-SPLIT`) |

**PM merge OK** — 1 commit 已 pushed origin main, no conflict.

**Methodology lessons**:
1. **Single-commit Tier review template suitable for late-arriving cross-tier track**: Track 4 landed 76s 後 Tier 8 batch review，獨立 review 維持 8-axis 標準 + Track-specific 7 對抗點 (PM prompt) 即可，無需重做整 batch
2. **Dual invalidate hook 同 callsite 無 ordering contract**: H2 + H5 兩 hint 在 lock release 後依序發出，daemon-thread fire-and-forget；Rust handler 對 reason 字串純 logging 無 ordering 依賴；test 必用 set comparison（unordered）反映 contract
3. **Hot-path snapshot lockless-read pattern**: 當 SSOT 持有 value-object 屬性 (self._adaptive)，writer 始終在 self._lock 下原子性 replace whole reference — reader 可不取鎖直接讀屬性 (CPython GIL 保證 attribute reference assignment 原子性)；docstring 必清楚記錄此契約 + writer 必嚴守原子 replace pattern
4. **§九 800 warning line 應作 LOC 累積信號開 follow-up plan ahead**: Tier 8 Track 2 strategist_agent.py 1200 exact-touch 是「無 warning 直撞硬限」教訓；Tier 8 Track 4 cost_tracker 930 應同樣開 follow-up ticket 而非無視，避免下次 commit 又加 100 LOC 進入 1100+ 才警
5. **SSOT 共享 + degradation 一致性**: H5 reuses cost_tracker SSOT with H2 → cost_tracker=None race 同 drop H2+H5；不是 bug 是 by design (Sub-task 3-1 已建立 contract，Sub-task 3-3 復用無新風險)；test 必顯式驗證共享 drop 路徑 (test_h5_dropped_when_cost_tracker_none) 而非單獨各 H 測 fail
6. **Metadata projection at Python boundary 是設計選擇 trade-off**: Rust serde(default) 已 forward-compat 容忍 unknown key，理論上 Python 不需 pre-filter；但 pre-filter 帶來 (a) 窄 wire payload (b) 清晰 schema contract (c) maintainer 一眼看出 H5 hot-path 與 Cost Summary API 的 lens 區別 — design judgment acceptable，E2 不退回
