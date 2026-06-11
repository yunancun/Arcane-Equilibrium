# E1 報告 — L2 P4 E1-C stage0r verdict 三向映射微修 · 2026-06-11

- **Branch / worktree**：`feat/l2-p4-e1c` @ `/tmp/wt-l2-p4-e1c`
- **Base**：`e752e960`（E2 RETURN 修復輪收口）
- **Commit**：`9f12a1d4`（已 push origin；2 檔 +63/−31）
- **狀態**：E1 IMPLEMENTATION DONE，待 E2 審查

## 任務摘要

上輪 E2 RETURN 修復把 stage0r verdict 映射收成「僅 `pass` 進真值表，其餘一律
skip-pending」——最小安全解，但使 M1 已 ratify 真值表
`failed ⇔ n_trades≥30 AND (net<0 OR NOT stage0r_green)` 的 NOT-green 臂被結構性
餓死。PM 裁決三向映射：

| verdict | 映射 | 後果 |
|---|---|---|
| `pass` | `stage0r_green=True` 進真值表 | confirmed/pending 按 net+days |
| `fail` | `stage0r_green=False` 進真值表 | n≥30 → failed + debit_failed + 鑄 dead-mode lesson（QC FIX-1.3「被證偽→鑄 dead-mode」；`fail` 是 replay preflight 上 DSR/PBO/cost gate 的結論性統計否定） |
| `defer_data` / 缺席 | 本輪 skip，維持 pending | 非結論性，不進真值表、不鑄 lesson（上輪裁決不變） |

## 修改清單（2 檔，0 其他改動）

1. `program_code/ml_training/alpha_wealth_refund_reconciler.py`
   - verdict 映射處三向重寫（功能行 ~5 行）：
     `stage0r_verdict not in ("pass","fail")` → `stage0r_deferred` 計數 + skip；
     否則 `stage0r_green = stage0r_verdict == "pass"` 進真值表。
   - MODULE_NOTE 硬邊界 bullet + `_STAGE0R_VERDICT_SQL` 注釋塊同步更新裁決理由
     （中文；舊兩向映射敘述全部訂正，無殘留誤導注釋）。
   - summary 計數鍵更名 `stage0r_not_pass` → `stage0r_deferred`。
2. `program_code/ml_training/tests/test_alpha_wealth_refund_reconciler.py`
   - 新 `test_stage0r_fail_verdict_enters_truth_table_failed_mints_dead_mode`：
     verdict='fail' + n=40 + net=+5bps（≥0）→ 斷言 failed=1 + `debit_failed`
     事件（amount=0、evidence 帶 `"stage0r_green": false`）+ dead-mode lesson
     鑄造，且 why 文案 = "stage0r replay preflight not green"、net<0 文案不得
     出現（證 NOT-green 臂獨立驅動，非搭 net<0 便車）。
   - 原 parametrize `["defer_data","fail"]` 拆分：defer_data 維持 pending 斷言
     不動（僅計數鍵改名），補字彙外值 `some_future_verdict` 釘 fail-closed 臂。
   - `test_failed_only_reachable_via_negative_net` 更名為
     `test_failed_via_negative_net_with_green_stage0r`：其「failed 唯一可達 via
     net<0 / not-green 文案結構性不可達」閉環宣稱被本輪裁決推翻，docstring 改為
     「兩臂 why 歸因分流」語義；斷言本身不變（該情境下仍正確）。
   - `test_stage0r_verdict_missing_stays_pending`（缺席案例）**未動**。

## 關鍵 diff（映射核心）

```python
stage0r_verdict = str(verdict_row[0])
if stage0r_verdict not in ("pass", "fail"):
    # PM 三向裁決：'defer_data' = 非結論性——既不退款也不鑄 dead-mode，
    # 本輪跳過維持 pending（與 verdict 缺席同構）。字彙外值同走此臂
    # （fail-closed：不認識的 verdict 不渲染結論）。
    summary["stage0r_deferred"] += 1
    continue
# 'fail' 是 gate 的結論性統計否定——按 QC FIX-1.3 走 A 線真值表 False 臂；
# 'pass' 走 True 臂。NOT-green 臂自此真實可達。
stage0r_green = stage0r_verdict == "pass"
```

## 驗證證據（mac_dev venv 3.12.13，即時跑）

- **綠**：`test_alpha_wealth_refund_reconciler.py` **18 passed**（17→18，淨 +1：
  parametrize 維持 ×2 + 新 fail 測）；adjacent `test_residual_hidden_oos_bridge.py`
  + `test_residual_stage0r_preflight.py` **51 passed**；合跑 **69 passed / 0 failed**。
- **Mutation bite**（先 commit 再 mutate，python exact-string 正向替換；還原用
  `git checkout --` 於已 commit 檔，安全）：把 fail 臂改回 skip-pending
  （`not in ("pass","fail")` → `!= "pass"`）→ **僅 fail 案例測試紅（1 failed /
  17 passed）**，defer/缺席測試在 mutation 下仍綠（證測試區分度）；還原後 69 全綠。
- **cron adjacent**：`test_ml_training_maintenance_cron_static.py` = 3 passed +
  1 failed（`test_f08_runner_pins_the_five_audit_jobs`）。**pre-existing 實證**：
  detached worktree @ base `e752e960` 同樣 1 failed / 3 passed（清單相同）。
  根因 = merge-seam：main 側 audit 測試（`da2aba119`，經 merge `809bf568` 入
  分支）pin `VALID_JOBS == CORE_JOBS + AUDIT_JOBS`，而分支 `f90f1a26` 引入
  `OPTIONAL_JOBS = ("residual_preflight", "alpha_wealth_reconciler")` 併入
  VALID_JOBS。**非本輪引入**（本 diff 0 觸碰該兩檔），但 merge main 前須收
  ——超出本微修「0 其他改動」範圍，flag PM/E2 裁決（修法大概率 = 更新 main 側
  pin 斷言納入 OPTIONAL_JOBS）。

## 治理對照

- 硬邊界 0 觸碰：max_retries / live_execution_allowed / execution_authority /
  system_mode 無涉；寫面仍僅 `research.alpha_wealth_ledger`（append-only）+
  `agent.lessons`；測試檔既有 hard-boundary 指紋測試（含路徑紅線）續綠。
- 0 migration / 0 Rust / 0 新 singleton / 0 新硬編路徑。
- 三重 OFF 不變（flag 預設 0 + cron OPTIONAL + V138 0 rows），行為中性。
- 注釋 Chinese-first；舊映射的誤導性注釋（MODULE_NOTE/SQL 塊/inline）全數同步
  訂正（注釋 = governance trail）。

## 小決策（E1 自決，註明理由）

1. **計數鍵更名 `stage0r_not_pass` → `stage0r_deferred`**：三向映射後 `fail`
   字面上也是 not-pass 卻進真值表不再計入，舊名對讀 cron JSON 的 operator 構成
   誤導。消費面查證：全庫 grep 僅 3 hits（源碼 ×2 + 本測試檔 ×1）；cron wrapper
   `{"summary": summary}` 整包透傳不讀鍵；healthcheck [83]-[87] 不讀此鍵。
2. **字彙外值走 defer 臂（fail-closed）**：PM 裁決只列 {pass, fail, defer_data,
   缺席}；不認識的 verdict 不渲染結論性裁決（不退款、不鑄 lesson），與缺席同構。
   已用 parametrize `some_future_verdict` 釘住。
3. **net<0 臂測試更名**：原名/docstring 宣稱「failed 唯一可達 via net<0」是上輪
   兩向映射的閉環斷言，本輪被推翻；留著 = 誤導性測試文檔。斷言未動。

## 不確定之處

- 無設計層不確定。唯一未決事項 = 上述 f08 merge-seam pre-existing 紅的歸屬與
  收法（PM/E2 裁決）。

## Operator / PM 下一步

1. E2 對抗審查本 commit `9f12a1d4`（單 commit，diff 面小）。
2. E2/PM 裁決 f08 pin 測試 merge-seam 紅的收法（merge main 前必收）。
3. E4 Linux 回歸時連帶驗：reconciler fail-verdict 路徑真 PG dry-run（沿
   E1-C 既有 owed-E4 清單：dead-mode retrieve_lessons 真查 + E2E dry-run）。
