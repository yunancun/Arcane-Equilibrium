# rtk — pinned build + pytest error 計數修復 patch

> 正本:本目錄是我們對 [rtk](https://github.com/rtk-ai/rtk)(Rust Token Killer,
> coding-agent 輸出壓縮 proxy)的 pin + 本地 patch 來源。
> `.claude/hooks/rtk-rewrite.sh` 所裝的 binary 必須按本檔流程自建,
> 不得直接裝上游 release(上游 v0.42.2 有 pytest error 計數缺陷,對 E4
> 測試基準線是生死級失真)。

## Pin

| 項目 | 值 |
|---|---|
| Upstream repo | `https://github.com/rtk-ai/rtk.git`(Apache License 2.0) |
| Pin SHA(upstream `develop` HEAD @ 2026-06-11) | `6785a6c7695d7273e722214a295249a84819b6f0` |
| Cargo.toml 版本 | 0.42.2(develop = 0.43.0-rc 線) |
| 本地 patch | `0001-fix-pytest-error-count.patch`(已驗證在 pin SHA 上 `git apply --check` 乾淨) |
| 上游 PR | <https://github.com/rtk-ai/rtk/pull/2399>(target `develop`;merge 後可改 pin 至含修復的上游 SHA 並移除 patch) |

## 缺陷描述(patch 修什麼)

上游 `src/cmds/python/pytest_cmd.rs` 完全不認得 pytest 的 error 計數:

1. **error 計數消失(主缺陷)**:`20 passed, 1 error in 1.94s`(exit 1)被壓成
   `Pytest: 20 passed` 全綠短格式 — agent 只讀壓縮摘要會誤判 suite 綠。
   根因:`parse_summary_line` 只解析 passed/failed/skipped/xfailed/xpassed;
   `build_pytest_summary` 在 `failed==0 && passed>0` 時提前 return,
   把已收集的 ERROR 細節一併丟棄。
2. **collection error 誤導**:`Interrupted: 1 error during collection`(exit 2)
   顯示成 `Pytest: No tests collected`。
3. **`=== ERRORS ===` 區塊從未被捕捉**:fixture/collection error 的原因
   在壓縮輸出中完全不可見;單行 `ERROR ...` summary 條目渲染成空白項。
4. **`-q` 裸 summary 用 substring 啟發式誤捕 stdout 內容**(E2 對抗審查發現,
   patch 第二輪修):失敗測試的 Captured stdout 含
   `worker 3 passed in shard cleanup` 之類行會被當成 summary →
   上游 base 對 RED run 輸出**假全綠** `Pytest: 3 passed`(exit=1 卻零細節);
   patch 初版加寬 error 臂後同型誤捕(`retrying after error in connection pool`)
   反使 RED run 變 `No tests collected`。修法=整行 summary 文法錨定
   (每個逗號段 `<count> <category>` + 尾綴 `in <float>s` + 可選 `(h:mm:ss)`)
   + last-match-wins(真 footer 永遠是輸出最後一個合法形,即使 stdout 印出
   逐字 summary 形也會被真行覆蓋)。

Patch 後行為(實測,對照 native pytest):

| 場景 | native pytest(exit) | patch 前 rtk | patch 後 rtk |
|---|---|---|---|
| 壞 fixture | `20 passed, 1 error`(1) | `Pytest: 20 passed` | `Pytest: 20 passed, 0 failed, 1 error` + ERROR 細節 |
| collection error | `1 error`(2) | `Pytest: No tests collected` | `Pytest: 0 passed, 0 failed, 1 error` + `ERROR collecting ...` |
| 混合 | `2 failed, 7 passed, 1 error`(1) | `Pytest: 7 passed, 2 failed` | `Pytest: 7 passed, 2 failed, 1 error` + 全部細節 |
| 全綠 | `5 passed`(0) | `Pytest: 5 passed` | `Pytest: 5 passed`(byte-identical,無回歸) |
| stdout 含 `...error in...` 餌 + RED | `1 failed, 1 passed`(1) | `1 passed, 1 failed`(base 碰巧不中此餌) | `Pytest: 1 passed, 1 failed` + 細節 |
| stdout 含 `...passed in...` 餌 + RED | `1 failed, 1 passed`(1) | **`Pytest: 3 passed` 假全綠** | `Pytest: 1 passed, 1 failed` + 細節 |

exit code 兩側皆原樣透傳(rtk 本就透傳,patch 不碰)。

> patch 為**單一 squash commit**(初版 + E2 回歸修復合一);
> `git apply` 一次即得最終態,無 0002。

## 雙端 build + 安裝

Mac 與 Linux(trade-core)同一流程;需 Rust toolchain(上游 rust-version 1.91+):

```bash
git clone https://github.com/rtk-ai/rtk.git /tmp/rtk-build && cd /tmp/rtk-build && git checkout 6785a6c7695d7273e722214a295249a84819b6f0 && git apply /path/to/srv/tools/rtk/0001-fix-pytest-error-count.patch && cargo build --release
```

產物在 `/tmp/rtk-build/target/release/rtk`。安裝位置由 PM/operator 決定
(hook 端解析見 `.claude/hooks/rtk-rewrite.sh`);裝機前先跑 smoke:

```bash
/tmp/rtk-build/target/release/rtk pytest --help >/dev/null && echo OK
```

驗證 patch 已生效(對任一含壞 fixture 的 pytest 目錄):輸出必須含
`N error`,不得是純 `Pytest: N passed`。

## 出處與授權

- 上游:rtk-ai/rtk,**Apache License 2.0**(LICENSE 全文見上游 repo)。
- 本目錄 patch 為我們提交上游的同一份修復
  (PR [#2399](https://github.com/rtk-ai/rtk/pull/2399),
  branch `yunancun/rtk:fix/pytest-error-count`,commit `32561a07`,
  squash 含 E2 回歸修復輪),
  以 Apache 2.0 條款使用與再分發,保留原始版權聲明。
- 上游 merge 並發版後:更新 pin SHA → 重建 → 刪除本 patch 行,本檔表格同步。
