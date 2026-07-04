//! P1-4a G3 drift lane 接線契約測試（2026-07-04 冷審計 R2）。
//!
//! MODULE_NOTE
//! 模塊用途：以 include_str! 源碼掃描釘住 main_pipelines.rs 三個 pipeline spawn
//!   （paper/demo/live）的 feature_tx 接線，防止回歸為 `feature_tx: None`。
//! 為什麼需要：`features.online_latest` 的唯一 producer 是 pipeline 的
//!   FeatureSnapshot emit（step_1_2）。歷史上僅 Paper 接線（D19 遺留），Paper
//!   封存後全鏈斷供，表凍結於 2026-05-06，G3 drift 偵測（風控腿）全鏈 no-op。
//!   編譯器管不到「某 call site 被改回 None」這種語義回歸，故以源碼掃描守住
//!   （範式對齊 tick_pipeline/tests/fast_track_reduce.rs 的 include_str! 先例）。
//! 硬邊界：本測試放獨立檔案，避免 include_str! 自掃描時把測試內的字面模式
//!   計入命中數。

/// 不變量：三個 spawn fn（paper/demo/live）全部 `writers.feature_tx.clone()`，
/// 且整檔不得殘留任何 `feature_tx: None`（含 decision_feature_tx 等子字串命中
/// 也一律視為違規——該檔所有 writer channel 皆應走 writers 共享 sender）。
#[test]
fn test_all_pipeline_spawns_wire_feature_tx() {
    let src = include_str!("../main_pipelines.rs");

    let wired = src.matches("feature_tx: writers.feature_tx.clone()").count();
    assert_eq!(
        wired, 3,
        "main_pipelines.rs 必須恰有 3 處 `feature_tx: writers.feature_tx.clone()`\
         （paper/demo/live 各一）；計數漂移 = 某 pipeline 斷供 features.online_latest\
         （G3 drift lane 凍結事故根因），實得 {wired}"
    );

    let none_hits = src.matches("feature_tx: None").count();
    assert_eq!(
        none_hits, 0,
        "main_pipelines.rs 不得出現 `feature_tx: None`（含子字串命中）；\
         實得 {none_hits} 處——feature 族 writer sender 一律共享 writers.* clone"
    );
}
