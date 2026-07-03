# E1 報告 — 環境/import 型測試假紅四項修復（test-only）· 2026-07-03

## 任務摘要

修 E4 2026-07-03 盤點確認的四組 pre-existing 假紅（環境/import 型），目標：Mac 從 repo root 裸跑
`python3 -m pytest` 不再假紅、不削弱斷言、不破壞 Linux 行為。全部 test-only，零生產代碼改動。

## 修改清單（4 檔，全在本票範圍內）

| 檔 | 類型 | 根因分類 | 修法 |
|---|---|---|---|
| `tests/test_spike_cross_lang_rust_binding.py` | M | env（非互動 shell PATH 無 cargo + `~/.cargo/bin/cargo` symlink 鏈斷裂） | 測試側新 `_locate_cargo()` 四層定位 + module-level `skipif`（僅工具真缺席）+ 子行程 PATH 前置 cargo bin dir |
| `helper_scripts/research/tests/test_runtime_governance_ipc_readonly_snapshot.py` | M | test 側 bare import（`from app.ipc_client import` 需 control_api_v1 於 sys.path） | 測試內改 `program_code.` 前綴全限定 import（不動 conftest、不改生產代碼） |
| `helper_scripts/research/tests/test_tail_dislocation_shallow_retune.py` | M | test 側 bare import（`import screen` 需 `tail_dislocation_meanrev/` 於 sys.path） | 測試檔頭補 sys.path（仿 conftest RESEARCH_DIR 模式，scope 限本檔） |
| `tests/misc_tools/__init__.py` | 新增 | pytest prepend import mode 重名 collection 互斥（與 `tests/local_model_tools/test_pure_utils.py` 同 basename） | 目錄級 `__init__.py`（鏡像 `tests/ml_training/__init__.py` 既有解法） |

## 各項根因與關鍵決策

### 1. cargo ×5（`FileNotFoundError: 'cargo'`）

環境事實（本 Mac 親證）：
- `~/.cargo/bin/cargo -> rustup -> /opt/homebrew/bin/rustup-init`（**不存在**，homebrew 已改名 `rustup`）→ symlink 鏈斷裂。
- 真 cargo 在 `~/.rustup/toolchains/stable-aarch64-apple-darwin/bin/cargo`（1.95.0），`rustup which cargo` 可解析。

修法：
- `_locate_cargo()` 順序：`shutil.which("cargo")` → `~/.cargo/bin/cargo`（`is_file()` 跟隨 symlink，斷鏈自動跳過）→ `rustup which cargo`（which 找不到 rustup 再試 `~/.cargo/bin/rustup`）→ `~/.rustup/toolchains/*/bin/cargo` glob 兜底。
- `pytestmark = pytest.mark.skipif(CARGO_BIN is None, reason=...)`，reason 列出全部已檢查位置。
- `_run_rust_fixture` 用 `CARGO_BIN` 絕對路徑 + 子行程 env `PATH` 前置 cargo bin dir——直呼 toolchain cargo 時保證 rustc/rustdoc 同 toolchain 可尋，不影響父行程。
- 未改 timeout=300、未改任何斷言、未改 cargo 命令參數。

證據：
- cargo 存在時真跑：手動 warm-run（cold build 2m50s < 300s timeout，fixture ok，`RUST_FIXTURE_JSON: {"mean": 20, "sigma": 7.905694150420948}`）；修後 pytest `5 passed in 0.89s`（warm cache）。
- skip 分支真實性：fake HOME + 剝離 PATH 環境下 `5 skipped`，reason=`cargo not found: checked PATH, ~/.cargo/bin/cargo, \`rustup which cargo\`, and ~/.rustup/toolchains/*/bin/cargo`。

### 2. runtime_governance（1 假紅：ModuleNotFoundError 被 SUT 包裝成 error reason）

bare import 在**測試檔** `_protocol_error_dispatcher` 內（非 SUT；SUT 本身已用 program_code 全限定 + 自注入 srv root 到 sys.path）。選全限定 import 而非 conftest 補路徑的理由：`app` 是通用頂層名，進 conftest 會對整個 research suite 生效（影響面大）；SUT import 時已保證 `program_code.` 在任何 cwd 可解析，測試只需要 exception class 本體。修後 6/6 綠（無任何 PYTHONPATH workaround）。

### 3. tail_dislocation（collection error 中斷整個 research suite）

`tail_dislocation_meanrev/` 非 package，模組間 bare import。選測試檔頭補路徑而非 conftest 的理由：`screen` 是極通用模組名，進 conftest 全域 sys.path 有污染其他測試 import 解析的風險（repo 內雖僅一個 screen.py，防禦性收窄 scope）。修後 15 passed。

### 4. test_pure_utils 重名 collection 互斥

- 評估四選項：**(a) 兩子目錄各加 `__init__.py` — 否決**：scratchpad temp-repo probe 實證 `tests/local_model_tools/__init__.py` 會令頂層 package 名 `local_model_tools` 進 sys.modules，遮蔽真 `program_code/local_model_tools`，使其 `from local_model_tools.hurst_exponent import ...` 假紅。**(b) pytest.ini addopts `--import-mode=importlib` — 否決**：全 repo pytest 行為改變，E4 memory 已記載 importlib 對 control_api_v1 主套會撞 conftest 致 4 collection error。**(c) 重命名 — 可行但非既有 pattern**。**(d) 僅 `tests/misc_tools/__init__.py` — 採用**：`tests/ml_training/__init__.py` 已是同一問題的既有解法（其 test_pure_utils 用 `program_code.` 全限定 import 無遮蔽問題）；misc_tools 的測試用 bare `bybit_h_stage_common` 等（非 `misc_tools.` 前綴），且 grep 證無人 bare-import `misc_tools`，零遮蔽風險。
- 影響評估：`tests/` 進 sys.path 的條件在 migrations/ml_training `__init__.py` 存在時**本已成立**，本修非首例；pytest.ini 未動，全 repo 行為零變（兩套件前後全量對比見下）。

## 驗證（前後對比，Mac repo root 裸跑）

| Suite | Before | After |
|---|---|---|
| `tests/ -q --import-mode=importlib` | 12 failed / 793 passed / 2 skipped | 1 failed / 804 passed / 2 skipped |
| `tests/ -q`（預設 mode，裸跑） | collection interrupted（test_pure_utils 互斥） | 1 failed / 804 passed / 2 skipped（807 全量收集） |
| `helper_scripts/research/tests/ -q`（裸跑，無 PYTHONPATH） | collection interrupted；排除壞檔=1 failed / 1401 passed / 3 skipped | **1417 passed / 3 skipped / 0 failed**（≥1415 達標） |

- cargo ×5：failed→passed（真跑，非 skip）。
- runtime_governance：6/6 綠。
- failed 名單 diff（importlib 前後）：消失 11 條 = 本票 cargo ×5 + 範圍外 6 條（confirm_modal_a11y / new_vuln_3_4 / prompt_modal / strategy_action ×2 / v072_writer）——後 6 條為**並行 session 期間修復**（git status 佐證：該 6 個測試檔全部 ` M` dirty，非本票改動）。
- 殘留 1 failed = `tests/structure/test_event_consumer_split_static.py`（dispatch.rs 1108>800 行）——範圍外 pre-existing，源自並行 session 髒檔 `rust/.../step_4_5_dispatch.rs`（本票禁碰清單）。
- `py_compile` 4 檔 OK；`git diff --check` rc=0。

## 治理對照

- 未碰硬邊界（max_retries / live_execution_allowed / execution_authority / system_mode）：本票純 test-only，0 生產代碼。
- 未碰共享髒樹禁區：standing_envelope 兩檔、rust/ 髒檔、memory/（除本角色 memory.md）、TODO.md 全未動。
- 不削弱斷言：5 條 cargo 測試斷言原樣；skipif 僅「工具真缺席」且 reason 明確；其餘三項純 import/collection 修復。
- 跨平台：無硬編碼 user path（`Path.home()` / `Path(__file__)` 推算）；Linux 上 cargo 在 PATH → `_locate_cargo()` 第一層直接命中，行為不變。
- 注釋全中文（技術名詞保留英文）。
- 無 commit（等 E2 → E4 → PM 鏈）。

## 不確定之處

1. `tests/ -q` 裸跑殘留的 1 failed（event_consumer split 800 行 guard）依賴並行 session 的 rust 髒檔何時收斂；E4 回歸時若該檔已 commit/修剪，數字會再變。
2. 全裸 `python3 -m pytest`（不帶目錄參數，收集整個 repo 含 control_api_v1 4600+ 主套）不在本票驗證範圍——按任務驗證節的兩條 scoped 命令執行；E4 memory 亦記載 importlib 與 control_api_v1 conftest 互斥，維持現狀。
3. research suite 的 3 skipped 為 pre-existing（前後一致），未動。

## Operator 下一步

- E2 對抗審查本報告 + 4 檔 diff；重點:(a) `_locate_cargo()` 定位順序與 skipif 合法性;(b) `tests/misc_tools/__init__.py` 的 prepend-mode 語意（probe 結論）;(c) 兩個 research 測試的 import scope 決策。
- E4 回歸建議命令：`python3 -m pytest tests/ -q` 與 `python3 -m pytest helper_scripts/research/tests/ -q` 兩條裸跑（Mac）+ Linux 側同命令確認 cargo PATH 正常路徑不退。
