# E1 IMPL — P3-AUDIT-SCRIPT-STALE-CONST funding_arb audit polish

- Date: 2026-05-21
- Branch/HEAD: (working tree change，未 commit；待 E2 review)
- Spec source: FA F2 RCA (2026-05-21) verdict + operator prompt P3-AUDIT-SCRIPT-STALE-CONST

## 1. 任務摘要

`helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.py:71` 寫死
`SL_HARD_CAP_PCT = 0.03`（2026-05-02 funding_arb override 期望值）。
W-AUDIT-6 (2026-05-09) 後該 per-strategy override 從 demo TOML 移除，
funding_arb effective SL gate 退化為 global `limits.stop_loss_max_pct` =
25%（dyn_stop floor 25 × 0.25 = 6.25%）。FA F2 RCA 指出 6.29% loss/notional
fill 經此 audit script 觸發「SL gate failure」**假警報**，root cause = stale
const。任務 = 改 audit script 從 demo TOML 動態讀 SL hard cap + 加 test。

## 2. 修改清單

| 檔 | 改動 |
|---|---|
| `helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.py` | (1) module docstring + module-level comment 註明 W-AUDIT-6 後 stale 0.03 已淘汰 + 歷史 cross-ref caveat；(2) 加 `tomllib (3.11+) → tomli → None` 三層 fallback import；(3) 新 `_load_sl_hard_cap_pct()` 函數動態讀 `risk_config_demo.toml`，優先 `per_strategy.funding_arb.stop_loss_max_pct_override` > `limits.stop_loss_max_pct`；(4) 拆 const：`SL_HARD_CAP_PCT` 改為 module-load 動態值（當前 0.25），新 `SL_OBSERVE_BUCKET_PCT = 0.03`（hardcoded SQL FILTER 觀測 bucket）；(5) SQL `sl_cap` 參數改用 `SL_OBSERVE_BUCKET_PCT`（保 `n_over_3pct` 歷史可比）；(6) `evaluate_2a_trigger` 兩條 rationale 改用 f-string `{effective_sl_pct:.1f}%`；(7) `render_markdown` 加 effective SL gate header + 表格列名改為「observe bucket」+ effective gate failure 文字；(8) `main()` exit_code 1 條件從 `n_over_5pct > 0` 改為 `max_loss_notional_pct > SL_HARD_CAP_PCT + SL_SLIPPAGE_BUFFER_PCT`（語意正確：effective gate + slippage buffer 才是 gate failure 邊界）；(9) docstring exit codes 同步 |
| `helper_scripts/db/audit/test_funding_arb_14d_audit.py` (NEW) | 5 unittest 覆蓋 `_load_sl_hard_cap_pct` 四條 path（global fallback / funding_arb override / missing per_strategy / per_strategy 存在但無 override key）+ 1 real TOML smoke test 驗 W-AUDIT-6 後當前 effective = 25%；用 `importlib.util.spec_from_file_location` 動態載入有日期前綴的 audit module |

## 3. 改前 / 改後核心值對照

| 項目 | 改前 (stale) | 改後 (dynamic) |
|---|---|---|
| `SL_HARD_CAP_PCT` (module-level) | `0.03` (hardcoded) | `_load_sl_hard_cap_pct()` → `0.25` (from TOML) |
| effective gate failure threshold | (none — 用 `n_over_5pct > 0` 寫死 5%) | `0.30` = `SL_HARD_CAP_PCT + SL_SLIPPAGE_BUFFER_PCT` (動態) |
| FA F2 那 6.29% fill 是否觸發 exit_code 1 | **YES (假警報)** | **NO (0.0629 < 0.30)** ✓ |
| SQL `n_over_3pct` / `n_over_5pct` FILTER 值 | 0.03 / 0.05 | 0.03 / 0.05 (不變 — 用新 `SL_OBSERVE_BUCKET_PCT`) |
| render header「3% hard cap; >5% = SL gate bug」 | 寫死 | f-string「effective SL gate {N.N}%; >{M.M}% = SL gate failure」(動態) |
| decision rationale「3% SL 救不回 / 3% SL cannot save it」 | 寫死 | f-string「當前 effective SL gate ({N.N}%) 救不回」(動態) |

## 4. tomllib 讀取邏輯

```python
def _load_sl_hard_cap_pct() -> float:
    """從 risk_config_demo.toml 動態讀取 funding_arb SL hard cap (純小數比例)。
    
    優先級：
      1. per_strategy.funding_arb.stop_loss_max_pct_override (若存在)
      2. limits.stop_loss_max_pct (global fallback)
    """
    if tomllib is None:  # pragma: no cover
        print("[WARN] tomllib unavailable ... 回退 STALE_REFERENCE_2026_05_02 = 0.03",
              file=sys.stderr)
        return 0.03  # STALE_REFERENCE_2026_05_02
    
    toml_path = (
        Path(__file__).resolve().parents[3]
        / "settings" / "risk_control_rules" / "risk_config_demo.toml"
    )
    with toml_path.open("rb") as f:
        cfg = tomllib.load(f)
    
    per_strategy = cfg.get("per_strategy", {}).get("funding_arb", {})
    override = per_strategy.get("stop_loss_max_pct_override")
    if override is not None:
        return float(override) / 100.0
    
    return float(cfg["limits"]["stop_loss_max_pct"]) / 100.0


SL_HARD_CAP_PCT = _load_sl_hard_cap_pct()  # module-load 跑一次
```

三層 fallback：`tomllib` (3.11+) → `tomli` → `None` (stale 0.03 + stderr 警告)。對齊既有 `engine_watchdog.py:34-41` / `checks_cost_edge.py:143-145` / `test_grid_blocked_symbols_config.py:11-14` 模式。

## 5. Test 驗證

### 5.1 unittest 5/5 PASS

```
test_global_fallback_returns_25_pct ........................... ok
test_funding_arb_override_takes_priority ...................... ok
test_missing_per_strategy_section_falls_back_to_global ........ ok
test_per_strategy_funding_arb_missing_override_key_falls_back . ok
test_current_demo_toml_returns_25_pct ......................... ok

Ran 5 tests in 0.002s
OK
```

執行：`python3 -m unittest helper_scripts.db.audit.test_funding_arb_14d_audit -v`

### 5.2 Module-level smoke (E1 額外驗證)

```
SL_HARD_CAP_PCT (effective, dynamic) = 0.25
SL_OBSERVE_BUCKET_PCT (legacy observe) = 0.03
SL_SLIPPAGE_BUFFER_PCT (legacy observe) = 0.05
effective + slippage_buffer (gate failure threshold) = 0.3
6.29% < gate failure threshold? True   ← FA F2 假警報已修
```

### 5.3 Syntax / argparse

```
$ python3 helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.py --help
usage: 2026-05-16_funding_arb_14d_audit.py [-h] [--quiet]
...

$ python3 -m py_compile helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.py \
                          helper_scripts/db/audit/test_funding_arb_14d_audit.py
compile OK
```

## 6. 治理對照

- **範圍**：嚴格按 prompt 指定文件（audit script + 新 test）；未動 `risk_config_demo.toml`；未動其他 audit script；未動 `passive_wait_healthcheck/db.py`。
- **注釋語言**：中文 default，技術名詞（`tomllib`、`Wilson`、`SQL FILTER`、`per_strategy`、`stop_loss_max_pct_override` 等）英文保留；舊 bilingual block 仍存（未觸及 → 不改）。
- **跨平台**：`Path(__file__).resolve().parents[3]` 動態取 srv root，無硬編碼 `/home/ncyu` / `/Users/ncyu` / TradeBot 路徑。Mac 3.10 + tomli + Linux 3.12 + tomllib 兩條 path 都驗。
- **Linux PG dry-run 要求**：本任務不涉 V### migration、不動 PG schema、純 audit script polish；不需 PG dry-run。
- **GUI sign-off SOP**：本任務不動 JS / GUI；不適用 `node --check`。
- **檔案大小**：audit script 462 → 581 行（< 800 warning / << 2000 hard cap）；新 test 檔 131 行。
- **新 singleton / 新 cron / 新 script index entry**：無；本任務純 polish + 加 test，不引入新可變狀態。

## 7. Push back / OQ

### 7.1 Push back（已採納為設計選擇，需 E2 verdict）

**Prompt 字面 vs 語意實際**：prompt 寫
```python
SL_HARD_CAP_PCT = _load_sl_hard_cap_pct()  # 改為動態讀 TOML
```
直譯會把 `0.03 → 0.25`，但 SQL `_AGG_SQL` 同時用 `%(sl_cap)s` 計算 `n_over_3pct` ——
若 `sl_cap = SL_HARD_CAP_PCT = 0.25`，`n_over_3pct` 變「fill 損失 > 25% notional 的數量」，
歷史 audit 表格「Fills exceeding 3% notional」（觀察 slippage zone）的意義就消失。

**E1 做法**：拆兩個 const：
- `SL_OBSERVE_BUCKET_PCT = 0.03` (hardcoded) → 純 SQL FILTER 統計觀測 bucket，與 effective SL gate 解耦
- `SL_SLIPPAGE_BUFFER_PCT = 0.05` (hardcoded) → 同上
- `SL_HARD_CAP_PCT = _load_sl_hard_cap_pct()` → 動態，反映 effective gate，用於 rationale / render / exit_code 邏輯

請 E2 / FA verdict：是否同意此「拆 const」拆分？三條替代：
- **(a) 採納 E1 拆分**（目前實作）— 保留 SQL bucket 歷史可比性 + dynamic effective gate
- **(b) 嚴格直譯 prompt** — 全部 const 統一動態 → SQL filter 變 25%/25%，audit 表格失去「3% 觀察 zone」意義（但跟 effective gate 一致）
- **(c) 完全廢除 SQL `n_over_3pct` / `n_over_5pct`** — 改為以 max_loss_pct + effective gate 計算 + 表格只報「fills exceeding effective gate」、「fills exceeding effective + buffer」

### 7.2 OQ — Open Questions

1. **OQ-AUDIT-1 歷史 cross-ref**：本動態讀只反映**當前** TOML，不重建歷史。若被 audit 的 fill 落在 W-AUDIT-6 commit (2026-05-09) 之前，當期 effective SL 才是 3%。已在 module docstring + `_load_sl_hard_cap_pct` docstring 明標 caveat + 「需 `git log -p settings/risk_control_rules/risk_config_demo.toml` 做 commit timeline cross-ref」。但本 script 不自動做此 cross-ref。如需歷史正確 audit，是否要另開 FIX ticket 引入 git log parsing？目前判斷：留 OQ，PM 後續決定（audit script 用途偏 spot-check，不必要做 fully historical reconstruction）。

2. **OQ-AUDIT-2 SL_OBSERVE_BUCKET_PCT 是否該改名為更明確的「observability bucket」變數名**：目前命名「SL_OBSERVE_BUCKET_PCT」可能仍讓 maintainer 誤以為與 SL gate 有關。替代命名 `LEGACY_LOSS_BUCKET_3PCT` / `OBS_LOSS_BUCKET_3PCT`。E1 push back：當前命名加上 module-level comment block 三段詳細解釋已足夠 disambig；但若 E2 認為命名仍有歧義，建議改為 `OBS_LOSS_BUCKET_LO = 0.03` / `OBS_LOSS_BUCKET_HI = 0.05`（明示為觀測 bucket）。

3. **OQ-AUDIT-3 stale fallback 0.03 是否該 raise 而非降級**：tomllib + tomli 都不存在的場景下 `_load_sl_hard_cap_pct` 回 stale 0.03 + stderr 警告，audit 仍能跑。替代：直接 `raise RuntimeError("tomllib / tomli required")` 讓 audit 拒跑。Linux 3.12 runtime 不可能命中此 path；Mac 3.10 ad-hoc 跑 audit 也已裝 tomli。**保守選降級**（既有 `engine_watchdog.py` / `checks_cost_edge.py` 都這麼做），但若 E2 認為應 fail-closed raise 也可改。

### 7.3 不確定之處

無重大不確定。一個次要觀察：
- module-level `SL_HARD_CAP_PCT = _load_sl_hard_cap_pct()` 會在 module import 時讀真實 TOML（unittest 預設 fixture 副作用）。若 test 環境 TOML 不存在或內容異常，import 階段直接 raise FileNotFoundError / KeyError → 5/5 test 全失敗。當前 `helper_scripts/db/audit/test_funding_arb_14d_audit.py` 假設真實 TOML 在 srv tree（這在 dev / runtime / CI 都成立）。若未來分離 audit script 至 separate package 必處理 lazy load。

## 8. 對 FA F2 RCA verdict 的閉環效果

- **FA F2 RCA verdict**：「6.29% loss/notional → SL gate failure 是假警報」
- **改前 audit 行為**：寫死 `SL_HARD_CAP_PCT = 0.03` + exit_code 1 條件 `n_over_5pct > 0`（任何 fill > 5% 就觸發）→ 6.29% fill 觸發 exit_code 1 + render header「3% hard cap」claim
- **改後 audit 行為**：動態讀 `SL_HARD_CAP_PCT = 0.25`，exit_code 1 條件 `max_loss_pct > 0.30` → 6.29% fill **不**觸發；render header 顯示 effective SL gate 25% + observe bucket 3% / 5% 為「歷史觀測 bucket，非當前 gate threshold」

驗算：FA F2 那筆 fill `max_loss_notional_pct = 0.0629` < `SL_HARD_CAP_PCT (0.25) + SL_SLIPPAGE_BUFFER_PCT (0.05) = 0.30` → return 0（無假警報），同時 `n_over_3pct` / `n_over_5pct` 統計仍正常計入觀察表格。

## 9. Operator / E2 下一步

1. **E2 review**：
   - 對 §7.1 push back 三選一給 verdict（推薦 (a)）
   - 對 §7.2 OQ-AUDIT-1/2/3 給 verdict
   - 驗 `_load_sl_hard_cap_pct` 三條 path 邏輯正確性
   - 驗 module docstring W-AUDIT-6 cross-ref 是否充分（特別是歷史 audit caveat）
2. **E4 regression**：跑 audit script 在當前 demo data（如 Linux runtime PG 可達），確認：
   - Markdown render 表格列名「Effective SL gate ... 25.0%」正確顯示
   - decision rationale 中「effective SL gate ({N.N}%) 救不回」N.N = 25.0
   - exit code = 0（無 max_loss > 30% 場景時）
3. **QA Audit**（若 E2 通過）：
   - 確認 audit 在 demo runtime PG 上跑出對應 14d window 結果不破壞舊 expected
   - 跑 `pytest helper_scripts/db/audit/test_funding_arb_14d_audit.py -v` 確認 5/5 pass
4. **PM**：commit + push（強制鏈 E1→E2→E4→QA→PM）

## 10. 檔案絕對路徑

- 改動 1：`/Users/ncyu/Projects/TradeBot/srv/helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.py`
- 新增：`/Users/ncyu/Projects/TradeBot/srv/helper_scripts/db/audit/test_funding_arb_14d_audit.py`
- 本 report：`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-21--p3_audit_script_stale_const_fix.md`

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-21--p3_audit_script_stale_const_fix.md）
