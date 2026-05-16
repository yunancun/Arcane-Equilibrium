# E1 · P1-WP03-DEPLOY-GATE Round 2 Fix Self-Report

**Date**：2026-05-16
**Agent**：E1
**Ticket**：`P1-WP03-DEPLOY-GATE-IMPL` Round 2
**Round 1 E2 review**：`docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-16--p1_wp03_deploy_gate_e2_review.md`
**Status**：🟡 **ROUND 2 IMPL DONE — 待 E2 重審 → E4 回歸 → PM 統一 commit**
**Branch**：`main`（工作樹乾淨；等 PM 派 E2 review）

---

## §1 任務摘要

PA Round 2 派發針對 E2 review 識別的 **1 MEDIUM + 3 LOW + 1 missing test** 中
強制必修部分（per E2 Verdict RETURN）：

| 嚴重 | 處置 |
|---|---|
| **MEDIUM-1**（BLOCKING）：ZERO_FILLS false-positive | ✅ 修（採用方案 B：T1+T2 secondary guard）|
| **LOW-1**（BLOCKING per E2）：REQUIRED escalation FAIL msg 無 revert hint | ✅ 修（msg 加 `revert_recommended=false (approach_escalation, no flag written)` hint）|
| **Missing test**（BLOCKING per E2）：`test_zero_fills_env_override_age_mismatch` | ✅ 補（per E2 推薦場景）|
| **LOW-2**（P2 defer）：FAIL msg `[FLAG_SET]` 結構化 prefix | ⏸ 留 P2 ticket（per PA 指示）|
| **LOW-3**（P2 defer）：flag write fail-soft + verdict FAIL 雙訊息混淆 | ⏸ 留 P2 ticket（per PA 指示）|

---

## §2 Code diff summary

| 檔案 | 變更類型 | LOC delta | post-IMPL 大小 |
|---|---|---:|---:|
| `helper_scripts/db/passive_wait_healthcheck/checks_wp03_deploy_gate.py` | Patch MEDIUM-1 + LOW-1 | **+9 / -3** | 593 / 2000 |
| `helper_scripts/db/test_wp03_deploy_gate_healthcheck.py` | +1 new test | **+67** | 595 / 2000 |
| **合計** | | **+76 / -3** | — |

**未動到的檔案（confirmed read-only verify）**：
- `helper_scripts/db/passive_wait_healthcheck/__init__.py`（per PA spec restrictions）
- `helper_scripts/db/passive_wait_healthcheck/runner.py`（已 wire，無需動）
- PA spec 本身：未動
- 任何 WP-03 / grid_helpers.rs 業務代碼：未動
- 任何 live / authorization / lease 邏輯：未動

---

## §3 修法詳述

### 3.1 MEDIUM-1：ZERO_FILLS false-positive secondary guard（方案 B）

**E2 confirmed 重現場景**：
- `OPENCLAW_WP03_DEPLOY_GATE_LOOKBACK_HOURS=48`
- engine age = 30h（< 48）
- T1 12h 有 50 fills（策略 active）
- T2 48h n=0（query window > engine age 純粹 mechanic）
- 舊邏輯 `age_h >= 24 and t2["n"] == 0` → 誤判 dormancy → 寫 revert flag

**根因**：`t2["n"] == 0` 不分辨「真實 dormancy」vs「env override 使 t2 window > engine age 的 mechanical zero」。

**修法（方案 B per PA 指定）**：加 `t1["n"] == 0` secondary guard。T1 12h 是 hardcoded floor（永遠 ≤ T2 window），如果 T1 也 0 fills 才是真實 dormancy。

**修改位置**：`checks_wp03_deploy_gate.py` L512-521

```python
# ZERO_FILLS：age_h >= 24h 且 T1 12h + T2 (24h 或 env override) 都 n == 0（spec §4.2）
# 嚴重副作用 — grid 全 dormancy 可能是 WP-03 root cause（sigma 過收）
# 雙窗 secondary guard（E2 Round 1 MEDIUM-1 fix）：避免當 LOOKBACK_HOURS env override
# 使 t2 window > engine age 時 t2["n"]=0 純粹是 query window 超過 engine age 而非
# 真 dormancy 的 false-positive；T1 12h（hardcoded floor）+ T2 都 0 fills 才算真 dormancy
if age_h >= T2_WINDOW_HOURS_DEFAULT and t1["n"] == 0 and t2["n"] == 0:
    triggers.append((
        "ZERO_FILLS",
        f"12h n=0 + {t2_window_hours}h n=0 grid_trading — possible strategy dormancy from WP-03",
    ))
```

**Trigger msg 同步更新**：從 `{t2_window_hours}h n=0` 改為 `12h n=0 + {t2_window_hours}h n=0` — 揭露雙窗 evidence，operator 看 flag 即知 secondary guard 都滿足才寫。

**為什麼選方案 B 而非 A**：
- (A) `age_h >= t2_window_hours`：仍以 t2 為單一 evidence；只解決 env override 場景但不解決「t2 = 24h default + age = 30h + t1 有 fills」case（雖該 case 罕見但語義仍不嚴謹）
- (B) `t1["n"] == 0 and t2["n"] == 0`：雙窗 confirm；無論 env override 與否語義都嚴謹，且 t1 永遠是 hardcoded 12h（不會跟 t2 window 一起變），是更穩健的 guard

PA 推薦 (B) 同 E2 Q4 conservative design 對齊。

### 3.2 LOW-1：REQUIRED escalation FAIL msg revert_recommended=false hint

**問題**：Step 4 hard FAIL msg 含 `revert_recommended=true`，Step 5 REQUIRED escalation FAIL msg 缺對稱 hint，operator 看到 FAIL 但 `wp03_revert_flag` 不存在會困惑。

**修法**：FAIL msg 加 `revert_recommended=false (approach_escalation, no flag written)` 明確 hint。

**修改位置**：`checks_wp03_deploy_gate.py` L572-578

```python
if verdict == "FAIL":
    # REQUIRED env 升 FAIL：仍視為觸發 revert（保守 strict mode）
    # 但本路徑 warnings approach 而非 hard trigger，不寫 revert flag
    # （flag 是 hard trigger 的 advisory，approach 升 FAIL 純 escalation）
    # E2 Round 1 LOW-1 fix：msg 明寫 revert_recommended=false hint，讓 operator
    # / GUI 看到 FAIL 但 wp03_revert_flag 不存在時不會困惑（與 Step 4 hard FAIL
    # 的 revert_recommended=true 對稱）
    return (
        "FAIL",
        f"[69] WP-03 deploy-gate FAIL (REQUIRED escalation) "
        f"revert_recommended=false (approach_escalation, no flag written) — "
        f"approaching triggers: {'; '.join(warnings)} — {base_msg}",
    )
```

### 3.3 Missing test：`test_zero_fills_env_override_age_mismatch`

**Per E2 推薦場景**：
- `LOOKBACK_HOURS=48` 設置
- engine age = 30h
- T1 12h has 50 fills（avg=+5，active）
- T2 48h n=0（mechanic zero）
- T3 7d n=0（同因，但 T3 min_sample=200 不 trigger）
- **Expected**：PASS（修法 (B) 後 secondary guard 不滿足 → 不觸 ZERO_FILLS）

**修改位置**：`test_wp03_deploy_gate_healthcheck.py` 插在 `test_fail_zero_fills_dormancy` 之後（並排對比）

**Mock pattern 對齊既有**：
- `_FakeDT` datetime patch（與 `test_fail_zero_fills_dormancy` 同 pattern）
- `_baseline_query_result(50, 5.0, 10.0)` 3-tuple PG return shape
- `_baseline_query_result(0, None, None)` 模擬 PG `AVG(NULL)=NULL`（IMPL `float(avg or 0.0)` 處理）
- `OPENCLAW_WP03_DEPLOY_GATE_LOOKBACK_HOURS=48` env override（與 `test_t2_window_env_override` 同 pattern）

**Assertion**：
- `status == "PASS"`
- `"ZERO_FILLS" not in msg`
- revert flag 不存在
- evidence msg 含 `"12h n=50"` + `"48h n=0"`（驗證雙窗 fills 都顯示）

**反向 sanity check**（為什麼這 test 真實打修法）：如果回退到 round 1 邏輯 `age_h >= 24 and t2["n"] == 0`，age=30 >= 24 + t2["n"]=0 → ZERO_FILLS trigger → FAIL → 寫 flag → test fail。所以 test 非 trivial PASS。

---

## §4 Verification

### 4.1 syntax check

```bash
$ python3 -m py_compile checks_wp03_deploy_gate.py test_wp03_deploy_gate_healthcheck.py
PY_COMPILE OK
```

### 4.2 wp03 test suite（18/18 PASS）

```
test_baseline_cache_reuse                         PASSED  [既有]
test_baseline_insufficient_sample_warn            PASSED  [既有]
test_fail_t1_critical                             PASSED  [既有]
test_fail_t2_high                                 PASSED  [既有]
test_fail_t3_cumulative_drift                     PASSED  [既有]
test_fail_zero_fills_dormancy                     PASSED  [既有；T1+T2 都 0 仍滿足 guard]
test_low_sample_skip_trigger                      PASSED  [既有]
test_pass_all_windows_within_tolerance            PASSED  [既有]
test_pre_deploy_no_engine_pid                     PASSED  [既有]
test_pre_evaluable_recent_deploy                  PASSED  [既有]
test_required_env_escalates_warn_to_fail          PASSED  [既有；msg 新含 revert_recommended=false]
test_stale_engine_pid_before_deploy               PASSED  [既有]
test_t2_window_env_override                       PASSED  [既有]
test_table_absent_warn                            PASSED  [既有]
test_warn_t1_approach                             PASSED  [既有]
test_warn_t2_approach                             PASSED  [既有]
test_warn_t3_approach                             PASSED  [既有]
test_zero_fills_env_override_age_mismatch         PASSED  [新增]
================== 18 passed in 0.04s ==================
```

### 4.3 sibling regression（386 PASS，0 fail）

```bash
$ pytest helper_scripts/db/ -q
386 passed in 0.36s
```

對比 Round 1 baseline 385 → Round 2 386（+1 新 test，0 regression）。

### 4.4 Mock review verdict（self-check）

| 檢查 | 結果 |
|---|---|
| Mock fetchone shape 對齊真 PG `_query_grid_window` return | ✅ `(n, avg, std)` 3-tuple |
| Mock `(0, None, None)` 對齊 PG `AVG(NULL)=NULL` 行為 | ✅ IMPL `float(avg or 0.0)` None-safe |
| `_FakeDT` pattern 與既有 `test_fail_zero_fills_dormancy` 對齊 | ✅ 同 `_patch` + `_FakeDT` 子類 |
| 新 test 反向 sanity（撤修法時 test fail）| ✅ 如撤 `t1["n"]==0` guard → ZERO_FILLS trigger → assertion fail |
| 新 test 不 hide MEDIUM-1 semantic | ✅ 真實打到雙窗 secondary guard 路徑 |
| Test `setUp` clean env + tmp data_dir | ✅ 用既有 fixture pattern |

### 4.5 LOW-1 修法不破其他 assertion 反向 check

既有 `test_required_env_escalates_warn_to_fail`（L428-450）：
- assert `status == "FAIL"`：✅ 仍 FAIL
- assert `"REQUIRED escalation" in msg`：✅ msg 仍含
- assert `not flag_path.exists()`：✅ 仍 false（不寫 flag 邏輯未動）

新 msg `... FAIL (REQUIRED escalation) revert_recommended=false (approach_escalation, no flag written) — approaching triggers: ...` 對既有 substring 不破壞，新增 hint 純 additive。

---

## §5 跨平台 / 治理 / 硬邊界對照

| 維度 | 評估 |
|---|---|
| 跨平台 grep `/home/ncyu`/`/Users/[^/]+/` | ✅ 0 命中（新增 code 全 std lib） |
| 文件 LOC（800 / 2000 limit）| ✅ checks 593 / test 595，皆 < 800 |
| 注釋默認中文（per 2026-05-05）| ✅ 修改部分新增注釋全中文 |
| SQL injection | N/A（本 patch 0 動 SQL） |
| 硬邊界（live/auth/lease/max_retries）| ✅ 0 觸碰 |
| ADR-0020 manual-only revert | ✅ 保持；flag write 邏輯未動 |
| 16 根原則 | ✅ 與 Round 1 同對照 |

---

## §6 P2 ticket 留待 follow-up

per PA Round 2 指示，以下 LOW-2 / LOW-3 不在本次 round 2 scope，留 P2 ticket：

### P2-WP03-MSG-STRUCT
**對應 E2 LOW-2**：FAIL msg 加 `[FLAG_SET]` 結構化 prefix，方便 alert / GUI regex parse。
**Scope**：`_write_revert_flag` 成功路徑回 msg 加 prefix；非 functional fix，純 structured logging 強化。
**優先級**：P2（GUI / alert downstream 不依賴 flag exists 才需要）

### P2-WP03-ALERT-FLAG-INDEPENDENCE
**對應 E2 LOW-3**：flag write fail-soft（`flag write failed: ...`）+ verdict FAIL 雙訊息混淆 — alert / GUI 應改用 msg substring grep 而非 flag file exists 判斷。
**Scope**：補 alert downstream logic doc / GUI banner spec / operator runbook 對應「flag write failed 但 FAIL」場景的決策樹。
**優先級**：P2（與 hardening 配對；非 Round 2 必修）

PA / PM 後續開 ticket 時 reference 此 sign-off §6。

---

## §7 不確定之處 + Operator/E2/E4 需重點驗

### 7.1 已完成
- MEDIUM-1 修：`checks_wp03_deploy_gate.py` L512-521 加 `t1["n"] == 0` secondary guard + trigger msg 同步含雙窗 evidence
- LOW-1 修：L572-578 REQUIRED escalation FAIL msg 加 `revert_recommended=false (approach_escalation, no flag written)` hint
- 補 test `test_zero_fills_env_override_age_mismatch`（67 LOC）
- 18/18 wp03 test PASS + 386/0 sibling regression 全 PASS
- 注釋默認中文（per 2026-05-05 governance）
- 0 硬編碼 user path
- 0 SQL 動到（純 trigger logic + msg patch）

### 7.2 待 reviewer 把關

| Reviewer | 範圍 | 預期判定點 |
|---|---|---|
| **E2 Round 2** | 重審 — secondary guard 邏輯是否覆蓋所有 env override + age + fills 排列組合？LOW-1 msg 是否對齊「revert_recommended」既有 GUI/alert 解析慣例？新 test 是否 cover 真實 PG None semantic？P2 ticket 是否清楚？| APPROVE 或 RETURN 細節 |
| **E4** | Linux trade-core 跑 386 test + cron 真實 fire | 真 PG schema 與 mock 對齊；engine_pid mtime 在 v35 rebuild 後正確；flag write 跨 cron run 行為 |
| **PM** | 統一 commit + push | 等 E2 Round 2 APPROVE → E4 PASS → PM commit |

### 7.3 仍未驗證的場景

1. **真實 PG `learning.mlde_edge_training_rows` empty COUNT/AVG 行為**：本 Round 2 假設 mock `(0, None, None)` 與真 PG `SELECT COUNT(*)::int, AVG(NULL)::float8, STDDEV(NULL)::float8 FROM ... WHERE no_row_match` 對齊（PG `AVG([no row])` 返 NULL）— E4 應 Linux PG 真實 query 驗證
2. **`OPENCLAW_WP03_DEPLOY_GATE_LOOKBACK_HOURS` 真實 cron 環境注入**：本 round 不動 cron / install，env override 由 operator manual export；若未設則 fallback default 24h（既有邏輯）
3. **LOW-1 msg hint 與 GUI / alert grep 對齊**：假設 GUI / alert 對 Step 4 grep `revert_recommended=true` + 對 Step 5 grep `revert_recommended=false` 區分；若 GUI 用更 strict regex 或 JSON-flavored prefix 則 LOW-2（P2）更重要

### 7.4 Operator 下一步

1. 派 **E2 Round 2** 重審（focus §7.2 + §7.3 議題；驗 MEDIUM-1 + LOW-1 修法是否符合 E2 Round 1 verdict 期望）
2. E2 GREEN → 派 **E4** Linux runtime regression（真 PG schema + cron fire + flag JSON 結構）
3. E4 GREEN → **PM 統一 commit** + push
4. 開 P2 ticket：`P2-WP03-MSG-STRUCT` + `P2-WP03-ALERT-FLAG-INDEPENDENCE`

---

## 附錄 A：關鍵 diff 摘錄

### A.1 `checks_wp03_deploy_gate.py` MEDIUM-1 修法（L512-521）

```diff
-    # ZERO_FILLS：age_h >= 24h 且 24h n == 0（spec §4.2）
+    # ZERO_FILLS：age_h >= 24h 且 T1 12h + T2 (24h 或 env override) 都 n == 0（spec §4.2）
     # 嚴重副作用 — grid 全 dormancy 可能是 WP-03 root cause（sigma 過收）
-    if age_h >= T2_WINDOW_HOURS_DEFAULT and t2["n"] == 0:
+    # 雙窗 secondary guard（E2 Round 1 MEDIUM-1 fix）：避免當 LOOKBACK_HOURS env override
+    # 使 t2 window > engine age 時 t2["n"]=0 純粹是 query window 超過 engine age 而非
+    # 真 dormancy 的 false-positive；T1 12h（hardcoded floor）+ T2 都 0 fills 才算真 dormancy
+    if age_h >= T2_WINDOW_HOURS_DEFAULT and t1["n"] == 0 and t2["n"] == 0:
         triggers.append((
             "ZERO_FILLS",
-            f"{t2_window_hours}h grid_trading n=0 — possible strategy dormancy from WP-03",
+            f"12h n=0 + {t2_window_hours}h n=0 grid_trading — possible strategy dormancy from WP-03",
         ))
```

### A.2 `checks_wp03_deploy_gate.py` LOW-1 修法（L572-578）

```diff
         if verdict == "FAIL":
             # REQUIRED env 升 FAIL：仍視為觸發 revert（保守 strict mode）
             # 但本路徑 warnings approach 而非 hard trigger，不寫 revert flag
             # （flag 是 hard trigger 的 advisory，approach 升 FAIL 純 escalation）
+            # E2 Round 1 LOW-1 fix：msg 明寫 revert_recommended=false hint，讓 operator
+            # / GUI 看到 FAIL 但 wp03_revert_flag 不存在時不會困惑（與 Step 4 hard FAIL
+            # 的 revert_recommended=true 對稱）
             return (
                 "FAIL",
-                f"[69] WP-03 deploy-gate FAIL (REQUIRED escalation) — "
+                f"[69] WP-03 deploy-gate FAIL (REQUIRED escalation) "
+                f"revert_recommended=false (approach_escalation, no flag written) — "
                 f"approaching triggers: {'; '.join(warnings)} — {base_msg}",
             )
```

### A.3 `test_wp03_deploy_gate_healthcheck.py` 新 test（插在 `test_fail_zero_fills_dormancy` 後）

```python
def test_zero_fills_env_override_age_mismatch(self) -> None:
    """ZERO_FILLS false-positive guard（E2 Round 1 MEDIUM-1）：t2 window > engine age
    且 t2 n=0 但 t1 仍有 fills（策略 active），不應觸 ZERO_FILLS。

    場景：LOOKBACK_HOURS=48 + engine age=30h + T1 12h 50 fills + T2 48h n=0
    → 修法 (B) 後 t1["n"]==0 secondary guard 不滿足 → 不觸 ZERO_FILLS
    → 走 PASS path（T1/T2/T3 全 fine，無 approach warn 也無 hard trigger）。
    """
    from unittest.mock import patch as _patch
    import datetime as _dt

    os.environ["OPENCLAW_WP03_DEPLOY_GATE_LOOKBACK_HOURS"] = "48"
    _write_engine_pid(Path(self._tmp_data.name), mtime_iso=WP03_DEPLOY_TIMESTAMP_UTC)

    # Patch datetime.now 回 deploy_ts + 30h，age=30h < t2_window=48h
    deploy_ts = _dt.datetime.fromisoformat(WP03_DEPLOY_TIMESTAMP_UTC.replace("Z", "+00:00"))
    fake_now = deploy_ts + _dt.timedelta(hours=30)

    class _FakeDT(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fake_now.replace(tzinfo=None)
            return fake_now.astimezone(tz)

    cur = _mock_cursor([
        _table_exists_row(),
        _baseline_query_result(500, 8.0, 12.0),
        _baseline_query_result(50, 5.0, 10.0),  # T1 12h active
        _baseline_query_result(0, None, None),  # T2 48h mechanic zero
        _baseline_query_result(0, None, None),  # T3 7d mechanic zero
    ])

    with _patch(
        "helper_scripts.db.passive_wait_healthcheck.checks_wp03_deploy_gate.datetime",
        _FakeDT,
    ):
        status, msg = check_69_wp03_ou_sigma_deploy_gate(cur)

    self.assertEqual(status, "PASS", msg)
    self.assertNotIn("ZERO_FILLS", msg)
    flag_path = Path(self._tmp_data.name) / "wp03_revert_flag"
    self.assertFalse(flag_path.exists(), "ZERO_FILLS false-positive guard must not write revert flag")
    self.assertIn("12h n=50", msg)
    self.assertIn("48h n=0", msg)
```

---

**E1 ROUND 2 IMPLEMENTATION DONE：待 E2 重審（report path：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-16--wp03_deploy_gate_round2_fix.md`）**
