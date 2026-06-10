# E1 報告 — half_life_estimator 測試 scipy importorskip 守衛修復

日期:2026-06-10
角色:E1(Backend Developer)
分支:`fix/half-life-test-scipy-skip`(已 push origin)
Commit:`dc5c60d74e4770fc698b0e34ad2ee8ead43d8ce2`
Worktree:`/tmp/hl_scipy_fix`(保留,供 E2/E4/PM 使用,base = origin/main `02c80f3b`)
NO-OP 檢查:origin/main 上目標檔 grep `importorskip` 零命中 → 非 NO-OP,正常執行。

## 任務摘要

PM 已完成 RCA:Linux runtime(trade-core `/usr/bin/python3`)無 scipy,`half_life_estimator.py` 在 `_SCIPY_AVAILABLE=False` 時設計性靜默降級回 `default_14d`,致 `test_pnl_decay_pass` / `test_sharpe_decay_pass` 兩個 fit-path 測試穩定 FAIL(`method_used` 得 `'default_14d'`)。修法 = 兩測試前置 `pytest.importorskip("scipy")`(比照 `test_onnx_exporter_quantile` 重依賴守衛慣例)+ `requirements-ml.txt` 顯式宣告 scipy。estimator 本體與所有斷言零改動。

## 修改清單

| 檔案 | 改動 |
|---|---|
| `program_code/learning_engine/tests/test_half_life_estimator.py` | +6 行:兩個 fit-path 測試函數 docstring 後各加 2 行中文注釋 + `pytest.importorskip("scipy")`;`pytest` 已在檔頭 import,無新 import |
| `requirements-ml.txt` | +1 行:`scikit-learn` 行後加 `scipy>=1.10.0`(注釋對齊既有 column 26 風格,中文注釋) |

`git diff origin/main --stat`:

```
 program_code/learning_engine/tests/test_half_life_estimator.py | 6 ++++++
 requirements-ml.txt                                            | 1 +
 2 files changed, 7 insertions(+)
```

## 關鍵 diff

test_half_life_estimator.py(兩處同構,以 `test_pnl_decay_pass` 為例):

```python
    """
    # fit 路徑意圖必須有 scipy;無 scipy 時 estimator 設計性降級 default_14d,
    # 此處應誠實 SKIP 而非 FAIL(比照 test_onnx_exporter_quantile 重依賴守衛慣例)。
    pytest.importorskip("scipy")
    true_hl = 7.0
```

requirements-ml.txt:

```
scipy>=1.10.0            # half_life_estimator / _regime_math 曲線擬合與統計檢定(sklearn 轉依賴已隱含,顯式宣告求可重現)
```

## 驗證(全部親跑,Mac)

1. `python3 -m py_compile program_code/learning_engine/tests/test_half_life_estimator.py` → **OK**。
2. 解譯器探測:計劃列的 `python3.12`(無 pytest)/`python3.13`/`/opt/homebrew/bin/python3`/`~/.venv/bin/python` 皆不可用;改用 repo 自有 `venvs/mac_dev/bin/python`(3.12 + pytest + numpy + pandas + scipy 1.17.1,E1 memory 既載的正解 venv)。
3. 有 scipy(真實環境):`7 passed in 1.33s` — 斷言原樣全跑,零放寬。
4. 無 scipy(PYTHONPATH 注入 `raise ModuleNotFoundError` 的 scipy shadow,模擬 Linux absent-module):`5 passed, 2 skipped in 0.27s`,0 warnings — 誠實跳過。
   - 注:初版用 `raise ImportError` shadow 觸發 pytest importorskip deprecation warning;那是 module-exists-but-broken 路徑的 artifact,真實 absent scipy 是 `ModuleNotFoundError`,clean skip 無 warning。已用精確模擬重驗。

## 治理對照

- 硬邊界(max_retries=0 / live_execution_allowed / execution_authority / system_mode):未觸碰。
- 0 migration / 0 Rust / 0 production 代碼改動(estimator 本體未動,per 計劃)。
- 注釋規範:新注釋全中文,英文僅留技術識別符(scipy / default_14d / SKIP/FAIL / 檔名),符合 bilingual-comment-style。
- 跨平台:無硬編碼路徑。
- 多 session dirty tree:主 checkout 零觸碰,全程在 detached worktree 操作。

## 不確定之處

- scipy 版本下限 `>=1.10.0` 為 PM 計劃指定值,Mac 實測 1.17.1;Linux runtime 實際安裝版本未驗(該機本無 scipy,requirements 宣告供未來重現)。
- Linux 實證(trade-core `/usr/bin/python3` 跑出 5 passed 2 skipped)留給 E4 回歸。

## Operator / PM 下一步

1. E2 對抗審查(本報告 + commit `dc5c60d7`)。
2. E4 Linux 回歸:trade-core 上跑該測試檔,期望 5 passed 2 skipped(無 scipy);有 scipy 環境期望 7 passed。
3. E4 過後 PM 統一 commit/merge 決策;worktree `/tmp/hl_scipy_fix` 用畢可由 PM 清理(`git worktree remove`)。
