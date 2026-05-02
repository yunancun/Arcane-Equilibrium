# E1 Report — LG5-W3-FUP-2 Fix 1 ROUND 2

Date: 2026-05-02
Author: E1
Sprint: LG5-W3-FUP-2 Fix 1
Round: 2 (E2 RETURN with 1 MED + 1 LOW)
Status: DONE — awaiting E2 round-2 review

---

## 1. 任務摘要

Operator/PA 派發 ROUND 2 純 docs/comment 修。E2 round 1 RETURN 2 finding：
- **MED-1**：`docs/healthchecks/2026-05-02--lg5_health_checks.md:217` literal `/home/ncyu/BybitOpenClaw/srv/...` 違 CLAUDE.md §七 ★★ 跨平台規則。
- **LOW-1**：3 處事實錯 — `learning.decision_features` 在 **V017** 創建（`V017__edge_predictor_tables.sql:29`），不是 V019（V019 是 `strategist_applied_params`）。

完成狀態：4 處目標位置全部修正 + 連帶 3 處同源 V019 殘留（inline comment + test docstring）一併修；驗證 4/4 綠。

---

## 2. 修改清單

| 路徑 | 變更 | 行數 | 說明 |
|---|---|---|---|
| `helper_scripts/db/passive_wait_healthcheck/checks_governance.py` | 修 | -4/+4 | docstring V019→V017、FAIL msg V019→V017、2 條 inline comment V019→V017 |
| `helper_scripts/db/test_lg5_healthchecks.py` | 修 | -3/+3 | 模組 docstring V019→V017、test name `test_fail_when_v019_missing`→`test_fail_when_v017_missing`、assertion `V019 not applied`→`V017 not applied` |
| `docs/healthchecks/2026-05-02--lg5_health_checks.md` | 修 | -5/+13 | pre-condition V019→V017、crontab 段落從 literal `/home/ncyu/...` 改成 `<ABSOLUTE_REPO_ROOT>` placeholder 描述式樣 |

無業務邏輯變動。無 SQL migration。無新 singleton。

---

## 3. 關鍵 diff（最能說明變更）

### 3.1 healthcheck doc：跨平台模板替換 literal 路徑

```diff
 2. **Add to crontab** (Linux trade-core):
    ```bash
    crontab -e
-   # add: */30 * * * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/edge_label_backfill_cron.sh
+   # crontab block — cron does NOT expand $VARS in command position, so operator
+   # MUST resolve $OPENCLAW_BASE_DIR to a literal absolute path before pasting.
+   #
+   # Pattern (do NOT paste verbatim — substitute the literal path first):
+   #   */30 * * * * <ABSOLUTE_REPO_ROOT>/helper_scripts/cron/edge_label_backfill_cron.sh
+   #
+   # Where <ABSOLUTE_REPO_ROOT> is the value of $OPENCLAW_BASE_DIR on the host:
+   #   * Linux trade-core default = $HOME/BybitOpenClaw/srv (resolve $HOME by hand)
+   #   * Mac dev default          = the Mac repo checkout root (e.g. under $HOME)
+   #
+   # Confirm the resolved path with: echo "$OPENCLAW_BASE_DIR" before editing crontab.
    ```
```

### 3.2 V017 fix（4 處對外消息 + 2 處 inline）

```diff
- - `learning.decision_features` exists (V019 deployed) — else FAIL.
+ - `learning.decision_features` exists (V017 deployed) — else FAIL.

-     Pre-conditions (fail-closed):
-         * ``learning.decision_features`` exists (V019 deployed) — else FAIL.
+     Pre-conditions (fail-closed):
+         * ``learning.decision_features`` exists (V017 deployed) — else FAIL.

-     # Existence pre-check — V019 hypertable required.
-     # 表存在檢查 — V019 hypertable 必須存在。
+     # Existence pre-check — V017 hypertable required.
+     # 表存在檢查 — V017 hypertable 必須存在。

-             "[43] learning.decision_features missing — V019 not applied",
+             "[43] learning.decision_features missing — V017 not applied",

- 覆蓋 PASS / WARN / FAIL by age / FAIL by no rows / FAIL by V019 missing。
+ 覆蓋 PASS / WARN / FAIL by age / FAIL by no rows / FAIL by V017 missing。

-     def test_fail_when_v019_missing(self) -> None:
-         """V019 not applied → FAIL fast / V019 未部署即 FAIL。"""
+     def test_fail_when_v017_missing(self) -> None:
+         """V017 not applied → FAIL fast / V017 未部署即 FAIL。"""

-         self.assertIn("V019 not applied", msg)
+         self.assertIn("V017 not applied", msg)
```

---

## 4. 治理對照

- **CLAUDE.md §七 ★★ 跨平台兼容性**：MED-1 fix 直接遵循「路徑不硬編碼 / 禁 user-home 絕對字面值」；新 cron block 用 `<ABSOLUTE_REPO_ROOT>` placeholder + `echo "$OPENCLAW_BASE_DIR"` 引導 operator 自行解析，不留 Linux 路徑 literal 也不留 Mac path literal（兩者都會命中 `/home/ncyu|/Users/[^/]+` grep）。
- **CLAUDE.md §七 雙語注釋**：所有改動的 docstring + inline 維持原中英對照樣式，未削減注釋。
- **CLAUDE.md §九 singleton**：未新增任何 singleton；未動 `_consumer` / `_LEADER_LOCK_FD` 任何登記行。
- **CLAUDE.md §二 16 條根原則**：純 docs/comment 修，零交易邏輯變動，無原則衝突。
- **§七「不允許在修復過程中順手優化」**：嚴格只動 PA/E2 列出的 4 處 + 連帶同源 3 處（同概念事實錯誤的 inline comment / test docstring，屬同一 finding 範圍而非「順手優化」）。

---

## 5. 不確定之處

- **「連帶 3 處 V019 殘留」是否屬範圍**：PA 明列 4 處 fix。我修完 4 處後跑 grep 還有 3 個 V019 殘留（2 條 inline comment 「V019 hypertable required」+ 1 條 test 模組 docstring 「FAIL by V019 missing」），都是同概念事實錯誤的延伸。我判斷屬同一 LOW-1 finding 範圍（對外文字事實一致性），未額外擴大；若 E2 認為應分票 → 我撤回這 3 條。
- **`/Users/<name>` placeholder example 也命中跨平台 grep**：原以為 `<name>` 是 placeholder 應該安全，實測 regex `/Users/[^/]+` 仍命中（`<name>` 滿足 `[^/]+`）。修正為純文字描述「Mac dev 取 Mac 端 $HOME 下的 repo checkout root」避免任何 `/Users/...` literal pattern。E2 若有更佳模板樣式請指出。
- **跨平台風險 §七.★★**：已驗 doc 0 hit；跨平台 OK。
- **測試覆蓋判斷**：test rename 是純改名（同邏輯 + 同 assertion fixture），test 數仍 19、全綠；無新邏輯需新 case。

---

## 6. Operator 下一步

### 已驗 (Mac CC 直驗，無 ssh)
- `grep "V019" <3 files>` exit 1 (0 hit) — V019 全清
- `grep -E '/home/ncyu|/Users/[^/]+' docs/healthchecks/2026-05-02--lg5_health_checks.md` exit 1 (0 hit) — 跨平台合規
- `python3 -m pytest helper_scripts/db/test_lg5_healthchecks.py -q` → 19 passed in 0.03s
- `git diff --check` exit 0 — 無 whitespace / 衝突殘留

### 等待 / 不做
- **不 commit / 不 push** — E2 round 2 審查通過後 PM 統一處理
- **不 deploy** — 純 docs/comment，無 runtime artifact
- 不需 ssh trade-core；本輪純 Mac dev 變動

### E2 round 2 審查重點
1. 連帶修的 3 處 V019 殘留是否接受納入本輪 (vs 拆 follow-up)
2. 新 cron block 模板的「指引性」是否足夠 operator 一看就知道怎麼解析（vs 需更具體 example）
3. 4 條 checklist 全綠

---

E1 FUP-2 Fix 1 ROUND 2 DONE: 等 E2 審查
report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-02--lg5_w3_fup_2_fix_1_round2.md`
