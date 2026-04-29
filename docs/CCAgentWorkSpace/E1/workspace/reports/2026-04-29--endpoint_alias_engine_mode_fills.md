# E1 報告 — endpoint alias `engine_mode_fills_summary`

**日期**：2026-04-29
**任務**：在 `agents_routes.py` 加 endpoint alias `/api/v1/agents/engine_mode_fills_summary`，與既有 `/api/v1/agents/shadow_vs_live_summary` 共享同一個 handler / 同一個 helper。舊路徑保留供 backward compat。
**完成狀態**：完成，待 E2 審查 + E4 回歸。
**詳細報告**：`srv/.claude_reports/20260429_192523_e1_endpoint_alias_engine_mode_fills.md`

---

## 修改清單（簡）

| 檔案 | 動作 | LOC |
|---|---|---|
| `app/agents_routes.py` | 抽 shared handler + 加 canonical route + module docstring 更新 | 334 → 387 |
| `app/agents_routes_helpers.py` | 加 `_fetch_engine_mode_fills_summary` + `afetch_engine_mode_fills_summary` 一行 delegate；既有 fn 命名+behavior 不動 | 783 → 798 |
| `tests/test_agents_routes.py` | 加 2 測試（route registered + alias same payload as legacy） | 872 → 988 |

## 驗收（Mac dev）

```
cd /Users/ncyu/Projects/TradeBot/srv && \
  ./venvs/mac_dev/bin/python -m pytest \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agents_routes.py \
  -k "engine_mode or shadow_vs_live" -v
```
**結果**：6 passed（4 legacy 0 regression + 2 new alias 全綠）。
全檔：23 passed（含 `test_helpers_module_under_size_guards` 重綠）。

## 邊界遵守

- 0 改 SQL（per spec）
- 0 改前端（GUI 走 E1a 並行 task）
- 0 改 PG schema
- 0 刪舊 endpoint（backward compat）
- 0 改既有 helper 命名 / behavior（避免 import 破裂）
- 0 觸 §四 硬邊界（max_retries / live_execution_allowed / execution_authority / system_mode）
- 0 hardcoded 路徑（grep clean）

## 不確定點

詳細 6 項見 `.claude_reports/...e1_endpoint_alias_engine_mode_fills.md` §5。主要是「既有 legacy fn 命名是否最終 deprecation」「`data_category` 字串是否最終正名」等留給 PA / PM 後續 ticket。
