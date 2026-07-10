# E1 報告 — test_snapshot_stable_entrypoint.py test-only 修復（pre-existing 3 測）

日期：2026-07-10（第二輪定稿；E2 第二輪對抗複審 APPROVE_WITH_NITS，nit 已收）
角色：E1（Backend Developer）
狀態：DONE（PASS to E4；未 commit / 未 stage）
派發源：Conductor（PM），承 E4 GUI P0.2 批次 1 回歸 detached-worktree A/B 歸因；中途 E2 RETURN(1 HIGH) 一輪

## 1. 任務摘要

修復 `tests/test_snapshot_stable_entrypoint.py` 的 pre-existing 3 測失敗（clean HEAD 即敗，非 GUI 改動所致）。**test-only**：唯一允許改動檔 = 該測試檔本身；業務邏輯 / middleware / 豁免清單一律不碰。

## 2. 最終修法（與 working tree diff 一致）

只改 `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_snapshot_stable_entrypoint.py`（單檔）：

1. **CSRF double-submit 自鑄對**（根因 1，403）：模組常量 `_CSRF_TOKEN = "test-csrf-token"`；`build_client()` 設 `client.cookies.set("oc_csrf", _CSRF_TOKEN)`；`auth_headers()` 加 `X-CSRF-Token` 同值。`main_legacy.py:330` 無條件掛 `CSRFMiddleware`，POST 需 cookie+header 同值；豁免清單是源碼寫死安全硬邊界，自鑄同值對是合規通過非繞過。middleware 零改動。
2. **原 4 模組 sys.modules 刪除保留 + 單一同調實例就地刷新**（根因 2，order-dependent）：
   ```python
   base = sys.modules["app.main"].base
   base.settings = base.Settings()
   base.STORE = base.JsonStateStore(base.settings.state_file_path)
   base.mark_compile_dirty()
   ```
   機制（E2 第二輪親證為真）：刪 sys.modules 條目後，fresh `main.py` 的 `from . import main_legacy` 走 CPython `_handle_fromlist` **父包屬性捷徑**——`app` 包物件上殘留的舊 `main_legacy` 屬性使刪除形同虛設，拿回的是先行測試檔（如 `test_agents_routes.py` collection 期，當時 `OPENCLAW_API_TOKEN` / `OPENCLAW_STATE_FILE` 未設 → settings 落入隨機 token 與預設 state 檔）留下的同一個舊模組 → 所有請求 401。且 ~40 個 route/ops 模組在模組層 `from . import main_legacy as _base` 凍結指向它，構成**單一同調實例**。正解不是擴大刪除（重則劈成新舊兩半），而是保住同調實例、重建其 env 派生狀態：settings 重讀本測試 env、STORE 重綁本測試 state 檔、殘留編譯快取失效。`main.py:134-136` 的 patch 打在 `JsonStateStore` 類層，新構造的 STORE 天然帶 snapshot-stable 讀寫語義（E2 親證非碰巧通過）；settings 單例住 main_legacy 且「測試依賴 reload 重建 Settings」是套件既有契約（auth.py / main_legacy.py MODULE_NOTE 明言）。

## 3. 演變軌跡（一段帶過）

R1 先按派發方案落地「全清 app.* + `app.db_pool` 豁免」→ 四驗收綠但 E2 tail-sweep 抓到 HIGH：`test_strategist_agent.py` 下游新紅（該檔 collection 期綁定舊 class，全清使字串 patch 落在重生模組、舊 class 呼舊模組函數 → mock 失效）→ 按 RETURN fallback 條款收窄實測：4+state_compiler 出現 401、4+`app` 包出現讀寫分家（rev 不進 / 409）——bisect 過程發現**父包屬性捷徑**才是真機制（原 4 模組刪除本就形同虛設；R1 全清有效只因連 `app` 包一起刪殺掉捷徑，但代價是把同調實例劈半的風險轉嫁到全部 ~40 個凍結 `_base` 的模組）→ 定案「刪除保留 + 就地刷新」。E2 第二輪以 mutation 剝塊 probe 證刷新塊 load-bearing、+state_compiler 為 inert 非劈半（目標檔注釋量詞已按 NIT-2 軟化為「輕則 inert、重則劈半」）。

## 4. 驗收結果（最終輪全 PASS；Mac，pytest 9.0.3 / fastapi 0.136.1；engine socket / PG refused / AgentEventStore stderr 為 Mac 預期噪音）

| 命令 | 結果 |
|---|---|
| `pytest tests/test_snapshot_stable_entrypoint.py -q`（solo） | `3 passed` |
| `pytest tests/test_agents_routes.py tests/test_snapshot_stable_entrypoint.py -q` | `28 passed` |
| `pytest tests/test_ops1_csrf_middleware.py -q` | `19 passed`（middleware 行為未動） |
| `pytest tests/test_runtime_snapshot_bridge.py tests/test_snapshot_stable_entrypoint.py -q` | `1 failed, 5 passed` = bridge 持平其 solo pre-existing 基線（`test_control_route_returns_503_...` 改動前 clean 態 solo 即敗，同 CSRF 家族 403≠503，與本 diff 無關） |
| `pytest tests/test_snapshot_stable_entrypoint.py tests/test_strategist_agent.py -q`（E2 HIGH repro） | `51 passed` |
| 反序 `tests/test_strategist_agent.py tests/test_snapshot_stable_entrypoint.py -q` | `51 passed` |
| E2 tail-sweep collateral gate（target 後 47 檔） | 基線 `2 failed, 555 passed` → target-prepended `2 failed, 558 passed`，FAILED 集完全相同（兩紅均 pre-existing 於 `test_strategist_promote_phase2.py`），零 collateral（尾段由 conductor 代跑完成） |

NIT-2 注釋軟化後複跑確認：solo `3 passed`、agents+target `28 passed`（見本輪回報）。

## 5. 治理對照

- 硬約束零觸碰：max_retries / live_execution_allowed / execution_authority / system_mode 無涉；CSRF 豁免清單（安全硬邊界）未改。
- 業務邏輯零改動：diff 僅目標測試檔；middleware、main、main_legacy、conftest、strategist_agent、db_pool 全原樣。conftest 對 `app.db_pool` 的進程級 prod-DB 封鎖（P0 2026-06-10）不受影響（最終方案完全不做 app.* 面刪除）。
- 注釋規範：新注釋全中文、只講「為什麼」；NIT-2 量詞已軟化。
- 秘密衛生：報告與 repo 文件不含任何真實 token 值（歸因期間 probe 曾在會話輸出印出 `.secrets/api_token` 解析值，未進任何 repo 檔案）。
- 不 commit / 不 stage：工作樹留給 E4/PM；平行 GUI session 的 M 態檔未觸碰。

## 6. 不確定之處 / 殘留

- 就地刷新依賴「settings 單例住 main_legacy、測試可 reload 重建」的既有套件契約（auth.py MODULE_NOTE 明言）；若日後 settings 遷出 main_legacy，此測試需隨動。
- `tests/test_runtime_snapshot_bridge.py::test_control_route_returns_503_...` solo 即敗為同 CSRF 家族 pre-existing，非本任務範圍。

## 7. Operator / PM 下一步

1. E4 回歸（E2 已 PASS to E4）。
2. Follow-up 候選（建議 PM 開票）：bridge 檔 503 測套用同款 CSRF 自鑄對修法（test-only）；`tests/test_api_contract.py` solo 失敗維持既有已知問題原判。
