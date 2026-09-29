"""Bounded continuity metadata for encrypted recovery archives; imports never start work."""
import json
import math
import uuid
from . import db, features, files, memory


def export(project_id):
    return {'memory': memory.get(project_id), 'plans': features.listing(project_id)}


def statements(project_id, data):
    if data is None:
        return []  # Backward compatible with v0.3–v0.5 recovery archives.
    if not isinstance(data, dict) or len(json.dumps(data)) > 2_000_000:
        raise ValueError('Invalid recovery continuity metadata.')
    result = []
    context = data.get('memory', {})
    body = memory.validate(context.get('body', {}))
    notes = context.get('agent_notes', [])
    if not isinstance(notes, list) or len(notes) > 20 or any(
            not isinstance(n, dict) or not isinstance(n.get('text'), str) or len(n['text']) > 1500 or files.SECRET.search(n['text']) for n in notes):
        raise ValueError('Invalid recovery project notes.')
    result.append(('INSERT INTO project_memory(project_id,body,agent_notes,revision,updated_at) VALUES(%s,%s,%s,1,%s)',
        (project_id, json.dumps(body), json.dumps([{'text': n['text'], 'at': str(n.get('at', ''))[:80]} for n in notes]), db.now())))
    plans = data.get('plans', [])
    if not isinstance(plans, list) or len(plans) > 100:
        raise ValueError('Recovery supports at most 100 feature plans.')
    for plan in plans:
        items = features.validate(plan['title'], [{k: item[k] for k in ('title', 'prompt', 'acceptance')} for item in plan['milestones']])
        for item, original in zip(items, plan['milestones']):
            item['status'] = 'completed' if original['status'] == 'completed' else 'needs_review'
            item['result'] = str(original.get('result', ''))[:6000]
            digest = original.get('validated_digest')
            item['validated_digest'] = digest if isinstance(digest, str) and len(digest) == 64 else None
        usage = plan.get('usage', {})
        for key in ('input_tokens', 'output_tokens', 'requests', 'retries', 'estimated_usd'):
            value = usage.get(key, 0)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1e12:
                raise ValueError('Invalid recovery usage totals.')
        if usage.get('limits'):
            for key in ('budget_usd', 'max_input_tokens', 'max_output_tokens', 'input_rate', 'output_rate'):
                value = usage['limits'].get(key)
                if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1e12:
                    raise ValueError('Invalid recovery budget.')
        checkpoint = {'phase': 'recovered_needs_review'}
        reservation = plan.get('checkpoint', {}).get('reservation')
        if reservation:
            for key in ('input_tokens', 'output_tokens', 'estimated_usd'):
                value = reservation.get(key)
                if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1e12:
                    raise ValueError('Invalid recovery in-flight reservation.')
            checkpoint['reservation'] = {k: reservation[k] for k in ('input_tokens', 'output_tokens', 'estimated_usd')}
        settings = plan.get('settings', {})
        if settings and (settings.get('provider') not in {'local', 'openai', 'anthropic'} or not isinstance(settings.get('model'), str) or len(settings['model']) > 200):
            raise ValueError('Invalid recovery model settings.')
        result.append(('INSERT INTO feature_plans(id,project_id,title,milestones,status,checkpoint,usage,settings,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (uuid.uuid4().hex, project_id, plan['title'], json.dumps(items), 'needs_review', json.dumps(checkpoint), json.dumps(usage),
             json.dumps({k: settings[k] for k in ('provider', 'model')} if settings else {}), db.now(), db.now())))
    return result
