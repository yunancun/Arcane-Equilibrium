# E1 Fix Report — STRATEGIST-SINGLETON-POLLUTION P3 (Option B + A combined)

**Date**: 2026-04-28 CEST
**Base HEAD**: `e2875da` (origin/main)
**Worktree**: main repo working tree (per LOSSES/SINGLETON pattern)
**PA RFC**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--strategist_singleton_pollution_investigation.md`
**Verdict**: **35 → 0 fail in `test_h_state_query_handler.py`. W3 8/8 PASS, W2/W1/LOSSES 40/40 PASS, no regression.**

---

## §1 任務摘要

PA RFC 揪出 root cause = CPython `from PKG import SUB` attribute precedence — `test_api_contract.py:16` 的 `importlib.reload(main_legacy)+importlib.reload(main)` 透過 transitive import 將真 `app.strategy_wiring` 永久綁到 `app` package attribute。test fixture `_install_fake_strategy_wiring` 只 patch `sys.modules`，沒 patch attribute → `_collect_h_snapshots` / `_collect_agent_snapshots` 內 `from . import strategy_wiring as _sw` 解析回真 STRATEGIST_AGENT（zero stats），35 個對 fake 值的 assertion 全 fail。

**修法**：
- **Option B（production，主修）**：`h_state_query_handler.py` 兩處 `from . import strategy_wiring as _sw` 改 `_sw = sys.modules.get("app.strategy_wiring")`，繞過 attribute precedence。runtime 語意等價（uvicorn boot 時 sys.modules 與 package attr 同步填入）；既有 fail-soft None fallback 已支持 lookup miss → empty shell。
- **Option A（test fixture，defense-in-depth）**：`_install_fake_strategy_wiring` 同時 patch `sys.modules["app.strategy_wiring"]` 與 `app.strategy_wiring` package attribute；`_restore_strategy_wiring` atomic 反序還原（含 sentinel 區分「原無屬性」vs「原綁 None」）。鏡 W3 fix（commit `a2b660d`）dual-patch pattern。Backward-compat 接受舊單值 `prev` 形狀。

完成狀態：✅ Mac 隔離跑 90/90 PASS · ✅ 同 session 跑（含 polluter）108/108 PASS · ✅ W3 8/8 PASS 不退化 · ✅ W2+W1+LOSSES 40/40 PASS 不退化 · 無新 fail 引入。

## §2 修改清單

| Path | 動作 | 行數 | 一句話說明 |
|---|---|---|---|
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/h_state_query_handler.py` | 修改 | +49 / -16（淨 +33；含長雙語注釋）| (1) 加 `import sys` (2) `_collect_h_snapshots` 內 `from . import strategy_wiring as _sw` 改 `sys.modules.get` (3) `_collect_agent_snapshots` 內同改（共 2 處） |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_h_state_query_handler.py` | 修改 | +75 / -8（淨 +67；含 sentinel + 雙語注釋）| `_install_fake_strategy_wiring` 加 `app.strategy_wiring` attribute patch + 回 tuple `(prev_in_modules, prev_attr)`；`_restore_strategy_wiring` 接 tuple，含 sentinel `_SW_ATTR_MISSING` 區分原無屬性 vs 原綁 None；backward-compat 接受舊單值 prev |

## §3 關鍵 diff

### h_state_query_handler.py — Option B production fix

```diff
 import logging
 import os
+import sys
 import time
 from typing import Any, Optional
```

```python
# _collect_h_snapshots (line ~327)
# OLD:
#     try:
#         from . import strategy_wiring as _sw  # noqa: PLC0415
#     except Exception as exc: ...
# NEW:
    _sw = sys.modules.get("app.strategy_wiring")
    if _sw is None:
        logger.debug(
            "_collect_h_snapshots: app.strategy_wiring not in sys.modules; "
            "falling back to empty shell "
            "/ sys.modules 缺 app.strategy_wiring；退回空殼"
        )
        return None, None, None, None, None
```

(`_collect_agent_snapshots` line ~490 同樣模式，second occurrence。)

### test_h_state_query_handler.py — Option A defense-in-depth

```python
_SW_ATTR_MISSING = object()  # sentinel for "no attribute on app pkg"

def _install_fake_strategy_wiring(strategist, ...):
    # ... existing fake_mod construction ...
    sys.modules["app.strategy_wiring"] = fake_mod
    # NEW: also patch app package attribute (W3 dual-patch parity)
    import app as _app_pkg
    prev_attr = getattr(_app_pkg, "strategy_wiring", _SW_ATTR_MISSING)
    _app_pkg.strategy_wiring = fake_mod
    return (prev_in_modules, prev_attr)

def _restore_strategy_wiring(prev):
    # backward-compat: accept old single-value prev
    if isinstance(prev, tuple) and len(prev) == 2:
        prev_in_modules, prev_attr = prev
    else:
        prev_in_modules, prev_attr = prev, _SW_ATTR_MISSING
    # restore sys.modules
    if prev_in_modules is None:
        sys.modules.pop("app.strategy_wiring", None)
    else:
        sys.modules["app.strategy_wiring"] = prev_in_modules
    # restore parent attr (sentinel-aware)
    import app as _app_pkg
    if prev_attr is _SW_ATTR_MISSING:
        if hasattr(_app_pkg, "strategy_wiring"):
            try: delattr(_app_pkg, "strategy_wiring")
            except AttributeError: pass
    else:
        _app_pkg.strategy_wiring = prev_attr
```

## §4 治理對照

| 編號 / 規範 | 符合 / 違反 / N/A | 說明 |
|---|---|---|
| CLAUDE.md §二 #6 失敗默認收縮 | ✅ 符合 | sys.modules.get → None 走既有 empty-shell fallback；handler 永不 raise |
| CLAUDE.md §二 #8 交易可解釋 | ✅ 符合 | runtime 行為等價（uvicorn boot 時 sys.modules + attr 同步填入） |
| CLAUDE.md §七 雙語注釋 | ✅ 符合 | production 兩處 + test fixture 三處皆中英對照（含 root cause + fix 推理 + W3 對稱說明） |
| CLAUDE.md §七 跨平台兼容 | ✅ 符合 | 純 Python 標準庫（`sys.modules.get`），Mac/Linux 行為一致 |
| CLAUDE.md §九 Singleton 表 | N/A | 無新 singleton；`_SW_ATTR_MISSING` 是 module-private sentinel 非 process global |
| 硬約束（max_retries=0 / live_execution_allowed / execution_authority / system_mode） | ✅ 符合 | 0 觸碰 |
| PA RFC scope 邊界 | ✅ 符合 | 嚴格 Option B + A only；未碰 17 fail executor_shadow / 3 fail phase2_routes / 18 fail strategist_promote |
| 完成序列（不直接 commit，等 E2 → E4 → PM） | ✅ 符合 | 未 commit；報告寫入 reports/ |

## §5 測試結果

| 驗收項 | 命令 | 期望 | 實際 |
|---|---|---|---|
| 隔離跑 h_state | `pytest test_h_state_query_handler.py -v` | 35 fail → 0 fail | **90 passed in 0.05s** ✅ |
| 同 session（含 polluter）| `pytest test_api_contract.py test_h_state_query_handler.py` | 35 fail → 0 fail | **108 passed in 1.45s** ✅（18 api_contract + 90 h_state） |
| W3 regression | `pytest test_strategist_cognitive_integration.py -v` | 8/8 PASS | **8 passed in 0.02s** ✅ |
| W2+W1+LOSSES regression | `pytest test_cognitive_modulator_coverage test_strategist_cognitive_w1_fix test_g8_01_fup_losses_wiring -q` | 全綠 | **40 passed in 0.04s** ✅ |
| 全 control_api_v1 套件 | `pytest control_api_v1/tests/` | ≤ baseline 38（35 h_state 消失）| **38 failed, 3070 passed**（17 executor_shadow + 18 strategist_promote + 3 phase2_routes，全部 PA RFC §6 標 out-of-scope，pre-existing 同 root cause family；隔離跑各自全綠） |

**Baseline 對齊驗證**：跑 `git stash && pytest test_strategist_promote_api.py` → 18 passed 確認 promote_api 屬同 sibling-pollution family pre-existing fail（PA RFC §2.1 漏列），非本 fix 引入。stash 已 pop 復原。

## §6 不確定之處

1. **Linux 端未驗** — Mac dev-only。PA RFC §3.3 推論「Linux 上同 commit 應同樣 35 fail」，本 fix Linux 上應同樣 35 → 0；建議 E4 regression 階段 ssh trade-core 跑一遍確認。
2. **`test_strategist_promote_api.py` 18 fail** — 同 root cause family（sibling pollution），但不在本 ticket scope（PA RFC §6 explicit）。下一輪維護週期可再開 ticket 派同樣 Option B + A pattern 修。
3. **`_install_fake_strategy_wiring` signature 變更** — return shape 從單值 module 改 tuple。本檔 `_restore_strategy_wiring` 已 backward-compat 接舊單值；其他 sibling test 若直接 introspect tuple 會打破（已 grep 確認只本檔內呼叫 `_install_fake_strategy_wiring`，無外部 caller）。
4. **`app.strategy_wiring` attribute restore 對 sibling test 副作用** — 若有 test 依賴 `_install_fake_strategy_wiring` 後 attribute 永留 fake（極不合理），會打破。實測 90 passed 證明本檔內 fixture 全 finally restore 對；外部 test_api_contract.py / test_strategist_promote_api.py 等 polluter 自己 reload 重綁，本 fix restore `_MISSING_` 也只是回到「未 reload 過」狀態，後續 reload 仍會重新綁 → safe。

## §7 Operator 下一步

1. **E2 review**：審查兩 file diff，重點：
   - h_state_query_handler.py 兩處 sys.modules.get（含長雙語注釋）是否符合「runtime 語意等價」承諾
   - test fixture 雙 patch + sentinel restore 是否 atomic、無 leak
   - 確認 PA RFC scope 邊界遵守（無擴展到其他 fail set）
2. **E4 regression**：除上面 4 個 Mac 驗收項外，建議 ssh trade-core 跑：
   - `cd ~/BybitOpenClaw/srv && PYTHONPATH=. python -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_h_state_query_handler.py -v`
   - 期望同 Mac 90 passed
3. **可選 follow-up（不阻 P3）**：
   - `test_strategist_promote_api.py` 18 fail 開新 ticket（同 root cause family，可同樣 Option B + A pattern）
   - `test_executor_shadow_toggle_api.py` 17 fail 開新 ticket
   - `test_phase2_routes.py` 3 fail 開新 ticket
4. **Commit**：本 fix 不 commit；返主會話統一 commit + push（worktree 模式 + LOSSES/SINGLETON pattern）。

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-28--strategist_singleton_pollution_fix.md`）
