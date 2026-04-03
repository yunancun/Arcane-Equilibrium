# 關鍵路徑 + Contingency + 量化指標

## 關鍵路徑（9 個任務）

```
0a-02(Schema DDL) → 0b-02(TimescaleDB) → 1-02(FeatureCollector) → 2-06(Context Snapshot) 
→ 2-11(LightGBM Scorer) → 2-21(Rust ml_scorer.rs) → 3a-01(update_params API) 
→ 3b-02(Optuna TPE) → 3b-05(Thompson Sampling) → 6-01(放權管線)
```

**耽誤任何一個延遲整體。**

## 有 Float 的任務（可延遲不影響整體）

- DL-3（Phase 4）：實驗性，可砍，節省 ~5 天
- DL-1 / DL-2（Phase 5）：可延後到 Phase 6 後
- 新聞接口（Phase 4）：Mock 階段無真實依賴
- 文檔（Phase 6）：可與驗收並行
- 相關性矩陣（Phase 5）：獨立模組

## Contingency（超時 +50% 時觸發）

| Phase | 動作 |
|-------|------|
| 0 +50% | 砍 VIEW 橋接，Dashboard 暫斷 |
| 1 +50% | PSI/ADWIN 延到 Phase 3b |
| 2 +50% | ONNX PoC 延到 Phase 4，先 Python-only Scorer |
| 3a +50% | 只做 Python 5 策略，Rust 延到 Phase 5 |
| 3b +50% | 砍 BH-FDR + Grid Pareto，只做 TPE+TS 核心 |
| 4 +50% | 砍 DL-3 + LinUCB |
| 5 +50% | 砍 DL-1 + DL-2，只做 James-Stein |

## Phase 間可 Overlap

- Phase 0b 尾 + Phase 1 頭：ML 側不等 TimescaleDB，節省 ~3 天
- Phase 4 中 + Phase 5 頭：DL-1/DL-2 可提前，節省 ~5 天

## 甘特圖

```
W    1    2    3    4    5    6    7    8    9    10   11   12   13   14   15   16   17   18   19   20
     4/11 4/18 4/25 5/02 5/09 5/16 5/23 5/30 6/06 6/13 6/20 6/27 7/04 7/11 7/18 7/25 8/01 8/08 8/15 8/22
     ├──┤
     0a
          ├──┼──┤
          0b
                    ├──┼──┤
                    Phase 1
                              ├──┼──┼──┼──┤
                              Phase 2 [+buffer]
                                             ├──┼──┤
                                             Phase 3a
                                                       ├──┼──┤
                                                       Phase 3b
                                                                 ├──┼──┼──┤
                                                                 Phase 4
                                                                           ├──┼──┼──┤
                                                                           Phase 5
                                                                                     ├──┼──┤
                                                                                     Phase 6

Quality: ↑E5     ↑E5          ↑E5                ↑E5    ↑E5            ↑E5          ↑E5    ↑QA
```
