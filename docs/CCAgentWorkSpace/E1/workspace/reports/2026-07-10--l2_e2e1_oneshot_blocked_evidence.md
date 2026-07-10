# E1 — L2 E2E-1 one-shot 執行證據包（BLOCKED：真 model call 結構性不可達）· 2026-07-10

STATUS: BLOCKED
Ticket: `TODO.md` `P1-L2-ADVISORY-MESH-E2E-1`（operator 已批 one-shot，批文=R3 charter WP-C.2）
執行者: E1（R3 修復包）· Linux runtime `trade-core` `~/BybitOpenClaw/srv` HEAD `8dfa1200a`（tree clean）
Runtime 證據目錄: `/home/ncyu/BybitOpenClaw/var/openclaw/l2_e2e1_oneshot_20260710/`

## 1. 一句話結論

E2E-1 既定程序（記錄前置→enable `ml_advisory.diagnose_leak`→單次 dispatch→驗證→立即復原 disabled→驗證復原）**全程按序執行且 fail-closed 復原完成**，但「真 model call」一步**在當前部署 runtime 結構性不可達**：cascade 在 17ms 內走 `cloud_unavailable_or_unparsable` 錯誤路徑——control API venv **未安裝 anthropic / openai SDK**（三個 cloud provider 全不可用），而唯一物理可用的 local_llm/Ollama 路徑被「executor 硬編 tier=sonnet + 配置校驗死鎖」擋死（見 §5）。**L2 現仍全 disabled（已驗證）**，本次淨效果=1 行誠實的 error-path `agent.l2_calls` row + 2 行 seam log，實際 model 花費 $0.00。

## 2. 程序執行記錄（前/後 flag 狀態、復原確認）

| 步驟 | 結果 | 證據 |
|---|---|---|
| 前置狀態 | registry 3 stanza 全 `enabled=false`；`enabled_before: []`；TOML sha256 `a48b0a85…fc411729`；runtime HEAD `8dfa1200a` clean；PG `agent.l2_calls`=1（歷史 row，見 §4）、`l2_gate_seam_log`=4、`agent.lessons(source='ml_advisory')`=0 | `registry_sha_before.txt` / `enabled_before.txt` / PG query |
| enable（一次性窗口） | 僅 diagnose_leak stanza：`enabled=true` + `debounce_secs 900→0`（900s trailing-edge debounce 使「單次 dispatch」必被 `debounced` 拒——置 0 是讓既定程序「dispatch 一次」可 admit 的最小偏差，窗口後隨檔案復原） | 腳本 python 段（行內容斷言 fail-closed） |
| reload | `POST /registry/reload` 200；`enabled_window: ['ml_advisory.diagnose_leak']` | `reload_enable.json` |
| 單次 dispatch | `POST /ml-advisory/dispatch` 200：`admitted=true, admission_reason=admitted, routed_to=neutral_sink, l2_reply_id=l2r:81346608c06e`；notes=`executor: stage=cloud_unavailable_or_unparsable sink_written=False` + `M4 ollama_screen DISABLED（flag MIT）` | `dispatch_request.json` / `dispatch_response.json` |
| 立即復原 | trap `git checkout -- settings/l2_capability_registry.toml` + reload 200；TOML sha256 復原後 **與前置逐位相同** `a48b0a85…fc411729`；`enabled_after_restore: []` | `reload_restore.json` / `registry_sha_after.txt` |
| 復原驗證（獨立二查） | runtime tree `git status --porcelain` 乾淨；6 次連續 GET `/registry/capabilities`（覆蓋 4 uvicorn worker）全回 `enabled=[]` | 本報告 §7 命令 |

dispatch context = 真實 runtime 資料（`logs/ml_training_maintenance_status.log` 2026-07-09 條目逐字抽取，`mlde_shadow_advisor=error` 連日模式），零捏造指標。

## 3. 本次寫入的 runtime rows（誠實錯誤路徑，非成功證據）

- `agent.l2_calls` 新 row：`l2r:81346608c06e` | `ml_advisory.diagnose_leak` | model=`anthropic:sonnet` | input/output_tokens=NULL | **cost_usd=0.0** | latency_ms=**17** | parsed_output=`{"error":"cloud_no_output_or_unparsable","no_output":true,…}` | raw_response 空 | 2026-07-10 03:26:36+02。17ms+零 token+空回應=**provider 直接不可用**，非真 model 呼叫。
- `learning.l2_gate_seam_log` seam 5：admission pass（`AUTO_VIA_GATE`）；seam 6：`ollama_screen` 記 `no_benchmark_artifact_screen_disabled_flag_mit`（M4 校準 artifact 不存在→screen fail-closed 停用，設計內行為）。
- `agent.lessons` sink：0 新 row（cloud 失敗短路，不寫 sink）。
- 實際成本：**$0.00**（無任何 provider 被真實呼叫；admission/budget 閘均未觸發扣費）。

## 4. 根因（親證）

1. **anthropic SDK 未安裝**：`.venv/bin/python3 -c "import anthropic"` → `ModuleNotFoundError`；journalctl 2026-07-10 03:26:36 `anthropic SDK 未安裝；AnthropicProvider 不可用` + `L2 provider anthropic 不可用（SDK 缺 / key 缺）`（worker 833849）。
2. **openai SDK 同缺** → deepseek/openai provider（fallback_tier2/3）同樣不可用；venv 內僅 httpx。key 本身三家皆已配置（provider store env_present=true）——缺的是 SDK 不是憑證。
3. **歷史同病**：2026-06-10 既存 row `l2r:93166da5722f`（同 capability、cost 0.0、空回應、latency 0）與本次同一簽名 ⇒ 此 venv 的 L2 cloud 呼叫**自部署以來從未真正打通**；TODO row 中「l2_calls=0」的 evidence 描述在本次之前已 stale（實為 1 行 error-path row）。

## 5. 為何不能在本 one-shot 內自行繞通（結構性死鎖）

- 唯一物理可用 provider = `local_llm`（Ollama up，`qwen3.5:9b-q4_K_M`/`27b` 在列，OllamaClient 走 stdlib HTTP 無 SDK 依賴）——**與 TODO 驗收「real Ollama model call」措辭一致**，但：
  - executor `_run_cloud_interpret` 硬編 `base_tier=TIER_SONNET`；provider=local_llm 時映射為 `local:sonnet` → Ollama 無名為 `sonnet` 的模型 → `RuntimeError`（`_provider_complete` 只 catch TimeoutError）→ 例外傳播、**連 ledger row 都不寫**。
  - 唯一能同時指定 (provider, 確切 local tier) 的旋鈕 = `fallback_tier2_provider/model` + `threshold_pct=0`，但 `POST /config` 的 `_validate_layer2_model_config` 會校驗**合併後全部三組 pair**——現存 config 帶 grandfathered 非法對 `default_provider=anthropic + default_model="qwen3.5:9b"`（校驗上線前寫入），故任何觸碰 6 個 provider/model 鍵的更新**必 400**，除非同時「修正」default 對；而修正後**原非法值永遠寫不回去**（校驗擋）⇒ 精確復原經 API 不可能。
  - 繞 API 直改 `layer2_cost_state.json` 需重啟 control API 才能讓 4 個 worker 的 in-memory config 收斂 ⇒ 服務重啟=deploy scope，超出本 one-shot 授權。
- 依 charter 誠實紀律（「任何一步失敗:fail-closed 復原並如實報 BLOCKED」；「用既有已部署 dormant 基建,不需新代碼」前提在 runtime 實況下不成立），**不硬做**，fail-closed 復原後止步。

## 6. 解鎖路徑（供 PM/operator 拍板，均超出本次授權）

任選其一後 E2E-1 可重跑（重跑程序=本報告 §2，腳本可復用）：
- **A（最小）**：control API venv 安裝 `anthropic` SDK（runtime env 變更，需 E3 scope）→ 現配置 anthropic:sonnet 路徑即通，單次成本≈$0.02（sonnet $3/$15 per Mtok，context≈2KB+1024 max tokens，per-call cap $0.50 內）。
- **B（Ollama 對齊 TODO 措辭）**：修復 grandfathered 非法 default 對 + 臨時 pin `fallback_tier2=local_llm/local:qwen3.5:9b-q4_K_M`（留永久 config 變更：default 對無法復原為原非法值；且 4-worker in-memory 收斂需多次 POST 或重啟）→ 真 Ollama 呼叫、成本 $0。
- **C（治本）**：小改 executor 讓 local_llm 路徑用 config 內確切 local tier（新代碼，走 PA→E1→E2→E4 全鏈）。

## 7. 可重跑驗證命令

```bash
# L2 仍 disabled（任意時刻可驗）
ssh trade-core 'cd ~/BybitOpenClaw/srv && sha256sum settings/l2_capability_registry.toml && git status --porcelain | head'
# 期望 sha=a48b0a854872cb37cdc10aed115d7931d96f1e914cc3eab45ecdc7ecfc411729、tree 乾淨
ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai -Atc \"SELECT l2_reply_id, model, cost_usd, latency_ms, created_at FROM agent.l2_calls ORDER BY created_at;\""
# 期望 2 行：l2r:93166da5722f（2026-06-10）與 l2r:81346608c06e（2026-07-10），皆 cost 0.0
ssh trade-core '.venv 路徑見報告 §4；import anthropic / import openai 均 ModuleNotFoundError'
```

## 8. 治理對照

- 硬邊界零觸碰：no live / no order / Cost Gate 不動 / demo-only；PG 僅由 runtime 服務按設計寫入（admission seam + error ledger row=真實審計事件，不刪）。
- 復原契約滿足：L2 三 capability 全 disabled、TOML byte-identical、runtime tree 乾淨——**完成後 L2 仍 disabled** ✔。
- 偏差披露：①窗口內臨時 `debounce_secs 900→0`（已隨檔復原；不動則單次 dispatch 必被 debounce 拒，與「dispatch 一次」的既定程序矛盾）；②TODO 驗收「real Ollama model call」在現 runtime 任何配置下都不可達（§5），非本次操作造成。
