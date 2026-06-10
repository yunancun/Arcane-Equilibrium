# E2 PR Adversarial Review — fix/half-life-test-scipy-skip `dc5c60d7` · 2026-06-10

審查對象:branch `fix/half-life-test-scipy-skip`,commit `dc5c60d74e4770fc698b0e34ad2ee8ead43d8ce2`(origin 已推,base = origin/main `02c80f3b`,恰領先 1 commit)。worktree `/tmp/hl_scipy_fix`。

## 結論

**APPROVE-with-nits(PASS to E4)— 0 個需修 finding;2 個 INFO 建議交 PM 裁量,不退 E1。**

## 改動範圍

```
program_code/learning_engine/tests/test_half_life_estimator.py | +6 / -0
requirements-ml.txt                                            | +1 / -0
```

numstat 純插入零刪除;與預期(2 檔 +7 行)逐位一致,無 scope creep。

## 逐項 verdict(對 PM 7 個審查重點)

### 1. regression-testing-protocol 紅線 — PASS

- **斷言語意一字未動**:`git diff origin/main --numstat` = 6+0 / 1+0,零刪除行 ⇒ 7 個測試的全部斷言 byte-untouched。測試數守恆:base 7 個 `def test_` → HEAD 7 個。
- **importorskip 只產生可見誠實 SKIP,非假綠**:親跑 mode 2(無 scipy shadow)輸出 `5 passed, 2 skipped`,short summary 明示 `SKIPPED [1] ...:104: could not import 'scipy': simulated scipy absence`(:104/:133 兩處)。SKIP 計數獨立顯示,不混入 pass。
- **其餘 5 綠測試零觸碰**(零刪除行即證)。

### 2. importorskip 放置正確性 — PASS

- 置於函數體 docstring 後、首個 statement 位置,與 repo 慣例 `program_code/ml_training/tests/test_onnx_exporter_quantile.py`(:41-43/:100-102/:149-150 同款函數體內 importorskip)一致。
- `import pytest` 既有(test 檔 line 20),無新 import。
- **collection 邊界正確(實證)**:模組頂層 import 僅 numpy/pandas/pytest/estimator(estimator 自身 try/except ImportError 守衛),shadow 模式下 `collected 7 items` 收集成功無 error。`_make_decay_fills` 僅依賴 numpy/pandas — 5 個未守衛測試在無 scipy 下仍可用 fixture(shadow 下 5 passed 實證)。
- 對抗判定:module-level importorskip 反而是錯的(會 skip 全部 7 個);函數級是正確的 surgical 邊界。
- `learning_engine/tests/` 無 conftest.py(僅 `__init__.py`),無 fixture/collection 階段坑。

### 3. requirements-ml.txt — PASS

- **Floor 合理**:scikit-learn>=1.5.0 自身 scipy 下限 ≈1.6,`scipy>=1.10.0` 更嚴格無衝突;runtime venv 實測 1.17.1 滿足。實際用到的 API(`scipy.optimize.curve_fit`、`stats.f.cdf`、`stats.skew/kurtosis/norm.cdf/chi2.cdf`)全是遠古 API,1.10.0 floor 安全。py3.12 下 pip 自動 resolve ≥1.11.x wheel,floor 不造成安裝問題。
- **Column 對齊**:awk 驗證全檔 13 行 `#` 全在 col 26,新行一致。
- **注釋合規**:中文為主 + 精確識別符(half_life_estimator/_regime_math/sklearn),符合 bilingual-comment-style;與既有 line 12 skl2onnx「transitive declared for reproducibility」先例同構。
- **消費者無破壞**:`mac_bootstrap.sh:301` 純 `pip install -r`(加行 benign);`.github/` 零命中(無 CI 消費者);`docs/KNOWN_ISSUES.md` / `cross_platform_redeploy_dependencies.md` 是散文指針(「權威來源=requirements-ml.txt」)非逐包 inventory,無 stale-by-one。pip 對 inline comment + UTF-8 中文無解析問題(檔頭 line 2 既有中文)。

### 4. 覆蓋面盲區(E2 獨立判斷)— surgical scope 取捨正確;1 條 INFO 建議

- 獨立分析:`test_default_fallback_small_sample` 的 n-gate 在任何 scipy 相關代碼**之前** fire,雙模式行使同一路徑,無歧義。`test_default_fallback_high_p_value` / `test_module_level_shortcut` / `test_half_life_clamped_within_bounds` 在無 scipy 下走降級短路但**仍驗證其公開契約**(純噪音→default_14d / shortcut==direct / clamp 邊界)— 而 trade-core 上降級路徑**就是該解譯器的真實生產路徑**,讓這 3 測試在 scipy-less 環境繼續跑反而保留了該環境的行為驗證;加守衛會**減少**覆蓋。不擴守衛是正確取捨,非偷懶。
- **INFO-1(建議,不阻塞)**:`test_default_fallback_high_p_value` 的 docstring 意圖(「兩擬合皆未通過 p-value 門檻」)只在有 scipy 時被行使;無 scipy 時綠在短路路徑 = 綠但行使路徑不同的未明示細節。建議檔頭加一行注釋明示雙模式語意(「test 1-2 = fit-path-only 需 scipy 否則 skip;test 3-7 雙模式皆跑,無 scipy 時驗證的是降級契約」)。一行注釋,PM 裁量是否值得多一輪。

### 5. commit message 誠實性 — PASS(零 overclaim)

行為矩陣**全部親跑重證,非採信自報**:
- 「有 scipy:7 passed」→ 親跑 `venvs/mac_dev`(py3.12 + scipy 1.17.1):**7 passed** ✓
- 「無 scipy:5 passed 2 skipped」→ 親建 PYTHONPATH ModuleNotFoundError shadow:**5 passed 2 skipped**,skip 恰為兩個 fit-path 測試 ✓
- 「斷言語意零改動」→ numstat 零刪除 + 測試數 7→7 守恆 ✓
- RCA 宣稱「與日期/seed/容差無關」→ 讀碼證實:fixture seed 固定(42/123)、base_ts 固定 2026-04-01、estimator `t_days = ts_seconds - ts_seconds[0]`(half_life_estimator.py:371)無 wall-clock ✓
- 「比照 test_onnx_exporter_quantile 慣例」→ 親讀證實同款 ✓
- nano-note:「函數體首行加 pytest.importorskip」實際是 docstring + 2 行注釋後的首個 statement — 描述合理(注釋非 statement),非 finding。

### 6. 工作樹衛生 — PASS

- `git -C /Users/ncyu/Projects/TradeBot/srv status --porcelain -- program_code/learning_engine/ requirements-ml.txt` → **空輸出**,主 checkout 兩受審路徑零觸碰。
- 狀態註記(非本 PR 問題):主 checkout HEAD `f0bffcab` 在本地 lineage(含 SUPERSEDED L2 feature 譜系 `1f34653c` + 本地 agents-revamp commit),與 origin/main `02c80f3b` 分歧 — 已知 multi-session 狀態,照 §5c 不碰不 revert,僅記錄。
- `/tmp/hl_scipy_fix` worktree 在 review 前、mutation probe 後均 `status --porcelain` 空(probe 用 untracked 副本,跑完即刪,親驗清潔)。

### 7. 攻擊面自由發揮 — 無 E1 隱藏問題;1 條 INFO 觀察

- **Production caller proof(§3.10 式)**:`grep -rn "half_life_estimator|HalfLifeEstimator|estimate_half_life" program_code helper_scripts`(排除自身與測試)→ 唯一命中 `embargo_validator.py:160` 為訊息字串字面,**0 production import caller**。⇒ (a) trade-core 降級今日零生產影響;(b) test-only 修復範圍正確;(c) requirements 宣告屬 reproducibility 衛生非生產 hotfix。與 MODULE_NOTE「current IMPL ships fixture-driven」一致。
- **mutation bite(對抗核心證據)**:取 base 版(02c80f3b)test 檔在 shadow 下跑 → **恰 2 FAILED**:`assert 'default_14d' == 'pnl_decay'` / `'sharpe_decay'`,**精準重現 trade-core 2F/5P 症狀** ⇒ RCA 為真因非症狀遮蓋;守衛非 vacuous。
- `_regime_math.py` 同款守衛宣稱屬實,且其 scipy 呼叫(psr_zero 的 skew/kurtosis/norm.cdf、kupiec 的 chi2.cdf)全在 `_SCIPY_AVAILABLE` 分支後,有 math.erf/erfc fallback — 無 latent 未守衛呼叫。
- program_code 全部 `test_*.py` 中引用 scipy 的**只有本檔** ⇒ trade-core scipy-less 解譯器無其他隱藏 scipy 測試破面。
- importorskip 僅捕 ImportError 族;scipy 裝壞拋其他例外仍 fail-loud,無吞錯。
- **INFO-2(轉 PM/operator,非 E1 缺陷)**:requirements-ml.txt 宣告是 necessary-not-sufficient — 無任何 CI/cron 會把它裝進 trade-core `/usr/bin/python3`(mac_bootstrap 僅 Mac venv)。今日 0 production caller 故無影響;未來 half_life fit 路徑真要在 trade-core 活化時,須 operator 在對應解譯器/venv 實裝 scipy,屆時這行宣告才落地。

## 8 條 reviewer checklist

| Item | 狀態 |
|---|---|
| 改動範圍與方案一致 | PASS(2 檔 +7,零 creep) |
| 無 except:pass / 吞異常 | PASS(diff 無任何 except) |
| 日誌 %s 格式 | N/A(diff 無日誌) |
| 新 API 端點 operator gate | N/A |
| except HTTPException 順序 | N/A |
| detail=str(e) | N/A |
| asyncio blocking lock | N/A |
| 私有屬性穿透 | PASS(無) |

## OpenClaw §3 checklist

| Item | 狀態 |
|---|---|
| §3.1 跨平台硬編路徑 | PASS(diff 零命中) |
| §3.2 注釋中文為主 | PASS(新注釋全中文+識別符) |
| §3.3-3.5 Rust/IPC/Migration | N/A(未觸) |
| §3.8 檔案大小 | PASS(test 檔 229 行 / requirements 17 行) |
| §3.10 caller proof | PASS(0 production caller,grep 附上) |

## §5 multi-session race check

| 條目 | 結果 |
|---|---|
| 5a fetch + sibling window | PASS:origin/main=`02c80f3b`=branch base,branch 恰 +1 commit,遠端 SHA 與本地一致;主 checkout lineage 分歧為已知他 session 狀態(僅記錄) |
| 5b status clean | PASS:worktree porcelain 空 |
| 5c unknown WIP | PASS:worktree 無外來改動;主 checkout 已知狀態未碰 |
| 5d sign-off path clean | N/A(本報告 Write-only 勿 commit,PM 收口) |
| 5e review 期間 sibling push | PASS:收尾 re-fetch origin/main 仍 `02c80f3b`,branch 未動 |

## Findings 總表

| 嚴重性 | 位置 | 描述 | 建議 |
|---|---|---|---|
| INFO-1 | test_half_life_estimator.py 檔頭 | 5 個未守衛測試在無 scipy 環境綠在降級路徑(契約仍被驗證,取捨正確),雙模式語意未明示 | 檔頭加 1 行注釋明示;PM 裁量,不要求修復輪 |
| INFO-2 | requirements-ml.txt / 部署面 | scipy 宣告 necessary-not-sufficient:無自動管道裝進 trade-core system python;今日 0 production caller 無影響 | 未來 fit 路徑活化時 operator 實裝;記錄即可 |

無 CRITICAL / HIGH / MEDIUM / LOW。E2 未直接修任何 typo/lint(無可修項)。

## 證據摘要(全部親跑)

1. Mode 1(scipy 1.17.1):`7 passed in 0.83s`
2. Mode 2(PYTHONPATH shadow ModuleNotFoundError):`5 passed, 2 skipped`,SKIPPED 行明示 :104/:133 + 理由
3. Mode 3(base 版 + shadow):`2 failed`,`assert 'default_14d' == 'pnl_decay'` / `'sharpe_decay'` — 重現 trade-core 症狀,守衛有 bite
4. probe 清理後 `git status --porcelain` 空(兩次驗證)

— E2,2026-06-10
