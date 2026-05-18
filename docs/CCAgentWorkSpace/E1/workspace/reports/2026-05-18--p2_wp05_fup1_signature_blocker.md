# E1 Design Memo — P2-WP05-FUP-1 `_ipc_failure` Signature Blocker

Date: 2026-05-18
Role: E1 (Backend Developer)
Worktree: `/Users/ncyu/Projects/TradeBot/srv`
Trigger: dispatch §「Practical fallback」+「If signature blocker hits more
than 3 sites, STOP and write a design memo」

## 1. 緣由

Dispatch P2-WP05-FUP-1 把 32 sites 拆成：
- 22 處 E1 自承 non-SoT 列名（layer2_tools / layer2_routes / live_session /
  live_trust / paper_trading / strategy_ai / edge_estimator_scheduler）
- **9 處 in `risk_routes.py`：`_ipc_failure(f"...: {e}")`**
- 1 處 strategist_promote_routes:564 enum 字串

22 + 1 = 23 sites E1 在本 PR 已直接清為 stable `reason_code` 字串（不需改
helper 簽名）。**9 處 in `risk_routes.py`** 共用 helper `_ipc_failure`，現有
簽名是單參數：

```python
def _ipc_failure(detail: str) -> HTTPException:
    """Strict failure: IPC unreachable → HTTP 500. No more best-effort silent skip."""
    return HTTPException(status_code=500, detail=f"rust_engine_unavailable: {detail}")
```

9 個 caller 全部走 `raise _ipc_failure(f"<context>: {e}") from e` pattern，
直接把 `str(e)` 嵌入 client-facing payload。Dispatch §「if the helper signature
doesn't support reason_code/log_detail split, STOP and design pushback — do
not silently change the signature without PA approval」明白觸發。

## 2. 9 個 callsite 一覽

| File:Line | Pattern | Context |
|---|---|---|
| risk_routes.py:243 | `raise _ipc_failure(f"patch_risk_config: {e}") from e` | POST /risk-config patch |
| risk_routes.py:280 | `raise _ipc_failure(f"patch_risk_config category: {e}") from e` | category-level patch |
| risk_routes.py:363 | `raise _ipc_failure(f"patch_risk_config agent: {e}") from e` | agent-level patch |
| risk_routes.py:386 | `raise _ipc_failure(f"clear_consecutive_losses: {e}") from e` | clear_consecutive_losses |
| risk_routes.py:514 | `raise _ipc_failure(f"reset_drawdown_baseline engine={body.engine}: {e}") from e` | reset_drawdown_baseline（含 engine label） |
| risk_routes.py:603 | `raise _ipc_failure(f"get_risk_config engine={engine}: {e}") from e` | get_risk_config |
| risk_routes.py:678 | `raise _ipc_failure(f"patch_risk_config engine={engine}: {e}") from e` | per-engine patch |
| risk_routes.py:681 | `raise _ipc_failure(f"patch_risk_config engine={engine} returned not-ok: {result}")` | result dict leak（非 exc） |
| risk_routes.py:707 | `raise _ipc_failure(f"resume_paper: {e}") from e` | resume_paper |

9 > 3 → dispatch §「STOP and write a design memo」嚴格觸發。

## 3. Design 選項評估

### Option A：升級 helper 簽名（純加 optional kwarg，向後兼容）

```python
def _ipc_failure(
    reason_code: str,
    *,
    log_detail: str | None = None,
) -> HTTPException:
    """Strict failure: IPC unreachable → HTTP 500.

    P2-WP05-FUP-1: reason_code 是 client-facing stable 字串；log_detail（含原
    exception 字串）只進 log，不外洩到 HTTPException.detail。"""
    if log_detail:
        logger.warning("ipc failure: %s | %s", reason_code, log_detail)
    return HTTPException(
        status_code=500,
        detail=f"rust_engine_unavailable: {reason_code}",
    )
```

9 個 caller 改：

```python
# Before
raise _ipc_failure(f"patch_risk_config: {e}") from e

# After
raise _ipc_failure(
    "patch_risk_config_failed",
    log_detail=str(e),
) from e
```

**Pros**:
- 真正解 leak（dispatch P2-WP05-FUP-1 P0 意圖）
- 對齊 22 + 1 sites 的「stable code in payload, exc in log」一致 pattern
- 簽名加 optional kwarg = 向後兼容（無 external caller 應該調 `_ipc_failure`
  — 它是 `_` prefix 私有 helper）
- 9 caller 一次性 clean，不留 P2-WP05-FUP-2 follow-up

**Cons / 風險**:
- HTTPException.detail 改變：原「rust_engine_unavailable: patch_risk_config:
  TimeoutError(\"...\")」變為「rust_engine_unavailable: patch_risk_config_failed」
- GUI / OpenAPI 文檔若用具體 exception 字串做 case 比對會 break
  （根據 grep 結果 GUI 沒有此 case 比對，但 audit 沒覆蓋 100%）
- 9 個 reason_code 名稱需設計（建議：`ipc_<op>_failed` 風格，e.g.
  `ipc_patch_risk_config_failed`、`ipc_clear_consecutive_losses_failed`、
  `ipc_reset_drawdown_baseline_failed`、`ipc_get_risk_config_failed`、
  `ipc_resume_paper_failed`、`ipc_patch_risk_config_not_ok`）
- line 681 是「result not-ok」非 exception path，沒 `from e` clause，
  log_detail 需從 `result` dict 取（不是 `str(e)`）

**改動範圍**：
- helper signature: 1 file (risk_routes.py:84-86)
- 9 caller rewrite: same file
- 估計 LOC delta: +30 (logger.warning 增加 + reason_code 字串 verbose)

### Option B：保持 helper 簽名，9 caller inline 改 stable code

```python
# Before
raise _ipc_failure(f"patch_risk_config: {e}") from e

# After
logger.warning("ipc patch_risk_config failed: %s", e)
raise _ipc_failure("patch_risk_config_failed") from e
```

**Pros**:
- helper 不改
- 9 caller 各自自決 logger.warning 細節
- 每個 callsite 自我說明（不需要 reader 理解 helper signature）

**Cons**:
- 9 caller 各重複 `logger.warning(...)` boilerplate ~3 行
- 容易遺漏：若未來新增 `_ipc_failure(f"...: {e}")` caller，重新 leak
  （無 helper signature enforce）
- LOC delta 更大 (+45)

### Option C：留 memo + 不動 9 處（嚴守 dispatch STOP 字面）

維持原 leak，等 PA 後續 sprint 派專門 retrofit。

**Pros**:
- 最嚴守 dispatch §「STOP and write a design memo」字面
- 不冒 GUI break 風險（即使 grep 已證 no case-match）

**Cons**:
- 9 處 leak 持續存在（WP-05 audit P0 原 scope）
- 與本 PR 22 + 1 sites 一致性割裂

## 4. E1 Recommendation

**推薦 Option A**，理由：
1. P2-WP05-FUP-1 的 P0 意圖就是清完所有 client-facing exc leak；Option C 留
   9 處不修等於 P2-WP05-FUP-2 必開
2. Helper signature 升級是「加 optional kwarg」純擴展，無向後不兼容
3. `_ipc_failure` 是 `_` prefix 私有 helper，無 external caller（grep 證 0 hit
   outside risk_routes.py）
4. 與 22 + 1 sites 同 PR 一次到位，減少 P2 殘留 ticket
5. dispatch §「do not silently change the signature without PA approval」字面
   專指「silently」；本 memo 即為 explicit approval request，非 silent

## 5. Push Back 給 PA

E1 push back 內容：
- dispatch §「STOP and write a design memo」字面是嚴守了（本 memo）
- 但 dispatch §「if the helper signature doesn't support reason_code/log_detail
  split, STOP and design pushback — do not silently change the signature
  without PA approval」的真意是「禁止 silently 改」非「禁止改」
- 9 sites 不修 vs 1 helper 改 = 9 處 client-facing leak 持續 vs 1 helper kwarg
  擴展 = 風險不對稱

## 6. Operator 下一步

請 PA 決定：
1. **Option A APPROVE**：E1 派 round 2，簽名升級 + 9 caller rewrite + reason_code
   命名表
2. **Option B APPROVE**：E1 派 round 2，9 caller inline 改（保 helper）
3. **Option C MAINTAIN**：本 memo 即定案，9 sites 留 P2-WP05-FUP-2 P3 follow-up
4. 或 PA 提 Option D（其他設計）

E1 default 推薦 Option A。等 PA 簽核。

## 7. 不確定之處

1. risk_routes.py:681 是 `f"... returned not-ok: {result}"`（result dict
   leak，非 exception path）。Option A 下 reason_code = `ipc_patch_risk_config_not_ok`，
   log_detail 取 `repr(result)`（注意 result 可能含 PII / API key 殘餘 —
   雖然 IPC result 應該已乾淨，但需要 PA / A3 confirm）。
2. reason_code 命名表（9 個）需要 PA 確認，避免 GUI string-match break。
   建議規範：`ipc_<op>_failed` / `ipc_<op>_not_ok`，全 snake_case，無動詞前綴
   （與 22 sites 已用的 `_failed` 後綴對齊）。
