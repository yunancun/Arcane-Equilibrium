# E1 — P0-OPS-4 GAP-D Track A round 3 — 3 MED fix (E2 round 2 returns)

**日期**: 2026-05-27
**任務**: 修 E2 round 2 review (`2026-05-27--ops_4_gap_bd_e2_review.md`) 的 3 MED
**狀態**: IMPL DONE，待 E2 re-review

---

## 1. 任務摘要

E2 round 2 verdict: **APPROVE-WITH-CONDITION** (0 BLOCKER / 0 HIGH / 3 MED / 4 LOW)

本 round 修完 3 MED；4 LOW 列 P3 backlog defer。

| # | 嚴重性 | 位置 | 修法 |
|---|---|---|---|
| 1 | MED-1 | `check_pg_dump_freshness.py:483` `run()` | 開頭加 `_platform_guard()` 呼叫 |
| 2 | MED-2 | `check_pg_dump_freshness.py:452` `check_7_audit_trail` | 加 heartbeat mtime cross-check（n_rows==0 但 heartbeat fresh → 升 WARN） |
| 3 | MED-3 | `install_pg_dump_cron.sh:71` | 加 `_validate_cron_env_value()` + 7 env-var validation + cron-conflict regex |

---

## 2. 修改清單

| 路徑 | LOC 變化 | 改動性質 |
|---|---|---|
| `srv/helper_scripts/canary/healthchecks/check_pg_dump_freshness.py` | 616 → 662 (+46) | MED-1: `run()` 開頭加 `_platform_guard()` + docstring；MED-2: `check_7_audit_trail` signature 加 optional `paths`/`now_epoch` 參數 + n_rows==0 分支加 heartbeat cross-check 升 WARN；run() 呼叫 site 加傳 paths/now_epoch |
| `srv/helper_scripts/cron/install_pg_dump_cron.sh` | 97 → 132 (+35) | MED-3: 新增 `_validate_cron_env_value()` Bash function + 7 個 env-var validation call + cron-conflict regex reject + length > 200 abort exit 6 |

總 +81 LOC。無新增 / 刪除檔。

---

## 3. 3 MED 細節

### MED-1: `run()` 加 platform guard

```python
def run(
    max_age_hours: int = DEFAULT_MAX_AGE_HOURS,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> dict:
    """跑 7 個 check 並合併 verdict。

    為什麼 run() 開頭也呼 _platform_guard()：
      passive_wait_healthcheck.checks_cron_heartbeat.check_80_pg_dump_freshness
      wrapper 直接 ``mod.run()`` 不經 main()，會繞過 main() 平台守門...
    """
    import time
    _platform_guard()
    paths = _resolve_paths()
    now_epoch = time.time()
    ...
```

**原問題**：standalone `main()` 有 `_platform_guard()`，但 wrapper `checks_cron_heartbeat.check_80_pg_dump_freshness` 直接 `mod.run()` 繞過。Mac dev 跑 passive_wait_healthcheck 會走 check[6] subprocess `pg_restore`（BSD vs GNU 行為差）+ check[7] connect_pg → false-FAIL flap。

**驗證**：Mac empirical `python3 -c "import check_pg_dump_freshness as m; m.run()"` exit 2 with platform refuse 訊息（之前會跑 check[6] subprocess 出錯）。

### MED-2: heartbeat mtime cross-check

```python
def check_7_audit_trail(
    max_age_hours: int,
    paths: dict[str, Path] | None = None,
    now_epoch: float | None = None,
) -> tuple[str, str]:
    ...
    if n_rows == 0:
        # heartbeat cross-check：若 cron 最近確實 fire 過但 0 row
        # → INSERT silent fail（V113 drop / permission drift / payload bug）
        # → 升 WARN 解 mask（E2 round 2 MED-2）
        heartbeat_mtime = None
        if paths is not None and now_epoch is not None:
            heartbeat_mtime = _stat_mtime(paths["heartbeat"])
        if heartbeat_mtime is not None and now_epoch is not None:
            heartbeat_age_hours = (now_epoch - heartbeat_mtime) / 3600.0
            if heartbeat_age_hours < max_age_hours:
                return (
                    VERDICT_WARN,
                    f"cron heartbeat fresh "
                    f"({heartbeat_age_hours:.1f}h < {max_age_hours}h) "
                    f"but 0 pg_dump_completed row in 7d — "
                    f"audit INSERT likely silent fail "
                    f"(V113 dropped? permission drift? payload jsonb cast?). "
                    f"檢查 {paths['log_dir']}/trading_ai_pg_dump_cron.log",
                )
        return (
            VERDICT_INSUFFICIENT_SAMPLE,
            "no pg_dump_completed event in last 7d (cron not yet fired)",
        )
```

**原問題**：原 `if n_rows == 0: INSUFFICIENT_SAMPLE` 無法分辨「cron 從未 fire」與「cron fired 但 INSERT 被 `|| true` silent 吞」。
**修法**：cross-check 兩條獨立信號（heartbeat sentinel mtime + DB row count）。若 heartbeat fresh 但 row=0 → 升 WARN with diag log path。
**signature 向後相容**：`paths` / `now_epoch` 都是 optional，若沒傳則退化為純 INSUFFICIENT_SAMPLE（既有第三方 caller 不破）；本 module 內 `run()` 呼叫 site 已加傳。

### MED-3: cron env-var validation + cron-conflict regex

```bash
# ----- env value validation：防 cron 特殊字 / 空格 / 過長 entry 解析錯亂（E2 round 2 MED-3）-----
_validate_cron_env_value() {
    local name="$1"
    local value="$2"
    if [[ -z "$value" ]]; then
        echo "ERROR: cron env value empty: ${name}" >&2
        exit 6
    fi
    if [[ ${#value} -gt 200 ]]; then
        echo "ERROR: cron env value too long (>200 chars): ${name}=${value}" >&2
        echo "       crontab line size limit risk；請縮短 path 或 abort。" >&2
        exit 6
    fi
    if [[ "$value" =~ [[:space:]%[:cntrl:]\"\'\\\$\`] ]]; then
        echo "ERROR: cron-conflict character in ${name}=${value}" >&2
        echo "       Disallowed: space / % (cron stdin newline) / control / quote / backslash / \$ / backtick" >&2
        echo "       請用 ASCII path 無 special char；或 abort 並用 systemd timer 替代 cron。" >&2
        exit 6
    fi
}

_validate_cron_env_value "OPENCLAW_BASE_DIR" "$OPENCLAW_BASE_DIR"
_validate_cron_env_value "OPENCLAW_DATA_DIR" "$OPENCLAW_DATA_DIR"
_validate_cron_env_value "OPENCLAW_SECRETS_ROOT" "$OPENCLAW_SECRETS_ROOT"
_validate_cron_env_value "OPENCLAW_BACKUP_ROOT" "$OPENCLAW_BACKUP_ROOT"
_validate_cron_env_value "OPENCLAW_BACKUP_RETENTION_DAYS" "$OPENCLAW_BACKUP_RETENTION_DAYS"
_validate_cron_env_value "OPENCLAW_BACKUP_HOUR_UTC" "$OPENCLAW_BACKUP_HOUR_UTC"
_validate_cron_env_value "WRAPPER" "$WRAPPER"
```

**原問題**：`OPENCLAW_BACKUP_ROOT` 含 `%`/空格 → crontab entry 解析錯亂或 silent corruption。
**修法**：validation reject + abort exit 6；不採 `printf %q` 因 cron 不跑 full shell parser，`%` 即使 quoted 仍當 stdin newline；唯一可靠 = ASCII strict validation。

---

## 4. 測試結果

### 4.1 Mac syntax 全綠 + Mac fail-fast verify

```
$ python3 -m py_compile helper_scripts/canary/healthchecks/check_pg_dump_freshness.py
PY_COMPILE OK

$ bash -n helper_scripts/cron/install_pg_dump_cron.sh
BASH_N OK

$ python3 helper_scripts/canary/healthchecks/check_pg_dump_freshness.py --status
ERROR: check_pg_dump_freshness.py requires Linux runtime (current sys.platform='darwin').
       Mac dev 走 ssh trade-core；本 check 依賴 GNU stat 與 Linux pg_dump 路徑語義。
EXIT=2

$ python3 -c "import sys; sys.path.insert(0,'helper_scripts/canary/healthchecks'); import check_pg_dump_freshness as m; m.run()"
ERROR: check_pg_dump_freshness.py requires Linux runtime (current sys.platform='darwin').
       Mac dev 走 ssh trade-core；本 check 依賴 GNU stat 與 Linux pg_dump 路徑語義。
PASS: run() exit code=2 on Mac (wrapper path now fail-fast)
```

**MED-1 兩條路徑都驗 fail-fast** — standalone main() + wrapper run() 皆 exit 2。

### 4.2 Linux empirical run() 7-check JSON

```
$ ssh trade-core "source ~/BybitOpenClaw/secrets/environment_files/basic_system_services.env; \
    cd ~/BybitOpenClaw/srv && \
    cp /tmp/check_pg_dump_freshness_round3.py helper_scripts/canary/healthchecks/_round3_test.py && \
    ~/.venv/bin/python3 -c '...mod.run()...'"

{
  "verdict": "INSUFFICIENT_SAMPLE",
  "checks": [
    ["[1]", "PASS", "backup dir OK (/home/ncyu/pg_backups)"],
    ["[2]", "INSUFFICIENT_SAMPLE", "no trading_ai_*.dump found (cron not yet fired)"],
    ["[3]", "INSUFFICIENT_SAMPLE", "no dump file to size-check"],
    ["[4]", "INSUFFICIENT_SAMPLE", "no dump file to md5-check"],
    ["[5]", "INSUFFICIENT_SAMPLE", "no dump file to retention-check"],
    ["[6]", "INSUFFICIENT_SAMPLE", "no dump file to schema-check"],
    ["[7]", "INSUFFICIENT_SAMPLE", "no pg_dump_completed event in last 7d (cron not yet fired)"]
  ]
}
```

Linux Linux platform guard 讓 run() 通過，7-check 全 INSUFFICIENT_SAMPLE-skip（V113 未 land + cron 未 fire — pre-deploy 期 expected）。check[7] heartbeat cross-check 未觸發（heartbeat sentinel 不存在），fallthrough 到原 INSUFFICIENT_SAMPLE 路徑。

### 4.3 Linux empirical install_pg_dump_cron.sh validation negative tests

```
$ # Test 1: clean env (DRY-RUN should exit 0)
$ OPENCLAW_BASE_DIR=... OPENCLAW_BACKUP_ROOT=/tmp/pg_backups_test bash test_install.sh
------- proposed crontab entry -------
DRY-RUN: not modifying crontab.
exit=0

$ # Test 2: % in OPENCLAW_BACKUP_ROOT
$ OPENCLAW_BACKUP_ROOT='/tmp/pg%backups' bash test_install.sh
ERROR: cron-conflict character in OPENCLAW_BACKUP_ROOT=/tmp/pg%backups
       Disallowed: space / % (cron stdin newline) / control / quote / backslash / $ / backtick
exit=6

$ # Test 3: space
$ OPENCLAW_BACKUP_ROOT='/tmp/pg backups' bash test_install.sh
ERROR: cron-conflict character in OPENCLAW_BACKUP_ROOT=/tmp/pg backups
exit=6

$ # Test 4: >200 chars
$ OPENCLAW_BACKUP_ROOT=$(python3 -c 'print("/tmp/" + "x"*250)') bash test_install.sh
ERROR: cron env value too long (>200 chars): OPENCLAW_BACKUP_ROOT=...
exit=6
```

4/4 negative + 1/1 positive 全綠。

---

## 5. 治理對照

| 項目 | 對齊 | 證據 |
|---|---|---|
| E2 round 2 MED-1 「`run()` 加 `_platform_guard()`」 | ✅ | check_pg_dump_freshness.py:528 |
| E2 round 2 MED-2 「heartbeat mtime cross-check 解 silent V113-INSERT-fail mask」 | ✅ | check_pg_dump_freshness.py:467-489 |
| E2 round 2 MED-3 「install_pg_dump_cron.sh ENTRY env-var validation + cron-conflict」 | ✅ | install_pg_dump_cron.sh:71-100 + 102 |
| memory `feedback_cross_platform` 跨平台 | ✅ | Mac fail-fast 兩條路徑都驗 |
| memory `feedback_chinese_only_comments` Chinese-first | ✅ | 3 處新增注釋全中文 |
| 硬邊界 max_retries / live_execution / system_mode 不可改 | ✅ | 純 read-only check + cron install validation；無 mutate any governance state |
| CLAUDE.md §九 800/2000 LOC 警戒 | ✅ | 662 + 132 都 < 800 |
| 不擴 scope（task 嚴格 = 只修 3 MED）| ✅ | 4 LOW 全 defer P3 backlog；無順手「優化」 |

---

## 6. 不確定之處

### 6.1 MED-2 heartbeat cross-check 邊角

當 `paths["heartbeat"]` 是 `data_dir / "cron_heartbeat" / "trading_ai_pg_dump.last_fire"`，這就是 cron wrapper line 63 `touch "$HEARTBEAT_DIR/trading_ai_pg_dump.last_fire"` 寫的同個 file。但若 operator 改 `OPENCLAW_DATA_DIR` 沒一致更新，路徑會錯位。當前依 cron wrapper + healthcheck 共享 env 解析語義，**operator 必保持 `OPENCLAW_DATA_DIR` 兩處一致**（已對齊 cron 預設）。

### 6.2 MED-3 validation 與既有 `$HOME` 預設值的相容

`OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"` 預設展開 `$HOME` 為 `/home/ncyu`，總長 < 200 char，無 special char — Linux runtime OK。但若 `$HOME` 路徑含 space / `%` / control char（極罕見 edge case）會 abort。**Operator HOME 路徑必 ASCII clean**（trade-core /home/ncyu 已符合）。

### 6.3 4 LOW defer 中 LOW-1 push back

E2 列 LOW-1：`trading_ai_pg_dump_cron.sh:63` heartbeat sentinel 被 touch 但 round 2 `check_pg_dump_freshness.py:122` resolve 後無 check 讀 — 「dead resolution」。

**Round 3 MED-2 fix 已使用 heartbeat sentinel**（cross-check n_rows==0 場景），LOW-1 dead resolution 自動消解 — 變成「live cross-check signal」。E2 round 3 re-review 時可順便重新評估 LOW-1 是否仍有效（推測：可從 P3 backlog 移除）。

我看後悔不一併修：LOW-1 順手消解。但其餘 3 LOW（LOW-2 timeout 60→120s / LOW-3 cron lock dir 同步 / LOW-4 report 描述更正）嚴格守 task scope 不擴。

### 6.4 MED-1 兩條 guard 重複是否冗餘？

`main()` 仍呼 `_platform_guard()` + `run()` 也呼。重複 OK — `main()` 是 CLI entry，必須早 fail；`run()` 是 wrapper entry，必須獨立 fail-fast。**未來若有第三條 entry path（如 pytest fixture mock），不需修；`_platform_guard()` 是冪等**（sys.exit 或 noop）。

---

## 7. Operator 下一步

1. **E2 round 3 re-review**（≤5min；只看 3 處 diff）
   - `check_pg_dump_freshness.py:528 run()` `_platform_guard()` 呼叫
   - `check_pg_dump_freshness.py:400-490 check_7_audit_trail` signature + heartbeat cross-check
   - `install_pg_dump_cron.sh:71-102 _validate_cron_env_value` + ENTRY 組裝
2. E2 sign-off 後 **E4 regression**（per E2 §9 必跑 1+3+4，建議 2+5）
3. PM commit + push round 3 + round 2 + round 1 三 wave 合 PR
4. 部署順序（operator 上線）：commit/push → ssh trade-core git pull → apply V113 → install_pg_dump_cron.sh → wait 03:00 UTC fire → `passive_wait_healthcheck.sh --quiet` 應看 `[80] verdict=PASS`

---

## 8. 文件參考

- **E2 round 2 review**: `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-27--ops_4_gap_bd_e2_review.md` §5 + §10 conditions
- **E1 round 2 IMPL**: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-27--ops_4_round_2_e1_pg_dump_healthcheck.md`
- **Round 1 land**: 4 個檔 commit chain（cron/install + cron + verify + V113）
- **Memory log**: `docs/CCAgentWorkSpace/E1/memory.md` 末段 2026-05-27 round 3

---

**E1 IMPLEMENTATION DONE: 待 E2 審查（report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-27--ops_4_round_3_e1_3med_fix.md）**
