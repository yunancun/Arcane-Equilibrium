"""Aggregate acceptance for the persisted S2.4 UID wave chain."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
RECEIPT_ROOT = ROOT / "docs/execution_plan/ai_ml_landing/receipts"

EARLY_SEMANTIC_HEAD = "90713b5565fb49a4d36193b05a4ddff48cf32fbc"
LATE_SEMANTIC_HEAD = "6fd4ea739b736b6d00000f7e66913f7c8ee8a8e1"
EXPECTED_W2_ABI_DIGEST = (
    "sha256:9b2751b3659f4676459bc29d575255835ebdfba0e254af0eb030f92849bab89c"
)
SEMANTIC_HEAD_BY_GENERATION = {
    "S2.4-WP4-W0": EARLY_SEMANTIC_HEAD,
    "S2.4-WP4-W1": EARLY_SEMANTIC_HEAD,
    "S2.4-WP4-W2": LATE_SEMANTIC_HEAD,
    "S2.4-WP4-W3": LATE_SEMANTIC_HEAD,
    "S2.4-WP4-W4": LATE_SEMANTIC_HEAD,
    "S2.4-WP4-W5": LATE_SEMANTIC_HEAD,
}

PERSISTED_MANIFEST = {
    "S2.4-WP4-W0": {
        "S2.4-WP4-W0-derivation-record.json",
        "S2.4-WP4-W0-source-admission-receipt-v1.json",
        "S2.4-WP4-W0-wave-exit-receipt-v1.json",
    },
    "S2.4-WP4-W1": {
        "S2.4-WP4-W1-derivation-record.json",
        "S2.4-WP4-W1-regenerated-W0-source-admission-receipt-v1.json",
        "S2.4-WP4-W1-regenerated-W0-wave-exit-receipt-v1.json",
        "S2.4-WP4-W1-wave-exit-receipt-v1.json",
    },
    "S2.4-WP4-W2": {
        "S2.4-WP4-W2-derivation-record.json",
        "S2.4-WP4-W2-regenerated-W0-source-admission-receipt-v1.json",
        "S2.4-WP4-W2-regenerated-W0-wave-exit-receipt-v1.json",
        "S2.4-WP4-W2-regenerated-W1-wave-exit-receipt-v1.json",
        "S2.4-WP4-W2-wave-exit-receipt-v1.json",
    },
    "S2.4-WP4-W3": {
        "S2.4-WP4-W3-derivation-record.json",
        "S2.4-WP4-W3-regenerated-W0-source-admission-receipt-v1.json",
        "S2.4-WP4-W3-regenerated-W0-wave-exit-receipt-v1.json",
        "S2.4-WP4-W3-regenerated-W1-wave-exit-receipt-v1.json",
        "S2.4-WP4-W3-regenerated-W2-wave-exit-receipt-v1.json",
        "S2.4-WP4-W3-wave-exit-receipt-v1.json",
    },
    "S2.4-WP4-W4": {
        "S2.4-WP4-W4-derivation-record.json",
        "S2.4-WP4-W4-regenerated-W0-source-admission-receipt-v1.json",
        "S2.4-WP4-W4-regenerated-W0-wave-exit-receipt-v1.json",
        "S2.4-WP4-W4-regenerated-W1-wave-exit-receipt-v1.json",
        "S2.4-WP4-W4-regenerated-W2-wave-exit-receipt-v1.json",
        "S2.4-WP4-W4-regenerated-W3-wave-exit-receipt-v1.json",
        "S2.4-WP4-W4-wave-exit-receipt-v1.json",
    },
    "S2.4-WP4-W5": {
        "S2.4-WP4-W5-derivation-record.json",
        "S2.4-WP4-W5-regenerated-W0-source-admission-receipt-v1.json",
        "S2.4-WP4-W5-regenerated-W0-wave-exit-receipt-v1.json",
        "S2.4-WP4-W5-regenerated-W1-wave-exit-receipt-v1.json",
        "S2.4-WP4-W5-regenerated-W2-wave-exit-receipt-v1.json",
        "S2.4-WP4-W5-regenerated-W3-wave-exit-receipt-v1.json",
        "S2.4-WP4-W5-regenerated-W4-wave-exit-receipt-v1.json",
        "S2.4-WP4-W5-wave-exit-receipt-v1.json",
    },
}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _generation_records(directory: str) -> tuple[dict, dict, list[dict]]:
    records = [
        _read(RECEIPT_ROOT / directory / name)
        for name in sorted(PERSISTED_MANIFEST[directory])
    ]
    derivations = [
        record for record in records
        if str(record.get("schema_version", "")).endswith("_informal")
    ]
    admissions = [
        record for record in records
        if record.get("schema_version") == "s2_4_source_admission_receipt_v1"
    ]
    exits = sorted(
        (
            record for record in records
            if record.get("schema_version") == "s2_4_wave_exit_receipt_v1"
        ),
        key=lambda record: int(record["wave"][1:]),
    )
    assert len(derivations) == len(admissions) == 1
    return derivations[0], admissions[0], exits


@pytest.fixture(scope="module")
def semantic_views(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    views: dict[str, Path] = {}
    for head in (EARLY_SEMANTIC_HEAD, LATE_SEMANTIC_HEAD):
        view = tmp_path_factory.mktemp("uid-semantic-view") / head[:6]
        subprocess.run(
            [
                "git",
                "clone",
                "--quiet",
                "--local",
                "--no-checkout",
                str(ROOT),
                str(view),
            ],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-c",
                "advice.detachedHead=false",
                "-C",
                str(view),
                "checkout",
                "--quiet",
                "--detach",
                head,
            ],
            check=True,
        )
        observed_head = subprocess.run(
            ["git", "-C", str(view), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        observed_branch = subprocess.run(
            ["git", "-C", str(view), "branch", "--show-current"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        observed_status = subprocess.run(
            [
                "git",
                "-C",
                str(view),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert (observed_head, observed_branch, observed_status) == (head, "", "")
        views[head] = view
    return views


_SEMANTIC_VALIDATOR = r"""
import copy
import json
import sys
from pathlib import Path

root = Path.cwd()
for path in (
    root / "helper_scripts/maintenance_scripts",
    root / "program_code/ml_training",
    root / "program_code",
):
    sys.path.insert(0, str(path))

from aiml_gate_receipt_schema_core import canonical_digest
from aiml_gate_receipt_validator import derive_wave_exit_status, validate_aiml_artifact
from aiml_gate_receipt_wave_w2 import w2_exported_abi_projection

payload = json.load(sys.stdin)
derivation = payload["derivation"]
admission = payload["admission"]
exits = payload["exits"]
validations = [validate_aiml_artifact(admission)]
derivations = []
for index, receipt in enumerate(exits):
    validations.append(validate_aiml_artifact(receipt))
    derivations.append(derive_wave_exit_status(
        receipt,
        source_admission_receipt=admission,
        predecessor_wave_receipt=exits[index - 1] if index else None,
        predecessor_wave_chain=tuple(exits[:index - 1]) if index > 1 else (),
    ))

result = {
    "derivation_validation": validate_aiml_artifact(derivation),
    "validations": validations,
    "derivations": derivations,
    "self_links": [
        receipt["self_digest"] == canonical_digest({
            key: value for key, value in receipt.items() if key != "self_digest"
        })
        for receipt in (admission, *exits)
    ],
}
if payload["exercise_negatives"]:
    broken_terminal = copy.deepcopy(exits[-1])
    broken_terminal["predecessor_wave_receipt_digest"] = "sha256:" + "0" * 64
    broken_terminal["self_digest"] = canonical_digest({
        key: value for key, value in broken_terminal.items() if key != "self_digest"
    })
    result["predecessor_tamper"] = derive_wave_exit_status(
        broken_terminal,
        source_admission_receipt=admission,
        predecessor_wave_receipt=exits[-2],
        predecessor_wave_chain=tuple(exits[:-2]),
    )
    w2_index = next(
        index for index, receipt in enumerate(exits) if receipt["wave"] == "W2"
    )
    broken_w2 = copy.deepcopy(exits[w2_index])
    broken_w2["exported_abi_digest"] = "sha256:" + "0" * 64
    broken_w2["self_digest"] = canonical_digest({
        key: value for key, value in broken_w2.items() if key != "self_digest"
    })
    result["w2_abi_tamper_validation"] = validate_aiml_artifact(broken_w2)
    result["w2_abi_tamper"] = derive_wave_exit_status(
        broken_w2,
        source_admission_receipt=admission,
        predecessor_wave_receipt=exits[w2_index - 1],
        predecessor_wave_chain=tuple(exits[:w2_index - 1]),
    )
if payload["recompute_w2_abi"]:
    result["w2_abi_digest"] = canonical_digest(w2_exported_abi_projection(root))
json.dump(result, sys.stdout, sort_keys=True)
"""


def _validate_at_semantic_head(
    view: Path,
    derivation: dict,
    admission: dict,
    exits: list[dict],
    *,
    exercise_negatives: bool = False,
    recompute_w2_abi: bool = False,
) -> dict:
    completed = subprocess.run(
        [sys.executable, "-I", "-c", _SEMANTIC_VALIDATOR],
        cwd=view,
        input=json.dumps({
            "derivation": derivation,
            "admission": admission,
            "exits": exits,
            "exercise_negatives": exercise_negatives,
            "recompute_w2_abi": recompute_w2_abi,
        }),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_persisted_uid_inventory_is_the_literal_six_generation_manifest() -> None:
    assert set(PERSISTED_MANIFEST) == {
        "S2.4-WP4-W0",
        "S2.4-WP4-W1",
        "S2.4-WP4-W2",
        "S2.4-WP4-W3",
        "S2.4-WP4-W4",
        "S2.4-WP4-W5",
    }
    for directory, expected_names in PERSISTED_MANIFEST.items():
        actual_names = {
            path.name for path in (RECEIPT_ROOT / directory).glob("*.json")
        }
        assert actual_names == expected_names, directory

    records = [
        _read(RECEIPT_ROOT / directory / name)
        for directory, names in PERSISTED_MANIFEST.items()
        for name in names
    ]
    assert len(records) == 33
    assert sum(
        "derivation-record" in name
        for names in PERSISTED_MANIFEST.values()
        for name in names
    ) == 6
    assert sum(
        record.get("schema_version") == "s2_4_source_admission_receipt_v1"
        for record in records
    ) == 6
    assert sum(
        record.get("schema_version") == "s2_4_wave_exit_receipt_v1"
        for record in records
    ) == 21


def test_every_generation_rederives_at_its_semantic_source(
    semantic_views: dict[str, Path],
) -> None:
    for generation_index, directory in enumerate(PERSISTED_MANIFEST):
        derivation, admission, exits = _generation_records(directory)
        semantic_head = SEMANTIC_HEAD_BY_GENERATION[directory]
        assert len(exits) == generation_index + 1
        assert [receipt["wave"] for receipt in exits] == [
            f"W{index}" for index in range(generation_index + 1)
        ]
        assert {
            derivation["source_head"],
            admission["source_head"],
            *(receipt["source_head"] for receipt in exits),
        } == {semantic_head}
        assert derivation["schema_version"].endswith("_informal")
        assert not {"self_digest", "status", "pass", "done"}.intersection(derivation)
        assert "production_authority_flags" not in derivation

        for index, receipt in enumerate(exits):
            assert receipt["source_admission_receipt_digest"] == admission["self_digest"]
            assert receipt["predecessor_wave_receipt_digest"] == (
                None if index == 0 else exits[index - 1]["self_digest"]
            )

        result = _validate_at_semantic_head(
            semantic_views[semantic_head], derivation, admission, exits
        )
        assert result["derivation_validation"]
        assert result["validations"] == [[] for _ in range(len(exits) + 1)]
        assert result["self_links"] == [True for _ in range(len(exits) + 1)]
        assert result["derivations"] == [
            {"status": "PASS", "reasons": []} for _ in exits
        ]


def test_w2_abi_and_chain_tampering_fail_closed(
    semantic_views: dict[str, Path],
) -> None:
    w2_receipts = []
    for directory in PERSISTED_MANIFEST:
        _derivation, _admission, exits = _generation_records(directory)
        w2_receipts.extend(receipt for receipt in exits if receipt["wave"] == "W2")
    assert len(w2_receipts) == 4
    assert {receipt["exported_abi_digest"] for receipt in w2_receipts} == {
        EXPECTED_W2_ABI_DIGEST
    }

    derivation, admission, exits = _generation_records("S2.4-WP4-W5")
    result = _validate_at_semantic_head(
        semantic_views[LATE_SEMANTIC_HEAD],
        derivation,
        admission,
        exits,
        exercise_negatives=True,
        recompute_w2_abi=True,
    )
    assert result["w2_abi_digest"] == EXPECTED_W2_ABI_DIGEST
    assert result["predecessor_tamper"]["status"] == "NOT_PASS"
    assert any(
        "predecessor_wave_receipt_digest" in reason
        for reason in result["predecessor_tamper"]["reasons"]
    )
    assert result["w2_abi_tamper_validation"]
    assert result["w2_abi_tamper"]["status"] == "NOT_PASS"
    assert result["w2_abi_tamper"]["reasons"]
