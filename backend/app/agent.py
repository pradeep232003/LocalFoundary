import json
import os

from . import codebase_rag, code_tools, config, db, dependencies, features, files, memory, providers, sandbox, visual, usage as usage_meter


def redact(text):
    text = str(text)
    for name in ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'BUILDER_TOKEN'):
        value = os.environ.get(name)
        if value:
            text = text.replace(value, '[redacted]')
    return files.SECRET.sub('[redacted secret]', text)


def dispatch(project_id, name, args):
    source = sandbox.source_dir(project_id)
    if name == 'list_files':
        return '\n'.join(files.list_files(source))
    if name == 'read_file':
        return files.read(source, args['path'])
    if name == 'inspect_file':
        return code_tools.inspect(source, args['path'])
    if name == 'patch_file':
        return code_tools.patch(source, args['path'], args['expected_sha256'], args['edits'])
    if name == 'search_code':
        return code_tools.search(source, args['query'])
    if name == 'code_index':
        return code_tools.index(source)
    if name == 'read_context':
        return memory.get(project_id)
    if name == 'remember':
        return memory.remember(project_id, args['note'])
    if name == 'plan_features':
        return features.create(project_id, args['title'], args['milestones'])
    if name == 'write_file':
        return files.write(source, args['path'], args['content'])
    if name == 'delete_file':
        return files.delete(source, args['path'])
    if name == 'start_preview':
        url = sandbox.start(project_id)
        db.query('UPDATE projects SET preview_url=%s WHERE id=%s', (url, project_id))
        return url
    if name == 'logs':
        return sandbox.logs(project_id)
    if name == 'check':
        return sandbox.check(project_id, args['service'])
    if name == 'run_command':
        return sandbox.execute(project_id, args['service'], args['command'])
    if name == 'request_dependencies':
        return dependencies.propose(project_id, args['packages'], args['reason'])
    if name == 'inspect_preview':
        return visual.capture(project_id, args['path'], args['viewport'], args['actions'])
    raise ValueError('Unknown tool.')


def build(project_id, run_id, provider, cancelled, limits, session=None):
    session = session if session is not None else {}
    history = db.query("SELECT role,content FROM messages WHERE project_id=%s AND mode='coder' ORDER BY id DESC LIMIT 12", (project_id,))
    history.reverse()
    # Message windows start with user, with context bounded between builds.
    while history and history[0]['role'] != 'user':
        history.pop(0)
    history = [{'role': r['role'], 'content': r['content'][:16000]} for r in history]
    retrieval_query = next((row['content'] for row in reversed(history) if row['role'] == 'user'), '')
    context = memory.context(project_id)
    if context and history:
        history[0]['content'] = context + '\nCurrent conversation:\n' + history[0]['content']
    if retrieval_query and 'history' not in session:
        retrieved = codebase_rag.context(project_id, retrieval_query)
        if retrieved:
            history[-1]['content'] += '\n\n' + retrieved
    history = session.setdefault('history', history)
    meter = session.setdefault('meter', usage_meter.Meter(limits))
    checkpoint = session.get('checkpoint', lambda *args, **kwargs: None)
    final = ''
    for step in range(config.MAX_STEPS):
        if cancelled.is_set():
            raise InterruptedError('Build stopped. Completed edits remain available.')
        db.event(run_id, 'status', f'Working · step {step + 1} of {config.MAX_STEPS}')
        allowance = meter.allowance(history, providers.SYSTEM, providers.TOOLS)
        checkpoint('request_started', reservation=meter.reservation)
        def retry(attempt, delay, reason):
            meter.retries += 1
            db.event(run_id, 'retry', f'Provider retry {attempt}/2 after {reason}; waiting {delay:g}s.')
        items, texts, calls, provider_usage, truncated = providers.ask(
            provider, history, max_output_tokens=allowance, on_retry=retry)
        before_requests = meter.requests
        try:
            meter.record(provider, provider_usage)
        finally:
            if meter.requests > before_requests:
                checkpoint('request_settled')
        usage_data = meter.data()
        db.query('UPDATE runs SET usage=%s WHERE id=%s', (json.dumps(usage_data), run_id))
        db.event(run_id, 'usage',
                 f'{usage_data["input_tokens"]:,} input · {usage_data["output_tokens"]:,} output · '
                 f'about ${usage_data["estimated_usd"]:.4f}', usage=usage_data)
        if truncated:
            raise RuntimeError('The model hit its output limit. Ask for a smaller change; incomplete tool calls were not executed.')
        if cancelled.is_set():
            raise InterruptedError('Build stopped. Completed edits remain available.')
        for text in texts:
            final = redact(text)
            db.event(run_id, 'assistant', final)
        if not calls:
            providers.append_turn(provider, history, items, [])
            final = final or 'The model returned no text or tool actions. Try a more specific request.'
            return final, usage_data
        results = []
        images, awaiting_approval, awaiting_plan = [], False, False
        if len(calls) > 24:
            raise RuntimeError('The model requested too many tools in a single step.')
        for call in calls:
            if cancelled.is_set():
                raise InterruptedError('Build stopped. Completed edits remain available.')
            error = False
            try:
                if awaiting_approval or awaiting_plan:
                    raise ValueError('Build paused for review. Remaining tools were not executed.')
                args = json.loads(call['arguments']) if isinstance(call['arguments'], str) else call['arguments']
                if not isinstance(args, dict):
                    raise ValueError('Tool arguments must be an object.')
                if call['name'] == 'run_command' and session.get('restrict_commands'):
                    raise ValueError('Shell commands are disabled for resumed milestones. Inspect state and use patches, migrations, and trusted checks.')
                if call['name'] == 'plan_features' and session.get('checkpoint'):
                    raise ValueError('A milestone is already running. Complete this milestone; do not create nested plans.')
                label = call['name'] + (' · ' + str(args['path']) if 'path' in args else '')
                db.event(run_id, 'tool', redact(label))
                checkpoint('tool_started', tool=call['name'], path=str(args.get('path', ''))[:300])
                text = dispatch(project_id, call['name'], args)
                checkpoint('tool_finished', tool=call['name'], source_digest=files.digest(sandbox.source_dir(project_id)))
                if call['name'] == 'request_dependencies':
                    awaiting_approval = True
                if call['name'] == 'plan_features':
                    awaiting_plan = True
                if call['name'] == 'inspect_preview' and session.get('share_screenshots'):
                    images.append(visual.image_data(project_id, text['id']))
                if isinstance(text, dict):
                    text = json.dumps(text)
            except Exception as exc:
                error, text = True, str(exc)
            text = redact(text)
            if len(text) > 24000:
                text = text[:24000] + '\n[Output truncated at 24,000 characters. Do not overwrite a partially read file.]'
            db.event(run_id, 'tool_error' if error else 'result', text[:4000])
            results.append({'id': call['id'], 'text': text, 'error': error})
        providers.append_turn(provider, history, items, results)
        if images:
            providers.append_images(provider, history, images)
        if awaiting_approval:
            raise dependencies.ApprovalRequired('Review the package request in Packages, then continue the build. No dependency was installed automatically.')
        if awaiting_plan:
            raise features.PlanReady('Feature plan saved. Review and start it from Roadmap.')
    raise RuntimeError('Step limit reached. Edits are saved locally, but the build was not marked successful.')
