import pytest

from app import usage


def test_known_model_prices_and_environment_override(monkeypatch):
    assert usage.defaults('anthropic', 'claude-sonnet-4-6')['input_rate'] == 3.0
    assert usage.defaults('openai', 'gpt-5.4')['output_rate'] == 15.0
    monkeypatch.setenv('OPENAI_INPUT_USD_PER_MILLION', '1.25')
    monkeypatch.setenv('OPENAI_OUTPUT_USD_PER_MILLION', '8.5')
    custom = usage.defaults('openai', 'custom-model')
    assert custom['pricing_known'] is True
    assert (custom['input_rate'], custom['output_rate']) == (1.25, 8.5)


def test_meter_enforces_input_output_and_cost_limits():
    meter = usage.Meter(usage.Limits(budget_usd=.10, max_input_tokens=10_000,
                                     max_output_tokens=1_000, input_rate=3, output_rate=15))
    assert 256 <= meter.allowance([{'role': 'user', 'content': 'small'}], 'system', []) <= 1_000
    meter.record('openai', {'input_tokens': 500, 'output_tokens': 250})
    data = meter.data()
    assert data['requests'] == 1
    assert data['estimated_usd'] == pytest.approx(.00525)

    with pytest.raises(usage.BudgetExceeded, match='token limit'):
        meter.record('openai', {'input_tokens': 1, 'output_tokens': 751})


def test_meter_fails_closed_on_missing_usage_or_oversized_prompt():
    meter = usage.Meter(usage.Limits(budget_usd=2, max_input_tokens=10_000,
                                     max_output_tokens=2_000, input_rate=3, output_rate=15))
    with pytest.raises(usage.BudgetExceeded, match='no token usage'):
        meter.record('openai', {'output_tokens': 2})

    huge = [{'role': 'user', 'content': 'x' * 30_000}]
    with pytest.raises(usage.BudgetExceeded, match='Input-token budget'):
        meter.allowance(huge, 'system', [])


def test_anthropic_cache_tokens_are_counted_conservatively():
    meter = usage.Meter(usage.Limits(budget_usd=2, max_input_tokens=20_000,
                                     max_output_tokens=2_000, input_rate=3, output_rate=15))
    meter.record('anthropic', {'input_tokens': 100, 'cache_creation_input_tokens': 200,
                               'cache_read_input_tokens': 300, 'output_tokens': 50})
    assert meter.data()['input_tokens'] == 600
