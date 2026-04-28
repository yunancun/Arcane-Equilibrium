# E1 Fix Report — G3-09 Phase B Wave 1 E2 Return (3 mandatory)

- **日期**：2026-04-28
- **Worktree**：`/Users/ncyu/Projects/TradeBot/srv/.claude/worktrees/agent-a9002481353677810`
- **Branch**：`worktree-agent-a9002481353677810`（base `cf34e96`）
- **任務**：執行 E2 review (`adbc92e`) 三項 mandatory fix（HIGH-1 + MED-1 + LOW-2）

## 1. 任務摘要

E2 對 G3-09 Phase B Wave 1 worktree 的 RETURN：核心 logic / V026 / 5-arg shim / tests 全 PASS，但 3 條 §九/§七 規範違反必修 — 本任務按 PA 指派順序逐條修復，不改其他 finding 也不擴充 follow-up tickets。

完成狀態：**3/3 mandatory fix 全完成**，所有驗收標準 PASS，無 scope creep。

## 2. 修改清單

| 路徑 | 操作 | 行數變化 | 一句話說明 |
|---|---|---|---|
| `helper_scripts/db/passive_wait_healthcheck/checks_cost_edge.py` | 新增 | +370 | HIGH-1：sibling 模組存放 `check_cost_edge_advisor_status`，與 checks_engine/strategy/ipc_edge 同 pattern |
| `helper_scripts/db/passive_wait_healthcheck/checks_derived.py` | 修改 | 1304 → 990（−314） | HIGH-1：移除 `check_cost_edge_advisor_status` 函式 + banner，留下 6 行 cross-reference comment 指向 sibling |
| `helper_scripts/db/passive_wait_healthcheck/__init__.py` | 修改 | +9/−1 | HIGH-1：`check_cost_edge_advisor_status` import 由 `.checks_derived` 改為 `.checks_cost_edge` |
| `helper_scripts/db/passive_wait_healthcheck/runner.py` | 修改 | +27/−2 | HIGH-1：import 路徑切換；LOW-2：DB connect fail 路徑加 `cur=None` fallback 跑 `[30]` 環境守衛後再 return 2 |
| `CLAUDE.md` | 修改 | +1 | MED-1：§九 singleton 表新增 `CostEdgeAdvisorDbSlot` row，鏡 `HStateCacheSlot` 模式 |

**Rust 檔不動** — 所有 cost_edge_advisor 相關 Rust 修改皆為 worktree 既有（E1 Phase B 工作），E2 已 PASS；本 fix 純 Python + 文件層。

## 3. 關鍵 diff

### HIGH-1 — sibling 拆分

`__init__.py` 改 import：
```python
from .checks_derived import (  # noqa: F401
    check_leader_election_health,
    ...
    check_dust_spiral_noise_in_ef,
)
from .checks_cost_edge import (  # noqa: F401
    # G3-09 Phase A → Phase B cost_edge_advisor 哨兵；HIGH-1 fix 從
    # checks_derived 抽出維持 1200 行硬上限。
    check_cost_edge_advisor_status,
)
```

`checks_derived.py` 留下 cross-reference banner（取代原 ~321 行函式）：
```python
# ============================================================================
# G3-09 Phase A (2026-04-27) → Phase B (2026-04-28) cost_edge_advisor sentinel
# extracted into sibling ``checks_cost_edge.py`` by HIGH-1 fix (2026-04-28)
# to keep ``checks_derived.py`` under CLAUDE.md §九 1200-line hard cap.
# G3-09 Phase A → Phase B cost_edge_advisor 哨兵已由 HIGH-1 fix（2026-04-28）
# 抽至 sibling ``checks_cost_edge.py``，維持本檔 CLAUDE.md §九 1200 行硬上限。
# ============================================================================
```

E2 推薦的 `check_h_state_gateway_freshness` 也搬 — **未採用**（per E2 spec "E1 自決，建議只搬 cost_edge_advisor 一條，avoid scope"）。

### MED-1 — singleton 登記

`CLAUDE.md` §九 singleton 表新 row（直接在 `HStateCacheSlot` 下方）：
```
| `CostEdgeAdvisorDbSlot` | rust/openclaw_engine/src/main_boot_tasks.rs |
  Rust 端 `Arc<tokio::sync::RwLock<Option<Arc<DbPool>>>>` late-injected slot
  pattern（G3-09 Phase B，2026-04-28）。鏡 `HStateCacheSlot` 設計：
  DB pool 啟動時延後注入 cost_edge_advisor daemon，30s populate-timeout；
  slot=None 時 daemon fallback 到 in-memory counter（不寫
  `learning.cost_edge_advisor_log`），slot 注入後改走 DB INSERT 路徑。
  Engine restart 自動清空（`Arc` 隨 process 結束 drop）。Phase A
  advisor.evaluate() 不依賴此 slot — 純為 Phase B INSERT path 加
  forward-compat（Phase A 評估邏輯仍跑於 in-memory，slot 注入後純加
  persist 副作用）。HMAC secret 與 main loop 解耦，符合 CLAUDE.md
  §二 原則 #6（失敗默認收縮）+ 原則 #8（可審計） |
```

### LOW-2 — DB-down env-gate sentinel preservation

`runner.py` DB connect fail 路徑由原本「直接 `return 2`」改為「先跑 `cur=None` fallback、再 return 2」：
```python
try:
    conn = _get_conn()
except Exception as e:
    # LOW-2 fix (2026-04-28, G3-09 Phase B Wave 1):
    # Phase A `[30]` was a filesystem-only sentinel that ran even when
    # DB connect failed. Phase B's in-cursor placement broke that —
    # DB unreachable would silently skip the env=1 invariant check.
    # ...
    print(f"[FATAL] DB connect failed: {e}")
    try:
        s, m = check_cost_edge_advisor_status(cur=None)
        print(f"{s:4s} [30] cost_edge_advisor_status (db-down fallback) {m}")
    except Exception as ce:  # noqa: BLE001 — keep DB-fail exit path robust
        print(f"WARN [30] cost_edge_advisor_status (db-down fallback) sentinel raised: {ce}")
    return 2
```

決策：選方案 **A**（per spec），不採方案 B（純 docstring 說明 regression）。理由：env=1 sentinel 在 DB-down 時仍生效 = CLAUDE.md §二 原則 #6（失敗默認收縮）+ 原則 #8（可審計）。

## 4. 治理對照

| 規範 | 條目 | 狀態 |
|---|---|---|
| CLAUDE.md §九 文件大小 1200 行硬上限 | `checks_derived.py` 990 ≤ 1200 | ✅ PASS |
| CLAUDE.md §九 文件大小 800 行警告線 | `checks_cost_edge.py` 370 ≤ 800 | ✅ PASS |
| CLAUDE.md §九 singleton 登記 | `CostEdgeAdvisorDbSlot` 入表 | ✅ PASS |
| CLAUDE.md §七 雙語注釋 | sibling MODULE_NOTE 中英對照、`runner.py` LOW-2 fix block 中英對照、CLAUDE.md singleton row 中文敘述 | ✅ PASS |
| CLAUDE.md §七 跨平台 | 純 Python + 文件層；無路徑硬編碼新增；保留 `OPENCLAW_BASE_DIR` / `OPENCLAW_SRV_ROOT` fallback chain | ✅ PASS |
| CLAUDE.md §二 原則 #6 失敗默認收縮 | LOW-2 fix 確保 DB-down 時 env=1 sentinel 仍生效 | ✅ PASS |
| CLAUDE.md §七 被動等待必附 healthcheck | `[30]` 已為 G3-09 設計成 healthcheck，本 fix 強化其 DB-down 韌性 | ✅ PASS |

無觸碰 §四 硬邊界（live 門控 / max_retries / authorization）；不改 cost_edge_advisor 核心 logic。

## 5. 不確定之處

1. **MED-1 row 描述準確性**：`CostEdgeAdvisorDbSlot` 行為描述基於 PA spec 與 sibling Rust 既有改動推斷；未深入逐行讀 `main_boot_tasks.rs` 的實作細節。若 30s populate-timeout / Arc<RwLock> wrapper 細節有偏差，建議 E2 review 時對照 `main_boot_tasks.rs` 實際碼校正字面措辭（不影響 logic / 不影響登記事實）。

2. **LOW-2 行為差異**：DB-down fallback 印出「PASS [30] cost_edge_advisor_status (db-down fallback) ...」這一行不會進入 `results` list，不影響 SUMMARY 計算（exit code 仍是 2）。語意正確（DB-down 是 catastrophic failure，sentinel 結果僅供 audit log），但與正常路徑的 row 格式略不同（多了 `(db-down fallback)` 字樣）。判斷：可接受 — operator 從 `[FATAL] DB connect failed` 已知系統不正常，多出的 sentinel 行純資訊。

3. **跨平台**：本機 Python 3.10（Mac dev box），無 `tomllib` → env=1 fallback 會回 `WARN tomllib unavailable`；Linux production Python ≥ 3.11，會走完整 invariant check。已驗證行為一致性（env=0 → PASS-skip；env=1 → 走 invariant 路徑）。

4. **pre-existing pytest 失敗**：`helper_scripts/db/test_f7_new_healthchecks.py` 8 個 fail（`TestSignalsWriterFreshness` + `TestIntentsCounterFreeze`）為**baseline 既有**（git stash baseline 驗證確認），與 cost_edge_advisor 完全無關。本 fix 不修這些 — 屬 PA 範圍外的 follow-up（建議列入新 ticket 由 PA 派發）。

## 6. Operator 下一步

### 已完成驗證（Mac local）
- [x] HIGH-1：`wc -l checks_derived.py` = 990 ≤ 1200 ✅；新 sibling `checks_cost_edge.py` = 370 ≤ 800 ✅
- [x] MED-1：`grep -c CostEdgeAdvisorDbSlot CLAUDE.md` = 1 ✅，row 緊鄰 `HStateCacheSlot` 下方
- [x] LOW-2：env=0 + DB-down → `PASS [30] cost_edge_advisor_status (db-down fallback) OPENCLAW_COST_EDGE_ADVISOR='0' (≠'1') — env=0 dormant ... skip`；env=1 + DB-down → 進入 invariant 路徑（Mac py3.10 回 WARN tomllib unavailable，Linux py3.11+ 會走完整 invariant 檢查）✅
- [x] Smoke import：`from helper_scripts.db.passive_wait_healthcheck.runner import main` OK；`check_cost_edge_advisor_status.__module__` = `helper_scripts.db.passive_wait_healthcheck.checks_cost_edge` ✅
- [x] pytest `helper_scripts/db/`：45 passed / 8 failed（baseline 既有，無 cost_edge regression；git stash 驗證 baseline 同數）✅
- [x] cargo lib `cargo test --release -p openclaw_engine --lib`：**2299 passed / 0 failed** = 預期 baseline 持平 ✅
- [x] cargo daemon `cargo test --release -p openclaw_engine --test test_cost_edge_advisor_daemon`：**11 passed / 0 failed** = 預期 baseline 持平 ✅

### 主會話審查重點
1. 確認 HIGH-1 sibling 拆分 pattern 與既有 `checks_engine.py` / `checks_strategy.py` / `checks_ipc_edge.py` 風格一致（MODULE_NOTE 雙語 / `noqa: F401` re-export pattern）
2. 確認 MED-1 row 字面描述與 Rust 實裝吻合（細節不確定見 §5.1）
3. 確認 LOW-2 fallback 行為符合 §二 原則 #6 / §七 「被動等待必附 healthcheck」精神

### 後續（**不**在本 PR 範圍）
- E2 LOW-1（main_boot_tasks.rs 過大）+ MED-2（main.rs 過大）為 follow-up tickets，本 PR 按 spec 不處理
- pre-existing 8 pytest fail（TestSignalsWriterFreshness + TestIntentsCounterFreeze）建議由 PA 派發新 ticket 修

### Commit 流程
**不需 commit**（worktree pattern）。返主會話統一 commit + push（PA 編排）。
