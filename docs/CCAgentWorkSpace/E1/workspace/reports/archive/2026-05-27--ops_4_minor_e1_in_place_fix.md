# E1 OPS-4 systemd minor in-place fix · 2026-05-27

**Scope**: E2 review (`2026-05-27--ops_4_systemd_e2_review.md`) §6 列 1 MED + 3 LOW，E1 直接在 commit `65e78437` working tree 上補；不重 round，不 commit。

**Files touched**: 4

| 檔 | 用途 |
|---|---|
| `helper_scripts/systemd/openclaw-engine.service` | MED-1 刪空 Requires= directive |
| `helper_scripts/systemd/install_engine_service.sh` | LOW-2 verify warn/error 區分 + LOW-3 root guard |
| `helper_scripts/systemd/install_watchdog_service.sh` | LOW-2 verify warn/error 區分 + LOW-3 root guard |
| `helper_scripts/systemd/README.md` | LOW-4 reset-failed recovery 提示 |

---

## §1 4 fix LOC 變動矩陣

| # | 嚴重 | 檔:行 | 變動 | LOC |
|---|---|---|---|---|
| 1 | MED | `openclaw-engine.service:38` | 刪 `Requires=` 空值，改為注釋說明 | -1/+1（淨 0；行號不變）|
| 2a | LOW | `install_engine_service.sh:88-92 → 88-103` | `systemd-analyze verify` 失敗時 grep stdout：含 `Error` → exit 11；只 Warning → 繼續 | +11 LOC |
| 2b | LOW | `install_watchdog_service.sh:105-108 → 105-121` | 同 2a 邏輯 | +14 LOC |
| 3a | LOW | `install_engine_service.sh:59-66`（新增於 id -u 檢查後）| `[[ "$ENGINE_USER" == "root" ]] && exit 12` + 提示 | +8 LOC |
| 3b | LOW | `install_watchdog_service.sh:78-85`（新增於 id -u 檢查後）| 同 3a | +8 LOC |
| 4 | LOW | `README.md §B end of code block` | 補 `reset-failed` recovery 兩行命令 + 中文說明 | +5 LOC |

**合計**：+47 LOC / -1 LOC；無 logic mutation（僅補 guard + 文字）。

**exit code 表更新（須記於 README 後續 follow-up，本任務範圍外不動）**：
- engine install：原 1-9 → 新增 11 (verify Error) + 12 (root user)
- watchdog install：原 1-9 → 新增 11 (verify Error) + 12 (root user)

---

## §2 驗證結果

### bash -n syntax
```
bash -n install_engine_service.sh  → PASS（engine PASS）
bash -n install_watchdog_service.sh → PASS（watchdog PASS）
```

### systemd-analyze verify openclaw-engine.service
**未在 Mac 跑**（`command -v systemd-analyze` 在 Darwin 25.5.0 空輸出，systemd 不存 macOS）。

E4 regression / operator deploy 時須於 Linux trade-core 跑：
```bash
ssh trade-core "sudo systemd-analyze verify /etc/systemd/system/openclaw-engine.service"
# 預期：刪 Requires= 空 directive 後，warn 應消失（或剩 Documentation file:// 提示）
```

### Requires= 刪除確認
```
$ grep -n "Requires" openclaw-engine.service
38:# 不設 Requires= — 故意無硬依賴，systemd 空值 directive 會 warn，整行省略才合法
```
僅注釋說明，無 directive；空 directive 移除 confirmed。

### 跨平台硬編碼 grep
`/home/ncyu` 11 hit 全在注釋（example / 占位符提示文字）；0 logic line 違反。**與 E2 review §1 cross-verify 完全一致**。

### root user guard 邏輯驗證（dry run）
- 正常 sudo + 非 root user → `SUDO_USER` 帶非 root 值 → skip guard
- `sudo` 由 root 觸發 → `SUDO_USER=root` 或 fallback `id -un=root` → guard hit → exit 12
- 顯式 `export ENGINE_USER=root` → guard hit → exit 12

### verify warn vs error 邏輯驗證（dry run）
- verify rc=0 → skip 區段
- verify rc≠0 + stdout 含 "Warning" 不含 "Error" → echo 訊息 + 繼續
- verify rc≠0 + stdout 含 "Error" → echo 訊息 + exit 11
- 邏輯用 `grep -qi 'Error'` 大小寫不敏感，匹配 systemd-analyze 已知輸出格式（"Error: ..." / "error in" 等）

---

## §3 Deploy verification SOP unchanged confirm

E2 review §6 結論「不重 round；無 logic 變動」成立：

- **無 PG schema / IPC contract / hot path 改動** → engine restart 行為不變
- **無 Rust binary 改動** → `--rebuild` 流程不變
- **install script exit code 擴張**（11/12 新增） → operator runbook 文字未更新（exit code 對照表非本任務範圍；建議 follow-up TODO）
- **README §B 新增 reset-failed 提示** → 純文字補充，不改既有 enable/start 鏈

E4 regression 動作不變（per E2 §6 結論）：
1. `bash -n install_engine_service.sh install_watchdog_service.sh` 重跑 → PASS（本 report §2 已驗）
2. 渲染 README.md（GitHub / VSCode preview）confirm §B reset-failed block 無 markdown 破損
3. **Linux 端**（operator）：`systemd-analyze verify openclaw-engine.service` 重跑 → 預期 warning count 減少（少了空 Requires= 警告）

---

## §4 不確定 / Follow-up

1. **systemd-analyze 對「整行刪除 Requires=」是否完全靜默** — 未在 Mac 驗證；trade-core 演練時若仍有「Documentation file://」warning，屬非 blocker（E2 review §1 已預期）
2. **exit code 文件化** — README 未列各 exit code 對照表（1-12）；建議 follow-up TODO 補
3. **`grep -qi 'Error'` 誤匹配風險** — 若 systemd-analyze 輸出 `"...some-feature.Error.code..."` 形式可能誤判；當前 systemd 226+ 輸出格式 `Warning: ...` / `Error: ...` 為主，誤判概率極低
4. **root guard 在容器化 Linux（如 LXC unprivileged）的行為** — 若容器內 UID=root mapping 到 host 非 root，本 guard 仍會擋；非當前部署目標但未來 follow-up 須評估

---

## §5 Operator 下一步

1. E4 regression：本 report §3 三項
2. 若 E4 PASS → PM 統一 commit + push（4 file 變動 + 本 report）
3. Deploy 時走 E2 review §6 既有 SOP（無變化）

---

E1 IMPLEMENTATION DONE: 待 E4 regression（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-27--ops_4_minor_e1_in_place_fix.md`）
