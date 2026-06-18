# TODO v171 Active Queue Archive Pass #3

日期：2026-06-18
角色：PM
範圍：TODO §5 active queue hygiene

## 結論

本輪只歸檔兩個已完成且下一步已由其他 active row 承接的 §5 rows：

- `AUDIT-2026-06-14-MIGRATION-TREE-1`
- `AEG-S2-EVIDENCE-AUTOMATION`

## 判定

`AUDIT-2026-06-14-MIGRATION-TREE-1` 已完成實作、部署與 checksum repair apply；TODO row 內的剩餘價值是歷史證據與未來 migration discipline，已由 V### / Linux PG dry-run 規則承接。

`AEG-S2-EVIDENCE-AUTOMATION` 的 S2 runner 基建已完成；剩餘候選 rows / Gate-B fresh run 工作由 `AEG-S3-CANDIDATE-DIRECT-ROWS` 與 §6 Gate-B row 承接。

## 保留項

其他 DONE-ish rows 暫不歸檔，因為仍帶有政策、deploy、operator、future-date、event-trigger 或 source-vs-runtime gate。

## 邊界

Docs hygiene only。未執行 CI、deploy、rebuild、restart，未改 production source、runtime、DB、auth、risk、order 或 trading state。
