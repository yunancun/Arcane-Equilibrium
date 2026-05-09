//! Replay runner manifest schema and fail-closed signature verification.

use std::path::Path;

use openclaw_engine::replay::manifest_signer::{
    canonical_body_for_signing, compute_body_hash, compute_key_fingerprint, InMemoryKeyArchive,
    KeyStatus, ManifestSigner,
};

#[derive(serde::Deserialize, Debug)]
pub(crate) struct ReplayManifest {
    pub(crate) experiment_id: String,
    pub(crate) data_tier: String,
    pub(crate) fixture_uri: String,
    /// Hex-encoded HMAC-SHA256 signature over the canonical manifest body
    /// (the body with envelope fields `signature`, `manifest_hash`,
    /// `signature_key_ref` stripped, then re-serialized via
    /// `serde_json::to_vec` — same canonicalisation as the Python sibling
    /// signer's `json.dumps(sort_keys=True, separators=(',', ':'),
    /// ensure_ascii=False)`).
    ///
    /// 對 canonical manifest body 的 hex HMAC-SHA256 簽名（body = 整個
    /// manifest 剝除 envelope 欄位 `signature` / `manifest_hash` /
    /// `signature_key_ref` 後，以 `serde_json::to_vec` 重序列化 — 與 Python
    /// sibling signer 的 `json.dumps(sort_keys=True, separators=(',', ':'),
    /// ensure_ascii=False)` 同 canonicalisation）。
    ///
    /// REF-20 Sprint 1 Track B：本欄位從 `#[allow(dead_code)]` placeholder
    /// 升級為 verify path 的 expected signature — 不再對 disk content 重簽
    /// 然後 verify（那是 tautology）。攻擊面：拿到 signing key 即可造任意
    /// manifest；唯一防線是 fail-closed verify。
    pub(crate) signature: String,
    /// Hex-encoded SHA-256 of the canonical body (declared by the signer).
    /// Verified by computing `compute_body_hash(canonical_body_for_signing(
    /// disk_bytes))` and byte-comparing against this declared value.
    ///
    /// canonical body 的 hex SHA-256（由 signer 宣告）。
    /// 驗證方式：對磁碟 bytes 跑 `canonical_body_for_signing` → `compute_body_hash`，
    /// 重算結果與此宣告值 byte 比對。
    ///
    /// REF-20 Sprint 1 Track B：本欄位從 `#[allow(dead_code)]` 升級為 verify
    /// path 的 expected hash — 確保 disk content 與簽名時的 body 一致（防
    /// post-sign tampering of body fields outside `signature`/`manifest_hash`）。
    pub(crate) manifest_hash: String,
    /// Optional signature key fingerprint (must match the disk key's
    /// fingerprint for the verify path to find a key in the in-memory
    /// archive). When absent the verify path falls back to the disk-key's
    /// own fingerprint (V042 SQL archive landing in Wave 6 will tighten this).
    ///
    /// 選用 signature key fingerprint（必與磁碟 key 的 fingerprint 相符，
    /// verify 路徑才能在 archive 找到 key）。缺時 fallback 到磁碟 key 自算
    /// fingerprint（V042 SQL archive 於 Wave 6 land 後會收緊此路徑）。
    #[serde(default)]
    pub(crate) signature_key_ref: Option<String>,
    /// Optional run id (Track A `_write_manifest_fixture` writes this from
    /// the V045 PK so the Rust binary can self-verify
    /// `manifest.run_id == output_dir.basename()` per PA Push Back #2).
    ///
    /// `#[serde(default)]` for backward-compatibility with existing fixtures
    /// that pre-date Track A (e.g. `tests/fixtures/replay_manifest_signer/`
    /// stripped-body fixtures).
    ///
    /// 選用 run id（Track A `_write_manifest_fixture` 從 V045 PK 寫入，使
    /// Rust binary 可自驗 `manifest.run_id == output_dir.basename()`，依
    /// PA Push Back #2）。
    ///
    /// `#[serde(default)]` 為向後相容既有 fixture（如
    /// `tests/fixtures/replay_manifest_signer/` stripped-body fixture）。
    #[serde(default)]
    pub(crate) run_id: Option<String>,
    /// REF-20 Sprint B2 R5-T4: optional strategy name (matches V049
    /// `manifest_jsonb.strategy`; e.g. "grid_trading" / "ma_crossover").
    /// When `None` the replay runner falls back to the synthetic walker
    /// path (R5-T3 e2e proof_1/4/5 baseline). When `Some(name)` R5-T4 wires
    /// a real `StrategyFactory::create_with_params(default)` instance plus
    /// `ReplayRiskAdapter` (6-Gate path) under the existing
    /// `IsolatedPipeline::with_adapter_pipeline()` setter.
    ///
    /// REF-20 Sprint B2 R5-T4：選用策略名（對齊 V049 `manifest_jsonb.strategy`；
    /// 例 "grid_trading" / "ma_crossover"）。`None` 時 runner fallback 至
    /// synthetic walker（R5-T3 e2e proof_1/4/5 baseline）。`Some(name)` 時
    /// R5-T4 透過既有 `IsolatedPipeline::with_adapter_pipeline()` setter
    /// 接入真實 `StrategyFactory::create_with_params(default)` instance + 6-Gate
    /// `ReplayRiskAdapter`。
    ///
    /// `#[serde(default)]` 為向後相容 R5-T3 前的 manifest fixture（無 strategy
    /// 欄位即視為 synthetic walker 路徑，proof_1/4/5 不退）。
    #[serde(default)]
    pub(crate) strategy: Option<String>,
    /// REF-20 Sprint B2 R5-T4: optional starting balance (defaults to
    /// `runner::DEFAULT_STARTING_BALANCE = 10_000.0`). Sourced from
    /// `manifest_jsonb.starting_balance` if present. Sprint A baseline picks
    /// 10_000 USDT for non-actionable replay; manifest may override only when
    /// `evidence_source_tier='calibrated_replay'` requires non-default anchor.
    ///
    /// REF-20 Sprint B2 R5-T4：選用起始餘額（預設
    /// `runner::DEFAULT_STARTING_BALANCE = 10_000.0`）。來自
    /// `manifest_jsonb.starting_balance`（若存在）。Sprint A baseline 取
    /// 10_000 USDT for non-actionable replay；僅當
    /// `evidence_source_tier='calibrated_replay'` 需非預設錨時 manifest 覆寫。
    #[serde(default)]
    pub(crate) starting_balance: Option<f64>,
    /// REF-20 Sprint B2 R5-T4 round 2: optional strategy-parameter blob
    /// matching V049 register handler's `_replay_strategy_params` injection.
    /// When present, the runner deserialises this `serde_json::Value` into
    /// a `StrategyParamsConfig` (sub-key for the manifest's `strategy` field
    /// e.g. `grid_trading`) and threads the customised params through
    /// `StrategyFactory::create_with_params(...)`. When absent, falls back
    /// to `StrategyParamsConfig::default()` (R5-T4 round 1 behaviour, A4
    /// parameter delta cannot be observed). When deserialisation fails
    /// (shape mismatch), runner exits non-zero with typed `Box<dyn Error>`
    /// so CI parses fail-mode (CLAUDE.md §四 fail-closed).
    ///
    /// REF-20 Sprint B2 R5-T4 round 2：選用策略參數 blob，對齊 V049 register
    /// handler 的 `_replay_strategy_params` 注入。存在時 runner 把此
    /// `serde_json::Value` 反序列化為 `StrategyParamsConfig`（包含 manifest
    /// `strategy` 對應子段，例如 `grid_trading`）並透過
    /// `StrategyFactory::create_with_params(...)` 接入；不存在時退回
    /// `StrategyParamsConfig::default()`（R5-T4 round 1 行為，無法觀察 A4
    /// 參數 delta）。Shape 不符 → 非 0 結束帶 typed `Box<dyn Error>`，CI
    /// 解析 fail-mode（CLAUDE.md §四 fail-closed）。
    ///
    /// `#[serde(default)]` 為向後相容 R5-T4 round 1 前的 manifest fixture
    /// （無此欄位即視為 default config，xlang 13/13 不退）。
    #[serde(default)]
    pub(crate) strategy_params: Option<serde_json::Value>,
    /// REF-20 Sprint B2 R5-T4 round 2: optional risk-override blob matching
    /// V049 register handler's `_replay_risk_overrides` injection. When
    /// present, runner deserialises this `serde_json::Value` into a
    /// `RiskConfig` (full schema; downstream gates read e.g.
    /// `limits.position_size_max_pct`). When absent, falls back to
    /// `RiskConfig::default()` (R5-T4 round 1 behaviour, A5 risk-delta
    /// cannot be observed). Fail-loud on shape mismatch / NaN /
    /// out-of-bounds via the same `Box<dyn Error>` non-zero-exit path.
    ///
    /// REF-20 Sprint B2 R5-T4 round 2：選用風險覆寫 blob，對齊 V049 register
    /// handler 的 `_replay_risk_overrides` 注入。存在時反序列化為完整
    /// `RiskConfig` schema（下游 gate 例如讀 `limits.position_size_max_pct`）；
    /// 不存在退回 `RiskConfig::default()`（R5-T4 round 1，無法觀察 A5）。
    /// Shape 不符 / NaN / 越界 → 同 `Box<dyn Error>` 非 0 結束。
    ///
    /// `#[serde(default)]` 同 `strategy_params`：向後相容、xlang 13/13 不退。
    #[serde(default)]
    pub(crate) risk_overrides: Option<serde_json::Value>,
    /// REF-21 full-chain replay mode marker. When `mode == "full_chain"`,
    /// the dedicated subprocess reconstructs a scanner timeline from the
    /// fixture before running the strategy/risk adapter path.
    #[serde(default)]
    pub(crate) mode: Option<String>,
    /// Optional scanner config snapshot captured by the control plane. Absent
    /// manifests use replay defaults (60-second scan interval, zero warmup).
    #[serde(default)]
    pub(crate) scanner_config: Option<serde_json::Value>,
    /// Optional historical edge estimate snapshot. Shape matches
    /// `EdgeEstimates::load_from_str`; absent manifests use an empty snapshot
    /// rather than reading current mutable settings.
    #[serde(default)]
    pub(crate) edge_estimates: Option<serde_json::Value>,
    /// REF-21 execution calibration overlay written by the control plane.
    /// The isolated runner currently consumes only
    /// `recommended_maker_fill_probability_cap`; slippage calibration flows
    /// through `risk_overrides.slippage`.
    #[serde(default)]
    pub(crate) execution_calibration: Option<serde_json::Value>,
}

/// Load the manifest JSON and run the manifest_signer verify path.
///
/// 載入 manifest JSON 並跑 manifest_signer 驗證路徑。
///
/// Semantics (EN, REF-20 Sprint 1 Track B FAIL-CLOSED rewrite):
///   1. Read `manifest_path` as UTF-8 JSON.
///   2. Parse into `ReplayManifest` (rejects on schema mismatch; rejects when
///      `signature` / `manifest_hash` envelope fields are absent — Wave 4 T1
///      placeholder behaviour was to skip verify here, which is the E3-P0-1
///      fail-open vulnerability this rewrite closes).
///   3. Locate sibling `key.hex` next to the manifest. If ABSENT → return
///      `Err("manifest_signer_key_missing: ...")`. Sprint 1 closes the
///      previous fail-open path that returned `Ok(manifest)` with a stderr
///      warning. V042 SQL-backed archive (Wave 6) will replace this sibling-
///      key fallback; until V042 lands, dev fixture + production deploy
///      operator MUST place a `key.hex` next to every signed manifest.
///   4. Verify via `ManifestSigner::verify`:
///      - Use `canonical_body_for_signing(disk_bytes)` to reproduce the
///        canonical signing payload (envelope fields stripped + sorted keys).
///      - Pass `manifest.signature` (from disk) as the `signature_hex`
///        argument — NOT a freshly-computed signature (the previous tautology
///        was: `let sig = signer.sign(body); signer.verify(body, hash, sig)`
///        which can never fail).
///      - Pass `manifest.manifest_hash` (from disk) as the
///        `manifest_declared_hash` argument.
///      - Resolve fingerprint: prefer `manifest.signature_key_ref` if present
///        (audit chain marker); else use disk-key's own fingerprint.
///   5. Verify path emits a typed `SignatureFailMode` on mismatch — convert
///      to a `Box<dyn Error>` with the fail-mode label so the binary exits
///      non-zero with audit-distinguishable stderr.
///
/// 語意（中，REF-20 Sprint 1 Track B FAIL-CLOSED 重寫）：
///   1. 以 UTF-8 JSON 讀 `manifest_path`。
///   2. parse 為 `ReplayManifest`（schema 不符即拒；缺 `signature` /
///      `manifest_hash` envelope 欄位即拒 — Wave 4 T1 placeholder 行為是
///      skip verify，這是本 rewrite 修的 E3-P0-1 fail-open）。
///   3. 找 sibling `key.hex`。缺即 `Err("manifest_signer_key_missing: ...")`。
///      Sprint 1 修掉舊有的「印 warning + return Ok」fail-open 路徑。V042
///      SQL-backed archive（Wave 6）將替代 sibling-key fallback；V042 land 前
///      dev fixture 與 production deploy operator 必須在每個 signed manifest
///      旁放一個 `key.hex`。
///   4. 透過 `ManifestSigner::verify` 驗證：
///      - 用 `canonical_body_for_signing(disk_bytes)` 重 canonicalize 出
///        簽名 payload（envelope 剝除 + sorted keys）。
///      - `manifest.signature`（from disk）為 `signature_hex` 參數 — 非新
///        重簽（舊 tautology：`let sig = signer.sign(body); signer.verify(
///        body, hash, sig)` 永不會 fail）。
///      - `manifest.manifest_hash`（from disk）為 `manifest_declared_hash`
///        參數。
///      - fingerprint 解析：若 `manifest.signature_key_ref` 存在優先（audit
///        chain marker）；否則用磁碟 key 自算 fingerprint。
///   5. verify 失敗回 typed `SignatureFailMode` → 轉成 `Box<dyn Error>` 帶
///      fail-mode label，使 binary 非 0 結束並印 audit-distinguishable stderr。
///
/// # E3-P0-1 root-cause closed by Sprint 1 Track B
/// E3-P0-1 by Sprint 1 Track B 修補的根因
///
/// Pre-Sprint-1 path (DELETED):
///   ```text
///   let signature_hex = signer.sign(canonical_body);  // self-sign
///   signer.verify(canonical_body, &body_hash, &signature_hex, ...) // verify-self
///   ```
/// → recomputed sig with same key + same canonical body == declared sig
///   trivially. Verify always Ok. Attacker with the signing key (or in any
///   directory without a sibling key.hex) could mint manifests that pass.
///
/// Sprint 1 Track B path:
///   - canonical body = strip envelope fields + sorted-keys serde_json.
///   - signer.verify(canon_body, manifest.manifest_hash, manifest.signature,
///                   fingerprint, archive)
///   - sig comes from disk file (was put there by Python sibling signer);
///     hash comes from disk file; canonical body comes from disk file;
///     verify recomputes HMAC over canonical body and compares to disk sig.
///   - Tautology closed.
pub(crate) fn load_and_verify_manifest(
    manifest_path: &Path,
) -> Result<ReplayManifest, Box<dyn std::error::Error>> {
    // Read + parse / 讀 + 解析。
    let raw = std::fs::read_to_string(manifest_path)?;
    let manifest: ReplayManifest = serde_json::from_str(&raw)?;

    // Look for sibling `key.hex` (matches the fixture layout used by
    // `tests/fixtures/replay_manifest_signer/`). REF-20 Sprint 1 Track B:
    // ABSENT → hard error (was: stderr warning + Ok fall-through, which is
    // the E3-P0-1 fail-open vulnerability).
    //
    // 尋找 sibling `key.hex`（對齊 `tests/fixtures/replay_manifest_signer/`
    // 的 fixture layout）。REF-20 Sprint 1 Track B：缺即 hard error
    // （舊路徑：印 stderr warning + Ok fall-through，是 E3-P0-1 fail-open）。
    //
    // V042 SQL-backed archive notes:
    // - V042 reserved at workplan level but unscheduled until Wave 6+.
    // - Until V042 lands, sibling key.hex fallback is the ONLY production
    //   key source; operator MUST place a key.hex next to every manifest
    //   (PA Push Back #3 surfaces this as an operator runbook contract +
    //   adds the `check_replay_manifest_key_presence()` healthcheck).
    let key_hex_path = manifest_path
        .parent()
        .map(|p| p.join("key.hex"))
        .unwrap_or_else(|| std::path::PathBuf::from("key.hex"));
    if !key_hex_path.exists() {
        return Err(format!(
            "manifest_signer_key_missing: sibling key.hex absent at {}; \
             production path requires either (a) operator-deployed sibling \
             key.hex per V042 archive deploy runbook (Wave 6+) or (b) V042 \
             SQL-backed KeyArchive (not yet landed) — fail-closed",
            key_hex_path.display()
        )
        .into());
    }

    // Read key file / 讀 key 檔案。
    let key_file_content = std::fs::read(&key_hex_path)?;
    let key_hex_str = std::str::from_utf8(&key_file_content)?.trim().to_string();
    let key_bytes = hex::decode(&key_hex_str).map_err(|e| {
        format!(
            "manifest_signer_key_invalid_hex: key.hex at {} not valid hex: {}",
            key_hex_path.display(),
            e
        )
    })?;
    if key_bytes.len() != 32 {
        return Err(format!(
            "manifest_signer_key_invalid_length: key.hex must decode to \
             32 bytes (got {} bytes at {})",
            key_bytes.len(),
            key_hex_path.display()
        )
        .into());
    }
    let disk_fingerprint = compute_key_fingerprint(&key_file_content);
    let signer = ManifestSigner::new_from_bytes_for_test(key_bytes, disk_fingerprint.clone());

    // Resolve verify fingerprint:
    //   - If manifest declares `signature_key_ref` → use that (audit chain
    //     marker; production V042 archive lookup keys on this).
    //   - Else fall back to disk-key's own fingerprint (Track A
    //     `_write_manifest_fixture` may omit `signature_key_ref` in dev mode).
    //
    // 解析 verify fingerprint：
    //   - manifest 宣告 `signature_key_ref` → 用宣告值（audit chain；prod V042
    //     archive 以此 key 查 status）。
    //   - 否則 fallback 為磁碟 key 自算 fingerprint（Track A
    //     `_write_manifest_fixture` 在 dev 模式可省 `signature_key_ref`）。
    let verify_fingerprint = manifest
        .signature_key_ref
        .clone()
        .unwrap_or_else(|| disk_fingerprint.clone());

    // 不變量 / Invariant: archive 必含 verify_fingerprint with status=Active —
    //   Wave 4 T1 用 in-memory archive 自填當前 disk-key fingerprint 即可
    //   （Wave 6 V042 SQL archive 落地後改用真實 status）。
    //   若 manifest.signature_key_ref 與磁碟 fingerprint 不一致 → archive
    //   lookup miss → KeyMissing fail-mode（保留 audit-distinguish）。
    let archive = {
        let mut a = InMemoryKeyArchive::new();
        a.insert(disk_fingerprint.clone(), KeyStatus::Active);
        a
    };

    // REF-20 Sprint 1 Track B canonical body path:
    //   strip envelope fields (signature / manifest_hash / signature_key_ref)
    //   + sorted-keys serde_json::to_vec → byte-equal Python sibling signer.
    //
    // canonicalize 路徑（REF-20 Sprint 1 Track B）：
    //   strip envelope 欄位 + sorted-keys serde_json::to_vec → 與 Python
    //   sibling signer byte-equal。
    let canonical_body = canonical_body_for_signing(raw.as_bytes()).map_err(|e| {
        format!(
            "manifest_signer_canonicalize_failed: {} (manifest body must \
                 be top-level JSON object per V3 §5)",
            e
        )
    })?;

    // Sanity gate / 完整性 gate: declared manifest_hash must match the
    // actual hash of the canonical body. This catches body-tampering after
    // sign even when the (still-correct) signature happens to verify against
    // a partially-tampered body — `manifest_hash` is the redundant integrity
    // anchor V3 §5 requires (mode 2/4 = `manifest_hash_mismatch`).
    //
    // Note: this gate fires BEFORE `signer.verify(...)` so the error label
    // reflects the actual semantic failure (declared hash drift) rather than
    // SignatureMismatch (which would surface only because the recomputed
    // sig over the tampered body differs from the disk-stored sig).
    let actual_body_hash = compute_body_hash(&canonical_body);
    if actual_body_hash != manifest.manifest_hash {
        return Err(format!(
            "manifest_signer_verify_failed: mode={} declared={} actual={}",
            "manifest_hash_mismatch", manifest.manifest_hash, actual_body_hash
        )
        .into());
    }

    // Final verify: HMAC sig + body hash + archive gates (per V3 §5 verify
    // order). Caller-supplied disk values are the expected inputs; this is
    // the key inversion vs the pre-Sprint-1 self-sign tautology.
    //
    // 最終 verify：HMAC sig + body hash + archive gate（V3 §5 順序）。
    // caller 提供的磁碟值為 expected 輸入；這是相對 Sprint 1 前 self-sign
    // tautology 的關鍵反轉。
    if let Err(fail) = signer.verify(
        &canonical_body,
        &manifest.manifest_hash,
        &manifest.signature,
        &verify_fingerprint,
        &archive,
    ) {
        return Err(format!(
            "manifest_signer_verify_failed: mode={} fingerprint={} \
             manifest={}",
            fail.audit_label(),
            verify_fingerprint,
            manifest_path.display()
        )
        .into());
    }
    Ok(manifest)
}

// ---------------------------------------------------------------------------
// REF-20 Sprint 1 Track B — fail-closed manifest verify tests
// REF-20 Sprint 1 Track B — fail-closed manifest 驗證測試
//
// Five mandatory tests bind to PA Sprint 1 dispatch §4 (改點 #4):
//   (a) tautology defense: post-sign body tampering surfaces (was: silently
//       passed pre-Sprint-1).
//   (b) key.hex absent → hard error (was: stderr warning + Ok fall-through).
//   (c) signature tampered (1 byte) → SignatureMismatch surfaced.
//   (d) declared manifest_hash drifted (1 byte) → manifest_hash_mismatch.
//   (happy) full single-file manifest with correct sig + hash → Ok.
//   (xlang) canonical_body_for_signing byte-equal to Python sibling.
//
// PA dispatch §4 改點 #4 4 fail-mode + 1 happy + 1 xlang sanity 共 6 test。
// ---------------------------------------------------------------------------
