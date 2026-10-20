"""U4 唯讀查詢：只用自行建立的合成帳本，不依賴既有測試檔。"""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import pytest
from program_code.research.r8_ledger import ledger as mod


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('禁止網路')
    for name in ('connect', 'connect_ex'):
        monkeypatch.setattr(socket.socket, name, denied)
    monkeypatch.setattr(socket, 'create_connection', denied)


class Clock:
    def __init__(self):
        self.at = datetime(2026, 10, 20, tzinfo=timezone.utc)

    def __call__(self):
        self.at += timedelta(seconds=1)
        return self.at


def registration(hid='h1', generation=1, lookback=13*86400):
    return {'hypothesis_id': hid, 'generation': generation, 'family': 'synthetic',
            'economic_mechanism': '構造資料', 'decision_period': {'unit': 'day', 'value': 1},
            'expected_holding_seconds': 86400, 'expected_turnover': 1,
            'pessimistic_cost_ratio': 0.5, 'data_range': {'start': mod.DEFAULT_BOUNDARIES[0], 'end': mod.DEFAULT_BOUNDARIES[-1]},
            'time_splits': mod.split_intervals(), 'primary_metric': 'after_cost_sharpe',
            'candidate_thresholds': {'sharpe': 1},
            'multiple_testing': {'method': 'BY', 'fdr': 0.1, 'members': ['h1', 'h2'], 'members_sha256': mod.sha256(['h1', 'h2'])},
            'max_lookback_seconds': lookback, 'label_period_seconds': 86400, 'max_holding_seconds': 86400,
            'selection': {'type': 'time_series', 'rule': '固定標的', 'known_at_period_start': mod.DEFAULT_BOUNDARIES[0], 'symbols': ['XUSDT']},
            'previous_no_go': None, 'split_rationale': '固定', 'sharpe_frequency_seconds': 86400,
            'oos_protocol': {'scheme': 'expanding', 'initial_train_seconds': 365*86400, 'test_seconds': 30*86400,
                             'step_seconds': 30*86400, 'purge_seconds': 7*86400, 'embargo_seconds': 7*86400},
            'baselines': [{'id': 'no_trade', 'kind': 'strategy_independent'}, {'id': 'buy_hold', 'kind': 'strategy_independent'}],
            'falsification_rule': {'degradation_z': 1}}


def make_book(path, record=None):
    book = mod.ResearchLedger(path, clock=Clock())
    book.preregister(record or registration())
    return book


def begin(book, hid='h1', tid='t1'):
    window = {'start': '2022-01-01T00:00:00Z', 'end': '2022-02-01T00:00:00Z'}
    config = {'strategy_parameters': {}, 'cost_model_parameters': {}}
    record = {'trial_id': tid, 'hypothesis_id': hid, 'generation': 1, 'parent_trial_id': None,
              'variant_parameters': {}, 'data_window': window, 'fit_window': window, 'score_window': window,
              'manifest_sha256': '1'*64, 'data_files': {'a': '2'*64}, 'code_commit': '3'*40,
              'cost_model': {'id': 'c', 'version': '1'}, 'fill_model': {'id': 'f', 'version': '1'},
              'configuration': config, 'configuration_sha256': mod.sha256(config),
              'engine': {'id': 'e', 'version': '1'}, 'dependencies': {},
              'time_semantics': {'known_at': 'close', 'fill_at': 'next', 'simulated_latency_ms': 0},
              'random_seed': 1, 'sharpe_frequency': {'unit': 'day', 'seconds': 86400, 'annualized': False},
              'evaluation_kind': 'in_sample', 'role': 'exploratory'}
    book.begin_trial(record)
    return record


def snapshot(book):
    return {name: (book.out/(name+'.jsonl')).read_bytes() if (book.out/(name+'.jsonl')).exists() else None
            for name in mod.LEDGERS}


def test_data_access_out_of_sample_readonly(tmp_path):
    book = make_book(tmp_path/'ledger')
    before = snapshot(book)
    access = book.data_access('h1')
    assert access['generation'] == 1
    assert access['out_of_sample'] == {'start': '2020-01-01T00:00:00Z', 'end': '2026-01-01T00:00:00Z'}
    assert access['selection']['symbols'] == ['XUSDT']
    assert access['max_lookback_seconds'] == 1123200
    assert access['holdout'] is None
    assert len(access['time_splits']) == 4
    assert snapshot(book) == before


def test_trial_record_full_identity_readonly(tmp_path):
    book = make_book(tmp_path/'ledger')
    original = begin(book)
    before = snapshot(book)
    result = book.trial_record('t1')
    assert all(result['record'][key] == value for key, value in original.items())
    assert {'started_at', 'variant_parameters_sha256', 'preregistration_sha256'} <= result['record'].keys()
    assert result['finished'] is False
    assert result['status'] == 'aborted'
    assert snapshot(book) == before
    with pytest.raises(mod.LedgerError):
        book.trial_record('absent')


@pytest.mark.parametrize('status', ['completed', 'failed', 'aborted'])
def test_trial_record_finished_status(tmp_path, status):
    book = make_book(tmp_path/'ledger')
    begin(book)
    book.finish_trial('t1', {'status': status, 'result_summary': {'synthetic': True},
                            'ended_at': book.clock().isoformat()})
    before = snapshot(book)
    assert book.trial_record('t1')['status'] == status
    assert book.trial_record('t1')['finished'] is True
    assert snapshot(book) == before


def append_fixture_event(book, name, payload):
    # 只建立合成鏈事件，測試特定狀態的讀取，不以此宣稱結算流程已驗證。
    path = book.out/(name+'.jsonl')
    rows = [json.loads(line) for line in path.read_bytes().splitlines()] if path.exists() else []
    unsigned = {'sequence': len(rows)+1, 'previous': rows[-1]['hash'] if rows else '0'*64,
                'payload': {**payload, 'recorded_at': book.clock().isoformat().replace('+00:00', 'Z')}}
    with path.open('ab') as stream:
        stream.write(mod.canonical({**unsigned, 'hash': mod.sha256(unsigned)})+b'\n')


@pytest.mark.parametrize('state', ['unopened', 'denied', 'other_candidate', 'candidate'])
def test_holdout_state_only_opened_candidate(tmp_path, state):
    book = make_book(tmp_path/'ledger')
    interval = {'start': '2026-01-08T00:00:00Z', 'end': '2026-05-15T00:00:00Z'}
    if state != 'unopened':
        append_fixture_event(book, 'holdouts', {'action': 'denied' if state == 'denied' else 'opened',
                            'generation': 1, 'intervals': {'h2' if state == 'other_candidate' else 'h1': interval}})
    before = snapshot(book)
    assert book.data_access('h1')['holdout'] == (interval if state == 'candidate' else None)
    assert snapshot(book) == before


def test_generation_two_never_gets_first_holdout(tmp_path):
    book = make_book(tmp_path/'ledger', registration(generation=2))
    append_fixture_event(book, 'holdouts', {'action': 'opened', 'generation': 1, 'intervals': {'h1': {'start': '2026-01-08T00:00:00Z', 'end': '2026-05-15T00:00:00Z'}}})
    assert book.data_access('h1')['holdout'] is None


def test_withdrawal_requires_own_started_trial_and_unknown_rejected(tmp_path):
    book = make_book(tmp_path/'ledger')
    book.preregister(registration('h2'))
    begin(book)
    begin(book, 'h2', 't2')
    book.withdraw_hypothesis('h1', '合成撤回')
    before = snapshot(book)
    for hid, tid in [('absent', None), ('h1', None), ('h1', 'absent'), ('h1', 't2')]:
        with pytest.raises(mod.LedgerError):
            book.data_access(hid, tid)
    assert book.data_access('h1', 't1')['generation'] == 1
    assert snapshot(book) == before


@pytest.mark.parametrize('name', mod.LEDGERS)
@pytest.mark.parametrize('method', ['data_access', 'trial_record'])
def test_all_three_chains_verified_without_writing(tmp_path, name, method):
    book = make_book(tmp_path/'ledger')
    begin(book)
    path = book.out/(name+'.jsonl')
    path.write_bytes((path.read_bytes() if path.exists() else b'')+b'corrupt\n')
    before = snapshot(book)
    with pytest.raises(mod.LedgerError):
        getattr(book, method)('h1' if method == 'data_access' else 't1')
    assert snapshot(book) == before


def test_query_does_not_recover_pending_falsification(tmp_path, monkeypatch):
    book = make_book(tmp_path/'ledger')
    begin(book)
    def forbidden(*args):
        raise AssertionError('唯讀查詢不得進入寫入復原')
    monkeypatch.setattr(book, '_recover_falsifications', forbidden)
    assert book.data_access('h1')['generation'] == 1
    assert not book.trial_record('t1')['finished']
