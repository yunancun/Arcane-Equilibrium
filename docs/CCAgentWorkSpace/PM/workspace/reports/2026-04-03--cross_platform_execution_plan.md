# XP-1~4 跨平台兼容性 — 執行計劃
# PM 制定 · 2026-04-03
# 測試基準：3703 passed · 目標：0 回歸

---

## 1. 依賴分析與執行順序

```
XP-1（路徑）──────────┐
XP-2（LLM 抽象預審）──┤── 全部可並行（無互相依賴）
XP-3（部署文檔）───────┤
XP-4（requirements）───┘
```

**結論：4 個任務完全獨立，可 4 E1 全並行。**

理由：
- XP-1 改路徑字符串，不改模塊接口
- XP-2 僅標記調用點（Phase 1 才正式實現 ABC 接口），不改代碼
- XP-3 純文檔產出
- XP-4 改 requirements.txt + 加平台守衛，不影響路徑或 LLM

唯一微弱耦合：XP-1 若發現 Ollama 路徑硬編碼也歸 XP-2 處理 — 但實際已確認 `ollama_client.py` 只有 1 處 `DEFAULT_OLLAMA_BASE_URL`，XP-2 標記即可，XP-1 不重複處理。

---

## 2. 風險矩陣

| 任務 | 風險等級 | 影響面 | 主要風險 | 緩解措施 |
|------|---------|--------|---------|---------|
| **XP-1** | **HIGH** | 189 .py + 47 .sh + 1 docker-compose | 改錯路徑 → 啟動失敗/config 讀不到/日誌寫不出 | 分三批：app 層(2) → legacy scripts(187+47) → config(1)；每批跑測試 |
| **XP-2** | **LOW** | 僅標記，不改代碼 | 標記遺漏 | grep 驗證覆蓋率 |
| **XP-3** | **ZERO** | 新建文檔 | 無 | N/A |
| **XP-4** | **LOW** | 1 個 requirements.txt + 少量 conditional import | 版本衝突；平台守衛遺漏 | pip freeze 對比；psutil 已有，只需確認 |

### XP-1 風險細化

掃描結果分類：
- **control_api_v1 app 層**：2 個文件（test_auto_bridge.py + auto_bridge script）— 高優先
- **Legacy pipeline/event/risk 模塊**：~187 個 .py — 大部分是 `MODULE_NOTE` 或 `contract_check` 中的路徑引用，非運行時依賴
- **Shell 腳本**：47 個 .sh — `cd /home/ncyu/...` 模式，需改為 `SCRIPT_DIR` 相對路徑
- **Docker/config**：1 個 docker-compose.yml — volume mount 路徑

**關鍵判斷**：大部分 `/home/ncyu` 出現在 legacy pipeline 模塊的 `MODULE_NOTE` 文檔字符串和 `contract_check` 輸出路徑中。這些是**信息性引用**，不是運行時路徑依賴。真正的運行時路徑硬編碼集中在：
1. Shell 腳本的 `cd` / `source` / `PYTHONPATH` 設定
2. `auto_bridge` 腳本的文件讀寫路徑
3. docker-compose.yml 的 volume mount

---

## 3. 安全改動策略

### 3.1 分支策略
```
feature branch: feature/xp-cross-platform
從 main 分支，完成後 merge back
```

### 3.2 改動順序（XP-1 專用，最高風險項）

**Phase A — 定義替換規則（先寫不改）**：
```python
# 替換模式：
# /home/ncyu/BybitOpenClaw/srv  → PROJECT_ROOT（os.environ 或 pathlib 推導）
# /home/ncyu/srv               → PROJECT_ROOT（symlink，同上）
# /home/ncyu                   → HOME（os.environ["HOME"]）
```

**Phase B — 按影響面分批改**：
1. **Batch 1**（app 層 2 文件）→ 跑全量測試 → 確認 3703 passed
2. **Batch 2**（shell 腳本 47 文件）→ 跑 shell 語法檢查 + 全量測試
3. **Batch 3**（legacy pipeline 187 .py 文檔字符串）→ 跑全量測試
4. **Batch 4**（docker-compose 1 文件）→ 驗證 compose config

**Phase C — 驗證**：
```bash
# 確認零殘留
grep -r '/home/ncyu' --include='*.py' --include='*.sh' | grep -v '.md' | grep -v '__pycache__'
# 全量測試
python3 -m pytest --ignore=database_files -q --tb=no
```

### 3.3 回滾方案
```bash
git stash   # 或
git checkout main -- <file>  # 單文件回滾
# feature branch 整體放棄：git branch -D feature/xp-cross-platform
```

---

## 4. E1 派發與並行度

### 最大並行度：4（4 個 E1 完全獨立）

---

### E1-Alpha：XP-1 路徑硬編碼修復（4h）

**指令**：
1. 在 `app/` 或項目公共位置新增 `PROJECT_ROOT` 常量（`pathlib.Path(__file__).resolve().parents[N]` 或 `os.environ.get("OPENCLAW_PROJECT_ROOT", ...)`）
2. **Batch 1**：修復 `control_api_v1/` 下 2 個 .py 文件的運行時路徑
3. **Batch 2**：修復 47 個 .sh 腳本，統一為 `SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"` + 相對路徑
4. **Batch 3**：修復 187 個 legacy .py 文件中的 `MODULE_NOTE` 路徑引用 — **注意：這些大部分是文檔字符串，用 `sed` 批量替換即可，但必須跑測試確認零破壞**
5. **Batch 4**：docker-compose.yml volume mount 改環境變量
6. 每 Batch 完成跑一次 `python3 -m pytest --ignore=database_files -q --tb=no`，確認 ≥ 3703 passed

**驗收**：
```bash
# 零殘留（排除 .md 文檔和 .git）
grep -rn '/home/ncyu' --include='*.py' --include='*.sh' --include='*.yml' --include='*.json' | wc -l
# 期望：0
```

**風險提醒**：
- Shell 腳本中 `source /home/ncyu/.../run_with_trading_env.sh` 是運行時依賴，改錯會導致所有腳本失敗
- `PYTHONPATH` 設定必須同步改
- 不要動 `.md` 文檔中的路徑引用（那些是歷史記錄）

---

### E1-Beta：XP-2 LLM 抽象層預審（2h）

**指令**：
1. 掃描所有直接引用 Ollama 的代碼：
   - `ollama_client.py`：已確認 `DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"` — 標記為 Phase 1.8 ABC 候選
   - `phase2_strategy_routes.py` / `data_source_enforcer.py` / `perception_data_plane.py`：掃描 Ollama 調用方式
2. 產出標記文檔：`docs/decisions/2026-04-03--llm_abstraction_audit.md`
   - 列出每個調用點：文件、行號、調用方式（直接 HTTP / client wrapper）
   - 標記哪些需要走 ABC 接口（Phase 1.8）
   - 標記哪些已經通過 `ollama_client.py` 封裝（低改動）
3. **不改任何生產代碼**（Phase 1.8 才改）

**驗收**：
- 產出文檔完整
- grep 確認所有 Ollama 調用點已覆蓋
- 測試不跑（無代碼改動）

---

### E1-Gamma：XP-3 服務部署遷移文檔（2h）

**指令**：
1. 新建 `helper_scripts/deploy/README.md`
2. 內容包含：
   - 環境變量清單（從 shell 腳本和 Python 代碼中提取所有 `os.environ` / `os.getenv`）
   - 端口配置（8000 API / 11434 Ollama / 5432 Postgres / 3000 Grafana）
   - systemd → launchd 對照表（service file → plist file 映射）
   - 啟動順序：Postgres → Ollama → API Server → Market Data
   - 依賴服務列表及版本要求
   - macOS 特殊注意事項（brew install / launchctl 命令）
3. 中英雙語

**驗收**：
- 文檔存在且內容完整
- 不需要跑測試（純文檔）

---

### E1-Delta：XP-4 requirements.txt 審計（1h）

**指令**：
1. 掃描 `control_api_v1/` 所有 .py 文件的 `import` 語句
2. 對比 `requirements.txt`，找出：
   - 缺失項（代碼 import 了但 requirements 沒列）
   - 多餘項（requirements 列了但代碼沒用）
3. 檢查 Linux-only 依賴：
   - `psutil`：跨平台，無需守衛 ✅
   - 確認無其他 Linux-only 包（如 `python-systemd`、`inotify` 等）
4. 如有缺失項，補入 requirements.txt
5. 如有 Linux-only 依賴，在對應 .py 文件加 `sys.platform` 條件 import

**驗收**：
```bash
# 跑全量測試
python3 -m pytest --ignore=database_files -q --tb=no
# 期望：≥ 3703 passed
```

---

## 5. 壁鐘時間估算

```
Phase 1: E1 並行執行（4 Agent 同時）
  XP-1: 4h ──────────────────────────┐
  XP-2: 2h ──────────┐              │
  XP-3: 2h ──────────┤ 2h 完成      │
  XP-4: 1h ─┐ 1h    │              │
             完成     完成            │
                                     4h 完成（瓶頸）
  Phase 1 壁鐘 = 4h（由 XP-1 決定）

Phase 2: E2 代碼審查
  XP-1 審查: 1.5h（最大改動）
  XP-2 審查: 0.5h（僅文檔，快速）
  XP-3 審查: 0.5h（僅文檔）
  XP-4 審查: 0.5h
  E2 壁鐘 = 1.5h（可並行審查不同 XP）

Phase 3: E4 全量回歸
  全量測試一次: ~0.5h
  E4 壁鐘 = 0.5h

Phase 4: PM 確認 + commit
  壁鐘 = 0.25h

────────────────────────────
總壁鐘時間 ≈ 6.25h（~6.5h 含 buffer）
總人時     ≈ 9h + 3h（E2+E4）= 12h
```

### 關鍵路徑
```
XP-1 E1 執行（4h）→ E2 審查（1.5h）→ E4 回歸（0.5h）→ PM 確認（0.25h）= 6.25h
```

XP-2/3/4 不在關鍵路徑上，它們的 E2 審查可與 XP-1 E2 並行。

---

## 6. 風險緩解決策摘要

| # | 決策 | 理由 |
|---|------|------|
| 1 | XP-1 分 4 batch 逐批改 + 測試 | 189+47 文件一次改完回歸失敗無法定位 |
| 2 | Legacy .py 的 MODULE_NOTE 用 sed 批量替換 | 人工改 187 文件不現實；但替換後必須跑測試 |
| 3 | Shell 腳本用 SCRIPT_DIR 模式 | 業界標準，可移植，不依賴任何用戶名 |
| 4 | XP-2 只標記不改 | Phase 1.8 才正式實現 ABC，現在改會引入未測試的抽象層 |
| 5 | Feature branch | 主分支隨時可回滾 |
| 6 | .md 文檔路徑不改 | 歷史記錄，改了反而失去追溯價值 |

---

## 7. 成功標準

```
[ ] XP-1：grep '/home/ncyu' *.py *.sh *.yml = 0 結果（排除 .md）
[ ] XP-2：產出 LLM 調用點標記文檔，覆蓋率 100%
[ ] XP-3：helper_scripts/deploy/README.md 存在且完整
[ ] XP-4：requirements.txt 與實際 import 100% 對齊
[ ] 全量測試：≥ 3703 passed，0 新回歸
[ ] E2 審查通過
[ ] E4 回歸通過
```
