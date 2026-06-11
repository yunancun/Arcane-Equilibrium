# L2 P4 E1-C — E2 RETURN 修復輪報告（改號 V138 / [83]-[87] + 三語義修復）

- 日期：2026-06-11
- 角色：E1
- 分支：`feat/l2-p4-e1c`（worktree `/tmp/wt-l2-p4-e1c`）
- 基底：`f90f1a26`（段2）→ merge `origin/main`（tip `62085d17`）
- 產出 commit：**merge `809bf568`** + **fix `e752e960`**，已 push origin
  （`f90f1a26..e752e960`）
- 狀態：E1 IMPLEMENTATION DONE，待 re-E2；`git status --porcelain` 乾淨

## 一、任務摘要

E2 審查期間 P5-SM 鏈 merge 進 origin/main（`ca80d084`）佔走 V137
（`V137__lease_ipc_soak_events.sql`）與 healthcheck `[82]`。本輪四項：
1. C-CRIT-1 改號 + merge（V137→V138、[82]-[86]→[83]-[87]）
2. C-LOW-1 `prh_falsification_chk` 頂層型別鎖（1 行 CHECK）
3. C-LOW-2 registry double-seal warning no-bite（新測試）
4. PM 裁決折入：stage0r `defer` verdict 改映 pending（非 failed）

動手前 re-fetch 實證：origin/main 仍 `62085d17`，**V138 free / [83]+ free**
（`git grep 'V138|check_8[3-9]_' origin/main` 僅 2 處散文式「免開 V138」
假設性提及，零實際佔用）。push 前再次 re-fetch 確認未再被搶。

## 二、commit 拆分（小決策，自選並註明理由）

PM 允許「一個 merge commit + 一個修復 commit」，拆分點自選：

- **`809bf568`（merge commit）**：衝突解法 + **全部機械改號**（6 檔）。
  理由：runner import 改名後若 checks 檔不同 commit 落地，merge commit
  import-RED；migration 不改名則樹內雙 V137。故機械改號整體進 merge
  commit，保每 commit import-coherent + migration 命名空間單號。
  **A 點綠性已實證**：detached worktree checkout `809bf568` → 樹內單一
  V138、runner import OK、104 passed。
- **`e752e960`（fix commit）**：僅三語義修復（4 檔 +108/−21），供 E2
  隔離審查淨 delta。

## 三、改號清單（檔案 / 函數 / 編號對照）

| 項目 | 舊 | 新 |
|---|---|---|
| migration 檔名 | `sql/migrations/V137__research_fdr_tables.sql` | `V138__research_fdr_tables.sql`（git mv） |
| migration 檔內字面 | `V137` ×20（Guard A/B/C FAIL、role-absent NOTICE、註釋） | `V138` ×20 |
| migration 檔內 hc 引用 | `[85]` cross-family dup | `[86]` |
| checks 五函數 | `check_82_alpha_wealth_family_cardinality` / `check_83_..._orphan_refund` / `check_84_..._refund_amount_mismatch` / `check_85_pre_reg_cross_family_duplicate_spec` / `check_86_hidden_oos_state_regression` | `check_83_*` / `check_84_*` / `check_85_*` / `check_86_*` / `check_87_*`（單趟映射替換，無鏈式覆蓋） |
| deploy 探測 helper | `_v137_deployed`（checks + reconciler 各一） | `_fdr_tables_deployed`（撞號免疫命名，PM 指令） |
| reconciler skip 字串 | `"v137_not_deployed"` | `"fdr_tables_not_deployed"`（同款免疫化，小決策） |
| checks-test fixture/測名 | `_cur_v137` / `test_82_*..test_86_*` / `test_86_skips_independently_of_v137` | `_cur_fdr` / `test_83_*..test_87_*` / `test_87_skips_independently_of_fdr_tables` |
| runner | import 五函數 + append `[82]`-`[86]` | import 改名 + P5-SM `[82]` 塊保留在前、我的塊 `[83]`-`[87]` 在後（註釋註明平移原因） |
| SCRIPT_INDEX | 最後更新行 + 3 表行 `[82]`-`[86]`/V137 | `[83]`-`[87]`/V138 |
| cron `ml_training_maintenance.py` | 2 處 V137 註釋 | V138 |
| reconciler docstring | `[82]-[86]` 引用 + V137 ×6 | `[83]-[87]` + V138 |

未碰：e1b 檔（0 檔交集）；P5-SM 全部檔（其 V137=lease_ipc_soak_events 合法）；
P2/P3b 散文「無 V137」歷史提及（l2_capability_registry.py / altcap_basket.py /
TOML，PM merge 後統一 sweep）。

## 四、merge 衝突解法摘要（恰 2 處，皆並存解，merge 非 rebase、未 force-push）

1. `helper_scripts/SCRIPT_INDEX.md`（「最後更新」行）：我的 E1-C 條目
   （同步改 V138/[83]-[87]）置前 → P5-SM 條目降「歷史更新：同日」 →
   共同尾巴（L2 P2p sentinel 起）逐字保留。Python 腳本以
   `歷史更新：同日 L2 Mesh P2p incident sentinel` 為錨點切分、斷言兩側
   尾巴 byte-identical 後重組。
2. `helper_scripts/db/passive_wait_healthcheck/runner.py`（append 區）：
   P5-SM `[82] lease_ipc_soak_window` 塊（含註釋）原樣保留在前，我的塊
   平移 [83]-[87] 接後。import 區自動 merge 成功（P5-SM `check_81`/
   `check_82` import 行原樣保留），我的 import 塊只改函數名與註釋。

## 五、Linux dry-run 四實證（原文）

環境：trade-core `trading_postgres`（PostgreSQL 16.11），
`CREATE DATABASE p4v138_dryrun TEMPLATE template0`（template1 collation
version mismatch workaround），完事 `DROP DATABASE` + pg_database 計數=0
+ 容器/host 暫存檔全清。

**APPLY 1**：exit 0（尾段 `COMMIT`）。
**APPLY 2（冪等）**：exit 0，`grep -cE ERROR` = **0**（全程
`already exists, skipping` NOTICE）。

**(a) N-1 — NULL n_eff 必拒**：
```
ERROR:  new row for relation "alpha_wealth_ledger" violates check constraint "awl_debit_fields_chk"
DETAIL:  Failing row contains (3, 2026-06-11 03:01:42.747451+02, ml_advisory:funding, ml_advisory, funding, debit, dryrun-d1, -0.0005000000, 0.0005000000, null, null, 1, null, null, null, {}, dryrun).
```

**(b) N-2 — 同 debit_id refund 後第二 terminal 撞 unique**：
```
ERROR:  duplicate key value violates unique constraint "awl_one_terminal_per_debit"
DETAIL:  Key (debit_id)=(dryrun-d2) already exists.
```

**(c) role-absent NOTICE**（APPLY 1 與 2 皆出，:215/:424/:463 三處）：
```
psql:/tmp/V138.sql:424: NOTICE:  V138: trading_ai role absent (dev sandbox); REVOKE on PUBLIC sufficient
psql:/tmp/V138.sql:463: NOTICE:  V138: trading_ai role absent (dev sandbox); view grants skipped
```

**(d) C-LOW-1 修復生效 — 頂層 array spec_jsonb 必拒**（修復前此 INSERT
經 `?` 元素匹配 TRUE + `->` NULL + typeof(NULL) NULL ⇒ 三值放行）：
```
ERROR:  new row for relation "pre_registered_hypotheses" violates check constraint "prh_falsification_chk"
DETAIL:  Failing row contains (2, 2026-06-11 03:01:42.898808+02, ml_advisory:basis, ml_advisory, basis, null, ["falsification_test"], bbbb…bbbb, null, dryrun).
```

佐證：`alpha_wealth_debit_state` 視圖 `dryrun-d2 → confirmed`。

## 六、defer→pending 測試證據 + 字彙偏差（deviation）

**字彙偏差（最小安全解，唯一 deviation）**：派工原文「producer 只寫
pass/defer 兩種 verdict（residual_stage0r_preflight.py:605）」——實查
gate 字彙 = `ResidualAlphaVerdict = Literal["pass", "fail", "defer_data"]`
（`residual_alpha_gate.py:34`），且 preflight 對**任何** verdict 皆蓋章寫
payload（:589/:600-603）。按裁決操作核心「只有 `verdict=='pass'` 才進
demo_confirm_verdict」落地：**非 pass（defer_data / fail / 其他）一律
skip-pending**，計入新 summary 計數 `stage0r_not_pass`（與既有
`stage0r_verdict_missing` 分流，觀測誠實）。gate-fail verdict 同收
skip-pending 臂——與「failed 僅經 net<0 路徑可達」一致。

實作位置：`alpha_wealth_refund_reconciler.py` verdict 讀取後
`if not stage0r_green: summary["stage0r_not_pass"] += 1; continue`
（中文 rationale 注釋含 PM 裁決四要素）；`_STAGE0R_VERDICT_SQL` 註釋 +
MODULE_NOTE 硬邊界行同步。

測試證據：
- `test_stage0r_non_pass_verdict_stays_pending_zero_dead_mode`
  （parametrize `defer_data` / `fail`）：demo net=+5bps、40 trades 下
  斷言 `stage0r_not_pass==1`、`failed==0`、`confirmed==0`、
  ledger inserts==[]、lessons inserts==[]。
- `test_failed_only_reachable_via_negative_net`：stage0r=pass + net=−8bps
  → failed=1，lesson why 必為 `net -8.00 bps < 0`，
  `stage0r replay preflight not green` 文案**不在** content（結構性不可達）。
- 取代 `test_failed_on_stage0r_red_regardless_of_net`（其斷言舊 False-臂
  行為，裁決後語義反轉，屬必然 collateral 更新非回歸）。
- **mutation bite**：移除 non-pass guard → `[defer_data]`/`[fail]` 兩測紅
  （assert 320 行 stage0r_not_pass）；還原 → 綠。

## 七、C-LOW-1 / C-LOW-2 關鍵 diff

C-LOW-1（`V138__research_fdr_tables.sql`，fix commit 內）：
```sql
    CONSTRAINT prh_falsification_chk CHECK (
        jsonb_typeof(spec_jsonb) = 'object'          -- ← 新增（最前置）
        AND spec_jsonb ? 'falsification_test'
        AND jsonb_typeof(spec_jsonb->'falsification_test') = 'object'
        ...
```
檔頭「兩個殘洞」→「三個殘洞」+ inline 註釋補第 (3) 洞攻擊路徑說明。

C-LOW-2（`test_residual_hidden_oos_bridge.py` 檔尾新測試）：直驅
`_persist_hidden_oos_state_registry`，`_FakeCursor` 實例 `rowcount=0` +
`caplog` 斷言 `"double-seal skipped"`；mutation 證：刪
`experiment_registry.py:1159-1164` warning 塊 → 紅，還原 → 綠。

## 八、測試與驗證總表

| 套件 | 結果 |
|---|---|
| 三主測試檔（reconciler / checks / cron） | **30 passed**（28 原 −1 取代 +2 parametrize +1 新） |
| adjacent（bridge / preflight / producer_db / cron dir / healthcheck dir） | **148 passed** |
| full `ml_training` + `learning_engine` | **983 passed / 16 skipped**（基線 980/16，+3=淨新增，0 回歸） |
| mutation ×2（C-LOW-2 warning 塊 / non-pass guard） | 皆「刪→紅、還原→綠」 |
| commit A（`809bf568`）綠性 | detached worktree：單一 V138、runner import OK、104 passed |
| Linux dry-run | apply×2 冪等 + 四實證（上節原文） |

venv：`srv/venvs/mac_dev/bin/python`（3.12）。

## 九、治理對照

- 硬邊界 token：0 新增（`test_hard_boundary_fingerprints_zero_hits` 續綠，
  涵蓋 reconciler + checks 檔）；0 硬編碼 user path。
- Guard A/B/C：V138 全保留（僅字面改號 + C-LOW-1 收緊，無放寬面）。
- 行為中性：三重 OFF 不變（flag 預設 0 + 不在 DEFAULT_JOBS + V138 0 rows）。
- 注釋：全新增中文（英文僅技術名詞）；修 CHECK 同步修「封死」註釋
  （誤導性註釋=governance trail 教訓）。
- merge 非 rebase、未 force-push；P5-SM [82] import/append 原樣保留。

## 十、不確定之處

1. **defer 字彙偏差**（§六）需 re-E2 / PM 確認「gate-fail verdict 也收
   skip-pending 臂」符合裁決意圖（替代解=fail 單獨開臂，但那會重新引入
   非 net<0 的 dead-mode 鑄造路徑，與裁決文字矛盾，故未採）。
2. `stage0r_not_pass` 計數器命名（非 `stage0r_deferred`）：因臂同時收
   defer_data 與 fail，按誠實命名原則自選。
3. P2/P3b 檔的「無 V137」散文提及（l2_capability_registry.py 等 4 處）
   未碰，等 PM merge 後統一 sweep（派工原文指示）。

## 十一、Operator / PM 下一步

1. re-E2 對抗審本輪兩 commit（fix commit `e752e960` 為語義淨 delta）。
2. E4 Linux 回歸（owed 不變：dead-mode retrieve_lessons 真查 +
   reconciler 真 PG E2E dry-run；V138 schema 驗證本輪已四實證）。
3. merge 後 PM sweep B 線/P2/P3b 散文 V137 字面（派工已預告）。
