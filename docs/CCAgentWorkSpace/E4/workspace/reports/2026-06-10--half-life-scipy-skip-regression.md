# E4 Regression Test Report — fix/half-life-test-scipy-skip `6c8c40b4` · 2026-06-10

被驗:branch `fix/half-life-test-scipy-skip`,最終 SHA `6c8c40b4e784c6a1ff5f78a2119cf328b658d3df`(origin 已推;merge-base = origin/main = Linux 主 checkout HEAD = `02c80f3b`,branch 恰 +2 commits:`dc5c60d7` 修復 + `6c8c40b4` E2 INFO-1 docstring)。
驗證環境:Linux trade-core(失敗被回報的 runtime),detached worktree `/tmp/hl_fix_e4`,prod 主 checkout `/home/ncyu/BybitOpenClaw/srv` 全程零觸碰(porcelain=0 前後雙驗)。
前序:E1 報告 `E1/workspace/reports/2026-06-10--half-life-test-scipy-skip.md`;E2 APPROVE-with-nits(0 需修,2 INFO)`E2/workspace/reports/2026-06-10--half-life-scipy-skip-review.md`。

## 總裁決

**PASS** — 驗證矩陣 7 步全綠,兩遍同綠非 flaky,0 新 fail,測試數 7 守恆,estimator 業務邏輯零改動。
附 1 個基準線帳本歸屬更正(Finding-1,證據性推翻 task brief 的「8→6」預期,屬記帳口徑非代碼問題,不阻塞 PASS,交 PM 裁決)。

## Test 結果矩陣

| Lane | 修復前(基線) | 修復後(實測) | 跑遍數 | delta |
|---|---|---|---|---|
| 本檔 @ Linux `/usr/bin/python3`(無 scipy,本案核心) | 5 passed / 2 failed(症狀回報;同日 main 主 checkout 重現) | **5 passed / 2 skipped** | ×2 identical | 2f→2s,0 遮蓋 |
| 本檔 @ scipy venv(`/tmp/hl_e4_venv`,未來 un-skip 防雷) | —(新 lane) | **7 passed** | ×2 identical | fit 斷言當代庫版本真過 |
| 鄰域 `program_code/learning_engine/tests/` @ system python | **246 passed / 2 failed**(main `02c80f3b` 主 checkout 唯讀親跑,2F 恰為本案兩測試) | **246 passed / 2 skipped / 0 failed** | ×2 identical(22.61s/22.49s) | 精確 2f→2s,248 items 守恆,0 新 fail |
| tests/ 控制面 ledger(4661/8,2026-06-08~10 記錄) | 8 pre-existing | 未跑(本改動 0 觸碰該 scope) | — | 期望不變(見 Finding-1) |

## 逐項輸出原文(裁剪到關鍵行)

### Step 1 — 取碼
```
准备工作区（分离头指针 6c8c40b4）
HEAD 现在位于 6c8c40b4 docs(test): half_life 測試檔頭明示雙模式語意(E2 INFO-1)
WORKTREE_OK
```

### Step 2 — 無 scipy 路徑(run 1 含 collection header;run 2 -q -rs)
```
platform linux -- Python 3.12.3, pytest-9.0.2, pluggy-1.6.0
rootdir: /tmp/hl_fix_e4
configfile: pytest.ini
plugins: asyncio-1.3.0, anyio-4.13.0
collected 7 items

program_code/learning_engine/tests/test_half_life_estimator.py ss.....   [100%]
SKIPPED [1] program_code/learning_engine/tests/test_half_life_estimator.py:108: could not import 'scipy': No module named 'scipy'
SKIPPED [1] program_code/learning_engine/tests/test_half_life_estimator.py:137: could not import 'scipy': No module named 'scipy'
========================= 5 passed, 2 skipped in 0.30s =========================
```
run 2(-q -rs):`5 passed, 2 skipped in 0.24s`,SKIPPED 兩行 byte-identical。**collected 7 items 確認,無 collection error,測試數守恆**;skip 理由含 scipy ✓;skip 行號 :108/:137 = E2 在 `dc5c60d7` 觀測的 :104/:133 + docstring 4 行位移,一致。

### Step 3 — 有 scipy 路徑(venv)
```
PIP_EXIT=0
numpy 2.4.6 / pandas 3.0.3 / pytest 9.0.3 / scipy 1.17.1
run 1: program_code/learning_engine/tests/test_half_life_estimator.py .......   [100%]
run 2: 7 passed, 2 warnings in 0.49s
```
**7 passed ×2**。Linux 當代庫版本下兩個 fit 斷言(`pnl_decay`/`sharpe_decay` 還原 true half-life)真的會過,未來 un-skip 無雷。venv scipy 1.17.1 與 control_api `.venv` 實裝版本一致(見 Finding-2)。2 warnings = venv 無 pytest-asyncio 致 pytest.ini asyncio 選項 unknown-option warning,本檔無 async 測試,無害(INFO)。

### Step 4 — 鄰域回歸
修復前(main `02c80f3b` 主 checkout,唯讀):
```
FAILED program_code/learning_engine/tests/test_half_life_estimator.py::test_pnl_decay_pass
FAILED program_code/learning_engine/tests/test_half_life_estimator.py::test_sharpe_decay_pass
2 failed, 246 passed in 22.29s        (assert 'default_14d' == 'sharpe_decay' — 症狀精確重現)
```
修復後(worktree):
```
run 1: 246 passed, 2 skipped in 22.61s
run 2: 246 passed, 2 skipped in 22.49s
```
唯一狀態變化 = 本案 2 測試 fail→skip;其餘 246 測試狀態不變;0 新 fail。

### Step 6 — 無 mock 遮蓋
```
git diff origin/main -- program_code/learning_engine/half_life_estimator.py  → 空輸出(EXIT=0)
git diff origin/main...HEAD --stat:
 program_code/learning_engine/tests/test_half_life_estimator.py | 10 ++++++++++
 requirements-ml.txt                                            |  1 +
 2 files changed, 11 insertions(+)
```
estimator 業務邏輯零改動;全 diff 純插入零刪除(斷言零刪除,佐證 E2);`pytest.importorskip("scipy")` 置於兩個 fit-path 測試 docstring 後首 statement = **env-gate 產生可見誠實 SKIP(理由外顯),非 mock、非 xfail、非斷言放寬**。requirements-ml.txt +1 行 `scipy>=1.10.0` 宣告。

### Step 7 — 清理
```
CLEANUP_DONE;/tmp/hl_fix_e4 與 /tmp/hl_e4_venv 確認不存在;
worktree list = main(02c80f3b)+ /tmp/wt-l2-owed-test(他 session 既有,未觸碰);PORCELAIN_LINES=0
```

## Step 5 — 基準線對帳(regression-testing-protocol)

**Finding-1(基準線帳本歸屬更正;severity LOW-記帳/confidence MEDIUM-HIGH;交 PM 裁決)**:task brief 預期「全 suite failed 8→6」隱含本案 2F ∈ 06-08~10 記錄的「4661 passed/8 pre-existing」。實證推斷 **2F 不在該 8 之列**,判斷依據:
1. 該 8-fail 名單原文不存在於任何可定位報告(僅 memory 摘要存數字),無法直接點名核對 — 此為本判定唯一不確定來源。
2. **量級論證**:worktree root 裸收集(系統 python)= **7325 tests + 3 collection errors**;4661+8≈4669 與之差 2656,不可能是 skip 差 → 該「full suite」非 root 全收集口徑,最自然解讀 = `tests/` 控制面 scope(Mac tests/ 4328 items + Linux 額外可收集 ≈ 4669),**不含 `program_code/learning_engine/tests/`**。
3. **解譯器論證**:control_api `.venv` 有 scipy 1.17.1 → 即便某口徑用 .venv 收了本檔也會 7 passed 不入 fail 名單;只有 scipy-less 系統 python lane 才產生本案 2F。
4. 本案 2F 的已記錄歸屬 = **2026-06-10 P3b producer-gate ledger**(learning_engine+ml_training+research @ scipy-less 解譯器 = 794 passed/2 failed,2F 正是本檔,當時已標 pre-existing、main 亦 fail)— 與「4661/8」是**不相交 scope 的兩本帳**。

**修正後的 post-land 基線期望**(取代「8→6」):
- `tests/` 控制面 ledger:**8 不變**(本改動 0 觸碰該 scope)。
- producer-gate lane(scipy-less):**failed 2→0、skipped +2、passed 不變**(鄰域實測已證此轉換:246p/2f→246p/2s)。
- 本檔單檔:scipy-less = **5p+2s**(非 7p、非 2f);有 scipy = **7p**。
- 未來任何 root 全量口徑在 scipy-less 解譯器下,本檔貢獻 5p+2s。

PM 預期的方向(failed −2、skipped +2)在「包含本檔的 scipy-less 口徑」下成立,僅帳本歸屬須更正。

## 新增測試
無(本案為既有測試的環境守衛;E2 #4 已裁定不擴守衛是正確取捨——其餘 5 測試在 scipy-less 環境繼續驗證降級契約 = trade-core 真實生產語意)。

## Mock 審查
| Test | mock 內容 | OK? |
|---|---|---|
| test_pnl_decay_pass / test_sharpe_decay_pass | 無 mock;`importorskip("scipy")` = env-gate,缺依賴時可見 SKIP 含理由 | OK(非業務邏輯遮蓋) |
| 其餘 5 測試 | 零觸碰(diff 零刪除行) | OK |

## 浮點一致性 / SLA 壓測
N/A(test-only 守衛 + requirements 宣告;0 production 代碼、0 indicator、0 hot path;E2 已證 0 production caller)。

## 跑兩遍結果
- Step 2:run1 = run2 = 5p/2s(SKIPPED 行 byte-identical)→ 非 flaky
- Step 3:run1 = run2 = 7p → 非 flaky
- Step 4:run1 = run2 = 246p/2s → 非 flaky

## 其他 findings(全量輸出)
- **Finding-2(INFO/confidence HIGH)**:Linux 解譯器二元性實證 — `/usr/bin/python3` 無 scipy、control_api `.venv` scipy 1.17.1。修復後本檔在兩 lane 均誠實綠(5p/2s 與 7p),docstring 雙模式注釋與現實相符。
- **Finding-3(INFO/pre-existing)**:root 裸收集有 3 個 collection errors(含已知 `tests/ml_training/test_pure_utils.py` 重名問題,E4 memory 既載),與本案無關,僅因本次跑了 root collect-only 順帶記錄。
- **Finding-4(INFO,承 E2 INFO-2)**:requirements-ml.txt 宣告 necessary-not-sufficient — 無管道自動裝進 trade-core 系統 python;今日 0 production caller 無影響;未來 fit 路徑活化須 operator 實裝 scipy(.venv 已有 1.17.1,floor `>=1.10.0` 滿足)。
- **Hygiene**:prod 主 checkout porcelain=0(前後雙驗);臨時工件全清;`/tmp/wt-l2-owed-test` 為他 session 既有 worktree,未觸碰;E1 的 Mac worktree `/tmp/hl_scipy_fix` 依 E1 報告由 PM 收口清理。

## 結論

**E4 REGRESSION DONE: PASS**。退 E1 修復清單:無。PM 可 merge(基準線記帳按 Finding-1 修正口徑)。
