# Stock/ETF Docs README Index Gate Restoration

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；docs README/index structure gate restoration

## 結論

已修復 full docs README/index structure gate 的既有 drift。這次只更新 `docs/README.md` 的穩定入口索引，
不改 production code、runtime behavior、IBKR/Bybit connector、secret、DB/evidence writer 或 paper
order route。

## 變更

- 新增 `Static Guard Index`。
- 補回 `docs/agents/` guard-required entries：`agents/domain.md`、`agents/issue-tracker.md`、
  `agents/triage-labels.md`。
- 補回 helper script registry：`../helper_scripts/SCRIPT_INDEX.md`。
- 補回 `CCAgentWorkSpace/` 19 個 Agent / role directories 描述，並固定
  `CCAgentWorkSpace/MIT/`、`CCAgentWorkSpace/BB/`、`CCAgentWorkSpace/Operator/` trace anchors。
- 補回 `docs/archive/` top-level Markdown 檔名索引。

## 驗證

- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py --tb=short`：`7 passed`。
- Dynamic docs trace coverage：PASS；主計畫與 Operator summary checkpoint title coverage 保持同步。
- `git diff --check`：PASS。

## 邊界

- 無 production code change。
- 無 trading logic / risk semantics change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access、read-only probe execution。
- 無 result import、DB/evidence writer、paper order route、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
