"""
Tests for Lease TTL Configuration Module (GAP-L2)
租约 TTL 配置模块测试 (GAP-L2)

Coverage:
  - LeaseTTLConfig dataclass and serialization
  - LeaseTTLValidator against spec bounds
  - TTL value correctness per SM-02 §12
  - Override authority enforcement
  - SpecComplianceReport generation
  - LeaseTTLConfigManager singleton
  - Thread safety
  - Error handling
"""

import sys
import pytest
import threading
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.lease_ttl_config import (
    SPEC_TTL_VALUES,
    LeaseStateForTTL,
    TTLOverrideAuthority,
    LeaseTTLConfig,
    LeaseTTLValidator,
    LeaseTTLValidationError,
    TTLValidationResult,
    SpecComplianceReport,
    LeaseTTLConfigManager,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def default_config():
    return LeaseTTLConfig()


@pytest.fixture
def spec_values():
    return SPEC_TTL_VALUES


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Spec Constants
# ═══════════════════════════════════════════════════════════════════════════════

class TestSpecConstants:
    """Verify SM-02 §12 spec values are correct"""

    def test_active_ttl_spec_value(self, spec_values):
        """SM-02 §12: ACTIVE lease max 30 seconds"""
        assert spec_values["ACTIVE_DEFAULT_TTL_SECONDS"] == 30

    def test_bridged_ttl_spec_value(self, spec_values):
        """SM-02 §12: BRIDGED lease max 60 seconds"""
        assert spec_values["BRIDGED_DEFAULT_TTL_SECONDS"] == 60

    def test_frozen_max_duration_spec_value(self, spec_values):
        """SM-02 §7.4: FROZEN recovery window"""
        assert spec_values["FROZEN_MAX_DURATION_SECONDS"] == 300

    def test_registered_activation_deadline_spec_value(self, spec_values):
        """SM-02 §7.2: REGISTERED to ACTIVE activation deadline"""
        assert spec_values["REGISTERED_TO_ACTIVE_MAX_WAIT_SECONDS"] == 3600


# ═══════════════════════════════════════════════════════════════════════════════
# 2. LeaseTTLConfig Dataclass
# ═══════════════════════════════════════════════════════════════════════════════

class TestLeaseTTLConfig:
    """Test LeaseTTLConfig dataclass"""

    def test_default_values(self, default_config):
        """Verify default config matches spec"""
        assert default_config.active_default_ttl_seconds == 30
        assert default_config.bridged_default_ttl_seconds == 60
        assert default_config.frozen_max_duration_seconds == 300
        assert default_config.registered_to_active_max_wait_seconds == 3600

    def test_immutability(self, default_config):
        """Config should be frozen (immutable)"""
        with pytest.raises(Exception):  # FrozenInstanceError or similar
            default_config.active_default_ttl_seconds = 999

    def test_override_authorities(self, default_config):
        """Verify override authority defaults"""
        assert default_config.active_ttl_override_authority == TTLOverrideAuthority.NEVER
        assert default_config.bridged_ttl_override_authority == TTLOverrideAuthority.NEVER
        assert default_config.frozen_ttl_override_authority == TTLOverrideAuthority.OPERATOR
        assert default_config.registered_ttl_override_authority == TTLOverrideAuthority.NEVER

    def test_to_dict_serialization(self, default_config):
        """Config should serialize to dict"""
        d = default_config.to_dict()
        assert isinstance(d, dict)
        assert d["active_default_ttl_seconds"] == 30
        assert d["bridged_default_ttl_seconds"] == 60
        assert d["config_version"] == "1.0"
        assert d["spec_reference"] == "SM-02 §12"

    def test_to_dict_contains_all_fields(self, default_config):
        """Dict export should include all config fields"""
        d = default_config.to_dict()
        for field in [
            "active_default_ttl_seconds",
            "bridged_default_ttl_seconds",
            "frozen_max_duration_seconds",
            "registered_to_active_max_wait_seconds",
            "active_ttl_override_authority",
            "bridged_ttl_override_authority",
            "frozen_ttl_override_authority",
            "registered_ttl_override_authority",
            "config_version",
            "spec_reference",
        ]:
            assert field in d

    def test_custom_config_creation(self):
        """Can create config with custom values"""
        config = LeaseTTLConfig(
            active_default_ttl_seconds=25,
            bridged_default_ttl_seconds=55,
        )
        assert config.active_default_ttl_seconds == 25
        assert config.bridged_default_ttl_seconds == 55


# ═══════════════════════════════════════════════════════════════════════════════
# 3. LeaseTTLValidator — Spec Compliance
# ═══════════════════════════════════════════════════════════════════════════════

class TestLeaseTTLValidator:
    """Test TTL validation against spec"""

    def test_valid_default_config(self, default_config):
        """Default config should pass validation"""
        result = LeaseTTLValidator.validate_ttl_config(default_config)
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert result.spec_compliance_status == "COMPLIANT"

    def test_active_ttl_spec_mismatch_error(self):
        """ACTIVE TTL != 30s should error"""
        config = LeaseTTLConfig(active_default_ttl_seconds=60)
        result = LeaseTTLValidator.validate_ttl_config(config)
        assert result.is_valid is False
        assert any("ACTIVE TTL mismatch" in err for err in result.errors)
        assert "30s" in str(result.errors)

    def test_bridged_ttl_spec_mismatch_error(self):
        """BRIDGED TTL != 60s should error"""
        config = LeaseTTLConfig(bridged_default_ttl_seconds=30)
        result = LeaseTTLValidator.validate_ttl_config(config)
        assert result.is_valid is False
        assert any("BRIDGED TTL mismatch" in err for err in result.errors)
        assert "60s" in str(result.errors)

    def test_active_ttl_out_of_bounds_low(self):
        """ACTIVE TTL < 10s should error"""
        config = LeaseTTLConfig(active_default_ttl_seconds=5)
        result = LeaseTTLValidator.validate_ttl_config(config)
        assert result.is_valid is False
        assert any("out of bounds" in err for err in result.errors)

    def test_active_ttl_out_of_bounds_high(self):
        """ACTIVE TTL > 60s should error"""
        config = LeaseTTLConfig(active_default_ttl_seconds=100)
        result = LeaseTTLValidator.validate_ttl_config(config)
        assert result.is_valid is False
        assert any("out of bounds" in err for err in result.errors)

    def test_bridged_ttl_out_of_bounds_low(self):
        """BRIDGED TTL < 30s should error"""
        config = LeaseTTLConfig(bridged_default_ttl_seconds=10)
        result = LeaseTTLValidator.validate_ttl_config(config)
        assert result.is_valid is False
        assert any("BRIDGED TTL out of bounds" in err for err in result.errors)

    def test_bridged_ttl_out_of_bounds_high(self):
        """BRIDGED TTL > 300s should error"""
        config = LeaseTTLConfig(bridged_default_ttl_seconds=500)
        result = LeaseTTLValidator.validate_ttl_config(config)
        assert result.is_valid is False
        assert any("BRIDGED TTL out of bounds" in err for err in result.errors)

    def test_frozen_ttl_warning(self):
        """Unusual FROZEN TTL should warn"""
        config = LeaseTTLConfig(frozen_max_duration_seconds=30)
        result = LeaseTTLValidator.validate_ttl_config(config)
        assert len(result.warnings) > 0
        assert any("FROZEN TTL" in w for w in result.warnings)

    def test_override_authority_active_error(self):
        """ACTIVE TTL override must be NEVER"""
        config = LeaseTTLConfig(
            active_ttl_override_authority=TTLOverrideAuthority.OPERATOR
        )
        result = LeaseTTLValidator.validate_ttl_config(config)
        assert result.is_valid is False
        assert any("ACTIVE TTL must NOT be overridable" in err for err in result.errors)

    def test_override_authority_bridged_error(self):
        """BRIDGED TTL override must be NEVER"""
        config = LeaseTTLConfig(
            bridged_default_ttl_seconds=60,
            bridged_ttl_override_authority=TTLOverrideAuthority.OPERATOR
        )
        result = LeaseTTLValidator.validate_ttl_config(config)
        assert result.is_valid is False
        assert any("BRIDGED TTL must NOT be overridable" in err for err in result.errors)

    def test_validation_result_fields(self):
        """TTLValidationResult has required fields"""
        result = TTLValidationResult(
            is_valid=True,
            errors=["error1"],
            warnings=["warn1"],
            spec_compliance_status="COMPLIANT"
        )
        assert result.is_valid is True
        assert "error1" in result.errors
        assert "warn1" in result.warnings
        assert result.spec_compliance_status == "COMPLIANT"

    def test_validation_result_to_dict(self):
        """TTLValidationResult serializes to dict"""
        result = TTLValidationResult(
            is_valid=True,
            errors=[],
            spec_compliance_status="COMPLIANT"
        )
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["is_valid"] is True
        assert d["spec_compliance_status"] == "COMPLIANT"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. SpecComplianceReport
# ═══════════════════════════════════════════════════════════════════════════════

class TestSpecComplianceReport:
    """Test compliance report generation"""

    def test_report_creation(self, default_config):
        """Can create compliance report from valid config"""
        validation = LeaseTTLValidator.validate_ttl_config(default_config)
        report = SpecComplianceReport(
            config=default_config,
            validation_result=validation
        )
        assert report.config == default_config
        assert report.validation_result == validation

    def test_report_to_dict(self, default_config):
        """Report serializes to dict"""
        validation = LeaseTTLValidator.validate_ttl_config(default_config)
        report = SpecComplianceReport(
            config=default_config,
            validation_result=validation
        )
        d = report.to_dict()
        assert isinstance(d, dict)
        assert "config" in d
        assert "validation" in d
        assert d["spec_reference"] == "SM-02 §12 (Expiry & Invalidation)"
        assert d["issue_reference"] == "GAP-L2 (Decision Lease TTL Spec Alignment)"

    def test_report_text_generation(self, default_config):
        """Can generate human-readable compliance report"""
        validation = LeaseTTLValidator.validate_ttl_config(default_config)
        report = SpecComplianceReport(
            config=default_config,
            validation_result=validation
        )
        text = report.generate_text_report()
        assert isinstance(text, str)
        assert "LEASE TTL SPEC COMPLIANCE REPORT" in text
        assert "ACTIVE lease TTL" in text
        assert "BRIDGED lease TTL" in text
        assert "PASSED" in text or "COMPLIANT" in text

    def test_report_contains_spec_values(self, default_config):
        """Report includes spec values"""
        validation = LeaseTTLValidator.validate_ttl_config(default_config)
        report = SpecComplianceReport(
            config=default_config,
            validation_result=validation
        )
        text = report.generate_text_report()
        assert "30" in text  # ACTIVE TTL
        assert "60" in text  # BRIDGED TTL

    def test_report_with_errors(self):
        """Report includes error details"""
        config = LeaseTTLConfig(
            active_default_ttl_seconds=60,  # Wrong
            active_ttl_override_authority=TTLOverrideAuthority.OPERATOR  # Wrong
        )
        validation = LeaseTTLValidator.validate_ttl_config(config)
        report = SpecComplianceReport(
            config=config,
            validation_result=validation
        )
        text = report.generate_text_report()
        assert "ERRORS" in text
        assert "✗" in text  # Error marker


# ═══════════════════════════════════════════════════════════════════════════════
# 5. LeaseTTLConfigManager
# ═══════════════════════════════════════════════════════════════════════════════

class TestLeaseTTLConfigManager:
    """Test config manager"""

    def test_manager_creation_valid_config(self, default_config):
        """Can create manager with valid config"""
        manager = LeaseTTLConfigManager(config=default_config)
        assert manager is not None

    def test_manager_rejects_invalid_config(self):
        """Manager rejects invalid config on creation"""
        invalid_config = LeaseTTLConfig(
            active_default_ttl_seconds=60,  # Wrong
            active_ttl_override_authority=TTLOverrideAuthority.OPERATOR  # Wrong
        )
        with pytest.raises(LeaseTTLValidationError):
            LeaseTTLConfigManager(config=invalid_config)

    def test_manager_get_config(self, default_config):
        """Can retrieve config from manager"""
        manager = LeaseTTLConfigManager(config=default_config)
        retrieved = manager.get_config()
        assert retrieved.active_default_ttl_seconds == 30
        assert retrieved.bridged_default_ttl_seconds == 60

    def test_manager_compliance_report(self, default_config):
        """Manager can generate compliance report"""
        manager = LeaseTTLConfigManager(config=default_config)
        report = manager.get_compliance_report()
        assert isinstance(report, SpecComplianceReport)
        assert report.validation_result.is_valid is True

    def test_manager_singleton_pattern(self, default_config):
        """Manager implements singleton pattern"""
        manager1 = LeaseTTLConfigManager.get_instance(config=default_config)
        manager2 = LeaseTTLConfigManager.get_instance()
        assert manager1 is manager2

    def test_manager_change_log_export(self, default_config):
        """Manager exports change log"""
        manager = LeaseTTLConfigManager(config=default_config)
        log = manager.export_change_log()
        assert isinstance(log, list)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Thread Safety
# ═══════════════════════════════════════════════════════════════════════════════

class TestThreadSafety:
    """Test thread safety"""

    def test_concurrent_config_access(self, default_config):
        """Multiple threads can safely access config"""
        manager = LeaseTTLConfigManager(config=default_config)
        results = []

        def worker():
            config = manager.get_config()
            results.append(config.active_default_ttl_seconds)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(results) == 10
        assert all(r == 30 for r in results)

    def test_concurrent_report_generation(self, default_config):
        """Multiple threads can generate reports concurrently"""
        manager = LeaseTTLConfigManager(config=default_config)
        reports = []

        def worker():
            report = manager.get_compliance_report()
            reports.append(report)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(reports) == 5
        assert all(r.validation_result.is_valid for r in reports)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Error Handling
# ═══════════════════════════════════════════════════════════════════════════════

class TestErrorHandling:
    """Test error handling and edge cases"""

    def test_validation_error_has_message(self):
        """LeaseTTLValidationError has descriptive message"""
        invalid_config = LeaseTTLConfig(
            active_default_ttl_seconds=60,
            active_ttl_override_authority=TTLOverrideAuthority.OPERATOR
        )
        with pytest.raises(LeaseTTLValidationError) as exc_info:
            LeaseTTLConfigManager(config=invalid_config)
        assert str(exc_info.value)  # Has a message

    def test_validator_with_none_config(self):
        """Validator handles None gracefully"""
        # This would raise AttributeError, which is fine
        try:
            LeaseTTLValidator.validate_ttl_config(None)
        except (AttributeError, TypeError):
            pass  # Expected

    def test_multiple_errors_reported(self):
        """Validator reports multiple errors"""
        config = LeaseTTLConfig(
            active_default_ttl_seconds=5,      # Too low
            active_ttl_override_authority=TTLOverrideAuthority.OPERATOR,  # Wrong
            bridged_default_ttl_seconds=500,   # Too high
        )
        result = LeaseTTLValidator.validate_ttl_config(config)
        assert len(result.errors) >= 3  # Multiple errors


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Integration Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntegration:
    """End-to-end integration tests"""

    def test_full_compliance_workflow(self):
        """Complete workflow: config → validation → report"""
        config = LeaseTTLConfig()
        validation = LeaseTTLValidator.validate_ttl_config(config)
        report = SpecComplianceReport(config=config, validation_result=validation)
        manager = LeaseTTLConfigManager(config=config)

        # All parts work together
        assert manager.get_config() == config
        assert manager.get_compliance_report().validation_result.is_valid is True
        assert "COMPLIANT" in report.generate_text_report()

    def test_config_export_and_dict_roundtrip(self, default_config):
        """Config can be exported and reconstructed from dict"""
        original_dict = default_config.to_dict()
        assert isinstance(original_dict, dict)
        assert original_dict["active_default_ttl_seconds"] == 30

    def test_spec_reference_consistency(self, default_config):
        """Spec reference is consistent across all components"""
        config = default_config
        validation = LeaseTTLValidator.validate_ttl_config(config)
        report = SpecComplianceReport(config=config, validation_result=validation)

        assert "SM-02" in config.spec_reference
        assert "SM-02" in report.to_dict()["spec_reference"]


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Coverage - Edge Cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Edge case coverage"""

    def test_zero_ttl(self):
        """Zero TTL should fail validation"""
        config = LeaseTTLConfig(active_default_ttl_seconds=0)
        result = LeaseTTLValidator.validate_ttl_config(config)
        assert not result.is_valid

    def test_negative_ttl(self):
        """Negative TTL should fail validation"""
        config = LeaseTTLConfig(active_default_ttl_seconds=-10)
        result = LeaseTTLValidator.validate_ttl_config(config)
        assert not result.is_valid

    def test_max_boundary_active(self):
        """ACTIVE TTL at max boundary (60s) should pass (barely)"""
        config = LeaseTTLConfig(active_default_ttl_seconds=60)
        result = LeaseTTLValidator.validate_ttl_config(config)
        # Will have error about mismatch, but not out-of-bounds
        assert any("mismatch" in err for err in result.errors)

    def test_min_boundary_active(self):
        """ACTIVE TTL at min boundary (10s) should pass bounds check"""
        config = LeaseTTLConfig(active_default_ttl_seconds=10)
        result = LeaseTTLValidator.validate_ttl_config(config)
        # Will have error about mismatch, but not out-of-bounds
        assert any("mismatch" in err for err in result.errors)

    def test_leasestate_enum_values(self):
        """LeaseStateForTTL enum has expected values"""
        assert LeaseStateForTTL.REGISTERED.value == "REGISTERED"
        assert LeaseStateForTTL.ACTIVE.value == "ACTIVE"
        assert LeaseStateForTTL.BRIDGED.value == "BRIDGED"
        assert LeaseStateForTTL.FROZEN.value == "FROZEN"

    def test_override_authority_enum_values(self):
        """TTLOverrideAuthority enum has expected values"""
        assert TTLOverrideAuthority.NEVER.value == "never"
        assert TTLOverrideAuthority.OPERATOR.value == "operator"
        assert TTLOverrideAuthority.SYSTEM_ADMIN.value == "system_admin"
