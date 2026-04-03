# XP-1~4 Cross-Platform Compatibility Audit — Ubuntu → macOS Migration
# 跨平台兼容性審計 — Ubuntu → macOS（Mac Studio M5 Ultra）遷移

**PA**: Project Architect
**日期**: 2026-04-03
**範圍**: 全項目掃描（program_code/ + helper_scripts/ + settings/ + systemd units）
**目標**: 識別所有平台依賴，為 macOS 遷移制定改動方案

---

## 總覽

| 類別 | 發現數 | 必須改 | 需驗證 | 可接受 |
|------|--------|--------|--------|--------|
| XP-1 硬編碼路徑 | 146+ | 79 | 12 | 55 |
| XP-2 Ollama/LLM | 8 | 0 | 2 | 6 |
| XP-3 系統服務依賴 | 18 | 5 | 8 | 5 |
| XP-4 依賴審計 | 9 | 0 | 3 | 6 |

**風險評估**: 核心交易 API（control_api_v1/app/）遷移風險 **低**。硬編碼路徑集中在歷史遺留模塊（decision_lease、business_events、io_and_persistence），這些大多不在 live 管線中。

---

## XP-1：路徑硬編碼掃描

### 1.1 `/home/ncyu/srv/` 硬編碼路徑（必須改，~100 處）

#### 集群 A：trade_executor/bybit_decision_lease/ — 36 個文件

所有文件使用同一模式：
```python
BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
```

**完整文件列表**（每個文件 1-2 處）：
- `bybit_decision_lease_consume_final_audit.py:8`
- `bybit_decision_lease_adaptive_ttl.py:23`
- `bybit_decision_lease_replay_guard_contract_check.py:8`
- `bybit_decision_lease_consume_policy.py:8`
- `bybit_execution_authority_aggregator_final_audit.py:10`
- `bybit_operator_ack_shadow_contract_check.py:10`
- `bybit_decision_lease_replay_policy_contract_check.py:8`
- `bybit_decision_lease_replay_contract_check.py:8`
- `bybit_decision_lease_friction_metrics.py:20`
- `bybit_execution_authority_aggregator_contract_check.py:10`
- `bybit_decision_lease_friction_final_audit.py:8`
- `bybit_decision_lease_preflight.py:9`
- `bybit_manual_approval_packet_final_audit.py:10`
- `bybit_decision_lease_consume_gate.py:8`
- `bybit_decision_lease_schema_contract_check.py:9`
- `bybit_decision_lease_contract_check.py:9`
- `bybit_decision_lease_replay_final_audit.py:8`
- `bybit_decision_lease_adaptive_ttl_contract_check.py:8`
- `bybit_decision_lease_chapter_handoff.py:10`
- `bybit_decision_lease_shadow_contract_check.py:8`
- `bybit_decision_lease_shadow_audit.py:8`
- `bybit_decision_lease_replay_policy.py:9`
- `bybit_decision_lease_preflight_contract_check.py:8`
- `bybit_operator_ack_shadow.py:10`
- `bybit_decision_lease_approval_bridge_final_audit.py:10`
- `bybit_execution_authority_aggregator.py:27`
- `bybit_decision_lease_consume_policy_contract_check.py:8`
- `bybit_decision_lease_shadow_issue.py:9`
- `bybit_manual_approval_packet.py:26`
- `bybit_decision_lease_chapter_contract_check.py:10`
- `bybit_decision_lease_approval_bridge_contract_check.py:10`
- `bybit_decision_lease_approval_bridge.py:26`
- `bybit_decision_lease_replay_guard.py:8`
- `bybit_decision_lease_friction_metrics_contract_check.py:8`
- `bybit_decision_lease_chapter_final_audit.py:10`
- `bybit_decision_lease_consume_contract_check.py:8`
- `bybit_decision_lease_chapter_summary.py:10`
- `bybit_operator_ack_shadow_final_audit.py:10`
- `bybit_decision_lease_shadow_issue_contract_check.py:8`

**建議改法**：統一替換為環境變量 + 相對路徑：
```python
import os
_SRV_ROOT = os.getenv("OPENCLAW_SRV_ROOT", os.path.expanduser("~/BybitOpenClaw/srv"))
BASE = Path(os.path.join(_SRV_ROOT, "docker_projects/trading_services/runtime/bybit/thought_gate"))
```
或在模塊頂部建一個 `_resolve_base()` 共用函數。

#### 集群 B：market_data_processor/bybit_business_events/ — 20+ 個文件

同樣模式，路徑指向 `/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/...`

**代表文件**：
- `bybit_business_event_contract_check.py:23-24`
- `bybit_business_event_acceptance_suite.py:39-62`（20+ 個 Path 常量）
- `bybit_business_event_fixture_pack_builder.py:36`
- `bybit_business_event_replay_harness.py:37-39`
- `bybit_business_event_state_resolver.py:35-37`
- `bybit_business_event_ingestion_from_ws.py:30-34`
- `bybit_business_event_extract_from_ws_jsonl.py:25-26`
- `bybit_business_event_final_audit.py:29-39`（11 個 Path 常量）

**建議改法**：同集群 A，統一用 `_SRV_ROOT` 環境變量。

#### 集群 C：io_and_persistence/ — 15+ 個文件

**代表文件**：
- `bybit_private_ws_listener.py:14-17` — API key/secret + output dir
- `bybit_load_ws_jsonl_to_postgres.py:6`
- `bybit_public_connectivity_status_writer.py:6`
- `bybit_private_account_check.py:33,36`
- `bybit_private_ws_smoke_test.py:13-16`
- `bybit_private_positions_check.py:33,36`
- `bybit_ws_smoke_to_postgres.py:35-37` — 含 venv 路徑！
- `bybit_private_readonly_precheck.py:5-6`
- `bybit_snapshot_to_postgres.py:39-44`
- `bybit_private_execution_history_check.py:33,36`
- `bybit_normalize_latest_snapshot_to_postgres.py:28`
- `bybit_decision_packet_to_postgres.py:27`
- `bybit_private_rest_preflight_guard.py:36-41`
- `bybit_private_ws_smoke_test_v2.py:14-17`
- `bybit_private_order_history_check.py:33,36`
- `bybit_private_ws_listener_ctl.sh:4-6` — shell 腳本硬編碼 python 和路徑

#### 集群 D：ai_agents/bybit_thought_gate/ — 4 個文件

- `bybit_ai_route_selector_contract_check.py:21`
- `bybit_thought_gate_input_builder.py:59,68,71,74,77`（5 個字符串路徑）
- `bybit_ai_prompt_prep_builder.py:54`
- `bybit_ai_route_selector_builder.py:43`
- `bybit_thought_gate_decision_builder.py:51`

#### 集群 E：misc_tools/ — 4 個文件

- `bybit_demo_gate_final_audit_contract_check.py:40`
- `bybit_demo_gate_contract_contract_check.py:40`
- `bybit_demo_gate_readiness_contract_check.py:40`
- `bybit_decision_packet_pipeline.py:7-8`
- `bybit_demo_gate_handoff_builder.py:40`

### 1.2 `~/BybitOpenClaw/` 路徑（core app 中，需驗證）

這些使用 `os.path.expanduser("~")` ，在 macOS 上 `~` 會正確解析為 `/Users/<user>/`，
但前提是 macOS 上同樣存在 `~/BybitOpenClaw/` 目錄結構。

| 文件 | 行號 | 路徑 | 判定 |
|------|------|------|------|
| `bybit_demo_connector.py` | 110,117 | `~/BybitOpenClaw/secrets/secret_files/bybit/demo/api_key` | **需驗證** — 目錄結構須在 macOS 上重建 |
| `risk_manager.py` | 607-609 | `~/BybitOpenClaw/srv/settings/risk_control_rules/operator_risk_config.json` | **需驗證** — expanduser 可行，結構須存在 |
| `grafana_data_writer.py` | 52 | `~/BybitOpenClaw/secrets/compose_env/trading_services.env` | **需驗證** |
| `bybit_demo_sync.py` | 37 | `~/BybitOpenClaw/secrets/compose_env/trading_services.env` | **需驗證** |
| `auth.py` | 64 | `~/BybitOpenClaw/secrets/gui_auth.env` | **需驗證** |

**判定**: `expanduser("~")` 在 macOS 上正確工作（解析為 `/Users/<user>/`），但需要確保相同的目錄層次在新機器上存在。建議遷移時建一個 setup script 創建所有 secrets 目錄。

### 1.3 相對路徑 / `__file__` 基準路徑（可接受）

以下模塊使用 `os.path.dirname(__file__)` 構建相對路徑，跨平台安全：
- `_path_setup.py` — 5 級 dirname 上溯到 program_code/
- `evolution_auto_scheduler.py` — 同模式
- `pipeline_bridge.py:179-180` — `../runtime/strategy_state.json`
- `layer2_tools.py:653-658` — `../../observer_verdict_latest.json`
- `layer2_cost_tracker.py:87-88` — `../runtime/layer2_cost_state.json`
- `truth_source_registry.py:69-70` — 相對 app/ 目錄
- `experiment_ledger.py:63-64` — 相對 app/ 目錄
- `legacy_routes.py:109` — `Path(__file__).resolve().parent / "static"`
- `auth.py:101` — `Path(__file__).resolve().parent.parent / ".secrets" / "api_token"`

**判定**：全部 **可接受**，跨平台安全。

### 1.4 `/tmp/` 路徑使用

| 文件 | 用途 | macOS 影響 |
|------|------|------------|
| docs 中的 `.md` 文件 | 文檔範例 | 無影響 |
| `test_integration_phase8.py:38+` | `GovernanceHub(audit_dir="/tmp/test_gov")` | **需驗證** — macOS `/tmp` → `/private/tmp` symlink，測試可能需改用 `tempfile.mkdtemp()` |
| `test_experiment_ledger.py:786` | `/tmp/nonexistent_snapshot_xyz_12345.json` | 可接受（故意不存在的路徑） |
| `legacy_routes.py:214,632` | P1-14 已修復：用 `work_dir/logs/` 而非 `/tmp/` | **可接受** |

**判定**：測試中的 `/tmp/` 在 macOS 上通常正常（`/tmp` 是 `/private/tmp` 的 symlink），但建議改用 `tempfile` 標準庫以保持一致。

### 1.5 Shell 腳本中的硬編碼路徑

| 文件 | 行號 | 路徑 | 判定 |
|------|------|------|------|
| `cron_observer_cycle.sh` | 9 | `REPO="/home/ncyu/BybitOpenClaw/srv"` | **必須改** |
| `prune_dated_files.sh` | 6 | `BASE="/home/ncyu/BybitOpenClaw/srv"` | **必須改** |
| `run_with_trading_env.sh` | 12 | `VENV_DIR="/home/ncyu/srv/venvs/openclaw_bybit_ai"` | **必須改** |
| `bybit_private_ws_listener_ctl.sh` | 4-6 | Python bin + script + log 全部硬編碼 | **必須改** |
| `refresh_h0_upstream_and_diag_public_microstructure.sh` | 4,6-7 | cd + 多個路徑 | **必須改** |

**建議改法**：所有 shell 腳本改為 `SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"` + 相對路徑基準，或讀取 `$OPENCLAW_SRV_ROOT` 環境變量。

### 1.6 Virtualenv 路徑

| 文件 | 路徑 | 判定 |
|------|------|------|
| `bybit_ws_smoke_to_postgres.py:37` | `Path("/home/ncyu/srv/venvs/trading_ws/bin/python")` | **必須改** |
| `bybit_private_ws_listener_ctl.sh:4` | `"/home/ncyu/srv/venvs/trading_ws/bin/python"` | **必須改** |
| `run_with_trading_env.sh:12` | `VENV_DIR="/home/ncyu/srv/venvs/openclaw_bybit_ai"` | **必須改** |
| `cron_observer_cycle.sh:10` | `.venv/bin/python3`（相對） | **可接受** |
| `start_local.sh:37-69` | `.venv/`（相對） | **可接受** |

### 1.7 Systemd Unit 文件（必須改，macOS 不支持 systemd）

| 文件 | 內容 |
|------|------|
| `~/.config/systemd/user/openclaw-trading-api.service` | WorkingDirectory + ExecStart 全部硬編碼 `/home/ncyu/` |
| `~/.config/systemd/user/openclaw-gateway.service` | ExecStart 硬編碼 + **API keys 明文暴露在 Environment 行** |

**macOS 替代方案**：launchd plist（`~/Library/LaunchAgents/`）

**安全注意**：`openclaw-gateway.service` 第 14-15 行包含明文 OPENAI_API_KEY 和 ANTHROPIC_API_KEY。遷移時必須改用 Keychain 或 `.env` 文件引用。

### 1.8 settings/ 中的路徑

- `settings/system_notes/bybit_readonly_credentials_protocol_v1.md:22-23` — 文檔引用 `/home/ncyu/srv/settings/secret_files/`，需更新文檔。

### XP-1 改動風險評估

- **核心交易管線（control_api_v1/app/）**: 風險 **低** — 幾乎全部使用 `expanduser("~")` 或 `__file__` 相對路徑
- **歷史遺留模塊（decision_lease, business_events, io_and_persistence）**: 風險 **高** — ~80 處硬編碼，但這些模塊不在 live 管線中（Chapter A-K 階段的基礎設施腳本）
- **Shell 腳本**: 風險 **中** — 5+ 個腳本需要改，但都是輔助工具

### XP-1 建議改法

**方案：環境變量 + 共用 resolve 函數**

1. 新增環境變量 `OPENCLAW_SRV_ROOT`（默認 `~/BybitOpenClaw/srv`）
2. 建一個 `_resolve_paths.py` 共用模塊：
```python
import os
SRV_ROOT = os.getenv("OPENCLAW_SRV_ROOT", os.path.expanduser("~/BybitOpenClaw/srv"))
RUNTIME_BASE = os.path.join(SRV_ROOT, "docker_projects/trading_services/runtime/bybit")
SECRETS_BASE = os.path.join(os.path.expanduser("~"), "BybitOpenClaw/secrets")
```
3. 批量 sed 替換集群 A-E 中的硬編碼路徑
4. Shell 腳本改為讀取 `$OPENCLAW_SRV_ROOT` 或 `SCRIPT_DIR` 自動推導
5. Systemd → launchd plist 遷移

---

## XP-2：Ollama/LLM 直接調用掃描

### 2.1 Ollama 抽象層設計（可接受）

核心客戶端：`control_api_v1/app/ollama_client.py`
- 使用 `urllib.request` 標準庫（無第三方依賴）
- 默認 URL：`http://127.0.0.1:11434`（通過 `OLLAMA_BASE_URL` 環境變量可覆蓋）
- 默認模型：`qwen3.5:9b-q4_K_M`（通過 `OLLAMA_MODEL` 環境變量可覆蓋）
- 線程安全單例 + 連接池

**跨平台判定**：**完全可接受** — 純 HTTP 客戶端，macOS 上 Ollama 同樣監聽 `127.0.0.1:11434`。

### 2.2 所有 Ollama 引用路徑

| 調用方式 | 文件 | 判定 |
|---------|------|------|
| **通過抽象層** `get_ollama_client()` | `phase2_strategy_routes.py`, `layer2_routes.py`, `layer2_tools.py`, `layer2_engine.py` | **可接受** |
| **注入式** `ollama_client=` 構造參數 | `strategist_agent.py`, `analyst_agent.py`, `guardian_agent.py` | **可接受** |
| **setter 注入** `set_ollama_client()` | `pipeline_bridge.py` | **可接受** |
| **直接 URL** `localhost:11434` | `test_ollama_integration.py:57`（測試文件） | **可接受**（測試 mock） |

### 2.3 web-pilot 二進制路徑

`layer2_tools.py:399,405`：
```python
web_pilot = os.path.expanduser("~/.local/bin/web-pilot")
```

**判定**：**需驗證** — macOS 上 `~/.local/bin/` 可能不存在或 web-pilot 未安裝。建議改為 `shutil.which("web-pilot")` 先搜索 PATH，再回退到固定路徑。

### 2.4 openclaw CLI 二進制

`paper_trading_routes.py:1009-1011`：
```python
subprocess.run(["openclaw", "gateway", "usage-cost", "--json", "--days", "30"], ...)
```

**判定**：**需驗證** — 依賴 `openclaw` 在 PATH 中可用。macOS 上需確認 npm global 安裝路徑。

### XP-2 風險評估

**風險：極低** — Ollama 抽象層設計良好，所有調用通過 `OllamaClient` 單例。macOS 上 Ollama 行為一致（ARM 原生支持 M5 Ultra）。僅 web-pilot 和 openclaw CLI 需確認安裝。

---

## XP-3：系統服務依賴掃描

### 3.1 Systemd Unit 文件（必須改）

| 文件 | macOS 替代 |
|------|-----------|
| `~/.config/systemd/user/openclaw-trading-api.service` | `~/Library/LaunchAgents/com.openclaw.trading-api.plist` |
| `~/.config/systemd/user/openclaw-gateway.service` | `~/Library/LaunchAgents/com.openclaw.gateway.plist` |

**建議**：遷移為 launchd plist，或改用 `pm2` / `supervisord` 等跨平台進程管理器。

### 3.2 psutil 使用（需驗證）

只有一處生產代碼使用 psutil：

**`h0_gate.py:803-813`** — H0HealthWorker
```python
import psutil
cpu_pct = psutil.cpu_percent(interval=None)
mem = psutil.virtual_memory()
memory_available_mb = int(mem.available / (1024 * 1024))
```

**判定**：**可接受** — 已有 ImportError fallback（safe defaults）。psutil 在 macOS ARM 上完全支持，`virtual_memory()` 和 `cpu_percent()` API 跨平台一致。

### 3.3 subprocess 調用中的 Linux 特定命令

| 文件 | 命令 | macOS 兼容性 |
|------|------|-------------|
| `legacy_routes.py:231` | `bash script_path` | **可接受** — macOS 有 bash |
| `legacy_routes.py:219` | `kill PID` | **可接受** — macOS kill 語法一致 |
| `paper_trading_routes.py:1009` | `openclaw gateway usage-cost` | **需驗證** — CLI 需安裝 |
| `layer2_tools.py:407` | `web-pilot search` | **需驗證** — 二進制需安裝 |
| 多個 io_and_persistence 文件 | `psql` subprocess | **可接受** — macOS 有 psql |
| `bybit_observer_pipeline.py:21` | 通用 subprocess.run | **可接受** |

### 3.4 `/proc/` 和 `/sys/` 引用

僅一處：`test_experiment_ledger.py:899` — 用 `/proc/nonexistent_dir/` 作為不可寫路徑測試。

**判定**：**需驗證** — macOS 無 `/proc/`，但該測試的目的是驗證寫入不存在路徑時的失敗處理。macOS 上 `/proc/` 路徑確實不存在，測試仍會通過（FileNotFoundError/PermissionError）。

### 3.5 信號處理

| 文件 | 用法 | macOS 兼容性 |
|------|------|-------------|
| `bybit_private_ws_listener.py:114-115` | `signal.SIGINT` + `signal.SIGTERM` | **可接受** — 標準 POSIX 信號 |
| `auto_bridge_observer_to_runtime_snapshot.py:536-537` | 同上 | **可接受** |
| `legacy_routes.py:206` | `import signal`（用於 kill） | **可接受** |

**判定**：全部使用 POSIX 標準信號，macOS 完全兼容。無 Linux 特有信號（如 SIGRTMIN）。

### 3.6 tempfile 使用

所有 tempfile 調用使用 Python 標準庫 `tempfile.mkstemp()` / `tempfile.mkdtemp()`，跨平台安全。

### XP-3 風險評估

**風險：中** — 主要風險在 systemd → launchd 遷移。生產代碼本身無 Linux 特有 API。

---

## XP-4：依賴審計

### 4.1 requirements.txt 內容

文件：`program_code/exchange_connectors/bybit_connector/control_api_v1/requirements.txt`

| 依賴 | 版本 | macOS ARM 兼容性 |
|------|------|----------------|
| fastapi>=0.115.0 | 純 Python | **可接受** |
| uvicorn[standard]>=0.27.0 | 純 Python + uvloop | **需驗證** — uvloop 在 macOS ARM 有原生支持 |
| pydantic>=2.11.0 | Rust 擴展 | **可接受** — 有 macOS ARM wheel |
| httpx>=0.28.0 | 純 Python | **可接受** |
| slowapi>=0.1.9 | 純 Python | **可接受** |
| websocket-client>=1.8.0 | 純 Python | **可接受** |
| psutil>=5.9.0 | C 擴展 | **可接受** — 有 macOS ARM wheel |
| beautifulsoup4>=4.12.0 | 純 Python | **可接受** |
| pytest>=8.0.0 | 純 Python | **可接受** |
| pytest-asyncio>=0.23.0 | 純 Python | **可接受** |

### 4.2 未列入 requirements 但實際使用的標準庫模塊

以下全部是 Python 標準庫，跨平台安全：
- `urllib.request` / `urllib.error` — ollama_client
- `subprocess` — layer2_tools, legacy_routes, 多個 io 腳本
- `signal` — ws_listener, auto_bridge
- `threading` — ollama_client, pipeline_bridge, h0_gate, 等
- `asyncio` — 全系統
- `tempfile` — legacy_routes, state_store, paper_trading_engine
- `json`, `os`, `pathlib`, `time`, `logging` — 全系統

### 4.3 隱含依賴（需驗證）

| 依賴 | 用途 | macOS 兼容性 |
|------|------|-------------|
| `jq` | shell 腳本 JSON 解析 | **需安裝** — `brew install jq` |
| `bc` | cron_daily_report.sh 計算 | **可接受** — macOS 內建 |
| `curl` | shell 腳本 API 調用 | **可接受** — macOS 內建 |
| `psql` | 多個 _to_postgres 腳本 | **需安裝** — `brew install postgresql` |
| `web-pilot` | layer2_tools L4 搜索 | **需安裝** |
| `openclaw` CLI | paper_trading_routes AI cost | **需安裝** — npm global |
| Ollama | 本地 LLM | **需安裝** — macOS ARM 原生支持 |
| PostgreSQL | 數據存儲 | **需安裝** — `brew install postgresql` 或 Docker |

### XP-4 風險評估

**風險：低** — 所有 Python 依賴有 macOS ARM wheel。外部工具（jq, psql, Ollama）需手動安裝但都有 macOS 版本。

---

## 遷移優先級與執行計劃

### Phase 1：零改動可運行（30 分鐘）

在 macOS 上：
1. 克隆 repo 到 `~/BybitOpenClaw/srv/`
2. 重建 secrets 目錄結構（`~/BybitOpenClaw/secrets/`）
3. 建 venv + `pip install -r requirements.txt`
4. `export OPENCLAW_SRV_ROOT=~/BybitOpenClaw/srv`
5. 安裝 Ollama（`brew install ollama`，拉 qwen3.5 模型）
6. 核心 API 應可直接啟動（`uvicorn app.main:app`）

**預計結果**：control_api_v1 立即可用。歷史遺留腳本會失敗但不影響交易管線。

### Phase 2：環境變量化（2-3 小時，~80 處改動）

1. 新增 `_resolve_paths.py` 或環境變量 `OPENCLAW_SRV_ROOT`
2. 批量替換集群 A-E 的硬編碼路徑
3. 修復 5+ 個 shell 腳本的硬編碼路徑

### Phase 3：服務管理遷移（1-2 小時）

1. 建 launchd plist 替代 systemd units
2. API key 從明文 Environment → Keychain 或 `.env` 文件

### Phase 4：驗證（2 小時）

1. 全量 pytest 回歸
2. Paper Trading 端到端冒煙
3. Shell 腳本逐一驗證

---

## 測試策略

### XP-1 路徑改動驗證
- 全量 pytest：`python3 -m pytest --ignore=database_files -q`（3703 tests 基準線）
- 手動驗證：啟動 Paper Trading session → 下單 → 止損觸發 → 學習記錄
- Shell 腳本：逐一在 macOS 上 dry-run

### XP-2 Ollama 驗證
- `curl http://127.0.0.1:11434/api/tags` 確認模型列表
- 觸發一次 L1 edge filter（通過 Paper Trading 信號流）
- M5 Ultra 上的推理延遲基準測試（預計比 Ubuntu CPU 快 3-5x）

### XP-3 服務驗證
- launchd plist load/unload 測試
- 進程自動重啟測試
- psutil 採樣結果對比

### XP-4 依賴驗證
- `pip check` 確認無衝突
- `brew list` 確認外部工具就位

---

## 附錄：安全發現

**CRITICAL**：`~/.config/systemd/user/openclaw-gateway.service` 第 14-15 行包含明文 API keys：
```
Environment=OPENAI_API_KEY=sk-proj-kRAWo...
Environment=ANTHROPIC_API_KEY=sk-ant-api03-sOQq...
```
這些文件在 `~/.config/systemd/user/` 下，**不在 git repo 內**，不會洩漏到 GitHub。
但遷移到 macOS 時仍建議改用 Keychain 或 `.env` 文件引用，避免明文存於 plist 中。
