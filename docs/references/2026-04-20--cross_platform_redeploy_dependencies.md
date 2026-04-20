# Cross-Platform Redeploy — Dependency Reference
# 跨平台重部署 — 依賴參考

> **目的**：記錄把本倉庫從 Linux 主機搬到 macOS（Apple Silicon, `aarch64-apple-darwin`）開發/運行所需的全部依賴與平台差異。
> **適用**：clean-machine 冷裝；既有 Linux 部署不需重跑此流程。
> **最後更新**：2026-04-20
> **權威來源**：`requirements-ml.txt` · `program_code/exchange_connectors/bybit_connector/control_api_v1/requirements.txt` · `rust/Cargo.toml` · `rust/rust-toolchain.toml` · `docker/docker-compose.test.yml`

---

## 1. 快速結論

- **無系統庫外部依賴**：Rust 端用 `rustls`（非 `openssl-sys`）；Python 套件全有 Apple Silicon 預編譯 wheel。
- **不需要 Node.js**：控制層是 FastAPI（純 Python），無前端 build step。
- **systemd 單元用不了**：Linux `/etc/systemd/system/*.service`（`engine_watchdog` 等）在 Mac 上須改成 launchd `.plist` 或手動跑 `helper_scripts/restart_all.sh`。
- **`/tmp` 行為差異要處理**：Mac `/tmp` 是 `/private/tmp` symlink 且不自動清；必須設 `OPENCLAW_DATA_DIR`。
- **live 憑證要重簽**：`authorization.json` canonical payload 含 env vars，Linux→Mac 前後 env 不一致 → HMAC 驗簽失敗（見 §7）。

---

## 2. 核心運行時版本

| 組件 | 版本 | 來源 |
|---|---|---|
| Rust toolchain | `stable` + `rustfmt` + `clippy` | `rust/rust-toolchain.toml` |
| Rust target | `aarch64-apple-darwin`（M 系列原生） | memory `project_mac_deployment_target` |
| Python | 3.12+（當前 Linux 3.12.3） | runtime |
| Node / npm | ❌ 不需要 | — |
| PostgreSQL / TimescaleDB | pg16 + TimescaleDB | `docker/docker-compose.test.yml` |

---

## 3. macOS 安裝步驟

### 3.1 Homebrew 套件

```bash
# 核心工具
brew install rustup-init postgresql@16 ollama git python@3.12

# 可選：Docker Desktop for Mac（跑 timescaledb 測試容器時需要）
brew install --cask docker
```

**特別說明**：
- `openssl`：❌ 不需要安裝。`openclaw_engine/Cargo.toml` 的 `reqwest`/`tokio-tungstenite`/`sqlx` 全部走 `rustls` TLS。
- `libpq`：❌ 不需要。`psycopg2-binary` 帶預編譯 libpq。
- `cmake` / `clang`：❌ 不需要（Xcode Command Line Tools 夠用）。

### 3.2 Xcode Command Line Tools

```bash
xcode-select --install
```

### 3.3 Rust toolchain

```bash
rustup-init -y --default-toolchain stable
source "$HOME/.cargo/env"
rustup component add rustfmt clippy
rustup target add aarch64-apple-darwin
# 可選：Intel Mac 跨編譯
# rustup target add x86_64-apple-darwin
```

### 3.4 Python 虛擬環境

```bash
cd ~/BybitOpenClaw/srv
python3.12 -m venv venvs/mac_dev
source venvs/mac_dev/bin/activate

pip install --upgrade pip wheel
pip install -r requirements-ml.txt
pip install -r program_code/exchange_connectors/bybit_connector/control_api_v1/requirements.txt
```

所有套件 Apple Silicon wheel 齊備（lightgbm、onnxruntime、psycopg2-binary、psutil、scikit-learn 等），無需編譯 C 擴展。

### 3.5 Ollama + 本地 LLM

```bash
brew install ollama
brew services start ollama

# Settings → Model Memory：按統一記憶體配置
#   128GB Mac → 預留 ~54GB 給模型（對齊 project_hardware_constraints）
#   64GB Mac  → ~30GB
#   32GB Mac  → ~16GB，只能跑小模型

# 模型缺失時代碼降級到啟發式（見 ollama_client fallback），不 crash
```

### 3.6 資料庫（兩種路徑擇一）

**路徑 A — Docker（推薦用於測試）**
```bash
cd ~/BybitOpenClaw/srv
docker compose -f docker/docker-compose.test.yml up -d
# TimescaleDB pg16，port 15432:5432，DB openclaw_test
```

**路徑 B — 本機 PostgreSQL**
```bash
brew services start postgresql@16
# 若要 TimescaleDB 擴充：
#   brew tap timescale/tap && brew install timescaledb
#   依 timescaledb-tune 輸出調 postgresql.conf
```

---

## 4. Rust 構建

```bash
cd ~/BybitOpenClaw/srv/rust
cargo build --release
```

Cargo 會自動拉 `ort`（ONNX Runtime）的 macOS 預編譯 `libonnxruntime.dylib`（由 `download-binaries` + `copy-dylibs` feature 提供）。無需手動安裝 ONNX Runtime。

---

## 5. 必要環境變數（Mac 版 `.zshrc`）

```bash
# Runtime 路徑（Mac 必設，Linux fallback 到 /tmp/openclaw）
export OPENCLAW_DATA_DIR="$HOME/.openclaw_runtime"
export OPENCLAW_BASE_DIR="$HOME/BybitOpenClaw/srv"
export OPENCLAW_SECRETS_DIR="$OPENCLAW_BASE_DIR/settings/secret_files/bybit"

# IPC HMAC secret（Python↔Rust 綁定契約，不可洩漏）
# export OPENCLAW_IPC_SECRET="<與 Linux 同一值，或重簽 authorization.json>"

# Live 硬鎖（只在真實 Mainnet 部署時打開）
# export OPENCLAW_ALLOW_MAINNET=1

# Paper pipeline 預設關閉（需要時才打開）
# export OPENCLAW_ENABLE_PAPER=1

# 便利別名
alias oc-clean-runtime='rm -f "$OPENCLAW_DATA_DIR"/{*.sock,engine_maintenance.flag}'
```

初始化：
```bash
mkdir -p "$OPENCLAW_DATA_DIR"
oc-clean-runtime
```

---

## 6. Linux ↔ Mac 差異對照表

| 功能 | Linux | macOS 替代 |
|---|---|---|
| 服務管理 | `systemctl start/stop openclaw-*` | launchd `.plist` 於 `~/Library/LaunchAgents/` 或手動 `restart_all.sh` |
| 引擎 watchdog | `engine_watchdog.service` (systemd unit) | 手動 `restart_all.sh` 或寫 `.plist`（尚未實作範本） |
| 日誌路徑 | `/var/log/openclaw-*` | `$OPENCLAW_DATA_DIR/engine_logs/` |
| IPC socket | `/tmp/openclaw/engine.sock` | `$OPENCLAW_DATA_DIR/engine.sock` |
| `/tmp` 生命週期 | 開機清空 | 不清空 → 舊 socket 會擋新 process |
| 套件管理 | `apt` / `dpkg` | `brew` |
| Python 安裝 | 系統 python3 | `brew install python@3.12` 或 `pyenv` |

---

## 7. Live 憑證跨平台遷移（HMAC 驗簽陷阱）

**LIVE-GATE-BINDING-1** 要求 `authorization.json` 的 canonical payload 對 Python/Rust byte-for-byte 一致，`OPENCLAW_IPC_SECRET` 為 HMAC key。

跨平台搬遷時：

1. **同一 `OPENCLAW_IPC_SECRET`**：Linux 與 Mac 必須用相同值，否則驗簽 401。
2. **`envs_allowed` 欄位**：canonical payload 含 Python 側取樣的 env vars sort+dedup，Linux↔Mac 如果有 env 差異（例如 `PATH` 細節）不會影響（Python 只選特定白名單 envs），但若白名單本身調整過，必須 **從 Python 端 renew/approve 路由重新簽發**，不能直接 `cp` 檔案。
3. **Mac 部署步驟**：
   - 先完成 Python 啟動 + Operator 角色登入
   - 經 Python `/api/v1/system/approve_live_authorization` 路由重新簽 `authorization.json`
   - Rust 端 `build_exchange_pipeline` 啟動時會同步驗簽（`startup.rs:467-494`）

---

## 8. 還沒解決的 Mac 部署缺口

| 項目 | 狀態 | 備註 |
|---|---|---|
| `helper_scripts/mac_bootstrap.sh` | ⏳ TODO | 一鍵安裝腳本（跟本 README 配套） |
| launchd `.plist` 範本 | ⏳ 未寫 | 對應 Linux `engine_watchdog.service` 等 |
| `/home/ncyu/...` 硬編碼殘留 | ⚠️ 未 100% 清 | CLAUDE.md §七 要求但未全查；搬遷前 `grep -r /home/ncyu rust/ program_code/` 一次 |
| GUI dev hot-reload | 未驗證 | Mac uvicorn `--reload` 路徑 watch 行為與 Linux inotify 差異 |

---

## 9. 驗證清單（冷裝完成後）

```bash
# 工具鏈
rustc --version      # 預期：stable-aarch64-apple-darwin
python3 --version    # 預期：Python 3.12+
ollama --version     # 預期：ollama version ...

# 構建
cd ~/BybitOpenClaw/srv/rust && cargo build --release   # 應成功

# 測試
cd ~/BybitOpenClaw/srv
pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests -x   # smoke
cargo test -p openclaw_engine --lib                                                # Rust smoke

# Runtime 目錄
ls -la "$OPENCLAW_DATA_DIR"   # 應存在且可寫
```

---

## 參考

- CLAUDE.md §六「跨平台 Runtime 路徑」
- CLAUDE.md §七「跨平台兼容性」
- memory: `project_mac_deployment_target.md` / `project_hardware_constraints.md` / `feedback_cross_platform.md`
- LIVE-GATE-BINDING-1 實作：`docs/worklogs/2026-04-18--live_gate_binding_1_implementation.md`
