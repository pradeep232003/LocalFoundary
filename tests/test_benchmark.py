"""The benchmark harness needs a model to produce a measurement, but its accounting
must be right before any measurement is worth reading. These cover the parts that
decide what a run reports: case selection, event accounting across the API's 100-event
pages, outcome classification, and the rendered report.
"""
import importlib.util
import json
import types

import pytest

from app import config

spec = importlib.util.spec_from_file_location('foundry_benchmark', config.ROOT / 'scripts/benchmark.py')
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)

PROMPTS = config.ROOT / 'scripts/benchmark/prompts.json'


def options(**overrides):
    defaults = dict(provider='local', budget=2.0, max_repairs=2, max_input_tokens=1000,
                    max_output_tokens=100, timeout=5)
    return types.SimpleNamespace(**{**defaults, **overrides})


class FakeBuilder:
    """Stands in for the builder API. Pages events exactly as the real endpoint does."""

    def __init__(self, run_status='completed', validation='passed', visual=('passed', 'passed'),
                 events=None, fail_on=None):
        self.run_status, self.validation, self.visual = run_status, validation, visual
        self.events = events or []
        self.fail_on = fail_on or set()
        self.cancelled = False

    def request(self, method, path, **kwargs):
        if any(fragment in path for fragment in self.fail_on):
            raise RuntimeError(f'HTTP 500 from {path}')
        if path == '/projects':
            return {'id': 'p' * 32}
        if path.endswith('/build'):
            return {'run_id': 'r' * 32}
        if path.endswith('/cancel'):
            self.cancelled = True
            return {'message': 'stop requested'}
        if path.startswith('/projects/'):
            return {'last_validation': {'status': self.validation, 'browser_checks': True,
                                        'checks': [{'name': 'Backend tests', 'status': self.validation}]},
                    'visual_checks': [{'viewport': v, 'status': s}
                                      for v, s in zip(('desktop', 'mobile'), self.visual)]}
        raise AssertionError('unexpected path ' + path)

    def all_events(self, run_id):
        page = {'id': run_id, 'status': self.run_status,
                'usage': {'input_tokens': 100, 'output_tokens': 20, 'estimated_usd': 0.5}}
        return page, self.events


def test_prompt_set_is_well_formed():
    data = json.loads(PROMPTS.read_text())
    ids = [case['id'] for case in data['cases']]
    assert len(ids) == len(set(ids)), 'case ids must be unique'
    for case in data['cases']:
        assert case['profile'] in {'starter', 'accounts'}
        assert case['tier'] in {1, 2, 3}
        assert len(case['prompt']) > 80, 'a benchmark prompt should be a real request'
        assert case['expect'], 'every case needs reviewer expectations'


def test_case_selection_by_tier_and_id():
    assert {case['tier'] for case in benchmark.load_cases(PROMPTS, {1}, None)} == {1}
    picked = benchmark.load_cases(PROMPTS, set(), ['booking'])
    assert [case['id'] for case in picked] == ['booking']
    with pytest.raises(SystemExit):
        benchmark.load_cases(PROMPTS, set(), ['does-not-exist'])
    with pytest.raises(SystemExit):
        benchmark.load_cases(PROMPTS, {99}, None)


def test_event_accounting_separates_repairs_checks_and_errors():
    summary = benchmark.summarize_events([
        {'kind': 'tool', 'text': 'patch_file'},
        {'kind': 'repair', 'text': 'Automatic repair 1/2.'},
        {'kind': 'tool', 'text': 'write_file'},
        {'kind': 'repair', 'text': 'Automatic repair 2/2.'},
        {'kind': 'check', 'text': 'Backend tests passed.', 'status': 'passed'},
        {'kind': 'tool_error', 'text': 'patch did not apply'},
        {'kind': 'usage', 'text': 'ignored'},
    ])
    assert summary['repairs'] == 2
    assert summary['tool_calls'] == 2
    assert summary['checks'] == [{'text': 'Backend tests passed.', 'status': 'passed'}]
    assert summary['errors'] == ['patch did not apply']


def test_event_paging_follows_the_after_cursor(monkeypatch):
    """The run endpoint returns 100 events at a time; miss the cursor and repair
    counts silently undercount on any long build."""
    events = [{'id': i, 'kind': 'repair' if i <= 3 else 'tool', 'text': 'x'} for i in range(1, 251)]
    pages = []

    class Paging(FakeBuilder):
        def request(self, method, path, **kwargs):
            after = kwargs.get('params', {}).get('after', 0)
            window = [event for event in events if event['id'] > after][:100]
            pages.append(after)
            return {'id': 'r', 'status': 'completed', 'events': window,
                    'more': len([e for e in events if e['id'] > after]) > 100, 'usage': {}}

    builder = Paging()
    status, collected = benchmark.Builder.all_events(builder, 'r' * 32)
    assert pages == [0, 100, 200], 'each page must resume after the last event id'
    assert len(collected) == 250
    assert benchmark.summarize_events(collected)['repairs'] == 3


@pytest.mark.parametrize('run_status,validation,visual,expected', [
    ('completed', 'passed', ('passed', 'passed'), 'passed'),
    ('completed', 'failed', ('passed', 'passed'), 'validation_failed'),
    ('completed', 'passed', ('passed', 'failed'), 'browser_failed'),
    ('completed', 'passed', (), 'browser_failed'),
    ('failed', 'failed', (), 'build_failed'),
    ('budget_exceeded', 'passed', ('passed', 'passed'), 'build_failed'),
])
def test_outcome_classification(run_status, validation, visual, expected):
    builder = FakeBuilder(run_status=run_status, validation=validation, visual=visual)
    record = benchmark.run_case(builder, json.loads(PROMPTS.read_text())['cases'][0], options())
    assert record['outcome'] == expected
    assert record['usage']['estimated_usd'] == 0.5


def test_a_stuck_run_times_out_and_is_cancelled():
    builder = FakeBuilder(run_status='running')
    record = benchmark.run_case(builder, json.loads(PROMPTS.read_text())['cases'][0], options(timeout=0))
    assert record['outcome'] == 'timeout'
    assert builder.cancelled, 'a timed-out run must not be left spending budget'


def test_builder_failure_is_reported_as_a_harness_error_not_a_model_result():
    builder = FakeBuilder(fail_on={'/build'})
    record = benchmark.run_case(builder, json.loads(PROMPTS.read_text())['cases'][0], options())
    assert record['outcome'] == 'harness_error'
    assert 'HTTP 500' in record['detail']


def test_report_states_the_pass_rate_and_keeps_the_manual_checklist():
    results = [
        benchmark.run_case(FakeBuilder(), json.loads(PROMPTS.read_text())['cases'][0], options()),
        benchmark.run_case(FakeBuilder(validation='failed'), json.loads(PROMPTS.read_text())['cases'][1], options()),
    ]
    for record, case in zip(results, json.loads(PROMPTS.read_text())['cases']):
        record['tier'] = case['tier']
    text = benchmark.render_markdown({
        'created_at': '2026-09-21T00:00:00+00:00', 'provider': 'local', 'model': 'stub',
        'prompt_version': 1, 'results': results})
    assert 'Tier 1: 1/2 passed' in text
    assert '**passed**' in text and '**validation_failed**' in text
    # A green row is not evidence the app is any good; the checklist must survive.
    assert 'It does not mean the app is good' in text
    for expectation in results[0]['expect']:
        assert expectation in text
