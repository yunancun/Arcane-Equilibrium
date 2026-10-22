"""依帳本唯讀授權切片 U1 資料；本版一律拒絕 holdout 物化。"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

from program_code.research.r8_ledger.ledger import ResearchLedger, LedgerError, canonical

P3B_MANIFEST_SHA256 = 'b6519a7b2f5eae4759612690790ddb6680db62aa4e723427f51c21a7d6257006'
TOOL_VERSION = 'r8-public-data-2'
DATA_START = '2020-01-01T00:00:00Z'
MIN_LOOKBACK_SECONDS = 13 * 86400
HOUR = 3600000
DAY = 24 * HOUR
HEADERS = {
    'kline': ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'],
    'funding': ['timestamp', 'funding_rate'],
    'open_interest': ['timestamp', 'open_interest'],
}
DATASETS = (('kline', '60'), ('kline', 'D'), ('open_interest', '4h'), ('funding', 'funding'))
TRAIN_END = 1751328000000
V2 = 'v2-terminal-suffix-20261022'
STANDARD_SHA256 = 'afcb87578676c998b4ce7529c6e1c09d5214cfe7e8af53ad03d120781c696931'
V1_STANDARDS = (STANDARD_SHA256, 'd0fbf9ff02d080027d575eb6488f2c552c3a583485b8c685166fe0ef94b2af98',
                'ba65fbca3b9230ad1807b82c923e9e60ab870edbe5c1e0d5090ebce99b06f6d0', '125901d0341487bd058be70e7cc2ed27be7c3be270a45d05587e471104b7cacf',
                'ad80220cd6dc3f8dc5c451c6281aa9f1b2acf7fbb47bc80ed21eb3905710110c')
# Reviewed deployment pins: (P3b SHA, readable start/end, symbols, verification.json SHA).
# No directory scan, caller policy selection, mutable latest, or unverified fallback.
VERIFICATION_BUNDLES = ((P3B_MANIFEST_SHA256, 1585094400000, 1607990400000,
                         ('BCHUSDT', 'BTCUSDT'),
                         '58fd0d224de878e42c78f0a0e1132683dbd0fc3fe9fc5e7d13c95a28d20258b0'),)
REF_KEYS = set('kind relative_path url sha256 row request_id list_index byte_start byte_end trade_id line_sha256'.split())
CORRECTION_KEYS = set('schema_version correction_id symbol dataset interval timestamp field original_value candidate_value corrected_value unit formula evidence_kind source_refs coverage_status order_status rule_ids decision reason_code row_action policy_sha256 approval_event supersedes'.split())
VERIFICATION_KEYS = set('schema_version status policy_sha256 p3b_manifest_sha256 sample_plan_sha256 previous_corrections_sha256 review_refs tool_commit readable counts files reason_codes'.split())
SEMANTIC_KEYS = set('schema_version policy_sha256 volume_semantics_policy symbol day_start timestamp hour_classification day_applicable original_volume trade_volume volume_delta volume_source tail_group_count tail_count tail_volume tail_first_timestamp tail_last_timestamp prefix_first_timestamp prefix_count source_refs reason_codes confidence_evidence'.split())
HOUR_CLASSIFICATIONS = set('STRICT_C3 TERMINAL_SUFFIX_EXACT PARTIAL_SUBSET_UNDETERMINED PARTIAL_TIMESTAMP_SUBSET NO_COMPLETE_SUFFIX POSITIVE_VOLUME_DELTA MISSING_ORIGINAL_HOUR IDENTITY_UNCERTAIN OUT_OF_SCOPE C1_INVALID C2_CONFLICT EMPTY_PREFIX'.split())


def _fail(reason):
    raise MaterializationError(reason)


def _encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail('DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def _json(raw):
    value = json.loads(raw, object_pairs_hook=_pairs, parse_float=lambda _: _fail('JSON_FLOAT_DENIED'),
                       parse_constant=lambda _: _fail('INVALID_NUMBER'))
    if _encoded(value) != raw:
        _fail('NONCANONICAL_JSON')
    return value


def _keys(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        _fail('SCHEMA_FIELDS')


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        _fail('INVALID_SHA256')
    return value


def _number(value):
    if not isinstance(value, str) or value.strip() != value or '_' in value:
        _fail('INVALID_NUMBER')
    return Fraction(Decimal(_decimal(value)))


def _text(value):
    if value is None:
        return None
    n, d = Fraction(value).as_integer_ratio()
    sign, n = ('-' if n < 0 else ''), abs(n)
    a = b = 0
    while d % 2 == 0:
        d //= 2; a += 1
    while d % 5 == 0:
        d //= 5; b += 1
    if d != 1:
        _fail('NONTERMINATING_OUTPUT_DECIMAL')
    scale = max(a, b)
    digits = str(n * 2**(scale-a) * 5**(scale-b)).zfill(scale+1)
    return sign+((digits[:-scale]+'.'+digits[-scale:]).rstrip('0').rstrip('.') if scale else digits)


def _ref_sort(ref):
    return tuple(ref[k] if ref[k] is not None else default for k, default in
                 [('kind', ''), ('relative_path', ''), ('row', -1), ('list_index', -1), ('byte_start', -1)])


def _refs(refs):
    return sorted({canonical(ref): ref for ref in refs}.values(), key=_ref_sort)


def _strings(value, *, nonempty=False):
    if not isinstance(value, list) or any(not isinstance(x, str) or not x for x in value) or value != sorted(set(value)) or nonempty and not value:
        _fail('STRING_ARRAY')


def _details(value):
    if not isinstance(value, list):
        _fail('DETAILS_SCHEMA')
    names = []
    for item in value:
        _keys(item, {'name', 'value'})
        if not isinstance(item['name'], str) or not item['name'] or item['value'] is not None and not isinstance(item['value'], str):
            _fail('DETAILS_SCHEMA')
        names.append(item['name'])
    if names != sorted(set(names)):
        _fail('DETAILS_ORDER')


def _csv_ref(filename, sha, row, line):
    ref = dict.fromkeys(REF_KEYS)
    ref.update(kind='csv', relative_path=filename, sha256=sha, row=row, line_sha256=_digest(line))
    return ref


def _safe_path(root, name):
    if not isinstance(name, str) or not name or '\\' in name or name.startswith('/') or any(p in ('', '.', '..') for p in name.split('/')):
        _fail('UNSAFE_PATH')
    path = root
    for part in name.split('/'):
        path = path/part
        if path.is_symlink():
            _fail('SYMLINK_DENIED')
    return path


class _Bundle:
    """Authenticate the fixed producer bundle before any scoped market decoding."""
    def __init__(self, root, manifest_sha, start, end, symbols):
        self.raw = {}
        self.source_root, self.manifest_sha = root, manifest_sha
        self.start, self.end, self.symbols = start, end, symbols
        matches = [p for p in VERIFICATION_BUNDLES if p[0] == manifest_sha and
                   (p[1], p[2]) == (start, end) and set(symbols) == set(p[3])]
        if len(matches) != 1:
            _fail('BUNDLE_PIN_NOT_UNIQUE')
        pin = matches[0]
        self.bundle_sha = pin[4]
        self.root = _safe_path(root.parent, 'verification-bundles/'+_sha(pin[4]))
        raw = _source_bytes(self.root, 'verification.json', pin[4])
        report = _json(raw)
        self.version = {'r8_data_verification_v1': 1, 'r8_data_verification_v2': 2}.get(report.get('schema_version'))
        if self.version is None:
            _fail('VERIFICATION_SCHEMA_VERSION')
        _keys(report, VERIFICATION_KEYS | ({'standard_sha256', 'volume_semantics_policy'} if self.version == 2 else set()))
        _keys(report['counts'], {'input_rows', 'checked_days', 'flagged_days', 'corrected_fields', 'unresolved_rows'})
        if any(type(n) is not int or n < 0 for n in report['counts'].values()):
            _fail('VERIFICATION_COUNTS')
        if not isinstance(report['tool_commit'], str) or not re.fullmatch('[0-9a-f]{40}', report['tool_commit']):
            _fail('TOOL_COMMIT')
        for key in ('policy_sha256', 'p3b_manifest_sha256', 'sample_plan_sha256', 'previous_corrections_sha256'):
            if report[key] is not None:
                _sha(report[key])
        _strings(report['reason_codes'])
        if report['p3b_manifest_sha256'] != manifest_sha or report['readable'] != {'start': pin[1], 'end': pin[2]}:
            _fail('BUNDLE_SCOPE_IDENTITY')
        if not _timestamp(DATA_START) <= pin[1] < pin[2] <= TRAIN_END:
            _fail('BUNDLE_OUTSIDE_TRAINING')
        if report['status'] != 'READY':
            _fail('VERIFICATION_BLOCKED')
        self.report, self.raw = report, {'verification.json': raw}
        required = {'policy.json', 'corrections.jsonl', 'findings.jsonl'} | ({'volume_semantics.jsonl'} if self.version == 2 else set())
        if not required <= set(report['files']) or set(report['files']) - required - {'sample_plan.json', 'sample_report.txt'}:
            _fail('BUNDLE_FILES')
        for name, meta in report['files'].items():
            _keys(meta, {'sha256', 'rows'})
            data = _source_bytes(self.root, name, _sha(meta['sha256']))
            if type(meta['rows']) is not int or meta['rows'] != len(data.splitlines()):
                _fail('BUNDLE_ROW_COUNT')
            self.raw[name] = data
        self.policy = _json(self.raw['policy.json'])
        self.policy_sha = _digest(self.raw['policy.json'])
        template = _json(Path(__file__).with_name('data_verification_policy.json').read_bytes())
        template['p3b_manifest_sha256'] = manifest_sha
        if self.version == 1:
            template.pop('volume_semantics_policy')
            template.update(schema_version='r8_data_verification_policy_v1', approval_event='RH-20261022-04')
            if self.policy.get('standard_sha256') not in V1_STANDARDS:
                _fail('POLICY_STANDARD')
            template['standard_sha256'] = self.policy['standard_sha256']
        if self.policy != template or report['policy_sha256'] != self.policy_sha:
            _fail('POLICY_MISMATCH')
        if self.version == 2 and (report['volume_semantics_policy'] != V2 or report['standard_sha256'] != STANDARD_SHA256):
            _fail('POLICY_MISMATCH')
        self.valid_policy = self.raw['policy.json']
        self._sample_plan()
        self.start, self.end, self.symbols = start, end, symbols
        self.source_root, self.verified_refs = root, set()
        self.check_refs(report['review_refs'])
        self.corrections = self._corrections()
        self.findings = self._findings()
        self.semantics = self._semantics() if self.version == 2 else []

    def _sample_plan(self):
        raw = self.raw.get('sample_plan.json')
        if self.report['sample_plan_sha256'] != (_digest(raw) if raw is not None else None):
            _fail('SAMPLE_PLAN_DIGEST')
        if raw is None:
            if 'sample_report.txt' in self.raw:
                _fail('SAMPLE_REPORT_WITHOUT_PLAN')
            return
        plan = _json(raw)
        expected_keys = {'schema_version', 'policy_sha256', 'p3b_manifest_sha256', 'readable', 'seed', 'strata'}
        if not isinstance(plan, dict) or set(plan) != expected_keys:
            _fail('SAMPLE_PLAN_SCHEMA')
        if (plan['schema_version'] != 'r8_verification_sample_plan_v1' or plan['seed'] != 20261022
                or plan['readable'] != self.report['readable'] or plan['p3b_manifest_sha256'] != self.manifest_sha):
            _fail('SAMPLE_PLAN_IDENTITY')
        accepted = {self.policy_sha} if self.version == 1 else set()
        if self.version == 2:
            original = dict(self.policy)
            original.pop('volume_semantics_policy')
            original.update(schema_version='r8_data_verification_policy_v1', approval_event='RH-20261022-04')
            for standard in V1_STANDARDS:
                original['standard_sha256'] = standard
                accepted.add(_digest(_encoded(original)))
        if plan['policy_sha256'] not in accepted:
            _fail('SAMPLE_PLAN_POLICY')
        tiers = ('GE_100M', 'GE_10M', 'GE_1M', 'NO_OPEN')
        if not isinstance(plan['strata'], list):
            _fail('SAMPLE_PLAN_STRATA')
        order, seen = [], set()
        for stratum in plan['strata']:
            if not isinstance(stratum, dict) or set(stratum) != {'year','tier','population_size','base_size','max_size','draws'}:
                _fail('SAMPLE_PLAN_STRATUM_SCHEMA')
            if any(type(stratum[k]) is not int or stratum[k] < 0 for k in ('year','population_size','base_size','max_size')) or stratum['tier'] not in tiers:
                _fail('SAMPLE_PLAN_STRATUM_TYPE')
            population = stratum['population_size']
            if (stratum['base_size'] != min(300, population) or stratum['max_size'] != min(900, population)
                    or not isinstance(stratum['draws'], list) or len(stratum['draws']) != stratum['max_size']):
                _fail('SAMPLE_PLAN_SAMPLE_SIZE')
            order.append((stratum['year'], tiers.index(stratum['tier'])))
            for rank, draw in enumerate(stratum['draws'], 1):
                if not isinstance(draw, dict) or set(draw) != {'rank','symbol','day_start'}:
                    _fail('SAMPLE_PLAN_DRAW_SCHEMA')
                if type(draw['rank']) is not int or draw['rank'] != rank or type(draw['day_start']) is not int:
                    _fail('SAMPLE_PLAN_RANK')
                day = draw['day_start']
                if draw['symbol'] not in self.symbols or day % DAY or not self.start <= day < day+DAY <= self.end or _date(day).year != stratum['year']:
                    _fail('SAMPLE_PLAN_DRAW_SCOPE')
                key = (draw['symbol'], day)
                if key in seen:
                    _fail('SAMPLE_PLAN_DUPLICATE_DRAW')
                seen.add(key)
        if order != sorted(set(order)):
            _fail('SAMPLE_PLAN_STRATUM_ORDER')
        if 'sample_report.txt' in self.raw:
            lines = self.raw['sample_report.txt'].splitlines()
            if lines[:2] != [('sample_plan_sha256='+_digest(raw)).encode(), b'base denominator only; expansion is diagnostic']:
                _fail('SAMPLE_REPORT_IDENTITY')

    def scoped(self, name):
        selected = []
        for line in self.raw[name].splitlines(keepends=True):
            # Extract routing metadata only. Never JSON-decode an out-of-scope market value.
            t = re.search(rb'"timestamp":(null|[0-9]+)(?:,|})', line)
            s = re.search(rb'"symbol":"([A-Z0-9]+)"', line)
            if t is None or s is None:
                _fail('BUNDLE_ROUTING_IDENTITY')
            if t[1] == b'null':
                _fail('UNROUTABLE_TIMESTAMP')
            if s[1].decode('ascii') not in self.symbols or not self.start <= int(t[1]) < self.end:
                _fail('BUNDLE_SCOPE_ESCAPE')
            selected.append(_json(line))
        return selected

    def check_refs(self, refs):
        if not isinstance(refs, list):
            _fail('SOURCE_REF_ORDER')
        for ref in refs:
            _keys(ref, REF_KEYS)
            if ref['kind'] not in ('raw', 'csv', 'trade', 'instruments', 'policy', 'plan', 'report'):
                _fail('SOURCE_REF_KIND')
            for key in ('url', 'request_id', 'trade_id'):
                if ref[key] is not None and not isinstance(ref[key], str):
                    _fail('SOURCE_REF_TYPE')
            for key in ('row', 'list_index', 'byte_start', 'byte_end'):
                if ref[key] is not None and (type(ref[key]) is not int or ref[key] < (1 if key == 'row' else 0)):
                    _fail('SOURCE_REF_TYPE')
            if ref['line_sha256'] is not None:
                _sha(ref['line_sha256'])
            if ref['relative_path'] is None:
                if ref['sha256'] is not None:
                    _fail('SOURCE_REF_IDENTITY')
                continue
            identity = (ref['relative_path'], _sha(ref['sha256']))
            if identity in self.verified_refs:
                continue
            base = self.source_root if _safe_path(self.source_root, ref['relative_path']).is_file() else self.root
            _source_bytes(base, *identity)
            self.verified_refs.add(identity)
        if refs != _refs(refs):
            _fail('SOURCE_REF_ORDER')

    def _corrections(self):
        result, ids = {}, {}
        rows = self.scoped('corrections.jsonl')
        if rows != sorted(rows, key=lambda c: (c['timestamp'], c['symbol'], c['dataset'], c['interval'], c['field'], c['correction_id'])):
            _fail('CORRECTION_ORDER')
        for c in rows:
            _keys(c, CORRECTION_KEYS | ({'volume_semantics_policy', 'volume_source', 'reason_codes'} if self.version == 2 else set()))
            if c['schema_version'] != f'r8_data_correction_v{self.version}' or c['policy_sha256'] != self.policy_sha or c['approval_event'] != self.policy['approval_event']:
                _fail('CORRECTION_POLICY')
            if c['interval'] not in ('60', 'D', '1') or c['dataset'] != {'60':'kline_hour', 'D':'kline_day', '1':'kline_minute'}[c['interval']] or c['field'] not in HEADERS['kline'][1:]:
                _fail('CORRECTION_IDENTITY')
            if c['decision'] not in ('KEEP', 'CORRECT', 'UNRESOLVED') or c['row_action'] not in ('include', 'missing'):
                _fail('CORRECTION_DECISION')
            if c['coverage_status'] not in ('PASS', 'CONFLICT', 'UNAVAILABLE', 'NOT_APPLICABLE') or c['order_status'] not in ('UNIQUE', 'TIMESTAMP_MULTI_PRICE', 'UNAVAILABLE', 'NOT_APPLICABLE'):
                _fail('CORRECTION_GATE')
            if c['evidence_kind'] not in ('trade_adjudication', 'reported_turnover_selection') or not c['source_refs']:
                _fail('MISSING_EVIDENCE')
            _strings(c['rule_ids'], nonempty=True)
            for key in ('unit', 'formula', 'reason_code'):
                if not isinstance(c[key], str) or not c[key]:
                    _fail('CORRECTION_TYPE')
            for key in ('original_value', 'candidate_value', 'corrected_value'):
                if c[key] is not None and not isinstance(c[key], str):
                    _fail('CORRECTION_TYPE')
            if c['decision'] == 'CORRECT':
                if c['corrected_value'] != _text(_number(c['corrected_value'])):
                    _fail('CORRECTION_VALUE')
            elif c['corrected_value'] is not None:
                _fail('CORRECTION_VALUE')
            if c['decision'] == 'UNRESOLVED' and c['row_action'] != 'missing':
                _fail('UNRESOLVED_INCLUDED')
            if self.version == 2:
                _strings(c['reason_codes'])
                if c['volume_semantics_policy'] != V2 or c['volume_source'] not in (None, 'v1_strict', 'trade_reconstructed_terminal_suffix') or c['field'] != 'volume' and c['volume_source'] is not None:
                    _fail('CORRECTION_VOLUME_POLICY')
            self.check_refs(c['source_refs'])
            key = (c['symbol'], c['interval'], c['timestamp'], c['field'])
            if key in result or c['correction_id'] in ids:
                _fail('CORRECTION_CONFLICT')
            result[key] = c; ids[c['correction_id']] = c
        for c in rows:
            seen, previous = {c['correction_id']}, c['supersedes']
            while previous in ids:
                if previous in seen:
                    _fail('SUPERSEDES_CYCLE')
                seen.add(previous); previous = ids[previous]['supersedes']
            if _digest(_encoded({k:v for k,v in c.items() if k != 'correction_id'})) != c['correction_id']:
                _fail('CORRECTION_ID_MISMATCH')
        return result

    def _findings(self):
        keys = set('schema_version finding_id symbol dataset interval timestamp field rule_id reason_code source_refs details'.split())
        rows = self.scoped('findings.jsonl')
        for row in rows:
            _keys(row, keys)
            if row['schema_version'] != 'r8_data_finding_v1':
                _fail('FINDING_SCHEMA')
            for key in ('field', 'rule_id', 'reason_code'):
                if not isinstance(row[key], str) or not row[key]:
                    _fail('FINDING_TYPE')
            _details(row['details']); self.check_refs(row['source_refs'])
            if _digest(_encoded({k:v for k,v in row.items() if k != 'finding_id'})) != row['finding_id']:
                _fail('FINDING_ID')
        if rows != sorted(rows, key=lambda r:(r['timestamp'], r['symbol'], r['dataset'], r['interval'], r['field'], r['finding_id'])):
            _fail('FINDING_ORDER')
        return rows

    def _semantics(self):
        rows = self.scoped('volume_semantics.jsonl')
        if rows != sorted(rows, key=lambda r:(r['day_start'], r['symbol'], r['timestamp'])):
            _fail('VOLUME_SEMANTICS_ORDER')
        seen = set()
        for row in rows:
            _keys(row, SEMANTIC_KEYS)
            key = (row['symbol'], row['timestamp'])
            if key in seen:
                _fail('VOLUME_SEMANTICS_CONFLICT')
            seen.add(key)
            if row['schema_version'] != 'r8_volume_semantics_v2' or row['policy_sha256'] != self.policy_sha or row['volume_semantics_policy'] != V2:
                _fail('VOLUME_SEMANTICS_POLICY')
            if row['hour_classification'] not in HOUR_CLASSIFICATIONS or type(row['day_applicable']) is not bool:
                _fail('VOLUME_SEMANTICS_CLASSIFICATION')
            if type(row['day_start']) is not int or row['day_start'] != row['timestamp']//DAY*DAY or row['timestamp'] % HOUR:
                _fail('VOLUME_SEMANTICS_TIME')
            for key in ('original_volume', 'trade_volume', 'volume_delta', 'tail_volume', 'tail_first_timestamp', 'tail_last_timestamp', 'prefix_first_timestamp'):
                if row[key] is not None and (not isinstance(row[key], str) or row[key] != _text(_number(row[key]))):
                    _fail('VOLUME_SEMANTICS_NUMBER')
            for key in ('tail_group_count', 'tail_count', 'prefix_count'):
                if row[key] is not None and (type(row[key]) is not int or row[key] < 0):
                    _fail('VOLUME_SEMANTICS_COUNT')
            _strings(row['reason_codes'])
            if row['volume_source'] not in (None, 'v1_strict', 'trade_reconstructed_terminal_suffix'):
                _fail('VOLUME_SEMANTICS_SOURCE')
            self.check_refs(row['source_refs'])
            _keys(row['confidence_evidence'], {'prefix_hlc', 'tail_minute', 'next_hour_open'})
            for evidence in row['confidence_evidence'].values():
                _keys(evidence, {'status', 'source_refs', 'details'})
                if evidence['status'] not in ('SUPPORTS', 'CONTRADICTS', 'UNAVAILABLE', 'AMBIGUOUS'):
                    _fail('VOLUME_CONFIDENCE_STATUS')
                self.check_refs(evidence['source_refs'])
                _details(evidence['details'])
            if all(row[k] is not None for k in ('original_volume', 'trade_volume', 'volume_delta')):
                if _number(row['original_volume'])-_number(row['trade_volume']) != _number(row['volume_delta']):
                    _fail('VOLUME_DELTA_MISMATCH')
        days = {}
        for row in rows:
            days.setdefault((row['symbol'], row['day_start']), []).append(row)
        for (symbol, day), group in days.items():
            applicable = group[0]['day_applicable']
            if any(r['day_applicable'] != applicable for r in group):
                _fail('VOLUME_DAY_APPLICABILITY_CONFLICT')
            if applicable:
                if (not any(r['hour_classification'] == 'TERMINAL_SUFFIX_EXACT' for r in group)
                        or any(r['hour_classification'] not in ('STRICT_C3', 'TERMINAL_SUFFIX_EXACT') for r in group)):
                    _fail('VOLUME_DAY_NOT_APPLICABLE')
                for row in group:
                    expected = 'v1_strict' if row['hour_classification'] == 'STRICT_C3' else 'trade_reconstructed_terminal_suffix'
                    if row['volume_source'] != expected:
                        _fail('VOLUME_FIXED_SOURCE_MISMATCH')
                    correction = self.corrections.get((symbol, '60', row['timestamp'], 'volume'))
                    self._selected_volume(correction, expected, _number(row['trade_volume']))
                self._selected_volume(self.corrections.get((symbol, 'D', day, 'volume')),
                                      'trade_reconstructed_terminal_suffix',
                                      sum((_number(r['trade_volume']) for r in group), Fraction()))
            elif any(r['volume_source'] == 'trade_reconstructed_terminal_suffix' for r in group):
                _fail('VOLUME_UNAPPROVED_SOURCE')
        return rows

    @staticmethod
    def _selected_volume(correction, source, expected):
        if correction is None:
            _fail('VOLUME_CORRECTION_MISSING')
        if correction['decision'] != 'UNRESOLVED':
            value = correction['corrected_value'] if correction['decision'] == 'CORRECT' else correction['original_value']
            if correction['volume_source'] != source or _number(value) != expected:
                _fail('VOLUME_FIXED_SOURCE_MISMATCH')

    def binding(self, book, hypothesis):
        with book._lock():
            registration = book._registration(hypothesis)
        record = registration['record']
        if record.get('data_family') not in ('ordinary', 'listing'):
            _fail('BINDING_DATA_FAMILY')
        policy = record.get('data_policy_sha256')
        if not isinstance(policy, str) or not re.fullmatch('[0-9a-f]{64}', policy) or policy != self.policy_sha:
            _fail('BINDING_DATA_POLICY_SHA256')
        return dict(schema_version='r8_verification_hypothesis_binding_v1', hypothesis_id=hypothesis,
                    family=record['data_family'], policy_sha256=policy, registration_sha256=registration['record_sha256'])

    def blocked(self, out, reason):
        # Failure evidence is separate from the atomic, usable materialization.
        path = out.with_name(out.name+'.blocked')
        if path.exists():
            return  # Keep the first failure immutable; a retry needs a new output identity.
        path.mkdir(exist_ok=False)
        policy = _json(Path(__file__).with_name('data_verification_policy.json').read_bytes())
        policy['p3b_manifest_sha256'] = self.manifest_sha
        if getattr(self, 'version', 2) == 1:
            policy.pop('volume_semantics_policy')
            policy.update(schema_version='r8_data_verification_policy_v1', approval_event='RH-20261022-04')
        # Retain only validated, scoped candidates here. The immutable input
        # bundle stays in place; its byte digests identify any rejected input.
        raw = {'policy.json':getattr(self, 'valid_policy', _encoded(policy)),
               'corrections.jsonl':b''.join(_encoded(c) for c in getattr(self, 'corrections', {}).values()),
               'findings.jsonl':b''.join(_encoded(f) for f in getattr(self, 'findings', [])),
               'volume_semantics.jsonl':b''.join(_encoded(r) for r in getattr(self, 'semantics', []))}
        details = {f'input_{name}_sha256':_digest(data) for name,data in self.raw.items()}
        if hasattr(self, 'bundle_sha'):
            details['verification_bundle_sha256'] = self.bundle_sha
        if not re.fullmatch('[A-Z][A-Z0-9_]*', reason):
            details['failure_message'] = reason
            reason = 'U4_MATERIALIZATION_REJECTED'
        ref = dict.fromkeys(REF_KEYS)
        ref.update(kind='policy', relative_path='policy.json', sha256=_digest(raw['policy.json']))
        if self.symbols:
            finding = dict(schema_version='r8_data_finding_v1', symbol=self.symbols[0], dataset='kline_day',
                           interval='D', timestamp=None, field='row', rule_id='DV-U4', reason_code=reason,
                           source_refs=[ref], details=[{'name':k,'value':v} for k,v in sorted(details.items())])
            finding['finding_id'] = _digest(_encoded(finding))
            # A null timestamp sorts before all dated producer findings.
            raw['findings.jsonl'] = _encoded(finding)+raw['findings.jsonl']
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=Path(__file__).resolve().parents[3], text=True).strip()
        report = dict(schema_version='r8_data_verification_v2', status='BLOCKED',
            policy_sha256=_digest(raw['policy.json']), p3b_manifest_sha256=self.manifest_sha,
            sample_plan_sha256=_digest(raw['sample_plan.json']) if 'sample_plan.json' in raw else None,
            previous_corrections_sha256=None, review_refs=[], tool_commit=commit,
            readable={'start':self.start, 'end':self.end},
            counts=dict.fromkeys(('input_rows','checked_days','flagged_days','corrected_fields','unresolved_rows'),0),
            files={k:{'sha256':_digest(v),'rows':len(v.splitlines())} for k,v in raw.items()}, reason_codes=[reason],
            standard_sha256=STANDARD_SHA256, volume_semantics_policy=V2)
        if getattr(self, 'version', 2) == 1:
            report.update(schema_version='r8_data_verification_v1')
            report.pop('standard_sha256'); report.pop('volume_semantics_policy')
            if not raw['volume_semantics.jsonl']:
                raw.pop('volume_semantics.jsonl'); report['files'].pop('volume_semantics.jsonl')
        for name, data in raw.items():
            (path/name).write_bytes(data)
        (path/'verification.json').write_bytes(_encoded(report))


class MaterializationError(ValueError):
    """來源、可讀範圍或輸出不符合物化契約。"""


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _integer(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not re.fullmatch(r'[0-9]+', str(value)):
        raise MaterializationError('時間戳或間隔須為非負整數')
    return int(value)


def _timestamp(value):
    if type(value) is int:
        return value
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is None or dt.utcoffset() != timedelta(0) or dt.microsecond % 1000:
            raise ValueError()
        delta = dt - datetime(1970, 1, 1, tzinfo=timezone.utc)
        return (delta.days * 86400 + delta.seconds) * 1000 + delta.microseconds // 1000
    except (ValueError, TypeError, AttributeError) as exc:
        raise MaterializationError('時間須為 UTC ISO8601，最多毫秒精度') from exc


def _date(stamp):
    return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=stamp)


def _window(value):
    if isinstance(value, str):
        parts = value.split(',')
        if len(parts) != 2:
            raise MaterializationError('window 須為起點,終點')
        value = dict(zip(('start', 'end'), parts))
    if not isinstance(value, dict) or set(value) != {'start', 'end'}:
        raise MaterializationError('window 須有 start 與 end')
    start, end = _timestamp(value['start']), _timestamp(value['end'])
    if start >= end:
        raise MaterializationError('視窗須為非空遞增區間')
    return start, end


def _decimal(value, *, positive=False, nonnegative=False):
    try:
        if not isinstance(value, str) or not value.strip():
            raise InvalidOperation()
        number = Decimal(value)
        if not number.is_finite() or positive and number <= 0 or nonnegative and number < 0:
            raise InvalidOperation()
        return format(number, 'f')
    except (InvalidOperation, ValueError) as exc:
        raise MaterializationError('數值缺失、非有限或不符合正負限制') from exc


def _source_bytes(root, relative, expected):
    path = _safe_path(root, relative)
    if not path.resolve().is_relative_to(root) or not path.is_file():
        raise MaterializationError('來源檔案不存在或越出 U1 目錄')
    raw = path.read_bytes()
    if _digest(raw) != expected:
        raise MaterializationError('來源雜湊不符: ' + relative)
    return raw


def _market_rows(raw, meta, filename, start, end, bundle):
    """One overlay feeds source, LEAN, and custom. Original byte slices stay separate."""
    lines = gzip.decompress(raw).splitlines(keepends=True)
    if not lines or next(csv.reader([lines[0].decode()])) != HEADERS['kline']:
        _fail('CSV_HEADER')
    original, effective, rows, originals, refs, missing = [lines[0]], [lines[0]], [], {}, {}, []
    period = HOUR if meta['interval'] == '60' else DAY
    used, previous = set(), None
    for line_number, line in enumerate(lines[1:], 2):
        t = _integer(line.split(b',', 1)[0].decode('ascii'))
        if not start <= t < end:
            continue
        corrections = [bundle.corrections.get((meta['symbol'], meta['interval'], t, f)) for f in HEADERS['kline'][1:]]
        if t+period > end:
            # A producer scope quarantine has no decoded market fields. Preserve
            # its identity, not the future close/high/low embedded in this line.
            ref = _csv_ref(filename, meta['sha256'], line_number, line)
            if any(c is None or c['row_action'] != 'missing' or c['original_value'] is not None or ref not in c['source_refs'] for c in corrections):
                _fail('UNCLOSED_BAR_NOT_QUARANTINED')
            used.update((meta['symbol'], meta['interval'], t, f) for f in HEADERS['kline'][1:])
            missing.append((t, end))
            continue
        original.append(line)
        fields = next(csv.reader([line.decode()]))
        if len(fields) != 7:
            _fail('CSV_ROW_SCHEMA')
        origin_ref = _csv_ref(filename, meta['sha256'], line_number, line)
        values = fields[1:]
        original_values = values[:]
        discard = any(c and c['row_action'] == 'missing' for c in corrections)
        for i, c in enumerate(corrections):
            if c is None:
                continue
            if origin_ref not in c['source_refs'] or (c['original_value'] != values[i] and c['reason_code'] != 'DUPLICATE_KEY'):
                _fail('CORRECTION_ORIGINAL_MISMATCH')
            used.add((meta['symbol'], meta['interval'], t, HEADERS['kline'][i+1]))
            if c['decision'] == 'CORRECT':
                values[i] = c['corrected_value']
        if previous is not None and t < previous:
            _fail('UNSORTED_SOURCE')
        if t in originals and not discard:
            _fail('DUPLICATE_SOURCE')
        previous = t
        originals[t] = None if t in originals else original_values
        refs.setdefault(t, []).append(origin_ref)
        if discard:
            missing.append((t, min(t+period, end)))
            continue
        if t % period or t+period > end:
            _fail('UNCLOSED_OR_OFF_GRID_BAR')
        nums = [_number(v) for v in values]
        o, h, l, c, v, a = nums
        if min(o, h, l, c) <= 0 or min(v, a) < 0 or l > min(o, c) or h < max(o, c) or l > h:
            _fail('EFFECTIVE_L1_FAILED')
        rows.append((t, [_text(n) for n in nums]))
        effective.append(_csv([[fields[0], *values]]))
    for key, correction in bundle.corrections.items():
        if key[:2] == (meta['symbol'], meta['interval']) and key not in used:
            if correction['original_value'] is not None or correction['row_action'] != 'missing':
                _fail('CORRECTION_SOURCE_ROW_MISSING')
            missing.append((key[2], min(key[2]+period, end)))
    return rows, b''.join(effective), b''.join(original), originals, refs, missing


def _merged_gaps(intervals, period):
    merged = []
    for a, b in sorted(set(intervals)):
        if a >= b:
            continue
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(b, merged[-1][1])
        else:
            merged.append([a, b])
    return [{'start': a, 'end_exclusive': b, 'count': (b-a+period-1)//period} for a, b in merged]


def _median(values):
    values = sorted(values)
    n = len(values)
    return values[n//2] if n % 2 else (values[n//2-1]+values[n//2])/2


def _tier(value):
    return next((name for n, name in [(100000000, 'GE_100M'), (10000000, 'GE_10M'), (1000000, 'GE_1M')] if value >= n), 'NO_OPEN')


def _quantity(day, first, hours, refs):
    begin = max(day, first)
    expected = list(range(begin, day+DAY, HOUR))
    full = all(t in hours for t in expected)
    total = sum((_number(hours[t][4]) for t in expected), Fraction()) if full else None
    record = dict(day_start=day, volume_sum=_text(total), hour_count=len(expected),
                  status=('FULL' if len(expected) == 24 else 'PARTIAL') if full else 'MISSING',
                  source_refs=_refs([r for t in expected for r in refs.get(t, [])]))
    return record, total/len(expected) if full and expected else None


def _listing(symbol, first, launch, origin_refs, hours, daily, hour_refs, end, policy_sha):
    origin_day = first//DAY*DAY
    records, quantities, q = [], [], []
    stage, reason = 'initial', 'OBSERVED_FIRST_HOUR'
    def record(day, known, cooling):
        records.append(dict(schema_version='r8_listing_regime_v1', symbol=symbol, day_start=day,
            known_at=known, observed_listing_at=first, launch_time=launch,
            listing_time_mismatch=abs(first-launch) > DAY, origin_refs=origin_refs,
            stage=stage, reason_code=reason, cooling=cooling, quantity_inputs=quantities[-14:], policy_sha256=policy_sha))
    if first+HOUR <= end:
        record(origin_day, first+HOUR, None)
    for day in range(origin_day, end-DAY+1, DAY):
        quantity, value = _quantity(day, first, hours, hour_refs)
        quantities.append(quantity); q.append(value)
        age = len(q)
        reason = 'STAGE_CONTINUES'
        if stage == 'initial':
            valid = all(x is not None for x in q)
            early = valid and max(q) > 0 and q[-1]*2 <= max(q)
            if age >= 3 or early:
                stage, reason = 'middle', 'INITIAL_MAX_DAY' if age >= 3 and not early else 'INITIAL_PEAK_RATIO'
        elif stage == 'middle' and age >= 7:
            valid = all(x is not None for x in q[-7:])
            mean7 = sum(q[-7:])/7 if valid else 0
            early = valid and mean7 > 0 and abs(sum(q[-3:])/3-mean7)*5 <= mean7
            if age >= 15 or early:
                stage, reason = 'stabilizing', 'MIDDLE_MAX_DAY' if age >= 15 and not early else 'MIDDLE_MEAN_CONVERGENCE'
        elif stage == 'stabilizing' and age >= 15:
            valid = len(q) >= 14 and all(x is not None for x in q[-14:])
            med14 = _median(q[-14:]) if valid else 0
            early = valid and med14 > 0 and abs(_median(q[-7:])-med14)*5 <= med14 and day+DAY >= ((first+DAY-1)//DAY+12)*DAY
            if age >= 30 or early:
                stage, reason = 'ordinary', 'STABILIZING_MAX_DAY' if age >= 30 and not early else 'STABILIZING_MEDIAN_CONVERGENCE'
        days = list(range(day-6*DAY, day+DAY, DAY))
        cooling = (all(_number(daily[t][5]) < 1000000 for t in days)
                   if all(t >= first and t in daily for t in days) else None)
        record(day+DAY, day+DAY, cooling)
    return records


def _turnover(symbol, first, start, end, original_daily, daily, hours, daily_refs, hour_refs, policy_sha, *, history_first=None):
    records = []
    history_first = first if history_first is None else history_first
    for decision_day in range((start+DAY-1)//DAY*DAY, end, DAY):
        inputs, d_values, e_values, h_values, reasons = [], [], [], [], set()
        sufficient = decision_day >= ((history_first+DAY-1)//DAY+12)*DAY
        for day in range(decision_day-12*DAY, decision_day, DAY):
            original = original_daily.get(day)
            effective = daily.get(day)
            original_amount = None
            if original is not None and day >= first:
                try:
                    amount = _number(original[5])
                    if amount >= 0:
                        original_amount = original[5]
                except (MaterializationError, InvalidOperation):
                    pass
            effective_amount = effective[5] if effective is not None and day >= first else None
            inputs.append(dict(day_start=day, exchange_reported=original_amount, effective_reported=effective_amount,
                sum_hourly_reported=None, daily_status='VALID' if effective_amount is not None else 'MISSING',
                hourly_status='NOT_EVALUATED', source_refs=_refs(daily_refs.get(day, []))))
            d_values.append(_number(original_amount) if original_amount is not None else Fraction())
            e_values.append(_number(effective_amount) if effective_amount is not None else Fraction())
            if effective_amount is None:
                reasons.add('DAILY_INPUT_MISSING')
        m_d, m_e = _median(d_values), _median(e_values)
        triggered = any(abs(m_e-t)*20 <= t for t in (1000000, 10000000, 100000000))
        if triggered:
            reasons.add('THRESHOLD_BAND')
            for item in inputs:
                day = item['day_start']; grid = list(range(day, day+DAY, HOUR))
                complete = day >= first and all(t in hours for t in grid)
                total = sum((_number(hours[t][5]) for t in grid), Fraction()) if complete else None
                item.update(sum_hourly_reported=_text(total), hourly_status='VALID' if complete else 'MISSING',
                            source_refs=_refs(item['source_refs']+[r for t in grid for r in hour_refs.get(t, [])]))
                h_values.append(total if total is not None else Fraction())
                if total is None:
                    reasons.add('TURNOVER_INPUT_INCOMPLETE')
        m_h = _median(h_values) if triggered else None
        td, te, th = _tier(m_d), _tier(m_e), _tier(m_h) if triggered else None
        selected_source, selected = 'effective_daily', m_e
        if triggered and th != te:
            selected_source, selected = 'hourly_sum', m_h
            reasons.add('EFFECTIVE_HOURLY_TIER_DIFFERENCE')
        if triggered and td != th:
            reasons.add('ORIGINAL_HOURLY_TIER_DIFFERENCE')
        if not sufficient:
            reasons.add('HISTORY_INSUFFICIENT')
        records.append(dict(schema_version='r8_turnover_decision_v1', symbol=symbol,
            decision_utc_day=decision_day, known_at=decision_day, policy_sha256=policy_sha,
            history_sufficient=sufficient, inputs=inputs, m_d=_text(m_d), m_e=_text(m_e), m_h=_text(m_h),
            tier_d=td, tier_e=te, tier_h=th, triggered=triggered, selected_source=selected_source,
            selected_median=_text(selected), selected_tier=_tier(selected) if sufficient else 'NO_OPEN',
            status='READY', reason_codes=sorted(reasons)))
    return records


def _check_decisions(rows):
    keys = set('schema_version symbol decision_utc_day known_at policy_sha256 history_sufficient inputs m_d m_e m_h tier_d tier_e tier_h triggered selected_source selected_median selected_tier status reason_codes'.split())
    input_keys = set('day_start exchange_reported effective_reported sum_hourly_reported daily_status hourly_status source_refs'.split())
    seen = set()
    for row in rows:
        _keys(row, keys)
        key = (row['symbol'], row['decision_utc_day'], row['policy_sha256'])
        if key in seen:
            _fail('TURNOVER_DECISION_CONFLICT')
        seen.add(key)
        if row['schema_version'] != 'r8_turnover_decision_v1' or row['known_at'] != row['decision_utc_day'] or type(row['known_at']) is not int or row['known_at'] % DAY:
            _fail('TURNOVER_DECISION_IDENTITY')
        _sha(row['policy_sha256']); _strings(row['reason_codes'])
        if type(row['history_sufficient']) is not bool or type(row['triggered']) is not bool:
            _fail('TURNOVER_DECISION_TYPE')
        if not isinstance(row['inputs'], list) or len(row['inputs']) != 12:
            _fail('TURNOVER_INPUT_COUNT')
        for index, item in enumerate(row['inputs']):
            _keys(item, input_keys)
            if item['day_start'] != row['known_at']-(12-index)*DAY:
                _fail('TURNOVER_INPUT_TIME')
            if any(item[k] not in ('VALID', 'MISSING', 'INVALID', 'NOT_EVALUATED') for k in ('daily_status', 'hourly_status')):
                _fail('TURNOVER_INPUT_STATUS')
            for k in ('exchange_reported', 'effective_reported', 'sum_hourly_reported'):
                if item[k] is not None and _number(item[k]) < 0:
                    _fail('TURNOVER_INPUT_NUMBER')
        selected = [row[k] for k in ('selected_source', 'selected_median', 'selected_tier')]
        if row['status'] == 'BLOCKED':
            if any(v is not None for v in selected) or not row['reason_codes']:
                _fail('TURNOVER_BLOCKED_REASON_REQUIRED')
        elif row['status'] == 'READY':
            if row['selected_source'] not in ('effective_daily', 'hourly_sum') or any(v is None for v in selected):
                _fail('TURNOVER_SELECTION_MISSING')
            if row['selected_tier'] != (_tier(_number(row['selected_median'])) if row['history_sufficient'] else 'NO_OPEN'):
                _fail('TURNOVER_SELECTION_TIER')
        else:
            _fail('TURNOVER_DECISION_STATUS')
    if rows != sorted(rows, key=lambda r:(r['decision_utc_day'], r['symbol'])):
        _fail('TURNOVER_DECISION_ORDER')


def _instruments(root, manifest, symbols):
    raw = _source_bytes(root, 'requests.jsonl', manifest['request_log_sha256'])
    records = {}
    for line in raw.splitlines():
        record = json.loads(line)
        request_id = record['request_id']
        if type(request_id) is not int or request_id <= 0 or request_id in records:
            raise MaterializationError('請求代號不合法或重複')
        records[request_id] = record
    ids = manifest['universe_request_ids']
    if not isinstance(ids, list) or not ids or any(type(i) is not int or i <= 0 for i in ids) or len(set(ids)) != len(ids):
        raise MaterializationError('universe_request_ids 不合法')
    instruments = {}
    for request_id in ids:
        record = records[request_id]
        page = json.loads(_source_bytes(root, f'raw/{request_id}.json', record['raw_sha256']))
        if record['endpoint'] != '/v5/market/instruments-info':
            raise MaterializationError('原始頁不是 instruments-info')
        # 探測失敗的頁仍核對雜湊，但不能作屬性來源。
        if record['http_status'] != 200 or record['retCode'] != 0 or page.get('retCode') != 0:
            continue
        for item in page['result']['list']:
            symbol = item.get('symbol')
            if symbol not in symbols:
                continue
            if item.get('contractType') != 'LinearPerpetual' or item.get('settleCoin') != 'USDT' or item.get('status') not in ('Trading', 'Closed'):
                raise MaterializationError('標的不是已開盤 USDT 永續合約')
            if symbol in instruments and instruments[symbol] != item:
                raise MaterializationError('原始頁的合約屬性衝突')
            instruments[symbol] = item
    if set(instruments) != set(symbols):
        raise MaterializationError('原始頁缺少所需標的')
    return instruments


def _selected_rows(raw, dataset, start, end, delivery):
    lines = gzip.decompress(raw).splitlines(keepends=True)
    if not lines or next(csv.reader([lines[0].decode('utf-8')])) != HEADERS[dataset]:
        raise MaterializationError('U1 CSV 標頭不符')
    selected, original, previous = [], [lines[0]], None
    for line in lines[1:]:
        # 整檔位元組只用於來源雜湊；範圍外只掃時間戳，不解讀數值或推導市場資訊。
        stamp = _integer(line.split(b',', 1)[0].decode('ascii'))
        if not start <= stamp < end and not (dataset == 'funding' and stamp == end):
            continue
        if dataset == 'funding' and delivery and stamp > delivery:
            continue
        row = next(csv.reader([line.decode('utf-8')]))
        if len(row) != len(HEADERS[dataset]) or previous is not None and stamp <= previous:
            raise MaterializationError('可讀資料列結構不符或時間不嚴格遞增')
        previous = stamp
        numbers = [_decimal(value, positive=(dataset == 'kline' and i < 4),
                            nonnegative=(dataset == 'open_interest' or dataset == 'kline' and i >= 4))
                   for i, value in enumerate(row[1:])]
        selected.append((stamp, numbers))
        original.append(line)
    return selected, b''.join(original)


def _csv(rows):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n')
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')


def _zip(symbol, raw):
    stream = io.BytesIO()
    info = zipfile.ZipInfo(symbol.lower()+'_trade_perp.csv', (1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    # 不壓縮以避免 zlib 版本影響確定性的位元組。
    info.compress_type = zipfile.ZIP_STORED
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr(info, raw)
    return stream.getvalue()


def _output_path(out):
    out = Path(out).absolute()
    if out.exists() or out.is_symlink():
        raise MaterializationError('輸出目錄必須不存在')
    resolved = out.resolve()
    if any((parent/'.git').exists() for parent in (resolved, *resolved.parents)):
        raise MaterializationError('輸出不可位於倉庫內')
    if not resolved.parent.is_dir():
        raise MaterializationError('輸出的父目錄必須存在')
    return resolved


def materialize(*, u1, u1_manifest_sha256, ledger, hypothesis, window, out,
                trial=None, validation=False):
    """物化一個已授權樣本外視窗；成功後回傳 §7.1 manifest。"""
    destination = _output_path(out)
    try:
        return _materialize(u1=u1, u1_manifest_sha256=u1_manifest_sha256, ledger=ledger,
                            hypothesis=hypothesis, window=window, out=destination, trial=trial, validation=validation)
    except (MaterializationError, LedgerError, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        # Invalid requests without a source/window identity cannot fabricate one.
        try:
            _sha(u1_manifest_sha256)
            start, end = _window(window)
        except (MaterializationError, ValueError, TypeError):
            raise exc
        if not destination.exists():
            failure = _Bundle.__new__(_Bundle)
            failure.raw, failure.manifest_sha = {}, u1_manifest_sha256
            failure.start, failure.end, failure.symbols = start, end, []
            reason = str(exc) if isinstance(exc, (MaterializationError, LedgerError)) else 'SOURCE_IO_OR_SCHEMA_FAILURE'
            failure.blocked(destination, reason)
        if isinstance(exc, (MaterializationError, LedgerError, OSError)):
            raise
        raise MaterializationError('SOURCE_IO_OR_SCHEMA_FAILURE') from exc


def _materialize(*, u1, u1_manifest_sha256, ledger, hypothesis, window, out,
                 trial=None, validation=False):
    out = _output_path(out)
    ledger = Path(ledger)
    if not ledger.is_dir() or not (ledger/'ledger_id.json').is_file():
        raise MaterializationError('帳本目錄與 ledger_id.json 必須已存在')
    book = ResearchLedger(ledger)
    access = book.data_access(hypothesis, trial)
    start, end = _window(window)
    if trial is not None and (start, end) != _window(book.trial_record(trial)['record']['data_window']):
        raise MaterializationError('視窗必須等於已開始試驗的 data_window')
    allowed_start, allowed_end = _window(access['out_of_sample'])
    if not allowed_start <= start < end <= allowed_end:
        raise MaterializationError('本版只物化樣本外，拒絕所有 holdout 區間')
    if end > TRAIN_END:
        _fail('VERIFICATION_SCOPE_OUTSIDE_TRAINING')
    lookback = access['max_lookback_seconds']
    if isinstance(lookback, bool) or not isinstance(lookback, (int, float)) or lookback < MIN_LOOKBACK_SECONDS:
        raise MaterializationError('最長回看不得小於 13 日')
    duration = Decimal(str(lookback)) * 1000
    if not duration.is_finite() or duration != duration.to_integral_value():
        raise MaterializationError('回看須為有限的毫秒長度')
    warm_start = start - int(duration)
    data_start = _timestamp(DATA_START)
    if warm_start < allowed_start and not (allowed_start == data_start and warm_start < data_start):
        raise MaterializationError('暖機越出可讀範圍')
    for segment in access['time_splits']:
        if segment['kind'] == 'holdout':
            a, b = _window({k: segment[k] for k in ('start', 'end')})
            if warm_start < b and a < start:
                raise MaterializationError('暖機跨入不可讀 holdout')
    strategy_symbols = access['selection'].get('symbols')
    if (not isinstance(strategy_symbols, list) or not strategy_symbols
            or any(not isinstance(s, str) or not re.fullmatch(r'[A-Z0-9]{1,32}', s) for s in strategy_symbols)
            or len(set(strategy_symbols)) != len(strategy_symbols)):
        raise MaterializationError('預登記須列出不重複的 selection.symbols')
    symbols = sorted(set(strategy_symbols) | {'BTCUSDT'})
    root = Path(u1).resolve()
    if not validation and u1_manifest_sha256 != P3B_MANIFEST_SHA256:
        raise MaterializationError('研究來源必須是釘住的 P3b manifest')
    source_manifest = json.loads(_source_bytes(root, 'manifest.json', u1_manifest_sha256))
    if source_manifest['tool_version'] != TOOL_VERSION:
        raise MaterializationError('U1 工具版本不符')
    instruments = _instruments(root, source_manifest, symbols)
    bundle = _Bundle.__new__(_Bundle)
    try:
        bundle.__init__(root, u1_manifest_sha256, max(warm_start, data_start), end, symbols)
        binding = bundle.binding(book, hypothesis)
    except MaterializationError as exc:
        bundle.blocked(out, str(exc))
        raise
    limitations = ['合約屬性為取數當時值，歷史變更未驗證。']
    if warm_start < data_start:
        limitations.append('暖機早於 2020-01-01 的部分為空。')
    result = {'schema_version': 'r8_materialization_v1', 'u1_manifest_sha256': u1_manifest_sha256,
              'u1_tool_version': TOOL_VERSION, 'ledger_id': book.ledger_id, 'hypothesis_id': hypothesis,
              'generation': access['generation'], 'purpose': 'validation' if validation else 'research',
              'window': {'start': start, 'end': end},
              'warmup': {'start': warm_start, 'end': start}, 'readable': access,
              'symbols': symbols, 'strategy_symbols': strategy_symbols, 'files': {}, 'gaps': {},
              'first_bar': {}, 'min_notional': {}, 'funding_interval_ms': {}, 'delistings': {},
              'symbol_properties_overlay_sha256': None, 'limitations': limitations}
    temporary = Path(tempfile.mkdtemp(prefix='.'+out.name+'-', dir=out.parent))
    try:
        def emit(name, raw, rows, source_file, source_sha256):
            path = temporary/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            stamps = [t for t, _ in rows]
            result['files'][name] = {'sha256': _digest(raw), 'rows': len(rows),
                                     'first': stamps[0] if stamps else None, 'last': stamps[-1] if stamps else None,
                                     'source_file': source_file, 'source_sha256': source_sha256}

        def emit_evidence(name, value, stamps=None, jsonl=False):
            values = value if jsonl else [value]
            raw = b''.join(_encoded(v) for v in values)
            emit(name, raw, [(t, None) for t in (stamps if stamps is not None else [None]*len(values))],
                 'manifest.json', u1_manifest_sha256)

        emit_evidence('verification/hypothesis_binding.json', binding)
        for name, raw in bundle.raw.items():
            if name.endswith('.jsonl'):
                values = bundle.scoped(name)
                emit_evidence('verification/'+name, values, [v['timestamp'] for v in values], jsonl=True)
            else:
                emit('verification/'+name, raw, [(None, None)]*len(raw.splitlines()), 'manifest.json', u1_manifest_sha256)
        limitations.extend(['2020–2021 自報成交額近似；小時 close×volume 近似仍未證明逐小時精確。',
                            '上市首箱可能含箱內上市前時間；q 按完整箱計，不外推。',
                            '資料品質證據僅供框架；同程序 Python 不構成完整假說隔離。'])
        if any(c['row_action'] == 'missing' for c in bundle.corrections.values()):
            limitations.append('未決行情已按逐列裁決隔離；funding／OI 獨立保留。')
        if bundle.version == 2:
            limitations.append('v2 尾段選源及信心證據僅存 verification；READY 不代表抽樣或研究驗收。')
        overlay, listing_records, turnover_records = [], [], []
        for symbol in symbols:
            item = instruments[symbol]
            tick = _decimal(item['priceFilter']['tickSize'], positive=True)
            lot = item['lotSizeFilter']
            step = _decimal(lot['qtyStep'], positive=True)
            minimum = _decimal(lot['minOrderQty'], positive=True)
            notional = lot.get('minNotionalValue')
            missing_reason = None
            if 'minNotionalValue' not in lot:
                missing_reason = '鍵不存在'
            elif notional is None:
                missing_reason = '值為 None'
            elif isinstance(notional, str) and not notional.strip():
                missing_reason = '值為空字串' if notional == '' else '值僅含空白'
            if missing_reason is not None:
                limitations.append(f'{symbol}: 缺 minNotionalValue（{missing_reason}），記為 0。')
                notional = '0'
            result['min_notional'][symbol] = _decimal(notional, nonnegative=True)
            interval = _integer(item['fundingInterval']) * 60000
            if interval <= 0:
                raise MaterializationError('資金費間隔須為正')
            result['funding_interval_ms'][symbol] = interval
            delivery = _integer(item.get('deliveryTime', '0'))
            overlay.append(['bybit', symbol, 'cryptofuture', symbol, 'USDT', '1', tick, step, symbol, minimum, ''])
            result['gaps'][symbol] = {}
            market = {}
            for dataset, interval_name in DATASETS:
                filename = f'{dataset}_{symbol}_{interval_name}.csv.gz'
                meta = source_manifest['files'][filename]
                if (meta['dataset'], meta['symbol'], meta['interval']) != (dataset, symbol, interval_name):
                    raise MaterializationError('來源檔案身份不符')
                raw = _source_bytes(root, filename, meta['sha256'])
                missing = []
                if dataset == 'kline':
                    rows, effective, original, originals, refs, missing = _market_rows(
                        raw, meta, filename, max(warm_start, data_start), end, bundle)
                    market[interval_name] = (dict(rows), originals, refs, meta)
                    emit('verification/original/'+filename[:-3], original,
                         [(int(line.split(b',', 1)[0]), None) for line in original.splitlines()[1:]], filename, meta['sha256'])
                else:
                    rows, effective = _selected_rows(raw, dataset, max(warm_start, data_start), end, delivery)
                emit('source/'+filename[:-3], effective, rows, filename, meta['sha256'])
                key = 'kline_hour' if interval_name == '60' else 'kline_day' if interval_name == 'D' else dataset
                clipped = list(missing)
                period = HOUR if interval_name == '60' else DAY if interval_name == 'D' else 4*HOUR
                for gap in meta['gaps']['missing_intervals']:
                    a, b = max(_integer(gap['start']), warm_start, data_start), min(_integer(gap['end_exclusive']), end)
                    if a < b:
                        clipped.append((a, b))
                result['gaps'][symbol][key] = _merged_gaps(clipped, period)
                if dataset == 'kline':
                    if interval_name == '60':
                        emit(f'lean/cryptofuture/bybit/hour/{symbol.lower()}_trade.zip',
                             _zip(symbol, _csv([[_date(t).strftime('%Y%m%d %H:%M'), *n[:5]] for t, n in rows])), rows, filename, meta['sha256'])
                        first = meta['first_timestamp']
                        result['first_bar'][symbol] = first if max(warm_start, data_start) <= first < end else None
                        if delivery and warm_start <= delivery <= end:
                            last = next((t for t, _ in reversed(rows) if t < delivery), None)
                            result['delistings'][symbol] = {'deliveryTime': delivery,
                                                           'partial_last_bar': last is not None and last < delivery < last+HOUR}
                    else:
                        emit(f'custom/kline_day/{symbol.lower()}.csv', _csv([[t+DAY, t, *n[:5]] for t, n in rows]), rows, filename, meta['sha256'])
                    resolution = 'hour' if interval_name == '60' else 'day'
                    offset = HOUR if interval_name == '60' else DAY
                    emit(f'custom/turnover_{resolution}/{symbol.lower()}.csv', _csv([[t+offset, t, n[5]] for t, n in rows]), rows, filename, meta['sha256'])
                else:
                    offset = 4*HOUR if dataset == 'open_interest' else 0
                    emit(f'custom/{dataset}/{symbol.lower()}.csv', _csv([[t+offset, t, n[0]] for t, n in rows]), rows, filename, meta['sha256'])
            hours, original_hours, hour_refs, hour_meta = market['60']
            daily, original_daily, daily_refs, _ = market['D']
            if hour_meta['first_timestamp'] < max(warm_start, data_start):
                _fail('LISTING_ORIGIN_UNKNOWN')
            first = None
            for t, n in sorted(original_hours.items()):
                if n is None:
                    _fail('LISTING_ORIGIN_UNKNOWN')
                if _number(n[4]) > 0:
                    first = t
                    break
            if first is None:
                _fail('LISTING_ORIGIN_UNKNOWN')
            launch = _integer(item['launchTime'])
            origin_refs = list(hour_refs[first])
            requests = {r['request_id']:r for r in map(json.loads, (root/'requests.jsonl').read_bytes().splitlines())}
            for rid in source_manifest['universe_request_ids']:
                page = json.loads(_source_bytes(root, f'raw/{rid}.json', requests[rid]['raw_sha256']))
                for index, entry in enumerate(page['result']['list']):
                    if entry.get('symbol') == symbol:
                        ref = dict.fromkeys(REF_KEYS)
                        ref.update(kind='instruments', relative_path=f'raw/{rid}.json', sha256=requests[rid]['raw_sha256'],
                                   request_id=str(rid), list_index=index)
                        origin_refs.append(ref)
            regimes = _listing(symbol, first, launch, _refs(origin_refs), hours, daily, hour_refs, end, bundle.policy_sha)
            listing_records.extend(regimes)
            header = ['known_at', 'day_start', 'stage', 'reason_code', 'cooling', 'policy_sha256']
            projected = [[r[k] if k != 'cooling' else json.dumps(r[k]) for k in header] for r in regimes]
            emit(f'custom/listing_regime/{symbol.lower()}.csv', _csv([header, *projected]),
                 [(r['known_at'], None) for r in regimes], 'manifest.json', u1_manifest_sha256)
            turnover_records.extend(_turnover(symbol, first, start, end, original_daily, daily, hours, daily_refs, hour_refs,
                                              bundle.policy_sha, history_first=result['first_bar'][symbol]))
        listing_records.sort(key=lambda r:(r['known_at'], r['symbol']))
        turnover_records.sort(key=lambda r:(r['decision_utc_day'], r['symbol']))
        _check_decisions(turnover_records)
        emit_evidence('verification/listing_regimes.jsonl', listing_records, [r['known_at'] for r in listing_records], jsonl=True)
        emit_evidence('verification/turnover_decisions.jsonl', turnover_records, [r['known_at'] for r in turnover_records], jsonl=True)
        overlay_raw = _csv(overlay)
        (temporary/'symbol_properties_overlay.csv').write_bytes(overlay_raw)
        result['symbol_properties_overlay_sha256'] = _digest(overlay_raw)
        (temporary/'materialization.json').write_bytes(canonical(result))
        if out.exists() or out.is_symlink():
            raise MaterializationError('輸出目錄已被建立')
        os.rename(temporary, out)
    except MaterializationError as exc:
        bundle.blocked(out, str(exc))
        raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('u1', 'u1-manifest-sha256', 'ledger', 'hypothesis', 'window', 'out'):
        parser.add_argument('--'+flag, required=True)
    parser.add_argument('--trial')
    parser.add_argument('--validation', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = materialize(**vars(args))
        print(canonical(result).decode('utf-8'))
    except (MaterializationError, LedgerError, OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, str(exc)+'\n')


if __name__ == '__main__':
    main()
