/**
 * REF-20 Wave 2 P1-U9 — Paper Replay Lab 中文 i18n 對照表
 * REF-20 Wave 2 P1-U9 — Paper Replay Lab Chinese i18n table (Chinese dominant)
 *
 * MODULE_NOTE
 * 模組目的：集中管理 Paper Replay Lab UI 介面所有 operator-facing 字串的中英對照，
 *           中文為主導（per `feedback_chinese_output`），技術名詞保留 English（per
 *           `bilingual-comment-style` skill）。9 對照表覆蓋 mode badge / verdict /
 *           disabled state / execution confidence / calibration freshness / sample
 *           power / handoff phrase / terminology / acceptance check。
 * Module purpose: centralize all operator-facing UI string translations for the
 *                 Paper Replay Lab tab. Chinese-dominant (per operator preference);
 *                 technical terms kept in English (per bilingual-comment-style).
 *                 9 lookup tables cover mode badge / verdict / disabled state /
 *                 execution confidence / calibration freshness / sample power /
 *                 handoff phrase / terminology / acceptance check.
 *
 * 上游契約 / Upstream contracts:
 *  - UX SoT: docs/execution_plan/2026-05-02--ref20_ux_subdoc_v1.md
 *    §5 Verdict labels / §6 Handoff fields / §7 Mode Badges / §8 Disabled State
 *    Contract / §9 Terminology / §11 P1 Acceptance
 *  - Workplan: docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
 *    §4 Wave 2 R20-P1-U9 + §5.2 KPI thresholds
 *  - Dispatch: docs/execution_plan/2026-05-03--ref20_wave2_dispatch_v1.md
 *
 * 主要 export / Main exports:
 *  - window.OpenClawI18n_zh: 9 nested 對照表 (read-only lookup map)
 *  - window.t_zh(key_path): dot-path lookup helper, 缺鍵 fallback 至 raw key
 *
 * 依賴 / Dependencies: 無 (standalone, 須在 common.js 之後 / app-paper.js 之前載入)
 *                      None (standalone; load after common.js, before app-paper.js)
 *
 * 硬邊界 / Hard constraints:
 *  - 不變字串 (translation 一旦 land): UI string 變更必同步更新本檔且通知 A3 review
 *  - 中文主導 + 技術名詞 EN: e.g. "煙霧回放 (Smoke Replay)" 而非單純「冒煙測試」
 *  - 純 lookup, 0 backend 寫入 / 0 fetch / 0 API call
 *  - 0 risk param touch, 0 governance impact
 *
 * Invariant / 不變量:
 *  - window.OpenClawI18n_zh 一旦定義即 read-only (caller 禁改寫；如需擴充走 PR)
 *  - 9 對照表 schema 對應 UX subdoc 條目；新增 key 必先 sync UX subdoc
 */

// 中文 i18n 對照表 / Chinese i18n lookup table
// 設為 const + 凍結 (Object.freeze depth-1)，禁意外改寫
window.OpenClawI18n_zh = {

  // ─── Table 1/9: Mode Badge labels (UX §7) ─────────────────────────────────
  // 模式徽章標籤：每筆 replay result 必含 4 維 badge，operator 一眼判斷可執行性
  // Mode badge labels: every visible replay result must show all four badges
  mode_badge: {
    // run_mode 5 值（per UX §7）
    // run_mode 5 values (UX §7)
    run_mode: {
      paper_session: '紙面 Session',
      replay_smoke: '煙霧回放',
      calibrated_replay: '校準回放',
      advisory: '建議證據',
      handoff: '候選交接',
      unknown: '未知'
    },
    // data_tier 5 值 (S0-S4 evidence source)
    // data_tier 5 values (S0-S4 evidence source ladder)
    data_tier: {
      S0: '真實成交 (S0)',
      S1: '真實 ticker (S1)',
      S2: '合成市場 (S2)',
      S3: '純合成 (S3)',
      S4: 'fixture 預設 (S4)',
      real: '真實數據',
      synthetic: '合成數據',
      mixed: '混合',
      unknown: '未知'
    },
    // execution_confidence 3 值（per UX §7 #1 / non-actionable 視覺強制）
    // execution_confidence 3 values (UX §7 rule #1: 'none' must be visually non-actionable)
    // 'none' 字串內含 ⚠️ emoji 為 task spec 對齊；CSS 仍須加灰底+紅邊+tooltip
    // 'none' string includes ⚠️ per task spec; CSS must still apply grey+red border+tooltip
    execution_confidence: {
      none: '無信心 ⚠️',
      limited: '有限信心',
      calibrated: '已校準',
      high: '高信心',                 // legacy alias (P3+ calibrated 同義)
      medium: '中信心',               // legacy alias
      low: '低信心'
    },
    // runtime_environment 2 值
    // runtime_environment 2 values (Linux trade-core vs Mac dev smoke)
    runtime_environment: {
      linux_trade_core: 'Linux 主節點',
      mac_dev_smoke_test_only: 'Mac 開發機（僅冒煙）',
      unknown: '未知'
    },
    // calibration_freshness 3 值（per workplan §5.2 KPI 閾值 ≤72h fresh）
    // calibration_freshness 3 values (per workplan §5.2 freshness threshold ≤72h)
    calibration_freshness: {
      fresh: '新鮮 (≤72h)',
      stale: '陳舊 (>72h)',
      unknown: '未知',
      pending: '待校準'
    },
    // output_policy 3 值（同 execution_confidence 但語義不同：政策 vs 評估）
    // output_policy 3 values (semantic distinct from execution_confidence: policy vs assessment)
    output_policy: {
      actionable: '可執行',
      advisory: '建議',
      none: '不可執行'
    }
  },

  // ─── Table 2/9: Verdict labels (UX §5) ─────────────────────────────────────
  // 判定標籤：Compare sub-tab 顯示 baseline vs candidate 結果
  // Verdict labels: Compare sub-tab baseline vs candidate result classification
  // 重要：永無 `live_approved` replay verdict (per UX §5 last sentence)
  // CRITICAL: there is NO `live_approved` replay verdict (per UX §5)
  verdict: {
    reject: '拒絕 (Reject)',
    defer_data: '延後（資料不足）',
    defer_calibration: '延後（校準不足）',
    research_only: '僅研究 (Research only)',
    demo_candidate: 'Demo 候選 (P6 後)',  // 僅 P6 gate 通過後出現 / only after P6 gates
    pending: '待判定',
    unknown: '未知'
  },

  // ─── Table 3/9: Disabled State Contract (UX §8) ────────────────────────────
  // 禁用狀態合約：disabled controls 必說明確切阻塞 phase/gate
  // Disabled state contract: disabled controls must explain the exact missing gate
  disabled_state: {
    // 6 allowed examples (per UX §8)
    // 6 allowed examples (per UX §8)
    p2_backend_pending: 'P2 後端待施工',
    requires_linux_replay_rerun: '需 Linux 端重跑回放',
    execution_calibration_unavailable: '執行校準尚未可用',
    insufficient_sample_n_lt_30: '樣本不足 (n < 30)',
    handoff_disabled_until_p6: '候選交接 P6 之前停用',
    manifest_signature_missing: '清單簽名缺失',
    // 額外 phase-gate 阻塞語（A3 + workplan 衍生）
    // Additional phase-gate messages (A3 + workplan derived)
    p3_calibration_incomplete: 'P3 校準未完成',
    p4_advisory_not_verified: 'P4 建議尚未驗證',
    mac_no_private_data: 'Mac 開發機禁用真實私有資料',
    cooldown_in_progress: '冷卻中，請稍候',
    duplicate_idempotency_key: '冪等鍵重複',
    // 反模式（禁用顯示文案，operator 看到必 push back）/ Forbidden anti-patterns
    forbidden_coming_soon: '【禁用文案】Coming soon — 必註明 phase/gate',
    forbidden_no_op_click: '【禁用】hidden no-op 點擊'
  },

  // ─── Table 4/9: Execution Confidence detail (UX §7 + §9) ───────────────────
  // 執行可信度詳細：3 維中每維對應的 tooltip + 標誌 (caller 用)
  // Execution confidence detail: tooltip + visual indicator per level
  execution_confidence: {
    none: {
      label: '無信心',
      icon: '⚠️',
      tooltip: '此回放未經執行模型校準，結果僅供結構驗證，不得作為策略決策依據。',
      tooltip_en: 'Replay not calibrated; result is structural-only and must not drive strategy decisions.'
    },
    limited: {
      label: '有限信心',
      icon: '◐',
      tooltip: '已套用粗略費率/maker-taker 模型，但未通過 freshness/power gate；僅參考。',
      tooltip_en: 'Coarse fee/maker-taker model applied; freshness/power gate not yet passed; advisory only.'
    },
    calibrated: {
      label: '已校準',
      icon: '✓',
      tooltip: '已通過 calibration freshness ≤72h + sample power ≥200 雙閘，結果可作為策略證據。',
      tooltip_en: 'Both calibration freshness (≤72h) and sample power (≥200) gates passed; result is policy-grade evidence.'
    }
  },

  // ─── Table 5/9: Calibration Freshness detail (UX §9 + workplan §5.2) ───────
  // 校準新鮮度：≤72h fresh / >72h stale / 等待 / 從未校準
  // Calibration freshness: ≤72h fresh / >72h stale / pending / never
  calibration_freshness: {
    fresh: {
      label: '新鮮',
      threshold_hours: 72,
      tooltip: '校準距今 ≤72 小時，可信賴。',
      tooltip_en: 'Calibration ≤72h old; trustworthy.'
    },
    stale: {
      label: '陳舊',
      threshold_hours: 72,
      tooltip: '校準 >72 小時前，建議重跑。',
      tooltip_en: 'Calibration >72h old; rerun recommended.'
    },
    pending: {
      label: '待校準',
      tooltip: '此 strategy::symbol 尚未完成校準。',
      tooltip_en: 'This strategy::symbol has not been calibrated yet.'
    },
    unknown: {
      label: '未知',
      tooltip: '校準時間戳缺失。',
      tooltip_en: 'Calibration timestamp missing.'
    }
  },

  // ─── Table 6/9: Sample / Power Gate messages (UX §8 + workplan §5.2) ──────
  // 樣本量與 power gate：n<30 / 30≤n<200 limited / n≥200 calibrated
  // Sample / power gate: n<30 / 30≤n<200 limited / n≥200 calibrated thresholds
  sample_power: {
    insufficient: {
      label: '樣本不足',
      threshold: 30,
      tooltip: '樣本數 n < 30，cell 級 calibration 無法成立。',
      tooltip_en: 'n < 30; cell-level calibration cannot be formed.'
    },
    limited: {
      label: '樣本受限',
      threshold_low: 30,
      threshold_high: 200,
      tooltip: '30 ≤ n < 200，可形成假說但未達 power gate。',
      tooltip_en: '30 ≤ n < 200; hypothesis allowed but power gate not met.'
    },
    sufficient: {
      label: '樣本充足',
      threshold: 200,
      tooltip: 'n ≥ 200，通過 strategy-window power gate。',
      tooltip_en: 'n ≥ 200; strategy-window power gate passed.'
    },
    n_lt_30_block: '樣本不足 (n < 30) — handoff blocked',
    n_lt_200_warn: '樣本受限 (n < 200) — calibrated 級別無法達成'
  },

  // ─── Table 7/9: Handoff Phrase / Modal text (UX §6 + workplan R20-P6-H1/H2) ─
  // Handoff 候選交接：typed confirmation phrase + 9 fields + cooldown
  // Handoff: typed confirmation phrase regex + 9 fields + cooldown messages
  handoff_phrase: {
    // typed phrase format (per A3 §7.4 #19 推薦 + workplan R20-P6-S13 regex)
    // Typed phrase format (A3 recommendation + workplan R20-P6-S13 regex)
    phrase_template: 'HANDOFF <experiment_id>',
    phrase_regex: '^HANDOFF [a-z0-9-]{36}$',
    phrase_hint: '請輸入 "HANDOFF " + 36 字元 experiment_id (UUID 格式)',
    phrase_hint_en: 'Type "HANDOFF " + 36-char experiment_id (UUID format)',
    // 9 必填欄位 (per UX §6)
    // 9 required fields (UX §6)
    field_typed_phrase: 'Typed 確認語',
    field_idempotency_key: '冪等鍵',
    field_manifest_hash: '清單雜湊',
    field_baseline_delta: '基準差異',
    field_data_tier: '資料層級',
    field_execution_confidence: '執行可信度',
    field_trace_id: '追蹤 ID',
    field_replay_experiment_id: '回放實驗 ID',
    field_pm_operator_identity: 'PM/Operator 身份',
    // cooldown / 雙 actor messages (workplan §4 R20-P6-H2)
    // Cooldown / dual-actor messages (workplan R20-P6-H2)
    cooldown_active: '冷卻期 ≥30 秒進行中，請稍候',
    cooldown_active_en: 'Cooldown ≥30s in progress',
    dual_actor_required: '需第二位 operator 確認',
    dual_actor_required_en: 'Second operator confirmation required',
    handoff_disabled_pre_p6: 'Handoff 在 P6 之前停用',
    handoff_disabled_pre_p6_en: 'Handoff disabled until P6'
  },

  // ─── Table 8/9: Terminology (UX §9 — 9 official rows) ──────────────────────
  // 9 行官方術語對照（UX §9 直引）+ 1 條 UI 使用準則
  // 9 official terminology rows (verbatim from UX §9) + 1 UI guideline
  terminology: {
    replay: {
      en: 'Replay',
      zh: '快速回放',
      meaning: 'accelerated historical run',
      meaning_zh: '加速歷史運行'
    },
    backtest: {
      en: 'Backtest',
      zh: '回測',
      meaning: 'only for calibrated P3+ reports',
      meaning_zh: '僅 P3+ 校準後 reports 適用'
    },
    smoke_replay: {
      en: 'Smoke Replay',
      zh: '煙霧回放',
      meaning: 'P2 non-actionable test',
      meaning_zh: 'P2 階段不可執行的測試'
    },
    execution_confidence: {
      en: 'Execution Confidence',
      zh: '執行可信度',
      meaning: 'none / limited / calibrated',
      meaning_zh: '無 / 有限 / 已校準'
    },
    data_tier: {
      en: 'Data Tier',
      zh: '資料層級',
      meaning: 'S0-S4 evidence source',
      meaning_zh: 'S0-S4 證據來源階梯'
    },
    baseline: {
      en: 'Baseline',
      zh: '基準配置',
      meaning: 'current/demo snapshot under comparison',
      meaning_zh: '當前/demo 比較中的快照'
    },
    candidate: {
      en: 'Candidate',
      zh: '候選配置',
      meaning: 'config/strategy patch under test',
      meaning_zh: '受測的 config/策略修補'
    },
    handoff: {
      en: 'Handoff',
      zh: '候選交接',
      meaning: 'bounded demo candidate path',
      meaning_zh: '受限 demo 候選路徑'
    },
    advisory: {
      en: 'Advisory',
      zh: '建議證據',
      meaning: 'MLDE/Dream recommendation, not mutation',
      meaning_zh: 'MLDE/Dream 建議，不執行寫入'
    },
    // UI 文案使用準則 (per UX §9 末段)
    // UI copy guideline (UX §9 final paragraph)
    p2_must_use_smoke_not_backtest: 'P2 必用「煙霧回放 / Smoke Replay」，禁稱「回測 / Backtest」'
  },

  // ─── Table 9/9: P1 Acceptance Check labels (UX §11) ────────────────────────
  // P1 驗收 7 條：UI surface 必滿足才能進入 Wave 2 closure
  // P1 acceptance 7 conditions: must pass before Wave 2 closure
  acceptance_check: {
    ia_accepted: 'IA (information architecture) 已接受',
    shell_specified: 'Session/Replay/Compare/Handoff shell 行為已定義',
    manual_controls_removed: '手動 submit/cancel 控制已移除（或隔離至 legacy-only dev 介面）',
    disabled_states_use_phase_gate_language: 'disabled state 使用 phase/gate 語言',
    all_results_have_4_mode_badges: '所有 replay result mock 含 4 mode badge',
    none_state_visually_non_actionable: 'execution_confidence=none 視覺上不可執行',
    handoff_disabled_pre_p6: 'Handoff 在 P6 前無法點擊',
    // P1 完成必跑 regression check
    // P1 completion required regression check
    regression_paper_replay_lab_no_order_submit: 'Paper Replay Lab 不可提交訂單（regression check）'
  }
};

// 凍結頂層 + 9 子表 depth-1（防意外寫入）
// Freeze top-level + each of 9 sub-tables depth-1 (prevent accidental writes)
Object.freeze(window.OpenClawI18n_zh);
Object.keys(window.OpenClawI18n_zh).forEach(function(k) {
  if (typeof window.OpenClawI18n_zh[k] === 'object' && window.OpenClawI18n_zh[k] !== null) {
    Object.freeze(window.OpenClawI18n_zh[k]);
  }
});

/**
 * t_zh — dot-path lookup helper.
 *
 * 用法 / Usage:
 *   t_zh('mode_badge.data_tier.real')          → '真實數據'
 *   t_zh('verdict.reject')                     → '拒絕 (Reject)'
 *   t_zh('execution_confidence.none.label')    → '無信心'
 *   t_zh('terminology.smoke_replay.zh')        → '煙霧回放'
 *
 * 缺鍵處理 / Missing key handling:
 *   缺鍵時返回 raw key path（fail-loud，方便 dev 抓 typo）
 *   Returns raw key path on miss (fail-loud, helps catch dev typos)
 *
 * SAFETY / 不變量:
 *   - 純讀取 / pure read
 *   - 不允許穿越 prototype chain (Object.prototype.toString 等)
 *   - key_path 必為 string (non-string 直接返回 raw input)
 *
 * @param {string} key_path - dot-path key, e.g. 'mode_badge.data_tier.real'
 * @returns {string} 對應中文字串 / corresponding Chinese string, or raw key on miss
 */
window.t_zh = function(key_path) {
  // Edge case: 非 string 輸入直接返回（呼叫端 typo 防禦）
  // Edge: non-string input returns as-is (defensive against typos)
  if (typeof key_path !== 'string' || key_path.length === 0) {
    return String(key_path);
  }

  var parts = key_path.split('.');
  var node = window.OpenClawI18n_zh;
  for (var i = 0; i < parts.length; i++) {
    var p = parts[i];
    // 不變量：只走 own property (per Object.prototype.hasOwnProperty)
    // Invariant: walk only own properties (avoid prototype-chain leaks)
    if (node == null || typeof node !== 'object' ||
        !Object.prototype.hasOwnProperty.call(node, p)) {
      // 缺鍵：返回 raw key 方便 dev 看到 typo
      // Miss: return raw key so dev sees the typo immediately
      return key_path;
    }
    node = node[p];
  }
  // 終端值：string 直接返 / 非 string (object/number) 走 String() 強轉
  // Terminal value: string returned directly; non-string coerced via String()
  return typeof node === 'string' ? node : String(node);
};
