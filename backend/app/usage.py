"""Conservative cost estimates and token limits, checked before every model request."""
from dataclasses import dataclass, asdict
import json
import math
import os


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Limits:
    budget_usd: float = 2.0
    max_input_tokens: int = 180000
    max_output_tokens: int = 24000
    input_rate: float = 3.0
    output_rate: float = 15.0


def defaults(provider, model):
    # Standard text rates for these exact models; custom models require configured rates.
    known = {'claude-sonnet-4-6': (3.0, 15.0), 'gpt-5.4': (2.5, 15.0)}
    if provider == 'local':
        return {'budget_usd': 0.0, 'max_input_tokens': 180000, 'max_output_tokens': 24000,
                'input_rate': 0.0, 'output_rate': 0.0,
                'pricing_checked': 'local', 'pricing_known': bool(model)}
    rates = known.get(model)
    prefix = 'ANTHROPIC' if provider == 'anthropic' else 'OPENAI'
    input_rate = os.environ.get(prefix + '_INPUT_USD_PER_MILLION')
    output_rate = os.environ.get(prefix + '_OUTPUT_USD_PER_MILLION')
    if input_rate is not None and output_rate is not None:
        rates = (float(input_rate), float(output_rate))
    return {'budget_usd': 2.0, 'max_input_tokens': 180000, 'max_output_tokens': 24000,
            'input_rate': rates[0] if rates else None, 'output_rate': rates[1] if rates else None,
            'pricing_checked': '2026-09-15', 'pricing_known': bool(rates)}


def normalized(provider, usage):
    input_tokens = int(usage.get('input_tokens', 0))
    if provider == 'anthropic':
        input_tokens += int(usage.get('cache_creation_input_tokens', 0)) + int(usage.get('cache_read_input_tokens', 0))
    return input_tokens, int(usage.get('output_tokens', 0))


class Meter:
    def __init__(self, limits):
        self.limits = limits
        self.input_tokens = self.output_tokens = self.requests = self.retries = 0
        self.estimated_usd = 0.0

    def allowance(self, history, system, tools):
        # Approximate at one token per three UTF-8 bytes plus framing overhead.
        # This remains conservative for typical English/code prompts; actual provider
        # usage is enforced immediately after each response.
        # Base64 bytes are not text tokens. Reserve 5,000 input tokens per bounded
        # viewport image, then reconcile against actual provider usage.
        image_count = 0
        def compact(value):
            nonlocal image_count
            if isinstance(value, dict):
                if value.get('type') in {'input_image', 'image', 'image_url'}:
                    image_count += 1
                    return {'type': 'image', 'content': '[bounded viewport screenshot]'}
                return {key: compact(item) for key, item in value.items()}
            if isinstance(value, list):
                return [compact(item) for item in value]
            return value
        size = len(json.dumps(compact({'input': history, 'system': system, 'tools': tools}), ensure_ascii=False).encode())
        upper_input = math.ceil(size / 3) + 4096 + image_count * 5000
        if self.input_tokens + upper_input > self.limits.max_input_tokens:
            raise BudgetExceeded('Input-token budget reached. Start a smaller follow-up build.')
        remainder = self.limits.budget_usd - self.estimated_usd - upper_input * self.limits.input_rate / 1_000_000
        affordable = (self.limits.max_output_tokens - self.output_tokens if self.limits.output_rate == 0 else
                      math.floor(remainder * 1_000_000 / self.limits.output_rate))
        output = min(8000, self.limits.max_output_tokens - self.output_tokens, affordable)
        if output < 256:
            raise BudgetExceeded('Build budget reached. Saved edits remain available; increase the budget or narrow the request.')
        self.reservation = {'input_tokens': upper_input, 'output_tokens': output,
                            'estimated_usd': (upper_input*self.limits.input_rate + output*self.limits.output_rate)/1_000_000}
        return output

    def record(self, provider, usage):
        if 'input_tokens' not in usage or 'output_tokens' not in usage:
            raise BudgetExceeded('The provider returned no token usage. Further calls were stopped to protect the budget.')
        input_tokens, output_tokens = normalized(provider, usage)
        if input_tokens < 0 or output_tokens < 0:
            raise BudgetExceeded('Invalid provider usage. Further calls were stopped.')
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.requests += 1
        self.estimated_usd += (input_tokens * self.limits.input_rate + output_tokens * self.limits.output_rate) / 1_000_000
        if self.input_tokens > self.limits.max_input_tokens or self.output_tokens > self.limits.max_output_tokens:
            raise BudgetExceeded('Provider usage reached the token limit. No further model calls will be made.')
        if self.estimated_usd > self.limits.budget_usd:
            raise BudgetExceeded('Provider usage reached the build budget. No further model calls will be made.')

    def data(self):
        return {'input_tokens': self.input_tokens, 'output_tokens': self.output_tokens,
                'requests': self.requests, 'retries': self.retries, 'estimated_usd': round(self.estimated_usd, 6),
                'limits': asdict(self.limits), 'estimate_note': 'Standard-rate estimate; provider billing is authoritative.'}
