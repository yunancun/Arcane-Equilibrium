# PM Sign-off — OPS-2 Phase-2 cutover(merge-ready;deploy operator-gated)

**日期** 2026-06-10 ｜ **branch** `fix/ops2-phase2-cutover`(base main `28e376c0`)｜ **commits** `a3d27729`→`cf1b9320`→`e34a8772`→`823e53ad`(未 push 未 merge)

## 1. 鏈完成度(全角色)

| 角色 | verdict | 要點 |
|---|---|---|
| E1 | DONE `a3d27729` | 移除 fallback+WARN 機制;env 缺失 fail-loud;Rust 4154/1(flake)+Py 62/0 |
| E2 第 1 輪 | RETURN(1H/1M/1L) | HIGH=漏掃 collateral 測試(base-vs-HEAD diff 66→67 抓到);production 本體 mutation 驗證全對 |
| E1 fix | DONE `cf1b9320` | 三項修畢;Rust 4155/0;Py 全套 base-diff 歸零(66↔66 逐條一致) |
| re-E2 | **ACCEPT** | 0 漂移(diff 恰 3 檔);rename 零 caller 影響實證;E1 數字 0 處不符 |
| E4 | **PASS** `e34a8772` | 兩端全套×2 輪;測試數名字級對賬 0 靜默消失;mock 檢查 gate-chain 非短路(毒注 bite 親驗);+1 永久負向測試;stress flake 獨立裁定=環境性(HEAD 均值不劣於 base) |
| CC | **APPROVE-CONDITIONAL(A-)** | 16/16+9/9+硬邊界 0 觸碰,0 BLOCKER;G5 強化方向;4 條件見 §3 |
| BB | **SIGN-OFF(0 FLAG)** | Bybit API surface 0 觸碰 VERIFIED;runbook Bybit 側段落未受影響;與 OP-1 無順序耦合;字典 0 drift;3 INFO 全記錄 |
| PM | **APPROVE(merge-ready)** | 本報告;deploy 仍 operator-gated |

E2 advisory A1(panic 被 LIVE-GATE-BINDING-1 post-dominate→實際症狀=live 拒 spawn 非 panic 阻 boot)已折進 `823e53ad` 措辭校準。

## 2. C-A 證據包(soak WARN=0,CC 條件)

**§13.1 grep 原樣輸出**(2026-06-10 10:19Z,ssh trade-core):
```
grep -c ops2_secret_split_phase1_fallback /tmp/openclaw/engine.log /tmp/openclaw/api.log
/tmp/openclaw/engine.log:0
/tmp/openclaw/api.log:0
```
**覆蓋面誠實聲明**:log 被 restart 多次截斷(06-03/06-07/06-08/06-10〔L2 deploy〕),「14d 單一連續 log」不可重建。判定依據改為:
- **4 個獨立 restart 窗全 0 WARN**(每次 restart 全量重讀 env=獨立檢驗 fallback 觸發條件):①06-03 後窗 ②06-07 全量 rebuild 後窗 ③06-08 atomic deploy 後窗(238MB log,當日 08:24 親驗 0)④06-10 L2 deploy 後窗(10:00:02Z 起新 log,10:19Z 親驗 0)。
- **結構性論證**:fallback 觸發=新 env 缺失,一旦成立每天 24 條 rate-limited WARN 持續發射,不可能只落在 log 縫隙。
- **journald 全窗檢索**(`--since 2026-05-27 --until 2026-06-10`)=0 條;弱佐證(engine/API 為 user process 非 systemd unit,journald 覆蓋未證,不單獨依賴)。
- **§13.1 gate-3**:`live_auth_signing_key.txt` mode **600**/65 bytes/mtime **2026-05-28 12:20**(soak 起點後未被改動)= PASS。
- 失敗模式不對稱兜底(CC):即使覆蓋仍有縫,cutover 錯判的後果=live 不可用(loud),無失防路徑。

## 3. CC 四條件 ledger

| 條件 | 狀態 |
|---|---|
| CC-MED-1 doc-reconcile | ✅ **DONE** `823e53ad`(PM 拍板保留 seed;runbook §4.2.1/§13.1/故障表/§13.5+spec §3.3 五處措辭校準;CC-LOW-2 §13.2 補 `live_auth_key_missing` token 順帶) |
| C-A soak 證據附 sign-off 包 | ✅ **DONE**(本報告 §2) |
| C-B 手動 renew+watcher respawn 驗證留證 | ⬜ **operator @ deploy**(§13.1 救濟路徑:cutover 時手動 renew 一次+5s watcher respawn 後驗 trust-status,留 audit row) |
| C-C 外部 Grafana/journald alert 同步+親簽 | ⬜ **operator @ deploy 前**(新字串 `live_auth_signing_key_missing`+`AuthError::LiveAuthSigningKeyMissing`+`live_auth_key_missing`〔CC-LOW-2〕;親簽 `ops2_phase2_external_alert_aligned` audit row) |

## 4. Operator deploy checklist(順序)

1. **C-C** 外部 alert rule 加 3 字串+親簽(repo 外不可 audit,唯一前置)。
2. **merge**:branch off `28e376c0`,origin/main 已前進(L2 deploy+docs);E2/BB 已驗與 L2 0 重疊,預期乾淨 merge(或 operator 選 rebase)。
3. **deploy**:Rust 變更需 `--rebuild`(#6 慣例);merge 後 **full Linux regression owed**(E4 註明,隨 deploy gate 補)。
4. **C-B**:deploy 後手動 `/auth/renew` 一次+驗 trust-status,留證。
5. **§13.6** D+15~D+44 verify SOP 起算;**首次 90d urandom rotation due 2026-09-08**(在此之前 missing-file 重啟會靜默重耦合兩 secret 域——runbook 已載明,見 seed echo 即排查)。

## 5. 殘留(非 blocker)

- CC-LOW-1:Python `_sign_authorization_payload` 參數名 `ipc_secret` 殘留(cosmetic,下次觸檔改)。
- BB INFO-3:Bybit `rpiTakerAccess`(rollout 至 06-12)0 影響,留下次例行 compat audit。
- E4 owed:Linux full regression @ merge+rebuild。
- 程序註記:BB 原被 PM 裁定跳過(誤讀 §13.3),後經 runbook §13 owner 行(:586)發現指名 BB sign-off,撤回裁定補派並完成——記錄此修正以保決策可追溯。
