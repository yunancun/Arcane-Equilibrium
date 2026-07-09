# E1 LG5-W3-FUP-1 — `review_live_candidate` consumer scheduler 接線

**Date**: 2026-05-02
**Owner**: E1
**Spec source**: PA dispatch LG5-W3-FUP-1 (HIGH)
**Branch**: main (uncommitted, awaiting E2 review)
**Repo**: `/Users/ncyu/Projects/TradeBot/srv/`

---

## 1. 任務摘要

PA 派發任務：把 IMPL-2 `review_live_candidate(hub, candidate_id)` consumer 接進現有 scheduler 系統，每 N 分鐘 poll `learning.mlde_param_applications` pending live promotion candidates 並逐個 review，藉此修復 production runtime healthcheck `[42] live_candidate_eval_contract` FAIL（`recent_24h_total=8` 但 `unaudited_over_1h=27` —— consumer 已 land 但無 scheduler 在 call）。

**完成狀態**：完成。新增 sibling 模組 `lg5_review_consumer_scheduler.py` + `Lg5ReviewConsumer` daemon thread + `main.py` startup hook + 10 unit tests + 健康檢查文檔更新。10/10 新測試 PASS，相關 regression 88/88 PASS，full pytest 3727 PASS（5 pre-existing Mac dev numpy/sklearn fail 不相關）。

---

## 2. 修改清單

| Path | 動作 | 行數 | 說明 |
|---|---|---|---|
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/lg5_review_consumer_scheduler.py` | 新增 | 442 | LG-5 consumer 排程器主檔。`Lg5ReviewConsumer` class + `start_consumer_scheduler()` + `_acquire_leader_lock()` + `_fetch_pending_candidate_ids()` + `_config_from_env()` + `_reset_for_tests()`。 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py` | 修改 | +28 | startup hook 在 EdgeEstimatorScheduler 之後 lazy-import `start_consumer_scheduler()`，fail-open。 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_lg5_consumer_scheduler.py` | 新增 | 256 | 10 unit tests：cycle aggregation × 1、per-candidate fail-open × 1、auth gate × 2、empty pool × 1、env config × 3、start gate × 2。 |
| `docs/healthchecks/2026-05-02--lg5_health_checks.md` | 修改 | +60 | 新增 LG5-W3-FUP-1 章節：行為摘要、env-var inventory、defaults rationale、operational verification、與 `[42]` 的關係。 |
| `docs/CCAgentWorkSpace/E1/memory.md` | 修改 | +25 | 追加本任務 lessons（sync vs async / LOC budget / sibling 分檔策略 / lazy import 循環 / `_reset_for_tests` pattern）。 |

**LOC delta**：新增 ~698 行 production+test+doc，修改 ~88 行。`edge_estimator_scheduler.py` **未動**（保 855 行不再增）。

---

## 3. 關鍵 diff

### 3.1 `lg5_review_consumer_scheduler.py`（新模組）核心 cycle 邏輯

```python
def _run_cycle(self, *, reason: str) -> dict[str, Any]:
    t_start = time.time()
    hub = self._resolve_hub()
    if hub is None:
        # Hub unavailable — record skip, no DB read
        ...

    # Hard skip if not authorized — RFC §4 / CLAUDE.md §四 fail-closed.
    try:
        authorized = bool(hub.is_authorized()) if hasattr(hub, "is_authorized") else True
    except Exception as exc:  # noqa: BLE001
        authorized = False
    if not authorized:
        summary = {"skipped": "not_authorized", "reason": reason}
        with self._lock:
            self._cycles_skipped_not_authorized += 1
        return summary

    candidate_ids = _fetch_pending_candidate_ids(self._max_per_cycle)
    reviewed = approved = rejected = deferred = 0
    errors: list[dict[str, Any]] = []

    from .governance_hub_live_candidate_review import review_live_candidate

    for cid in candidate_ids:
        try:
            verdict = review_live_candidate(
                hub, candidate_id=cid,
                decided_by="GovernanceHub.review_live_candidate.scheduler",
            )
            reviewed += 1
            decision = getattr(verdict, "decision", "defer")
            if decision == "approve":   approved += 1
            elif decision == "reject":  rejected += 1
            else:                       deferred += 1
        except Exception as exc:  # noqa: BLE001 — per-candidate fail-open
            self._total_errors += 1
            errors.append({"candidate_id": cid,
                           "error_class": type(exc).__name__,
                           "error_msg": str(exc)})

    # Aggregate INFO log + status update ...
    return summary
```

### 3.2 `main.py` startup hook 接線

```python
# ── LG5-W3-FUP-1: review_live_candidate consumer scheduler ───────────────
# 啟動 LG-5 IMPL-2 consumer 排程器（每 5min poll pending live candidates）。
# Sibling daemon to EdgeEstimatorScheduler with independent leader election;
# under uvicorn --workers 4 only one worker actually runs the consumer.
try:
    from .lg5_review_consumer_scheduler import (
        start_consumer_scheduler as _start_lg5_consumer,
    )
    _lg5_consumer = _start_lg5_consumer()
    if _lg5_consumer is not None:
        base.logger.info(
            "Lg5ReviewConsumer started (leader worker) / "
            "LG-5 review consumer 已啟動（leader worker）"
        )
    else:
        base.logger.info(
            "Lg5ReviewConsumer skipped (non-leader worker or env disabled) / "
            "LG-5 review consumer 跳過（非 leader 或 env 關閉）"
        )
except Exception as _lg5_consumer_exc:
    base.logger.warning(
        "Lg5ReviewConsumer startup failed (fail-open): %s / "
        "LG-5 consumer 啟動失敗（不阻斷）：%s",
        _lg5_consumer_exc, _lg5_consumer_exc,
    )
```

### 3.3 SQL fetch（oldest-first 緩解 backlog）

```sql
SELECT id
FROM learning.mlde_param_applications
WHERE engine_mode = 'live'
  AND status = 'candidate'
  AND application_type = 'live_promotion_candidate'
  AND decision_lease_id IS NULL
ORDER BY ts ASC
LIMIT %s
```

`ORDER BY ts ASC`（oldest-first）確保 `[42] unaudited_over_1h` backlog 中等最久的 candidate 優先處理。`LIMIT` 由 `OPENCLAW_LG5_CONSUMER_MAX_PER_CYCLE` 控制（default 16，對齊 `R4_PENDING_CAP` = `mlde_demo_applier.max_recommendations`）。

---

## 4. 治理對照

| 條目 | 條款 | 狀態 |
|---|---|---|
| CLAUDE.md §二 #1 單一寫入口 | consumer 不寫訂單；只 invoke review_live_candidate（其本身只寫 audit log + UPDATE candidate row）。 | 符合 |
| CLAUDE.md §二 #6 失敗默認收縮 | hub 不可達 / 未授權 / DB fetch 失敗 → fail-closed 跳過 cycle；單 candidate 失敗 fail-open 不中斷批次（PA spec 明確要求）。 | 符合 |
| CLAUDE.md §二 #8 交易可解釋 | 每 cycle INFO log 聚合統計；audit row 由 review_live_candidate 自帶（不重複 emission）；status() 提供 SQL/grep 替代品。 | 符合 |
| CLAUDE.md §四 硬邊界 | 未動 max_retries / live_execution_allowed / authorization.json / risk_config / V035。 | 符合 |
| CLAUDE.md §七 雙語注釋 | 模組頂 MODULE_NOTE 雙語、所有 public function docstring 雙語、inline 不變量雙語、INFO/WARN log 字符串雙語。 | 符合 |
| CLAUDE.md §七 跨平台 | env var fallback 模式（`OPENCLAW_DATA_DIR` → `/tmp/openclaw`）；fcntl.flock POSIX-portable；無 `/home/ncyu` / `/Users/<name>` 硬編碼。 | 符合 |
| CLAUDE.md §九 文件大小 | 新檔 442 行（< 800 警告線）；`edge_estimator_scheduler.py` 855 行**未增**（避免推進警告線）。 | 符合 |
| CLAUDE.md §九 singleton 登記 | `_consumer` / `_consumer_lock` / `_LEADER_LOCK_FD` / `_LEADER_LOCK_PATH` 為新 singleton —— **建議 E2 在 §九 表登記**（請見「不確定之處」）。 | **新增需登記** |
| RFC v2 §2.3 audit emission | review_live_candidate 自帶 audit row；wrapper 不重複（PA spec 明確要求）。 | 符合 |
| RFC v2 §4 `[42]` revoke trigger | 此 wire-up 修正 root cause；deploy 後 `[42] unaudited_over_1h` 應 ~5 min 內 27 → 0。 | 解 |
| RFC v2 §4 lease TTL bands | 全留給 review_live_candidate 內部處理（含 learning_period flag）。 | 符合 |

**未規範但合理之處**：
- `OPENCLAW_LG5_CONSUMER_*` env var 命名 prefix 與既有 `OPENCLAW_*` 對齊。
- `lg5_review_consumer.leader.lock` sentinel 命名與 `edge_scheduler.leader.lock` 對齊。
- `decided_by="GovernanceHub.review_live_candidate.scheduler"` 字串符合 PA spec docstring 樣式（`.scheduler` / `.operator_manual:<actor>` / `.bulk_re_evaluation`）。

---

## 5. 不確定之處

1. **CLAUDE.md §九 singleton 表登記**：本檔新增 4 個 module-level singleton（`_consumer`、`_consumer_lock`、`_LEADER_LOCK_FD`、`_LEADER_LOCK_PATH`）。E2 審查時是否要求一併在 CLAUDE.md §九 表加 row？我**未動** CLAUDE.md（不擴張 PA 給定的改動範圍），但治理規定「新增 singleton 必須在此表登記」。建議 E2 決定是否同 commit 補登記，或單開後續任務。
2. **PA spec async vs 我選 sync**：PA 樣板寫 `async def _run_lg5_review_consumer(ipc_call: IpcCall, ...)` 但既有 EdgeEstimatorScheduler 全 sync threading.Thread。我選 sync 與既有 pattern 一致（押 PA「選你認為最 clean 的」授權）。若 E2 認為應改 async，需重構為 `asyncio.create_task` + 引入 event loop ownership。
3. **新 sibling file vs 接進 edge_estimator_scheduler.py**：PA 提兩個選項，我選 sibling file 因 edge_estimator_scheduler.py 已 855 行（過 800 警告線）。若 E2 認為應集中於 edge_estimator_scheduler.py，需先安排 split 任務再接（會推 LOC 至 ~1050+）。
4. **獨立 leader lock vs 共用 edge scheduler 的 leader 身份**：我選獨立 sentinel `lg5_review_consumer.leader.lock`，理由 = 一方 crash 不影響另一方。但 uvicorn workers=4 下變成「2 個 worker 各持一鎖」（edge leader + consumer leader 不一定同 worker）—— 這是 acceptable 但偏離「single leader」直覺。E2 若認為應共用，需設計 shared sentinel。
5. **Cross-platform pytest 限制**：我在 Mac dev 跑測試不能完全 verify Linux runtime 行為（PG connection / socket path）；新 unit test 純 mock 依賴（fcntl.flock 是 OS-level，Mac/Linux 都支援）。建議 E4 在 Linux 端跑 `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_lg5_consumer_scheduler.py` 確認跨平台。
6. **PA 強約束 `OPENCLAW_LG5_CONSUMER_ENABLED=true`**：PA spec 寫 default `true`，我實裝為 default `"1"`（env 字串以 `!= "0"` 判定）—— 等價但允許 `1/yes/true/anything-not-0` 都 enable。若 E2 認為應嚴格只接受 `true/false`，需小調 `_config_from_env()`。

---

## 6. Operator 下一步

### 6.1 審查重點（給 E2）

- [ ] 確認 sibling file 策略 vs PA「最自然位置 = edge_estimator_scheduler.py」是否可接受
- [ ] 確認 sync threading vs PA spec async 寫法選擇
- [ ] 確認獨立 leader lock vs 共用 leader 身份
- [ ] 確認是否同 commit 補 CLAUDE.md §九 singleton 表登記
- [ ] grep 雙語注釋（每 public function / class / module 都應雙語）
- [ ] grep cross-platform 路徑硬編碼（已自驗 0 hit）
- [ ] 跑 `git diff --check`（已自驗 0）

### 6.2 給 E4 的 regression 任務

```bash
# Mac 端已驗證
cd /Users/ncyu/Projects/TradeBot/srv && python3 -m pytest \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_lg5_consumer_scheduler.py \
  program_code/ml_training/tests/test_mlde_demo_applier.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_lg5_review_live_candidate.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_edge_estimator_scheduler_min_observation_ts.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_edge_estimator_scheduler_leader_lock.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_edge_estimator_scheduler_observability.py -q
# 預期：88 passed
```

```bash
# Linux 端 (E4 必跑)
ssh trade-core "cd ~/BybitOpenClaw/srv && python3 -m pytest \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_lg5_consumer_scheduler.py -q"
# 預期：10 passed
```

### 6.3 給 PM 的部署觀察點（rollout 後）

- 等 E2 + E4 + QA 通過後 PM 統一 commit + push + `restart_all.sh --rebuild --keep-auth`（**E1 不直接 commit / deploy**）。
- Deploy 後**~5 min 內** healthcheck `[42] live_candidate_eval_contract` 應從 FAIL（27 unaudited）→ PASS（0 unaudited）。
- 監看：`journalctl -u openclaw-api --since "30 min ago" | grep "Lg5ReviewConsumer\["` —— 應每 5 min 一行 INFO log + 一個 leader-elected 行。
- 若 30 min 後 `[42]` 仍 FAIL：(1) 確認 `OPENCLAW_LG5_CONSUMER_ENABLED` 不是 0；(2) 確認恰好 1 個 worker 報 `elected leader`；(3) 確認 `cycles_skipped_not_authorized` 沒在累積（若有 = hub 未授權，需先修 authorization）。

### 6.4 Mac CC 自驗結果

```text
py_compile:                              PASS (3 files)
new tests (test_lg5_consumer_scheduler):  10 passed in 0.03s
related regression (88 tests):            88 passed in 0.50s
full pytest (skipping 10 pre-existing
  numpy/sklearn collection errors):       3727 passed / 5 failed (5 pre-existing
                                         Mac dev numpy/sklearn unavailable; not
                                         caused by this change)
git diff --check:                         0 warnings
cross-platform grep (硬編碼路徑):          0 hits
```

---

**Wait gate**：E2 review → E4 regression → QA Sign-off → PM 統一 commit + push + deploy。E1 不自行 commit。
