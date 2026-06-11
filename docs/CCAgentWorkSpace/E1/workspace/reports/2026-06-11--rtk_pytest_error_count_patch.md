# E1 報告 — rtk pytest error 計數缺陷修復(patch + 自建 binary + 上游 PR)

日期:2026-06-11
任務來源:PM dispatch(rtk P0 採用案的 pytest error 計數缺陷修復)
工作區:`/tmp/rtk-work`(fresh full clone,非 /tmp/repo-eval/rtk 舊 clone)

## 任務摘要

修復 rtk(github.com/rtk-ai/rtk,Apache 2.0)`rtk pytest` 壓縮輸出吞掉 pytest
error 計數的缺陷(我方評估 agent 在 v0.42.2 實測復現),產出:
①可套用於 pin SHA 的 git patch;②本地自建 patched release binary;③上游 PR。

## Pin / 版本事實

- **Pin SHA = `6785a6c7695d7273e722214a295249a84819b6f0`**(upstream 預設 branch
  `develop` 的 HEAD @ 2026-06-11;`origin/HEAD -> origin/develop`,所以「main HEAD」
  即此 SHA)。Cargo.toml version 0.42.2(develop 為 0.43.0-rc 線)。
- 與 v0.42.2 release 對比:dispatch 給的行號(parse_summary_line ~L288-317、
  build_pytest_summary ~L189)在 develop HEAD 完全吻合,缺陷原樣存在。
- 修復 commit:`8a87a1e6c33d8f9c0d02bd2092c2ba118eb1a3de`,branch
  `fix/pytest-error-count`(基於 pin SHA,符合上游 `fix/<scope>-<desc>` 命名規範)。

## 根因(實碼確認,非僅 dispatch 轉述)

`src/cmds/python/pytest_cmd.rs` 四處互相疊加:

1. `parse_summary_line` 只解析 passed/failed/skipped/xfailed/xpassed,無 `error(s)`。
2. `build_pytest_summary` 在 `failed==0 && passed>0 && !extras_present` 提前 return
   全綠短格式,把已收集進 failures vec 的 ERROR 行一併丟棄。
3. summary line 捕捉條件(`===` 包裹形 + `-q` 裸形兩處)都不含 `error` token →
   error-only summary(`=== 1 error in 0.12s ===`)整行抓不到 → 全零 →
   「No tests collected」(次缺陷的直接成因)。
4. 加碼發現:`=== ERRORS ===` 區塊從未被狀態機捕捉(細節全失);單行
   `ERROR ...` short-summary 條目雖被收進 failures vec,但渲染分支只認
   `___`/`FAILED` 前綴 → 渲染成空白項。

## 修改清單

| 位置 | 改動 |
|---|---|
| `/tmp/rtk-work/src/cmds/python/pytest_cmd.rs`(唯一改檔) | source +38/−8(其中 9 行英文註釋);tests +95(4 個新單元測試)。總 +133/−8。 |
| `PytestCounts` | + `errors: usize` 欄位 |
| 狀態轉移 | `=== ERRORS ===` 併入 FAILURES 同路徑(細節區塊保留,**真實使用 load-bearing**:rtk 注入 `-rxX`,short summary 不列 FAILED/ERROR 行,細節唯一來源就是 ERRORS 區塊) |
| summary 捕捉 ×2 | `===` 形加 `contains("error")`;`-q` 裸形加 `contains(" error")`(`ERRORS` 大寫不會誤中;`Interrupted:` 行無 ` in ` 不會誤中——皆驗證) |
| `parse_summary_line` | + `word.contains("error")` 分支(單複數 `error/errors` 都中) |
| 全零 guard | + `&& errors == 0`(collection error 不再報 No tests collected) |
| 全綠提前 return | + `errors == 0 && failures.is_empty()`(後者是對「summary 解析漏抓但細節已收集」的 fail-closed 兜底) |
| headline | errors>0 時追加 `, N error(s)`(沿用上游 skipped/xfailed 條件段風格;`0 failed` 保留=上游既有 headline-pair 風格,skip-only 場景今天就印 `0 failed`) |
| 渲染分支 | `FAILED` 分支擴成 `FAILED || ERROR`,ERROR 條目標 `[ERROR]` 標籤(修空白項 bug) |

未動:exit code 透傳(本就正確)、tee 機制、`filter_pytest_output` 簽名
(`pipe_cmd.rs` 另有引用,零影響)、其他任何檔案。

## 關鍵 diff(source 部分;tests 見 patch 全文)

```diff
-        } else if trimmed.starts_with("===") && trimmed.contains("FAILURES") {
+        } else if trimmed.starts_with("===")
+            && (trimmed.contains("FAILURES") || trimmed.contains("ERRORS"))
+        {
+            // ERRORS sections (broken fixtures, collection errors) carry the
+            // same kind of detail blocks as FAILURES and must not be dropped.
             state = ParseState::Failures;
@@
                 || trimmed.contains("skipped")
+                || trimmed.contains("error"))           // === 形 summary 捕捉
@@
                 || trimmed.contains(" skipped")
+                || trimmed.contains(" error"))          // -q 裸形 summary 捕捉
@@ struct PytestCounts
+    errors: usize,
@@ build_pytest_summary
-    if passed == 0 && failed == 0 && skipped == 0 && xfailed == 0 && xpassed == 0 {
+    if passed == 0 && failed == 0 && skipped == 0 && xfailed == 0 && xpassed == 0 && errors == 0 {
         return "Pytest: No tests collected".to_string();
@@
-    if failed == 0 && passed > 0 && !extras_present {
+    // Errors (or any collected failure detail) must never collapse into the
+    // all-green short form: that would hide real breakage from the caller.
+    if failed == 0 && errors == 0 && passed > 0 && !extras_present && failures.is_empty() {
         return format!("Pytest: {} passed", passed);
@@
     result.push_str(&format!("Pytest: {} passed, {} failed", passed, failed));
+    if errors > 0 {
+        result.push_str(&format!(", {} error{}", errors, if errors == 1 { "" } else { "s" }));
+    }
@@ failures 渲染
-            } else if first_line.starts_with("FAILED") {
+            } else if first_line.starts_with("FAILED") || first_line.starts_with("ERROR") {
+                // ... label = "ERROR" | "FAIL";trim 兩種前綴;render "[ERROR] path"
@@ parse_summary_line
+            } else if word.contains("error") {
+                // Matches both "1 error" and "2 errors" (setup/teardown or
+                // collection errors). These are real failures for the caller.
+                counts.errors = n;
+            }
```

diff 全文 = `srv/tools/rtk/0001-fix-pytest-error-count.patch`(git format-patch
產物,250 行,已驗證 `git apply --check` 在 pin SHA 乾淨套用)。

## 三層測試結果

### a) Rust 單元測試(新增 4 個,仿既有 inline 模式)

| 測試 | 覆蓋 fixture 字串 | 結果 |
|---|---|---|
| `test_parse_summary_line_errors` | `20 passed, 1 error`(裸)/ `2 errors` / `=== 1 error ===`(error-only)/ `1 passed, 2 failed, 3 errors`(混合) | PASS |
| `test_filter_pytest_errors_not_collapsed_to_all_green` | fixture error 全輸出(ERRORS 區塊 + 裸 summary) | PASS |
| `test_filter_pytest_collection_error` | `Interrupted: 1 error during collection` + `=== 1 error in 0.12s ===` | PASS |
| `test_filter_pytest_mixed_failures_and_errors` | `7 passed, 2 failed, 1 error` + `[ERROR]` 標籤斷言 | PASS |

**Mutation bite 已證**:臨時移除 `error` 解析分支 → 4 個新測試全紅
(panicked at :450/:485/:507/:533)、既有 9 個 pytest 測試仍綠 → 還原後 13/13 綠。

### b) 既有測試回歸(全 workspace)

| 基準 | 結果 |
|---|---|
| base(pin SHA 6785a6c7) | 2150 passed / 0 failed / 8 ignored |
| HEAD(8a87a1e6) | **2154 passed / 0 failed / 8 ignored**(差值恰 = 我的 +4) |
| `cargo fmt --all --check` | PASS |
| `cargo clippy --all-targets` | 0 warnings |

(8 ignored = 上游需安裝 binary 的整合測試,base 與 HEAD 相同,非我引入。)

### c) 真實對抗驗證(`/tmp/pytest-scenarios/`,native pytest 9.0.3 @ mac_dev venv vs rtk binary)

| 場景 | native pytest(exit) | base rtk @6785a6c7(exit) | patched rtk(exit) | 判定 |
|---|---|---|---|---|
| s1 壞 fixture(conftest raise) | `20 passed, 1 error in 0.04s`(1) | `Pytest: 20 passed`(1)← **吞 error** | `Pytest: 20 passed, 0 failed, 1 error` + `ERROR at setup of test_uses_broken` 細節 + tee 提示(1) | FIXED |
| s2 collection error(import 不存在模組) | `1 error in 0.05s` + Interrupted(2) | `Pytest: No tests collected`(2)← **誤導** | `Pytest: 0 passed, 0 failed, 1 error` + `ERROR collecting tests/test_s2.py` + ModuleNotFoundError 細節(2) | FIXED |
| s3 混合 7P+2F+1E | `2 failed, 7 passed, 1 error in 0.02s`(1) | `Pytest: 7 passed, 2 failed`(1)← **吞 error 計數+細節** | `Pytest: 7 passed, 2 failed, 1 error` + 3 個問題全列(error 細節含 `bad fixture` raise 行)(1) | FIXED |
| s0 全綠 sanity | `5 passed`(0) | `Pytest: 5 passed`(0) | `Pytest: 5 passed`(0)**byte-identical** | 無回歸 |

exit code 四場景兩 binary 全部與 native 一致(透傳本就正確,patch 未碰)。

## 交付物

| 物件 | 路徑 |
|---|---|
| patch | `/Users/ncyu/Projects/TradeBot/srv/tools/rtk/0001-fix-pytest-error-count.patch` |
| README(pin/缺陷/build/授權/PR) | `/Users/ncyu/Projects/TradeBot/srv/tools/rtk/README.md` |
| patched release binary(供 E4 驗證/PM 裝機,未入 PATH) | `/tmp/rtk-work/target/release/rtk`(已複驗為 patched 版) |
| base binary(A/B 對照用,可棄) | `/tmp/rtk-base-binary` |
| 場景目錄 | `/tmp/pytest-scenarios/{s0_all_green,s1_fixture_error,s2_collection_error,s3_mixed}` |
| **上游 PR** | **<https://github.com/rtk-ai/rtk/pull/2399>**(OPEN,target `develop` 按上游規範;branch `yunancun/rtk:fix/pytest-error-count`;PR 正文含復現輸出+測試證據+Claude Code 署名行) |

## 治理對照

- 全程在 /tmp 工作;我們 repo 只新增 `srv/tools/rtk/`(2 檔)+ 本報告 + E1
  memory 追加,**未 commit 我們 repo**(等 PM 批次)。
- 上游規範遵守:CONTRIBUTING 全讀;Conventional Commit `fix(pytest): ...`;
  branch 命名 `fix/<scope>-<desc>`;PR template(Summary/Test plan checklist)
  照填;pre-commit gate 三關(fmt --check / clippy / test)全過;TDD(mutation
  bite 證測試先紅後綠);代碼註釋英文(上游慣例,dispatch 明示;
  bilingual-comment-style 適用於我們 repo,不適用上游貢獻)。
- Apache 2.0:README 含出處與授權聲明;patch 即我們提交上游的同一份修復。
- 硬約束零接觸(純外部工具 repo,無 migration/singleton/IPC)。

## 不確定之處(誠實披露)

1. **CLA 待簽(operator 動作)**:上游 CONTRIBUTING 要求 CLA Assistant 簽署
   (PR 開啟後 bot 留言,點連結用 GitHub 帳號 yunancun 簽一次)。截至報告時
   bot 留言尚未出現(PR 剛開,唯一 check `check-target` SKIPPED=target develop
   正確);未簽 CLA 上游不會 merge。
2. **headline 含 `0 failed`**:errors>0 且 failed==0 時輸出
   `Pytest: 20 passed, 0 failed, 1 error`(dispatch 範例為 `20 passed, 1 error`)。
   理由:上游 headline-pair `{passed} passed, {failed} failed` 是固定骨架
   (skip-only 場景上游今天就印 `0 failed`),保留它=零修改既有行+風格一致,
   上游接受率優先;error 計數可見性(硬需求)不受影響。E4 斷言建議用
   `contains("1 error")` 而非整行精確匹配。
3. **diff 大小 vs 目標**:source diff +38/−8(含 9 行註釋)≈ dispatch 的
   `<40 行` 目標上緣;含上游強制要求的測試後總 +133/−8。再縮只能砍註釋或
   砍次缺陷修復,判斷不值得。
4. 上游 PR 量大(#2399 號段),review 時程不可控;在 merge 前我們靠本地
   patch + pin 自建,不阻塞。

## Operator / PM 下一步

1. PM:E2 審查本 patch → E4 用 `/tmp/rtk-work/target/release/rtk` 跑我們
   測試基準線驗證(尤其 tests/replay 4 個 collection error 場景與全庫
   error 計數對齊)→ 批次 commit `srv/tools/rtk/`。
2. Operator:PR #2399 出現 CLA Assistant 留言後用 yunancun 帳號簽署。
3. Linux 端裝機時按 `srv/tools/rtk/README.md` 雙端 build 流程(同 patch 同 SHA)。
4. 上游 merge 後:更新 pin SHA、刪 patch 行(README 已寫退場路徑)。

---

# E2 RETURN 修復輪(2026-06-11,同日第二輪)

## HIGH 發現與修法

**E2 HIGH(A/B 實證)**:patch 初版把 `-q` 裸 summary 捕捉的 substring 啟發式
加寬了 error 臂(`|| trimmed.contains(" error")`),但該啟發式是
「contains 類別詞 + contains ` in ` + 第一命中即佔位(`summary_line.is_empty()`)」——
失敗測試 Captured stdout 的 `retrying after error in connection pool` 行被誤捕為
summary → 真 footer 被擠掉 → RED run 輸出 `Pytest: No tests collected`,
重新打開補丁要修的缺陷 #2。

**修法(錨定整個啟發式,非只補 error 臂;採 E2 INFO 建議)**:

1. 新 `is_bare_summary_line()` 取代整段 substring 條件:**整行 summary 文法**
   — 每個逗號段必須是 `<count> <category>`(category 白名單 = pytest core
   全類別 passed/failed/skipped/deselected/xfailed/xpassed/error(s)/
   warning(s) + 插件常見 rerun)+ 尾綴 `in <float>s` + 可選 `(h:mm:ss)`
   (>60s run pytest 會加人類可讀後綴,純 `in X.XXs$` 錨會誤殺)。
2. **first-match → last-match**(移除 `summary_line.is_empty()` 佔位):
   真 footer 永遠是 pytest 輸出最後一個合法形;即使測試自己驅動 pytest 並把
   內層 summary 逐字印進 stdout(文法上不可分辨),也會被真行覆蓋。
   不改此項則文法錨仍留 false-green 向量。
3. dispatch 方案三(Failures/Summary 段內不捕捉)**經 trace 否決**:
   `-q` RED run 的真裸 summary 到達時狀態機正在 Failures/Summary 段內
   (`=== FAILURES ===` 之後),段內禁捕=連真 summary 一起丟。
4. **pre-existing 臂一併修復**(E2 INFO):`worker 3 passed in shard cleanup`
   餌在 upstream base 就被誤捕,且 base 對 RED run 輸出**假全綠**
   `Pytest: 3 passed`(exit=1、零細節)——比 INFO 預估更嚴重,已寫進 PR
   做為錨定整個啟發式的賣點(接受率正向)。

source delta(對初版):條件塊 14 行 → 1 行呼叫 + helper ~45 行(含 doc
comment);新測試 3 個 +~75 行。`is_some_and`/let-else 均為 codebase 既用
(rust-version 1.91)。

## 新增回歸測試(3 個,前一棒 4 個保留全綠)

| 測試 | 覆蓋 | mutation 紅證 |
|---|---|---|
| `test_is_bare_summary_line_anchoring` | 6 真形(含 `(0:01:01)` 後綴)accept + 7 餌形 reject(stdout prose / `===` 形 / `FAILED` 行 / `no tests ran`) | Mutation B 紅(:605,`5 failed widgets in 1.2s` 放行) |
| `test_filter_pytest_stdout_prose_not_mistaken_for_summary` | E2 HIGH 原場景:RED run + Captured stdout 兩餌行 → 斷言非 No tests collected、`1 passed, 1 failed`、細節在 | Mutation A 紅(:645) |
| `test_filter_pytest_verbatim_inner_summary_in_stdout` | stdout 逐字內層 summary `2 passed in 1.50s` → 真 footer 勝(鎖 last-match-wins) | Mutation A 紅(:672) |

**Mutation 自證**:A=把錨定 wiring 還原成舊 substring 條件 → 2 filter 級測試紅
(21 passed/2 failed)、helper 單測綠(helper 未動,符合預期);B=拔掉 helper
的 stats 文法臂(只留 duration 錨)→ helper 單測紅(15/1)。各自還原後
16/16 綠(9 既有 + 4 前一棒 + 3 新)。

## 測試與 A/B 復驗

- `cargo fmt --all --check` PASS / `cargo clippy --all-targets` 0 warnings /
  全 workspace **2157 passed / 0 failed / 8 ignored**(= base 2150 + 前一棒 4 + 本輪 3)。
- 六場景 × 四 binary(native pytest 9.0.3 / base@6785a6c / prev-patched@8a87a1e /
  fixed@32561a0),原始輸出 `/tmp/rtk-ab-results.txt`:

| 場景 | native(exit) | base | prev-patched(E2 抓的版本) | fixed |
|---|---|---|---|---|
| s0 全綠 | `5 passed`(0) | `Pytest: 5 passed` | 同 | 同(**byte-identical**) |
| s1 壞 fixture | `20 passed, 1 error`(1) | `20 passed` 吞 error | `20 passed, 0 failed, 1 error`+細節 | 同 prev-patched(前輪修復原樣保留) |
| s2 collection error | `1 error`(2) | `No tests collected` | `0 passed, 0 failed, 1 error`+細節 | 同 prev-patched |
| s3 混合 7P+2F+1E | `2 failed, 7 passed, 1 error`(1) | `7 passed, 2 failed` | 全列 | 同 prev-patched |
| **s4 stdout error 餌(E2 HIGH)** | `1 failed, 1 passed`(1) | `1 passed, 1 failed` OK | **`No tests collected`**(E2 場景重現) | **`1 passed, 1 failed`+細節 = FIXED** |
| **s5 stdout passed 餌(pre-existing)** | `1 failed, 1 passed`(1) | **`Pytest: 3 passed` 假全綠** | `3 passed, 0 failed`+細節(計數仍錯) | **`1 passed, 1 failed`+細節 = FIXED** |

exit code 六場景四 binary 全透傳一致。

## 交付物更新

| 物件 | 狀態 |
|---|---|
| commit | **squash 成單 commit `32561a0755757cdab5f7baeab05ec9b6f41148fb`**(直接落在 pin SHA 上;選 squash 理由:上游尚無人 review,單一自含 commit + 單一 0001 patch 檔對 E4/裝機最乾淨;message 加一條 anchored-detection bullet,Conventional Commit 保持) |
| patch | `srv/tools/rtk/0001-fix-pytest-error-count.patch` 重產(398 行),pin SHA 臨時 worktree `git apply --check` PASS |
| README | `srv/tools/rtk/README.md`:缺陷 #4(substring 誤捕,含 base 假全綠)、行為表 +2 餌場景行、單 squash commit 說明、commit SHA 更新 |
| binary | `/tmp/rtk-work/target/release/rtk` 重建(20:42,A/B 復驗即此 binary);prev-patched 留檔 `/tmp/rtk-prev-patched-binary` 供 E2 對照 |
| PR #2399 | force-with-lease 更新 head=`32561a0`;正文加英文「Review update: anchored `-q` bare-summary detection」節(披露 reviewer-found regression + pre-existing 假全綠 + 修法)+ test plan 數字更新(2157、+7 tests、5 場景) |
| 場景 | `/tmp/pytest-scenarios/` + `s4_stdout_error_bait` `s5_stdout_passed_bait` |

我們 repo 仍未 commit(等 E2→E4→PM 鏈)。CLA bot 留言已出現,operator 簽署
連結就緒:<https://cla-assistant.io/rtk-ai/rtk?pullRequest=2399>(用 yunancun)。

## 不確定之處(本輪)

1. category 白名單含 `rerun`(pytest-rerunfailures):省略它會讓裝該插件的
   使用者 summary 不被捕捉(回到 No tests collected),含它的代價是極小的
   餌面擴大。判斷收益>風險,已含。其他第三方插件若注入未知類別詞,該 run
   會退化為 No tests collected(與 base 對非 4 類別詞行為一致,非新增風險)。
2. last-match-wins 移除了 `summary_line.is_empty()`,語意上也覆蓋了 `===`
   wrapped 形誤捕的 pre-existing 弱點(bogus 早行被真 footer 覆蓋);wrapped
   臂本身的 substring 條件未動(餌面要求行首 `===`,實務不可達,動它純增
   diff 傷接受率)。PR 未對 wrapped 臂做任何聲稱。
