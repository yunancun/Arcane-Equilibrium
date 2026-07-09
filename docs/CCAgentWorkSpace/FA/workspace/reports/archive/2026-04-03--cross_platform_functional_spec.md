# XP-1~4 Cross-Platform Migration — Functional Specification & Acceptance Criteria
# 跨平台遷移功能規格與驗收標準

> FA (Functional Auditor) 出品 · 2026-04-03
> 基準：3703 passed / 24 failed / 17 errors (pre-existing)

---

## 一、代碼級現狀摘要（掃描結果）

### 1.1 硬編碼路徑分佈

| 類別 | 含 `/home/ncyu` 的 .py 文件數 | 總出現次數 | 說明 |
|------|-----|------|------|
| **Legacy 腳本**（A-K 章, 已不在 Live 路徑上） | ~150 | ~430 | `bybit_decision_lease/`、`bybit_event_driven/`、`bybit_business_events/`、`readonly_observer_pipeline/`、`io_and_persistence/`、`misc_tools/`、`risk_control/`、`ai_agents/` |
| **Live 運行時**（`control_api_v1/app/` + `local_model_tools/`） | **0** | **0** | 活躍交易系統零硬編碼 |
| **Scripts**（`control_api_v1/scripts/`） | 2 | 2 | `auto_bridge_observer_to_runtime_snapshot.py`、`beta_quickstart.sh` |
| **Tests**（`control_api_v1/tests/`） | 1 | 3 | `test_auto_bridge.py` |
| **Shell 腳本**（`helper_scripts/`） | ~15 | ~70 | 維護腳本、cron 腳本 |
| **文檔**（`docs/`、`CLAUDE.md`、`TODO.md` 等） | ~100+ | 大量 | 路徑說明、審計報告 |

### 1.2 Ollama 客戶端

`ollama_client.py` 已是乾淨抽象：
- 配置全部通過 `OllamaConfig` dataclass + env vars (`OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT`)
- 零硬編碼路徑、零 Linux-specific API
- 對外暴露 `OllamaClient`（通用 HTTP 客戶端）+ `OllamaResponse`（純數據）
- `is_available()` / `generate()` / `chat()` / `classify()` / `judge_edge()` 接口均與 OS 無關

### 1.3 系統依賴

- `psutil`：僅 `h0_gate.py` 使用，已有 `ImportError` fallback（安全默認值 cpu=0.0, mem=9999MB）
- 無 `systemd`/`launchd` 代碼引用，無 `.service` 文件
- `_path_setup.py`：使用相對 `__file__` 上溯，跨平台安全
- `requirements.txt`：所有依賴均跨平台（fastapi, uvicorn, httpx, websocket-client, psutil, beautifulsoup4）

### 1.4 服務部署

- 當前啟動方式：直接 `python3 -m uvicorn` 或通過 shell 腳本
- 無 systemd unit file 在 repo 中
- Cron 腳本 2 個：`cron_daily_report.sh`（無硬編碼路徑）、`cron_observer_cycle.sh`（有硬編碼路徑）

---

## 二、XP-1：路徑不硬編碼

### 2.1 「完成」的精確定義

**核心標準：Live 運行時零硬編碼（已達成）。**

XP-1 的範圍應限定為「影響系統運行的代碼」，而非所有歷史文件：

| 層次 | 標準 | 當前狀態 |
|------|------|---------|
| **P0 必須** | `control_api_v1/app/*.py` + `local_model_tools/**/*.py` 零 `/home/ncyu` | ✅ 已通過 |
| **P0 必須** | `control_api_v1/scripts/*.py` + `*.sh` 零 `/home/ncyu` | ❌ 2 文件需修 |
| **P1 應該** | `helper_scripts/*.sh` 改用 env var 或相對路徑 | ❌ ~15 文件需修 |
| **P2 建議** | Legacy 腳本（A-K 章）批量替換 | ⚠ 低優先級，見例外清單 |

### 2.2 驗收標準

```
- [ ] XP-1.1：grep -r "/home/ncyu" program_code/exchange_connectors/bybit_connector/control_api_v1/app/ 返回 0 結果
- [ ] XP-1.2：grep -r "/home/ncyu" program_code/local_model_tools/ 返回 0 結果
- [ ] XP-1.3：grep -r "/home/ncyu" program_code/exchange_connectors/bybit_connector/control_api_v1/scripts/ 返回 0 結果
      修復方式：TRADING_SERVICES_DIR 改為 os.getenv("OPENCLAW_TRADING_SERVICES_DIR", fallback)
      fallback 使用 Path(__file__).resolve() 相對上溯
- [ ] XP-1.4：helper_scripts/ 中所有 .sh 文件使用 REPO=${REPO:-$(dirname "$(realpath "$0")")/..} 模式
      或讀取 OPENCLAW_ROOT env var
- [ ] XP-1.5：cron_observer_cycle.sh 的 REPO= 行改為 ${OPENCLAW_ROOT:-...} 帶 fallback
- [ ] XP-1.6：所有新的路徑引用使用 Path(__file__) 相對定位或 os.environ 讀取
- [ ] XP-1.7：（P2）Legacy 腳本 ~150 文件的 BASE=Path("/home/ncyu/...") 改為
      BASE = Path(os.environ.get("OPENCLAW_RUNTIME_DIR", "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate"))
      （保留默認值向後兼容，但允許 macOS 覆蓋）
```

### 2.3 修復策略

**P0 文件清單（必須改）：**
1. `control_api_v1/scripts/auto_bridge_observer_to_runtime_snapshot.py` — 1 處
2. `control_api_v1/scripts/beta_quickstart.sh` — 1 處
3. `helper_scripts/cron_observer_cycle.sh` — 2 處

**P1 文件清單（應該改）：**
4. `helper_scripts/maintenance_scripts/prune_dated_files.sh`
5. `helper_scripts/maintenance_scripts/bybit_connector/run_with_trading_env.sh` — 5 處
6. 其他 `helper_scripts/maintenance_scripts/bybit_connector/*.sh` — ~10 文件

**P2 批量替換（可延後）：**
7. `trade_executor/bybit_decision_lease/` — 38 文件，全部用 BASE = Path(os.environ.get(...))
8. `market_data_processor/bybit_business_events/` — ~20 文件
9. 其他 legacy 目錄

---

## 三、XP-2：LocalLLMClient 抽象乾淨

### 3.1 「完成」的精確定義

**核心問題：現有 `ollama_client.py` 是否已足夠乾淨？**

**結論：已經足夠乾淨，無需額外抽象層。**

理由：
1. `OllamaClient` 類名雖含 "Ollama"，但接口完全通用（`generate(prompt)` → `OllamaResponse`）
2. 配置通過 env vars 注入，無硬編碼 Ollama-specific 假設
3. 所有調用方（`strategist_agent.py`、`analyst_agent.py`、`pipeline_bridge.py`）通過 `set_ollama_client()` setter 注入，天然支持替換
4. 強行引入 `LocalLLMClient` ABC 接口成本高（修改所有注入點），收益低（目前只有 Ollama 一個實現）

**何時才需要抽象：** 引入第二個本地 LLM 後端時（如 llama.cpp server、vLLM 等）。

### 3.2 驗收標準

```
- [ ] XP-2.1：ollama_client.py 不含任何硬編碼的 Ollama 特有端點路徑
      （當前 /api/generate, /api/chat, /api/tags 是 Ollama API，屬於實現細節，可接受）
- [ ] XP-2.2：所有消費方通過 setter 注入客戶端實例（不直接 import 單例）
      驗證：grep "from.*ollama_client import get_ollama_client" 只出現在初始化代碼中
- [ ] XP-2.3：OllamaResponse 不洩漏 Ollama-specific 字段到業務邏輯
      （eval_count/eval_duration_ns 僅用於性能監控，不影響交易決策，可接受）
- [ ] XP-2.4：如在 macOS 上 Ollama 不可用，系統仍正常啟動且交易管線不中斷
      （原則 14 已保障：Ollama crash → L0 fallback → 純確定性路徑）
- [ ] XP-2.5：文檔記錄如何替換 LLM 後端（在 CLAUDE.md 或遷移指南中）
```

### 3.3 風險評估

XP-2 的真正風險不在抽象層，而在：
- macOS 上 Ollama 安裝差異（brew install ollama vs apt install）
- 模型路徑差異（`~/.ollama/models` 在 macOS，`/usr/share/ollama/.ollama/models` 在 Linux）
- 但這些是部署問題，不是代碼問題 — `ollama_client.py` 只連 HTTP API，不關心模型存儲位置

---

## 四、XP-3：服務部署可遷移

### 4.1 「完成」的精確定義

遷移文檔需包含以下內容：

### 4.2 驗收標準

```
- [ ] XP-3.1：創建 docs/references/cross_platform_deployment_guide.md 包含：
      a. macOS 前置安裝清單（Python 3.12+, Ollama, PostgreSQL/替代, jq, curl）
      b. 環境變量映射表（OPENCLAW_ROOT, OPENCLAW_TRADING_SERVICES_DIR, OLLAMA_BASE_URL 等）
      c. systemd → launchd 遷移對照（如適用）
      d. Cron → launchd plist 遷移範例
      e. 常見差異清單（路徑分隔符、temp 目錄、用戶目錄結構）
- [ ] XP-3.2：啟動腳本 beta_quickstart.sh 在 macOS 上可直接執行（或提供 macOS 版本）
- [ ] XP-3.3：記錄 PostgreSQL 替代方案（macOS 上 Postgres.app vs brew install postgresql）
- [ ] XP-3.4：記錄日誌路徑在 macOS 上的推薦位置（~/Library/Logs/OpenClaw/ 或項目內 logs/）
- [ ] XP-3.5：記錄 settings/ 目錄（.env, secrets）在 macOS 上的安全存放建議
```

### 4.3 不需要做的事

- 不需要同時維護 systemd 和 launchd unit files — 文檔記錄足夠
- 不需要自動偵測 OS 切換啟動方式 — 部署時一次性配置
- 不需要 Docker 化 — 與項目的 「本地交易 Agent」定位衝突

---

## 五、XP-4：依賴管理乾淨

### 5.1 「完成」的精確定義

### 5.2 驗收標準

```
- [ ] XP-4.1：requirements.txt 中所有依賴在 macOS (ARM64) + Ubuntu (x86_64) 上均可安裝
      當前清單全部跨平台（fastapi, uvicorn, httpx, pydantic, slowapi, websocket-client,
      psutil, beautifulsoup4, pytest, pytest-asyncio）→ ✅ 已通過
- [ ] XP-4.2：psutil 在 requirements.txt 中標記為 optional 或帶平台守衛注釋
      建議：保持現狀，psutil 跨平台且 h0_gate.py 已有 ImportError fallback
- [ ] XP-4.3：無 Linux-only 依賴（如 inotify, epoll bindings, systemd-python）
      當前掃描結果：✅ 零 Linux-only 依賴
- [ ] XP-4.4：pip install -r requirements.txt 在 macOS Python 3.12 上零錯誤
- [ ] XP-4.5：如未來添加新依賴，README/CLAUDE.md 中記錄跨平台兼容性要求
```

### 5.3 風險評估

依賴層面風險極低：
- `psutil` 在 macOS 上完全支持（同一 PyPI 包，native C extension 自動編譯）
- `uvicorn[standard]` 中的 `uvloop` 在 macOS ARM64 上正常工作
- `websocket-client` 純 Python，零 native 依賴
- `beautifulsoup4` 純 Python

---

## 六、「不損壞現有程序」的驗證方案

### 6.1 測試對比策略

```
改動前基準：3703 passed / 24 failed / 17 errors
改動後要求：≥ 3703 passed / ≤ 24 failed / ≤ 17 errors
任何 passed→failed 轉換 = 回歸，必須修復
```

### 6.2 最易被路徑改動破壞的功能

| 優先級 | 功能 | 受影響文件 | 破壞風險 |
|--------|------|-----------|---------|
| **P0** | 服務啟動 | main.py → main_legacy.py → settings 讀取 | **低**（啟動流程不含硬編碼路徑） |
| **P0** | Config/Settings 讀取 | settings/ 目錄讀取 | **低**（通過相對路徑和 `__file__` 定位） |
| **P0** | 日誌寫入 | logs/ 目錄 | **低**（logging 標準庫，路徑由 config 控制） |
| **P1** | auto_bridge 腳本 | `scripts/auto_bridge_observer_to_runtime_snapshot.py` | **中**（直接硬編碼 TRADING_SERVICES_DIR） |
| **P1** | cron 定時任務 | `helper_scripts/cron_observer_cycle.sh` | **中**（REPO 路徑硬編碼） |
| **P2** | Legacy 合約檢查 | `bybit_decision_lease/*.py` 等 ~150 文件 | **低**（這些腳本不在 Live 路徑上，改了也不影響運行） |

### 6.3 測試執行方案

```
Step 1（Ubuntu 回歸 — 必須）：
  python3 -m pytest --ignore=database_files -q --tb=no
  比對 passed/failed/error 數量

Step 2（macOS 驗證 — 強烈建議但非阻塞）：
  在 macOS 上跑同樣的測試套件
  預期：部分依賴 Bybit API / Postgres 的測試可能因環境不同而 skip/fail
  關注：核心邏輯測試（app/tests/、local_model_tools/tests/）是否全通過

Step 3（人工啟動驗證 — 必須）：
  python3 -m uvicorn app.main:app --port 8000
  驗證啟動不報 FileNotFoundError / PathError
  驗證 /api/v1/health 端點可訪問
  驗證 /api/v1/governance/status 端點可訪問
```

### 6.4 E2 審查重點清單

```
- [ ] E2-R1：每個路徑修改都有 fallback（env var 不存在時的默認值）
- [ ] E2-R2：env var 名稱統一（OPENCLAW_ 前綴，全大寫，下劃線分隔）
- [ ] E2-R3：未引入新的 Linux-only 依賴
- [ ] E2-R4：_path_setup.py 的 __file__ 相對定位模式沒有被破壞
- [ ] E2-R5：monkey-patch 路徑（main.py → main_legacy.py）沒有被影響
- [ ] E2-R6：Legacy 腳本的批量替換使用統一的模式（不是每個文件用不同寫法）
- [ ] E2-R7：所有路徑字符串使用 pathlib.Path 或 os.path.join（不是字符串拼接）
- [ ] E2-R8：Windows 路徑分隔符問題（/）不影響（macOS 用 / ，與 Linux 一致）
```

---

## 七、例外清單（看似硬編碼但可接受）

以下情況 **不計入 XP-1 不合格項**：

### 7.1 文檔中的路徑引用（可接受）

- `CLAUDE.md` 中 §八「GitHub 與本地路徑」的 `/home/ncyu/BybitOpenClaw/srv` 描述
- `TODO.md` 中的路徑引用
- `docs/` 目錄下所有 `.md` 文件中的路徑描述（審計報告、工作日誌等）
- `SYSTEM_STATUS_REPORT.md` 中的路徑描述
- `program_code/*/docs/*.md` 中的文檔

**理由：** 文檔描述當前環境，遷移後應更新但不影響程序運行。

### 7.2 測試文件中的 mock 路徑（可接受）

- `control_api_v1/tests/test_auto_bridge.py` 中的 `SYSTEM_SNAPSHOT_PATH` 等常量
  **條件：** 測試文件中的路徑僅用於 mock/assert，不實際讀取文件系統

**理由：** 測試中的路徑是測試數據，不影響生產運行。但建議標記 `# NOTE: test-only path, not used at runtime`。

### 7.3 .gitignore 中的路徑模式（可接受）

- `.gitignore` 中的模式如 `settings/`、`trading_services/` 等
  **理由：** 這些是目錄名模式，不是絕對路徑。

### 7.4 __pycache__ 和 .venv 中的路徑（可接受）

- Python 編譯快取和虛擬環境中的絕對路徑
  **理由：** 這些是自動生成的，不需要手動修改，遷移後重建即可。

### 7.5 Legacy 腳本的默認值（有條件接受）

- `bybit_decision_lease/` 等 legacy 目錄中的 `BASE = Path("/home/ncyu/...")`
  **條件：** 改為 `os.environ.get("OPENCLAW_RUNTIME_DIR", "/home/ncyu/...")` 後，
  保留原始路徑作為默認值不算硬編碼違規。

**理由：** Legacy 腳本不在 Live 路徑上，且保留默認值確保向後兼容。

---

## 八、工時估算與優先級排序

| XP | P0 必須 | P1 應該 | P2 建議 | 總估時 |
|----|---------|---------|---------|--------|
| XP-1 | 3 文件 ~1h | ~15 文件 ~3h | ~150 文件 ~6h（批量 sed） | ~10h |
| XP-2 | 無需改動 | 文檔補充 ~0.5h | - | ~0.5h |
| XP-3 | 遷移文檔 ~2h | - | - | ~2h |
| XP-4 | 驗證現有依賴 ~0.5h | - | - | ~0.5h |
| **驗證** | Ubuntu 回歸 ~0.5h | macOS 測試 ~1h | - | ~1.5h |
| **合計** | | | | **~14.5h** |

### 推薦執行順序

```
Wave 1（P0，~4h）：
  XP-1 P0 3 文件修復 + XP-4 驗證 + Ubuntu 回歸

Wave 2（P1，~4h）：
  XP-1 P1 helper_scripts + XP-3 遷移文檔

Wave 3（P2，~6.5h，可延後）：
  XP-1 P2 legacy 批量替換 + XP-2 文檔 + macOS 實測
```

---

## 九、關鍵結論

1. **Live 運行時代碼已經跨平台就緒** — `app/` 和 `local_model_tools/` 零硬編碼路徑，這是最重要的發現。

2. **Ollama 客戶端抽象已足夠** — 不建議過度工程化，現有 `OllamaClient` + env var 配置模式已經乾淨。

3. **依賴管理無問題** — 所有依賴均跨平台，`psutil` 已有 ImportError fallback。

4. **真正需要改的只有 ~18 個文件**（P0+P1），其中 P0 僅 3 個文件。

5. **~150 個 legacy 文件的路徑硬編碼是低優先級**（P2），因為它們不在 Live 路徑上，改與不改不影響系統在 macOS 上運行。

6. **最大風險不在代碼而在部署**：PostgreSQL 配置、Ollama 安裝、cron → launchd 遷移。XP-3 的遷移文檔是防止部署問題的關鍵。
