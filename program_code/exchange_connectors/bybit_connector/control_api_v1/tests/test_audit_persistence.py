"""
Tests for Audit Persistence Layer — EX-01 §8 / GAP-H3
审计持久化层测试

Covers:
  - File writing and reading (JSON Lines)
  - Date-based rotation
  - Size-based rotation
  - Append-only guarantee
  - Query filters (time, source, event type, keyword)
  - Daily summary generation
  - AuditPipeline integration
  - Thread safety
  - Corrupted line handling
"""

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.audit_persistence import (
    AuditFileReader,
    AuditFileWriter,
    AuditPersistenceConfig,
    AuditPipeline,
    wrap_audit_record,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_audit_dir():
    """Temp directory for audit files / 临时审计目录"""
    with tempfile.TemporaryDirectory(prefix="audit_test_") as d:
        yield d


@pytest.fixture
def config(tmp_audit_dir):
    return AuditPersistenceConfig(
        base_dir=tmp_audit_dir,
        flush_after_write=True,
    )


@pytest.fixture
def writer(config):
    w = AuditFileWriter(config)
    yield w
    w.close()


@pytest.fixture
def reader(tmp_audit_dir):
    return AuditFileReader(base_dir=tmp_audit_dir)


@pytest.fixture
def pipeline(config):
    p = AuditPipeline(config)
    yield p
    p.close()


def _sample_record(event: str = "test_event") -> dict:
    return {
        "transition_id": f"tx:{os.urandom(6).hex()}",
        "trigger_event": event,
        "previous_status": "STATE_A",
        "next_status": "STATE_B",
        "initiated_by": "TestSuite",
        "effective_at_ms": int(time.time() * 1000),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Wrap Record / 记录封装测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestWrapRecord:
    def test_envelope_fields(self):
        record = {"key": "value"}
        envelope = wrap_audit_record(record, source="test")
        assert envelope["audit_id"].startswith("aud:")
        assert envelope["source"] == "test"
        assert "persisted_at_ms" in envelope
        assert envelope["record"] == record

    def test_unique_ids(self):
        r1 = wrap_audit_record({}, source="a")
        r2 = wrap_audit_record({}, source="a")
        assert r1["audit_id"] != r2["audit_id"]


# ═══════════════════════════════════════════════════════════════════════════════
# 2. File Writer / 文件写入测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestFileWriter:
    def test_write_creates_file(self, writer, tmp_audit_dir):
        writer.write(_sample_record(), source="test")
        files = list(Path(tmp_audit_dir).glob("*.jsonl"))
        assert len(files) == 1

    def test_write_appends_jsonl(self, writer, tmp_audit_dir):
        writer.write(_sample_record("evt1"), source="test")
        writer.write(_sample_record("evt2"), source="test")
        writer.write(_sample_record("evt3"), source="test")

        files = list(Path(tmp_audit_dir).glob("*.jsonl"))
        assert len(files) == 1

        with open(files[0], "r") as f:
            lines = [l for l in f if l.strip()]
        assert len(lines) == 3

        # Each line is valid JSON
        for line in lines:
            parsed = json.loads(line)
            assert "audit_id" in parsed
            assert "record" in parsed

    def test_write_returns_audit_id(self, writer):
        aid = writer.write(_sample_record(), source="test")
        assert aid.startswith("aud:")

    def test_total_records_counter(self, writer):
        for i in range(5):
            writer.write(_sample_record(), source="test")
        assert writer.total_records == 5

    def test_write_batch(self, writer, tmp_audit_dir):
        records = [_sample_record(f"batch_{i}") for i in range(10)]
        ids = writer.write_batch(records, source="batch_test")
        assert len(ids) == 10
        assert writer.total_records == 10

    def test_status(self, writer):
        writer.write(_sample_record(), source="test")
        status = writer.get_status()
        assert status["records_in_file"] == 1
        assert status["current_file"] is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 3. File Rotation / 文件轮转测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestRotation:
    def test_size_based_rotation(self, tmp_audit_dir):
        """Files should rotate when exceeding max size / 超大小限制应轮转"""
        config = AuditPersistenceConfig(
            base_dir=tmp_audit_dir,
            max_file_size_bytes=500,  # Very small for testing
            rotate_by_date=True,
        )
        writer = AuditFileWriter(config)

        # Write enough records to trigger rotation
        for i in range(50):
            writer.write({"data": "x" * 50, "seq": i}, source="size_test")

        writer.close()

        files = sorted(Path(tmp_audit_dir).glob("*.jsonl"))
        assert len(files) >= 2, f"Expected rotation, got {len(files)} files"

    def test_record_count_rotation(self, tmp_audit_dir):
        """Files should rotate when exceeding max records / 超记录数应轮转"""
        config = AuditPersistenceConfig(
            base_dir=tmp_audit_dir,
            max_records_per_file=5,
            max_file_size_bytes=999_999_999,  # Don't trigger size rotation
        )
        writer = AuditFileWriter(config)

        for i in range(12):
            writer.write({"seq": i}, source="count_test")

        writer.close()

        files = sorted(Path(tmp_audit_dir).glob("*.jsonl"))
        assert len(files) >= 2


# ═══════════════════════════════════════════════════════════════════════════════
# 4. File Reader / 文件读取测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestFileReader:
    def test_list_files(self, writer, reader, tmp_audit_dir):
        writer.write(_sample_record(), source="test")
        files = reader.list_files()
        assert len(files) == 1

    def test_read_file(self, writer, reader, tmp_audit_dir):
        writer.write(_sample_record("e1"), source="test")
        writer.write(_sample_record("e2"), source="test")

        files = reader.list_files()
        records = list(reader.read_file(files[0]))
        assert len(records) == 2
        assert records[0]["record"]["trigger_event"] == "e1"

    def test_corrupted_line_skipped(self, tmp_audit_dir):
        """Corrupted JSON lines should be skipped / 损坏行应被跳过"""
        fpath = Path(tmp_audit_dir) / "audit_2026-03-29.jsonl"
        with open(fpath, "w") as f:
            f.write('{"valid": true}\n')
            f.write('THIS IS NOT JSON\n')
            f.write('{"also_valid": true}\n')

        reader = AuditFileReader(base_dir=tmp_audit_dir)
        records = list(reader.read_file(fpath))
        assert len(records) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Query / 查询测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestQuery:
    def _seed_records(self, writer):
        """Seed test records / 写入测试记录"""
        for i in range(10):
            writer.write(
                {"trigger_event": f"event_{i % 3}", "seq": i, "data": f"record_{i}"},
                source=f"source_{i % 2}",
            )

    def test_query_all(self, writer, reader):
        self._seed_records(writer)
        results = reader.query(limit=100)
        assert len(results) == 10

    def test_query_by_source(self, writer, reader):
        self._seed_records(writer)
        results = reader.query(source="source_0", limit=100)
        assert all(r["source"] == "source_0" for r in results)
        assert len(results) == 5

    def test_query_by_event_type(self, writer, reader):
        self._seed_records(writer)
        results = reader.query(event_type="event_0", limit=100)
        assert len(results) > 0
        for r in results:
            assert "event_0" in r["record"]["trigger_event"]

    def test_query_by_keyword(self, writer, reader):
        self._seed_records(writer)
        results = reader.query(keyword="record_5", limit=100)
        assert len(results) == 1

    def test_query_limit(self, writer, reader):
        self._seed_records(writer)
        results = reader.query(limit=3)
        assert len(results) == 3

    def test_query_by_time_range(self, writer, reader):
        now_ms = int(time.time() * 1000)
        writer.write({"trigger_event": "old"}, source="test")
        time.sleep(0.01)
        mid_ms = int(time.time() * 1000)
        writer.write({"trigger_event": "new"}, source="test")

        results = reader.query(start_ms=mid_ms, limit=100)
        assert len(results) >= 1
        assert all(r["persisted_at_ms"] >= mid_ms for r in results)

    def test_query_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            reader = AuditFileReader(base_dir=d)
            results = reader.query()
            assert results == []


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Daily Summary / 每日摘要测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestDailySummary:
    def test_generate_summary(self, writer, reader):
        writer.write({"trigger_event": "evt_a"}, source="auth_sm")
        writer.write({"trigger_event": "evt_b"}, source="auth_sm")
        writer.write({"trigger_event": "evt_a"}, source="risk_gov")

        today = time.strftime("%Y-%m-%d", time.gmtime())
        summary = reader.generate_daily_summary(today)

        assert summary["date"] == today
        assert summary["total_records"] == 3
        assert summary["source_breakdown"]["auth_sm"] == 2
        assert summary["source_breakdown"]["risk_gov"] == 1
        assert summary["event_breakdown"]["evt_a"] == 2
        assert summary["event_breakdown"]["evt_b"] == 1

    def test_summary_empty_date(self, reader):
        summary = reader.generate_daily_summary("2000-01-01")
        assert summary["total_records"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Audit Pipeline / 审计管道测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditPipeline:
    def test_ingest_persists(self, pipeline, tmp_audit_dir):
        aid = pipeline.ingest(_sample_record(), source="test")
        assert aid.startswith("aud:")

        files = list(Path(tmp_audit_dir).glob("*.jsonl"))
        assert len(files) == 1

    def test_make_callback(self, pipeline):
        cb = pipeline.make_callback("auth_sm")
        cb({"trigger_event": "test"})
        assert len(pipeline.get_recent(10)) == 1
        assert pipeline.get_recent(10)[0]["source"] == "auth_sm"

    def test_subscribers_notified(self, pipeline):
        received = []
        pipeline.subscribe(lambda r: received.append(r))
        pipeline.ingest({"event": "test"}, source="sub_test")
        assert len(received) == 1

    def test_get_recent(self, pipeline):
        for i in range(5):
            pipeline.ingest({"seq": i}, source="test")
        recent = pipeline.get_recent(3)
        assert len(recent) == 3
        # Most recent first
        assert recent[0]["record"]["seq"] == 4

    def test_get_reader(self, pipeline):
        pipeline.ingest({"event": "test"}, source="reader_test")
        reader = pipeline.get_reader()
        results = reader.query(limit=100)
        assert len(results) == 1

    def test_pipeline_status(self, pipeline):
        pipeline.ingest({"event": "x"}, source="test")
        status = pipeline.get_status()
        assert status["in_memory_buffer_size"] == 1
        assert status["writer"]["records_in_file"] == 1

    def test_integration_with_state_machines(self, pipeline):
        """Simulate callback from authorization + risk governor / 模拟状态机回调"""
        auth_cb = pipeline.make_callback("authorization_sm")
        risk_cb = pipeline.make_callback("risk_governor")

        auth_cb({"transition_id": "atx:001", "trigger_event_type": "authorization_approved"})
        auth_cb({"transition_id": "atx:002", "trigger_event_type": "authorization_restricted"})
        risk_cb({"transition_id": "rgt:001", "trigger_event": "drawdown_warning"})

        reader = pipeline.get_reader()
        all_records = reader.query(limit=100)
        assert len(all_records) == 3

        auth_records = reader.query(source="authorization_sm", limit=100)
        assert len(auth_records) == 2

        risk_records = reader.query(source="risk_governor", limit=100)
        assert len(risk_records) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Thread Safety / 线程安全测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestThreadSafety:
    def test_concurrent_writes(self, writer, reader):
        """Concurrent writes should not lose or corrupt records / 并发写入不应丢失或损坏"""
        errors = []
        writes_per_thread = 20

        def write_worker(thread_id):
            try:
                for i in range(writes_per_thread):
                    writer.write({"thread": thread_id, "seq": i}, source=f"thread_{thread_id}")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=write_worker, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0
        assert writer.total_records == 5 * writes_per_thread

        # Verify all records readable and valid
        all_records = reader.query(limit=200)
        assert len(all_records) == 100


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Edge Cases / 边界情况测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_nonexistent_base_dir_created(self):
        with tempfile.TemporaryDirectory() as parent:
            nested = os.path.join(parent, "deep", "nested", "audit")
            config = AuditPersistenceConfig(base_dir=nested, create_dirs=True)
            writer = AuditFileWriter(config)
            writer.write({"test": True}, source="test")
            writer.close()
            assert Path(nested).exists()

    def test_unicode_in_records(self, writer, reader):
        writer.write({"message": "授权状态机迁移：DRAFT → ACTIVE", "emoji": "✅"}, source="unicode")
        results = reader.query(limit=10)
        assert len(results) == 1
        assert "授权" in results[0]["record"]["message"]

    def test_empty_record(self, writer, reader):
        writer.write({}, source="empty")
        results = reader.query(limit=10)
        assert len(results) == 1

    def test_close_idempotent(self, writer):
        writer.write({"test": True}, source="test")
        writer.close()
        writer.close()  # Should not raise

    def test_count_by_date(self, writer, reader):
        for i in range(5):
            writer.write({"seq": i}, source="test")
        counts = reader.count_by_date()
        today = time.strftime("%Y-%m-%d", time.gmtime())
        assert counts.get(today, 0) == 5
