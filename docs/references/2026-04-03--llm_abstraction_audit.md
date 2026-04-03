# LLM Abstraction Layer Pre-Audit — Ollama 調用點標記文檔
# LLM Abstraction Layer Pre-Audit — Ollama Call-Site Inventory

> 產出日期 / Date: 2026-04-03
> 角色 / Role: E1-Beta (XP-2)
> 目的 / Purpose: Phase 1 任務 1.8 前的現狀標記，不改任何代碼
> FA 結論：ollama_client.py 已足夠乾淨，抽象層留到 Phase 1 任務 1.8

---

## 一、調用點清單（生產代碼）

### 分類說明

| 標記 | 含義 |
|------|------|
| ✅ | 已通過抽象層（get_ollama_client() / setter injection / OllamaClient 實例） |
| ⚠️ | 直接調用 HTTP endpoint（需 Phase 1 修復） |
| 📌 | 配置/常量定義（可接受但標記） |

---

### 1. `ollama_client.py` — 核心抽象層（📌 配置 + 實現）

**路徑**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ollama_client.py`

| 行號 | 分類 | 內容 |
|------|------|------|
| 47 | 📌 | `DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"` |
| 48 | 📌 | `DEFAULT_MODEL = "qwen3.5:9b-q4_K_M"` |
| 49 | 📌 | `DEFAULT_TIMEOUT_SECONDS = 30` |
| 56 | 📌 | `os.getenv("OLLAMA_BASE_URL", ...)` env var 讀取 |
| 57 | 📌 | `os.getenv("OLLAMA_MODEL", ...)` env var 讀取 |
| 58 | 📌 | `os.getenv("OLLAMA_TIMEOUT", ...)` env var 讀取 |
| 145 | 📌 | `is_available()` 內部 HTTP `/api/tags` 健康檢查 |
| 186 | 📌 | `list_models()` 內部 HTTP `/api/tags` 模型列表 |
| 238 | 📌 | `generate()` 內部 HTTP `/api/generate` |
| 287 | 📌 | `chat()` 內部 HTTP `/api/chat` |
| 466 | 📌 | `get_ollama_client()` singleton 工廠 |
| 482 | 📌 | `get_ollama_client_27b()` 27B singleton 工廠 |
| 497 | 📌 | 27B 模型硬編碼 `"qwen3.5:27b-q4_K_M"` |
| 501 | 📌 | `reset_ollama_client()` 測試用重置 |

**結論**: 此文件本身就是抽象層，所有 HTTP 細節封裝在 `_post()` 方法中。Phase 1 時若需替換 LLM 後端，只需修改此文件或建立接口讓此文件實現。

---

### 2. `strategist_agent.py` — ✅ Setter Injection

**路徑**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_agent.py`

| 行號 | 分類 | 內容 |
|------|------|------|
| 126 | ✅ | `__init__(ollama_client: Optional[Any] = None)` 構造注入 |
| 132 | ✅ | `self._ollama = ollama_client` 存儲注入的客戶端 |
| 186 | ✅ | `"ollama_calls_tracked": 0` stats 計數器（僅名稱引用） |
| 360 | ✅ | `_record(provider="ollama", ...)` 成本記錄（字符串標籤） |
| 614 | ✅ | `self._ollama.is_available()` 通過注入實例調用 |
| 643 | ✅ | `self._ollama.judge_edge(context)` 通過注入實例調用 |
| 684 | ✅ | `record_fn(provider="ollama", ...)` 成本記錄（字符串標籤） |
| 686 | ✅ | `self._stats["ollama_calls_tracked"] += 1` stats 更新 |

**結論**: 完全通過構造函數注入，零直接 HTTP 調用。Phase 1 無需修改。

---

### 3. `analyst_agent.py` — ✅ Setter Injection

**路徑**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/analyst_agent.py`

| 行號 | 分類 | 內容 |
|------|------|------|
| 175 | ✅ | `__init__(ollama_client: Optional[Any] = None)` 構造注入 |
| 188 | ✅ | `self._ollama = ollama_client` 存儲注入的客戶端 |
| 653 | ✅ | `self._ollama.is_available()` 通過注入實例調用 |
| 687 | ✅ | `self._ollama.generate(...)` 通過注入實例調用 |

**結論**: 完全通過構造函數注入。Phase 1 無需修改。

---

### 4. `guardian_agent.py` — ✅ Setter Injection

**路徑**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/guardian_agent.py`

| 行號 | 分類 | 內容 |
|------|------|------|
| 101 | ✅ | `__init__(ollama_client: Optional[Any] = None)` 構造注入 |
| 108 | ✅ | `self._ollama = ollama_client` 存儲注入的客戶端 |
| 491 | ✅ | `self._ollama.is_available()` 通過注入實例調用 |
| 494 | ✅ | `self._ollama.classify(...)` 通過注入實例調用 |

**結論**: 完全通過構造函數注入。Phase 1 無需修改。

---

### 5. `pipeline_bridge.py` — ✅ Setter Injection

**路徑**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/pipeline_bridge.py`

| 行號 | 分類 | 內容 |
|------|------|------|
| 88 | ✅ | 注釋文檔：`set_ollama_client` setter 說明 |
| 138 | ✅ | `self._ollama_client = None` 初始化 |
| 262 | ✅ | `set_ollama_client(self, client)` setter 方法 |
| 267 | ✅ | `self._ollama_client = client` 存儲注入的客戶端 |
| 1060 | ✅ | `self._ollama_client` 可用性檢查 |
| 1650 | ✅ | `self._ollama_client.is_available()` 通過注入實例調用 |
| 1701 | ✅ | `self._ollama_client.judge_edge(...)` 通過注入實例調用 |

**結論**: 完全通過 setter 注入。Phase 1 無需修改。

---

### 6. `phase2_strategy_routes.py` — ✅ 工廠函數 + 注入

**路徑**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/phase2_strategy_routes.py`

| 行號 | 分類 | 內容 |
|------|------|------|
| 127 | ✅ | `from .ollama_client import OllamaClient` import 類型 |
| 157 | ✅ | `OLLAMA_CLIENT.is_available(force_check=True)` 啟動檢查 |
| 158 | ✅ | 日誌記錄 Ollama 可用性 |
| 180 | ✅ | `ollama_client=OLLAMA_CLIENT` 注入 StrategistAgent |
| 224 | ✅ | `ollama_client=OLLAMA_CLIENT` 注入 StrategistAgent |
| 257 | ✅ | `ollama_client=OLLAMA_CLIENT` 注入 StrategistAgent |
| 439 | ✅ | `PIPELINE_BRIDGE.set_ollama_client(OLLAMA_CLIENT)` 注入 PipelineBridge |
| 496 | ✅ | `from .ollama_client import get_ollama_client_27b` 工廠函數 |
| 500 | ✅ | `ollama_client=get_ollama_client_27b()` 注入 AnalystAgent |

**結論**: 此文件是注入的「接線中心」（wiring hub），通過工廠函數獲取 singleton 並注入各 Agent。Phase 1 時此文件需要更新以支持新 LLM 後端選擇。

---

### 7. `layer2_engine.py` — ✅ 工廠函數

**路徑**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_engine.py`

| 行號 | 分類 | 內容 |
|------|------|------|
| 67 | ✅ | `from .ollama_client import get_ollama_client` 工廠函數 import |
| 265 | ✅ | `client = get_ollama_client()` 獲取 singleton |
| 316 | ✅ | `result["triage_source"] = "local_ollama"` 字符串標籤 |

**結論**: 通過工廠函數獲取客戶端。Phase 1 需更新 import 路徑。

---

### 8. `layer2_tools.py` — ✅ 工廠函數

**路徑**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_tools.py`

| 行號 | 分類 | 內容 |
|------|------|------|
| 39 | ✅ | `from .ollama_client import get_ollama_client` 工廠函數 import |
| 396 | ✅ | `client = get_ollama_client()` 獲取 singleton |
| 459 | ✅ | `get_ollama_client().is_available()` 健康檢查 |
| 464 | ✅ | `client = get_ollama_client()` 獲取 singleton |

**結論**: 通過工廠函數獲取客戶端。Phase 1 需更新 import 路徑。

---

### 9. `layer2_routes.py` — ⚠️ 直接 HTTP 調用

**路徑**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_routes.py`

| 行號 | 分類 | 內容 |
|------|------|------|
| 345-346 | ✅ | `/ollama/status` 路由端點定義 |
| 358 | ✅ | `get_ollama_client()` 工廠函數獲取客戶端 |
| 360 | ✅ | `client.is_available()` 通過客戶端調用 |
| **374** | **⚠️** | **`url = client.config.base_url.rstrip("/") + "/api/tags"` 直接拼接 URL** |
| **375** | **⚠️** | **`urllib.request.urlopen(url, timeout=5)` 直接 HTTP 調用繞過客戶端** |

**結論**: 第 374-375 行繞過了 `OllamaClient.list_models()` 方法，直接調用 `/api/tags`。Phase 1 應改為 `client.list_models()`。這是唯一一處繞過抽象層的直接 HTTP 調用。

---

### 10. `layer2_cost_tracker.py` — ✅ 純數據記錄

**路徑**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_cost_tracker.py`

| 行號 | 分類 | 內容 |
|------|------|------|
| 96-99 | ✅ | `_ollama_stats` 內部統計字典初始化 |
| 508 | ✅ | `provider="ollama"` 字符串標籤用於記錄 |
| 524-527 | ✅ | `_ollama_stats` 統計邏輯 |
| 538-539 | ✅ | `ollama_calls` JSON 區段 |
| 555-578 | ✅ | `record_ollama_call()` DEPRECATED 包裝（→ `record_call(provider="ollama")`) |
| 585-605 | ✅ | `get_ollama_stats()` 統計讀取 |

**結論**: 純成本記錄模塊，不發 HTTP 請求。「ollama」僅作為 provider 字符串標籤。Phase 1 無需修改。

---

### 11. `data_source_enforcer.py` — ✅ 純字符串常量

**路徑**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/data_source_enforcer.py`

| 行號 | 分類 | 內容 |
|------|------|------|
| 485 | ✅ | `model_name: str` 參數文檔示例 `"ollama:llama2"` |
| 496 | ✅ | docstring 中的示例字符串 |
| 505 | ✅ | `if "ollama" in model_name.lower()` 字符串匹配分類 |

**結論**: 用於模型名稱分類，不調用任何 HTTP。Phase 1 無需修改。

---

### 12. `perception_data_plane.py` — ✅ 純枚舉值

**路徑**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/perception_data_plane.py`

| 行號 | 分類 | 內容 |
|------|------|------|
| 69 | ✅ | `LOCAL_OLLAMA = "local_ollama"` 枚舉成員 |

**結論**: 純數據源枚舉定義。Phase 1 無需修改。

---

### 13. GUI 前端 — 📌 配置引用

**路徑**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-ai.html`

| 行號 | 分類 | 內容 |
|------|------|------|
| 119 | 📌 | 模型名稱顯示文本 |
| 121 | 📌 | `placeholder/value="http://127.0.0.1:11434"` 端點地址硬編碼 |
| 125 | 📌 | Ollama 狀態詳情 DOM 元素 |
| 539-577 | ✅ | 通過 `ocApi('/api/v1/paper/layer2/ollama/status')` 調用後端 API（不直接調用 Ollama） |

**結論**: 前端通過後端 API 間接訪問 Ollama，不直接調用。端口 `11434` 僅為 placeholder 顯示。Phase 1 無需修改前端。

---

## 二、Phase 1 任務 1.8 需要修改的文件

### 必改（直接 HTTP 調用繞過抽象層）

| 優先級 | 文件 | 問題 | 修復方式 |
|--------|------|------|---------|
| P1 | `layer2_routes.py:374-375` | 直接 `urllib.request.urlopen` 調用 `/api/tags` | 改為 `client.list_models()` |

### 視抽象需求而改（工廠函數依賴）

若 Phase 1 引入 `LocalLLMClient` 接口（Protocol / ABC），以下文件的 import 路徑需更新：

| 文件 | 當前 import | 變更範圍 |
|------|------------|---------|
| `phase2_strategy_routes.py` | `from .ollama_client import OllamaClient, get_ollama_client, get_ollama_client_27b` | 接線中心，改為新工廠函數 |
| `layer2_engine.py` | `from .ollama_client import get_ollama_client` | 改 import 路徑 |
| `layer2_tools.py` | `from .ollama_client import get_ollama_client` | 改 import 路徑 |
| `layer2_routes.py` | `from .ollama_client import get_ollama_client` | 改 import 路徑 + 修復直接 HTTP |

### 無需修改

| 文件 | 原因 |
|------|------|
| `strategist_agent.py` | 構造注入 `Optional[Any]`，已是 duck-typing |
| `analyst_agent.py` | 構造注入 `Optional[Any]`，已是 duck-typing |
| `guardian_agent.py` | 構造注入 `Optional[Any]`，已是 duck-typing |
| `pipeline_bridge.py` | Setter 注入 `Any` 類型，已是 duck-typing |
| `layer2_cost_tracker.py` | 純數據記錄，不調用 LLM |
| `data_source_enforcer.py` | 純字符串匹配 |
| `perception_data_plane.py` | 純枚舉值 |
| `tab-ai.html` | 通過後端 API 間接訪問 |

---

## 三、現有抽象層接口清單（ollama_client.py）

### 配置類

```python
@dataclass
class OllamaConfig:
    base_url: str          # default: env OLLAMA_BASE_URL or "http://127.0.0.1:11434"
    model: str             # default: env OLLAMA_MODEL or "qwen3.5:9b-q4_K_M"
    timeout_seconds: int   # default: env OLLAMA_TIMEOUT or 30
    temperature: float     # default: 0.3
    max_retries: int       # default: 0 (CLAUDE.md hard boundary)
```

### 響應類

```python
@dataclass
class OllamaResponse:
    text: str              # 生成的文本
    model: str             # 使用的模型名
    success: bool          # 是否成功
    latency_ms: float      # 延遲（毫秒）
    error: str | None      # 錯誤信息
    eval_count: int        # 生成的 token 數
    eval_duration_ns: int  # 生成耗時（納秒）
    total_duration_ns: int # 總耗時（納秒）

    @property tokens_per_second -> float
    @property cost_usd -> float  # 永遠返回 0.0
```

### 客戶端公開方法

```python
class OllamaClient:
    def __init__(config: OllamaConfig | None = None)

    # 連通性
    def is_available(*, force_check: bool = False) -> bool
    async def is_available_async(*, force_check: bool = False) -> bool
    def list_models() -> list[str]

    # 推理
    def generate(prompt, *, system, model, temperature, max_tokens, timeout, think) -> OllamaResponse
    def chat(messages, *, system, model, temperature, max_tokens, timeout, think) -> OllamaResponse

    # 結構化輸出
    def classify(text, categories, *, system, model, timeout) -> OllamaResponse
    def judge_edge(market_context, *, model, timeout) -> OllamaResponse

    # 屬性
    @property config -> OllamaConfig
    @property model -> str
```

### 工廠函數（Singleton）

```python
def get_ollama_client(config: OllamaConfig | None = None) -> OllamaClient  # 9B default
def get_ollama_client_27b() -> OllamaClient                                 # 27B complex tasks
def reset_ollama_client() -> None                                            # testing only
```

---

## 四、macOS 上 Ollama 的安裝和配置差異

### 安裝方式

| 平台 | 安裝命令 | 說明 |
|------|---------|------|
| **Linux (Ubuntu/Debian)** | `curl -fsSL https://ollama.com/install.sh \| sh` | 安裝為 systemd 服務 |
| **macOS** | `brew install ollama` 或下載 .app | Homebrew 安裝或官方 GUI 應用 |
| **macOS (手動)** | 從 https://ollama.com 下載 Ollama.app | 拖入 Applications，GUI 管理 |

### 服務管理差異

| 項目 | Linux | macOS |
|------|-------|-------|
| 守護進程 | `systemctl start/stop ollama` | `brew services start/stop ollama` 或 Ollama.app 自動啟動 |
| 默認端口 | `127.0.0.1:11434` | `127.0.0.1:11434`（相同） |
| 自動啟動 | systemd enable | `brew services` 或 Login Items |
| GPU 支持 | NVIDIA CUDA（需 nvidia-container-toolkit）/ AMD ROCm | Apple Silicon Metal（自動檢測，無需配置） |
| 環境變量 | `/etc/systemd/system/ollama.service` 或 `/etc/environment` | `launchctl setenv` 或 `~/.zshrc` |
| 模型存儲 | `~/.ollama/models/` | `~/.ollama/models/`（相同） |
| 日誌 | `journalctl -u ollama` | `~/.ollama/logs/server.log` 或 Console.app |

### 配置兼容性分析

現有 `ollama_client.py` 的 OS 無關設計：
- ✅ 使用 HTTP REST API（`/api/generate`, `/api/chat`, `/api/tags`）— 完全跨平台
- ✅ 端口通過 `OLLAMA_BASE_URL` env var 可配 — 支持遠程 Ollama 實例
- ✅ 模型名通過 `OLLAMA_MODEL` env var 可配 — 支持不同模型
- ✅ 零 subprocess 調用（之前已重構） — 無 shell 依賴
- ✅ 使用 `urllib.request`（Python 標準庫） — 無第三方依賴

**macOS 上唯一需注意的點**：
1. Apple Silicon 的 Metal GPU 加速自動生效，推理速度與 Linux CUDA 不同（通常更慢但仍可用）
2. 若使用 Ollama.app（GUI 版），服務在用戶登錄時自動啟動；`brew services` 版則需手動配置
3. 模型量化選擇：Apple Silicon 統一內存架構下，可考慮 Q8 而非 Q4_K_M（顯存不是瓶頸）

---

## 五、審計結論摘要

### 統計

| 指標 | 數值 |
|------|------|
| 生產文件含 Ollama 引用 | 12 個（含 ollama_client.py 自身） |
| 測試文件含 Ollama 引用 | 16 個 |
| GUI 文件含 Ollama 引用 | 1 個（tab-ai.html） |
| ✅ 通過抽象層調用 | 10 個文件 |
| ⚠️ 直接 HTTP 繞過 | **1 處**（layer2_routes.py:374-375） |
| 📌 配置/常量定義 | 2 個文件（ollama_client.py + tab-ai.html） |

### 結論

現有 `ollama_client.py` 已經是一個事實上的抽象層：
1. 所有 Agent（Strategist / Analyst / Guardian）通過構造注入接收客戶端，類型為 `Optional[Any]`（duck-typing），天然支持替換
2. PipelineBridge 通過 setter 注入，同樣 duck-typing
3. 接線中心 `phase2_strategy_routes.py` 統一管理所有注入
4. **唯一的抽象洩漏**：`layer2_routes.py` 第 374-375 行直接調用 `/api/tags`，應改用 `client.list_models()`

FA 結論正確：現階段不需要新建 `LocalLLMClient` 抽象層。Phase 1 任務 1.8 時的工作量預估：
- 必改：1 處直接 HTTP 調用（~5 分鐘）
- 可選：4 個工廠函數 import 點（若引入接口類型，~30 分鐘）
- 無需改：7 個已使用 duck-typing 的文件
