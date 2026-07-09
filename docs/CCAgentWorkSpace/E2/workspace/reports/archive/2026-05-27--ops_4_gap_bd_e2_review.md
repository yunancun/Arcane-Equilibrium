# E2 對抗審核 — OPS-4 GAP B+D round 1 + 2 IMPL chain

**Date**: 2026-05-27
**Commits**: `1392c9e1` (round 1) + `261d3956` (round 2)
**Reviewer**: E2 (Senior Backend + Adversarial)
**Verdict**: **APPROVE-WITH-CONDITION** （3 MED + 4 LOW；可 E4 regression 並行修，不阻 first-day live）

---

## 1. 範圍與背景

審核 OPS-4 GAP B (MIT post-restore validation) + GAP D (PG dump cron + healthcheck) 的 E1 production code（FA scope read-only context；MIT 9-query SQL / runbook / template 已 read-only context）。

審核 10 個改動，**E1 production code 6 個**（純 review）：
- `helper_scripts/cron/install_pg_dump_cron.sh` (96)
- `helper_scripts/cron/trading_ai_pg_dump_cron.sh` (181)
- `helper_scripts/cron/verify_pg_dump.sh` (129)
- `sql/migrations/V113__governance_audit_log_pg_dump_event_types.sql` (200)
- `helper_scripts/canary/healthchecks/check_pg_dump_freshness.py` (616 NEW)
- `helper_scripts/db/passive_wait_healthcheck/{__init__,checks_cron_heartbeat,runner}.py` (+127 LOC 合計)
- `helper_scripts/SCRIPT_INDEX.md` (+8)

PA spec / MIT runbook / MIT SQL = context only。

---

## 2. 8 條 reviewer checklist

| Item | 狀態 | 備註 |
|---|---|---|
| 改動範圍與 PA 方案一致 | ✅ | 7 check 對應 PA §10.B.2，2 event_type 對應 §10.B.1 amended |
| 沒有 except:pass 或靜默吞異常 | ⚠️ | wrapper `BLE001` exception 包到 WARN/FAIL；governance_audit_log INSERT 失敗用 `|| true` 但有 stderr+log 記錄 — acceptable 並故意設計 |
| 日誌使用 %s 格式 | ✅ | Python 用 `_common.configure_logging` + `logger.critical("PG connect via DB_URL failed: %s", exc)` |
| 新 API 端點 _require_operator_role() | N/A | 無新 API endpoint |
| except HTTPException: raise 在 except Exception 之前 | N/A | 無 HTTP |
| detail=str(e) 已改 | N/A | 無 HTTP |
| asyncio 路由中沒 blocking threading.Lock | N/A | 純 cron / healthcheck 非 async |
| 沒有私有屬性穿透 | ✅ | 無 `._xxx` |

---

## 3. OpenClaw 9 條 §3 checklist

| Item | 狀態 | 備註 |
|---|---|---|
| 跨平台 grep（禁 `/home/ncyu` / `/Users/[^/]+`） | ✅ | 7 file 全 0 命中（唯一 hit 是 `feedback_cross_platform` reminder 注釋） |
| 注釋規範（中文為主） | ✅ | 6 個新檔注釋中文為主，英文僅技術詞 |
| Rust unsafe / unwrap | N/A | 本次無 Rust |
| 跨語言 IPC schema | N/A | Python ↔ Bash via env/file，無 IPC |
| Migration Guard A/B/C（V023 教訓） | ✅ | V113 Guard A=V035 base table；Guard B=V098 baseline halt_session_set；idempotency 短路 + ACCESS EXCLUSIVE race-free DROP+ADD pattern；Guard C N/A 無 hot-path index |
| healthcheck 配對（被動等待） | ✅ | round 1 cron + round 2 healthcheck 配對；無新 passive-wait TODO |
| Singleton 登記 | N/A | 無新 singleton |
| 文件大小 800/2000 | ⚠️ | `runner.py` 1428 < 2000 hard cap，但 > 800 warning；本次 +24 LOC 不惡化大幅，pre-existing 性質 |
| Bybit API 改動 | N/A | 不觸 Bybit |

---

## 4. 對抗反問結果

### Q1: 「SQL injection in cron INSERT path?」

| 視角 | 結果 |
|---|---|
| `event_type` literal | hard-coded `'pg_dump_completed'`/`'pg_dump_failed'`，無 user input；SAFE |
| `payload_json` via `$payload$...$payload$` dollar-quote | bash `\$payload\$` 解析為 PG dollar-quote 分隔符；payload 內含 `BACKUP_ROOT`/`DATESTAMP`/數字 — 攻擊者要控制這些 env 才能注入；內部 trusted env；SAFE |
| pathological `OPENCLAW_BACKUP_ROOT` 含 `"`/`$payload$` literal | malformed JSON → `::jsonb` cast 失敗 → INSERT fail → silent loss via `|| true`；NOT injection but **silent audit row loss**；ack acceptable scope |
| `pg_restore --list <latest>` subprocess | `shell=False` + Path-derived；SAFE |

### Q2: 「Race between cron + healthcheck?」

| 場景 | 結果 |
|---|---|
| Cron 03:00 UTC 寫 7-10 min；healthcheck 03:05 跑 → pg_restore --list on incomplete dump | possible false-FAIL flap window（10min/day）；healthcheck 不檢查 lock dir；**LOW** |
| Runner.py 開 PG conn + 標 [80] 又開另一條 PG conn | check_80 在 runner.conn.close() 後跑（runner.py:1269 vs check_80 1412）；新 conn 不衝；SAFE |
| V113 ACCESS EXCLUSIVE LOCK during DROP+ADD | block 並行 INSERT writer < 1s（CHECK 不掃資料）；safe 但要在 low-traffic 部署 |

### Q3: 「Platform guard 真生效？」

**BUG發現**：standalone `run()` 不呼叫 `_platform_guard()`，只 `main()` 呼。Wrapper `checks_cron_heartbeat.py` 直接呼 `mod.run()` BYPASS guard。

- Mac dev 跑 `passive_wait_healthcheck.sh` → wrapper → `mod.run()` → check[6] subprocess 跑 pg_restore（Mac BSD pg_restore 可能行為差/缺）→ FAIL false-positive
- E1 report §7.4 「Mac dev 直接 import 不會跑 check[6]（因為 platform guard）」**事實錯誤**

→ MED-1（見 §5）。

### Q4: 「V113 不 apply 但 cron run，audit row 失蹤如何被偵測？」

| 條件 | check[7] verdict |
|---|---|
| V113 未 apply | CHECK 缺 'pg_dump_completed' → INSUFFICIENT_SAMPLE-skip with note |
| V113 apply 但 INSERT silent fail（heartbeat 顯示 cron fired）| 0 rows → 仍 INSUFFICIENT_SAMPLE（不 escalate to WARN）；**masking 真實漏洞** |

→ MED-2（見 §5）建議 cross-check heartbeat mtime 升 WARN 解 mask。

### Q5: 「跨平台 heartbeat sentinel 真使用嗎？」

Cron wrapper line 63 touch `$HEARTBEAT_DIR/trading_ai_pg_dump.last_fire`。
`check_pg_dump_freshness.py` line 122 resolve 但 **無任何 check 讀**。Dead resolution。

→ LOW-1（見 §5）。

### Q6: 「PA spec §10.B.1 vs V113+cron event_type 數量差異」

PA spec 已在 round 1 commit (1392c9e1) AMEND DOWN to 2 event_type（行 608 amendment 註 + 行 683-692 P3 backlog tracking）。E1 carry-over #2 已 RESOLVED — 不阻。

---

## 5. Findings

| 嚴重性 | 位置 | 描述 | 建議修法 |
|---|---|---|---|
| **MED-1** | `check_pg_dump_freshness.py:483` `run()` | 缺 `_platform_guard()` 呼叫；wrapper `checks_cron_heartbeat.py:268` `mod.run()` BYPASS Mac/non-Linux 防線；Mac dev 跑 passive_wait_healthcheck 會走 subprocess `pg_restore` + connect_pg → false-FAIL flap | **方法 A**：`run()` 開頭加 `_platform_guard()`；**方法 B**：wrapper 加 `if sys.platform != "linux": return ("INSUFFICIENT_SAMPLE", "[80] non-Linux skip")` |
| **MED-2** | `check_pg_dump_freshness.py:452` `check_7_audit_trail` `if n_rows == 0` | 「V113 已 apply 但 INSERT silent fail」場景被 `INSUFFICIENT_SAMPLE` mask；無法分辨「cron 從未 fire」vs「cron fire 但 audit 寫失敗」 | cross-check heartbeat mtime：若 heartbeat fresh（<26h）但 n_rows=0 → 升 **WARN** with note `"cron fired but audit row missing (V113/permission drift?)"` |
| **MED-3** | `install_pg_dump_cron.sh:71` ENTRY 組裝 | env-var 值未引號保護；若 `OPENCLAW_BACKUP_ROOT` 含 `%`（cron 特殊字元，等效 newline）/ 空格 → entry 解析錯亂 | 加 validation：`[[ "$OPENCLAW_BACKUP_ROOT" =~ %|\\ ]] && exit 6`；OR `printf %q` 引號保護每個 env value |
| **LOW-1** | `trading_ai_pg_dump_cron.sh:63` + `check_pg_dump_freshness.py:122` | `trading_ai_pg_dump.last_fire` heartbeat sentinel 被 touch 但無 check 讀；資源浪費 + 機會浪費 | 選項 A：移除 cron wrapper line 60-63 的 touch；OR 選項 B：加 check[8] heartbeat mtime（與 [75]-[79] 性質一致） |
| **LOW-2** | `check_pg_dump_freshness.py:368` `timeout=60` | 60s timeout FAIL 對 6-9 GB dump 的 TOC 讀稍嚴（slow disk / contention 可能超）；FAIL severity 對非致命延遲過重 | timeout 改 120s + 超時 verdict 改 WARN（不 FAIL）；timeout 為 transient infrastructure issue |
| **LOW-3** | `check_pg_dump_freshness.py:335` `check_6_l0_schema_coverage` | 與 cron lock 無同步；若 healthcheck 在 cron 03:00 寫 dump 期間跑（10min/day 窗口）→ pg_restore --list on incomplete file → FAIL flap | 加 lock dir 檢查：`if (data_dir / "locks" / "trading_ai_pg_dump_cron.lock.d").exists(): return WARN "dump in progress, skip"` |
| **LOW-4** | `_emit_results` (runner.py:434) 不認識 `INSUFFICIENT_SAMPLE` literal | INSUFFICIENT_SAMPLE 行在 `--quiet` 下仍 print（不視為 PASS-skip）；E1 report §4 line 100 描述「fail-soft 期間默默 PASS-skip」**事實錯誤** | 行為本身正確（透出 IS 給 operator 看），但 E1 report 描述需更正；不需改 code |

---

## 6. 2 個 carry-over reconcile verdict

### Carry-over #1: Interpretation diff（`.sh` vs `.py` package wire）

**E2 verdict**: ✅ **APPROVE E1's interpretation**。

理由：
- `passive_wait_healthcheck.sh` 97 LOC = venv loader / env 載入 / args 轉發，**無任何 `check_NN_*()` Bash 函數**
- 真實 check container 在 `passive_wait_healthcheck/` Python package（runner.py orchestrator + 30+ checks_*.py module）
- E1 wire 到 `checks_cron_heartbeat.py` + runner.py `[80]` slot，**架構上唯一正確選擇**
- Task 文字「在 .sh 加 function」措辭不精，E1 interpretation 是合理推導
- 「不破既有 6 check 行為」承諾 100% 保持（.sh / [1]-[79] 任何 check 路徑均未動）

無需 round 3 修正方向。

### Carry-over #2: PA spec §10.B.1 4 event_type vs V113+cron 2 event_type

**E2 verdict**: ✅ **PA spec amendment 已 land at commit 1392c9e1**（round 1 同 commit）。

證據：
- spec line 608 「AMENDMENT 2026-05-27 round 2 reconcile：原列 4 event_type，V113 + cron round 1 land 真相只 2 個... 其餘 2 個列為 P3 future-V### follow-up backlog」
- spec line 689-690 P3 backlog 條目 PG-DUMP-EVENT-EXTEND-1（retention_dropped）+ EXTEND-2（md5_drift）
- spec line 692 promotion trigger 條件明確

E1 IMPL 不阻；2 個未實作 event_type 移到 P3 quarterly cleanup。決策路徑 = (a) PA amend spec to 2（已執行）。

---

## 7. 9 安全不變量驗（CLAUDE.md §四 + TODO §5）

| Invariant | 驗證結果 |
|---|---|
| **I1** 單一 controlled write entry | ✅ cron 只 INSERT learning.governance_audit_log（非 trading/orders/intents），lock dir 防 overrun |
| **I2** read/write 分離 | ✅ healthcheck 純 SELECT；cron INSERT 限 governance_audit_log |
| **I3** AI output 非命令 | N/A 無 AI |
| **I4** 策略不繞 Guardian | N/A 無策略 mutate |
| **I5** 生存高於利潤 | N/A 純 ops |
| **I6** Uncertainty default conservative | ✅ INSUFFICIENT_SAMPLE-skip fail-soft；非 fail-open / fake PASS |
| **I7** 學習不直寫 live state | N/A 純 ops；cron 不 mutate live config / strategy params |
| **I8** 每筆交易可重建 | ✅ governance_audit_log payload 含 dump_file / md5 / size / duration / db / host — 可重建 |
| **I9** local stop + exchange-side 並重 | N/A 無交易路徑 |
| **5-gate**（live_reserved + Operator + OPENCLAW_ALLOW_MAINNET + secret + auth.json） | ✅ V113 純擴 enum；cron 寫 audit log 不觸交易 gate；不繞任何 hard boundary |
| **LiveDemo 不降級** | ✅ 不觸 LiveDemo 路徑 |
| **Fake audit evidence** (I8 sub) | ✅ cron 失敗 → INSERT pg_dump_failed event；INSERT 本身失敗 → stderr+log WARN（不 fake PASS） |
| **secret leakage** | ✅ PGPASSWORD export 後僅 pg_dump/psql 用；LOG/JSONL 從不寫 PG_PASS；governance_audit_log payload 不含密 |

---

## 8. 16 root principles 違規查

| Principle | 結果 |
|---|---|
| #1 single write entry | ✅ |
| #2 read/write separation | ✅ |
| #3 Decision Lease | N/A 無 trading effect |
| #4 Guardian bypass | N/A |
| #5 survival | N/A |
| #6 uncertainty conservative | ✅ INSUFFICIENT_SAMPLE-skip |
| #7 learning 不重寫 live | N/A |
| **#8 reconstructable** | ✅ governance_audit_log payload 含 size/md5/dur/db/host — 滿足 reconstructable invariant；MIT GAP-B 9-query SQL 補強 invariant 1/2/7/8 post-restore |
| #9 local + exchange stop | N/A |
| **#10 fact/inference/assumption** | ⚠️ E1 report §7.4「Mac dev 不會跑 check[6]」**inference 錯誤**（已 §5 MED-1 標記）；其餘 §6 / §5 / §7 區分清楚 |
| #11-#16 | N/A 無 strategy/AI/portfolio decision |

---

## 9. Test coverage 評估（給 E4 regression scope）

E1 已跑 Mac py_compile + bash -n PASS + Linux empirical `--status` 跑通 EXIT=0。

### 建議 E4 regression 必跑：

1. **必跑 [80] 不破既有 [1]-[79]**
   ```
   ssh trade-core "bash $OPENCLAW_BASE_DIR/helper_scripts/db/passive_wait_healthcheck.sh --quiet"
   ```
   驗 `[80]` 行出現 + 其餘 79 check verdict 不變

2. **跨平台 Mac fail-fast**（E2 MED-1 直接驗）
   ```bash
   python3 srv/helper_scripts/canary/healthchecks/check_pg_dump_freshness.py --status
   ```
   Mac 跑：當前 `_platform_guard` only in main()，預期 exit 2；MED-1 修後驗 wrapper 路徑也 fail-fast

3. **V113 idempotency**
   ```bash
   ssh trade-core "psql ... -f srv/sql/migrations/V113__*.sql"
   ssh trade-core "psql ... -f srv/sql/migrations/V113__*.sql"  # 2nd run
   ```
   2nd run 應看 RAISE NOTICE skip，無 CHECK 重複

4. **cron dry-run**（不實 install）
   ```bash
   ssh trade-core "bash srv/helper_scripts/cron/install_pg_dump_cron.sh"  # DRY-RUN default
   ```
   驗 ENTRY 印出 + 退出 0

5. **wrapper 直跑 mod.run()**（模擬 [80] path）
   ```bash
   ssh trade-core "cd $BASE; .venv/bin/python3 -c 'from helper_scripts.db.passive_wait_healthcheck.checks_cron_heartbeat import check_80_pg_dump_freshness; print(check_80_pg_dump_freshness())'"
   ```

### Negative test 缺：

- E4 加 mock test：env `OPENCLAW_BACKUP_ROOT=/nonexistent/path` → check[1] FAIL；env `OPENCLAW_BACKUP_ROOT=$HOME` （非 trading_ai_*.dump）→ check[2] INSUFFICIENT_SAMPLE
- V113 不 apply + cron run → cron WARN 進 log，dump 主流程不阻

---

## 10. 結論

**Verdict**: **APPROVE-WITH-CONDITION**

**Conditions**（不阻 first-day live，可 E4 並行修）：

1. E1 round 3 修 **MED-1**（standalone `run()` 加 `_platform_guard()` OR wrapper 加 `sys.platform` guard）
2. E1 round 3 修 **MED-2**（cross-check heartbeat 解 silent V113-INSERT-fail mask）
3. E1 round 3 修 **MED-3**（install_pg_dump_cron.sh ENTRY env-var 引號保護 + `%` validation）
4. LOW-1/2/3/4 列入 P3 backlog（quarterly cleanup pick up），不阻 round 3

**Count**: 0 BLOCKER / 0 HIGH / 3 MED / 4 LOW

### E1 round 3 必修 items（≤15min 預估）：

| # | 檔 | 修法 |
|---|---|---|
| 1 | `check_pg_dump_freshness.py:483` | `def run(...)` 開頭加 `_platform_guard()` 呼叫 |
| 2 | `check_pg_dump_freshness.py:452-456` `check_7_audit_trail` | 加 heartbeat mtime cross-check：`heartbeat_age = paths["heartbeat"].stat().st_mtime ...`，若 heartbeat<26h 且 n_rows=0 → 升 WARN |
| 3 | `install_pg_dump_cron.sh:71` | `printf %q` 引號或 validation regex 防 `%`/space |
| 4 | E1 report §4 line 100 / §7.4 line 207 | 更正描述：`run()` 缺 platform guard fact；INSUFFICIENT_SAMPLE 在 `--quiet` 下實際會 print（不 PASS-skip） |

### Post-fix re-review minimal（E2 ≤5min）：

- 只重 review `check_pg_dump_freshness.py` 上述 2 處 + `install_pg_dump_cron.sh` 1 處
- 跑 `python3 -m py_compile` + `bash -n` + Linux re-empirical `--status` 確認 exit=0 仍對

### E4 regression scope（per §9）

最低必跑 1+3+4（runner not-break + V113 idempotency + cron dry-run）；建議加 2+5（platform guard + wrapper direct）。

---

## 11. 多 session race check (5a-5e per SOP)

| Item | 結果 |
|---|---|
| 5a `git fetch --prune origin` + 2h window 看 sibling push | origin/main HEAD = 261d3956（本次審 commit），無 sibling push 衝突；E2 audit 範圍清晰 |
| 5b `git status --porcelain` 確認 unstaged 全本任務 scope | 5 untracked report（A3/CC/E2/E4 sibling 平行工作）+ 3 modified（E4 memory / PA spec 小幅 +17/-2 / tab-governance.html）— **全非本次 OPS-4 GAP-B+D code scope**，per memory `multi_session_memory_race` 不 revert |
| 5c unknown WIP 禁 revert | ✅ 不 touch 任何 untracked / modified；只新增本 E2 report |
| 5d sign-off report commit 前 path clean | 本 report `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-27--ops_4_gap_bd_e2_review.md` 將新增；commit by PM |
| 5e PR review 期間 sibling push origin | 無新 sibling push 進 origin/main during this review |

✅ 5/5 通過。
