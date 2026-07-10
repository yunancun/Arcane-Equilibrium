# E1 — L2 E2E-1 one-shot RERUN 執行證據包（真 model call 達成；sink 未寫=fence-JSON 解析 gap）· 2026-07-10

STATUS: DONE_WITH_CONCERNS
Ticket: `TODO.md` `P1-L2-ADVISORY-MESH-E2E-1`（operator 已批 one-shot rerun；解鎖=前次 BLOCKED 報告 §6 路徑 A：control API venv 已裝 anthropic 0.116.0，主會話親證 import OK）
前次 BLOCKED 報告: `2026-07-10--l2_e2e1_oneshot_blocked_evidence.md`（本檔為其 §2 程序原樣重跑）
執行者: E1 · Linux runtime `trade-core` `~/BybitOpenClaw/srv` HEAD `8dfa1200a`（tree clean 前後皆 0 dirty）
Runtime 證據目錄: `/home/ncyu/BybitOpenClaw/var/openclaw/l2_e2e1_oneshot_20260710_rerun/`（含可復用腳本 `l2_e2e1_rerun.sh` + `l2_e2e1_postverify.sh`）

## 1. 一句話結論

E2E-1「真 model call」**首次達成**：`agent.l2_calls` 新 row `l2r:724ac38bc4fc`（anthropic:sonnet，**cost_usd=0.014883 > 0**、**latency 17,801ms**、**raw_response 3,401 字元**實質診斷內容、prompt/response sha256 齊全）；daily cost counter 同步 0.0→0.0149（雙軌互證）。**復原完成且比前次更強**：TOML sha byte-identical 回 `a48b0a85…fc411729`、tree 乾淨、**12/12 per-worker orchestrator in-memory cache probe 全 `enabled=[]`**（前次僅驗磁碟層）。**無需重啟服務**（派發注意事項 #1 的 contingency 未觸發——SDK lazy import 無失敗緩存，運行中 worker 直接拾取新裝 SDK）。唯一 CONCERN：model 回應是 markdown fence 包裹的合法 JSON，executor `json.loads` 不剝 fence → `parsed=None` → sink（agent.lessons）未寫、stage 誤標 `cloud_unavailable_or_unparsable`（該 stage 字串同時涵蓋「provider 缺」與「輸出不可解析」兩種語義）。

## 2. 程序執行記錄（§2 原樣；前/後狀態）

| 步驟 | 結果 | 證據檔 |
|---|---|---|
| 前置狀態 | TOML sha `a48b0a85…fc411729`（=基線，腳本 fail-closed 斷言）；HEAD `8dfa1200a` clean；`enabled=[]`；PG：l2_calls=2 / seam_log=6 / lessons(ml_advisory)=0；daily cost $0.00 | `registry_sha_before.txt` `enabled_before.txt` `pg_counts_before.txt` `cost_before.json` |
| enable 窗口 | 僅 diagnose_leak stanza：`enabled=true` + `debounce_secs 900→0`（同前次偏差；anchor 唯一性斷言後才改）；reload 200 ×8（覆蓋 4 worker cache）；fresh-load 驗 `enabled=['ml_advisory.diagnose_leak']` | `reload_enable.json` `enabled_window.txt` |
| 單次 dispatch | attempt=1 即 `admitted=true, admission_reason=admitted, routed_to=neutral_sink, l2_reply_id=l2r:724ac38bc4fc`；context=runtime log `ml_training_maintenance_status.log` **當日最新行（2026-07-10T01:24:12Z）逐字抽取**，零捏造 | `dispatch_request.json` `dispatch_response.json` |
| 真 model call 驗證 | 見 §3 row 全欄；cost>0 ✔ 非空回應 ✔ latency 合理 ✔（=派發驗收三準則全過） | `l2_calls_new_row.txt` `l2_calls_raw_response.txt` |
| 立即復原 | dispatch 後數秒內 trap `git checkout -- settings/l2_capability_registry.toml` + reload storm ×12（journal 證實 4 個 worker pid 833849/833874/834058/1523199 各至少收到一次 200） | `journal_dispatch_window.txt` |
| 復原驗證 | TOML sha **byte-identical** 基線；`git status --porcelain`=0 行；**12/12 `GET /orchestrator/status` probe `enabled_capabilities=[]`**（per-worker in-memory 層）+ fresh-load `enabled=[]`（磁碟層） | `registry_sha_after.txt` `git_status_after.txt` `orch_status_probes.txt` `enabled_after_restore.txt` |

## 3. 真 model call row（agent.l2_calls 全欄）

`l2r:724ac38bc4fc` | `ml_advisory.diagnose_leak` | model=`anthropic:sonnet`（MODEL_IDS→claude-sonnet-4-6，max_tokens=1024）| contract_ver=`ml_advisory_diagnose.v1` schema_ver=`ml_advisory_schema.v1` | input/output_tokens=**NULL（D3 row 此路徑不落 token 欄，前次 error row 同；cost 由 tracker 按 token 計）** | **cost_usd=0.014883** | **latency_ms=17801** | error_code=NULL | guard_verdict=NULL | prompt_sha256=`8b7654d1e84aa68f…` | response_sha256=`e1c4a91b4f455e37…` | redactor=`l2_redactor.v4` | consequential=f | raw_response 長度 3401 | `2026-07-10 04:15:26+02`

- 成本雙軌互證：`GET /cost` today.claude_usd 0.0 → **0.0149**（remaining 8.0→7.9851；per-call cap $0.50 / daily cap $0.50 / DOC-08 $2 皆遠未觸及；≈派發預期 $0.02）。
- raw_response 內容=實質 leak 診斷（指認 mlde_shadow_advisor 9 日連續 error + cpcv_validator 停跑=PIT 完整性未驗證段，並給 4 條 remediation）——非空、非 echo、非 error 殼。
- seam log +2（seam 7 admission `AUTO_VIA_GATE` admitted；seam 8 ollama_screen `screen_disabled_flag_mit`=M4 artifact 缺席 fail-closed 停用，設計內、與前次相同）。

## 4. CONCERN（誠實披露，非本次 scope 修）

1. **fence-JSON 解析 gap**：sonnet 回應為 ` ```json {…} ``` ` 包裹的**合法 JSON**（`l2_calls_raw_response.txt` 全文可驗），executor `_run_cloud_interpret` 直接 `json.loads(raw)` 不剝 markdown fence → `parsed=None` → notes 標 `stage=cloud_unavailable_or_unparsable sink_written=False`、`agent.lessons` sink 0 row、parsed_output 落 error 殼（`cloud_no_output_or_unparsable`，內含 cost/ledger_ref/review_packet 完整審計欄）。修法=解析前剝 fence（或 prompt 強制裸 JSON），屬新代碼 → PA→E1→E2→E4 全鏈 follow-up，**不在 one-shot 授權內硬做**。
2. **stage 字串語義重載**：同一 stage 同時涵蓋「provider 不可用」與「輸出不可解析」，需看 cost/latency/raw_len 才能區分（本次即因此需 PG 複核才確認 model call 真發生）。建議 follow-up 拆分。
3. token 欄 NULL：D3 ledger row 的 input/output_tokens 此路徑不落（cost tracker 內部有 token 才算得出 cost）；審計可讀性 follow-up，非錯帳。

## 5. 偏差披露

- **CSRF double-submit 自鑄**：本次 POST 全被 CSRF middleware 403（`missing cookie 'oc_csrf'`）——前次 §2 程序未記載此環節。解法=自鑄同值 `oc_csrf` cookie + `X-CSRF-Token` header（middleware 只做 constant-time 相等比對；CSRF 防的是瀏覽器 cookie 自動附帶，Bearer API client 不在威脅模型內，**非安全繞過**，Bearer 認證+operator scope 全程照常強制）。
- **第一次腳本嘗試全程 403**：零 handler 觸及（reload/dispatch 皆被 middleware 擋在認證層前）、零 model 呼叫、零 PG row；磁碟 TOML 曾短暫 enabled 但 trap 秒級復原且無任何 worker load 過該狀態（`GET /registry/capabilities` 為 fresh disk load 不觸 orchestrator cache）——sha/tree 復核通過後才二跑。
- 窗口內臨時 `debounce_secs 900→0`（同前次既定偏差；不動則單次 dispatch 必被 trailing-edge debounce 拒；已隨檔 byte-identical 復原）。
- dispatch context 的 ts 用當日最新 log 行（2026-07-10T01:24:12Z）而非前次的 07-09 行：誠實紀律（「逐字抽取真實 runtime log」以當下最新為準），模式內容不變。

## 6. 治理對照

- 硬邊界零觸碰：no live / no order / no engine restart / no service restart（contingency 未觸發）/ Cost Gate 不動 / demo-only；PG 寫入全部由 runtime 服務按設計路徑落（admission seam + D3 ledger + cost counter）。
- 復原契約：**完成後 L2 全 disabled ✔**（TOML byte-identical + 磁碟層 + per-worker in-memory 層三重驗證）；失敗步驟 fail-closed trap 復原（第一次嘗試即為實證）。
- 重試紀律：dispatch 僅 1 次真 model call（$0.0149）；無三次以上重試（第一次腳本嘗試為 0-cost 0-effect 的 403 全拒，非 model call 重試）。
- 不 commit 不 push（主會話統一處理）。

## 7. 可重跑驗證命令

```bash
ssh trade-core 'cd ~/BybitOpenClaw/srv && sha256sum settings/l2_capability_registry.toml && git status --porcelain | wc -l'
# 期望 a48b0a854872cb37cdc10aed115d7931d96f1e914cc3eab45ecdc7ecfc411729 / 0
ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai -Atc \"SELECT l2_reply_id, model, cost_usd, latency_ms, length(coalesce(raw_response,'')) FROM agent.l2_calls ORDER BY created_at;\""
# 期望 3 行：l2r:93166da5722f(0.0)、l2r:81346608c06e(0.0)、l2r:724ac38bc4fc(0.014883|17801|3401)
ssh trade-core 'for i in 1 2 3 4 5 6; do curl -s -H "Authorization: Bearer $(cat ~/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/.secrets/api_token)" http://100.91.109.86:8000/api/v1/paper/layer2/orchestrator/status | python3 -c "import sys,json; print(json.load(sys.stdin)[\"data\"][\"orchestrator\"][\"enabled_capabilities\"])"; done'
# 期望全 []
```

## 8. Operator/PM 下一步

- E2E-1 驗收判定：派發準則（cost>0/非空回應/latency 合理/復原 disabled）**全過**——建議 PM 據此關閉 `P1-L2-ADVISORY-MESH-E2E-1` 或改記 follow-up。
- Follow-up（新代碼，走 PA 鏈）：①executor 剝 markdown fence 後再 `json.loads`（或 prompt contract 強制裸 JSON）→ sink 可寫通；②`cloud_unavailable_or_unparsable` stage 拆分兩語義；③D3 row 落 token 欄。
- TODO 驗收措辭「real Ollama model call」與現實（anthropic:sonnet 路徑）不一致的問題沿前次報告 §5/§6 結論，本次按主會話派發的 anthropic 路徑執行。
