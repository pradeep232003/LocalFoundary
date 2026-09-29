"""Durable milestones. Resume inspects current state; it never replays old tool calls."""
import json
import math
import uuid
from . import db, files, sandbox, usage


class PlanReady(RuntimeError):
    pass


def validate(title, milestones):
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120 or files.SECRET.search(title):
        raise ValueError('Give the plan a short title without secrets.')
    if not isinstance(milestones, list) or not 1 <= len(milestones) <= 12:
        raise ValueError('A plan needs 1–12 milestones.')
    result = []
    for item in milestones:
        if not isinstance(item, dict) or set(item) != {'title', 'prompt', 'acceptance'}:
            raise ValueError('Each milestone needs a title, prompt and acceptance criteria.')
        for key, maximum in [('title', 120), ('prompt', 6000), ('acceptance', 3000)]:
            if not isinstance(item[key], str) or not 1 <= len(item[key].strip()) <= maximum or files.SECRET.search(item[key]):
                raise ValueError('Milestone text is missing, too long or contains a possible secret.')
        result.append({**item, 'id': uuid.uuid4().hex, 'status': 'pending', 'result': '', 'validated_digest': None})
    return result


def create(project_id, title, milestones):
    milestones = validate(title, milestones)
    identifier = uuid.uuid4().hex
    db.query('INSERT INTO feature_plans(id,project_id,title,milestones,status,checkpoint,usage,settings,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
             (identifier, project_id, title.strip(), json.dumps(milestones), 'ready', '{}', '{}', '{}', db.now(), db.now()))
    return get(project_id, identifier)


def decode(row):
    for field in ('milestones', 'checkpoint', 'usage', 'settings'):
        row[field] = json.loads(row[field])
    return row


def get(project_id, identifier):
    sandbox.validate_id(identifier)
    row = db.query('SELECT * FROM feature_plans WHERE id=%s AND project_id=%s', (identifier, project_id), one=True)
    if not row:
        raise ValueError('Feature plan was not found.')
    return decode(row)


def listing(project_id):
    return [decode(row) for row in db.query('SELECT * FROM feature_plans WHERE project_id=%s ORDER BY created_at DESC', (project_id,))]


def persist(plan):
    db.query('UPDATE feature_plans SET milestones=%s,status=%s,checkpoint=%s,usage=%s,settings=%s,updated_at=%s WHERE id=%s AND project_id=%s',
             (json.dumps(plan['milestones']), plan['status'], json.dumps(plan['checkpoint']), json.dumps(plan['usage']),
              json.dumps(plan['settings']), db.now(), plan['id'], plan['project_id']))


def meter_from(plan, limits):
    meter = usage.Meter(limits)
    data = plan['usage']
    for key in ('input_tokens', 'output_tokens', 'requests', 'retries', 'estimated_usd'):
        value = data.get(key, 0)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError('Stored plan usage is invalid.')
        setattr(meter, key, value)
    inflight = plan['checkpoint'].get('reservation')
    if inflight:
        # A lost response may have been billed. Reserve its estimate once, never reset usage on resume.
        meter.input_tokens += inflight['input_tokens']
        meter.output_tokens += inflight['output_tokens']
        meter.estimated_usd += inflight['estimated_usd']
        meter.requests += 1
        plan['checkpoint'].pop('reservation', None)
        plan['checkpoint']['uncertain_usage_reserved'] = True
        plan['usage'] = meter.data()
        persist(plan)
    return meter


def execute(project_id, identifier, run_id, cancelled, provider, model, limits, options, reviewed_digest, reviewed, snapshot):
    from . import builder, dependencies
    plan = get(project_id, identifier)
    if plan['status'] in {'running', 'completed'}:
        raise ValueError('This plan is running or already complete.')
    if reviewed_digest != files.digest(sandbox.source_dir(project_id)):
        raise ValueError('Source changed after review. Reload the plan before starting.')
    if plan['status'] != 'ready' and not reviewed:
        raise ValueError('Review the last checkpoint, source, and database changes before resuming.')
    if plan['settings'] and (plan['settings']['provider'] != provider or plan['settings']['model'] != model):
        raise ValueError('Resume with the same model/provider, or create a new plan.')
    previous_limits = plan['usage'].get('limits', {})
    if previous_limits and (previous_limits['input_rate'] != limits.input_rate or previous_limits['output_rate'] != limits.output_rate):
        raise ValueError('Model pricing changed. Create a new plan after reviewing remaining work.')
    meter = meter_from(plan, limits)
    plan['settings'] = {'provider': provider, 'model': model, 'options': options}
    plan['usage'] = meter.data()
    plan['status'] = 'running'
    persist(plan)
    current = None
    try:
        for item in plan['milestones']:
            if item['status'] == 'completed':
                continue
            if cancelled.is_set():
                raise InterruptedError('Milestone queue paused before the next feature.')
            current = item
            resuming = item['status'] != 'pending'
            item['status'] = 'running'
            snapshot(project_id, 'Before milestone: ' + item['title'])
            persist(plan)
            db.event(run_id, 'milestone', 'Building: ' + item['title'], milestone_id=item['id'])
            prompt = ('Plan: ' + plan['title'] + '\nMilestone: ' + item['title'] + '\n' + item['prompt'] +
                      '\nAcceptance criteria:\n' + item['acceptance'])
            if resuming:
                prompt += ('\nThis milestone was interrupted or failed. Inspect current files first. Do not replay previous commands. '
                           'Arbitrary sandbox shell commands are disabled for this resumed milestone. Use file patches, migrations, and trusted checks. '
                           'Last checkpoint: ' + json.dumps(plan['checkpoint']))
            db.message(project_id, 'user', prompt)
            def checkpoint(phase, **extra):
                plan['checkpoint'] = {'phase': phase, 'milestone_id': item['id'], 'at': db.now(), **extra}
                plan['usage'] = meter.data()
                persist(plan)
                db.query('UPDATE runs SET usage=%s WHERE id=%s', (json.dumps(meter.data()), run_id))
            session = {'meter': meter, 'checkpoint': checkpoint, 'restrict_commands': resuming,
                       'share_screenshots': options['share_screenshots']}
            try:
                final, _ = builder.run(project_id, run_id, provider, cancelled, limits, options['max_repairs'],
                                       options['browser_checks'], options['share_screenshots'], session=session)
                item.update(status='completed', result=final[:6000], validated_digest=files.digest(sandbox.source_dir(project_id)))
                db.message(project_id, 'assistant', 'Milestone completed: ' + item['title'] + '\n' + final)
                checkpoint('milestone_completed', source_digest=item['validated_digest'])
            finally:
                snapshot(project_id, 'After milestone: ' + item['title'] + ' (including partial changes)')
        plan['status'] = 'completed'
    except BaseException as exc:
        if current and current['status'] != 'completed':
            current['status'] = 'needs_review'
        plan['status'] = 'awaiting_packages' if isinstance(exc, dependencies.ApprovalRequired) else 'needs_review'
        # Preserve an in-flight request reservation when its actual usage was never returned.
        plan['usage'] = meter.data()
        raise
    finally:
        persist(plan)
