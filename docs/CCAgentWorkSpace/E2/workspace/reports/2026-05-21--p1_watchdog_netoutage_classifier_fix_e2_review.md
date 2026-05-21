# E2 PR Adversarial Review — P1-WATCHDOG-NETOUTAGE-CLASSIFIER-FIX · 2026-05-21

- Task: `P1-WATCHDOG-NETOUTAGE-CLASSIFIER-FIX`
- E1 report: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-21--p1_watchdog_netoutage_classifier_fix.md`
- Reviewer: E2
- Branch / commit: main · unstaged WIP (engine_watchdog.py / test_canary.py / E1 memory)
- Diff stats: `helper_scripts/canary/engine_watchdog.py +202 −33` / `helper_scripts/canary/test_canary.py +143 −5`
- Production runtime: NOT deployed; source-only PR
- Verdict: **RETURN to E1**（1 HIGH finding + 2 MEDIUM）

---

## 改動範圍

- `helper_scripts/canary/engine_watchdog.py` 1369 → 1501（+132 行 net）— 強化 `classify_engine_failure` from 1-gate to 4-gate + ambiguous-source guard；抽出 3 個 helper
- `helper_scripts/canary/test_canary.py` 723 → 857（+129 行 net）— `TestEngineFailureClassifier` 加 4 新 test + 1 既有 test 改意圖

調用方驗證：
- `classify_engine_failure` 全 repo 僅 1 個 production caller (`on_engine_crash` L614)
- 回傳型別不變（`"network_outage"` / `"engine_crash"`，無新枚舉值）
- `on_engine_crash` switch case unchanged（仍只區分這兩種）；caller 不需改

---

## 8 條 reviewer checklist

| Item | Status | Note |
|---|---|---|
| 改動範圍與 PA 方案一致 | OK | 純 classifier 強化，未動 strike / auto-restart / on_engine_crash 主流程 |
| 沒有 except:pass 或靜默吞異常 | OK | `OSError` 被收集到 `read_errors` list；最終 fail-closed default `engine_crash` |
| 日誌使用 %s 格式 | OK | 既有 logger.warning 用 `%s` |
| 新 API 端點 + operator_role | N/A | 純 internal helper，無 HTTP endpoint |
| HTTPException raise 順序 | N/A | 無 FastAPI |
| detail=str(e) 改 Internal server error | N/A | 無 FastAPI |
| asyncio 路由無 threading.Lock | N/A | 純同步 |
| 沒私有屬性穿透 | OK | 全 public helpers |

---

## OpenClaw §3 checklist

| Item | Status | Note |
|---|---|---|
| 3.1 跨平台 grep | OK | 無 `/home/ncyu` / `/Users/[^/]+` 硬編碼 |
| 3.2 注釋規範 | OK | 新注釋中文為主，技術 ID 保留英文；MODULE_NOTE 風格符合 |
| 3.3 Rust unsafe | N/A | 純 Python |
| 3.4 IPC schema 一致 | N/A | 純內部 |
| 3.5 Migration Guard | N/A | 無 SQL |
| 3.6 healthcheck 配對 | N/A | 不新增被動等待 TODO |
| 3.7 singleton/monkey-patch | N/A | 無 singleton 新增 |
| 3.8 文件大小 | OK | engine_watchdog.py 1501 < 2000 hard cap（已記錄 >800 exception）；test_canary.py 857 < 800 邊界，需注意（未超） |
| 3.9 Bybit API | N/A | 不觸 `/v5/*` |
| 3.10 P0/P1 caller proof | OK | 提供 caller chain `on_engine_crash → classify_engine_failure`；無其他 caller |
| 3.11 ML training invariant | N/A | 不觸 ML pipeline |

---

## 對抗反問與實證（28 個 adversarial probes）

E2 用 `python3 -c "..."` 手寫 28 個 adversarial scenario，逐個跑 classifier 驗收。摘要：

| Probe | 場景 | Expected | Actual | Verdict |
|---|---|---|---|---|
| 1 | aggregate 5 matches / 40 lines = 12.5% | network_outage | network_outage | OK |
| 2 | 5 DNS / 20 tail = 25% 邊界 | network_outage | network_outage | OK |
| 3 | **5 conn refused + 1 `pool timed out` (real PG)** | engine_crash（保守） | **network_outage** | **FALSE POSITIVE — HIGH** |
| 4 | 5x `ws stream reset` (不在 patterns 內) | engine_crash | engine_crash | OK |
| 5 | 3 DNS active + no rotated → < 5 MIN_MATCHES | engine_crash | engine_crash | OK |
| 6 | 4 active DNS + 1 rotated DNS → (d) aggregate 5/40=12.5% | network_outage | network_outage | OK |
| 7 | rotated permission denied (OSError) → fallback | engine_crash | engine_crash | OK |
| 8 | active 5 DNS + rotated 1 sqlx → guard 跨檔降級 | engine_crash | engine_crash | OK |
| 9 | active panic + rotated 10 DNS → (a) override | engine_crash | engine_crash | OK |
| 10 | active 4 + rotated 4 DNS + 1 sqlx → guard 抑制 aggregate | engine_crash | engine_crash | OK |
| 12 | 1 active DNS + 4 rotated DNS = 5/40=12.5% | network_outage | network_outage | OK |
| 13 | 1h-old rotated 10 DNS（超出 15min 窗口）+ active 3 DNS | engine_crash | engine_crash | OK |
| 14 | tail 邊界 5 DNS + 15 INFO | network_outage | network_outage | OK |
| 16 | head sqlx 在 tail 外 + tail 5 DNS | network_outage | network_outage | OK（tail 機制正確） |
| 17 | ANSI 包裹 5 DNS (real Rust tracing format) | network_outage | network_outage | OK |
| 18 | **ANSI 5 conn refused + ANSI real PG pool timed out** | engine_crash | **network_outage** | **FALSE POSITIVE — HIGH (real prod log)** |
| 19 | sparse 5 DNS / 20-line tail (可能跨數小時) | engine_crash (debatable) | network_outage | MEDIUM (push back §F) |
| 28 | active (b) 命中 + rotated ambiguous → guard 整體降級 | engine_crash | engine_crash | OK |

完整 28 probes 全項通過邏輯，僅 1 個 **真實 production false-positive 場景**未通過（probes 3 + 18）— 這就是 finding 1。

---

## Findings

### CRITICAL

無。

### HIGH

**HIGH-1**：`AMBIGUOUS_SOURCE_PATTERNS` 漏 production 真實 PG 失敗 pattern `pool timed out`，造成 false-positive 風險。

- **位置**：`helper_scripts/canary/engine_watchdog.py:152-162`
- **問題**：guard 列了 `postgres` / `pgconnection` / `sqlx` 等 token，但 **未涵蓋當前 `/Users/ncyu/.openclaw_runtime/engine.log` 第 4 行的真實 PG 失敗格式**：

  ```
  WARN openclaw_engine::database::pool: PG pool connect failed — DB writes disabled / PG 連接失敗，DB 寫入已禁用 error=pool timed out while waiting for an open connection
  ```

  此行 `.lower()` 後 = `... pg pool connect failed ... error=pool timed out while waiting for an open connection`。check：
  - `postgres` ⊄ line（出現的是 `pg` not `postgres`）
  - `pgconnection` ⊄ line（出現的是 `pg pool`）
  - `sqlx` ⊄ line（這條走 `openclaw_engine::database::pool` 不是 sqlx 層）
  - 其他 token 全部 ⊄

  **真實 attack scenario**：engine PG pool 耗盡（real bug）同時 Bybit WS 短暫重連（5 條 `connection refused`，NETWORK_OUTAGE_PATTERN 命中）：
  - 舊 classifier：5 條連續 → 算 outage（其實已是現有 v1 bug，但場景罕見）
  - 新 classifier：**仍誤判 network_outage** 因為新增的 ambiguous guard 抓不到 `pool timed out` / `pg pool connect failed`
  - 後果：watchdog 跳過 strike 計數 + 跳過 auto-restart → 真 PG bug 被吞掉
  - 注意：新 classifier 的 (c) interleaved gate 讓本場景更容易誤判（門檻從「5 連續」放寬到「5 條總數 + 25% 比例」）

  E2 已用 `Probe 3` + `Probe 18` 直接以 production 行字串 reproduce 出 false-positive 結果。

- **嚴重性理由**：
  - 新 PR 的設計初衷之一就是「不可錯把 PG/disk 故障標為 net-outage」（E1 §3.4 寫得很清楚）
  - 列的 token list **未經 production engine.log empirical 對照**，採推測式設計
  - 此盲區直接違反 task spec "若不確定 → 預設 engine_crash" 的保守原則
  - 新 (c)/(d) gate 放寬了 false-positive 觸發門檻，guard 應同步加強而非沿用推測 token list

- **修法建議**：
  1. 加入 `"pool timed out"` 到 `AMBIGUOUS_SOURCE_PATTERNS`
  2. 加入 `"pg pool"`（涵蓋 `PG pool connect failed` / `PG pool unavailable` 等 prefix）
  3. 加入 `"db_pool"`（engine 內部常見 token，見 production log 多處）
  4. 加 1 個 dedicated regression test：`test_pg_pool_exhaustion_with_concurrent_dns_errors_not_classified_as_net_outage`，用 production log 的真實字串 (含 ANSI escape) 構造 tail
  5. 在 `AMBIGUOUS_SOURCE_PATTERNS` 上方注釋追加：「token list 必須對照 production engine.log empirical patterns，不可純推測；新增前先 `grep -i 'pool\\|memory\\|disk\\|panic' /var/.../engine.log` 驗證」

### MEDIUM

**MEDIUM-1**：spec push back §3.2「ratio gate 等價 timestamp window」假設在 sparse log 場景下不成立，無 explicit edge case 防護或注釋。

- **位置**：`helper_scripts/canary/engine_watchdog.py:132-138`（ratio gate 注釋）+ E1 report §3.2
- **問題**：E1 push back 中寫「engine.log tail 20 行通常涵蓋幾分鐘範圍（每秒 ≤1 行的引擎輸出速率下）」，此假設在 production 99% 場景成立（current `/Users/ncyu/.openclaw_runtime/engine.log` 850 行 / 多分鐘 startup ≈ 每秒幾行），但 **engine 在 idle / paused / heavily-throttled 階段**寫入速率可下降到 <1 行/分鐘。E2 `Probe 19` 構造稀疏 5 DNS / 20-line tail，classifier 回 `network_outage`，沒辦法判斷實際時間跨度可能是數小時。
- **嚴重性**：MEDIUM（不是 CRITICAL/HIGH 因為 sparse log 場景在 production 罕見；如 engine 已 paused 通常還有其他 freshness 訊號）但仍是 spec push back 中未明說的假設。
- **修法建議**：
  - **選項 A（簡單）**：在 `_read_log_tail` 或 classifier 加 `_log_tail_time_span(lines)` helper，從 tail 第一行與最後一行 parse ISO-8601 timestamp，超過 5min 直接降級 engine_crash。Rust tracing 預設用 `with_timer(SystemTime)` 輸出 RFC3339 形式（已驗 production log 確認）— 不像 E1 §3.2 所稱「format 不一定保證對齊」。
  - **選項 B（最低成本）**：在 ratio gate 注釋追加 explicit assumption：「assumption: tail 20 行涵蓋 ≤5min；engine paused/throttled 場景下此 gate 可能誤判，已知限制由 §11 timestamp window upgrade 補。」並加 OQ 給 PM 決定是否升 P1 補 timestamp gate。
- **推薦選項 B**：本 PR 已涵蓋 95% 場景；timestamp window 是 follow-up enhancement，不阻 merge。但 PR 必須**明文記錄假設**以免下一個 maintainer 不知道盲區。

**MEDIUM-2**：`_count_network_matches(aggregate_lower)` 在 (d) gate 中被重複呼叫 2 次（L396 + L399）。

- **位置**：`helper_scripts/canary/engine_watchdog.py:394-402`
- **問題**：兩次 `_count_network_matches(aggregate_lower)`，每次 O(N×P)（N=120 lines max, P=5 patterns）。正確性無問題，但兩次 walk 是不必要的 perf nit。
- **嚴重性**：MEDIUM（perf 影響微小，但程式碼層次是顯著的重複，違反 helper 抽出的本意）
- **修法建議**：抽出一次計算到變數：
  ```python
  agg_matches = _count_network_matches(aggregate_lower)
  if len(aggregate_lower) > 0 and agg_matches >= NETWORK_OUTAGE_AGGREGATE_MIN_MATCHES \
      and (agg_matches / len(aggregate_lower)) >= NETWORK_OUTAGE_AGGREGATE_MIN_RATIO:
      return "network_outage"
  ```

### LOW

**LOW-1**：test placement push back 合理 — 但 docstring 應 cross-reference 兩個檔案以幫助 discoverability。

- **位置**：`helper_scripts/canary/test_engine_watchdog.py:1-22` MODULE_NOTE
- **問題**：E1 在 `test_canary.py::TestEngineFailureClassifier` 加 4 個新 test 是對的（既有 13 個 classifier test 在這），但 `test_engine_watchdog.py` 的 MODULE_NOTE 沒明說「classifier tests live in test_canary.py」。未來開發者 `pytest test_engine_watchdog.py` 不會跑 classifier test，可能誤以為缺 coverage。
- **嚴重性**：LOW（不阻 merge）
- **修法建議**：在 `test_engine_watchdog.py` MODULE_NOTE 末尾追加一行：「注：classify_engine_failure / on_engine_crash 等核心 watchdog routing 的 unittest 位於 `test_canary.py::TestEngineFailureClassifier` / `TestOnEngineCrashClassification`，本檔僅含 Layer B inert-probe scope。」
- E2 直接修還是退 E1：因為這是 documentation hygiene 而非業務邏輯，E2 不直接寫，等 E1 R2 一併處理。

**LOW-2**：（observational，非 blocker）`AMBIGUOUS_SOURCE_PATTERNS` `"watchdog timeout"` token 字面 lowercase 後仍含空格 `"watchdog timeout"`，正確；但與 Layer B `TRADING_INERT_PROLONGED` event name 不衝突（已驗，Layer B 寫 `INERT_PROBE_*` 不含 `watchdog timeout` 字串）。記錄保留。

---

## 嚴重性對應 + 動作

| 嚴重性 | 動作 |
|---|---|
| HIGH-1 | **必修**：補 `pool timed out` / `pg pool` / `db_pool` token + dedicated test + 注釋強化 |
| MEDIUM-1 | **必處理**：選 A 或 B；如選 B 必須在 classifier docstring 注明假設並開 OQ 給 PM |
| MEDIUM-2 | **必修**：抽出變數避免雙重計算 |
| LOW-1 | E1 R2 一併處理（test_engine_watchdog.py MODULE_NOTE cross-ref） |

---

## 跨檔影響面

- `classify_engine_failure` 全 repo 1 個 production caller (`on_engine_crash`), test layer caller 17 處（全部已驗）
- 回傳枚舉值不變（`"network_outage"` / `"engine_crash"` 只兩種，caller switch case 仍正確）
- `on_engine_crash` 已存在 `"network_outage"` 分支 (L616-634)，HIGH-1 修正只改 classifier 內部，**不影響任何 caller**
- `helper_scripts/canary/test_engine_watchdog.py` 40/40 PASS（Layer B inert-probe 不受影響，已驗）

---

## E1 push back 評估

| 編號 | E1 push back | E2 判斷 |
|---|---|---|
| Push back §1 | test 放 `test_canary.py` 而非 spec 提的 `test_engine_watchdog.py` | **合理**：既有 13 個 classifier test 都在 `test_canary.py::TestEngineFailureClassifier`，test_engine_watchdog.py 是 Layer B inert-probe 專用。test 局部性原則 + 共享 fixture 是正確選擇。LOW-1 提示加 cross-reference docstring。 |
| Push back §2 | 用 ratio gate 替代 spec 的 5min rolling timestamp window，理由「engine.log timestamp format 不一定保證對齊」 | **部分合理**：production engine.log 用 Rust `tracing_subscriber::fmt()` 默認 RFC3339 timestamp `2026-05-21T10:14:23.190848Z`（E2 已 grep 驗 — `/Users/ncyu/.openclaw_runtime/engine.log` L1-10）— 該 format 非「brittle」，Python 標準 stdlib 可解。但 E1 的 ratio gate **在 99% production 場景下等價** + 實作更簡單；trade-off 合理。**但 sparse log 邊緣場景** (engine paused/throttled) 下 ratio gate 會誤判，這是 §3.2 未涵蓋的盲區 → MEDIUM-1。 |

---

## 跨平台 / 注釋 / file size / emoji

- 跨平台 grep：clean，無 `/home/ncyu` / `/Users/[username]` 硬編碼
- 注釋規範：新注釋中文為主、技術 ID 保留英文、MODULE_NOTE 風格符合
- File size：engine_watchdog.py 1501 行（< 2000 cap，>800 已記錄 exception）；test_canary.py 857 行（剛超 800，未超 cap，但需注意）
- Emoji：clean，無 emoji
- TODO/FIXME：clean，無新增

---

## 多 session race check (§5)

- 5a fetch + sibling window：`git fetch --prune origin` done；2h 內 origin/main 無新 commit（最新 33ef66f5 是 yesterday's TODO closure）
- 5b status clean：unstaged 全為本 task scope (3 檔：engine_watchdog.py / test_canary.py / E1 memory)；untracked 是 E1 report + 兩個 execution-plan v5.2/5.3 (不屬本 task)
- 5c unknown WIP：所有 unstaged 都是本 task scope，未見 sibling 改動
- 5d sign-off path：未 commit
- 5e sibling push：origin/main 無 sibling push

---

## 結論

**RETURN to E1（1 HIGH + 2 MEDIUM + 1 LOW，共 4 finding 待修）**

主要阻擋 issue 是 HIGH-1：`AMBIGUOUS_SOURCE_PATTERNS` 漏 production 真實 PG 失敗 pattern `pool timed out` / `pg pool`，造成新 PR 設計初衷的 false-positive 防護**在最重要的場景下無效**。E2 已用 production engine.log 真實 ANSI-wrapped 字串 reproduce false-positive。E1 自評 §6 OQ 3 寫「AMBIGUOUS_SOURCE_PATTERNS 完整性」採「未來發現新 false-positive 再 patch」保守原則 — 但這個 pattern **已經在 current production log 出現**，不是「未來」場景，是 deploy 第一天就會誤判的真實場景。

E2 對抗結論：**本 PR 的 4-gate 邏輯架構 sound，guard 設計概念正確；但 token list 必須對照 production engine.log 實證補齊**，否則新 classifier 變成「比舊更易觸發 outage」+「false-positive guard 在真實 PG 故障場景無效」，淨效果可能不如保留舊 single-gate 行為。

---

## 退回 E1 修復清單

1. **HIGH-1**：`helper_scripts/canary/engine_watchdog.py:152-162` 加 `"pool timed out"`、`"pg pool"`、`"db_pool"` 三個 token 到 `AMBIGUOUS_SOURCE_PATTERNS`；同時加 token 注釋區塊說明「token 必須對照 production engine.log empirical 取樣」；補 1 個 dedicated regression test `test_pg_pool_exhaustion_with_concurrent_dns_errors_not_classified_as_net_outage` 用 production 真實 ANSI-wrapped 字串。
2. **MEDIUM-1**：選 A 或 B。
   - A：加 timestamp parse + 5min span guard（推 P1，但風險面增大）
   - B（推薦）：在 ratio gate 注釋追加 explicit assumption「tail 20 行 ≤5min @ 引擎正常輸出速率；sparse log 場景已知盲區，OQ 給 PM 決定是否升 P1 補 timestamp gate」；在 OQ list 加新項目 `OQ-NETOUTAGE-2: sparse-log timestamp window`。
3. **MEDIUM-2**：`helper_scripts/canary/engine_watchdog.py:394-402` 抽出 `agg_matches = _count_network_matches(aggregate_lower)` 變數，避免雙重 O(N×P) walk。
4. **LOW-1**：`helper_scripts/canary/test_engine_watchdog.py:1-22` MODULE_NOTE 末尾加 cross-reference line 指向 `test_canary.py::TestEngineFailureClassifier` / `TestOnEngineCrashClassification`。

修完後 E2 R2 review 應 < 10min（focus on HIGH-1 patch + token list 對照 production log）。
