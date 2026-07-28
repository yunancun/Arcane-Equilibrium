"""S2.2B(WP5 tranche 2)ingestion-compatibility seam 的中央委派葉。

facade(``aiml_gate_receipt_validator``)超過 2000 行治理門檻,故 S2.2B 的中央閘分支
下沉到本葉(facade 只保留 ≤6 行的委派分支;鏡 ``aiml_gate_receipt_s2_5`` 形制)。

本葉承載三塊(S2.5 design §10 的最小接口承諾 + S2.2A compatibility identity +
PROGRESS S2.2B row):

1. **`ingestion_compatibility_receipt_v1` 的整合驗** —— closed schema 之上補 schema
   表達不了的比較:
   * 內嵌 S2.2A source receipt 的三值鏈重算(``recompute(receipt) == 內嵌 self_digest
     == 外層綁定 digest``)+ 遞迴全套中央閘驗(內層 capture/training digest 反偽造
     重算屬 `_source_compatibility_receipt_errors`);
   * 內嵌 ``s2_5_final_attestation_v1`` 的三值鏈重算 + 遞迴**全套**中央閘驗
     (tranche 1b P1-2 紀律:digest 綁定只證 bytes;FINAL_ATTESTED 的 attestor SSHSIG
     驗簽、五維 verdicts、新鮮窗全在遞迴驗裡);
   * V151-V160 manifest 逐項 revalidation 的 typed 結果欄:expected 必等於 S2.2A
     fingerprints、result 由 observed↔expected 導出(caller 不可自證 MATCH)、任一
     非 MATCH ⇒ 成功 status 整份拒;
   * lane 錨定:source lane 錨 simulated ``SOURCE_SIMULATION_PASS``;runtime-DONE
     lane 必錨 production ``FINAL_ATTESTED``(simulated 錨 production 一律拒)。
2. **§9.2 never-refreshable 歸類** —— S2.2B receipt 屬 runtime 觀測類:證據只可重新
   觀測,永不可 refresh-by-reference(typed status 常量直接複用 contracts 葉)。
3. **evidence-class 紀律** —— source lane 恆 ``LOCAL_REPRODUCIBLE``;fixtures 不得假冒
   platform-attested;runtime DONE 需 ``PLATFORM_OR_EXTERNAL_ATTESTED`` + forward-
   compatible 的 ``runtime_attestor`` 簽章欄(其簽章驗證屬 S2.2B EFFECT session,
   本 source seam 在該 lane 由「production FINAL_ATTESTED 錨自身的 attestor 驗簽」
   鎖住——真 production final 在 key custody 下不可構造)。

⚠ SOURCE-TRUTH 邊界:乾淨 ``[]`` 只證 receipt 的內部自洽 + 上游綁定 + 離線結構;
「不」證任何 runtime 上的 manifest 真的被重驗。runtime-`DONE` 消費 `S2.5B@EFFECT_DONE`
(尚不存在),effect class 恆 `REMOTE_READONLY`,九項 authority 恆 false。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aiml_gate_receipt_schema_core import (
    _now_text,
    _parse_timestamp,
    artifact_self_digest,
    canonical_digest,
    resolve_facade,
)
from aiml_gate_receipt_s2_4_contracts import (
    DEPENDENCY_EVIDENCE_REOBSERVATION_REQUIRED,
    DEPENDENCY_REFRESH_BY_REFERENCE_FORBIDDEN,
    SOURCE_DEPENDENCY_STATUS_FRESH,
    SOURCE_DEPENDENCY_STATUS_REJECTED,
)

S2_2B_SCHEMA_VERSION = "ingestion_compatibility_receipt_v1"
S2_2B_EFFECT_CLASS = "REMOTE_READONLY"
# forward-compatible attestor profile(簽章驗證屬 S2.2B EFFECT session;常量先釘死,
# 使欄位形狀與 namespace 域分離自今日起就是封閉契約)。
S2_2B_ATTESTOR_IDENTITY = "aiml-s2-2b-ingestion-attestor-v1"
S2_2B_ATTESTOR_NAMESPACE = "arcane-equilibrium-aiml-s2-2b-ingestion-compatibility"
# typed statuses(成功語義分 lane 命名:simulation/source 永不是 attested success)。
S2_2B_STATUS_SOURCE_PASS = "SOURCE_REVALIDATION_PASS"
S2_2B_STATUS_RUNTIME_ATTESTED = "RUNTIME_COMPATIBILITY_ATTESTED"
S2_2B_STATUS_PENDING = "EXTERNAL_VERIFICATION_PENDING"
S2_2B_STATUS_REJECTED = "COMPATIBILITY_REJECTED"
_S2_2B_SUCCESS_STATUSES = frozenset({
    S2_2B_STATUS_SOURCE_PASS, S2_2B_STATUS_RUNTIME_ATTESTED,
})

# ── §9.2 never-refreshable 歸類(封閉表;additive,不動 S2.4/S2.5 owned 表 bytes)────
S2_2B_NEVER_REFRESHABLE_SCHEMAS: dict[str, tuple[str, ...]] = {
    "S2_2B_INGESTION_COMPATIBILITY": (S2_2B_SCHEMA_VERSION,),
}
S2_2B_NEVER_REFRESHABLE_EVIDENCE: dict[str, str] = {
    "S2_2B_INGESTION_COMPATIBILITY": (
        "an ingestion-compatibility receipt describes one live runtime revalidation "
        "moment and is always freshly re-observed; no refresh-by-reference"
    ),
}


def derive_s2_2b_source_dependency_admission_status(
    *,
    evidence_class: Any,
    receipt: Any,
    refresh: Any = None,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    """§9.2 的 S2.2B 臂(鏡 S2.5 執法形制):任何 refresh 一律 typed 禁;過期只可重觀測。"""

    if now is None:
        now = datetime.now(timezone.utc)
    verdict: dict[str, Any] = {
        "status": SOURCE_DEPENDENCY_STATUS_REJECTED,
        "reasons": [],
        "evidence_class": evidence_class,
        "refresh_admitted": False,
    }
    refreshes = (
        list(refresh) if isinstance(refresh, (list, tuple))
        else [] if refresh is None else [refresh]
    )
    expected_schemas = S2_2B_NEVER_REFRESHABLE_SCHEMAS.get(str(evidence_class))
    if expected_schemas is None:
        verdict["reasons"] = [
            f"{evidence_class!r} is not an S2.2B dependency-freshness class; the table "
            "is closed and an unknown class is never admitted"
        ]
        return verdict
    if refreshes:
        verdict["status"] = DEPENDENCY_REFRESH_BY_REFERENCE_FORBIDDEN
        verdict["reasons"] = [
            f"{evidence_class} can never be refreshed by reference: "
            f"{S2_2B_NEVER_REFRESHABLE_EVIDENCE[str(evidence_class)]} (§9.2)"
        ]
        return verdict
    if not isinstance(receipt, dict) or receipt.get("schema_version") not in expected_schemas:
        verdict["reasons"] = [
            f"{evidence_class} evidence is not the artifact this class names "
            f"(expected schema {expected_schemas})"
        ]
        return verdict
    expires = (receipt.get("manifest_revalidation") or {}).get("evidence_expires_at")
    try:
        if expires is None:
            raise ValueError("evidence carries no expiry")
        fresh = _parse_timestamp(str(expires)) > _parse_timestamp(
            _now_text(now) or str(now)
        )
    except (TypeError, ValueError) as error:
        verdict["reasons"] = [
            f"{evidence_class} freshness cannot be derived: {error} (fail-closed)"
        ]
        return verdict
    if fresh:
        verdict["status"] = SOURCE_DEPENDENCY_STATUS_FRESH
        return verdict
    verdict["status"] = DEPENDENCY_EVIDENCE_REOBSERVATION_REQUIRED
    verdict["reasons"] = [
        f"{evidence_class} is expired and cannot be refreshed by reference: "
        f"{S2_2B_NEVER_REFRESHABLE_EVIDENCE[str(evidence_class)]}"
    ]
    return verdict


# ── 內部小工具 ───────────────────────────────────────────────────────────────
def _bound_artifact_digest_ok(artifact: Any, bound_digest: Any) -> bool:
    """三值鏈(tranche 1b P1-2 紀律):``recompute(artifact) == artifact["self_digest"]
    == 外層綁定 digest``——自報 digest 的替身 stub 一律不採信。"""

    return (
        isinstance(artifact, dict)
        and bool(artifact.get("self_digest"))
        and artifact_self_digest(artifact) == artifact["self_digest"]
        and artifact["self_digest"] == bound_digest
    )


def _derived_item_result(expected: Any, observed: Any) -> str:
    """result 由 observed↔expected 導出(caller 不可自證 MATCH)。"""

    if observed is None:
        return "ABSENT"
    return "MATCH" if observed == expected else "MISMATCH"


def _manifest_revalidation_errors(
    revalidation: dict[str, Any], source_receipt: dict[str, Any], *, success: bool
) -> list[str]:
    """V151-V160 逐項 revalidation 的整合驗(expected 錨 S2.2A;result 導出式)。"""

    errors: list[str] = []
    expected_fingerprints = source_receipt.get("migration_fingerprints")
    if not isinstance(expected_fingerprints, dict) or not expected_fingerprints:
        return [
            "s2_2b manifest revalidation cannot anchor: the embedded S2.2A receipt "
            "carries no migration_fingerprints (fail-closed)"
        ]
    items = revalidation.get("items") or []
    files = [item.get("file") for item in items]
    if files != sorted(expected_fingerprints) or len(files) != len(set(files)):
        errors.append(
            "s2_2b manifest revalidation items must cover exactly the S2.2A "
            "migration-fingerprint set, sorted by file and unique (a dropped or "
            "smuggled row fails closed)"
        )
        return errors
    failing: list[str] = []
    for item in items:
        file_name = item["file"]
        if item.get("expected_fingerprint") != expected_fingerprints[file_name]:
            errors.append(
                f"s2_2b manifest revalidation expected_fingerprint for {file_name} "
                "does not equal the S2.2A-bound fingerprint (the expectation is "
                "anchored, never caller-supplied)"
            )
        derived = _derived_item_result(
            item.get("expected_fingerprint"), item.get("observed_fingerprint")
        )
        if item.get("result") != derived:
            errors.append(
                f"s2_2b manifest revalidation result for {file_name} does not derive "
                f"from observed↔expected (claimed {item.get('result')!r}, derived "
                f"{derived!r}); a claimed MATCH is never trusted"
            )
        if derived != "MATCH":
            failing.append(file_name)
    # learning_runtime_digest_match 由相等性導出(caller 不可自證)。
    recomputed_root = revalidation.get("application_root_learning_runtime_digest")
    derived_match = (
        recomputed_root is not None
        and recomputed_root == source_receipt.get("learning_runtime_digest")
    )
    if revalidation.get("learning_runtime_digest_match") is not derived_match:
        errors.append(
            "s2_2b learning_runtime_digest_match does not derive from the recomputed "
            "application-root digest vs the S2.2A learning_runtime_digest"
        )
    if success and (failing or not derived_match):
        errors.append(
            "s2_2b success requires every V151-V160 fingerprint revalidation to MATCH "
            f"and the application-root learning_runtime_digest to re-derive; failing: "
            f"{sorted(failing) or ['learning_runtime_digest']} (one failing item fails "
            "the whole receipt)"
        )
    return errors


def _freshness_errors(revalidation: dict[str, Any], now_text: str) -> list[str]:
    errors: list[str] = []
    try:
        observed = _parse_timestamp(str(revalidation.get("observed_at")))
        expires = _parse_timestamp(str(revalidation.get("evidence_expires_at")))
        moment = _parse_timestamp(now_text)
        if observed >= expires:
            errors.append("s2_2b observed_at must precede evidence_expires_at")
        if moment >= expires:
            errors.append("s2_2b revalidation evidence is expired at the central gate (fail-closed)")
    except (TypeError, ValueError) as error:
        errors.append(f"s2_2b revalidation timestamps are unparseable: {error}")
    return errors


def _final_attestation_anchor_errors(
    artifact: dict[str, Any], now_text: str
) -> list[str]:
    """s2_5_final_attestation 錨:三值鏈 + 遞迴全套中央閘 + lane 錨定。"""

    errors: list[str] = []
    facade = resolve_facade()
    final = artifact.get("s2_5_final_attestation")
    status = artifact.get("status")
    if not isinstance(final, dict):
        if status != S2_2B_STATUS_REJECTED:
            errors.append(
                "s2_2b requires the exact s2_5_final_attestation_v1 anchor in hand; "
                "absent anchor admits only COMPATIBILITY_REJECTED (design §10: the "
                "post-drill final attestation, never the S2.5A initial one)"
            )
        if artifact.get("s2_5_final_attestation_digest") is not None:
            errors.append(
                "s2_2b s2_5_final_attestation_digest must be null when no anchor is "
                "embedded (a one-sided digest claim is rejected)"
            )
        return errors
    if not _bound_artifact_digest_ok(final, artifact.get("s2_5_final_attestation_digest")):
        errors.append(
            "s2_2b s2_5_final_attestation binding does not re-derive (recompute == "
            "embedded self_digest == bound digest; a self-reported digest is never "
            "trusted)"
        )
        return errors
    # P1-2 紀律:錨要過**全套**中央閘(含 FINAL_ATTESTED 的 attestor 驗簽與新鮮窗)。
    central_errors = facade.validate_aiml_artifact(final, now=now_text)
    if central_errors:
        errors.append(
            "s2_2b s2_5_final_attestation anchor fails the central gate: "
            + "; ".join(central_errors)
        )
        return errors
    final_status = final.get("status")
    if status == S2_2B_STATUS_RUNTIME_ATTESTED:
        # runtime-DONE lane:必錨 production FINAL_ATTESTED;simulated 錨永不解鎖。
        if not (
            final_status == "FINAL_ATTESTED"
            and final.get("target_class") == "production"
        ):
            errors.append(
                "s2_2b RUNTIME_COMPATIBILITY_ATTESTED requires a production "
                "FINAL_ATTESTED final attestation; a simulated-lane anchor never "
                "unlocks the LR1 runtime DONE (fail-closed)"
            )
    elif status in {S2_2B_STATUS_SOURCE_PASS, S2_2B_STATUS_PENDING}:
        if final_status not in {"SOURCE_SIMULATION_PASS", "FINAL_ATTESTED"}:
            errors.append(
                "s2_2b source/pending lanes anchor only a successful final attestation "
                f"(SOURCE_SIMULATION_PASS or FINAL_ATTESTED); got {final_status!r}"
            )
    return errors


def validate_s2_2b_artifact(artifact: Any, *, now: Any = None) -> list[str]:
    """facade 委派入口:closed schema 已過,此處補整合/lane/新鮮度/上游重驗面。"""

    if not isinstance(artifact, dict):
        return ["s2_2b artifact must be an object"]
    now_text = _now_text(now)
    if now_text is None:
        return [
            "s2_2b artifact requires now for freshness at the central gate (fail-closed)"
        ]
    facade = resolve_facade()
    errors: list[str] = []
    if artifact.get("self_digest") != artifact_self_digest(artifact):
        errors.append("s2_2b receipt self_digest does not bind the canonical receipt")
    # 內嵌 S2.2A source receipt:三值鏈 + 遞迴全套中央閘(內層反偽造重算在其分支)。
    source_receipt = artifact.get("source_compatibility_receipt")
    if not _bound_artifact_digest_ok(
        source_receipt, artifact.get("source_compatibility_receipt_digest")
    ):
        errors.append(
            "s2_2b source_compatibility_receipt binding does not re-derive (recompute "
            "== embedded self_digest == bound digest; an S2.2A digest drift or a "
            "self-reported stub fails closed)"
        )
        return errors
    inner_errors = facade.validate_aiml_artifact(source_receipt)
    if inner_errors:
        errors.append(
            "s2_2b embedded S2.2A receipt fails the central gate: "
            + "; ".join(inner_errors)
        )
        return errors
    status = artifact.get("status")
    success = status in _S2_2B_SUCCESS_STATUSES
    revalidation = artifact.get("manifest_revalidation") or {}
    errors.extend(
        _manifest_revalidation_errors(revalidation, source_receipt, success=success)
    )
    errors.extend(_freshness_errors(revalidation, now_text))
    errors.extend(_final_attestation_anchor_errors(artifact, now_text))
    # evidence-class 紀律(schema 條件之上的代碼級縱深):
    attestor = artifact.get("runtime_attestor")
    if artifact.get("evidence_class") == "PLATFORM_OR_EXTERNAL_ATTESTED" and (
        status != S2_2B_STATUS_RUNTIME_ATTESTED or not isinstance(attestor, dict)
    ):
        errors.append(
            "s2_2b evidence_class PLATFORM_OR_EXTERNAL_ATTESTED requires the "
            "runtime-attested status with the runtime_attestor artifact in hand; a "
            "fixture never impersonates platform evidence (fail-closed)"
        )
    if status == S2_2B_STATUS_RUNTIME_ATTESTED and isinstance(attestor, dict):
        # forward-compatible 簽章欄:digest 綁定就地重算(簽章驗證屬 EFFECT session)。
        if attestor.get("manifest_revalidation_digest") != canonical_digest(revalidation):
            errors.append(
                "s2_2b runtime_attestor manifest_revalidation_digest does not "
                "re-derive from the receipt's revalidation face"
            )
        if attestor.get("s2_5_final_attestation_digest") != artifact.get(
            "s2_5_final_attestation_digest"
        ):
            errors.append(
                "s2_2b runtime_attestor s2_5_final_attestation_digest does not bind "
                "the exact final-attestation anchor"
            )
    if status == S2_2B_STATUS_SOURCE_PASS and artifact.get("evidence_class") != (
        "LOCAL_REPRODUCIBLE"
    ):
        errors.append(
            "s2_2b source-lane success is LOCAL_REPRODUCIBLE only (the source lane "
            "never claims platform evidence)"
        )
    if success and artifact.get("failure_reason") is not None:
        errors.append("s2_2b success carries no failure_reason")
    return errors


def s2_2b_abi_projection() -> dict[str, Any]:
    """S2.2B seam 的 code-owned 投影(registry/測試對賬用)。"""

    from aiml_gate_receipt_schema_core import SCHEMA_DIR, SCHEMA_FILES

    return {
        "schema_version": S2_2B_SCHEMA_VERSION,
        "effect_class": S2_2B_EFFECT_CLASS,
        "attestor_identity": S2_2B_ATTESTOR_IDENTITY,
        "attestor_namespace": S2_2B_ATTESTOR_NAMESPACE,
        "never_refreshable_classes": sorted(S2_2B_NEVER_REFRESHABLE_EVIDENCE),
        "runtime_done_consumes": "S2.5B@EFFECT_DONE",
        "schema_file_present": (
            S2_2B_SCHEMA_VERSION in SCHEMA_FILES
            and (SCHEMA_DIR / SCHEMA_FILES[S2_2B_SCHEMA_VERSION]).is_file()
        ),
    }
