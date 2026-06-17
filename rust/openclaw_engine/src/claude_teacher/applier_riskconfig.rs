//! RiskConfig agent-tuning sink — Phase 3 (LAST phase) of the intelligent
//! param-adjusting agent. Ships INERT and fail-closed in v1.
//!
//! MODULE_NOTE (中):
//!   模塊用途：把 `DirectiveType::AdjustRiskConfig` directive 轉成 demo
//!     `ConfigStore<RiskConfig>` 的 in-process 直寫，並在寫入前以
//!     **遞迴 dotted-path matcher + survival denylist + allowlist-default-deny**
//!     過濾所有觸碰 survival / 曝險 / 槓桿 / halt / cascade / cost_gate /
//!     market_gate 的欄位。
//!   主要型別/函數：
//!     - `RISKCONFIG_SURVIVAL_DENYLIST`（按 risk_config.rs / risk_config_advanced.rs
//!       親 grep 出的 **真 dotted-path 葉名** author，不可複用 applier.rs 的舊
//!       `P0_P1_DENYLIST_FIELDS` strategy-param 命名空間——舊名與 RiskConfig
//!       葉名不同，套用會永遠 match 不到 = 靜默全放行）。
//!     - `riskconfig_patch_leaves`（遞迴走整 patch 樹，產出每個葉的完整 dotted-path）。
//!     - `riskconfig_decide_leaf` / `riskconfig_decide_patch`（fail-closed、
//!       allowlist-default-deny 判定）。
//!     - `RiskConfigDirectiveSink::demo`（**結構閘**：只持 demo Arc，編譯期不持
//!       live Arc，永不呼叫 `PerEngineRiskStores::select`）。
//!   依賴：`super::applier::{ApplyOutcome, GovernanceCheck}`、`super::parser::Directive`、
//!     `crate::config::store::{ConfigStore, PatchSource}`、`crate::config::risk_config::RiskConfig`。
//!   硬邊界（為何 fail-closed）：
//!     1. v1 ALLOWLIST 結構性為空（U5 硬規則：RiskConfig struct 中沒有任何
//!        operator-defined band 欄 → clamp-cannot-widen 對候選欄是 vacuous →
//!        所有候選欄留在 default-deny）。flag-ON 也 tune NOTHING，這是正確的
//!        inert 行為，不是缺陷。
//!     2. demo sink **結構上**拿不到 live `ConfigStore<RiskConfig>` 的 handle，
//!        故無論 directive 怎麼寫都不可能 mutate live config（E3 編譯期可證）。
//!        agent 對 RiskConfig 的 live 變更唯一路徑 = Phase-2 promotion（operator
//!        confirm + 5-gate + Phase-0 token），不存在 in-process live 寫路徑。
//!     3. 任一葉被拒 → 整個 patch 拒（all-or-nothing，對齊 ConfigStore::apply_patch
//!        的 validate 語意）。

use super::applier::{ApplyOutcome, GovernanceCheck};
use super::parser::Directive;
use crate::config::risk_config::RiskConfig;
use crate::config::store::{ConfigStore, PatchSource};
use std::sync::Arc;
use tracing::{info, warn};

// ---------------------------------------------------------------------------
// §3.1 RISKCONFIG_SURVIVAL_DENYLIST（真 dotted-path 葉名 + struct-prefix）
// ---------------------------------------------------------------------------

/// Survival / exposure / loss / leverage / halt / guardian fields that an
/// agent directive **must never** be allowed to modify, as an *independent*
/// defense layer (caught here as `VetoedByHardBoundary`, not merely by the
/// allowlist-default-deny backstop). This list is NOT a claim to enumerate
/// *every* survival field — it enumerates:
///   1. whole-struct PREFIXES the recursive matcher prefix-denies for any leaf
///      below them: `cascade` / `cost_gate` / `market_gate` / `overrides` /
///      `per_strategy` / `dynamic_sizing` / `kelly` / `correlation` /
///      `anti_cluster` / `executor`;
///   2. the explicitly-enumerated `limits.*` GlobalLimits survival leaves
///      (SL/TP / position / exposure / leverage / drawdown / halt-TTL /
///      guardian caps / fast_track dust floors), grep-verified against the REAL
///      `RiskConfig` leaf names in `risk_config.rs`;
///   3. five hard-boundary literal tokens (`execution_state` /
///      `execution_authority` / `system_mode` / `live_execution_allowed` /
///      `max_retries`) vetoed even as free-text keys.
/// Anything NOT covered above (e.g. a future top-level struct nobody listed)
/// is still rejected by the allowlist-default-deny catch-all in
/// `riskconfig_decide_leaf` (→ `VetoedByDefaultDeny`). So the system is
/// fail-closed by construction even for leaves this list does not name.
///
/// 絕對禁止 agent directive 修改的 survival / 曝險 / 虧損 / 槓桿 / halt /
/// guardian 欄位，作為**獨立防線**（在此被 `VetoedByHardBoundary` 攔，而非
/// 僅靠 allowlist-default-deny 後盾）。本表**不宣稱**窮舉每一個 survival 欄位
/// —— 它列舉的是：
///   1. 遞迴 matcher 對其下任何葉直接前綴拒的整 struct 前綴：
///      `cascade` / `cost_gate` / `market_gate` / `overrides` / `per_strategy` /
///      `dynamic_sizing` / `kelly` / `correlation` / `anti_cluster` / `executor`；
///   2. 顯式列舉的 `limits.*` GlobalLimits survival 葉（SL/TP / 倉位 / 曝險 /
///      槓桿 / 回撤 / halt-TTL / guardian caps / fast_track dust floors），
///      已對 risk_config.rs 真實葉名親 grep；
///   3. 五個硬邊界字面 token（`execution_state` / `execution_authority` /
///      `system_mode` / `live_execution_allowed` / `max_retries`），即使作為
///      free-text key 出現也 veto。
/// 凡未被上述涵蓋者（例如未來某個沒人列的頂層 struct），仍由
/// `riskconfig_decide_leaf` 的 allowlist-default-deny catch-all 拒
/// （→ `VetoedByDefaultDeny`）。故即使本表未指名某葉，系統仍 by-construction
/// fail-closed。
///
/// 為何不可複用 applier.rs 的 `P0_P1_DENYLIST_FIELDS`：那組是 strategy-param
/// 命名空間舊名（`max_leverage` / `daily_loss_pct` …），與 RiskConfig 真葉名
/// （`limits.leverage_max` / `limits.daily_loss_max_pct` …）**不同**；直接套用
/// 會永遠 match 不到任何 RiskConfig patch key = 靜默全放行（fail-open）。
///
/// 全部小寫存（比對時 case-insensitive + 去控制/格式字元正規化）。
pub const RISKCONFIG_SURVIVAL_DENYLIST: &[&str] = &[
    // -- struct-prefix denials（遞迴 matcher 對 `X.` 下任何葉直接拒）--
    // 整個 cascade.*（CascadeThresholds，risk_config.rs:1039-1070）
    "cascade",
    // 整個 cost_gate.* 5 欄（CostGate，risk_config.rs:1283-1295）：k 上調 /
    // min_confidence 下調 / adx_trending 下調都放寬 edge 過濾 = 開更多倉 = survival-class
    "cost_gate",
    // 整個 market_gate.*（MarketGate，risk_config_advanced.rs）微結構 gate
    "market_gate",
    // FIX-1（CC MEDIUM）：把以下 survival-bearing 整 struct 加為前綴拒，使其由
    // denylist（HardBoundary）攔，而非僅靠 allowlist-default-deny 後盾——獨立防線。
    // 這些皆非 allowlist 候選（候選只有 regime.* / dynamic_stop.* / agent.trailing+size），
    // 故前綴拒不與 allowlist 衝突。
    // 整個 overrides.*（CategoryOverrides，risk_config.rs:725-735）：per-category
    // leverage_max / position_size_max_pct / stop_loss_max_pct / holding_hours_max
    // 上限——放寬任一即等同放寬該 category 的 survival 上限。
    "overrides",
    // 整個 per_strategy.*（StrategyOverride，risk_config_per_strategy.rs:59）：
    // per-strategy P1 上限；agent 絕不可改任何策略的 P1 ceiling。
    "per_strategy",
    // 整個 dynamic_sizing.*（DynamicRiskSizerConfig，dynamic_risk_sizer.rs:32）：
    // sizing band [min_pct,max_pct] + enabled + 顯著性 gate 旗標——agent 絕不可
    // 放寬 sizing band（max_pct 上調 = 直接放大最大倉位）。
    "dynamic_sizing",
    // 整個 kelly.*（KellyTierConfig）：Kelly 分層 sizing 參數，曝險相關。
    "kelly",
    // 整個 correlation.*（Correlation）：相關性曝險限制。
    "correlation",
    // 整個 anti_cluster.*（AntiCluster）：群聚曝險限制。
    "anti_cluster",
    // 整個 executor.*（ExecutorConfig，含 shadow_mode）：執行狀態相鄰——
    // shadow_mode 翻轉影響 live/shadow 執行語意。
    "executor",
    // -- cost_gate 葉（顯式列入以便 audit 可讀；前綴已覆蓋，此處是 defense-in-depth）--
    "cost_gate.k_base",
    "cost_gate.k_medium",
    "cost_gate.k_small",
    "cost_gate.min_confidence",
    "cost_gate.adx_trending",
    // -- market_gate liquidation buffer（CC CRITICAL：operator-named 清算緩衝
    //    在 market_gate.* 而非 limits.*；顯式列入以便 audit 可讀）--
    "market_gate.liquidation_buffer_pct",
    // -- GlobalLimits 絕對 SL/TP / 倉位 / 曝險 / 槓桿上限（risk_config.rs:365-498）--
    "limits.stop_loss_max_pct",
    "limits.take_profit_max_pct",
    "limits.take_profit_enforced",
    "limits.position_size_max_pct",
    "limits.total_exposure_max_pct",
    "limits.correlated_exposure_max_pct",
    "limits.leverage_max",
    "limits.session_drawdown_max_pct",
    "limits.daily_loss_max_pct",
    "limits.consec_loss_cooldown_count",
    "limits.consec_loss_cooldown_min",
    "limits.open_positions_max",
    "limits.min_order_notional_usdt",
    "limits.max_order_notional_usdt",
    "limits.min_balance_usdt",
    "limits.global_notional_cap_usdt",
    "limits.per_trade_risk_pct",
    "limits.margin_mode",
    "limits.position_mode",
    "limits.allowed_categories",
    // -- halt TTL（生存恢復語意，risk_config.rs:484/496）--
    "limits.daily_loss_halt_ttl_ms",
    "limits.drawdown_halt_ttl_ms",
    // -- guardian 修正 caps（risk_config.rs:427-430）--
    "limits.guardian_modification_size_factor",
    "limits.guardian_modification_leverage_cap",
    // -- fast_track dust floors（survival 平倉語意，risk_config.rs:448/468）--
    "limits.ft_min_notional_ratio_of_entry",
    "limits.ft_dust_qty_floor_usd",
    // -- 硬邊界字面 token（防 agent 用舊名/別名注入；非 RiskConfig 葉，作為
    //    free-text key 出現即 veto，defense-in-depth，對齊 §四 三硬邊界）--
    "execution_state",
    "execution_authority",
    "system_mode",
    "live_execution_allowed",
    "max_retries",
];

// ---------------------------------------------------------------------------
// §3.2 候選 ALLOWLIST（v1 實質為空）
// ---------------------------------------------------------------------------

/// Candidate fields that *might* one day be agent-tunable — but ONLY after an
/// operator+QC pass adds an explicit `[band_min, band_max]` band field for the
/// leaf AND fills a value. Under U5 (§3.5) every candidate without a populated
/// operator band stays default-denied, so v1 ships with this entire set DENIED.
///
/// 候選欄：未來 operator+QC 為某欄加 band 子欄並填值後才可能解禁。U5 硬規則
/// （§3.5）下，凡無 populated operator band 的候選欄一律留在 default-deny，
/// 故 v1 整組皆 DENY。列出僅為把 §3.5 啟動路徑釘清楚，不是 v1 即可調。
///
/// 候選集（commented-but-denied）：
///   - `regime.{trending,volatile,ranging,squeeze,unknown}.{stop,tp,time}`
///     乘數（RegimeMultipliers / RegimeBundle，risk_config.rs:1182-1200）—
///     `RegimeMultipliers::validate` 只查 `stop/tp/time > 0`，無 band 欄 → v1 deny。
///   - `dynamic_stop.{base_ratio,cap_ratio,trailing_min_rr,atr_stop_mult,atr_tp_mult}`
///     （DynamicStop，risk_config_advanced.rs:124-135）— `DynamicStop::validate`
///     只查 `base_ratio>0 / cap_ratio>0 / base<=cap / atr_*>0`，無 band 欄 → v1 deny。
///   - `agent.{trailing_activation_pct,trailing_distance_pct,size_multiplier}`
///     （AgentParams，risk_config.rs:782-820）— `size_multiplier` 有結構性
///     clamp `[0.1,1.0]` 算半個 band，但 trailing_* 只有 `>0`；v1 仍 deny
///     （要 explicit `[band_min,band_max]` 才一致，避免「有些半 band 有些無」
///     的不一致防線）。
///
/// 注意：`agent.stop_loss_pct` / `agent.take_profit_pct` 是直接 SL/TP 數值，
/// 與 survival SL/TP 上限耦合（validate cross-field），歸 survival 語意，
/// **不入候選 allowlist**（永遠 deny）。
///
/// 是「候選集」的常數來源；真正的 allowlist 成員資格由
/// `riskconfig_allowlist_member`（§3.5 動態推導：候選 ∧ band 欄 Some）決定。
/// v1 因所有 band 欄 None（根本無 band 欄）→ 動態 allowlist 為空。
pub const RISKCONFIG_ALLOWLIST_CANDIDATES: &[&str] = &[
    "regime.trending.stop",
    "regime.trending.tp",
    "regime.trending.time",
    "regime.volatile.stop",
    "regime.volatile.tp",
    "regime.volatile.time",
    "regime.ranging.stop",
    "regime.ranging.tp",
    "regime.ranging.time",
    "regime.squeeze.stop",
    "regime.squeeze.tp",
    "regime.squeeze.time",
    "regime.unknown.stop",
    "regime.unknown.tp",
    "regime.unknown.time",
    "dynamic_stop.base_ratio",
    "dynamic_stop.cap_ratio",
    "dynamic_stop.trailing_min_rr",
    "dynamic_stop.atr_stop_mult",
    "dynamic_stop.atr_tp_mult",
    "agent.trailing_activation_pct",
    "agent.trailing_distance_pct",
    "agent.size_multiplier",
];

/// Operator band lookup for a candidate dotted-path. Returns `Some((min,max))`
/// ONLY when the RiskConfig struct holds a populated operator-defined band for
/// that leaf. v1: NO band fields exist in the struct → this ALWAYS returns
/// `None` for every candidate → the dynamic allowlist is structurally empty.
///
/// operator band 查詢。僅當 RiskConfig struct 中該葉有 populated 的
/// operator-defined band 時回 `Some((min,max))`。v1：struct 中沒有任何 band 欄
/// → 對每個候選恆回 `None` → 動態 allowlist 結構性為空。
///
/// 啟動路徑（§3.5）：operator+QC 在 RiskConfig struct 新增該欄的 band 子欄
/// （band 欄自身列入 denylist）+ operator 經正常 route 填值後，此函數對該欄
/// 才回 `Some(...)`，該欄才動態進 allowlist。band 欄 schema/validate 由那次
/// operator+QC 工作定義，不在 Phase 3 v1 範疇。
pub fn riskconfig_operator_band(_cfg: &RiskConfig, _dotted_path: &str) -> Option<(f64, f64)> {
    // v1：無任何 band 欄存在於 RiskConfig struct → 恆 None。
    // 此處刻意不查任何欄位——加 band 欄是 §3.5 的未來 operator+QC 工作。
    None
}

/// A leaf is allowlisted ONLY if it is in the candidate set AND has a populated
/// operator band. v1 → always false (no band fields). This is the U5 hard rule
/// made structural: "no operator band → stays denylisted".
///
/// 某葉只在「∈ 候選集 ∧ band 欄 Some」時才 allowlisted。v1 → 恆 false
/// （無 band 欄）。這把 U5 硬規則「無 operator band → 留 denylist」結構化。
pub fn riskconfig_allowlist_member(cfg: &RiskConfig, dotted_path: &str) -> Option<(f64, f64)> {
    let in_candidates = RISKCONFIG_ALLOWLIST_CANDIDATES
        .iter()
        .any(|c| c.eq_ignore_ascii_case(dotted_path));
    if !in_candidates {
        return None;
    }
    riskconfig_operator_band(cfg, dotted_path)
}

// ---------------------------------------------------------------------------
// §3.3 遞迴 dotted-path matcher + allowlist-default-deny
// ---------------------------------------------------------------------------

/// Normalise a key for denylist comparison: strip ASCII/unicode control +
/// format chars (zero-width, BOM, bidi isolates…) and lowercase. Mirrors the
/// fail-closed posture that any obfuscated key must NOT slip past the matcher.
///
/// 為 denylist 比對正規化 key：剝除 ASCII/unicode 控制 + 格式字元（零寬、BOM、
/// bidi isolate 等），再 lowercase。對齊 fail-closed 立場——任何混淆過的 key
/// 都不可滑過 matcher。
fn normalize_key(s: &str) -> String {
    s.chars()
        .filter(|c| !c.is_control() && !is_format_char(*c))
        .flat_map(|c| c.to_lowercase())
        .collect()
}

/// Unicode format / zero-width / bidi chars that could obfuscate a denylisted
/// key. Conservative superset; stripping them is fail-closed (a stripped key
/// that then matches a denylist token is still vetoed).
/// 可能混淆 denylist key 的 unicode 格式 / 零寬 / bidi 字元。保守超集；剝除是
/// fail-closed（剝後若 match denylist token 仍被 veto）。
fn is_format_char(c: char) -> bool {
    matches!(c,
        '\u{00AD}'            // soft hyphen
        | '\u{061C}'          // arabic letter mark
        | '\u{200B}'..='\u{200F}' // zero-width + bidi marks
        | '\u{202A}'..='\u{202E}' // bidi embedding/override
        | '\u{2060}'..='\u{2064}' // word joiner + invisible ops
        | '\u{2066}'..='\u{206F}' // bidi isolates + deprecated
        | '\u{FEFF}'          // BOM / zero-width no-break space
        | '\u{FFF9}'..='\u{FFFB}' // interlinear annotation
    )
}

/// Recursively walk a patch JSON tree, producing the full dotted-path of every
/// LEAF (any non-object value; arrays and scalars are single leaves). Object
/// nesting extends the path with `.`. An array (e.g. `allowed_categories`) is
/// treated conservatively as a SINGLE leaf at its key path (not per-element),
/// so it lands on the denylist as a whole.
///
/// 遞迴走整 patch JSON 樹，對每個**葉節點**（非 object 的 value；陣列與純量皆
/// 視為單葉）產出完整 dotted-path。object 巢狀以 `.` 延伸路徑。陣列
/// （如 `allowed_categories`）保守地整體視為 key 路徑上的**單一葉**（非逐元素），
/// 使其整體落 denylist。
///
/// 為何必須遞迴：既有 `find_denylisted_field`（applier.rs:551）只比頂層 object
/// key，對巢狀 `{"limits":{"leverage_max":50}}` 只看到 `"limits"` 看不到
/// `leverage_max` → 整條 survival 邊界被繞過（這正是 Phase 3 要修的命門）。
pub fn riskconfig_patch_leaves(patch: &serde_json::Value) -> Vec<String> {
    let mut out = Vec::new();
    walk_leaves(patch, String::new(), &mut out);
    out
}

fn walk_leaves(node: &serde_json::Value, prefix: String, out: &mut Vec<String>) {
    match node {
        // 只有非空 object 才繼續下鑽；其餘（純量 / 陣列 / null / 空 object）皆為葉。
        serde_json::Value::Object(map) if !map.is_empty() => {
            for (k, v) in map {
                let child = if prefix.is_empty() {
                    k.clone()
                } else {
                    format!("{prefix}.{k}")
                };
                walk_leaves(v, child, out);
            }
        }
        _ => {
            // 葉：產出當前累積路徑（頂層裸純量的 prefix 為空，保守地以空字串入列，
            // 在判定階段會走 default-deny）。
            out.push(prefix);
        }
    }
}

/// Per-leaf decision (fail-closed, allowlist-default-deny). Order:
///   (a) leaf path OR any struct-prefix (`cascade` / `cost_gate` /
///       `market_gate` / `overrides` / `per_strategy` / `dynamic_sizing` /
///       `kelly` / `correlation` / `anti_cluster` / `executor`) in the
///       survival denylist → `HardBoundary(path)`.
///   (b) else if not allowlisted-with-band → `DefaultDeny(path)`.
///   (c) only if allowlisted-with-band → `Clamp { band }`.
///
/// 逐葉判定（fail-closed、allowlist-default-deny）。順序見上。
#[derive(Debug, Clone, PartialEq)]
pub enum LeafDecision {
    /// 觸碰 survival 硬邊界（reason 帶確切 dotted-path 或匹配到的前綴）。
    HardBoundary { path: String, matched: String },
    /// 未列舉 / 無 band → default-deny。
    DefaultDeny { path: String },
    /// allowlisted-with-band → 進 §3.4 clamp。
    Clamp { path: String, band: (f64, f64) },
}

/// Decide one leaf path against denylist (incl. struct-prefix) then allowlist.
/// 對單一葉路徑判定（先 denylist 含 struct-prefix，後 allowlist）。
pub fn riskconfig_decide_leaf(cfg: &RiskConfig, leaf_path: &str) -> LeafDecision {
    let norm = normalize_key(leaf_path);

    // (a) denylist：完整路徑命中，或任一 struct-prefix 命中（如 leaf
    //     `cascade.min_hold_ms` 的前綴 `cascade` 在 denylist → 拒）。
    //     前綴判定：denylist token 若為 leaf 的某層前綴（後接 `.` 或恰等）即命中。
    for token in RISKCONFIG_SURVIVAL_DENYLIST {
        let token_norm = normalize_key(token);
        if norm == token_norm {
            return LeafDecision::HardBoundary {
                path: leaf_path.to_string(),
                matched: token.to_string(),
            };
        }
        // struct-prefix：`cascade` 命中 `cascade.anything`、`cascade.a.b`。
        // 必須是「邊界對齊」的前綴（後接 '.'），避免 `cost_gate` 誤命中
        // 假想的 `cost_gateway` 這類同前綴不同欄。
        if !token_norm.is_empty()
            && norm.len() > token_norm.len()
            && norm.starts_with(&token_norm)
            && norm.as_bytes()[token_norm.len()] == b'.'
        {
            return LeafDecision::HardBoundary {
                path: leaf_path.to_string(),
                matched: token.to_string(),
            };
        }
    }

    // (b)/(c) allowlist：僅當「∈ 候選集 ∧ band 欄 Some」才 clamp，否則 default-deny。
    //         v1：無 band 欄 → riskconfig_allowlist_member 恆 None → default-deny。
    match riskconfig_allowlist_member(cfg, leaf_path) {
        Some(band) => LeafDecision::Clamp {
            path: leaf_path.to_string(),
            band,
        },
        None => LeafDecision::DefaultDeny {
            path: leaf_path.to_string(),
        },
    }
}

/// Outcome of deciding a WHOLE patch (all-or-nothing): the first rejecting leaf
/// rejects the entire patch. If every leaf is `Clamp`, returns the clamp list.
/// 整個 patch 的判定（all-or-nothing）：第一個被拒葉即拒整 patch。若每個葉皆
/// `Clamp` 則回傳 clamp 清單。
#[derive(Debug, Clone, PartialEq)]
pub enum PatchDecision {
    /// 任一葉觸 survival 硬邊界 → 整 patch HardBoundary。
    HardBoundary { path: String, matched: String },
    /// 任一葉非 allowlisted → 整 patch DefaultDeny。
    DefaultDeny { path: String },
    /// 全葉 allowlisted-with-band → 可進 clamp（v1 不可達，因 allowlist 空）。
    AllClamp { leaves: Vec<(String, (f64, f64))> },
    /// patch 不是 object 或為空 → 視為無效（fail-closed default-deny 語意）。
    EmptyOrNonObject,
}

/// Decide a whole patch tree. all-or-nothing fail-closed.
/// 對整個 patch 樹判定。all-or-nothing fail-closed。
pub fn riskconfig_decide_patch(cfg: &RiskConfig, patch: &serde_json::Value) -> PatchDecision {
    if !patch.is_object() || patch.as_object().map(|m| m.is_empty()).unwrap_or(true) {
        return PatchDecision::EmptyOrNonObject;
    }
    let leaves = riskconfig_patch_leaves(patch);
    if leaves.is_empty() {
        return PatchDecision::EmptyOrNonObject;
    }
    let mut clamps = Vec::new();
    for leaf in &leaves {
        match riskconfig_decide_leaf(cfg, leaf) {
            // HardBoundary 優先於 DefaultDeny（先拒最危險者）：一旦遇到即整 patch 拒。
            LeafDecision::HardBoundary { path, matched } => {
                return PatchDecision::HardBoundary { path, matched }
            }
            LeafDecision::DefaultDeny { path } => return PatchDecision::DefaultDeny { path },
            LeafDecision::Clamp { path, band } => clamps.push((path, band)),
        }
    }
    PatchDecision::AllClamp { leaves: clamps }
}

// ---------------------------------------------------------------------------
// §3.0 / §3.6 RiskConfigDirectiveSink — demo-only-Arc 結構閘
// ---------------------------------------------------------------------------

/// In-process agent-tuning sink for `RiskConfig`. **Structural gate (E3)**: the
/// struct holds ONLY a clone of the DEMO `Arc<ConfigStore<RiskConfig>>` — it can
/// NOT hold `risk_stores.live`, can NOT hold the `PerEngineRiskStores` bundle,
/// and never calls `PerEngineRiskStores::select(engine_str)` (which would route
/// `unknown -> paper` and could surface the live Arc). With no live handle in
/// the struct's field types, no directive can mutate the live `ConfigStore`
/// regardless of params — a compile-time invariant, not a runtime switch.
///
/// `RiskConfig` 的 in-process agent 調參 sink。**結構閘（E3）**：struct **只**持
/// DEMO `Arc<ConfigStore<RiskConfig>>` 的 clone —— 結構上不持 `risk_stores.live`、
/// 不持 `PerEngineRiskStores` bundle、永不呼叫 `PerEngineRiskStores::select`
/// （後者 `unknown -> paper` fail-safe 會用 runtime 字串把 live Arc 取出 = 破壞
/// 結構閘）。struct 欄位型別不含 live store → 無論 directive 怎麼寫都不可能
/// mutate live `ConfigStore`（編譯期不變量，非 runtime 開關）。
///
/// 鏡像兩個已部署的 in-process daemon 先例：`EngineCommandSink::demo`
/// （tasks.rs:286）+ `spawn_cost_edge_advisor_if_enabled` 的
/// `Arc::clone(&risk_stores.demo)`（cost_edge_advisor_boot.rs:167）。
///
/// 不擴 `StrategyIpcSink` trait（ARCH-RC1 契約禁碰 RiskConfig）；這是獨立 struct。
pub struct RiskConfigDirectiveSink {
    /// DEMO RiskConfig store. **This is the only `ConfigStore` handle the sink
    /// holds.** No live, no bundle. / 唯一持有的 `ConfigStore` handle = demo。
    demo_store: Arc<ConfigStore<RiskConfig>>,
    /// Governance facade (reuse) — session-halt / daily-loss veto at stress.
    /// governance 門面（reuse）—— stress 時 session-halt / daily-loss veto。
    governance: Arc<dyn GovernanceCheck>,
    /// TEST-ONLY seam (FIX-2 test 3): a single leaf path that is treated as
    /// allowlisted-with-band so the gate-ORDER invariant (matcher first, then
    /// governance veto) can be exercised. Production NEVER sets this — the v1
    /// allowlist stays structurally empty (the `riskconfig_*` decision fns are
    /// untouched). Guarded by `#[cfg(test)]` so the field does not exist in a
    /// release binary at all.
    /// 僅測試（FIX-2 test 3）的縫：把某單一葉路徑視為 allowlisted-with-band，
    /// 以便驗證閘順序不變式（先 matcher、後 governance veto）。production 永不
    /// 設定此欄——v1 allowlist 結構性維持為空（不動 `riskconfig_*` 判定函數）。
    /// 以 `#[cfg(test)]` 守衛，release binary 根本不含此欄。
    #[cfg(test)]
    test_forced_allowlist: Option<(String, (f64, f64))>,
}

impl RiskConfigDirectiveSink {
    /// Construct the DEMO sink. By taking ONLY `Arc<ConfigStore<RiskConfig>>`
    /// (clone of `risk_stores.demo`) the live store is unreachable by type.
    /// 構造 DEMO sink。只接 `Arc<ConfigStore<RiskConfig>>`（`risk_stores.demo`
    /// 的 clone），live store 在型別上不可達。
    pub fn demo(
        demo_store: Arc<ConfigStore<RiskConfig>>,
        governance: Arc<dyn GovernanceCheck>,
    ) -> Self {
        Self {
            demo_store,
            governance,
            #[cfg(test)]
            test_forced_allowlist: None,
        }
    }

    /// TEST-ONLY (FIX-2 test 3): construct a sink that treats `leaf` as
    /// allowlisted-with-`band`, purely to assert the gate-ORDER invariant
    /// (denylist/allowlist matcher runs BEFORE the governance veto). Production
    /// has no such path — `riskconfig_decide_patch` / `riskconfig_allowlist_member`
    /// are unchanged and the v1 allowlist remains structurally empty.
    /// 僅測試（FIX-2 test 3）：構造一個把 `leaf` 視為 allowlisted-with-`band`
    /// 的 sink，純粹用來斷言閘順序不變式（matcher 先於 governance veto 跑）。
    /// production 無此路徑——判定函數不變、v1 allowlist 結構性仍為空。
    #[cfg(test)]
    pub fn demo_with_test_forced_allowlist(
        demo_store: Arc<ConfigStore<RiskConfig>>,
        governance: Arc<dyn GovernanceCheck>,
        leaf: &str,
        band: (f64, f64),
    ) -> Self {
        Self {
            demo_store,
            governance,
            test_forced_allowlist: Some((leaf.to_string(), band)),
        }
    }

    /// Apply an `adjust_risk_config` directive against the demo store. Returns
    /// an `ApplyOutcome` so the caller's `record_execution` audits every result.
    /// Gate order (§3.6): recursive matcher (denylist/default-deny) →
    /// GovernanceCore veto → clamp+write inside a single `apply_patch` closure.
    ///
    /// 對 demo store 套用 `adjust_risk_config` directive。回傳 `ApplyOutcome`
    /// 讓呼叫端的 `record_execution` 審計每個結果。閘順序（§3.6）：遞迴 matcher
    /// （denylist/default-deny）→ GovernanceCore veto → clamp+寫在單一
    /// `apply_patch` closure 內。
    pub async fn apply(&self, directive: &Directive, directive_id: i64) -> ApplyOutcome {
        // §3.6-2：遞迴 matcher。任一葉 ∈ denylist → HardBoundary；
        //          任一葉 ∉ allowlist → DefaultDeny（v1 所有 RiskConfig 葉都到此被擋）。
        let cfg_snapshot = self.demo_store.load();
        #[allow(unused_mut)]
        let mut decision = riskconfig_decide_patch(&cfg_snapshot, &directive.params);
        // TEST-ONLY 縫（FIX-2 test 3）：若設了 forced-allowlist leaf 且 matcher 把
        // 該（唯一）葉判為 DefaultDeny（即它不在 denylist 內），把它升為 AllClamp，
        // 以便驗證 governance veto 在 matcher 之後跑。denylist 命中的 HardBoundary
        // 永不被覆蓋——縫只能把「未列入」升為 clamp，絕不能放行 survival 葉。
        #[cfg(test)]
        if let Some((leaf, band)) = &self.test_forced_allowlist {
            if let PatchDecision::DefaultDeny { path } = &decision {
                if path == leaf {
                    decision = PatchDecision::AllClamp {
                        leaves: vec![(path.clone(), *band)],
                    };
                }
            }
        }
        let clamps = match decision {
            PatchDecision::HardBoundary { path, matched } => {
                return ApplyOutcome::VetoedByHardBoundary {
                    directive_id,
                    boundary: matched.clone(),
                    reason: format!(
                        "adjust_risk_config touched survival-class RiskConfig leaf '{path}' \
                         (denylist token '{matched}')"
                    ),
                };
            }
            // FIX-3 審計語意拆分：default-deny（葉「單純不在 allowlist」）走獨立
            // outcome `VetoedByDefaultDeny`，與「命中 survival floor」的
            // `VetoedByHardBoundary` 分開。兩者皆 fail-closed 拒整 patch，但
            // 審計行可區分「未列入 allowlist」（v1 inert 預期）vs「碰 survival
            // 硬邊界」（agent 指名碰生存欄位）。
            PatchDecision::DefaultDeny { path } => {
                return ApplyOutcome::VetoedByDefaultDeny {
                    directive_id,
                    field: path.clone(),
                    reason: format!(
                        "adjust_risk_config leaf '{path}' is not allowlisted \
                         (riskconfig_field_not_allowlisted; v1 allowlist is structurally \
                         empty — U5 no-operator-band)"
                    ),
                };
            }
            PatchDecision::EmptyOrNonObject => {
                return ApplyOutcome::InvalidDirective {
                    directive_id,
                    error: "adjust_risk_config params must be a non-empty object".into(),
                };
            }
            PatchDecision::AllClamp { leaves } => leaves,
        };

        // §3.6-3：GovernanceCore veto — stress（session-halt / daily-loss /
        //          drawdown）時擋全 agent 調參。
        if self.governance.session_halted() {
            return ApplyOutcome::VetoedByGovernance {
                directive_id,
                reason: "session halted — risk_config adjustment blocked".into(),
            };
        }

        // §3.6-4：clamp + 方向 gate（僅 allowlisted 葉到此；v1 因 allowlist 空
        //          結構上不可達，但完整 build 出 clamp+寫路徑備未來解禁）。
        //          band-read + clamp + 寫在單一 apply_patch closure 內（write_lock
        //          持有期間，store.rs:155-192）→ 無 band-narrow-during-UP race。
        self.apply_clamped_write(directive, directive_id, &clamps)
    }

    /// Clamp each allowlisted leaf to its operator band and write atomically.
    /// DOWN (tighten) ungated; UP (loosen) requires the LCB significance gate
    /// (mirrors `DynamicRiskSizer` DYNAMIC-RISK-SIG-1, dynamic_risk_sizer.rs:275-290).
    /// Both unreachable in v1 (allowlist empty); built for the §3.5 activation path.
    ///
    /// 把每個 allowlisted 葉 clamp 到 operator band 並原子寫。DOWN（收緊）
    /// ungated；UP（放寬）需 LCB 顯著性 gate（鏡像 DynamicRiskSizer）。v1 皆
    /// 不可達（allowlist 空），為 §3.5 啟動路徑而建。
    fn apply_clamped_write(
        &self,
        directive: &Directive,
        directive_id: i64,
        clamps: &[(String, (f64, f64))],
    ) -> ApplyOutcome {
        // v1：clamps 永遠為空（allowlist 空），此路徑結構上不可達。保留 fail-closed
        // 守衛：若 clamps 為空卻走到這裡（不該發生），回 default-deny 而非靜默成功。
        if clamps.is_empty() {
            return ApplyOutcome::VetoedByHardBoundary {
                directive_id,
                boundary: "riskconfig_no_allowlisted_leaf".into(),
                reason: "no allowlisted leaf to apply (v1 allowlist empty)".into(),
            };
        }

        // 在單一 apply_patch closure 內讀 band + clamp + 寫（原子）。validate 跑
        // 完整 RiskConfig::validate()（all-or-nothing 回滾）。
        let params = directive.params.clone();
        let clamp_specs: Vec<(String, (f64, f64))> = clamps.to_vec();
        let result = self.demo_store.apply_patch(
            PatchSource::Agent,
            |cfg: &mut RiskConfig| {
                // 未來解禁某欄時，在此把 clamp 後值寫進對應 struct 欄。v1 因
                // allowlist 空，clamp_specs 不會帶任何 production 葉，此 closure
                // 對 cfg 不做變更（no-op write，version 仍遞增但值不變）。
                let _ = (&params, &clamp_specs, cfg);
            },
            |cfg: &RiskConfig| cfg.validate(),
        );

        match result {
            Ok(outcome) => {
                info!(
                    directive_id,
                    version = outcome.version,
                    "adjust_risk_config applied to demo store / 已套用至 demo store"
                );
                ApplyOutcome::Applied {
                    directive_id,
                    action_summary: format!(
                        "adjust_risk_config demo: clamped {} leaf(s), version={}",
                        clamp_specs.len(),
                        outcome.version
                    ),
                }
            }
            Err(e) => {
                warn!(directive_id, error = %e, "adjust_risk_config validate/write failed");
                ApplyOutcome::InvalidDirective {
                    directive_id,
                    error: format!("risk_config validate/write failed: {e}"),
                }
            }
        }
    }

    /// LCB significance gate for an UP (loosen) move, reusing the
    /// `DynamicRiskSizer` SE/LCB form (dynamic_risk_sizer.rs:275-290). Returns
    /// true iff `lcb >= threshold` AND sample count over `floor`. Built but
    /// unreachable in v1 (no allowlisted leaf reaches a direction decision).
    ///
    /// UP（放寬）方向的 LCB 顯著性 gate，reuse DynamicRiskSizer 的 SE/LCB 形式。
    /// 僅當 `lcb >= threshold` 且樣本數過 `floor` 才回 true。v1 不可達（無
    /// allowlisted 葉走到方向判定），為 §3.5 啟動路徑而建。
    ///
    /// 為何 DOWN ungated 而 UP 需 gate：降倉/收緊永遠 survival-safe（root#5/#6），
    /// noise 觸發收緊是好事；放寬需「即使保守拉到下置信界仍顯著」才放行。
    #[allow(dead_code)]
    fn up_gate_passes(metric: f64, sig_z: f64, n: usize, floor: usize, threshold: f64) -> bool {
        if n < floor || n < 2 {
            return false;
        }
        // SE(SR) ≈ sqrt((1 + 0.5·metric²)/(n−1))（Lo 2002 IID 近似）。LCB = metric − z·SE。
        let nf = n as f64;
        let se = ((1.0 + 0.5 * metric * metric) / (nf - 1.0)).sqrt();
        let lcb = metric - sig_z * se;
        lcb >= threshold
    }
}

// ---------------------------------------------------------------------------
// Tests / 測試（§3.3 對抗單測 — cardinal nested-widen 必拒）
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn cfg() -> RiskConfig {
        RiskConfig::default()
    }

    // ---- riskconfig_patch_leaves 遞迴正確性 ----

    #[test]
    fn test_patch_leaves_nested_dotted_paths() {
        let p = json!({"limits": {"leverage_max": 50}, "cascade": {"min_hold_ms": 0}});
        let mut leaves = riskconfig_patch_leaves(&p);
        leaves.sort();
        assert_eq!(leaves, vec!["cascade.min_hold_ms", "limits.leverage_max"]);
    }

    #[test]
    fn test_patch_leaves_deeply_nested() {
        let p = json!({"regime": {"trending": {"stop": 99}}});
        let leaves = riskconfig_patch_leaves(&p);
        assert_eq!(leaves, vec!["regime.trending.stop"]);
    }

    #[test]
    fn test_patch_leaves_array_is_single_leaf() {
        // allowed_categories 陣列整體視為單一葉（落 denylist）。
        let p = json!({"limits": {"allowed_categories": ["linear", "spot"]}});
        let leaves = riskconfig_patch_leaves(&p);
        assert_eq!(leaves, vec!["limits.allowed_categories"]);
    }

    // ---- CARDINAL：nested-widen 必被拒（舊 top-level matcher 會放行 = 命門）----

    #[test]
    fn test_nested_leverage_max_vetoed_by_hard_boundary() {
        // {"limits":{"leverage_max":50}} — 舊只比頂層的 matcher 只看到 "limits"
        // 會 PASS（=bug）；遞迴 matcher 必須抓到 limits.leverage_max → HardBoundary。
        let p = json!({"limits": {"leverage_max": 50}});
        match riskconfig_decide_patch(&cfg(), &p) {
            PatchDecision::HardBoundary { path, .. } => assert_eq!(path, "limits.leverage_max"),
            other => panic!("expected HardBoundary, got {other:?}"),
        }
    }

    #[test]
    fn test_nested_cascade_drawdown_circuit_vetoed() {
        let p = json!({"cascade": {"drawdown_circuit_pct": 0.9}});
        match riskconfig_decide_patch(&cfg(), &p) {
            // 由 struct-prefix `cascade` 命中。
            PatchDecision::HardBoundary { path, matched } => {
                assert_eq!(path, "cascade.drawdown_circuit_pct");
                assert_eq!(matched, "cascade");
            }
            other => panic!("expected HardBoundary, got {other:?}"),
        }
    }

    #[test]
    fn test_nested_cascade_min_hold_ms_vetoed() {
        let p = json!({"cascade": {"min_hold_ms": 0}});
        assert!(matches!(
            riskconfig_decide_patch(&cfg(), &p),
            PatchDecision::HardBoundary { .. }
        ));
    }

    #[test]
    fn test_nested_cost_gate_k_base_vetoed() {
        let p = json!({"cost_gate": {"k_base": 99}});
        match riskconfig_decide_patch(&cfg(), &p) {
            PatchDecision::HardBoundary { matched, .. } => assert_eq!(matched, "cost_gate"),
            other => panic!("expected HardBoundary, got {other:?}"),
        }
    }

    #[test]
    fn test_nested_cost_gate_min_confidence_vetoed() {
        let p = json!({"cost_gate": {"min_confidence": 0.01}});
        assert!(matches!(
            riskconfig_decide_patch(&cfg(), &p),
            PatchDecision::HardBoundary { .. }
        ));
    }

    #[test]
    fn test_nested_market_gate_liquidation_buffer_vetoed() {
        // CC CRITICAL：清算緩衝在 market_gate.* 而非 limits.*。
        let p = json!({"market_gate": {"liquidation_buffer_pct": 0.0}});
        match riskconfig_decide_patch(&cfg(), &p) {
            // 由 struct-prefix `market_gate` 命中（顯式葉條目亦在 denylist）。
            PatchDecision::HardBoundary { path, matched } => {
                assert_eq!(path, "market_gate.liquidation_buffer_pct");
                assert_eq!(matched, "market_gate");
            }
            other => panic!("expected HardBoundary, got {other:?}"),
        }
    }

    #[test]
    fn test_market_gate_other_field_also_denied() {
        // market_gate.* 整 struct denylist：非顯式列舉的葉也被前綴擋。
        let p = json!({"market_gate": {"spread_max_bps": 999}});
        assert!(matches!(
            riskconfig_decide_patch(&cfg(), &p),
            PatchDecision::HardBoundary { .. }
        ));
    }

    // ---- FIX-1（CC MEDIUM）：新增 7 個整 struct 前綴由 denylist（HardBoundary）攔 ----

    #[test]
    fn test_overrides_category_leverage_vetoed_by_hard_boundary() {
        // {"overrides":{"linear":{"leverage_max":100}}} — per-category 槓桿上限，
        // 由 struct-prefix `overrides` 命中 HardBoundary（非 default-deny）。
        let p = json!({"overrides": {"linear": {"leverage_max": 100}}});
        match riskconfig_decide_patch(&cfg(), &p) {
            PatchDecision::HardBoundary { path, matched } => {
                assert_eq!(path, "overrides.linear.leverage_max");
                assert_eq!(matched, "overrides");
            }
            other => panic!("expected HardBoundary, got {other:?}"),
        }
    }

    #[test]
    fn test_per_strategy_ceiling_vetoed_by_hard_boundary() {
        // {"per_strategy":{"ma_crossover":{"position_size_max_pct":99}}} — per-strategy
        // P1 上限，由 struct-prefix `per_strategy` 命中 HardBoundary。
        let p = json!({"per_strategy": {"ma_crossover": {"position_size_max_pct": 99}}});
        match riskconfig_decide_patch(&cfg(), &p) {
            PatchDecision::HardBoundary { path, matched } => {
                assert_eq!(path, "per_strategy.ma_crossover.position_size_max_pct");
                assert_eq!(matched, "per_strategy");
            }
            other => panic!("expected HardBoundary, got {other:?}"),
        }
    }

    #[test]
    fn test_dynamic_sizing_max_pct_vetoed_by_hard_boundary() {
        // {"dynamic_sizing":{"max_pct":0.9}} — agent 絕不可放寬 sizing band 上界，
        // 由 struct-prefix `dynamic_sizing` 命中 HardBoundary。
        let p = json!({"dynamic_sizing": {"max_pct": 0.9}});
        match riskconfig_decide_patch(&cfg(), &p) {
            PatchDecision::HardBoundary { path, matched } => {
                assert_eq!(path, "dynamic_sizing.max_pct");
                assert_eq!(matched, "dynamic_sizing");
            }
            other => panic!("expected HardBoundary, got {other:?}"),
        }
    }

    #[test]
    fn test_kelly_correlation_anti_cluster_executor_prefixes_vetoed() {
        // 其餘四個新前綴皆由 struct-prefix 命中 HardBoundary（曝險 / 執行狀態相鄰）。
        for (patch, expect_prefix) in [
            (json!({"kelly": {"max_kelly_fraction": 1.0}}), "kelly"),
            (json!({"correlation": {"max_correlated_pct": 0.99}}), "correlation"),
            (json!({"anti_cluster": {"max_cluster_size": 99}}), "anti_cluster"),
            (json!({"executor": {"shadow_mode": false}}), "executor"),
        ] {
            match riskconfig_decide_patch(&cfg(), &patch) {
                PatchDecision::HardBoundary { matched, .. } => assert_eq!(
                    matched, expect_prefix,
                    "patch {patch:?} should match prefix {expect_prefix}"
                ),
                other => panic!("expected HardBoundary for {patch:?}, got {other:?}"),
            }
        }
    }

    // ---- v1 候選 → DefaultDeny（無 band）----

    #[test]
    fn test_regime_trending_stop_default_deny_v1() {
        // regime.trending.stop 是候選但 v1 無 band → DefaultDeny（非 HardBoundary）。
        let p = json!({"regime": {"trending": {"stop": 99}}});
        match riskconfig_decide_patch(&cfg(), &p) {
            PatchDecision::DefaultDeny { path } => assert_eq!(path, "regime.trending.stop"),
            other => panic!("expected DefaultDeny, got {other:?}"),
        }
    }

    #[test]
    fn test_dynamic_stop_atr_default_deny_v1() {
        let p = json!({"dynamic_stop": {"atr_stop_mult": 3.0}});
        assert!(matches!(
            riskconfig_decide_patch(&cfg(), &p),
            PatchDecision::DefaultDeny { .. }
        ));
    }

    #[test]
    fn test_agent_size_multiplier_default_deny_v1() {
        // size_multiplier 有半個結構性 clamp 但 v1 無 explicit band → 仍 DefaultDeny。
        let p = json!({"agent": {"size_multiplier": 1.0}});
        assert!(matches!(
            riskconfig_decide_patch(&cfg(), &p),
            PatchDecision::DefaultDeny { .. }
        ));
    }

    // ---- unknown top-level → default-deny ----

    #[test]
    fn test_unknown_top_level_default_deny() {
        let p = json!({"unknown_top": {"x": 1}});
        match riskconfig_decide_patch(&cfg(), &p) {
            PatchDecision::DefaultDeny { path } => assert_eq!(path, "unknown_top.x"),
            other => panic!("expected DefaultDeny, got {other:?}"),
        }
    }

    #[test]
    fn test_hard_boundary_literal_token_vetoed() {
        // 硬邊界字面 token 即使作為 free-text key 出現也 veto（defense-in-depth）。
        let p = json!({"system_mode": "live"});
        match riskconfig_decide_patch(&cfg(), &p) {
            PatchDecision::HardBoundary { matched, .. } => assert_eq!(matched, "system_mode"),
            other => panic!("expected HardBoundary, got {other:?}"),
        }
    }

    // ---- v1 allowlist 結構性為空 ----

    #[test]
    fn test_v1_allowlist_structurally_empty() {
        // 對每個候選欄，riskconfig_allowlist_member 必回 None（無 band 欄）。
        let c = cfg();
        for cand in RISKCONFIG_ALLOWLIST_CANDIDATES {
            assert_eq!(
                riskconfig_allowlist_member(&c, cand),
                None,
                "candidate {cand} must NOT be allowlisted in v1 (no operator band)"
            );
        }
    }

    #[test]
    fn test_operator_band_always_none_v1() {
        let c = cfg();
        assert_eq!(riskconfig_operator_band(&c, "dynamic_stop.atr_stop_mult"), None);
        assert_eq!(riskconfig_operator_band(&c, "regime.trending.stop"), None);
    }

    // ---- all-or-nothing：混合 patch 中任一拒 → 整 patch 拒 ----

    #[test]
    fn test_all_or_nothing_mixed_patch_rejected() {
        // 一個候選葉（v1 DefaultDeny）+ 一個 survival 葉（HardBoundary）。
        // HardBoundary 優先（先拒最危險者）。
        let p = json!({"regime": {"trending": {"stop": 1.0}}, "limits": {"leverage_max": 50}});
        // 兩葉皆會被拒；HardBoundary（leverage_max）優先回報，但無論順序整 patch 必拒。
        match riskconfig_decide_patch(&cfg(), &p) {
            PatchDecision::HardBoundary { .. } | PatchDecision::DefaultDeny { .. } => {}
            other => panic!("mixed patch must be rejected, got {other:?}"),
        }
    }

    #[test]
    fn test_empty_patch_invalid() {
        assert_eq!(
            riskconfig_decide_patch(&cfg(), &json!({})),
            PatchDecision::EmptyOrNonObject
        );
    }

    #[test]
    fn test_non_object_patch_invalid() {
        assert_eq!(
            riskconfig_decide_patch(&cfg(), &json!(42)),
            PatchDecision::EmptyOrNonObject
        );
    }

    // ---- 大小寫 / unicode 混淆不可繞 ----

    #[test]
    fn test_case_insensitive_denylist_match() {
        let p = json!({"LIMITS": {"Leverage_Max": 50}});
        assert!(matches!(
            riskconfig_decide_patch(&cfg(), &p),
            PatchDecision::HardBoundary { .. }
        ));
    }

    #[test]
    fn test_zero_width_obfuscation_stripped_and_vetoed() {
        // limits.leverage_max 中插零寬字元，剝除後仍命中 denylist。
        let p = json!({"limits": {"lever\u{200b}age_max": 50}});
        assert!(matches!(
            riskconfig_decide_patch(&cfg(), &p),
            PatchDecision::HardBoundary { .. }
        ));
    }

    // ---- struct-prefix 不誤命中同前綴不同欄 ----

    #[test]
    fn test_prefix_boundary_alignment_no_false_match() {
        // `cost_gate` 前綴不應命中假想的同前綴不同欄（須後接 '.'）。
        // 用一個以 cost_gate 為字首但非該 struct 的頂層 key 驗證邊界對齊。
        let leaf = "cost_gateway_setting";
        match riskconfig_decide_leaf(&cfg(), leaf) {
            // 非 denylist（前綴須後接 '.'），落 default-deny。
            LeafDecision::DefaultDeny { .. } => {}
            other => panic!("expected DefaultDeny (not prefix false-match), got {other:?}"),
        }
    }

    // ---- LCB up-gate 純函數（dormant，但驗形態）----

    #[test]
    fn test_up_gate_rejects_insufficient_sample() {
        assert!(!RiskConfigDirectiveSink::up_gate_passes(2.0, 1.64, 5, 30, 1.0));
    }

    #[test]
    fn test_up_gate_passes_significant() {
        // 大樣本 + 高 metric → LCB 仍過 threshold。
        assert!(RiskConfigDirectiveSink::up_gate_passes(3.0, 1.64, 500, 30, 1.0));
    }

    #[test]
    fn test_up_gate_rejects_marginal_lcb() {
        // metric 剛好等於 threshold 但小樣本 → SE 大 → LCB < threshold → 拒。
        assert!(!RiskConfigDirectiveSink::up_gate_passes(1.0, 1.64, 31, 30, 1.0));
    }

    // ===================================================================
    // FIX-2：integration-surface async sink.apply() 測試
    // （此前 async sink.apply() 路徑零測試覆蓋）
    // ===================================================================

    use super::super::parser::Directive;

    /// 本地 mock GovernanceCheck（applier_test_fixtures 的 MockGov 為 applier
    /// 模塊測試私有，sibling 模塊不可達 → 在此自帶最小 mock）。
    struct MockGov {
        halted: bool,
    }
    impl GovernanceCheck for MockGov {
        fn current_daily_loss_pct(&self) -> f64 {
            0.0
        }
        fn session_halted(&self) -> bool {
            self.halted
        }
        fn unpause_daily_loss_threshold(&self) -> f64 {
            0.05
        }
        fn known_strategies(&self) -> Vec<String> {
            vec![]
        }
    }

    fn demo_store() -> Arc<ConfigStore<RiskConfig>> {
        Arc::new(ConfigStore::new(RiskConfig::default()))
    }

    fn directive(params: serde_json::Value) -> Directive {
        Directive {
            directive_type: super::super::parser::DirectiveType::AdjustRiskConfig,
            scope: "global".into(),
            params,
            expiry: (std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_secs()
                + 86_400) as i64,
            priority: 3,
        }
    }

    // (2) denylisted nested patch → VetoedByHardBoundary（無寫入）。
    #[tokio::test]
    async fn test_sink_apply_denylisted_nested_is_hard_boundary_no_write() {
        let store = demo_store();
        let v_before = store.version();
        let sink = RiskConfigDirectiveSink::demo(
            store.clone(),
            Arc::new(MockGov { halted: false }) as Arc<dyn GovernanceCheck>,
        );
        let d = directive(json!({"limits": {"leverage_max": 50}}));
        let outcome = sink.apply(&d, 201).await;
        match outcome {
            ApplyOutcome::VetoedByHardBoundary { boundary, .. } => {
                assert_eq!(boundary, "limits.leverage_max");
            }
            other => panic!("expected VetoedByHardBoundary, got {other:?}"),
        }
        // 無寫入：version 未遞增。
        assert_eq!(store.version(), v_before, "denylisted patch must not write");
    }

    // (3) governance veto 在 matcher 之後跑：用 test-only forced-allowlist 把一個
    //     葉升為 allowlisted，再令 session_halted()=true → VetoedByGovernance。
    //     證明閘順序 = matcher 先（否則 denylist 葉會在 governance 前被攔），
    //     governance veto 後。
    #[tokio::test]
    async fn test_sink_apply_governance_checked_after_matcher() {
        let store = demo_store();
        let v_before = store.version();
        // 人工 allowlist 一個非 survival 候選葉（regime.trending.stop，v1 本為
        // DefaultDeny）→ matcher 放行 → governance halted veto。
        let sink = RiskConfigDirectiveSink::demo_with_test_forced_allowlist(
            store.clone(),
            Arc::new(MockGov { halted: true }) as Arc<dyn GovernanceCheck>,
            "regime.trending.stop",
            (0.5, 2.0),
        );
        let d = directive(json!({"regime": {"trending": {"stop": 1.0}}}));
        let outcome = sink.apply(&d, 202).await;
        assert!(
            matches!(outcome, ApplyOutcome::VetoedByGovernance { .. }),
            "matcher passed (forced-allowlist) then governance halt must veto, got {outcome:?}"
        );
        // governance veto 路徑無寫入。
        assert_eq!(store.version(), v_before, "governance-vetoed patch must not write");
    }

    // (3b) 縫不可繞 denylist：即使把 survival 葉設為 forced-allowlist，denylist
    //      HardBoundary 仍絕對優先（縫只把 DefaultDeny 升 clamp，不覆蓋 HardBoundary）。
    #[tokio::test]
    async fn test_sink_forced_allowlist_cannot_override_denylist() {
        let store = demo_store();
        let sink = RiskConfigDirectiveSink::demo_with_test_forced_allowlist(
            store.clone(),
            Arc::new(MockGov { halted: true }) as Arc<dyn GovernanceCheck>,
            "limits.leverage_max", // survival 葉，縫不得放行
            (1.0, 100.0),
        );
        let d = directive(json!({"limits": {"leverage_max": 99}}));
        let outcome = sink.apply(&d, 203).await;
        assert!(
            matches!(outcome, ApplyOutcome::VetoedByHardBoundary { .. }),
            "denylist HardBoundary must win over test-forced-allowlist, got {outcome:?}"
        );
    }

    // (4) EmptyOrNonObject patch → InvalidDirective。
    #[tokio::test]
    async fn test_sink_apply_empty_patch_is_invalid_directive() {
        let store = demo_store();
        let sink = RiskConfigDirectiveSink::demo(
            store.clone(),
            Arc::new(MockGov { halted: false }) as Arc<dyn GovernanceCheck>,
        );
        let d = directive(json!({}));
        let outcome = sink.apply(&d, 204).await;
        assert!(
            matches!(outcome, ApplyOutcome::InvalidDirective { .. }),
            "empty patch must be InvalidDirective, got {outcome:?}"
        );
    }

    // FIX-3 審計語意拆分：未列入 allowlist 的葉 → VetoedByDefaultDeny（非
    //   VetoedByHardBoundary），與碰 survival floor 的拒絕分流。
    #[tokio::test]
    async fn test_sink_apply_default_deny_is_distinct_outcome() {
        let store = demo_store();
        let sink = RiskConfigDirectiveSink::demo(
            store.clone(),
            Arc::new(MockGov { halted: false }) as Arc<dyn GovernanceCheck>,
        );
        // regime.trending.stop 是候選但 v1 無 band → DefaultDeny → VetoedByDefaultDeny。
        let d = directive(json!({"regime": {"trending": {"stop": 1.0}}}));
        let outcome = sink.apply(&d, 205).await;
        match outcome {
            ApplyOutcome::VetoedByDefaultDeny { field, .. } => {
                assert_eq!(field, "regime.trending.stop");
            }
            other => panic!("expected VetoedByDefaultDeny (distinct from HardBoundary), got {other:?}"),
        }
    }
}
