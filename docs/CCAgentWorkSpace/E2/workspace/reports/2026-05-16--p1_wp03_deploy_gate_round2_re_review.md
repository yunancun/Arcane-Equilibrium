# E2 Round 2 Re-review — P1-WP03-DEPLOY-GATE · 2026-05-16

## 範圍
Focused 重審 E1 round 2 fix（per Round 1 RETURN：MEDIUM-1 + LOW-1 + 1 missing test）。
- `helper_scripts/db/passive_wait_healthcheck/checks_wp03_deploy_gate.py` +9/-3
- `helper_scripts/db/test_wp03_deploy_gate_healthcheck.py` +67
- Total +76/-3

## 1. MEDIUM-1 fix verdict — **PASS**
- `checks_wp03_deploy_gate.py:517` 真改為 `if age_h >= T2_WINDOW_HOURS_DEFAULT and t1["n"] == 0 and t2["n"] == 0:`（雙窗 secondary guard）
- Trigger msg L520 同步更新為 `f"12h n=0 + {t2_window_hours}h n=0 grid_trading..."` — 揭露雙窗 evidence
- False-positive 場景（env override 48h + age 30h + T1 50 fills + T2 n=0）：修後不觸 ZERO_FILLS（adversarial revert 證實 reverted 走 round-1 條件即 FAIL，round-2 條件 PASS）
- Real dormancy（T1=0 + T2=0）：仍觸 trigger（既有 `test_fail_zero_fills_dormancy` 仍 PASS）
- 注釋強化 4 行說明選方案 B 理由（雙窗 confirm > 改 t2_window_hours），sound

## 2. LOW-1 fix verdict — **PASS**
- `checks_wp03_deploy_gate.py:578-583` REQUIRED escalation FAIL msg 真含 `revert_recommended=false (approach_escalation, no flag written)` hint
- 與 Step 4 hard FAIL msg `revert_recommended=true` 對稱 — operator 一眼可區分 hard FAIL（有 flag）vs approach FAIL（無 flag）
- 注釋 L575-577 明寫 fix 原由
- 不破壞既有 `test_required_env_escalates_warn_to_fail`（assert `"REQUIRED escalation" in msg` substring，相容新 hint）

## 3. New test verdict — **PASS（real coverage, not trivial）**
- `test_zero_fills_env_override_age_mismatch` L367-423 setup 對齊 `test_fail_zero_fills_dormancy` pattern
- Mock fetchone 5-tuple：(exists, baseline 500, T1 50/+5, T2 0/None, T3 0/None) — 對齊真 PG return shape
- `OPENCLAW_WP03_DEPLOY_GATE_LOOKBACK_HOURS=48` + `_FakeDT.now = deploy_ts + 30h`
- Assertion 完整：`status=="PASS"` + `"ZERO_FILLS" not in msg` + flag 不存在 + msg 含 "12h n=50" + "48h n=0"
- **Adversarial reverse sanity verified**：local 改 source 回 round-1 邏輯 `if ... and t2["n"]==0:`，pytest 跑此單 test → **FAIL with `'FAIL' != 'PASS'`** + msg 含 ZERO_FILLS trigger（restore 後恢復）→ 證實 new test 真實打中 MEDIUM-1 修法，非 trivial PASS

## 4. 17 existing regression — **PASS（no break）**
- 18/18 wp03 test PASS（CC local pytest 確認）
- Sample 3 既有 sensitive test 重跑全 PASS：
  - `test_fail_zero_fills_dormancy`（T1=0+T2=0 真實 dormancy 仍 trigger）
  - `test_required_env_escalates_warn_to_fail`（新 msg substring 相容）
  - `test_t2_window_env_override`（env override 既有功能不破）
- E1 自報 386/0 sibling regression — local 跑 18 條 subset 確認 0 fail

## 5. LOW-2 / LOW-3 P2 ticket — **PASS**
Sign-off §6 明列：
- `P2-WP03-MSG-STRUCT`（LOW-2 結構化 prefix）— description 清楚（GUI/alert regex parse 強化）
- `P2-WP03-ALERT-FLAG-INDEPENDENCE`（LOW-3 flag write fail-soft 與 verdict 雙訊息分離）— description 清楚
- 兩 ticket scope 對齊 round 1 E2 LOW-2/3 finding，無漏

## 6. Scope creep check — **PASS**
- 真實 LOC：checks 594（claim 593，+1 是注釋多 1 行）/ test 592（claim 595，-3 是注釋少 3 行）— micro deviation 在容差內
- `git status` 僅 `checks_wp03_deploy_gate.py` + `test_wp03_deploy_gate_healthcheck.py` 兩檔 unstaged，**無連帶動其他 wp03 / passive_wait_healthcheck / risk_config / grid_helpers.rs / live auth / lease 業務檔**
- 0 unrelated change

## 7. Lexical scope shadow check — **PASS**
- AST 分析 `check_69_wp03_ou_sigma_deploy_gate`：0 nested function / 0 lambda / 0 closure
- 14 個 local name 全 statement-level（age_h, base_msg, exists, flag_diag, required, sorted_triggers, t1/t2/t3, t2_window_hours, t3_floor, t3_warn_floor, trigger_summary, verdict）— 全 explicit unique
- Round 2 patch 全 statement-level 邏輯修改 + 注釋，無 var rebinding / 無 closure capture / 無 shadow risk
- W-AUDIT-7c 教訓檢測：N/A（純 Python，無 inline-JS / no `node --check` needed）

## 8. Round 2 Final Verdict — **APPROVE**

E1 round 2 修法 sound：MEDIUM-1 false-positive guard 真實打中 + LOW-1 msg hint 正確對稱 + new test adversarial 反向驗證 not trivial + 0 regression + 0 scope creep + 0 lexical shadow + 2 P2 ticket 留 follow-up 清楚。

**Pass to E4** for Linux trade-core regression（per E1 §7.2）：
- 386/0 sibling regression on real PG
- `[69]` cron fire on real engine_pid mtime / V083 baseline window
- flag write 跨 cron run 驗證

## 9. 必修 push back — **無**

Round 1 RETURN 三項（MEDIUM-1 + LOW-1 + missing test）全部修妥；LOW-2 LOW-3 per PA 指示 P2 defer 合理 + ticket 列入。

---

## 附：Adversarial 驗證 log

```
# revert MEDIUM-1 fix → run new test alone
ASSERTION: 'FAIL' != 'PASS'
msg: "[69] WP-03 deploy-gate FAIL revert_recommended=true —
       triggers: ZERO_FILLS(12h n=0 + 48h n=0 grid_trading —
       possible strategy dormancy from WP-03) — flag written ..."
→ confirms reverted 邏輯（單 t2["n"]==0 條件）會 trigger 已知 false-positive 場景
→ new test 真實打中 fix semantic（restore source 後 18/18 PASS）
```
