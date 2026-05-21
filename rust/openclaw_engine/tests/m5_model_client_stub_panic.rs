//! M5 ModelClient trait stub panic 煙霧測試（Sprint 1A-δ）。
//!
//! MODULE_NOTE
//! 模塊用途：驗證 ADR-0035 §Decision 1 + canonical spec §2.3 反模式 Gate 1
//!   「6 method default panic」紀律 — 任一 Y1+Y2 caller 誤呼 `ModelClient`
//!   6 method 之一均必 panic，且 panic message 含 "M5" tag。
//! 主要測試：
//!   - 6 個 `#[should_panic(expected = "M5")]` test case，對應 canonical spec
//!     §2.1 鎖定的 6 method：get_predict / get_predict_streaming /
//!     drift_callback / rollback / throttle / health（不含舊 IMPL 的
//!     version / model_metadata / streaming_supported）
//!   - 1 個 dyn safety smoke test，驗證 trait object `Box<dyn ModelClient>`
//!     可構造（構造本身不 panic，僅呼叫 method 時 panic）
//! 依賴：openclaw_engine::model_client::{ModelClient, UnimplementedModelClient,
//!   FeatureVector, DistributionMetrics, ModelVersion}。
//! 硬邊界：
//!   1. 禁實作 mock ModelClient 隱藏 default body（per E4 SOP / canonical spec
//!      §2.3 Gate 2 反模式）。
//!   2. 禁驗證任一 method 真實返回值（Sprint 1A-δ 階段沒有真實返回值；全 panic）。
//!   3. 任何 panic message 不含 "M5" 視為 trait 改寫退化
//!      （per canonical spec §2.3 Gate 2 反模式）。
//!
//! 參考：
//!   - ADR-0035 §Decision 1（6 method default panic + fail-loud 紀律）
//!   - canonical spec §2.1 line 79-137（rust block 6 method 鎖定）
//!   - canonical spec §5 AC4（sibling panic test 6 case 全 panic）

use openclaw_engine::model_client::{
    DistributionMetrics, FeatureVector, ModelClient, ModelVersion, UnimplementedModelClient,
};

/// 驗 `get_predict` 觸發 unimplemented panic 且 message 含 "M5" tag。
#[test]
#[should_panic(expected = "M5")]
fn m5_stub_get_predict_panics() {
    let client = UnimplementedModelClient::default();
    let features = FeatureVector::default();
    let _ = client.get_predict(&features);
}

/// 驗 `get_predict_streaming` 觸發 unimplemented panic 且 message 含 "M5" tag。
#[test]
#[should_panic(expected = "M5")]
fn m5_stub_get_predict_streaming_panics() {
    let client = UnimplementedModelClient::default();
    let features = FeatureVector::default();
    let _ = client.get_predict_streaming(&features);
}

/// 驗 `drift_callback` 觸發 unimplemented panic 且 message 含 "M5" tag。
///
/// 為什麼：Y3+ activation 前無 drift detection 路徑；caller 誤呼必 fail-loud
/// （per canonical spec §2.2 表格第 3 列 panic 紀律）。
#[test]
#[should_panic(expected = "M5")]
fn m5_stub_drift_callback_panics() {
    let client = UnimplementedModelClient::default();
    let metrics = DistributionMetrics::default();
    let _ = client.drift_callback(&metrics);
}

/// 驗 `rollback` 觸發 unimplemented panic 且 message 含 "M5" tag。
///
/// 為什麼：Y3+ activation 前無 streaming model state，亦無 rollback target；
/// caller 誤呼必 fail-loud（per canonical spec §2.2 表格第 4 列）。
#[test]
#[should_panic(expected = "M5")]
fn m5_stub_rollback_panics() {
    let client = UnimplementedModelClient::default();
    let version = ModelVersion::default();
    let _ = client.rollback(version);
}

/// 驗 `throttle` 觸發 unimplemented panic 且 message 含 "M5" tag。
///
/// 為什麼：Y3+ activation 前無 streaming update 路徑；caller 設 rate hint 無
/// 落地路徑 → 必 fail-loud（per canonical spec §2.2 表格第 5 列）。
#[test]
#[should_panic(expected = "M5")]
fn m5_stub_throttle_panics() {
    let client = UnimplementedModelClient::default();
    let _ = client.throttle(0.1_f64);
}

/// 驗 `health` 觸發 unimplemented panic 且 message 含 "M5" tag。
#[test]
#[should_panic(expected = "M5")]
fn m5_stub_health_panics() {
    let client = UnimplementedModelClient::default();
    let _ = client.health();
}

/// 驗 trait dyn safety — `Box<dyn ModelClient>` 可構造，且構造本身不 panic。
///
/// 為什麼：trait 必須 `Send + Sync + 'static` dyn safe，否則 Y3+ activation
/// 期無法用 dynamic dispatch 切換 baseline / streaming 兩條 impl；本測試守護
/// 該 dyn safety 紀律，若 trait 改增 generic / associated type 違反 dyn safety
/// → 此 test 編譯 fail。
#[test]
fn m5_stub_trait_object_constructible() {
    // 構造 trait object 本身不應 panic；任一 method 呼叫才 panic（前 6 個
    // test 已驗）。
    let client: Box<dyn ModelClient> = Box::new(UnimplementedModelClient::default());
    // 取 raw pointer 後 drop — 確保 Box 真存活到此處，避免編譯器 dead code
    // elimination 把構造優化掉。
    let _ptr: *const dyn ModelClient = Box::into_raw(client);
    // 重新取回所有權後 drop（避免記憶體洩漏）。
    unsafe {
        drop(Box::from_raw(_ptr as *mut dyn ModelClient));
    }
}
