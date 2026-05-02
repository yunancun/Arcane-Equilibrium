# E1 Report — Audit script E2 MEDIUM fix（2026-05-02）

Branch：`audit/2026-05-09-and-16-3c-funding-arb-followup`
Base：5abb00e -> New：2937a82

## 1. 任務摘要
PA 派發兩個 E2 MEDIUM finding 修復：
- MED-1：14d audit `net_pnl` dead var + 矛盾英文註解
- MED-2：7d audit `DEPLOY_UTC` 來源證據

要求最小改動 / 零邏輯變化 / 不碰其他 4 個 audit 檔 / 不改 TODO.md / 不修 LOW（partial-close disclaimer 後續）/ 不 amend 既有 commit。狀態：完成、push、Linux synced。

## 2. 修改清單

| 檔 | 行為 | 行數 | 說明 |
|---|---|---|---|
| `helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.py` | 刪行 | -1 | 刪 dead var `net_pnl = stats.gross_bps_sum - 0.0`（未被引用、與下方 NOTE 矛盾） |
| `helper_scripts/db/audit/2026-05-09_3c_7d_audit.py` | 加注釋 | +14 | DEPLOY_UTC 之上補雙語 inline timeline + 解釋 commit ts ≠ deploy ts |

## 3. 關鍵 diff

### MED-1（14d audit）
```diff
-    net_pnl = stats.gross_bps_sum - 0.0   # gross_pnl already net of fee in fills.realized_pnl
     # 注意：trading.fills.realized_pnl 在 close fill 上已是 gross PnL；
```

### MED-2（7d audit）
```diff
 # True 3C TOML deploy timestamp: 2026-05-02 17:42 UTC (19:42 CEST).
+#
+# DEPLOY_UTC: runtime cutover moment when 3C TOML actually took effect.
+# NOT the commit timestamp (commit ts != deploy ts in OpenClaw):
+#   - commit a19797d (TOML edit):           2026-05-02 17:20:35 UTC
+#   - merge a51cdc5 (promote to main):      2026-05-02 16:17 UTC
+#   - restart_all attempt #1 (sqlx abort):  2026-05-02 16:35 UTC
+#   - restart_all attempt #2 (success):     2026-05-02 17:42:59 UTC <- ACTUAL DEPLOY
+#     (engine PID 3202566 lstart, snapshot writer first emitted with new TOML)
+# Between #1 and #2 engine was DOWN due to sqlx V028 hash drift; no trading.
+# Window split here ensures pre-deploy 7d baseline is genuinely pre-3C-TOML.
+#
+# DEPLOY_UTC：3C TOML 真正生效的 runtime cutover 時點，**不是** commit timestamp。
+# OpenClaw commit != deploy；commit/merge 是檔案改動，restart_all 才是運行時生效。
+# 詳見 project_2026_05_02_p0_sqlx_hash_drift.md memory entry。
 DEPLOY_UTC = "2026-05-02 17:42:00+00"
```

## 4. 治理對照

- CLAUDE.md §七「雙語注釋（強制）」：MED-2 補的 14 行嚴格雙語對照 —— 符合。
- CLAUDE.md §二 原則 #8「交易可解釋 — 為什麼、何時必可重建」：MED-2 timeline 是 audit script 自證據鏈的其中一環 —— 符合且加強。
- CLAUDE.md §八「最小影響底線」：本輪 +14/-1 only 兩檔，零邏輯動 —— 符合。
- 規則「Engine commit ≠ deploy」：本 commit 落實此原則於審計腳本注釋層。
- E2 review at 5abb00e（report path：`docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-02--audit_3c_7d_and_funding_arb_14d_review.md`）：兩個 MEDIUM 已對應修復；LOW（partial-close disclaimer）PA 明示後續處理。

## 5. 不確定之處

- ASCII-only：DEPLOY_UTC 注釋使用 `<-` 不用 `←`，避免 Mac/Linux 顯示 / cargo doc 編碼差異 —— 不確定 PA 模板是否預期 unicode arrow，但 ASCII 是更安全的跨平台選擇。
- 回顧後若 PA 發現 partial-close disclaimer LOW 需同 batch 修，需重派 E1。

## 6. Operator 下一步

- E2 重 review：對 commit 2937a82 確認兩個 MEDIUM 已關閉、無新 finding。
- E4 回歸：本輪純注釋/dead var 刪除不應觸發測試行為差，但仍依強制鏈跑回歸。
- PM Sign-off 後 push to main（branch policy 等 PA / PM 決定 squash vs merge）。

---

## Verify outputs

```
$ python3 -c "import ast; ast.parse(open('helper_scripts/db/audit/2026-05-09_3c_7d_audit.py').read())"; echo "exit=$?"
exit=0
$ python3 -c "import ast; ast.parse(open('helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.py').read())"; echo "exit=$?"
exit=0
$ git diff 5abb00e..HEAD --stat
 helper_scripts/db/audit/2026-05-09_3c_7d_audit.py          | 14 ++++++++++++++
 .../db/audit/2026-05-16_funding_arb_14d_audit.py           |  1 -
 2 files changed, 14 insertions(+), 1 deletion(-)
```

Linux trade-core sync：5abb00e -> 2937a82 (ff-only) confirmed。
