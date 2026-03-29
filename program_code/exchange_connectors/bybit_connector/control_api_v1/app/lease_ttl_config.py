"""
Lease TTL Configuration Module — SM-02 Governance Spec Alignment (GAP-L2)
租约 TTL 配置模块 — SM-02 治理规范对齐（GAP-L2）

MODULE_NOTE (中文):
  本模块实现 GAP-L2 对 Decision Lease TTL 值的正式规范对齐：

  **问题背景 / Issue Background:**
  - SM-02 规范明确定义 ACTIVE lease 默认 TTL 为 30 秒
  - 历史代码中曾出现 ACTIVE = 60 秒的偏差
  - 本模块通过单一真实来源（SSOT）确保 TTL 值始终与 SM-02 规范一致

  **实现内容 / Implementation:**
  - LeaseTTLConfig: 租约 TTL 参数数据类，包含所有 SM-02 规范定义的 TTL 值
  - LeaseTTLValidator: TTL 值验证器，检查所有 TTL 值是否在规范边界内
  - TTL 覆盖规则：定义哪些 TTL 可以被覆盖，以及由谁覆盖
  - 规范合规性报告：比较当前配置与 SM-02 规范需求
  - 完整审计日志：所有 TTL 更改都被记录

MODULE_NOTE (English):
  Implements formal spec alignment for Decision Lease TTL values per SM-02 governance spec (GAP-L2):

  **Issue Background:**
  - SM-02 spec explicitly defines ACTIVE lease default TTL as 30 seconds
  - Historical code had drift with ACTIVE = 60 seconds
  - This module enforces single source of truth (SSOT) ensuring all TTL values remain spec-aligned

  **Implementation:**
  - LeaseTTLConfig: Dataclass with all SM-02-defined TTL parameters
  - LeaseTTLValidator: Validates all TTL values are within spec bounds
  - TTL override rules: Defines which TTLs can be overridden and by whom
  - Spec compliance report: Compares current config vs SM-02 requirements
  - Audit trail: All TTL changes are logged

Key Design Invariants:
  - All TTL values are sourced from SM-02 §12 (Expiry & Invalidation)
  - ACTIVE lease TTL: 30 seconds (NOT 60) — enforced by spec
  - BRIDGED lease TTL: 60 seconds — enforced by spec
  - FROZEN lease max duration: 300 seconds (5 minutes) — recovery window
  - REGISTERED to ACTIVE max wait: 3600 seconds (1 hour) — activation deadline
  - No TTL can be bypassed; all overrides require audit trail
  - Thread-safe, immutable config objects
"""

from __future__ import annotations

import json
import logging
import time
import threading
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Constants / 常数 (SM-02 §12)
# ═══════════════════════════════════════════════════════════════════════════════

class LeaseStateForTTL(str, Enum):
    """Lease states that have explicit TTL constraints per SM-02 §12"""
    REGISTERED = "REGISTERED"
    ACTIVE = "ACTIVE"
    BRIDGED = "BRIDGED"
    FROZEN = "FROZEN"


class TTLOverrideAuthority(str, Enum):
    """Who can override TTL values"""
    SYSTEM_ADMIN = "system_admin"
    OPERATOR = "operator"
    INCIDENT_POLICY = "incident_policy"
    AUTHORIZATION_GOVERNANCE = "authorization_governance"
    NEVER = "never"  # TTL cannot be overridden


# ═══════════════════════════════════════════════════════════════════════════════
# Spec Reference (SM-02 §12)
# ═══════════════════════════════════════════════════════════════════════════════

SPEC_TTL_VALUES: dict[str, int] = {
    # SM-02 §12: "Decision Lease ACTIVE max 30 seconds → auto-EXPIRE"
    # 租约处于活跃状态最多30秒后自动过期
    "ACTIVE_DEFAULT_TTL_SECONDS": 30,

    # SM-02 §12: "Decision Lease BRIDGED max 60 seconds → auto-EXPIRE"
    # 租约已桥接至下游最多60秒后自动过期
    "BRIDGED_DEFAULT_TTL_SECONDS": 60,

    # SM-02 §7.4: FROZEN recovery window
    # 冻结状态下的恢复观察期
    "FROZEN_MAX_DURATION_SECONDS": 300,  # 5 minutes

    # SM-02 §7.2: REGISTERED to ACTIVE activation deadline
    # 已注册状态下激活的最大等待时间
    "REGISTERED_TO_ACTIVE_MAX_WAIT_SECONDS": 3600,  # 1 hour
}


# ═══════════════════════════════════════════════════════════════════════════════
# Lease TTL Configuration / 租约 TTL 配置
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class LeaseTTLConfig:
    """
    Formal TTL configuration for Decision Lease states per SM-02 §12.

    All values are locked to SM-02 spec and cannot be changed without
    explicit governance approval and audit trail.

    所有 TTL 值均锁定于 SM-02 规范，不可在没有明确治理批准和审计记录的情况下更改。
    """

    # ──────────────────────────────────────────────────────────────────────────
    # ACTIVE Lease TTL (SM-02 §12)
    # ──────────────────────────────────────────────────────────────────────────
    # Per SM-02: "Lease ACTIVE max 30 seconds → auto-EXPIRE"
    # Historical drift: Code had 60s → CORRECTED TO 30s
    active_default_ttl_seconds: int = SPEC_TTL_VALUES["ACTIVE_DEFAULT_TTL_SECONDS"]

    # ──────────────────────────────────────────────────────────────────────────
    # BRIDGED Lease TTL (SM-02 §12)
    # ──────────────────────────────────────────────────────────────────────────
    # Per SM-02: "Lease BRIDGED max 60 seconds → auto-EXPIRE"
    bridged_default_ttl_seconds: int = SPEC_TTL_VALUES["BRIDGED_DEFAULT_TTL_SECONDS"]

    # ──────────────────────────────────────────────────────────────────────────
    # FROZEN Lease Max Duration (SM-02 §7.4)
    # ──────────────────────────────────────────────────────────────────────────
    # Recovery observation window: frozen lease cannot stay frozen indefinitely
    frozen_max_duration_seconds: int = SPEC_TTL_VALUES["FROZEN_MAX_DURATION_SECONDS"]

    # ──────────────────────────────────────────────────────────────────────────
    # REGISTERED to ACTIVE Max Wait (SM-02 §7.2)
    # ──────────────────────────────────────────────────────────────────────────
    # Lease cannot wait in REGISTERED state indefinitely before activation
    registered_to_active_max_wait_seconds: int = SPEC_TTL_VALUES["REGISTERED_TO_ACTIVE_MAX_WAIT_SECONDS"]

    # ──────────────────────────────────────────────────────────────────────────
    # Override Rules / 覆盖规则
    # ──────────────────────────────────────────────────────────────────────────
    # Which TTLs can be overridden and by whom (typically NEVER for spec values)
    active_ttl_override_authority: TTLOverrideAuthority = TTLOverrideAuthority.NEVER
    bridged_ttl_override_authority: TTLOverrideAuthority = TTLOverrideAuthority.NEVER
    frozen_ttl_override_authority: TTLOverrideAuthority = TTLOverrideAuthority.OPERATOR
    registered_ttl_override_authority: TTLOverrideAuthority = TTLOverrideAuthority.NEVER

    # ──────────────────────────────────────────────────────────────────────────
    # Metadata / 元数据
    # ──────────────────────────────────────────────────────────────────────────
    config_version: str = "1.0"  # Config format version
    spec_reference: str = "SM-02 §12"  # Which spec section defines these values
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        """Export configuration as dict (excluding timestamps)"""
        return {
            "active_default_ttl_seconds": self.active_default_ttl_seconds,
            "bridged_default_ttl_seconds": self.bridged_default_ttl_seconds,
            "frozen_max_duration_seconds": self.frozen_max_duration_seconds,
            "registered_to_active_max_wait_seconds": self.registered_to_active_max_wait_seconds,
            "active_ttl_override_authority": self.active_ttl_override_authority.value,
            "bridged_ttl_override_authority": self.bridged_ttl_override_authority.value,
            "frozen_ttl_override_authority": self.frozen_ttl_override_authority.value,
            "registered_ttl_override_authority": self.registered_ttl_override_authority.value,
            "config_version": self.config_version,
            "spec_reference": self.spec_reference,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# TTL Validator / TTL 验证器
# ═══════════════════════════════════════════════════════════════════════════════

class LeaseTTLValidationError(Exception):
    """Raised when TTL configuration violates spec bounds"""
    pass


@dataclass
class TTLValidationResult:
    """Result of TTL validation check"""
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    spec_compliance_status: str = "COMPLIANT"  # COMPLIANT, NON_COMPLIANT, DEGRADED

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LeaseTTLValidator:
    """
    Validator for Lease TTL configuration against SM-02 spec bounds.
    确保 Lease TTL 配置符合 SM-02 规范边界的验证器。
    """

    # Min/Max bounds per spec
    MIN_ACTIVE_TTL_SECONDS = 10      # Absolute minimum
    MAX_ACTIVE_TTL_SECONDS = 60      # Absolute maximum (spec says 30)
    MIN_BRIDGED_TTL_SECONDS = 30
    MAX_BRIDGED_TTL_SECONDS = 300    # Absolute maximum
    MIN_FROZEN_TTL_SECONDS = 60
    MAX_FROZEN_TTL_SECONDS = 1800    # Max 30 minutes frozen

    @staticmethod
    def validate_ttl_config(config: LeaseTTLConfig) -> TTLValidationResult:
        """
        Validate TTL configuration against SM-02 spec bounds.

        Returns:
            TTLValidationResult with compliance status and any violations
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Check ACTIVE TTL
        if config.active_default_ttl_seconds != SPEC_TTL_VALUES["ACTIVE_DEFAULT_TTL_SECONDS"]:
            errors.append(
                f"ACTIVE TTL mismatch: got {config.active_default_ttl_seconds}s, "
                f"spec requires {SPEC_TTL_VALUES['ACTIVE_DEFAULT_TTL_SECONDS']}s (SM-02 §12)"
            )

        if not (LeaseTTLValidator.MIN_ACTIVE_TTL_SECONDS <=
                config.active_default_ttl_seconds <=
                LeaseTTLValidator.MAX_ACTIVE_TTL_SECONDS):
            errors.append(
                f"ACTIVE TTL out of bounds: {config.active_default_ttl_seconds}s "
                f"(min: {LeaseTTLValidator.MIN_ACTIVE_TTL_SECONDS}s, "
                f"max: {LeaseTTLValidator.MAX_ACTIVE_TTL_SECONDS}s)"
            )

        # Check BRIDGED TTL
        if config.bridged_default_ttl_seconds != SPEC_TTL_VALUES["BRIDGED_DEFAULT_TTL_SECONDS"]:
            errors.append(
                f"BRIDGED TTL mismatch: got {config.bridged_default_ttl_seconds}s, "
                f"spec requires {SPEC_TTL_VALUES['BRIDGED_DEFAULT_TTL_SECONDS']}s (SM-02 §12)"
            )

        if not (LeaseTTLValidator.MIN_BRIDGED_TTL_SECONDS <=
                config.bridged_default_ttl_seconds <=
                LeaseTTLValidator.MAX_BRIDGED_TTL_SECONDS):
            errors.append(
                f"BRIDGED TTL out of bounds: {config.bridged_default_ttl_seconds}s "
                f"(min: {LeaseTTLValidator.MIN_BRIDGED_TTL_SECONDS}s, "
                f"max: {LeaseTTLValidator.MAX_BRIDGED_TTL_SECONDS}s)"
            )

        # Check FROZEN TTL
        if not (LeaseTTLValidator.MIN_FROZEN_TTL_SECONDS <=
                config.frozen_max_duration_seconds <=
                LeaseTTLValidator.MAX_FROZEN_TTL_SECONDS):
            warnings.append(
                f"FROZEN TTL out of typical range: {config.frozen_max_duration_seconds}s "
                f"(recommended: {LeaseTTLValidator.MIN_FROZEN_TTL_SECONDS}s–"
                f"{LeaseTTLValidator.MAX_FROZEN_TTL_SECONDS}s)"
            )

        # Check REGISTERED→ACTIVE max wait
        if config.registered_to_active_max_wait_seconds < 60:
            warnings.append(
                f"REGISTERED→ACTIVE max wait is very short: "
                f"{config.registered_to_active_max_wait_seconds}s"
            )

        # Check override authorities — ACTIVE and BRIDGED must NOT be overridable
        if config.active_ttl_override_authority != TTLOverrideAuthority.NEVER:
            errors.append(
                f"ACTIVE TTL must NOT be overridable per spec (SM-02 §12), "
                f"but override_authority is {config.active_ttl_override_authority.value}"
            )

        if config.bridged_ttl_override_authority != TTLOverrideAuthority.NEVER:
            errors.append(
                f"BRIDGED TTL must NOT be overridable per spec (SM-02 §12), "
                f"but override_authority is {config.bridged_ttl_override_authority.value}"
            )

        is_valid = len(errors) == 0
        spec_status = "COMPLIANT" if is_valid else "NON_COMPLIANT"
        if warnings and is_valid:
            spec_status = "DEGRADED"

        return TTLValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            spec_compliance_status=spec_status,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Spec Compliance Report / 规范合规性报告
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SpecComplianceReport:
    """Detailed report comparing current config vs SM-02 spec requirements"""

    config: LeaseTTLConfig
    validation_result: TTLValidationResult
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        """Export compliance report as dict"""
        return {
            "timestamp_ms": self.timestamp_ms,
            "config": self.config.to_dict(),
            "validation": self.validation_result.to_dict(),
            "spec_reference": "SM-02 §12 (Expiry & Invalidation)",
            "issue_reference": "GAP-L2 (Decision Lease TTL Spec Alignment)",
            "spec_version": "V1",
        }

    def generate_text_report(self) -> str:
        """Generate human-readable compliance report"""
        lines = [
            "═" * 80,
            "LEASE TTL SPEC COMPLIANCE REPORT",
            "租约 TTL 规范合规性报告",
            "═" * 80,
            "",
            "ISSUE REFERENCE: GAP-L2",
            "SPEC REFERENCE: SM-02 §12 (Expiry & Invalidation Doctrine)",
            "",
            "COMPLIANCE STATUS: " + self.validation_result.spec_compliance_status,
            "",
            "─" * 80,
            "CONFIGURATION VALUES",
            "─" * 80,
            "",
            f"  ACTIVE lease TTL (default):          {self.config.active_default_ttl_seconds:4d}s  [spec: {SPEC_TTL_VALUES['ACTIVE_DEFAULT_TTL_SECONDS']}s]",
            f"  BRIDGED lease TTL (default):         {self.config.bridged_default_ttl_seconds:4d}s  [spec: {SPEC_TTL_VALUES['BRIDGED_DEFAULT_TTL_SECONDS']}s]",
            f"  FROZEN lease max duration:           {self.config.frozen_max_duration_seconds:4d}s",
            f"  REGISTERED→ACTIVE max wait:         {self.config.registered_to_active_max_wait_seconds:4d}s",
            "",
            "─" * 80,
            "OVERRIDE AUTHORITIES",
            "─" * 80,
            "",
            f"  ACTIVE TTL override:                 {self.config.active_ttl_override_authority.value}",
            f"  BRIDGED TTL override:                {self.config.bridged_ttl_override_authority.value}",
            f"  FROZEN TTL override:                 {self.config.frozen_ttl_override_authority.value}",
            f"  REGISTERED TTL override:             {self.config.registered_ttl_override_authority.value}",
            "",
        ]

        if self.validation_result.errors:
            lines.extend([
                "─" * 80,
                "ERRORS (Must be fixed)",
                "─" * 80,
                "",
            ])
            for err in self.validation_result.errors:
                lines.append(f"  ✗ {err}")
            lines.append("")

        if self.validation_result.warnings:
            lines.extend([
                "─" * 80,
                "WARNINGS",
                "─" * 80,
                "",
            ])
            for warn in self.validation_result.warnings:
                lines.append(f"  ⚠ {warn}")
            lines.append("")

        if self.validation_result.is_valid:
            lines.extend([
                "─" * 80,
                "VALIDATION: ✓ PASSED",
                "─" * 80,
                "",
                "All TTL values conform to SM-02 §12 specification.",
                "所有 TTL 值均符合 SM-02 §12 规范。",
                "",
            ])

        lines.extend([
            "═" * 80,
            f"Report generated at: {int(time.time())}",
            "═" * 80,
        ])

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Global Config Manager / 全局配置管理器
# ═══════════════════════════════════════════════════════════════════════════════

class LeaseTTLConfigManager:
    """
    Thread-safe manager for Lease TTL configuration.
    Ensures single source of truth (SSOT) for all TTL values.
    """

    _instance: Optional[LeaseTTLConfigManager] = None
    _lock = threading.Lock()

    def __init__(self, config: Optional[LeaseTTLConfig] = None):
        self._config = config or LeaseTTLConfig()
        self._config_lock = threading.Lock()
        self._change_log: list[dict[str, Any]] = []

        # Validate on init
        result = LeaseTTLValidator.validate_ttl_config(self._config)
        if not result.is_valid:
            raise LeaseTTLValidationError(
                "Initial config is invalid:\n" + "\n".join(result.errors)
            )

    @classmethod
    def get_instance(cls, config: Optional[LeaseTTLConfig] = None) -> LeaseTTLConfigManager:
        """Get singleton instance"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(config)
        return cls._instance

    def get_config(self) -> LeaseTTLConfig:
        """Get current config (immutable)"""
        with self._config_lock:
            return self._config

    def get_compliance_report(self) -> SpecComplianceReport:
        """Generate current compliance report"""
        config = self.get_config()
        validation = LeaseTTLValidator.validate_ttl_config(config)
        return SpecComplianceReport(config=config, validation_result=validation)

    def _record_change(self, change: dict[str, Any]) -> None:
        """Log a configuration change (internal use only)"""
        with self._config_lock:
            self._change_log.append({
                "timestamp_ms": int(time.time() * 1000),
                **change,
            })

    def export_change_log(self) -> list[dict[str, Any]]:
        """Export all configuration changes for audit"""
        with self._config_lock:
            return list(self._change_log)


# ═══════════════════════════════════════════════════════════════════════════════
# Module-level initialization / 模块级初始化
# ═══════════════════════════════════════════════════════════════════════════════

# Create default global config on module import
DEFAULT_LEASE_TTL_CONFIG = LeaseTTLConfig()

# Validate it on module init
_validation = LeaseTTLValidator.validate_ttl_config(DEFAULT_LEASE_TTL_CONFIG)
if not _validation.is_valid:
    logger.error(
        "Default Lease TTL config is invalid:\n%s",
        "\n".join(_validation.errors)
    )
else:
    logger.info("Lease TTL config initialized per SM-02 §12 spec")
    if _validation.warnings:
        for warn in _validation.warnings:
            logger.warning("TTL config warning: %s", warn)
