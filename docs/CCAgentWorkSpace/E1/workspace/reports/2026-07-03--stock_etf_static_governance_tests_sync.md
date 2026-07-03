# E1 — stock_etf 結構 static 治理測試 4 紅同步修復 · 2026-07-03

## 任務摘要

E4 2026-07-03 盤點確認 4 條 pre-existing red at clean HEAD（`d0eeafb41`）：Codex 時代
fixture 拆分持續推進，但 CC 側 static 治理測試未同步。本任務診斷先行：先驗證新現狀
逐條滿足治理意圖，才把斷言同步到已 merge 的現狀。**結論：無真回歸，全部為
static 測試 drift。**

## 根因（逐條對應 commit）

| 紅測試 | drift 來源 commit | 內容 |
|---|---|---|
| `test_stock_etf_ipc_fixture_tests_are_split_under_governance_cap` | `e259674fe`（2026-07-02 20:22，test: split stock ETF Rust IPC fixtures） | 父檔 stock_etf.rs 拆出 `core_status_fixtures.rs`（759 行）、status_fixtures.rs 拆出 `phase5_status_fixtures.rs`（401 行），EXPECTED_MODULES 4→6 |
| `test_stock_etf_ipc_fixture_tests_have_no_runtime_material_readers` | `631f5ce3b`（2026-07-01 22:02，引入）+ `e259674fe`/`02e6e342e`（擴充） | 父檔新增 `stock_etf_ipc_status_fixture_assertions_stay_exact` 源碼守衛，以 `include_str!` 編譯期內嵌自身測試樹 6 個源檔做斷言形狀掃描，命中 blanket token |
| `test_stock_etf_tail_status_fixtures_remain_source_only_tests` | `e259674fe` | launch/release_packet/disable_cleanup 三個尾段 status fixture 從 status_fixtures.rs 遷入 phase5_status_fixtures.rs |
| `test_stock_etf_route_fixture_package_preserves_import_surface` | `929593791`（2026-07-02 22:20，feat: expose stock ETF allowlist action buckets） | `__init__.py` 新增 `API_ALLOWLIST_{READ,PAPER_WRITE,DENIED}_ACTIONS` 三個再導出 |

三個 commit 皆為 HEAD ancestor（`git merge-base --is-ancestor` 親證），是已 merge main
的正常演進，各附 Codex 側 guard report 文檔，非未審夾帶。static 測試檔最後一次更新
在 `8ce99bf40`（2026-07-01 05:58），早於全部 drift commit——時間線吻合「拆分推進、
治理測試未同步」。

## 治理意圖驗證（改斷言前逐項親證，全部讀 HEAD 版本 `git show HEAD:`）

1. **拆分上限**：6 模組行數 194/401/434/571/745/759，父檔 128，全部 ≤ MAX_LINES=800；
   父檔含全部 6 個 `mod` 宣告。**MAX_LINES 上限值未動。**
2. **無 runtime material 讀取**：唯一命中=父檔 6 個 `include_str!`，引數全部為
   stock_etf 測試樹自身源檔（parent + 5 個 status 子模組；request_contracts 不在守衛
   範圍屬守衛作者意圖）。編譯期自源掃描非 runtime material 讀取。無 `include_bytes!`；
   子模組對全部三族 token（material/bybit/side-effect）掃描乾淨（原測試 glob 已覆蓋
   新模組且該兩條測試本來就綠）。
3. **source-only**：phase5_status_fixtures.rs 無 ib_insync/ibapi/IBApi/TcpStream/
   tokio::net/reqwest；6 個尾段 method 的 fixture 測試逐一 `git grep` 定位新家。
4. **import surface**：三個新導出為 phase2_payloads.py 靜態 list 常量，
   `from .phase2_payloads import` + `__all__` 雙處齊備；phase2_payloads.py 持續被
   `test_stock_etf_route_payload_fixtures_stay_source_only`（綠）覆蓋。

## 修改清單（僅 2 檔，未碰任何其他檔）

1. `tests/structure/test_stock_etf_ipc_tests_split_static.py`
   - EXPECTED_MODULES 4→6（+core_status_fixtures.rs / +phase5_status_fixtures.rs）；
     cap 測試補兩個新 `mod` 宣告斷言。
   - include_str! 豁免採 **deny-by-default 剝離法**：新增
     `SELF_SOURCE_INCLUDE_RE` + `ALLOWED_SELF_SOURCE_INCLUDES`
     （={"stock_etf.rs"} ∪ {"stock_etf/<EXPECTED_MODULES>"}，隨模組清單自動收斂）與
     `_strip_allowed_self_source_includes`；runtime-material 測試只對父檔剝離
     「字面引數落在允許集合」的 include_str! 後照常全 token 掃描。樹外引數、
     concat! 等非字面變形、子模組的 include_str!、任何 include_bytes! 一律仍咬
     （token 表本身一字未刪）。
   - 尾段 source-only 測試改 per-module 映射：status_fixtures.rs 驗
     account/reconciliation/scorecard，phase5_status_fixtures.rs 驗
     launch/release_packet/disable_cleanup；forbidden token 檢查對兩檔皆施加，
     斷言補 f-string 訊息利診斷。
   - 中文注釋記錄同步日期 + 對應 commit SHA。
2. `tests/structure/test_stock_etf_route_fixtures_split_static.py`
   - EXPECTED_EXPORTS +3（API_ALLOWLIST_DENIED/PAPER_WRITE/READ_ACTIONS），
     附同步注釋（commit 929593791 + source-only 驗證依據）。

## 驗證

- `python3 -m pytest tests/structure/test_stock_etf_ipc_tests_split_static.py tests/structure/test_stock_etf_route_fixtures_split_static.py -q --import-mode=importlib` → **10 passed**（原 4 failed 6 passed）。
- `py_compile` 兩檔 OK；`git diff --check` OK。
- Mutation probe 5 條親證豁免邊界 fail-closed：允許自源→剝離；`../../secrets.toml`
  →保留必咬；`include_str!(concat!(...))`→保留必咬；include_bytes!/include_str!
  仍在禁止 token 表。
- 讀 rust 檔一律 `git show HEAD:`（stock_etf 相關檔 worktree 本就 clean=HEAD；
  唯一髒的 tests/mod.rs 屬並行 IMPL-A，未讀未碰）。

## 治理對照

- 未放寬任何上限值（MAX_LINES=800 不動）；只同步模組/導出清單到已 commit 現狀。
- 未碰 standing_envelope_source_impact_guard 兩檔、rust/ 髒檔、memory/（repo 頂層）、
  TODO.md。無 commit。

## 不確定之處（小決策，自行擇定並註明理由）

- include_str! 豁免用「剝離允許項後照常掃描」而非「從 token 表刪除」或
  「豁免整個父檔」：前者保住 deny-by-default（任何新的樹外/變形 include 仍紅），
  後兩者會開放行邊。允許集合綁 EXPECTED_MODULES 派生，模組清單變動時豁免面自動
  同步，無第二份清單可漂移。
- request_contracts.rs 不在父檔 include_str! 守衛掃描範圍：判定為 Codex 守衛作者
  意圖（該守衛只針對 status blocker 斷言形狀），未替其擴面（不擴 scope）。

## Operator 下一步

E2 審查 → E4 回歸（可直接重跑上述 pytest 指令）→ PM 統一 commit。
