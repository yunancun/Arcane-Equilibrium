# 2026-07-03 冷酷對抗審計 — Stage 0 Baseline Freeze

> conductor(主會話)親做;凍結時刻 = 2026-07-03(Mac fetch origin 後採樣)。
> 用途:注入 openclaw-full-audit workflow `args.baseline`,對齊全軸 affected line;審計期間任何端的代碼變動不進本輪範圍。

## 1. 三端 git SHA

| 端 | SHA | branch | 狀態 |
|---|---|---|---|
| Mac (`~/Projects/TradeBot/srv`) | `d68a13298c5f60c3d6656cc9f465ae61aff7caa8` | main | **審計凍結基準(SoT)** |
| origin/main (fetch 後) | `d68a13298c5f60c3d6656cc9f465ae61aff7caa8` | main | 與 Mac 一致 |
| Linux runtime (`trade-core:~/BybitOpenClaw/srv`) | `262596c69e339a8aa6268b20ba3b25274c1f9e48` | main | worktree clean;**落後 3 commits** |

**三端 drift 判定**:Linux 落後的 3 個 commits(`0494e0e76`→`28c11bfb7`→`d68a13298`)全部為 `[skip ci]` governance 提交(共 20 檔:`.claude/agents|skills|workflows`、`CLAUDE.md`、docs 設計評審文檔),**零 runtime 代碼**。判定:非事故性 drift,不構成 source-vs-runtime 行為差異;但各軸對 runtime 行為的斷言以 Linux `262596c` 為實態底數,對治理/文檔的斷言以 Mac `d68a1329`(含 operator 2026-07-03 裁決座標落地)為準。

## 2. Dirty worktree 快照

- **Linux**:clean(零 dirty)。
- **Mac**:dirty 全部集中在 `memory/`(44 modified/deleted + 47 untracked),即 07-02 R4 巡檢 8 組 MERGE(63→36 條、35 原檔移 archive/)的**未 commit 產物**。`srv` 源碼、config、docs、`.claude/` **零 dirty** — 審計凍結基準不受影響。
- **懸掛風險註記**:多 session memory race 協議要求 commit-first,此批 memory 重組尚未 commit 屬懸掛態;不在本輪審計範圍內動它,交 operator 決定是否先 `git commit --only memory/`。

## 3. E4 測試基線錨(E4 memory.md 最新 `BASELINE:` 行)

主錨(line 977,最新):

```
BASELINE: 2026-07-03 passed=5492 failed=0 skipped=0 error=0 (rust cargo test --workspace --no-fail-fast, Linux trade-core debug, 8 ignored, 95 targets; @337a0442d 隔離 worktree; Mac 同刻副基準: srv tests/=805/0/2, tests/structure=380/0)
```

輔錨(line 972):Mac debug `openclaw_engine` FULL lib+integration+bins = 4670/0/0(6 ignored)@`77c7ce95b` dirty。

本輪 report-only 不跑修復,E4 軸僅做測試矩陣盲區審計,不重建 BASELINE;上述行是回歸判準的凍結參照。

## 4. Active SoT 清單

- `CLAUDE.md` @ `d68a1329`(含 operator 07-03 四裁決落地)
- `TODO.md`(active dispatch rows;Stage 4 前禁改)
- `.claude/`:agents 18 role、skills(含 ultracode-full-audit、openclaw-full-audit workflow 正本)、workflows
- `.codex/`:Codex 活躍治理層(06-18 起,非 hint mirror;納入 R4/FA 視野)
- config 三環境 TOML(paper/live/demo 故意獨立,禁純衛生合併)
- `docs/adr/`(含 ADR-0048 IBKR lane)、`docs/references/`(ARCH-RC1 統一 Config 契約)
- Runtime 實態:Linux `262596c` + PG(read-only)

## 5. Runtime 納入與 ssh 命令範圍

- Runtime **納入**,一律 read-only:`ssh trade-core` 限 `git rev-parse/status/log/diff`、檔案讀取(`cat`/`ls`/`head`)、`psql` SELECT-only。
- **禁止**:任何 git 寫操作、systemctl/restart/部署、config 寫入、engine IPC 寫入口、任何下單/平倉路徑觸碰。

## 6. 本輪禁止事項(report-only 硬邊界)

1. `fix=false`:全程 report-only,發現任何缺陷只進報告,不動代碼(operator 07-03 fix-on-discovery 原則在本輪被 Stage 顯式覆蓋:修復統一走 Stage 3 validated fix plan 批准後執行)。
2. TODO.md / memory / 業務代碼 / config 全程凍結,唯一允許寫入 = 各 agent workspace reports。
3. live fail-closed 5 hard gates 與 9 安全不變量**不受 over-gate 審查波及,永不鬆動**(裁決座標邊界條款)。
4. 審計期間不 pull/merge;若外部 session 推進 origin,本輪仍鎖 `d68a1329`。

## 7. 報告命名與落點

- Stage 0(本檔):`PM/workspace/reports/2026-07-03--cold_audit_baseline.md`
- Stage 2 各軸原始報告:workflow 自產,見返回 report_paths
- Stage 3:`PA/workspace/reports/2026-07-03--cold_audit_validated_fix_plan.md`
- Stage 4:`PM/workspace/reports/2026-07-03--cold_audit_pm_final.md`

## 8. `args.baseline` 注入串(Stage 2 用)

```
AUDIT_DATE=2026-07-03; 凍結基準 Mac HEAD=origin/main=d68a13298c5f60c3d6656cc9f465ae61aff7caa8 (main);
Linux runtime=262596c69e339a8aa6268b20ba3b25274c1f9e48 (clean, 落後 3 個 [skip ci] governance commits, 零 runtime 代碼 drift);
Mac dirty=僅 memory/ 重組未commit(源碼/config/docs 零 dirty);
E4 BASELINE: 2026-07-03 passed=5492 failed=0 (rust workspace, Linux debug, 8 ignored, 95 targets); Mac 副基準 srv tests/=805/0/2, structure=380/0;
runtime read-only 納入(ssh trade-core: git 讀/檔案讀/psql SELECT-only);report-only,fix=false;
live fail-closed 5 hard gates + 9 安全不變量不受 over-gate 審查波及。
```
