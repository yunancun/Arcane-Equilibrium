from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PRODUCER = ROOT / "rust/openclaw_engine/src/ibkr_phase2_gate_producer.rs"
BIN = ROOT / "rust/openclaw_engine/src/bin/ibkr_phase2_seal.rs"
CARGO = ROOT / "rust/openclaw_engine/Cargo.toml"


def _production_source() -> str:
    return PRODUCER.read_text(encoding="utf-8").split("#[cfg(all(test, unix))]", 1)[0]


def test_controlled_seal_has_dual_apply_gate_and_no_dead_code_blanket() -> None:
    source = _production_source()

    assert "pub fn phase2_apply_seal_if_explicitly_requested(" in source
    assert "if !cli_apply_requested" in source
    assert 'OPENCLAW_IBKR_PHASE2_SEAL_APPLY' in source
    assert 'Some("1")' in source
    assert "pub fn phase2_seal_dry_run()" in source
    assert "#![allow(dead_code)]" not in source


def test_production_control_inputs_never_promote_fixture_or_template() -> None:
    source = _production_source()

    assert "Phase2SealProductionInputsV1" in source
    assert "external_verification_pending:controlled_inputs_missing" in source
    assert "NonBybitApiAllowlistV1::accepted_fixture()" not in source
    assert "IbkrApiSessionTopologyV1::source_template()" not in source
    assert "IbkrSecretSlotContractV1::source_template()" not in source
    assert "IbkrPhase2PolicyBundleV1::source_template()" not in source


def test_only_standalone_bin_calls_apply_and_it_stays_no_contact() -> None:
    all_rust = list((ROOT / "rust/openclaw_engine/src").rglob("*.rs"))
    callers = []
    for path in all_rust:
        text = _production_source() if path == PRODUCER else path.read_text(encoding="utf-8")
        if path == PRODUCER:
            text = text.replace("pub fn phase2_apply_seal_if_explicitly_requested(", "")
        if "phase2_apply_seal_if_explicitly_requested(" in text:
            callers.append(path.relative_to(ROOT).as_posix())
    assert callers == ["rust/openclaw_engine/src/bin/ibkr_phase2_seal.rs"]

    bin_source = BIN.read_text(encoding="utf-8")
    assert "--apply" in bin_source
    assert "phase2_seal_dry_run" in bin_source
    for forbidden in (
        "TcpStream",
        "tokio::net",
        "reqwest",
        "ibapi",
        "ib_insync",
        "place_order",
        "cancel_order",
        "replace_order",
        "sqlx",
        "DATABASE_URL",
    ):
        assert forbidden not in bin_source


def test_immutable_generation_and_control_ledger_is_explicitly_fail_closed() -> None:
    source = _production_source()

    for required in (
        "Phase2SealedGenerationV1",
        "Phase2SealControlRecordV1",
        "Phase2SealControlAction",
        "GENE RATIONS_DIRNAME".replace(" ", ""),
        "CONTROLS_DIRNAME",
        "previous_control_hash",
        "controlled phase2 approval replay rejected",
        "already_applied_no_contact",
        "ambiguous immutable control chain",
        "supersession predecessor mismatch",
        "revoke predecessor mismatch",
        "Phase2ApplyLock",
        "libc::flock",
        "O_NOFOLLOW",
        "owner-only regular 0600",
        "post-write immutable lineage validation failed",
        "O_NONBLOCK",
    ):
        assert required in source
    assert "CURRENT_FILENAME" not in source
    assert "phase2_immutable_pass_artifact_present" in source
    assert "load_current_build_lineage" in source
    assert 'sha.len() == 40' in source


def test_cargo_registers_the_isolated_rust_only_control_bin() -> None:
    cargo = CARGO.read_text(encoding="utf-8")
    assert 'name = "ibkr_phase2_seal"' in cargo
    assert 'path = "src/bin/ibkr_phase2_seal.rs"' in cargo


def test_cli_rejects_dry_run_and_apply_together() -> None:
    source = BIN.read_text(encoding="utf-8")

    assert "--dry-run and --apply are mutually exclusive" in source
    assert "if apply && dry_run" in source
