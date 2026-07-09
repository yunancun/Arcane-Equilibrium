# E1 IMPL — P1-CRON-INSTALL-WAVE-1 + P2-WP05-CSP-UNSAFE-INLINE

Date: 2026-05-18
Author: E1
Status: SOURCE / TEST DONE — pending E2 review then E4 regression.
Operator gate: 已申明今日 source/test only；**未** install crontab、**未**
ssh trade-core、**未** carve real `/tmp/openclaw/` 路徑。

---

## 任務摘要

### Task 1 — P1-CRON-INSTALL-WAVE-1
5 個 cron wrapper 已 source/test land 但 crontab 尚未 install。為每個 cron
建立 heartbeat sentinel + healthcheck `[75]`-`[79]`，使「cron 是否按時 fire」
進入 passive_wait_healthcheck cron 監測。

### Task 2 — P2-WP05-CSP-UNSAFE-INLINE
為 GUI `app/static/trading.html` 的唯一外部 CDN `unpkg.com/lightweight-charts@4.1.0`
加 SRI integrity hash（SHA-384）+ 提供 helper script 給未來 CDN 用。

---

## 修改清單

### Task 1
| 路徑 | 動作 | LOC |
|---|---|---|
| `helper_scripts/db/passive_wait_healthcheck/checks_cron_heartbeat.py` | 新檔 — 5 公開 check + 共用 `_classify` | +192 |
| `helper_scripts/db/passive_wait_healthcheck/__init__.py` | 加 import + `__all__` 登記 | +18 |
| `helper_scripts/db/passive_wait_healthcheck/runner.py` | 加 import + 5 個 `results.append` 區塊（conn.close 後） | +25 |
| `helper_scripts/cron/panel_aggregator_health_cron.sh` | start-time touch sentinel | +6 |
| `helper_scripts/cron/wave9_replay_no_live_mutation_watch.sh` | start-time touch（exec 之前） | +7 |
| `helper_scripts/cron/replay_key_rotation_check.sh` | start-time touch sentinel | +6 |
| `helper_scripts/cron/feature_baseline_writer_cron.sh` | start-time touch sentinel | +6 |
| `helper_scripts/cron/blocked_symbols_30d_unblock_check_cron.sh` | start-time touch sentinel | +5 |
| `helper_scripts/db/test_cron_heartbeat_healthchecks.py` | 新檔 — 42 test | +233 |
| `docs/execution_plan/2026-05-18--p1_cron_install_wave_1_install_recipe.md` | 新檔 — operator-only install one-liner | +105 |
| `helper_scripts/SCRIPT_INDEX.md` | 登記 3 新檔 | +3 |

### Task 2
| 路徑 | 動作 | LOC |
|---|---|---|
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/trading.html` | 加 integrity + crossorigin + SRI 用意註解 | +7 |
| `helper_scripts/security/compute_sri_hashes.sh` | 新檔 — helper（version-pin 啟發檢查 + base64 SHA-384） | +93 |

**Net LOC delta**: +706（新 codepath 多為註解與 fixture matrix；test 占 33%）。

---

## 關鍵 diff（語義要點）

### `checks_cron_heartbeat.py` — 共用 classify
```python
def _classify(check_id, sentinel_name, cadence_label, threshold_seconds, now=None):
    sentinel = _resolve_heartbeat_dir() / sentinel_name
    warn_severity = "FAIL" if _required_mode() else "WARN"
    age = _age_seconds(sentinel, now_ts)
    if age is None: return (warn_severity, "heartbeat file missing ...")
    if age > threshold_seconds: return (warn_severity, "heartbeat stale ...")
    return ("PASS", "heartbeat fresh ...")
```
邊界：`age == threshold` → PASS（strictly-greater stale）。

### Cron wrapper heartbeat（5 個一致模式）
```bash
# Cron heartbeat sentinel — P1-CRON-INSTALL-WAVE-1（2026-05-18）。
# touch-at-start：「cron 被排程觸發」的證據，由 healthcheck [NN] 監測 mtime。
HEARTBEAT_DIR="${DATA}/cron_heartbeat"
mkdir -p "$HEARTBEAT_DIR" 2>/dev/null || true
touch "$HEARTBEAT_DIR/<name>.last_fire" 2>/dev/null || true
```
唯一例外：`wave9_replay_no_live_mutation_watch.sh` 用
`HEARTBEAT_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}/cron_heartbeat"`（該檔
無自有 `DATA` 變數）。

### trading.html SRI
```html
<script src="https://unpkg.com/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js"
        integrity="sha384-rcCMiCptH4kTlEbg0euOTUKWe72TESbrjElatnG+9BfbmUIV268UK/Pro5biJdGm"
        crossorigin="anonymous"></script>
```
hash 由 `compute_sri_hashes.sh` 計出，與 `bash helper` 輸出 byte-equivalent。

---

## 治理對照

| 規則 | 處理 |
|---|---|
| 不擴大 PA 範圍 | 僅 source/test；無 crontab install、無 ssh trade-core |
| 改動前先讀檔 | 讀 `checks_close_maker_audit.py` + `checks_live_pipeline.py` 模仿 helper signature；讀 runner.py 三段（imports / cursor block / post-close）；讀 5 個 wrapper 確認 exit pattern |
| 注釋默認中文 | 新代碼註解全中文（per `feedback_chinese_only_comments` 2026-05-05） |
| 新文件 800/2000 line cap | `checks_cron_heartbeat.py` 192 LOC / test 233 LOC，遠低於 800 |
| 新 script 登記 | SCRIPT_INDEX.md 加 3 條 |
| Shell paste-safety | install recipe 全部 one-liner，無 heredoc / multi-line `for`（per `feedback_shell_paste_safety` 2026-04-21） |
| 跨平台 grep | 所有路徑用 `${OPENCLAW_DATA_DIR}` / `${OPENCLAW_BASE_DIR}`；無 `/home/ncyu` / `/Users/ncyu` 硬編碼於程式碼（install recipe 內 literal 路徑是 cron 限制，operator 安裝專用） |
| Healthcheck 必附 review date / external action | install recipe `## Author / Sign-off` 段列 E2 / E4 / operator gate pending |
| Singleton 登記 | N/A（無新 mutable singleton） |
| SQL Guard A/B/C | N/A（無新 migration） |

---

## 不確定之處

1. **Threshold 75min（wave9 hourly）+ 25h（daily）+ 8d（weekly）**：grace 設計
   基於 cron 抖動經驗（5min/1h/1d/1d），若 E2 / operator 認為太鬆或太緊可
   調整；helper `_classify` 的 threshold_seconds 是參數化，**單一 caller
   修改一行即生效**。
2. **WARN-by-default policy**：operator dispatch 明示 cron infra 不是
   promotion-blocking。若 E2 認為應分等級（panel_aggregator 5min 用 WARN
   合理，weekly 30d unblock 過時 8d 可能就該 FAIL），可在 follow-up 給
   `[79]` 單獨 hardcode FAIL；目前 5 個一致 WARN。
3. **沒做** install crontab（operator 明令；report `## Operator 下一步`
   給 install one-liner）。
4. **沒做** `tab-monitoring.html` 的 `<iframe src="http://trade-core:3000/...">`：
   非 unpkg / cdnjs / jsdelivr 第三方 CDN，是同網域 Grafana iframe，不在
   P2-WP05 範圍。
5. **沒做** trading.html 的 `<a href="https://demo-trading.bybit.com">`：
   non-executable hyperlink，不在 SRI 適用範圍。

---

## Operator 下一步

1. E2 review（`.claude/agents/E2.md` race check + shellcheck-grade
   peer review on 5 cron diffs + Python module + tests + helper script）。
2. E4 regression（passive_wait_healthcheck 全套 + helper_scripts sibling
   smoke + GUI HTML node parse smoke）。
3. 若 E2 + E4 過 → operator 在 trade-core 跑 install recipe 5 條 one-liner
   `crontab -l 2>/dev/null | (cat; echo "...") | crontab -`。
4. Install 後等首個 cycle（panel 6min）→ `ls -la /tmp/openclaw/cron_heartbeat/`
   驗 sentinel 出現 → 跑 `python3 helper_scripts/db/passive_wait_healthcheck.py`
   grep `[75-79]` 應 PASS（已 fire）或 WARN（尚未 fire）。

---

## 驗證證據

- `pytest helper_scripts/db/test_cron_heartbeat_healthchecks.py -v`
  → **42 passed in 0.04s**
- `bash -n` × 5 cron wrappers → all PARSE_OK
- `bash -n helper_scripts/security/compute_sri_hashes.sh` → PARSE_OK
- `bash helper_scripts/security/compute_sri_hashes.sh` → hash 與
  `trading.html` 嵌入值 byte-equivalent
- Python `html.parser` feed `trading.html` → PARSE_OK
- `OPENCLAW_DATA_DIR=$TMPDATA bash panel_aggregator_health_cron.sh` →
  sentinel correctly touched 即使 wrapper 因 missing PG creds bail
- `python3 -c "from helper_scripts.db.passive_wait_healthcheck import (check_75_..., check_79_...); ..."` → IMPORT_OK
- `python3 -c "from helper_scripts.db.passive_wait_healthcheck.runner import main"` → RUNNER_IMPORT_OK

---

## E1 IMPLEMENTATION DONE
report path: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-18--p1_cron_install_wave_1_and_p2_wp05_csp_sri.md`
