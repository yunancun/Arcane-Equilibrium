# E1 IMPL — P2-RECONCILER-GET-POSITIONS-PAGINATION + P3-110017-D2-AUDIT-REMOVED-SEMANTICS

日期：2026-05-30
角色：E1（後端）
狀態：IMPL DONE，待 BB（交易所面，mandatory）+ E2 + E4

## worktree / branch / base
- worktree：`/tmp/wt-reconciler`
- branch：`fix/reconciler-pagination`
- base：main HEAD `cc6c54d0`（**非** prompt 給的 `eaf9a0d3` — 該 SHA 在此 repo 不存在，`git cat-file -t eaf9a0d3` fatal、fetch 後仍無 object；判定為 stale，改基於 verified main HEAD）
- commits（cc6c54d0..HEAD，3 個）：
  1. `fix(reconciler): P2 get_positions full-scan pagination (xiu fa B)`
  2. `docs(bybit-ref): get_positions limit/cursor pagination semantics [skip ci]`
  3. `fix(reconciler): P3 D2 audit removed_position true semantics (payload annotation)`
- worktree clean（無未 commit）；main checkout HEAD 未動。

## 任務摘要
- **Ticket 1（P2 主）**：`PositionManager::get_positions(Linear, None)` 全量 baseline 掃描原為單頁無 cursor 迴圈（Bybit linear 預設 limit=20），`parse_position_list` 丟棄 `nextPageCursor` → 持倉 > 單頁時 page2+ 漏報 → reconciler Orphan 偵測 + baseline 完整性盲區。修法 B：全量路徑加 limit=200 + cursor 分頁迴圈 + 三重 fail-closed；single-symbol point-query（S-6 gate）保持不動。
- **Ticket 2（P3 次）**：D2 ghost converge dispatch audit 硬傳 `removed_position=true`（baseline 推定），真實 removed 由 handler 端 `converge_exchange_zero_close` 決定（D1 已先收斂則 no-op→false）→ observability 失真。修法 = payload 語意標註（加 `confirmed` + `removed_position_semantics`），非 response_tx。

## 修改清單（4 檔，cc6c54d0..HEAD numstat）
| 檔 | +/- | 內容 |
|---|---|---|
| `rust/openclaw_engine/src/position_manager.rs` | +166/-2 | get_positions 雙路徑（point-query 不動 / 全量分頁迴圈）；新 `parse_position_list_with_cursor`；舊 `parse_position_list` 委派丟 cursor；2 const（FULL_SCAN_PAGE_LIMIT=\"200\" / FULL_SCAN_MAX_PAGES=50）；4 cursor 單測插入既有 `mod tests` |
| `rust/openclaw_engine/src/bybit_rest_client.rs` | +8 | `BybitApiError` 新增 `Other(String)` variant（client 端 fail-closed 錯誤，非交易所 retCode） |
| `rust/openclaw_engine/src/position_reconciler/mod.rs` | +17/-1 | dispatch 路徑 audit call 傳 `confirmed=false` + 中文 rationale |
| `rust/openclaw_engine/src/position_reconciler/orphan_handler.rs` | +18/-2 | `spawn_ghost_converge_audit` 加 `confirmed: bool` 參數 + payload 輸出 `confirmed` / `removed_position_semantics` + doc |
| `docs/references/2026-04-04--bybit_api_reference.md` | doc | get_positions 章節補 limit/cursor 分頁行為 + fail-closed 語意 |

## 關鍵 diff 要點
- **迴圈終止關鍵不變式**：`nextPageCursor` 空字串或缺失 → 正規化 `None`（`.filter(|s| !s.is_empty())`）。防 Bybit 回 `""` 被當有效 cursor 無限請求末頁。
- **三重 fail-closed**（全量路徑，皆拋 `BybitApiError::Other` 不靜默截斷）：
  1. `get_checked` 天然 fail-closed（非 0 retCode → Business；timeout → Transport）。
  2. cursor 與上一頁相同（未推進）→ 拋 Other。
  3. 超 `FULL_SCAN_MAX_PAGES=50` 仍有 cursor → 拋 Other。
- **single-symbol 路徑不動**：`symbol=Some` 仍單次取數、不傳 limit/cursor、忽略回傳 cursor（S-6 D2 收斂 gate 依賴）。
- **簽名兼容**：舊 `parse_position_list` 簽名不變（委派新函數丟 cursor）→ PyO3 `parse_position_list_pub` 零破壞（grep 確認無 Rust 外部 caller）。
- **D2 payload**：`confirmed=false` → `removed_position_semantics="dispatched-not-confirmed"`；下游分析據此區分推定與事實。

## 治理對照
- CLAUDE §四（Bybit timeout/非 0 retCode fail-closed，無隱藏 retry）：✅ 全量分頁沿用 get_checked 既有 fail-closed，未加任何 retry；分頁異常一律 fail-closed 拋錯。
- CLAUDE §八（Bybit-facing 須查 + 更新 reference）：✅ 已查 + 更新 get_positions 章節。
- Root Principle 6（不確定 → 保守）：✅ cursor 不推進 / 超頁數一律拋錯，不猜「已無更多倉」。
- 硬邊界（max_retries / live_execution / system_mode）：未觸碰。
- 注釋：新增/修改處中文（skill：Chinese-first）。
- scope：0 forbidden 檔（notification_failsafe/supervised_live/lcs_fade/stage0r/a2/8c/escalation/single_watcher 全未碰）。

## 驗收
- `cargo build -p openclaw_engine --lib`：PASS（exit 0）。
- `cargo clippy -p openclaw_engine --lib`：PASS，0 warning 引用本次改動檔。
- `cargo build -p openclaw_engine --lib --release`：Finished。
- `cargo test -p openclaw_engine --lib`：**3658 passed / 0 failed / 1 ignored**（含 +4 cursor 單測）。
- Mac engine not running 為預期，未誤判為 runtime fail。

## 不確定之處 / 需 review 注意
1. **新 public API surface**：`BybitApiError::Other(String)` 是契約擴張（非 singleton）。語意是「client 端 fail-closed 非交易所回應」。請 E2/BB 確認無誤用、且 error 觀測/分類管道（ret_code_counter 等）不需為 Other 補處理（目前 Other 只在 client 端 raise，不經 record_for_error，與 Business 路徑分離）。
2. **分頁迴圈無 unit-test 覆蓋**：`PositionManager.client` 是 concrete `Arc<BybitRestClient>`（非 trait），分頁迴圈需 live client 才能整段測；故 cursor 邏輯抽到 pure fn `parse_position_list_with_cursor` 單測（迴圈由其輸出驅動）。**E4 regression 建議**：在 Linux runtime 用實 demo 帳戶（>20 倉場景若可造）或 mock REST 驗全量分頁 end-to-end + 三重 fail-closed 觸發路徑。
3. **history rewrite 說明**：第一輪對錯誤路徑產生的 no-op commit 已隨刪 worktree 清除；第二輪初次 P2 commit 因 `::Other` variant 未先加而 RED，已 soft-reset 重組為當前乾淨 3-commit（enum+code+tests 同 commit，每 commit 可獨立 build）。

## 給 BB 的交易所面 review 重點
- **limit=200 合規**：Bybit linear `/v5/position/list` 單頁最大 200（預設 20），全量取 200 合規且最小往返。
- **cursor double-encode 約束**：cursor token 可能含 `%3A`/`%2C` escapes，原樣回傳不改寫（HTTP client 端負責不 double-encode），與 get_closed_pnl 同約束。
- **fail-closed 完整性**：三重防護（query 失敗 / cursor 不推進 / 超 50 頁）皆拋錯，絕不靜默截斷（截斷本身 = baseline 盲區）。
- **point-query 零行為改變**：S-6 D2 收斂 gate 路徑（symbol=Some）未動。
- **D2 audit 新欄位**：`confirmed` / `removed_position_semantics` 純 observability，不影響收斂決策或安全。

## Operator 下一步
- 派 BB（exchange-facing mandatory）→ E2 → E4 regression（含 Linux runtime 分頁 e2e + fail-closed 觸發驗證）→ QA → PM 統一 commit+push。
- 部署：純 Rust engine 改動，deploy 用 `restart_all.sh --rebuild`。

E1 IMPLEMENTATION DONE: 待 BB + E2 + E4（report path: docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-30--reconciler_pagination_d2_audit_impl.md）
