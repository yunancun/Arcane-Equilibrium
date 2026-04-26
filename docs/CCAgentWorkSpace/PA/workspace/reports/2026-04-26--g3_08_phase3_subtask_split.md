# G3-08 Phase 3 Sub-task Split — H2 + H4 + H5 Integration（PA Plan Only）

- **作者**：PA（Project Architect）
- **日期**：2026-04-26
- **Tier**：7 Track 3
- **狀態**：Plan only — 不寫實作代碼
- **依賴前置**（硬阻塞）：
  - G3-08 Phase 1A Rust h_state_cache（commit `aa287c4`）
  - G3-08 Phase 1B Python invalidator + query_handler（commit `1c7b20e`）
  - G3-08 Phase 1C strategy_wiring + healthcheck [20]（commit `5943337`）
  - G3-08 Phase 2 H1+H3 integration（commits `9120948` + `f2ed286`）
  - **Tier 7 Track 1 G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN E1**（並行進行中，next session 啟動先驗）
- **解阻 後續**：
  - G3-09 cost_edge_ratio 演算法（強依賴 H5，Sub-task 3 完成後 unblock）
  - G8-01 認知自適應 e2e 測試（弱依賴 H2/H5，Sub-task 4/Phase 4 為主）
  - 未來 GUI 統一 H 狀態 dashboard（Phase 3 完成後可單一 IPC pull H1-H5 全部）

---

## §1 背景：Phase 3 範圍 + Phase 1/2 關係 + Track 1 依賴

### 1.1 Phase 3 範圍（per PA G3-08 design §10.2 + §11.1）

PA design plan §10.2 + §11.1 規定 Phase 3 涵蓋 **H2 + H4 + H5 三模組** 的 Python→Rust 接線：

| 模組 | Python SSOT | Rust mirror（已 land Phase 1） | Phase 3 任務 |
|---|---|---|---|
| **H2** budget gate | `Layer2CostTracker.check_daily_budget()` + `_adaptive` | `H2BudgetState` (3 fields, types.rs:58-72) | 加 `get_h2_snapshot()` + invalidate hook |
| **H4** validator | `validate_ai_output()` (stateless fn) + `strategist_agent._stats["h4_validation_fail"]`（caller-side counter）| `H4ValidationStats` (2 fields, types.rs:158-163) | 加 `validation_pass` 計數器 + `get_h4_snapshot()` + invalidate hook |
| **H5** cost_logging | `Layer2CostTracker.get_cost_edge_ratio()` (line 656-692) + `_adaptive.{ai_spend_7d_usd,paper_pnl_7d_usd,data_days}` | `H5CostStats` (4 fields, types.rs:167-178) | 加 `get_h5_snapshot()` + invalidate hooks (Claude + search cost) |

**重點**：Phase 3 **純 Python 改動 + 1 個 query_handler 升級**。Rust 端 0 改動（types.rs 已備、HStateSnapshot.h2/h4/h5 已 wire 在 lib，poller stub 階段可直接吃新 schema 而無 silent regression — 因為 Phase 3 land 前 Track 1 Schema Align 已驗證 mirror 對齊）。

### 1.2 與 Phase 1/2 落地的成功 pattern 關係

| Phase | LOC | 改動文件 | Sub-task pattern |
|---|---|---|---|
| 1A Rust | ~1050 + 250 tests | h_state_cache/{mod,types,poller,tests}.rs + ipc_server/handlers/h_state.rs + slot/dispatch/main_boot wiring | **isolation worktree**，1 大 E1 |
| 1B Python | ~250 + 167 tests | h_state_invalidator.py + h_state_query_handler.py + IPC reverse route | 主樹，1 個 E1 |
| 1C 接線 | ~50 | strategy_wiring + CLAUDE §九 + passive_wait_healthcheck [20] | 主樹，串行收尾 |
| 2 H1+H3 | ~150 + 60 tests | h1_thought_gate (4 invalidate hook + get_h1_snapshot) + model_router (5 invalidate hook + get_h3_snapshot) + h_state_query_handler (Phase 1→2 升級) | 主樹，1 個 E1 |

**Phase 1+2 觀察**：4 + 1 commit 全綠，pattern 收斂在「**1 模組 = 1 invalidate hook 集合 + 1 snapshot method + query_handler 1 個 bucket**」。

### 1.3 Track 1 Schema Align 硬依賴

Track 1（隔壁 session，Tier 7 並行派）負責執行 PA RFC `2026-04-26--g3_08_h3_schema_align_decision.md` §7 的 H3RouteStats Rust rename + 3 field add。

**為什麼 Phase 3 必須等 Track 1**：

| 風險場景 | Track 1 未 land | Track 1 已 land |
|---|---|---|
| Phase 3 Sub-task 接 H2/H4/H5 schema | OK（H2/H4/H5 三 schema 與 H3 各自獨立） | OK |
| Phase 3 同步「先 audit H2/H4/H5 schema mirror」（PA RFC `g3_08_h3_schema_align_decision.md` §8.3 預警）| 失敗：H3 schema drift bug 還活 → 無 audit 可信 baseline | OK：H3 對齊後可仿照同 audit pattern 對 H2/H4/H5 |
| Phase 4 Sub-task 接 RealHStateFetcher（pull H1+H3+H2+H4+H5 一次）| Silent default-zero on H3 fields → polluted snapshot | Schema drift 已修，可信落地 |

**結論**：Track 1 必須先 commit + land + cargo test 綠，Phase 3 才開工。Next session PM 啟動 Phase 3 派發前必驗：

```bash
git log --oneline -5 | grep -i "PHASE-2-FUP-H3-SCHEMA-ALIGN"
ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib h_state_cache"
```

兩條都綠 → Phase 3 可派。

### 1.4 為什麼 Phase 3 拆 sub-task

PA design plan §11.1 估 Phase 3 全鏈 **3.5d wall-clock**（Python E1 2.5d + E2 0.5d + E4 0.5d）。一個 session 直派 3.5d 不適合：

1. context 壓力大（Phase 1+2 經驗：1 H 模組 = ~80 LOC + ~30 tests = 1 session 舒適）
2. 並行收益（H2 + H4 + H5 可獨立改 H4 / Layer2CostTracker 兩檔，無撞檔）
3. Roll-back 粒度（一次 land 三模組 → 任一爆 = 整個 Phase 3 必 revert；分 sub-task = per-module rollback）

**因此本 RFC 任務 = 將 Phase 3 拆成獨立可測試 sub-task**。

---

## §2 Sub-task 拆分方案 A/B/C 對比 + Recommend

### 2.1 Pattern A：mirror Phase 1A/B/C（功能層拆）

對 H2 / H4 / H5 各做：
- **Sub-task α** = Rust schema 補（如缺）
- **Sub-task β** = Python snapshot fn + invalidate hook
- **Sub-task γ** = query_handler bucket 升級 + healthcheck 新增

→ 3 sub-task × 3 模組 = **9 sub-task**（過細）。Phase 1 採此 pattern 因 Rust 是新建模組（mod.rs/types.rs/poller.rs/handler 4 sibling），但 Phase 3 **Rust 0 新檔 / 0 改動**（H2/H4/H5 schema 全在 types.rs 備好），Pattern A 三層拆完全是空 sub-task。

**致命短板**：Sub-task α 全空（Rust schema 0 改動），3 個 α 廢 sub-task。Pattern 拆過細 = ROI 低。

### 2.2 Pattern B：每模組 1 sub-task（per-H 模組整鏈）★ 推薦

每模組整鏈 1 sub-task（hook + snapshot + query_handler bucket + tests）：

| Sub-task | 範圍 | LOC | 影響檔案 |
|---|---|---|---|
| **3-1: H2 budget integration** | H2 invalidate hook (2-3) + `get_h2_snapshot()` + query_handler 加 H2 bucket + tests | ~80 | `layer2_cost_tracker.py` + `h_state_query_handler.py` + tests |
| **3-2: H4 validator integration** | strategist_agent 加 `validation_pass` 計數器 + invalidate hook (pass/fail) + `_h4_validator_get_snapshot()` (caller-side) + query_handler 加 H4 bucket + tests | ~70 | `strategist_agent.py` + `h_state_query_handler.py` + tests |
| **3-3: H5 cost_logging integration** | H5 invalidate hooks (record_claude_cost + record_search_cost) + `get_h5_snapshot()` (wraps `get_cost_edge_ratio`) + query_handler 加 H5 bucket + tests | ~80 | `layer2_cost_tracker.py` + `h_state_query_handler.py` + tests |

**3 sub-task 均為主樹**（純 Python 改 + 0 Rust 改 / 0 isolation 需求）。3-1 + 3-3 改同一檔（layer2_cost_tracker.py），但**改不同 method**（H2 vs H5）→ 可選串行（推薦避免雙修同檔造成 git conflict）。

**優點**：
- Pattern 鏡 Phase 2（1 sub-task = 完整 1 模組 chain，可獨立 ship）
- E2 review 簡單（1 模組 / 1 commit）
- E4 regression 集中（cargo lib + pytest baseline shift 可控）
- per-module rollback（任一 sub-task fail 不影響其他兩個）

**缺點**：
- query_handler bucket 加入分 3 commit（每 sub-task 加 1 bucket）
  - **緩解**：Phase 2 already showed pattern is additive — Sub-task 3-1 加 h2 bucket 不影響 h3，3-2 加 h4 不影響 h2/h3, etc.

### 2.3 Pattern C：先 schema audit 再 3 sub-task（4 sub-task）

C 把 Pattern B 前面加一個 **Sub-task 3-0: H2/H4/H5 Schema Mirror Audit**（per PA RFC `g3_08_h3_schema_align_decision.md` §8.3 建議「Phase 3 派發前 PA 同類 audit 一次 H2/H4/H5」）：

| Sub-task | 範圍 |
|---|---|
| **3-0: H2/H4/H5 schema mirror audit** | grep Python source 對齊 Rust H2BudgetState/H4ValidationStats/H5CostStats，補對齊 fix（如有） |
| **3-1 / 3-2 / 3-3** | 同 Pattern B |

**3-0 必要性分析**（基於我已讀完 H2/H4/H5 SSOT shape）：

| 模組 | Python SSOT shape | Rust mirror shape | Drift 風險 |
|---|---|---|---|
| H2 | `check_daily_budget()` 回 `(allowed: bool, remaining: float)` + `_config.daily_hard_cap_usd` + `_adaptive.multiplier`（3 source） | `H2BudgetState`：daily_remaining_usd (f64) / hard_cap_usd (f64) / adaptive_multiplier (f64) — 3 fields | **無 drift**：1:1 對齊 |
| H4 | `_stats["h4_validation_fail"]` (caller-side at strategist_agent.py:200, 944-950)；validation_pass **目前不計數** | `H4ValidationStats`：validation_fail (u64) / validation_pass (u64) — 2 fields | **部分 drift**：Rust 有 `validation_pass` 但 Python 不計數 → Sub-task 3-2 要新加 `validation_pass` counter |
| H5 | `get_cost_edge_ratio()` 回 `{"cost_edge_ratio", "ai_spend_7d_usd", "paper_pnl_7d_usd", "data_days", "roi_basis", "roi_disclaimer"}` (line 683-691) — 6 keys | `H5CostStats`：ai_spend_7d_usd (f64) / paper_pnl_7d_usd (f64) / cost_edge_ratio (Option<f64>) / data_days (u32) — 4 fields | **可控 drift**：Python 多 2 個 marker key (`roi_basis` / `roi_disclaimer`)；Rust 不解（forward-compat OK），但 Sub-task 3-3 要決定保不保 (推薦：保，純 metadata 不影響 hot-path) |

**結論**：H4 + H5 的 drift 已被本 RFC 識別並寫入 Sub-task 3-2 / 3-3，**不需獨立 Sub-task 3-0**。Pattern C 的 3-0 = 已被本 RFC §2.3 完成。

### 2.4 Pattern 對比決策矩陣

| 評分維度 | A 9 sub-task | B 3 sub-task ★ | C 4 sub-task |
|---|---|---|---|
| Pattern 一致性 | ❌ 與 Phase 2 不一致（過細） | ✅ 鏡 Phase 2 | ✅ 鏡 Phase 2 + audit prelude |
| Sub-task 大小 | ❌ 過細（α 全空） | ✅ 70-80 LOC 各 | 中 |
| 並行收益 | ❌ 串行依賴重 | ✅ 3-1 + 3-2 可並行（不同檔） / 3-3 待 3-1 完成（同檔避撞） | ✅ 同 B |
| ROI vs E2 review 成本 | ❌ 9 commit 9 review | ✅ 3 commit 3 review | 4 commit 4 review |
| Audit 涵蓋 | 中 | ✅ Drift 已併入 3-2/3-3 | ✅ 顯式 3-0 audit |
| 全鏈時間 | ~5d（過細） | **~3.5d**（per PA design plan §11.1） | ~4d |
| **總分** | 1/6 | **6/6** | 5/6 |

**結論：選 Pattern B（3 sub-task per-H 模組）**。

---

## §3 Sub-task 列表 + Dependency Graph

### 3.1 Sub-task 列表

| # | Sub-task | 依賴 | LOC | 並行性 |
|---|---|---|---|---|
| **3-1** | H2 budget integration | Track 1 ✅ + Phase 2 ✅ | ~80 | 與 3-2 並行 |
| **3-2** | H4 validator integration | Track 1 ✅ + Phase 2 ✅ | ~70 | 與 3-1 並行 |
| **3-3** | H5 cost_logging integration | 3-1 完成（同檔 layer2_cost_tracker.py 避雙修衝突） | ~80 | **串行**：在 3-1 之後 |

### 3.2 Dependency Graph（ASCII）

```
[Track 1 H3 Schema Align E1]  ← 硬前置（next session 啟動先驗）
       │
       ▼
┌──────────────────────────────┐
│ Phase 3 啟動                  │
└──────────────────────────────┘
       │
       ├─────────────┬─────────────┐
       ▼             ▼             │
   [3-1: H2]     [3-2: H4]         │
       │             │             │
       │  並行        │  並行        │
       │             │             │
       ▼             │             │
   [3-3: H5]         │             │
       │             │             │
       └─────┬───────┘             │
             ▼                     │
   [Phase 3 完成]                   │
             │                     │
             ▼                     │
   [G3-09 cost_edge_ratio]         │  解阻：H5 (3-3)
             │                     │
   [G8-01 認知 e2e]                │  弱依賴：H5 + H2
                                   │
                                   ▼
                          [Phase 4 5-Agent state]
                                  解阻：3-3 完成（pattern 確立後 Phase 4 鏡此模板）
```

### 3.3 撞檔風險矩陣

| Sub-task pair | 共享文件 | 並行可行 | 緩解 |
|---|---|---|---|
| 3-1 (H2) + 3-2 (H4) | h_state_query_handler.py（兩個 sub-task 各加 1 bucket） | ✅ Yes | 後 commit pull --rebase 自動 merge（add 不衝突 = 不同 dict key） |
| 3-1 (H2) + 3-3 (H5) | **layer2_cost_tracker.py**（兩個 sub-task 都改）+ h_state_query_handler.py | ❌ No（避免雙修同檔） | **串行**：3-3 在 3-1 之後 |
| 3-2 (H4) + 3-3 (H5) | h_state_query_handler.py | ✅ Yes | 同上 |

**派發推薦**（per PM 編排）：
- **第一波**：派 E1-Alpha (Sub-task 3-1) + E1-Beta (Sub-task 3-2) **並行**
- **第二波**（3-1 commit 後）：派 E1-Alpha (Sub-task 3-3)

全鏈 wall-clock：3-1 + 3-2 並行 ~1.5d → 3-3 ~1d → E2/E4 各 0.5d → **3.5d**（per PA design §11.1）

---

## §4 Sub-task 3-1 E1 prompt template（H2 budget integration）

下次 session PM 直接 paste 給 E1（self-contained，無需 PM 補上下文）。

````markdown
## 任務：G3-08 Phase 3 Sub-task 3-1 — H2 budget gate integration

### 背景

G3-08 Phase 3 拆 3 sub-task（H2/H4/H5）。本 sub-task = H2 budget gate 接線到 Rust h_state_cache
gateway。Pattern 鏡 Phase 2 commit `9120948`（H1+H3）。

### 前置驗證（開工前必跑）

```bash
# Track 1 H3 schema align 必先 land
git log --oneline -10 | grep -iE "G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN" || \
  echo "❌ Track 1 not landed - STOP"

# H2 schema (Rust H2BudgetState) 已備
ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release \
  -p openclaw_engine --lib h_state_cache::types"

# Phase 2 healthcheck [20] 仍綠
ssh trade-core "cd ~/BybitOpenClaw/srv && python3 helper_scripts/db/passive_wait_healthcheck.py 2>&1 | grep -i '\[20\]'"
```

### 改動文件

1. `program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_cost_tracker.py`
   - 加 import: `from .h_state_invalidator import invalidate_async as _invalidate_h_state_async`
   - `record_claude_cost()` (line 227) 後加 `_invalidate_h_state_async("h2.budget_consumed")`（H2 = same tracker，預算消耗即觸發）
   - 新增 method `get_h2_snapshot()` (參考 `get_h3_snapshot` line 426 pattern)

2. `program_code/exchange_connectors/bybit_connector/control_api_v1/app/h_state_query_handler.py`
   - `_collect_h_snapshots()` 加 `include_h2` 參數 + 從 `_sw.COST_TRACKER`（或 `STRATEGIST_AGENT.cost_tracker`，看哪個在 strategy_wiring 是 module-level singleton）讀
   - `build_h_state_full_response()` `h_states["h2"] = h2_dict` 接線

3. Tests:
   - `test_h_state_query_handler.py` 加 H2 round-trip case
   - `test_layer2_cost_tracker.py`（如存在）加 H2 snapshot test

### 具體實作

#### layer2_cost_tracker.py 新增 method（參考 h1_thought_gate.py:282 pattern）

```python
def get_h2_snapshot(self) -> dict:
    """Return a thread-safe snapshot of H2 budget state for h_state_cache exposure.
    回傳 H2 預算閘狀態的線程安全 snapshot，供 h_state_cache 暴露使用。

    Schema (PA design §5.2 H2BudgetState parity):
      - daily_remaining_usd: float — 當日剩餘預算 (USD)
      - hard_cap_usd:        float — 當日硬上限 (USD)
      - adaptive_multiplier: float — 自適應倍率（≤ 1.0 = 收縮）

    Pure-read: NO side effects. Acquires only `self._lock` (existing lock).
    純讀取：無副作用。只取 self._lock（既有鎖）。
    """
    with self._lock:
        # check_daily_budget() returns (allowed: bool, remaining: float)
        _allowed, remaining = self.check_daily_budget()
        return {
            "daily_remaining_usd": float(remaining),
            "hard_cap_usd": float(self._config.daily_hard_cap_usd),
            "adaptive_multiplier": float(self._adaptive.multiplier),
        }
```

#### record_claude_cost() invalidate hook（line 227 method body 末尾）

```python
def record_claude_cost(self, session, input_tokens, output_tokens, model_tier) -> float:
    # ... 既有 ...
    self._sync_to_rust_budget(...)  # 既有
    _invalidate_h_state_async("h2.budget_consumed")  # ← 新增（H2 是 budget gate，預算被消耗即推 hint）
    return cost
```

#### h_state_query_handler.py 加 H2 bucket（鏡 Phase 2 H1/H3 pattern）

```python
def _collect_h_snapshots(
    include_h1: bool,
    include_h3: bool,
    include_h2: bool = False,  # ← 新增
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    # ... 既有 H1/H3 ...
    h2_dict: Optional[dict[str, Any]] = None
    if include_h2:
        # H2 SSOT = Layer2CostTracker, accessed via STRATEGIST_AGENT.cost_tracker
        # or strategy_wiring.COST_TRACKER (whichever is the module-level singleton).
        cost_tracker = getattr(strategist, "cost_tracker", None)
        if cost_tracker is not None:
            h2_dict = _safe_snapshot_method(cost_tracker, "get_h2_snapshot")
    return h1_dict, h3_dict, h2_dict
```

（如 `_safe_snapshot` 簽名是 `(parent, attr_name, method_name)`，新增一個 helper `_safe_snapshot_method(parent, method_name)` 給直接 call。）

### 完成標準

- ✅ `cargo test --release -p openclaw_engine --lib h_state_cache` 全綠（baseline + 0 新 = 不變，因 Phase 3 純 Python）
- ✅ `pytest test_h_state_query_handler.py test_layer2_cost_tracker.py -v` 全綠 + 新增 ≥3 H2 test pass
- ✅ env=1 + IPC `query_h_state_full` 回 `{"version": 1, "h_states": {"h1": {...}, "h2": {...}, "h3": {...}}, ...}` 三 bucket 同框
- ✅ env=0 zero overhead（grep `_invalidate_h_state_async` 確認所有 callsite 都進入 env-gated invalidator）
- ✅ healthcheck [20] 仍綠（staleness < 30s）

### Commit message

```
feat(layer2): G3-08 Phase 3 Sub-task 3-1 — H2 budget gate integration

- layer2_cost_tracker.py:
  - new method get_h2_snapshot() returns 3-field dict per PA design §5.2 H2BudgetState
  - record_claude_cost() now invokes _invalidate_h_state_async("h2.budget_consumed")
  - add import: from .h_state_invalidator import invalidate_async as _invalidate_h_state_async

- h_state_query_handler.py: aggregate H2 bucket alongside Phase 2 H1/H3
  - _collect_h_snapshots gains include_h2 flag + pulls from STRATEGIST_AGENT.cost_tracker
  - build_h_state_full_response populates h_states["h2"] when env=1

- tests: +N H2 round-trip cases for query_handler + cost_tracker snapshot

Phase 3 Sub-task 3-1 of 3 (3-2 H4 + 3-3 H5 follow). Per PA RFC
docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g3_08_phase3_subtask_split.md
- Pattern B (per-H module) chosen over A (9 sub-task) and C (audit prelude)
- 3-1 + 3-2 may run in parallel; 3-3 serial after 3-1 (avoid double-edit
  layer2_cost_tracker.py).

Verified: cargo test pass; pytest pass; env=1 IPC returns 3-bucket snapshot;
env=0 zero overhead; healthcheck [20] green.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

### Estimated time

- 樂觀 0.75d / 中位 1d / 悲觀 1.5d
- 並行可與 Sub-task 3-2 同時跑（不同檔 layer2_cost_tracker.py vs strategist_agent.py）

### 一行回報

```
SUB-TASK 3-1 DONE — H2 integration commit <hash> pushed; pytest +N green; IPC 3-bucket OK
```
````

---

## §5 Sub-task 3-2 E1 prompt template（H4 validator integration）

````markdown
## 任務：G3-08 Phase 3 Sub-task 3-2 — H4 validator integration

### 背景

H4 validator (`h4_validator.py:38 validate_ai_output`) 是 stateless function；stats 由 caller
(`strategist_agent.py:200, 944-950`) 在 `self._stats["h4_validation_fail"]` 維護。**目前
`validation_pass` 不計數**，本 sub-task 須補上。Pattern 鏡 Phase 2 commit `9120948`。

### 前置驗證（開工前必跑）

```bash
git log --oneline -10 | grep -iE "G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN" || \
  echo "❌ Track 1 not landed - STOP"

# H4 schema (Rust H4ValidationStats) 已備（2 fields）
ssh trade-core "cd ~/BybitOpenClaw/srv/rust && grep -A 6 'pub struct H4ValidationStats' \
  rust/openclaw_engine/src/h_state_cache/types.rs"
```

### 改動文件

1. `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_agent.py`
   - line 200 附近 `_stats` 初始化加 `"h4_validation_pass": 0,`
   - line 944-950 區塊：`if not validate_ai_output(result)` 分支已寫 `validation_fail` += 1，
     在 `if` **else 分支**（pass 路徑）加：
     ```python
     with self._lock:
         self._stats["h4_validation_pass"] = self._stats.get("h4_validation_pass", 0) + 1
     _invalidate_h_state_async("h4.validation_pass")
     ```
   - 失敗分支 line 950 後加 `_invalidate_h_state_async("h4.validation_fail")`
   - 加 import：`from .h_state_invalidator import invalidate_async as _invalidate_h_state_async`
   - 新增 method `get_h4_snapshot()` 在 StrategistAgent class 內

2. `program_code/exchange_connectors/bybit_connector/control_api_v1/app/h_state_query_handler.py`
   - `_collect_h_snapshots` 加 `include_h4` 參數 + 直接從 `strategist` 讀（caller-side stats）
   - `build_h_state_full_response()` 加 `h_states["h4"] = h4_dict`

3. Tests:
   - `test_strategist_agent.py` 加 H4 snapshot test (validation_fail vs validation_pass 計數)
   - `test_h_state_query_handler.py` 加 H4 round-trip case

### 具體實作

#### strategist_agent.py 新增 method

```python
# ── G3-08 Phase 3: H4 state snapshot accessor ──
# G3-08 Phase 3：H4 狀態 snapshot 存取器

def get_h4_snapshot(self) -> Dict[str, Any]:
    """Return a thread-safe snapshot of H4 validation stats for h_state_cache.
    回傳 H4 驗證統計的線程安全 snapshot。

    Schema (PA design §5.2 H4ValidationStats parity):
      - validation_fail: int — h4_validator.validate_ai_output rejected count
      - validation_pass: int — h4_validator.validate_ai_output accepted count

    H4 stats are caller-side (strategist owns them) because h4_validator
    is a stateless pure function. Phase 3 Sub-task 3-2 added validation_pass
    counter (was missing pre-G3-08).
    H4 stats 由 caller (strategist) 維護（h4_validator 是 stateless 純函式）。
    Phase 3 Sub-task 3-2 補上 validation_pass 計數器（G3-08 前缺）。
    """
    with self._lock:
        return {
            "validation_fail": int(self._stats.get("h4_validation_fail", 0)),
            "validation_pass": int(self._stats.get("h4_validation_pass", 0)),
        }
```

#### strategist_agent.py L944-950 改寫

```python
if not validate_ai_output(result):
    logger.warning(...)
    with self._lock:
        self._stats["h4_validation_fail"] = self._stats.get("h4_validation_fail", 0) + 1
        self._stats["heuristic_evaluations"] += 1
    _invalidate_h_state_async("h4.validation_fail")  # ← 新增
    return _heuristic_evaluate(intel, self.config)

# H4 PASS 路徑（既有就沒計數）
with self._lock:
    self._stats["h4_validation_pass"] = self._stats.get("h4_validation_pass", 0) + 1
_invalidate_h_state_async("h4.validation_pass")  # ← 新增
```

### 完成標準

- ✅ pytest baseline shift +N（H4 snapshot test + H4 query_handler bucket test）
- ✅ env=1 + IPC `query_h_state_full` 回的 `h_states["h4"]` 含 `validation_fail` + `validation_pass` 兩計數
- ✅ env=0 zero overhead（grep `_invalidate_h_state_async("h4.…")` callsite 全 env-gated）
- ✅ healthcheck [20] 仍綠

### Commit message

```
feat(layer2): G3-08 Phase 3 Sub-task 3-2 — H4 validator integration

- strategist_agent.py:
  - new _stats["h4_validation_pass"] counter (was missing pre-G3-08)
  - line 944 if/else: invalidate_async("h4.validation_fail") on reject path,
    invalidate_async("h4.validation_pass") on accept path
  - new method get_h4_snapshot() returns 2-field dict per PA design §5.2

- h_state_query_handler.py: aggregate H4 bucket
  - _collect_h_snapshots gains include_h4 flag + reads strategist.get_h4_snapshot()
  - build_h_state_full_response populates h_states["h4"] when env=1

- tests: +N H4 round-trip cases for query_handler + strategist snapshot

Phase 3 Sub-task 3-2 of 3 (3-1 H2 + 3-3 H5 in parallel/serial). Per PA RFC
docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g3_08_phase3_subtask_split.md

Verified: pytest pass; env=1 IPC h_states.h4 populated; env=0 zero overhead.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

### Estimated time

- 樂觀 0.5d / 中位 0.75d / 悲觀 1d
- 並行 Sub-task 3-1（不同檔）

### 一行回報

```
SUB-TASK 3-2 DONE — H4 integration commit <hash> pushed; validation_pass counter live
```
````

---

## §6 Sub-task 3-3 E1 prompt template（H5 cost_logging integration）

````markdown
## 任務：G3-08 Phase 3 Sub-task 3-3 — H5 cost_logging integration

### 背景

H5 cost stats SSOT = `Layer2CostTracker.get_cost_edge_ratio()` (line 656-692) 回 6-key dict。
Rust mirror `H5CostStats` 解 4 fields（drop 2 metadata key per forward-compat）。本 sub-task =
最後一個 Phase 3 sub-task，**解阻 G3-09 cost_edge_ratio**。

### 前置驗證（開工前必跑）

```bash
# Sub-task 3-1 必先 commit（避免雙修 layer2_cost_tracker.py 衝突）
git log --oneline -5 | grep -iE "Sub-task 3-1.*H2" || \
  echo "❌ Sub-task 3-1 not landed - STOP, run 3-1 first"

# H5 schema 已備
ssh trade-core "cd ~/BybitOpenClaw/srv/rust && grep -A 12 'pub struct H5CostStats' \
  rust/openclaw_engine/src/h_state_cache/types.rs"
```

### 改動文件

1. `program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_cost_tracker.py`
   - `record_claude_cost()` 末尾再加 `_invalidate_h_state_async("h5.claude_cost_recorded")`
     （H2 hint 已在 Sub-task 3-1 加；H5 是同一 tracker 不同視角，加第二 hint）
   - `record_search_cost()` (line 249) 加 `_invalidate_h_state_async("h5.search_cost_recorded")`
   - 新增 method `get_h5_snapshot()` 包裹 `get_cost_edge_ratio()` 過濾 metadata

2. `program_code/exchange_connectors/bybit_connector/control_api_v1/app/h_state_query_handler.py`
   - `_collect_h_snapshots` 加 `include_h5` + 從 cost_tracker 讀
   - `build_h_state_full_response` 加 `h_states["h5"]`

3. Tests:
   - `test_layer2_cost_tracker.py` 加 H5 snapshot test
   - `test_h_state_query_handler.py` 加 H5 round-trip case
   - **回歸 test**：env=1 + IPC `query_h_state_full` 回 5 bucket（H1+H2+H3+H4+H5 同框）

### 具體實作

#### layer2_cost_tracker.py 新增 method

```python
def get_h5_snapshot(self) -> dict:
    """Return a thread-safe snapshot of H5 cost stats for h_state_cache exposure.
    回傳 H5 成本統計的線程安全 snapshot，供 h_state_cache 暴露使用。

    Schema (PA design §5.2 H5CostStats parity, drop metadata for hot-path):
      - ai_spend_7d_usd:   float — 7d AI 花費 (USD)
      - paper_pnl_7d_usd:  float — 7d Paper 模擬 PnL (USD)
      - cost_edge_ratio:   Optional[float] — paper_pnl / ai_spend (None when data_days < ADAPTIVE_MIN_DAYS)
      - data_days:         int — 累積資料天數

    NOTE: get_cost_edge_ratio() returns 6 keys (含 roi_basis / roi_disclaimer
    metadata strings). Rust H5CostStats only解 4 fields per PA design §5.2 (forward-compat
    keeps the metadata strings present in JSON; Rust serde silently drops unknown).
    註：get_cost_edge_ratio() 回 6 個 key（含 roi_basis / roi_disclaimer 元資料字串）。
    Rust H5CostStats 依 PA design §5.2 只解 4 fields（forward-compat：JSON 中 metadata 仍在，
    Rust serde 靜默忽略未知 key）。
    """
    full = self.get_cost_edge_ratio()
    return {
        "ai_spend_7d_usd": float(full.get("ai_spend_7d_usd", 0.0)),
        "paper_pnl_7d_usd": float(full.get("paper_pnl_7d_usd", 0.0)),
        "cost_edge_ratio": full.get("cost_edge_ratio"),  # Optional[float], may be None
        "data_days": int(full.get("data_days", 0)),
    }
```

#### record_claude_cost / record_search_cost invalidate hooks

```python
def record_claude_cost(self, session, input_tokens, output_tokens, model_tier) -> float:
    # ... 既有 ...
    self._sync_to_rust_budget(...)
    _invalidate_h_state_async("h2.budget_consumed")  # ← Sub-task 3-1 已加
    _invalidate_h_state_async("h5.claude_cost_recorded")  # ← 本 sub-task 新增
    return cost

def record_search_cost(self, session, provider, cost_usd) -> None:
    # ... 既有 ...
    _invalidate_h_state_async("h5.search_cost_recorded")  # ← 新增
```

### 完成標準

- ✅ pytest baseline shift +N（H5 snapshot test + 5-bucket round-trip test）
- ✅ env=1 + IPC `query_h_state_full` 回 5 bucket（h1/h2/h3/h4/h5 同框）
- ✅ Phase 3 完成 — `query_h_state_full` 回 `version: 1` + 5 bucket
- ✅ healthcheck [20] 仍綠
- ✅ **G3-09 unblock**：next session 可派 G3-09 cost_edge_ratio 演算法（Rust 端可走 IPC pull
  H5 cost_edge_ratio 即時讀）

### Commit message

```
feat(layer2): G3-08 Phase 3 Sub-task 3-3 — H5 cost_logging integration (Phase 3 complete)

- layer2_cost_tracker.py:
  - new method get_h5_snapshot() wraps get_cost_edge_ratio() (drop metadata for hot-path)
  - record_claude_cost() now also invokes invalidate_async("h5.claude_cost_recorded")
  - record_search_cost() now invokes invalidate_async("h5.search_cost_recorded")

- h_state_query_handler.py: aggregate H5 bucket — Phase 3 5-bucket complete
  - _collect_h_snapshots gains include_h5 flag
  - build_h_state_full_response populates h_states["h5"] when env=1
  - env=1 IPC query_h_state_full now returns h1/h2/h3/h4/h5 5-bucket snapshot

- tests: +N H5 round-trip cases + 5-bucket regression test

Phase 3 final sub-task. Per PA RFC
docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g3_08_phase3_subtask_split.md
- 3-1 (H2) + 3-2 (H4) parallel; 3-3 (this) serial after 3-1 (avoid double-edit)
- G3-09 cost_edge_ratio algorithm now unblocked (Rust hot-path can pull H5
  ai_spend_7d / paper_pnl_7d via IPC in <10s freshness)
- Phase 4 (5-Agent state events) unblocked: Phase 3 confirms per-module
  pattern works, Phase 4 mirrors same template

Verified: pytest pass; env=1 IPC 5-bucket; env=0 zero overhead; healthcheck [20] green.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

### Estimated time

- 樂觀 0.75d / 中位 1d / 悲觀 1.5d
- **必須串行**在 Sub-task 3-1 之後（同檔 layer2_cost_tracker.py 避雙修衝突）

### 一行回報

```
SUB-TASK 3-3 DONE — H5 integration commit <hash> pushed; Phase 3 5-bucket live; G3-09 unblocked
```
````

---

## §7（不適用）Sub-task 4

Pattern B 推薦 = 3 sub-task，**不需 Sub-task 4**。Pattern C 的 4 sub-task（含 schema audit prelude）已被本 RFC §2.3 證明 redundant（H4 + H5 drift 已寫進 3-2 / 3-3）。

**Phase 3 整合 smoke 不獨立 sub-task** — 已分散為各 sub-task 的「完成標準」中的 IPC round-trip 測試 + healthcheck [20]，不需額外整合 sub-task。

---

## §8 Risk 識別 + Mitigation

### 8.1 風險矩陣

| # | 風險 | 機率 | 影響 | 緩解 |
|---|---|---|---|---|
| R1 | 雙 sub-task 同時改 layer2_cost_tracker.py（3-1 + 3-3）git conflict | 中 | 中（重 rebase 即可） | **串行強制**（3-3 在 3-1 後派發） |
| R2 | Rust schema (H2/H4/H5) 與 Python snapshot 命名 silent drift | 低（已 audit）| **高**（silent default-zero per H3 RFC §1.1）| **本 RFC §2.3 H2/H4/H5 schema audit 已完成**：H2 1:1 對齊 / H4 補 validation_pass / H5 4-field subset OK（forward-compat 容忍 metadata） |
| R3 | invalidate_async daemon thread 在 H5 cost call 高頻 spawn 過多 | 中 | 中（ memory growth） | invalidate_async 內部已 fire-and-forget + daemon thread + try/except；per Phase 1 pytest stress test 已驗 100k call <30s。Phase 3 H5 真實流量遠小於 stress baseline |
| R4 | multi-worker uvicorn 4 worker 各 own Layer2CostTracker singleton → query_h_state_full 看到隨機某 worker view | 高 | 低（Phase 1+2 已 accept）| Phase 1 文檔已敘明（PA design §8.3 Risk 2），observability 字段 acceptable；Phase 4+ 評估 leader-only flock |
| R5 | env=1 切換時舊 worker 已 spawn invalidator daemon, 新 worker 沒 → 不一致 | 低 | 低（observability only）| Phase 1C strategy_wiring init 已驗，env flip 需 uvicorn restart |
| R6 | H2/H4/H5 schema 演化（如 Phase N+ 加新 cost field）需 Rust 跟改 | 中 | 低（forward-compat）| `#[serde(default)]` + HashMap fallback 已驗（H1/H3 test pattern）。新增 field 直接加 Python snapshot key + Rust types.rs 補 field（rebuild 後可讀）；舊 Rust binary 看到新 key 時靜默丟（觀察可接受） |

### 8.2 跨 H state polling 線程安全（PA Risk 5 升級）

Phase 1 Rust h_state_cache 已 spawn 1 個 daemon thread（每 10s poll）。
Phase 2 H1+H3 已加 callsite-side fire-and-forget invalidate_async（per-call spawn daemon thread, daemon 用後即死）。

**Phase 3 加入後總 process-global 線程數**：
- Phase 1 daemon: 1
- Phase 2 invalidate_async：每 H1/H3 call spawn 1 ephemeral daemon thread（生命週期 < 1s typical）
- Phase 3 H2/H4/H5 invalidate_async：each call spawn 1 ephemeral daemon thread

**Per Phase 1 stress test**：100k invalidate < 30s = ~3000 thread/sec spawn rate，daemon 用後即死，max alive < 100 typical。**安全**。

但**潛在 spawn rate 升級警告**：H5 record_claude_cost 在 ML pipeline 訓練/強化 cycle 高峰可能達 10-50/sec。Phase 3 land 後 24h dogfood 觀察 thread spawn rate，>500/sec 持續即考慮加 batch debounce 機制（300ms window 內合併）。

### 8.3 env-gate 策略：每個 H state 是否獨立 env var 還是共用

**推薦：保持共用 `OPENCLAW_H_STATE_GATEWAY=1`**（Phase 1+2 既有設計）

| 選項 | 優 | 劣 |
|---|---|---|
| A. 共用（OPENCLAW_H_STATE_GATEWAY=1）★ 推薦 | 簡單；統一 on/off；rollback 一鍵 | 不能 partial enable（如只開 H2 不開 H5）|
| B. per-H env var (OPENCLAW_H_STATE_H2=1 / OPENCLAW_H_STATE_H5=1 ...) | 可 partial enable | 8 env var（H1-H5 + 5-Agent + status + 主開關）= 維護複雜 |

**Recommend A**：Phase 3 預期 land 後一直開（H 狀態觀測無 negative 影響），分項 on/off 沒有實際 use case。Future per-H toggle 需求出現時再評估。

### 8.4 Phase 3 落地後第一週監控（healthcheck [20] 升級項）

`passive_wait_healthcheck.py [20]` Phase 1C 已加（基於 `get_h_state_status` IPC）。Phase 3 land 後可選升級加 5-bucket parity check：

```python
def check_h_state_5bucket_parity() -> tuple[str, str]:
    """[Xa] H State Gateway 5-bucket parity (Phase 3+)"""
    if os.environ.get("OPENCLAW_H_STATE_GATEWAY") != "1":
        return "PASS", "gateway disabled"
    snap = ipc_call("query_h_state_full", {})
    h_states = snap.get("h_states", {})
    expected = {"h1", "h2", "h3", "h4", "h5"}
    present = set(h_states.keys())
    missing = expected - present
    if missing:
        return "FAIL", f"missing buckets: {sorted(missing)}"
    return "PASS", f"5/5 buckets present (version={snap.get('version')})"
```

可在 Sub-task 3-3 commit 同次加（未列為 Phase 3 hard requirement，避免 sub-task scope creep）。

---

## §9 Phase 4 Unblock Path + G3-09 Dependency

### 9.1 Phase 4（5-Agent state events）unblock

**Phase 4 範圍**（per PA design plan §10.2.4 + §11.1）：5 Agent (Strategist / Guardian / Analyst / Executor / Scout) 各加 `get_stats_snapshot()` + invalidate hook，h_state_query_handler 加 `agent_states` bucket（per-agent state）。

**unblock condition**：Sub-task 3-3 完成（Phase 3 5-bucket 整合驗證 pattern 可行）即可派 Phase 4。

**為什麼是 3-3 而非 3-1/3-2**：
- 3-1 + 3-2 並行 = 兩個 H 模組驗證 pattern；3-3 完成 = 三模組驗證 + Phase 3 整體完成 = 能 confidently 移植 pattern 到 5 Agent
- 3-3 使用最複雜 SSOT（Layer2CostTracker.get_cost_edge_ratio 內含 6-key + Optional[float]），驗證 forward-compat 解 metadata 案例 = Phase 4 5 Agent 任意 stats schema 模板

**Phase 4 sub-task split 預告**（不在本 RFC scope，Phase 3 完成後 PA 另寫 RFC）：
- 推薦同 Pattern B：5 sub-task，每 Agent 1 個（Strategist 最複雜放最後）
- 預估 wall-clock 4d (per PA design §11.1) → 5 sub-task × ~0.8d each

### 9.2 G3-09 cost_edge_ratio 演算法 unblock

**G3-09 描述**（per TODO.md Wave 2 P3）：Rust hot-path 即時讀 `cost_edge_ratio`，超 0.8 觸發風控降頻 / 縮倉。

**強依賴 Sub-task 3-3**：
- Sub-task 3-3 完成後 Rust `cache.snapshot().h5.cost_edge_ratio` 可即時讀（DashMap lookup ≤1ms p99）
- Rust 端可在 intent_processor 或 risk_gate hot-path 走 `query_h_state(cache, "h5", "cost_edge_ratio")` 取值
- 讀取頻率：每 tick / 每 intent，受益於 Phase 1 cache pattern（不走 IPC roundtrip）

**G3-09 派發前置**：Sub-task 3-3 commit 後 24h dogfood 觀察 H5 數值流通 + healthcheck [20] 升級版確認 5-bucket parity 後可派。

### 9.3 完整 unblock graph

```
Phase 1 ✅ (commits aa287c4 / 1c7b20e / 5943337)
   ↓
Phase 2 ✅ (commits 9120948 + f2ed286 — H1+H3)
   ↓
Track 1 H3 Schema Align (next session 啟動先驗 ✅)
   ↓
   ┌──────────────┬──────────────┐
   ▼              ▼              │
Sub-task 3-1   Sub-task 3-2      │
(H2 budget)    (H4 validator)    │
   │              │              │
   └──────┬───────┘              │
          ▼                      │
   Sub-task 3-3                  │
   (H5 cost_logging)             │
          │                      │
          ├──── unblock ──→ G3-09 cost_edge_ratio
          │
          ├──── unblock ──→ Phase 4 5-Agent state events
          │
          └──── (with Phase 4) unblock ──→ G8-01 認知 e2e
```

---

## §10 治理對照（CLAUDE.md §二 16 根原則 + §四 硬邊界）

### 10.1 16 根原則

| # | 原則 | 狀態 |
|---|---|---|
| #1-#10 | 同 PA design plan §8.2（observability extension only）| ✅ 全綠 |
| #6 失敗默認收縮 | env=0 default + invalidator/poller 雙端 fail-closed default | ✅ |
| #13 AI 成本感知 | Phase 3 Sub-task 3-3 解阻 G3-09 → 強化 #13 | ⭐ |
| #15 多 Agent 協作 | Phase 4 unblock path 已標 | 🟡（Phase 4 task）|

### 10.2 §四 5 項 live 硬邊界

| 邊界 | 觸碰 | 說明 |
|---|---|---|
| live_reserved | ❌ | 純 observability |
| Operator 角色 auth | ❌ | 純 observability |
| OPENCLAW_ALLOW_MAINNET | ❌ | 不影響 Mainnet gate |
| API key/secret slot | ❌ | 不影響 secret resolution |
| authorization.json HMAC | ❌ | 不影響 5min re-verify |

**全 5 項零觸碰** ✅

### 10.3 §九 Singleton table 維護

Phase 1C 已登記 `_H_STATE_INVALIDATOR` + `HStateCacheSlot`（Rust）。Phase 3 不新增 singleton（重用 invalidator + STRATEGIST_AGENT.cost_tracker singleton）。**§九 不需更新**。

### 10.4 §七 文件大小

| 檔 | Phase 3 後預計 LOC | 警告線 800 / 硬上限 1200 |
|---|---|---|
| layer2_cost_tracker.py | 726 + ~30 (Sub-task 3-1) + ~25 (Sub-task 3-3) = ~781 | ⚠️ 接近警告線（不超）|
| strategist_agent.py | 1170 + ~25 (Sub-task 3-2) = ~1195 | ⚠️ 接近硬上限（不超） |
| h_state_query_handler.py | 419 + ~50 (3 sub-task 共 ~50) = ~470 | ✅ 安全 |

**警告**：Sub-task 3-2 land 後 strategist_agent.py 將達 ~1195 行，距 §九 1200 行硬上限 5 行。Phase 4 的 strategist Agent stats hook 不能再加（會超）。

**緩解**：Phase 4 Strategist sub-task 必然要先觸發 strategist_agent.py 拆檔（類似 G5-08 strategist_scheduler split pattern）。本 RFC 不解此問題（屬 Phase 4 範圍），但 PM 派發 Phase 4 Strategist sub-task 前必先評估拆檔。

---

## §11 沒做的事（E1/E2 領域）

- 沒寫 Sub-task 3-1/3-2/3-3 任何實作代碼（純 design + prompt template）
- 沒派 sub-agent（純 PA 主 agent 串行讀 + 寫）
- 沒跑 cargo test / pytest（E1/E4 任務）
- 沒驗 Track 1 是否已 land（next session PM 啟動前驗）
- 沒擴範圍到 Phase 4 5-Agent split（屬 Phase 3 完成後 PA 另寫 RFC）
- 沒擴範圍到 G3-09 cost_edge_ratio 演算法（屬 G3-09 ticket）

---

## §12 教訓備忘（給未來 PA / PM）

1. **Phase 1+2 commit pattern 收斂後，Phase 3+ sub-task 拆分應鏡 Phase 2**（Pattern B 1-模組-1-sub-task），不需重新發明 9-sub-task 細拆 (Pattern A) 或 audit-prelude 結構 (Pattern C)。
2. **「per-H 模組整鏈」優於「Rust/Python/接線三層拆」**：Phase 3 Rust 0 改動，三層拆會出現空 sub-task。Pattern 適用條件 = Phase 1A 已建好 schema + handler 架構。
3. **同檔雙 sub-task 強制串行**：3-1 + 3-3 都改 layer2_cost_tracker.py，並行會 conflict。Sub-task split 時必先 grep `git diff --stat` 預測 = 並行可行性的硬性 check。
4. **H4 stateless validator 的 stats 由 caller 維護**是反模式特例（H1/H3 stats 在自身 class）。Sub-task 3-2 必加 `validation_pass` counter（Phase 3 前缺，silent regression 一直存在）。
5. **schema mirror audit 應與 sub-task 拆分同 RFC 完成**，不需獨立 audit sub-task（Pattern C）— 本 RFC §2.3 證明 audit + 改動推薦可一份報告完成。
6. **strategist_agent.py 即將觸 §九 1200 硬上限**：Phase 4 Strategist sub-task 必先拆檔。本 RFC §10.4 已預警，Phase 4 RFC 必須包含拆檔 sub-task。

---

## §13 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|---|---|---|
| 2026-04-26 | G3-08 Phase 3 sub-task split design（推 Pattern B 3 sub-task / ETA 3.5d wall-clock） | workspace/reports/2026-04-26--g3_08_phase3_subtask_split.md |

---

**全文完。next: PM 啟動 next session 先驗 Track 1 H3 Schema Align E1 是否已 land + cargo test 綠 → 派 Sub-task 3-1 (E1-Alpha) + 3-2 (E1-Beta) 並行 → 3-1 commit 後派 3-3 (E1-Alpha 復用)。Phase 3 完成後 PM 評估 Phase 4 拆檔需求 + 派 G3-09 cost_edge_ratio。**
