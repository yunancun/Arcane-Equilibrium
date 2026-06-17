# PHASE 0 AUTH-1 對抗複核修復（generalize mint + panic + contract test）— E1 IMPL

- 日期：2026-06-17 · 角色：E1 · 狀態：IMPL DONE（待 E2）
- 範圍：修 Phase 0 (AUTH-1) 對抗 review confirmed findings；不擴 scope
- 決策依據：review output `tasks/w9lq91pki.output`（confirmedFindings + up03）+ spec §0.1-§0.9
- 不直接 commit（鏈 E1→E2→E4→QA→PM）

## 任務摘要
對抗 review 確認 crypto/token core SOUND（不可弱化）。真議題=token MINT 只接 `patch_risk_config`，
而 Rust chokepoint gate 全 13 LIVE_WRITE_METHODS@engine==live → 合法、已 5-gated 的 operator caller
（live session start/pause/resume、halt-recovery、executor flip、dynamic-risk、strategist promote）被
fail-closed 拒，破 live-session control。**裁定（遵照）=generalize mint，不豁免任何 method**（豁免重開
governor/drawdown/dynamic-risk 的 direct-socket bypass）。三修全綠。

## 修改清單
**RUST（1 檔）** `rust/openclaw_engine/src/ipc_server/live_authz.rs`
- FIX1：TTL 檢查 `(now - ts).abs()` → `(now as i128 - ts as i128).abs() > TTL as i128`（i64::MIN 不再 panic）。
- FIX1 test：`check_live_authz_extreme_ts_no_panic`（i64::MIN/MAX/±1 → TokenExpired 非 panic）。
- FIX2 interop test：`check_live_authz_nonpatch_happy_path`（resume_paper/set_dynamic_risk_enabled
  非-patch mint↔verify ACCEPT；旋鈕竄改→bad_token，analogous to T12）。
- FIX3 contract test：`contract_every_mutator_is_gated_or_explicitly_exempt`（25 個 state-mutating
  match arm 各斷言 in-allowlist XOR explicit-exempt，附 11 條豁免理由；新 mutator 不分類→紅）。

**PYTHON（7 source + 4 test）**
- `app/live_patch_token.py`：新 `hash_target_for(method, params)`（鏡 Rust canonical_hash_for 兩分支：
  patch 類→`params["patch"]`；非 patch→去 token 三欄+engine）；新 `call_params_with_token(method, params)`
  （任意 method 自動選分支鑄 token、回併入三欄的 params）；`_mint_fields` 共用核心。
- `app/live_session_endpoints.py`：新 `_live_call_params_with_token`；start(:194)/resume(:535) 5-gate 後
  鑄 resume_paper token；pause(:482) `_require_live_trade` 後鑄 pause_paper token。
- `app/executor_routes.py`：shadow-toggle engine==live（5-gate/operator-retreat 後）鑄 patch_risk_config token。
- `app/strategist_promote_routes.py`：update_strategy_params target=live（_verify_live_gate 後）鑄 token。
- `app/strategy_write_routes.py`：toggle_dynamic_risk engine==live **補完整 all_five_live_gates_ok**（原僅
  strategy:write scope）後鑄 token；`_sync_strategy_active` 顯式 engine="demo"（非-5-gate 路徑不鑄 live token）。
- `app/risk_view_client.py`：新 `_attach_live_token_if_live`；unhalt_session/reset_drawdown_baseline 的
  engine=="live" 分支鑄 token；clear_consecutive_losses 加 engine 參數；force_governor_* DEFERRED 註記。
- `app/risk_routes.py`：/reset-cooldown 顯式 engine="paper"；/unhalt-session 顯式 engine="paper"。
- `app/ipc_client.py`：latent pause/resume/reset wrapper DEFERRED 註記。
- test：`tests/test_live_authz_caller_retrofit_phase0.py`（新，8 test）；`test_live_patch_token_phase0.py`
  （+6：generalized-mint interop + paper-control engine）；`test_risk_view_client.py`（+1 demo-no-token，
  改 2 補 secret env + 斷言 token）；`test_executor_shadow_toggle_api.py`/`test_strategist_promote_api.py`
  （改 live 測試補 secret env + 斷言 token 三欄）。

## Caller 枚舉表（method → caller file:line → 分類 → 修）
| method | caller | 既有 gate | 分類 | 修 |
|---|---|---|---|---|
| resume_paper | live_session_endpoints.py:194 (start) | all_five_live_gates_ok | live-intent w/5-gate | gate 後鑄 token |
| pause_paper | live_session_endpoints.py:482 (pause) | _require_live_trade(operator+live:trade) | live-intent w/gate | gate 後鑄 token |
| resume_paper | live_session_endpoints.py:535 (resume) | all_five_live_gates_ok | live-intent w/5-gate | gate 後鑄 token |
| resume_paper | risk_view_client.unhalt_session("live")←live_halt_recovery:205 | operator-role（authz 被撤無法 5-gate）| live-recovery | engine==live 鑄 token |
| reset_drawdown_baseline | risk_view_client←live_halt_recovery:198 + /reset-drawdown-baseline | operator-role | live-recovery/operator | engine==live 鑄 token |
| patch_risk_config | executor_routes.py:489 (shadow flip) | _verify_live_gate(5-gate)/retreat=operator | live-intent | engine==live 鑄 token |
| update_strategy_params | strategist_promote_routes.py:696 | _verify_live_gate(5-gate) | live-active promotion | target==live 鑄 token |
| set_dynamic_risk_enabled | strategy_write_routes.py:87 (toggle) | strategy:write only | live-需收緊 | engine==live **補 5-gate** 再鑄 |
| set_strategy_active | strategy_write_routes.py:55 (_sync) | strategy:write, fire-and-forget | paper/demo-intent | 顯式 engine="demo" |
| clear_consecutive_losses | risk_routes.py:559 (/reset-cooldown) | _require_risk_write | paper-control | 顯式 engine="paper" |
| resume_paper | risk_routes.py:945 (/unhalt-session no-arg) | _require_risk_write | paper-control | 顯式 engine="paper" |
| pause_paper/resume_paper | paper_trading_routes.py / strategy_ai_routes.py | — | 已顯式 paper/demo | 無需改（已正確）|
| force_governor_tier_looser/tighter | risk_view_client（無 route caller，grep 親證）| — | DEFERRED | 註記，未 retrofit |
| pause_paper/resume_paper/reset_paper_state | ipc_client 低階 wrapper（無 caller）| — | LATENT | 註記，未 retrofit |
| update_risk_config | ipc_client typed wrapper←demo research calibrator | — | demo 研究工具非 control-plane | 無需改 |
| patch_risk_config | risk_routes update_per_engine_global_config + /config/global live | 5-gate（先前已修）| live-intent | 既有 mint（前批）|

## 非-patch mint↔verify interop 結果
Rust `check_live_authz_nonpatch_happy_path` PASS：resume_paper{engine:live}（hash 對象={}）+
set_dynamic_risk_enabled{engine:live,enabled:true}（hash 對象={"enabled":true}）in-Rust mint→verify ACCEPT；
旋鈕竄改→bad_token。Python `test_call_params_with_token_nonpatch_matches_rust_bind` PASS：對 resume_paper/
set_dynamic_risk_enabled/reset_drawdown_baseline，Python mint 的 token 用 Rust bind-string 同規則重建後
HMAC byte-相符 → 證跨語言互通（與 Rust 對偶）。`hash_target_for` 三分支斷言與 Rust canonical_hash_for 對齊。

## build/test tail + counts
- Rust：`cargo test -p openclaw_engine --lib` = **3936 passed / 0 failed / 1 ignored**（live_authz 15→**20**：
  +extreme_ts +contract +nonpatch_happy_path = +3 顯式新增，原 17 中含前批 15 + 本批；總 lib +4）。
  `cargo build -p openclaw_engine` OK（3 pre-existing warning，非我碼）。
- Python（Mac 3.10.1）：Phase-0 相關 focused 全綠：
  - 核心 10 檔（live_patch_token/risk_routes_live_config_gate/risk_view_client/retrofit/executor_shadow_toggle/
    strategist_promote/executor_shadow_to_live_e2e/phase2_strategy/live_gate_fallback/paper_live_gate）= **216 passed**。
  - risk/live/executor/strategist/strategy/ipc 全家（除 2 個 pre-existing cognitive 收集錯）= **520 passed / 2 skipped**。

## 治理對照（spec §0.9）
- 硬邊界 0 觸碰（live_execution_allowed/max_retries/system_mode/authorization.json）— grep 自證。
- 5-gate 權威留 Python；Rust 只 enforcer。**無 method 被豁免出 LIVE_WRITE_METHODS**（FIX3 contract test 釘死）。
- 原則 #4 強化：toggle_dynamic_risk live 補完整 5-gate（堵「strategy:write scope 寫 live 風險旋鈕」缺口）。
- #6 fail-closed：secret 缺 → Python mint raise → caller 502/500 fail-closed（kill-switch；retrofit test 證 pause 撤 secret→502，IPC 不被呼叫）。
- 無新 migration、無新 flag、無新 singleton。跨平台：0 hardcoded user path（grep 自證）。注釋中文為主（skill 正本）。

## 不確定之處 / 偏差（E2/E3 review 重點）
- **DEVIATION — strategy_write set_strategy_active 分類**：review 決策列其為「live-intent w/5-gate→mint」，
  但 grep 證 activate/pause/stop 路由僅 strategy:write scope（**無 5-gate**），且 sync 為 fire-and-forget
  （Python ORCHESTRATOR fallback）。在缺 5-gate 路徑鑄 live token=弱化授權。最小安全解=顯式 engine="demo"
  （Demo-only 促升 lane，CLAUDE §四；真 live 策略促升走 strategist_promote 的 5-gate+token）。理由已落碼註。
- **DEVIATION — toggle_dynamic_risk**：同理原僅 strategy:write，對 live **補** all_five_live_gates_ok 再鑄
  （非僅鑄 token），否則等於放行無 5-gate 的 live 風險旋鈕寫。
- **halt-recovery 安全 nuance（已遵決策，標註）**：reset_drawdown_baseline("live")+unhalt_session("live")
  經 operator-role gate（非完整 5-gate）——因 live-halt 期間 signed auth 被自動撤銷（五門必失敗），這是
  operator one-button recovery 唯一路徑。決策明列此 caller 為 retrofit 對象，故 engine==live 鑄 token。
  E3 若認為 recovery 也須某種額外門控，可加，但本批遵決策以 operator-role gate 為鑄 token 前提。
- **DEFERRED to Phase 2/3**：(1) force_governor_tier_looser/tighter 無 route caller（grep 親證）→ 註記未來
  retrofit 須 5-gate+token；(2) ipc_client 低階 pause/resume/reset wrapper 無 caller → latent 註記；
  (3) update_strategy_params target_engine:live 已是 active path（非 stub），本批已 retrofit（非 defer）。
- **audit fail-soft（spec §0.4 PARTIAL）**：維持前批 config_reject/config_patch fire-and-forget。

## Operator / E4 下一步
- E2 對抗審查（generalize 分支正確 / 各 caller mint 在 gate 後 / toggle_dynamic_risk 補 5-gate / contract test 完整性 / 無 method 豁免）。
- E4 Linux 實證（OWED）：**LiveDemo 是否填 live_slot**（填→primary_label=live→regression active；否則 latent，今部署未受影響但 true-live 立即受影響）+ 真 engine 跑 non-patch mint↔verify + 真 PG config_reject row + 真 live-session start/pause/resume e2e。
- broad-suite 74 fail 為 pre-existing env（Python 3.10.1≠專案 3.12 / 無 engine socket / 無 PG / program_code path）：
  相關檔 focused run 全綠 + learning_chapter/snapshot 等標準獨立執行亦 fail → 確認非本批引入。
- 部署需設 `OPENCLAW_LIVE_PATCH_SECRET`（獨立檔 chmod 600，≠IPC HMAC secret）；Python 與 Rust 讀同一 env/檔。
