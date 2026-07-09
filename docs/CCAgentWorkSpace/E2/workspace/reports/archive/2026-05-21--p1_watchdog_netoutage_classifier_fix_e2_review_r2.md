# P1-WATCHDOG-NETOUTAGE-CLASSIFIER-FIX — E2 R2 Adversarial Review

**日期**：2026-05-21
**Owner**：E2
**Trigger**：E1 R2 fix 通報後 E2 對抗審查
**Status**：✅ APPROVE — pass to E4

## VERDICT: APPROVE

4/4 R1 finding 真實修復；0 new regression；207/207 PASS；adversarial regression catcher 確認非 self-consistency mock；可直接 pass to E4 regression。

## R1 Finding 逐條驗證

| R1 Finding | R2 修法 | Evidence | 結果 |
|---|---|---|---|
| **HIGH-1** AMBIGUOUS_SOURCE_PATTERNS 漏 production PG pool token | `engine_watchdog.py:181-194` 補 `pg pool` / `pool timed out` / `db_pool`；`L161-180` 注釋 embed 維護規範「token list 必須對照 production engine.log empirical 取樣，不可純推測」；`test_canary.py:766-797` 新 dedicated test 用真實 ANSI-wrapped production line 4 字串；regression catcher 驗證移走 3 token → 同字串回 `network_outage`（即 FP 重現）→ test 真會紅；E2 probe 3/17/18/db_pool only/pg pool only **5/5 PASS** | ✅ FIXED |
| **MEDIUM-1** ratio gate sparse-log 盲區無 explicit 注釋 / OQ | `engine_watchdog.py:139-154` ratio gate 注釋追加 explicit 盲區假設（sparse log 風險場景 + 上游 mtime filter 保護 + OQ-NETOUTAGE-2 留 PM）；E1 R2 §6 OQ 寫明 A/B/C 三選項與 defer 推薦 | ✅ FIXED |
| **MEDIUM-2** `_count_network_matches` 雙重呼叫 | `engine_watchdog.py:427-434` 抽 `agg_matches = _count_network_matches(aggregate_lower)` local 變數，`if len > 0:` 邊界保留；單次 walk + 兩處 reuse | ✅ FIXED |
| **LOW-1** test_engine_watchdog.py MODULE_NOTE cross-ref | `test_engine_watchdog.py:20-26` MODULE_NOTE 末加 cross-reference 段，明示「classifier unittest 在 test_canary.py，本檔僅含 Layer B inert-probe scope；`pytest test_engine_watchdog.py` 不會覆蓋 classifier coverage」 | ✅ FIXED |

## 0 New Regression

- 19/19 classifier tests PASS / 207/207 canary suite PASS（本機驗證 `python3 -m pytest helper_scripts/canary/` 31.20s）
- R1 已 APPROVE 的 4-gate（panic / consecutive / interleaved / cross-rotation）邏輯未變
- 全部覆蓋 test 仍 GREEN

## 自驗 Regression Catcher（adversarial）

移走 3 個新 token → 同 production line 4 字串會回 `network_outage`（即 R1 FP 重現）→ R2 new test 會 fail。確認 test 真依賴新 token，self-consistency 過關，**修復不是 mock 自我安慰**。

## File Size

- `engine_watchdog.py`: 1532 行（R1 1501 → R2 +31 行）：< 2000 hard cap；> 800 已記錄 exception
- `test_canary.py`: 890 行（R1 857 → R2 +33）：> 800 警告線，< 2000；既有狀態
- `test_engine_watchdog.py`: 810 行（R1 803 → R2 +7）：剛過 800，< 2000；既有狀態

E1 R2 §5 已點名 size 警告，PA scope 限本 fix 不重構（trade-off 由 PM 決定）。E2 同意此判斷（拆檔屬獨立 follow-up）。

## 跨平台 + Emoji + 中文注釋

- 0 個 `/home/ncyu`
- 0 個 `/Users/ncyu`
- 0 個 emoji
- 新注釋中文為主、技術 ID 保留英文
- HIGH-1 維護規範注釋區明確 embed 對 future maintainer 的指引

## 多 Session Race Check

- 5a fetch + sibling window：origin/main 過去 2h 無 sibling push（最新 `fbe8b8d5`）
- 5b status clean：unstaged 4 檔（engine_watchdog.py / test_canary.py / test_engine_watchdog.py / E1 memory.md）全屬本 task scope
- 5c 無 unknown WIP
- 5d sign-off path：未 commit
- 5e PR review 期間無 sibling push

## OQ-NETOUTAGE-2 Backlog

E1 R2 已開 OQ 給 PM 後續決定 sparse-log timestamp window；本 PR 不擋。

## 報告交付規範注

E2 R2 review 透過 sub-agent 對話成果交付；本檔由 PM 主會話從 sub-agent message 落檔（內容 1:1 自 E2 findings）。
