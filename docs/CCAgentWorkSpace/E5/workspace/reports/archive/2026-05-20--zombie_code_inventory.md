# P2-STRUCT-2 — Zombie / Deprecated Code Inventory

**日期**：2026-05-20
**Agent**：E5 (Optimization Engineer)
**任務**：OpenClaw 治理 backlog P2-STRUCT-2 — read-only zombie/deprecated 代碼盤點
**範圍**：`program_code/`（Python source，task 文中「openclaw/strategies/risk/learning/api/gui」實際分布的容器目錄）+ `helper_scripts/` + `rust/openclaw_engine/src/` + `rust/openclaw_core/src/` + `tests/` + `rust/*/tests/`
**輸出**：列示候選；**不刪不改業務代碼**；建議處理由 PA 排入 Sprint。
**邊界注意**：task description 列「srv/openclaw/、srv/strategies/、srv/risk/、srv/learning/、srv/api/、srv/gui/」這些 top-level dir 在當前 repo **不存在**——實際 Python source 集中於 `program_code/`，本報告以 repo 真實結構執行盤點。

---

## 0. 範圍 baseline

- Python `.py` + Rust `.rs` source 檔（exclude `__pycache__` / `.pytest_cache` / `target/` / `.claude/worktrees/`）：**1226 files**
- 帶 deprecation/zombie marker（`DEPRECATED|FIXME|XXX|_legacy|_DEAD|_unused|@deprecated`）：**185 files**
- 當前 git HEAD：`232c3aff` (main branch dirty / 3 commits ahead of origin — operator WIP 含 v4 governance + 5 ADR + AMD)
- ADR-0015 sunset 7 module 已於 commit `449f628b` (2026-05-18) 全部退役驗證 0 殘留 import。

---

## 1. 無 caller public function

| file:line | symbol | last-touched / 證據 | 風險評估 | 建議處理 |
|---|---|---|---|---|
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub.py:302` | `GovernanceHub.check_learning_tier_capability(capability)` | RC-11 closed 2026-04-04（archive: `2026-04-12--changelog_archive_pre_0408.md:524`）；55+ 天前；grep 全 repo 0 prod caller | **Low**：方法本身 fail-closed return True；DeprecationWarning fires；不影響交易 | 已 `@deprecated`-decorated；2 sprint 後若無 caller 出現可刪。文檔保留即可 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub.py:366` | `GovernanceHub.is_enabled()` | RC-11；governance_hub.py:54 文檔自證「No external callers」 | **Low**：同上 | 已標 deprecated；`is_globally_enabled()` 取代；可隨下次 governance_hub refactor 刪除 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub.py:~525` | `GovernanceHub.get_risk_level()` (hub method, not route) | RC-11；governance_hub.py:525 文檔「No external callers. Rust GovernanceCore provides risk level」 | **Low**：governance_routes.py:801 `get_risk_level()` 是 FastAPI route 不同名同函；hub method 0 caller | 待刪。注意：不要誤刪 `governance_routes.py:801` (active endpoint) |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub.py:~556` | `GovernanceHub.check_risk_and_act()` | RC-11；governance_hub.py:556「No callers found」 | **Low** | 同上 — 可隨下 sprint 移除 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_cost_recording.py:355` | `record_ollama_call()` (module-level) | DEPRECATED；`layer2_cost_tracker.py:480` 仍透過 `_recording_sibling.record_ollama_call()` delegate 呼叫，但實際被呼叫的進入點是 `Layer2CostTracker.record_ollama_call` (delegator) | **Low**：delegator chain 仍 wire；ollama 走 free path | sibling delegator 也標 `@deprecated`；待全鏈 `record_call(provider='ollama', ...)` 接管後一次性刪除 |
| `rust/openclaw_core/src/risk/price_tracker.rs:138` | `PriceTracker::compute_atr_pct(symbol)` | DEPRECATED 2026-04-22 (P0-13)；`rust/openclaw_engine/src/` 全 grep 0 caller；自身 module unit tests 仍引（line 410/437/443/453） | **Medium**：注釋警告強烈（「100-1000x scale errors」）；但 active module 內 single dead method，意外被新代碼 import 危險 | (a) 加 `#[deprecated(since="0.x", note="...")]` attribute 觸發 build-time warn；(b) 同 module `compute_roc` / `worst_drop_for_held` 仍 active，**整 file 不刪**；(c) unit tests 改為「assert callable returns None」即可 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/state_models.py:392` | `AskPacketSnapshot.deprecation_notice: str \| None` field + `consultation_status` `"stub_pending_h_chain_integration"` | DEPRECATED notice field；class 本身被 `phase2_strategy_routes.py:80` + `strategy_ai_routes.py:82` import (`get_ai_consultation_status`) | **Low**：field 為 optional `None`；不影響 wire-format | active；但 `deprecation_notice` 字串目前無 producer 寫入。可考慮 P3 hygiene 移除 |

---

## 2. 過期 TODO / DEPRECATED（>30 天，相關 ticket 已 closed）

| file:line | marker | linked ticket | ticket 狀態 | 建議處理 |
|---|---|---|---|---|
| `rust/openclaw_engine/src/risk_checks.rs:416-430` | `// DEPRECATED (DUAL-TRACK-EXIT-1 Track P T3): legacy COST EDGE gate block` | DUAL-TRACK-EXIT-1 Track P (v2 SWAP `306993e` 2026-04-22) | **Closed** ~30 天前；memory `project_track_p_runtime_live.md` 證 V2 SWAP `306993e` 已 land；v1 8 直測整塊退役 | 註解 block 14 行可刪；保留「PHYS-LOCK above strictly more conservative」單行說明指向 spec doc 即可 |
| `rust/openclaw_engine/src/database/trading_writer.rs:480,640,784` | `// DEPRECATED: is_paper derived from engine_mode (compat with Grafana).` | Grafana 相容性 compat 注釋；無 ticket | **N/A** — Grafana 仍可能讀；engine_mode='paper' 路徑 active | 保留（永久 compat layer）；建議改寫為 `// COMPAT:` 取代 `DEPRECATED:` 避免誤導 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_write_routes.py:117,147,177,209,226` | `# TODO(R-IPC): Migrate to Rust command channel when available` | R-IPC（Rust IPC channel）；archive 中 R-07 Rust IPC 已 land | **Partial** — Rust IPC channel 已存在（lease bridge + ws_status 等）；migration scope 為 strategy commands | 5 處 TODO 應綁定具體 ticket（CC-CONTROL-1 之類）；目前 placeholder + 410 DEPRECATED endpoints 並存，治理意圖模糊 |
| `program_code/local_model_tools/strategy_auto_deployer.py:65` | `# DEPRECATED 2026-04-10: scan-driven deployment moved to Rust scanner.` | DEAD-PY-3 series；archive：`docs/archive/2026-04-23 DEDUP-PY-RUST` | **Closed** ~40 天前 | 全 file 是 STUB by design（保 API surface）；marker 仍正確 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_agent.py:629` | `# ── Intent Collection (DEPRECATED) / Intent 收集（已廢棄）──` + line 631 `collect_pending_intents()` | TD-2（MessageBus routing）；archive 中已 land | **Closed** | 方法 stub 仍 return `[]` + DeprecationWarning；test 仍引（test_strategist_agent.py:1458,1512 / test_batch7_conductor_strategist.py:458,468）；可隨 strategist_agent 下次 split 刪除 |
| `helper_scripts/canary/replay_runner.py:212` | `[DEPRECATED] Python shadow pipeline removed — strategies migrated to Rust.` | DEAD-PY-3 | **Closed** | active stub by design |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_write_routes.py:216` | `[DEPRECATED] Python strategy creation removed` (`create_strategy` route 410) | DEAD-PY-3 | **Closed** | active 410 endpoint by design；不刪 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/grafana_data_writer.py:23` | `DEPRECATED writes (now handled by Rust engine): market_tickers → Rust market_writer; trade_executions → Rust trading_writer` | Wave A/B Rust migration | **Closed** | active；該 module 仍寫 paper_pnl_snapshots + system_health（Rust 不覆蓋的 2 表） |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub.py:44-62` | `PARTIALLY DEPRECATED (R-07 + RC-11)` 大 comment block | R-07 + RC-11 | **Both closed** | block 已過期 21+ 天；可 trim 為單行「see ADR-0015 closure addendum」 |

---

## 3. 命名模式 zombie

| file path | pattern | 風險評估 | 建議處理 |
|---|---|---|---|
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main_legacy.py` | `_legacy*` filename | **Low** — active core (settings singleton + 5 register_*_routes import + 7+ route file 直接 `from . import main_legacy as base`)；自評「Wave A-D 拆分後保 ~420 行 backward-compat」 | 命名 misleading；建議重命名 `main_core_compat.py` 或 `main_singletons.py`（需 cross-repo grep + test rename 一同 land） |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/auth_legacy_routes.py` | `_legacy_routes` | Active：main_legacy.py:546 `register_auth_legacy_routes` import + register | 同上 — 命名 misleading；3 auth routes 全 active；建議和 main_legacy 同批 rename |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/gui_legacy_routes.py` | 同上 | Active：5 GUI / HTML routes (`/login`, `/`, `/gui`, `/console`, `/trading`) | 同上 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/system_legacy_routes.py` | 同上 | Active：13 system / health read routes 包含 `/api/v1/healthz` | 同上 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/learning_legacy_routes.py` | 同上 | Active：19 learning / PnL routes | 同上 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/control_legacy_routes.py` | 同上 | Active：15 control / operator-write routes | 同上 |

**結論**：6 個 `_legacy*` 檔名全部是 active 業務 code（共 ~55 routes），命名繼承自 Wave A-D 重構過渡期。**結構上不是 zombie**，但命名 misleading 對新 sub-agent / RAG 容易誤導。建議 PA 排「rename batch」工作組統一處理。

無其他 `_old_` / `*_DEAD` / `*_unused` filename 命中（grep 0 hit 除測試 mock `_unused` 變數）。

---

## 4. ADR 已 sunset 但代碼還在

| 模組 | sunset 來源 ADR | 當前 file 路徑 | 觀察期狀態 | 建議處理 |
|---|---|---|---|---|
| `attention.rs` | ADR-0015 §Closure Addendum (2026-05-19) | **已移除** commit `449f628b` 2026-05-18 | Closed | 無 |
| `attribution.rs` | 同上 | **已移除** `449f628b` | Closed | 無 |
| `cognitive.rs` | 同上 | **已移除** `449f628b` | Closed | 無 |
| `dream.rs` | 同上 | **已移除** `449f628b` | Closed | 無 |
| `message_bus.rs` | 同上 | **已移除** `449f628b` | Closed | 無 |
| `order_match.rs` | 同上 | **已移除** `449f628b` | Closed | 無 |
| `opportunity.rs` (openclaw_core) | 同上 | **已移除** `449f628b` | Closed | 無 |
| `scanner/opportunity.rs` (engine) | **非 ADR-0015 scope** | `rust/openclaw_engine/src/scanner/opportunity.rs` active | **Active** — 被 `scanner/runner.rs:28` + `scanner/scorer.rs:20` import | 不刪；單純命名與 retired core module 重疊；ADR-0015 closure addendum §「retirement set is closed」適用 |

**ADR-0015 殘留量化**：grep `use openclaw_core::(attention|attribution|cognitive|dream|message_bus|order_match|opportunity)` 全 repo 0 hit。**完全乾淨**。

**ARCH-RC1 1C-1 risk refactor**（commit `2007b677`）2 個 `openclaw_core::risk/{checks,config}.rs` 已 refactor 出去；ADR closure addendum §3 已記述。

---

## 5. 死 schema migration 但 Python/Rust 還寫

| schema 名 | drop migration | grep callsite | 嚴重度 | 建議處理 |
|---|---|---|---|---|
| `observability.scorer_predictions` | V069 (2026-04-25) 已 drop | `helper_scripts/db/fresh_start_reset.py:136` 仍列入 `WIPE_TABLES`（dev reset script） | **Low**：file 自評「對缺表已走 SKIPPED missing table 分支，無 prod 影響」；V096 同樣 P3 hygiene follow-up 留尾 | 同 V096 留尾——下次 fresh_start_reset.py 改動時順手清；無 prod runtime 影響 |
| `learning.rl_transitions` | V096 (2026-05-18) 已 drop | `helper_scripts/db/fresh_start_reset.py:121` 仍列 `WIPE_TABLES` (自帶 inline 注釋「V096 dropped; SKIPPED at runtime」) | **Low**：自評為 P3 hygiene；2026-05-18 cleanup sprint 留尾 | 隨下次 reset script touch 移除 |
| `learning.symbol_clusters` | V096 (2026-05-18) 已 drop | `helper_scripts/db/fresh_start_reset.py:126` 同上 | **Low** | 同上 |

**Prod source 殘留 = 0**。`program_code/` + `rust/` 全 grep 對 `scorer_predictions` / `rl_transitions` / `symbol_clusters` 的 writer/reader **0 命中**。所有殘留集中在：
- `helper_scripts/db/fresh_start_reset.py`（dev reset 工具，runtime 無影響）
- `tests/migrations/V*` migration regression test（by design 驗 drop SQL，**不刪**）
- `tests/helper_scripts/test_fresh_start_reset_missing_tables.py`（驗 SKIPPED missing table 分支）

**V069 task description 寫「6 個 schema 名」與實際 migration 內容不符**。V069 只 drop 1 個表（`observability.scorer_predictions`），V096 drop 2 個（`learning.rl_transitions` + `learning.symbol_clusters`），合計 3 個 dead schema 已被 migration 退役且 prod source 殘留 0。task description 該數字可能是混淆 V068（reclassification guard）/ V070 / V071 多份 migration 的累加，但目前實際 DROP statement 在 V069 + V096 = 3 個表。

---

## 6. 統計總結

| 類別 | 候選數 | 高風險 | 中風險 | 低風險 |
|---|---|---|---|---|
| 1. 無 caller public function | 7 | 0 | 1 (`compute_atr_pct`) | 6 |
| 2. 過期 TODO/DEPRECATED | 9 | 0 | 1 (R-IPC scope 模糊) | 8 |
| 3. 命名模式 zombie | 6 | 0 | 6 (rename batch) | 0 |
| 4. ADR-0015 sunset 殘留 | 0 (已 commit `449f628b`) | 0 | 0 | 0 |
| 5. 死 schema migration writer | 3 (fresh_start_reset 留尾) | 0 | 0 | 3 |
| **合計** | **25** | **0** | **8** | **17** |

---

## 7. 排序給 PA 的優先建議

**S-Tier（建議排入下個 Sprint cleanup 工作組）**：
1. `governance_hub.py` 4 個 RC-11 dead methods（`check_learning_tier_capability` / `is_enabled` / `get_risk_level` / `check_risk_and_act`）— RC-11 closed 55+ 天，可直接刪；保留 `trigger_risk_upgrade` (still called by `guardian_agent.py:1327`)
2. `risk_checks.rs:416-430` DUAL-TRACK-EXIT-1 DEPRECATED comment block 14 行 — V2 SWAP 30+ 天 closed

**A-Tier（中期 P3 hygiene）**：
3. 6 個 `*_legacy*.py` 重命名批次（含所有 import / test 更新）— 純命名改善，無語意改變
4. `helper_scripts/db/fresh_start_reset.py` 3 個 V069/V096 已 drop 表的 `WIPE_TABLES` entry 清除
5. `compute_atr_pct` 加 `#[deprecated(...)]` attribute 觸發 build warn（保留 fn，不刪 module）

**B-Tier（隨機 touch 順手）**：
6. `trading_writer.rs` 3 處 `// DEPRECATED: is_paper` → 改寫為 `// COMPAT:`（避免誤導）
7. `governance_hub.py:44-62` 大 comment block trim 為單行 ADR pointer
8. `strategy_write_routes.py` 5 處 `TODO(R-IPC)` 綁定具體 ticket（CC-CONTROL-1 之類）

---

## 8. E5 不做的事 — push back

- 全部 25 項僅是**候選**；E5 角色為 read-mostly + 報告，**不刪業務代碼**。
- ADR-0015 closure addendum 既為治理權威，**ADR-0015 sunset scope 已 closed**（449f628b），E5 不會嘗試擴大 sunset 集（不存在「missing 2 modules」工作）。
- `scanner/opportunity.rs` 雖與 retired `openclaw_core::opportunity.rs` 同名，但屬不同 crate 不同設計範疇；不算 zombie。
- 6 個 `*_legacy*.py` 雖命名 misleading，**結構上不是死代碼**；PA 決定是否 rename 即可。
- task description 中「srv/openclaw/、srv/strategies/...」top-level 目錄不存在；報告以 repo 實際結構 (`program_code/` 為 Python source 容器) 執行；如 task 範圍另有 intent，請 push back 提供新範圍邊界。
- task description 「V069 dropped 後是否還有 writer/reader 殘留（grep 6 個 schema 名）」與實際 V069 內容（只 drop 1 表）不一致；推測 task description 把 V069 + V068 reclassification guard + V096 multiple drops 混為「6 個」。本報告以實際 SQL DROP statement 為準（3 個表）。

---

## 9. Evidence index

- ADR-0015 closure addendum: `docs/adr/0015-openclaw-control-plane-repositioning.md:37-64`
- RC-11 closure: `docs/archive/2026-04-12--changelog_archive_pre_0408.md:524`
- DUAL-TRACK-EXIT-1 V2 SWAP: memory `project_track_p_runtime_live.md` + commit `306993e`
- DEAD-PY-3 series: `docs/archive/2026-04-23` DEDUP-PY-RUST batch
- V069 migration: `sql/migrations/V069__drop_dead_observability_scorer_predictions.sql`
- V096 migration: `sql/migrations/V096__drop_dead_learning_tables.sql`
- governance_hub @deprecated decorators: `program_code/.../app/governance_hub.py:296,362,518,548,587`
- fresh_start_reset.py residue: `helper_scripts/db/fresh_start_reset.py:121,126,136`
