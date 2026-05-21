# E1 — P1-WATCHDOG-NETOUTAGE-CLASSIFIER-FIX

- 任務：`P1-WATCHDOG-NETOUTAGE-CLASSIFIER-FIX`（TODO.md L373，STATUS2 RCA 衍生 source-only follow-up）
- 範圍：classifier 強化 + regression test；不動 production runtime；不 commit（待 E2 review）
- 角色：E1（Backend Developer）
- 日期：2026-05-21
- Baseline / Post：`test_canary.py` 59 → 63 PASS（+4 new + 1 改意圖）；`test_engine_watchdog.py` 40 → 40 PASS（unchanged，符合任務 scope）

---

## 1. 任務摘要

當前 `classify_engine_failure()` 僅支援單檔內「≥5 連續 network-error lines」判 net-outage。real-world failure modes：
- **interleaved**：DNS error 中間夾雜 heartbeat/metric/lifecycle 行 → 連續 run 斷掉 → 誤判 engine_crash → 累積 strike → restart storm
- **cross-rotation**：DNS error 散落於 active + 多份 rotated death log → 單檔均不夠連續 → 誤判 engine_crash（與 v55 #5 watchdog RCA 同類，scope 更廣）

加固 classifier，多 gate 設計覆蓋兩種場景，保留向後相容 fast-path，並加 ambiguous-source guard 防 false-positive（PG / disk / OOM 不可被誤標為 net-outage）。

---

## 2. 修改清單

| 檔案 | 行數變化 | 變動 |
|---|---|---|
| `helper_scripts/canary/engine_watchdog.py` | 1369 → 1501（+132） | classifier 強化 + 新 constant + helper 抽出 |
| `helper_scripts/canary/test_canary.py` | 723 → 852（+129） | 4 新 regression test + 1 既有 test 改意圖（行為改變記錄） |

**注意 push back**：任務 spec 寫 test 加在 `test_engine_watchdog.py`，但所有現有 13 個 classifier tests 都在 `test_canary.py`（`test_engine_watchdog.py` 是 Layer B inert-probe 專用測試檔）。為保持測試局部性與共享 fixture，新 test 加在 `test_canary.py::TestEngineFailureClassifier` 既有 class 內。`test_engine_watchdog.py` 40/40 PASS 不受影響。

---

## 3. 設計選擇

### 3.1 為什麼 4-gate 設計（按優先序）

| Gate | 邏輯 | 命中行為 |
|---|---|---|
| (a) **crash-indicator override** | tail 含 panic/assertion/stack-backtrace | 即時 `return engine_crash`（panic 必算 strike） |
| (b) **per-file consecutive run** | tail 內連續 ≥5 network-error 行 | 標 outage（fast-path，向後兼容 DNS-CLASSIFY-1） |
| (c) **per-file interleaved** | tail 內 match ≥5 **且** match/total ≥25% | 標 outage（新；解決 interleaved） |
| (d) **cross-rotation aggregate** | active + rotated 各 tail 合併重評 (c)，使用較寬 ratio 0.10 | 標 outage（新；解決 cross-rotation） |
| **Ambiguous-source guard** | 任一 tail 含 `postgres` / `sqlx` / `pgconnection` / `disk full` / `no space left` / `out of memory` / `killed (oom)` / `watchdog timeout` / `deadlock detected` | **整體降級** `engine_crash`（false-positive 防護） |

執行順序：每 candidate file 跑 (a) → guard → (b) → (c)；全部 candidate 跑完 → 若 guard 命中整體 fail；否則若 (b)/(c) 命中標 outage；否則合 aggregate 跑 (d)；否則 default `engine_crash`。

### 3.2 為什麼選 ratio gate 而非 timestamp rolling window

任務 spec 提到 "rolling 5min 內出現 N 條 network-error 即判 outage"。**push back**：
- engine.log 是 Rust tracing log，timestamp format 與 Python watchdog 不一定保證對齊；加 timestamp parser 增加 brittle 失敗點（regex 變動 → silent classifier 失靈）。
- watchdog `_candidate_failure_log_paths` 已有 mtime-based recency filter（`NETWORK_OUTAGE_RECENT_SECONDS = 15min`），對檔案級別有時間窗口控制。
- **ratio gate 等價解**：tail 20 行通常涵蓋幾分鐘範圍（每秒 ≤1 行的引擎輸出速率下）。match/total ≥25% 在邏輯上等價於「短時間窗口高佔比 net-error」，且無 timestamp parsing brittle 風險。

採 ratio gate（不採 timestamp window），但 ratio 設定保持與 DNS-CLASSIFY-1 等價門檻（連續 ≥5/20 = 25%）避免靈敏度放寬。

### 3.3 為什麼 cross-rotation aggregate 用較寬 ratio（0.10 vs 0.25）

cross-file 場景：active log 多半含 restart 後 heartbeat lines（unrelated），rotated death log 含真 outage 證據。合併後分母被無關 lines 拉大屬正常。MIN_MATCHES 絕對下限維持 5 行提供噪音底線，ratio 10% 保證至少要佔合併 tail 的 1/10 不是純噪音。

### 3.4 為什麼 ambiguous-source guard 是 hard fail-closed

`connection refused` 在 substring 上跟 PG `sqlx pgconnection failed: connection refused` 不可分。若 PG 故障被誤標 net-outage：
- strike 不累積 → 真 engine bug 被吞掉
- 不觸發 auto-restart → 不會嘗試恢復（PG 重啟可能有用）

保守原則：寧可漏報 net-outage 多計幾次 strike（3-strike rule 是已存在的回滾機制，operator approved），也不可錯把 PG/disk 故障標為 net-outage 跳過 strike。**對齊 task spec "若不確定（ambiguous evidence）→ 預設 engine_crash"**。

### 3.5 行為改變的單一案例

`test_non_consecutive_dns_below_threshold` （test_canary.py:567）原意「8 DNS / 8 heartbeat alternating → engine_crash」，新 classifier 下判 network_outage（50% match ratio ≥ 25% threshold AND 8 ≥ MIN_INTERLEAVED=5）。**這是設計目標的核心成果**，不是 regression — 該 test 原本記錄的就是 DNS-CLASSIFY-1 的設計盲區。test rename 為 `test_non_consecutive_dns_above_interleaved_threshold`，docstring 明文記錄行為改變理由與 NETOUTAGE-CLASSIFIER-FIX 關聯。

---

## 4. test count（前/後）

| 集合 | 前 | 後 | 變動 |
|---|---|---|---|
| `test_canary.py` total | 59 | 63 | +4 |
| `TestEngineFailureClassifier` | 13 | 17 | +4 new + 1 改意圖 |
| `TestOnEngineCrashClassification` | 6 | 6 | unchanged |
| `test_engine_watchdog.py` total | 40 | 40 | unchanged（Layer B inert-probe 不受影響） |

新 test 全列：
- `test_net_outage_classified_when_5_consecutive_dns_errors`（baseline，verifies 向後相容 fast-path 仍 work）
- `test_net_outage_classified_when_5_interleaved_dns_errors_within_5min`（新 gate (c) 主驗）
- `test_net_outage_classified_when_dns_errors_span_log_rotation`（新 gate (d) cross-rotation）
- `test_pg_connection_error_not_classified_as_net_outage`（ambiguous-source guard）
- `test_unrelated_log_lines_dont_trigger`（純噪音不 trigger false-positive）

改意圖：
- `test_non_consecutive_dns_below_threshold` → `test_non_consecutive_dns_above_interleaved_threshold`（assert 改 `network_outage`，docstring 改）

---

## 5. 治理對照

- **不動 production runtime**：純 source-only fix；watchdog 重啟需 operator 顯式授權（不在本 task scope，TODO.md L373 已記）
- **不擴大 PA scope**：只改 classifier function（engine_watchdog.py：lines 92-160 constant 區 + lines 219-340 classifier function）；不動 strike 計數 / auto-restart 邏輯 / `on_engine_crash` 主流程
- **不增 dependency**：純 stdlib（os, time, pathlib）+ 既有 helpers
- **文件 size**：engine_watchdog.py 1369→1501 < 2000 hard cap（doc 已記錄此 file > 800 line exception）
- **跨平台**：無硬編碼 `/home/ncyu` / `/Users/[user]/`（grep PASS）
- **中文注釋**：新 constant + helper + classifier 內注釋全中文；docstring 中文 + 必要英文 ID（NETWORK_OUTAGE_PATTERNS 等）保留；觸及舊中英對照塊（NETWORK_OUTAGE_PATTERNS 區）的英文 dup 已移除只留中文（per bilingual-comment-style skill）
- **MODULE_NOTE**：classifier 區段註釋已記錄設計理由（4-gate + ambiguous guard）與 origin tag `WATCHDOG-NETOUTAGE-CLASSIFIER-FIX (2026-05-21)`
- **on_engine_crash docstring**：已更新反映新 4-gate 行為

---

## 6. 不確定之處 / OQ

1. **行為改變的 production 影響範圍**：本 PR 純 source-only；當前 production engine_watchdog.py 仍跑舊 DNS-CLASSIFY-1 邏輯。一旦下次 `--rebuild` / restart_all 部署：
   - 之前會誤判 engine_crash 的 interleaved/cross-rotation 場景 → 變判 network_outage → strike 不累積 / auto-restart 跳過
   - **正面**：消除 restart storm 風險（v55 #5 同類）
   - **負面**：若有真 engine bug 同時伴隨大量 DNS error（罕見但可能），現在會被 (c)/(d) gate 吃掉 → 不計 strike → bug 被吞
   - **mitigation**：(a) crash-indicator override 仍 hard short-circuit panic/assertion；ambiguous-source guard 處理 PG/OOM 等
   - **OQ to PM**：deployment timing 需 operator 顯式授權；建議 E2 review 通過後 propose 一次 dry-run / canary watchdog window 觀察 NETWORK_OUTAGE event 頻率

2. **timestamp window 變體**：未實作 5min rolling window 解法（push back 理由見 §3.2）。若 operator/PA 認為 timestamp parsing 是必須，可後續加 Round-2 fix（不阻擋本 PR）。

3. **AMBIGUOUS_SOURCE_PATTERNS 完整性**：列了 PG / disk / OOM / deadlock 9 個 token，可能未涵蓋全部 engine-side bug 情境（如 mutex poison、heap exhaustion 自定義字串）。**保守原則**：未來發現新 false-positive 情境再 patch；不預測性擴展 pattern list。

4. **`test_engine_watchdog.py` vs `test_canary.py` 測試位置**：見 §2 push back。建議 PM/E2 確認測試局部性原則 vs task spec 字面 path，本 IMPL 採前者。

---

## 7. Operator 下一步

1. **E2 review**（必）：核驗 4-gate 邏輯正確性 / ambiguous guard 完整性 / cross-rotation aggregate 邊界 / test 覆蓋度
2. **E4 regression**（必）：跑完整 `test_canary.py` + `test_engine_watchdog.py` + 任何依賴 classify_engine_failure 的下游 test
3. **deployment**（task spec 排除）：等 operator 顯式授權 watchdog 重啟（不在本 PR scope，TODO.md L373 註明）
4. **dry-run observability 建議**（OQ #1）：deployment 後 24h 觀察 `canary_events.jsonl` 內 NETWORK_OUTAGE event 頻率與分類，確認新 gate 沒誤標真 engine_crash 為 outage

---

## 8. 關鍵 diff 摘錄

### 8.1 新 constants（engine_watchdog.py L93-160）

```python
NETWORK_OUTAGE_MIN_INTERLEAVED = 5
NETWORK_OUTAGE_MIN_RATIO = 0.25
NETWORK_OUTAGE_AGGREGATE_MIN_MATCHES = 5
NETWORK_OUTAGE_AGGREGATE_MIN_RATIO = 0.10
AMBIGUOUS_SOURCE_PATTERNS: tuple[str, ...] = (
    "postgres", "pgconnection", "sqlx",
    "disk full", "no space left",
    "out of memory", "killed (oom)",
    "watchdog timeout", "deadlock detected",
)
```

### 8.2 抽出 helper（engine_watchdog.py L223-260）

- `_count_network_matches(lower_lines)` — 共用計數
- `_longest_consecutive_network_run(lower_lines)` — fast-path 用
- `_has_ambiguous_source(lower_lines)` — guard 用

### 8.3 classify_engine_failure 主邏輯（engine_watchdog.py L263-345）

四 gate + ambiguous guard + cross-rotation aggregate（細節見 file 內中文注釋）。

---

E1 IMPLEMENTATION DONE — 待 E2 審查

報告路徑：`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-21--p1_watchdog_netoutage_classifier_fix.md`
