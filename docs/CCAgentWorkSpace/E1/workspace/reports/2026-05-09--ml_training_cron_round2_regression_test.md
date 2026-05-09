# 2026-05-09 — ml_training cron IPC __auth fix Round 2 regression test

**Agent**：E1（Backend Developer）
**Task source**：玄衡治理任務 Round 2（auto mode dispatch）— E2 verdict RETURN-TO-E1
**E2 review (round 1)**：`b3607c10` — 1 HIGH (regression test missing) + 2 LOW
**Round 1 fix commit**：`3d8d543e fix(ml-training): IPC __auth handshake to unblock optuna param_ranges`

---

## 1. 任務摘要

E1 Round 1 commit `3d8d543e` 業務邏輯（IPC __auth wire format / cron secret 注入）E2 給 PASS（11/11 byte-equal、ml_parameter_suggestions=0 真因 = fills<80 業務樣本不足 REFUTED IPC silent fail），但因缺 regression test commit 退回。

Round 2 完成：
- HIGH-1：補 `program_code/ml_training/tests/test_optuna_ipc_handshake.py`（557 行 / 12 test method / 4 case group 全 PASS）
- LOW-1：清 `optuna_optimizer.py:324, 416` 中英並列錯誤訊息為純中文（廢除 bilingual mandate 2026-05-05）
- LOW-2：deferred（P2 ticket「拆 IPC helper 至 `_ipc_helpers.py`」交接維護週期）

---

## 2. 修改清單

| 檔 | 變動 | LOC delta |
|---|---|---|
| `program_code/ml_training/tests/test_optuna_ipc_handshake.py` | 新檔 + 12 test method | +557 |
| `program_code/ml_training/optuna_optimizer.py` | LOW-1 line 324 + 416 中英並列 → 純中文 | -1（1011 → 1010） |

---

## 3. 4 case group 覆蓋率（全 PASS）

| Group | Case 數 | 覆蓋目標 | 通過率 |
|---|---|---|---|
| (a) `_resolve_ipc_secret` | 5 | env-only / file-only / missing-file fail-soft / strip whitespace / env > file precedence | 5/5 PASS |
| (b) `_send_ipc_command` mock socket | 4 | no-secret skips auth / auth-then-business happy / auth error JSON-RPC / socket timeout propagate | 4/4 PASS |
| (c) Wire format byte-equal | 1 | 與 `ipc_client._authenticate` line 595-614 byte-equal（id=0 / method=__auth / token=HMAC-SHA256(secret, str(ts).encode("utf-8")).hexdigest() / ensure_ascii=False / "\n" terminated） | 1/1 PASS |
| (d) Critical fail-closed 不變式 | 2（1 主 + 1 補強） | server 回 authenticated=false → RuntimeError + 缺 authenticated key → RuntimeError | 2/2 PASS |
| **總計** | **12** | — | **12/12 PASS** |

> Method 數比 brief 預期的 ~10 多 2 個（補強 (b) socket timeout case + (d) missing-key case），未來覆蓋更廣的 wire format / error frame regression。

---

## 4. 既有 ml_training pytest baseline delta

| 階段 | passed | skipped | failed |
|---|---|---|---|
| Round 2 開工前（Mac） | 353 | 31 | 0 |
| Round 2 完工後（Mac） | 365 | 31 | 0 |
| Delta | **+12** | 0 | 0 |

**0 regression**，新增 12 全部 PASS（對應新 test file）。

注：Mac 無 optuna 安裝，`test_optuna.py` 整檔走 `pytest.importorskip("optuna")` skip（1 collected 1 skipped），這是 Mac 環境限制不是 fix 影響；本 fix 設計時刻意讓新 test 不依賴 optuna（IPC helper 與 optuna 無耦合），確保 Mac/Linux 雙端可跑。

---

## 5. fail-closed 不變式測試真實性驗證（mock 不掩蓋邏輯）

按 brief 強制要求「mock 不可掩蓋邏輯，必驗真 byte sequence + 真 catch silent skip」，做 adversarial mutation 雙驗：

### 5.1 對抗實驗 1：把 raise RuntimeError 改成 silent skip pass

```python
# optuna_optimizer.py:396-399 改：
if not auth_resp.get("result", {}).get("authenticated"):
    pass  # ADVERSARIAL: silent skip
```

結果：
```
FAILED test_send_ipc_command_authenticated_false_raises_no_silent_skip
FAILED test_send_ipc_command_missing_authenticated_key_raises
```

(d) 兩個 case 立即 RED — 但因 silent pass 後 wire 2 業務 call 觸發 ConnectionError（FakeSocket 沒 prime business reply），錯誤型態不是 RuntimeError 而是 ConnectionError。從 fail-closed 觀點任何 raise 都比 silent return 好；但若希望錯誤型態精準，做了第二輪實驗。

### 5.2 對抗實驗 2：把 raise 改成 silent return {}（最危險 silent skip）

```python
# optuna_optimizer.py:396-399 改：
if not auth_resp.get("result", {}).get("authenticated"):
    return {}  # ADVERSARIAL: silent return empty
```

結果：
```
FAILED test_send_ipc_command_authenticated_false_raises_no_silent_skip
  Failed: DID NOT RAISE <class 'RuntimeError'>
FAILED test_send_ipc_command_missing_authenticated_key_raises
  Failed: DID NOT RAISE <class 'RuntimeError'>
```

(d) 立即 RED 並明確標「DID NOT RAISE RuntimeError」— **fail-closed regression guard 真實有效**，這正是 E2 反問 #4 點出的反模式（IPC silent fail 偽裝成業務樣本不足）的守門人。

### 5.3 還原 source code 後 12/12 PASS

兩輪 adversarial 實驗後還原 source code，re-run pytest 確認 12/12 PASS、0 regression、Mac baseline 365 passed / 31 skipped 不變。

---

## 6. 治理對照（CLAUDE.md 強制條款）

| 條款 | 狀態 |
|---|---|
| §七 跨平台兼容性 | ✓ `grep -E '(/home/ncyu\|/Users/[^/]+)' test_optuna_ipc_handshake.py optuna_optimizer.py` exit 0 / 0 hard-coded path |
| §七 注釋默認中文（2026-05-05 governance） | ✓ test 檔 docstring + inline 純中文；optuna_optimizer.py:324, 416 順手清完中英並列（LOW-1） |
| §七 SQL migration Guard A/B/C | n/a 無 SQL migration |
| §七 被動等待 healthcheck | n/a 非被動等待 TODO |
| §七 Sign-off git status clean | 待 commit；本 report 寫入後檢 `git status --porcelain` 確認 |
| §八 完成前驗證 | ✓ pytest 12/12 + adversarial mutation × 2 + baseline regression check |
| §八 「最小影響」 | ✓ 只新增 test 檔 + 改 LOW-1 兩行 error message；不擴及 LOW-2 拆檔（deferred P2） |
| §九 800 行警告線 | LOW-2 deferred：optuna_optimizer.py 現 1010 行（pre-existing baseline 946 + 64 net 增量）— P2 ticket「拆 `_resolve_ipc_secret` + `_read_response_line` + `_send_ipc_command` 至 `program_code/ml_training/_ipc_helpers.py`」 |
| §九 mock 不掩蓋邏輯（regression-testing-protocol） | ✓ adversarial mutation × 2 真實驗證 fail-closed 守門有效 |

---

## 7. LOW-1 commit hash + Round 2 commit hash + 行數

待 sign-off 後一次 commit + push origin/main：

預期 commit message（含「ml_training E1 Round 2: regression test per E2 verdict RETURN-TO-E1」）：

```
test(ml-training): IPC __auth handshake regression + LOW-1 cleanup

E1 Round 2: regression test per E2 verdict RETURN-TO-E1 (commit b3607c10)

HIGH-1: program_code/ml_training/tests/test_optuna_ipc_handshake.py
  +557 LOC / 12 test methods / 4 case group:
  (a) _resolve_ipc_secret  — 5 case (env / file / missing / strip / precedence)
  (b) _send_ipc_command    — 4 case (no-secret / happy / auth-error / timeout)
  (c) wire byte-equal      — 1 case vs ipc_client._authenticate line 595-614
  (d) fail-closed          — 2 case (authenticated=false / missing-key)
                             both adversarial-mutation verified

LOW-1: optuna_optimizer.py:324, 416 bilingual error message → pure Chinese
  (post-2026-05-05 governance: bilingual mandate retired)

LOW-2: deferred to P2 ticket (split IPC helpers to _ipc_helpers.py)

Tests: 12/12 PASS · ml_training pytest baseline 353 → 365 (no regression)
Adversarial: silent return {} mutation caught immediately (DID NOT RAISE
             RuntimeError) — fail-closed invariant真實守門
```

實際 hash 在執行 commit 後填入。

---

## 8. 三端 git log 同步

待 sign-off 後執行：

```bash
git add program_code/ml_training/tests/test_optuna_ipc_handshake.py \
        program_code/ml_training/optuna_optimizer.py \
        srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-09--ml_training_cron_round2_regression_test.md
git commit -m "<上述 message>"
git push origin main
ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main"
```

驗證三端同步：
- Mac HEAD = Round 2 commit
- origin/main = Round 2 commit
- Linux trade-core HEAD = Round 2 commit

---

## 9. 不確定之處

1. **memory.md 更新**：本 round 2 是 process gap 補洞（不是新業務 lesson），`memory.md` 已在 round 1 記過 IPC handshake 教訓；round 2 加一條「regression test process discipline」即可。

2. **下次 5/10 03:17 cron real-fire 監控**：仍需 operator/Linux CC 在 5/10 03:17 後驗 `status_json.optuna_optimizer.status==ok && param_ranges_source==ipc`，不在本 round 2 scope。

3. **(d) socket timeout case (b-4)**：用 `socket.timeout` 觸發；Python 3.10+ 將其作 `OSError` 子類，所以 `pytest.raises((socket.timeout, TimeoutError, OSError))` 三選一容忍；future 若 helper 改成 raise `RuntimeError("ipc timeout")` 包裹，本 case 仍 PASS（OSError chain），但若改成 silent return，本 case 立即 RED。

---

## 10. Operator 下一步

1. **E2 重 review**：Round 2 = pure test 補洞 + LOW-1 cosmetic，預期 PASS verdict。
2. **E4 回歸**：確認 ml_training pytest 365 passed / 31 skipped Mac baseline 與 Linux 一致；無新 regression。
3. **PM 統一 commit + push**：等 E2 → E4 → PM 簽字後一次性 commit + push origin/main + Linux pull。
4. **觀察 5/10 03:17 cron real-fire**（解耦 round 2，但屬本主題後續驗證）。

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-09--ml_training_cron_round2_regression_test.md`）
