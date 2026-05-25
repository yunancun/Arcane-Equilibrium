# E1 IMPL — AC-19 ALT bucket daily cron (W2-F NEW QA-2)

**Date**: 2026-05-25
**Owner**: E1 (per W1-G SOP §8 handoff)
**Trigger**: W2-F QA report `2026-05-25--w2f_stream_e_bucket_monitor_stream_b_m4_leakage_audit.md` NEW QA-2 HIGH — AC-19 cron 0% IMPL'd，Day 8/9 cron-captured trajectory 已 lose；5/26 EOD deadline
**SOP**: `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-25--ac19_alt_bucket_14d_monitor_sop.md` §8
**Scope**: 3 helper script + tests + SCRIPT_INDEX 更新；crontab line PM 接做 ssh paste
**Status**: IMPL DONE — 待 E2 審查 + PM crontab install

---

## §1 任務摘要

per W2-F QA-2：`ls /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/ac19_alt_bucket*` = 0 hit；JSONL summary 不存在。5/26 EOD 不 IMPL → 14d AC-19 trajectory 統計 power lose。

按 W1-G SOP §8 specification 落 4 個 deliverable：
1. SQL canonical (per SOP §2)
2. cron wrapper shell (per SOP §3.1)
3. CSV → JSONL writer + sanity verify (per SOP §3.1 step 2)
4. 44 pytest case 釘 contract

---

## §2 修改清單

| 新增/修改 | 路徑 | LOC | 說明 |
|---|---|---|---|
| 新增 | `helper_scripts/cron/ac19_alt_bucket_daily_query.sql` | 70 | bucket-split + Wilson CI 95% + 3 級 verdict (含 INSUFFICIENT_DATA n=0)；per W1-G SOP §2 canonical。 |
| 新增 | `helper_scripts/cron/ac19_alt_bucket_jsonl_writer.py` | 377 | stdlib only；wilson_lower/upper_95 / classify_verdict / load_psql_csv / build_jsonl_records (含 sanity drift > 1pp 偵測) / append_jsonl fsync / aggregate_exit_code。 |
| 新增 | `helper_scripts/cron/ac19_alt_bucket_daily_cron.sh` | 98 | secrets env load (對齊 panel_aggregator_health_cron) + lock mkdir + heartbeat sentinel + day_index>14 idempotent skip + psql --csv + writer 串接；exit 0/1/2 對應 verdict 聚合。 |
| 新增 | `helper_scripts/cron/tests/__init__.py` | 1 | 測試 package marker。 |
| 新增 | `helper_scripts/cron/tests/test_ac19_alt_bucket_daily.py` | 364 | 44 pytest case：Wilson 5 / verdict 13 / bucket 3 / day_index 5 / CSV 4 / JSONL 3 / append 2 / exit 5 / CLI 2。 |
| 修改 | `helper_scripts/SCRIPT_INDEX.md` | +9 | 新增 5 entry + 最後更新行更新。 |
| 修改 | `docs/CCAgentWorkSpace/E1/memory.md` | +30 | E1 自身工作日誌。 |

---

## §3 關鍵 diff（治理 / 設計核心點）

### §3.1 Wilson CI 雙端 sanity drift 偵測

Python `build_jsonl_records` 不直接信任 SQL CASE 的 verdict / Wilson lower；對每 row 重算後對比：

```python
drift = abs(recomputed_lower - sql_lower)
if drift > SANITY_DRIFT_TOLERANCE_PCT:  # 1.0pp
    record["sanity_drift_pct"] = round(drift, 2)
    record["sql_wilson_lower_pct"] = sql_lower
# 永遠用 Python 重算的 verdict 取代 SQL CASE
record["verdict"] = recomputed_verdict
```

為什麼：防 SQL 浮點 / `GREATEST(..., 0)` 邊界與 Python `math.sqrt` 結果系統性漂移；超過 1pp tolerance 寫 JSONL 留證據，但仍以 Python 為 SSOT 計算最終 verdict。Empirical Linux smoke 驗 0 drift（SQL 14.2 = Python 14.2）。

### §3.2 day_index > 14 idempotent skip

```bash
DAY_INDEX=$(python3 -c "from datetime import date; print((date.today() - date(2026,5,19)).days + 1)" 2>/dev/null || echo 0)
if [[ "$DAY_INDEX" -gt 14 ]]; then
    echo "[$(ts)] 14d window expired (day_index=${DAY_INDEX}/14); skipping. QA final verdict pending." >> "$DAILY_LOG"
    exit 0
fi
```

per W1-G SOP §3.3 14d expiry hook：cron 自身在 day > 14 後 idempotent skip，不會繼續寫 JSONL；QA 在 6/2 手動跑 final verdict report。

### §3.3 lock mkdir 防 overrun

```bash
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: ac19_alt_bucket_daily_cron already running (lock held)" >> "$DAILY_LOG"
    exit 0
fi
trap "rmdir \"$LOCK_DIR\" 2>/dev/null || true" EXIT INT TERM
```

對齊 `halt_audit_pg_writer_cron.sh` 範式；mkdir atomic，防同分鐘多次 fire（cron overrun 或 operator 手動 invoke 撞車）導致 JSONL 重複 append。

### §3.4 stdlib only（無 psycopg2 依賴）

`ac19_alt_bucket_jsonl_writer.py` 只用 `math / csv / json / argparse / pathlib`；PG query 由 wrapper script `psql --csv` 完成，writer 純走 CSV → JSONL pipeline。降低 cron entry 對 venv / pip 環境的依賴，避免 `psycopg2.OperationalError: fe_sendauth: no password supplied`（前車 LG5-W3-FUP-3-CRON-ENV 教訓）類的 cron barebones env 失敗。

---

## §4 治理對照

| 治理項 | 對應 |
|---|---|
| 硬邊界：max_retries=0 / authorization | ✅ 無觸碰；read-only SELECT + 寫 /tmp JSONL only |
| 新文件 MODULE_NOTE | ✅ writer.py + tests/__init__.py + test 套件均含；shell 用 file-level header 註釋 |
| 中文注釋默認 | ✅ 新代碼全中文注釋；無新增英文段 |
| 800 行警告 / 2000 行硬上限 | ✅ 最大檔 writer.py 377 行 |
| 新 singleton 登記 | N/A（純 stdlib module；無 singleton） |
| SCRIPT_INDEX.md 更新 | ✅ 5 entry + 最後更新行 |
| sub-agent hygiene SOP | ✅ ssh trade-core 僅 read-only psql + python3 dry-run + pytest；無 cargo build / sudo / 寫 PG |
| W1-G SOP §8 handoff | ✅ 3 script + tests + 1 crontab paste line 全完成 |
| pytest count | ✅ Mac 44/44 PASS + Linux 44/44 PASS |
| 跨平台 grep `/home/ncyu` | shell 用 `$HOME/BybitOpenClaw/srv` 默認 + `OPENCLAW_BASE_DIR` 注入 override；Python 純相對 path + Path() / 不硬編碼 |
| SQL 參數化 / SQL injection | ✅ SQL 完全靜態（無 placeholder），由 psql -f file 跑；writer Python 端不對 PG 寫，無 SQL injection 面 |

---

## §5 Mac pytest verify

```
$ python3 -m pytest helper_scripts/cron/tests/test_ac19_alt_bucket_daily.py -q
............................................                             [100%]
44 passed in 0.05s
```

44/44 PASS。

---

## §6 Linux 經驗 PG smoke test (read-only SELECT only)

scp 3 file + tests/ → trade-core；ssh 跑 psql --csv -f SQL → writer dry-run → pytest 44 case。

### §6.1 psql --csv 輸出

```
bucket,attempts,fills,timeouts,fill_rate_pct,wilson_lower_pct,wilson_upper_pct,verdict
alt,35,9,23,25.7,14.2,42.1,FAIL
large_cap,6,4,1,66.7,30.0,90.3,FAIL
```

對齊 W1-G SOP §1 baseline 完全一致：
- `alt 35 attempts / 9 fills / 23 timeouts = 25.7%` → Wilson lower 14.2% < 20% → **FAIL**
- `large_cap 6 attempts / 4 fills / 1 timeout = 66.7%` → Wilson lower 30.0% < 60% gate → **FAIL** (low-n)

### §6.2 writer dry-run JSONL stdout

```json
{"ts":"2026-05-25T19:36:55Z","day_index":7,"window_start":"2026-05-19T00:00:00Z","window_end":"2026-06-02T00:00:00Z","bucket":"alt","attempts":35,"fills":9,"timeouts":23,"fill_rate_pct":25.7,"wilson_lower_pct":14.2,"wilson_upper_pct":42.1,"verdict":"FAIL"}
{"ts":"2026-05-25T19:36:55Z","day_index":7,"window_start":"2026-05-19T00:00:00Z","window_end":"2026-06-02T00:00:00Z","bucket":"large_cap","attempts":6,"fills":4,"timeouts":1,"fill_rate_pct":66.7,"wilson_lower_pct":30.0,"wilson_upper_pct":90.3,"verdict":"FAIL"}
```

- Python 重算 Wilson lower = SQL 14.2（**0 drift**，無 sanity_drift_pct 欄位）
- day_index=7（5/25 UTC）正確（5/26 cron fire 將自動 = 8，覆蓋 W2-F NEW QA-2 Day-8 目標）
- 兩 row append OK

### §6.3 Linux pytest

```
............................................                             [100%]
44 passed in 0.06s
```

44/44 PASS（Mac + Linux 雙端 contract 對齊）。

---

## §7 Crontab line for PM operator paste

PM 主會話接做 ssh trade-core crontab install：

```
0 8 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw $HOME/BybitOpenClaw/srv/helper_scripts/cron/ac19_alt_bucket_daily_cron.sh >>/tmp/openclaw/logs/ac19_alt_bucket_daily_cron.cron.log 2>&1
```

Install recipe (PM 接做)：
```bash
ssh trade-core "(crontab -l 2>/dev/null; echo '0 8 * * * OPENCLAW_BASE_DIR=\$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \$HOME/BybitOpenClaw/srv/helper_scripts/cron/ac19_alt_bucket_daily_cron.sh >>/tmp/openclaw/logs/ac19_alt_bucket_daily_cron.cron.log 2>&1') | crontab -"
ssh trade-core 'crontab -l | grep ac19_alt_bucket'
```

5/26 08:00 UTC cron 首發即可 capture day_index=8。

---

## §8 5/26 EOD Deadline Tracking

| 階段 | Owner | 狀態 | ETA |
|---|---|---|---|
| 3 helper script IMPL | E1 | ✅ DONE (2026-05-25) | — |
| pytest 44 case | E1 | ✅ Mac + Linux 全 PASS | — |
| Linux empirical PG smoke | E1 | ✅ DONE (alt 14.2% / large_cap 30.0% 對齊 SOP §1) | — |
| Crontab paste | PM 主會話 | ⏳ 等 E2 sign-off → ssh paste | 5/26 08:00 UTC（首發前） |
| Day 8 cron evidence | cron auto | ⏳ 5/26 08:00 UTC 首發後驗證 | 5/26 08:01 UTC |
| Day 14 final verdict | QA 手動 | ⏳ 6/2 00:00 UTC | 6/2 |

**5/26 EOD deadline 達標**：3 script IMPL + 44 pytest PASS + Linux empirical smoke 全綠；PM 只需 crontab paste 即可 capture Day 8。

---

## §9 不確定之處

1. **SQL `1.96::numeric` vs Python `float(1.96)` 精度漂移**：本次 empirical 對齊 0 drift；但 Wilson lower 接近 30% 邊界（如未來 fill rate 提升 → Wilson lower 跨 30%）時，Python 與 SQL 可能在最後 0.05pp rounding 差異上 flip verdict。Python 端為 SSOT（已用 recomputed_verdict 覆蓋 SQL CASE），SQL CASE 已降為 informational。
2. **psql --csv 對 trailing summary line 行為**：`load_psql_csv` 用 defensive 邏輯 skip `(n rows)` 或 `---`，但 psql --csv 默認不印此 trailing；測試已 cover defensive case，empirical OK。
3. **lock dir 清理 race**：若 cron 內進程被 kill -9 lock dir 殘留，下次 cron 直接 SKIP。對齊 sibling `halt_audit_pg_writer_cron.sh` 範式，operator 可 `rmdir /tmp/openclaw/locks/ac19_alt_bucket_daily_cron.lock.d` 手動清。
4. **psycopg2 不依賴**：故意走 stdlib only；若未來 PA 想加更 rich 統計（如 binomial test p-value）需 psycopg2，再做切換。

---

## §10 Operator 下一步 / 鏈尾

1. **E2 審查**：審 3 script + 44 pytest case + SCRIPT_INDEX 更新 + 治理對照表
2. **E4 regression**（如 E2 通過後）：跑 full pytest suite 驗無新 regression
3. **PM crontab install**：per §7 install recipe ssh paste；驗 `crontab -l | grep ac19_alt_bucket`
4. **5/26 08:01 UTC day-8 cron evidence verify**：
   ```bash
   ssh trade-core 'tail /tmp/openclaw/logs/ac19_alt_bucket_daily_$(date -u +%Y-%m-%d).log'
   ssh trade-core 'tail /tmp/openclaw/ac19_alt_bucket_14d_summary.jsonl'
   ```

E1 IMPL DONE：待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-25--ac19_alt_bucket_cron_impl.md`）
