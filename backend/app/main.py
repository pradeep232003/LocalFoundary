import io
import json
import os
import secrets
import shutil
import threading
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Literal
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.staticfiles import StaticFiles

from . import (agent, automations, backups, builder, code_tools, codebase_rag, config, db, dependencies, diagnostics, documents, features, files,
               github, host, journeys, memory, mobile_builds, providers, recovery, releases, sandbox, specialists, usage, validation, visual)

pool = ThreadPoolExecutor(max_workers=3)
locks = {}
cancellations = {}
active_runs = {}
guard = threading.Lock()


@asynccontextmanager
async def lifespan(app):
    if len(config.TOKEN) < 32 or not config.DATABASE_URL:
        raise RuntimeError('Run ./scripts/setup.sh first; BUILDER_TOKEN and DATABASE_URL are required.')
    db.init()
    yield
    for event in list(cancellations.values()):
        event.set()
    pool.shutdown(wait=False, cancel_futures=True)
    db.close_all()


app = FastAPI(title='Local Foundry', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost'])


@app.middleware('http')
async def local_auth(request: Request, call_next):
    origin = request.headers.get('origin')
    origins = {f'http://127.0.0.1:{config.PORT}', f'http://localhost:{config.PORT}'}
    if os.environ.get('FOUNDRY_DEV_UI') == '1':
        origins.update({'http://127.0.0.1:5173', 'http://localhost:5173'})
    if origin and origin not in origins:
        return JSONResponse({'detail': 'Origin is not allowed.'}, status_code=403)
    if request.url.path.startswith('/api/'):
        expected = 'Bearer ' + config.TOKEN
        actual = request.headers.get('authorization', '')
        if not config.TOKEN or not secrets.compare_digest(actual.encode(), expected.encode()):
            return JSONResponse({'detail': 'Open the launch link printed by start.sh to unlock this session.'}, status_code=401)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; img-src 'self' data: blob:; font-src 'self'; "
        "frame-src http://127.0.0.1:*; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
    return response


@app.exception_handler(ValueError)
async def bad_value(request, exc):
    return JSONResponse({'detail': agent.redact(exc)}, status_code=400)


def project(project_id):
    sandbox.validate_id(project_id)
    row = db.query('SELECT * FROM projects WHERE id=%s', (project_id,), one=True)
    if not row:
        raise HTTPException(404, 'Project not found.')
    return row


def save_version(project_id, label):
    version = uuid.uuid4().hex
    digest = files.snapshot(sandbox.source_dir(project_id), sandbox.project_dir(project_id) / 'snapshots' / version)
    db.query('INSERT INTO versions(id,project_id,label,digest,created_at) VALUES(%s,%s,%s,%s,%s)',
             (version, project_id, label, digest, db.now()))
    return version


def launch(project_id, kind, action):
    project(project_id)
    with guard:
        lock = locks.setdefault(project_id, threading.Lock())
        if not lock.acquire(blocking=False):
            raise HTTPException(409, 'This project already has an operation running.')
        if len(active_runs) >= 3:
            lock.release()
            raise HTTPException(409, 'Three operations are already running. Wait for one to finish.')
        run_id = uuid.uuid4().hex
        cancelled = threading.Event()
        cancellations[run_id] = cancelled
        active_runs[project_id] = run_id
    try:
        db.query('INSERT INTO runs(id,project_id,kind,status,created_at) VALUES(%s,%s,%s,%s,%s)',
                 (run_id, project_id, kind, 'running', db.now()))
    except Exception:
        with guard:
            active_runs.pop(project_id, None)
            cancellations.pop(run_id, None)
        lock.release()
        raise

    def work():
        status = 'completed'
        try:
            action(run_id, cancelled)
        except InterruptedError as exc:
            status = 'cancelled'
            db.event(run_id, 'error', agent.redact(exc))
        except usage.BudgetExceeded as exc:
            status = 'budget_exceeded'
            db.event(run_id, 'error', agent.redact(exc))
        except dependencies.ApprovalRequired as exc:
            status = 'awaiting_approval'
            db.event(run_id, 'approval', agent.redact(exc))
        except features.PlanReady as exc:
            status = 'awaiting_plan'
            db.event(run_id, 'plan', agent.redact(exc))
        except Exception as exc:
            status = 'failed'
            db.event(run_id, 'error', agent.redact(exc))
        finally:
            try:
                db.query('UPDATE runs SET status=%s WHERE id=%s', (status, run_id))
            finally:
                with guard:
                    active_runs.pop(project_id, None)
                    cancellations.pop(run_id, None)
                lock.release()
    pool.submit(work)
    return {'run_id': run_id, 'kind': kind}


class NewProject(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    profile: Literal['starter', 'accounts'] = 'starter'


class Build(BaseModel):
    prompt: str = Field(min_length=1, max_length=12000)
    provider: Literal['anthropic', 'openai', 'local'] = 'anthropic'
    mode: Literal['coder', 'documents', 'files'] = 'coder'
    budget_usd: float = Field(default=2.0, ge=0, le=100)
    max_input_tokens: int = Field(default=180000, ge=10000, le=240000)
    max_output_tokens: int = Field(default=24000, ge=1000, le=64000)
    max_repairs: int = Field(default=2, ge=0, le=3)
    browser_checks: bool = True
    share_screenshots: bool = False


class PackageApproval(BaseModel):
    allow_network: bool = False


class ContextUpdate(BaseModel):
    body: dict
    revision: int = Field(ge=0)


class FeaturePlan(BaseModel):
    title: str
    milestones: list[dict]


class StartPlan(Build):
    prompt: str = 'Run the reviewed feature plan.'
    source_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    reviewed: bool = False


class BrowserCheck(BaseModel):
    path: str = '/'
    viewport: Literal['desktop', 'mobile'] = 'desktop'
    actions: list[dict] = Field(default_factory=list, max_length=12)


class ReleaseReview(BaseModel):
    source_digest: str = Field(pattern=r'^[0-9a-f]{64}$')


class MobileBuild(BaseModel):
    target: Literal['apk', 'aab', 'ipa']
    origin: str = Field(max_length=300)
    name: str = Field(min_length=1, max_length=30)
    app_id: str = Field(min_length=3, max_length=155)
    version: str = Field(default='1.0.0', max_length=30)
    build_number: int = Field(default=1, ge=1, le=2147483647)
    source_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    team_id: str = Field(default='', max_length=10)
    export_method: Literal['debugging', 'release-testing', 'app-store-connect'] = 'debugging'
    allow_network: bool = False
    # Play upload-key signing. Never persisted to the build record or its log.
    # Optional app icon; without it the build carries Capacitor's placeholder.
    icon_source: str = Field(default='', max_length=4096)
    icon_background: str = Field(default='#FFFFFF', max_length=7)
    keystore_path: str = Field(default='', max_length=4096)
    key_alias: str = Field(default='', max_length=64)
    store_password: str = Field(default='', max_length=200)
    key_password: str = Field(default='', max_length=200)


class Publish(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    message: str = Field(default='Save app from Local Foundry', min_length=1, max_length=200)
    expected_head: str | None = Field(default=None, max_length=64)
    source_digest: str = Field(min_length=64, max_length=64, pattern=r'^[0-9a-f]{64}$')


class GithubReview(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class RecoveryPassword(BaseModel):
    password: str = Field(min_length=12, max_length=200)


def parse_json(value, default=None):
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def require_validated(row, project_id):
    report = parse_json(row.get('last_validation'), {})
    if report.get('status') != 'passed' or report.get('source_digest') != files.digest(sandbox.source_dir(project_id)):
        raise ValueError('Run validation successfully on the current source before saving it to GitHub.')
    from .profiles import get as get_profile
    if get_profile(sandbox.source_dir(project_id)) == 'accounts' and report.get('gate_version', 0) < 6:
        raise ValueError('Run the protected security and authenticated journey validation before saving an Accounts release.')
    return report


@app.get('/api/config')
def settings():
    return {'providers': {p: {'model': m, 'configured': bool(m) if p == 'local' else bool(os.environ.get(
        'ANTHROPIC_API_KEY' if p == 'anthropic' else 'OPENAI_API_KEY')) and not config.OFFLINE_ONLY,
        'limits': usage.defaults(p, m)} for p, m in config.MODELS.items()},
        'version': '0.11.0', 'runtime': host.details(), 'local_vision': os.environ.get('LOCAL_VISION', '').lower() in {'1', 'true', 'yes'},
        'offline_only': config.OFFLINE_ONLY, 'documents_folder': str(config.DOCUMENTS),
        'files_folder': str(config.AUTOMATION_FILES),
        'docker_installed': bool(shutil.which('docker')), 'github_installed': bool(shutil.which('gh'))}


@app.get('/api/diagnostics')
def diagnostic_report():
    return diagnostics.report()


@app.get('/api/projects')
def list_projects():
    return db.query('SELECT * FROM projects ORDER BY created_at DESC')


@app.post('/api/projects', status_code=201)
def create_project(body: NewProject):
    name = body.name.strip()
    if not name:
        raise ValueError('Give the project a name.')
    project_id = uuid.uuid4().hex
    sandbox.seed(project_id, body.profile)
    db.query('INSERT INTO projects(id,name,created_at) VALUES(%s,%s,%s)', (project_id, name, db.now()))
    save_version(project_id, 'Starting template')
    return project(project_id)


@app.get('/api/projects/{project_id}')
def detail(project_id: str):
    row = project(project_id)
    from .profiles import get as get_profile
    row['profile'] = get_profile(sandbox.source_dir(project_id))
    row['sync_state'] = parse_json(row.get('sync_state'), {})
    row['last_validation'] = parse_json(row.get('last_validation'))
    row['source_digest'] = files.digest(sandbox.source_dir(project_id))
    if (row['last_validation'] and
            (row['last_validation'].get('source_digest') != row['source_digest'] or
             (row['profile'] == 'accounts' and row['last_validation'].get('gate_version', 0) < 6))):
        row['last_validation']['status'] = 'stale'
    row['messages'] = db.query('SELECT role,content,created_at,mode FROM messages WHERE project_id=%s ORDER BY id', (project_id,))
    row['versions'] = db.query('SELECT * FROM versions WHERE project_id=%s ORDER BY created_at DESC', (project_id,))
    row['backups'] = backups.listing(project_id)
    row['file_plans'] = automations.listing(project_id)
    row['documents'] = documents.status()
    row['recovery_exports'] = recovery.listing(project_id)
    row['dependency_requests'] = dependencies.listing(project_id)
    row['visual_checks'] = visual.listing(project_id)
    row['context'] = memory.get(project_id)
    row['feature_plans'] = features.listing(project_id)
    row['journeys'] = journeys.latest(project_id)
    row['active_run'] = active_runs.get(project_id)
    row['active_run_kind'] = None
    if row['active_run']:
        active = db.query('SELECT kind FROM runs WHERE id=%s', (row['active_run'],), one=True)
        row['active_run_kind'] = active['kind'] if active else None
    return row


@app.get('/api/projects/{project_id}/files')
def source_files(project_id: str):
    project(project_id)
    return files.list_files(sandbox.source_dir(project_id))


@app.get('/api/projects/{project_id}/file')
def source_file(project_id: str, path: str):
    project(project_id)
    return code_tools.inspect(sandbox.source_dir(project_id), path)


@app.get('/api/projects/{project_id}/rag/status')
@app.post('/api/projects/{project_id}/rag/reindex')
def rag_status(project_id: str):
    project(project_id)
    return codebase_rag.status(project_id)


class SourceSearch(BaseModel):
    query: str = Field(min_length=2, max_length=16000)
    top_k: int = Field(default=3, ge=1, le=8)


@app.post('/api/projects/{project_id}/rag/search')
def rag_search(project_id: str, body: SourceSearch):
    project(project_id)
    return codebase_rag.search(project_id, body.query, body.top_k)


@app.post('/api/projects/{project_id}/rag/config')
def rag_config(project_id: str, body: dict):
    project(project_id)
    return codebase_rag.configure(project_id, body)


@app.get('/api/projects/{project_id}/rag/export-db')
def rag_export(project_id: str):
    project(project_id)
    return Response(codebase_rag.export(project_id), media_type='application/vnd.sqlite3',
                    headers={'Content-Disposition': 'attachment; filename="codebase.sqlite"'})


@app.post('/api/agents/validate-price')
@app.post('/api/agents/validate-deal')
def unavailable_live_verification():
    return JSONResponse({'verified': False, 'detail': 'Live retailer verification is unavailable. No retailer connector is installed.'}, status_code=501)


@app.get('/api/projects/{project_id}/code-search')
def search_code(project_id: str, q: str):
    project(project_id)
    return code_tools.search(sandbox.source_dir(project_id), q)


def edit_metadata(project_id, action):
    project(project_id)
    with guard:
        lock = locks.setdefault(project_id, threading.Lock())
        if not lock.acquire(blocking=False):
            raise HTTPException(409, 'Wait for the project operation to finish.')
    try:
        return action()
    finally:
        lock.release()


@app.post('/api/projects/{project_id}/context')
def update_context(project_id: str, body: ContextUpdate):
    return edit_metadata(project_id, lambda: memory.save(project_id, body.body, body.revision))


@app.post('/api/projects/{project_id}/plans')
def create_feature_plan(project_id: str, body: FeaturePlan):
    return edit_metadata(project_id, lambda: features.create(project_id, body.title, body.milestones))


@app.post('/api/projects/{project_id}/plans/{plan_id}/start')
def start_feature_plan(project_id: str, plan_id: str, body: StartPlan):
    limits = build_limits(body)
    features.get(project_id, plan_id)
    options = {'max_repairs': body.max_repairs, 'browser_checks': body.browser_checks, 'share_screenshots': body.share_screenshots}
    return launch(project_id, 'milestones', lambda run_id, cancelled: features.execute(
        project_id, plan_id, run_id, cancelled, body.provider, config.MODELS[body.provider], limits, options,
        body.source_digest, body.reviewed, save_version))


def build_limits(body):
    providers.key_for(body.provider)
    price = usage.defaults(body.provider, config.MODELS[body.provider])
    if not price['pricing_known']:
        raise ValueError('Configure input/output token rates in .env for this custom model before building.')
    if body.provider != 'local' and body.budget_usd < .10:
        raise ValueError('Remote-provider builds require a budget of at least $0.10.')
    if body.share_screenshots and body.provider == 'local' and not settings()['local_vision']:
        raise ValueError('Enable LOCAL_VISION only after configuring an image-capable local model, or turn off screenshot sharing.')
    return usage.Limits(body.budget_usd, body.max_input_tokens, body.max_output_tokens,
                          price['input_rate'], price['output_rate'])


@app.post('/api/projects/{project_id}/build')
def start_build(project_id: str, body: Build):
    limits = build_limits(body)
    prompt = body.prompt.strip()
    if not prompt or files.SECRET.search(prompt):
        raise ValueError('Describe the app without including API keys or secrets.')
    def action(run_id, cancelled):
        db.message(project_id, 'user', prompt, body.mode)
        if body.mode != 'coder':
            final, _, plan = specialists.run(project_id, run_id, body.provider, prompt,
                                              cancelled, limits, body.mode)
            if body.mode == 'files' and plan:
                final += '\n\nThe plan is waiting for your approval in Files. No files were changed.'
            db.message(project_id, 'assistant', final, body.mode)
            return
        save_version(project_id, 'Before AI edit')
        final = None
        try:
            final, _ = builder.run(project_id, run_id, body.provider, cancelled, limits,
                                   body.max_repairs, body.browser_checks, body.share_screenshots)
        except dependencies.ApprovalRequired as exc:
            db.message(project_id, 'assistant', str(exc), body.mode)
            raise
        except Exception:
            if final:
                db.message(project_id, 'assistant', final + '\n\nChanges were saved, but automatic validation did not pass.', body.mode)
            raise
        else:
            db.message(project_id, 'assistant', final + '\n\nAll automatic checks passed.', body.mode)
        finally:
            save_version(project_id, 'After AI edit (including partial changes)')
    return launch(project_id, 'build' if body.mode == 'coder' else body.mode, action)


@app.post('/api/projects/{project_id}/preview/{operation}')
def preview(project_id: str, operation: Literal['start', 'stop']):
    def action(run_id, cancelled):
        db.event(run_id, 'status', 'Starting preview…' if operation == 'start' else 'Stopping preview…')
        if operation == 'start':
            backups.create(project_id, 'Before preview migrations')
            sandbox.apply_migrations(project_id)
            url = sandbox.start(project_id)
        else:
            url = None
        if operation == 'stop':
            sandbox.stop(project_id)
        db.query('UPDATE projects SET preview_url=%s WHERE id=%s', (url, project_id))
        db.event(run_id, 'preview', 'Preview ready.' if url else 'Preview stopped. Database preserved.', url=url)
    return launch(project_id, 'preview', action)


@app.get('/api/projects/{project_id}/logs')
def project_logs(project_id: str):
    project(project_id)
    try:
        return {'text': agent.redact(sandbox.logs(project_id))}
    except RuntimeError as exc:
        raise HTTPException(503, agent.redact(exc)) from exc


@app.post('/api/projects/{project_id}/restore/{version_id}')
def restore(project_id: str, version_id: str):
    sandbox.validate_id(version_id)
    version = db.query('SELECT * FROM versions WHERE id=%s AND project_id=%s', (version_id, project_id), one=True)
    if not version:
        raise HTTPException(404, 'Version not found.')
    def action(run_id, cancelled):
        save_version(project_id, 'Before restore')
        sandbox.stop(project_id)
        db.query('UPDATE projects SET preview_url=NULL WHERE id=%s', (project_id,))
        files.restore(sandbox.source_dir(project_id), sandbox.project_dir(project_id) / 'snapshots' / version_id)
        db.query('UPDATE projects SET last_validation=NULL WHERE id=%s', (project_id,))
        save_version(project_id, 'Restored ' + version['label'])
        db.event(run_id, 'status', 'Source restored. Start the preview when ready. Database data was not changed.')
    return launch(project_id, 'restore', action)


@app.post('/api/projects/{project_id}/validate')
def validate_project(project_id: str, browser_checks: bool = True):
    return launch(project_id, 'validation', lambda run_id, cancelled: validation.run(
        project_id, run_id, cancelled, browser_checks=browser_checks))


@app.post('/api/projects/{project_id}/packages/{request_id}/approve')
def approve_packages(project_id: str, request_id: str, body: PackageApproval):
    def action(run_id, cancelled):
        save_version(project_id, 'Before approved dependency changes')
        result = dependencies.apply(project_id, request_id, body.allow_network)
        save_version(project_id, 'After approved dependency changes')
        db.event(run_id, 'dependencies', result['message'], images=result['images'])
    return launch(project_id, 'dependencies', action)


@app.post('/api/projects/{project_id}/packages/{request_id}/reject')
def reject_packages(project_id: str, request_id: str):
    sandbox.validate_id(request_id)
    def action(run_id, cancelled):
        db.query("UPDATE dependency_requests SET status='rejected' WHERE id=%s AND project_id=%s AND status='pending'", (request_id, project_id))
        db.event(run_id, 'dependencies', 'Dependency request rejected. No packages installed.')
    return launch(project_id, 'dependencies', action)


@app.post('/api/projects/{project_id}/visual')
def inspect_app(project_id: str, body: BrowserCheck):
    options = visual.validate_options(body.path, body.viewport, body.actions)
    def action(run_id, cancelled):
        report = visual.capture(project_id, **options)
        db.event(run_id, 'visual', 'Browser check ' + report['status'] + '.', artifact=report)
        if report['status'] != 'passed':
            raise ValueError('Browser check failed. Review its screenshot and diagnostics in Visual.')
    return launch(project_id, 'visual', action)


@app.get('/api/projects/{project_id}/visual/{artifact_id}')
def screenshot(project_id: str, artifact_id: str):
    project(project_id)
    return FileResponse(visual.image_path(project_id, artifact_id), media_type='image/jpeg')


@app.post('/api/projects/{project_id}/release')
def release_bundle(project_id: str, body: ReleaseReview):
    row = project(project_id)
    with guard:
        lock = locks.setdefault(project_id, threading.Lock())
        if not lock.acquire(blocking=False):
            raise HTTPException(409, 'Wait for the current operation before exporting a release.')
    try:
        # Re-read after acquiring the lock; no stale pre-lock validation metadata.
        row = project(project_id)
        output = releases.bundle(project_id, parse_json(row.get('last_validation'), {}), body.source_digest)
        return Response(output, media_type='application/zip', headers={
            'Content-Disposition': f'attachment; filename="release-{project_id[:8]}.zip"'})
    finally:
        lock.release()


@app.post('/api/projects/{project_id}/github/review')
def review_github(project_id: str, body: GithubReview):
    if config.OFFLINE_ONLY:
        raise ValueError('GitHub is disabled while OFFLINE_ONLY is enabled.')
    github.validate_name(body.name)
    row = project(project_id)
    require_validated(row, project_id)
    repo = row['repo']
    baseline = parse_json(row.get('sync_state'), {})
    review = github.review(repo, sandbox.source_dir(project_id), baseline, initial=not bool(repo))
    review['repository_name'] = repo or body.name
    return review


@app.post('/api/projects/{project_id}/github')
def publish(project_id: str, body: Publish):
    if config.OFFLINE_ONLY:
        raise ValueError('GitHub is disabled while OFFLINE_ONLY is enabled.')
    github.validate_name(body.name)
    def action(run_id, cancelled):
        row = project(project_id)
        require_validated(row, project_id)
        baseline = parse_json(row.get('sync_state'), {})
        if not row['repo']:
            db.event(run_id, 'status', 'Creating a private GitHub repository…')
            repo = github.create_private(body.name)
            state = github.remote_state(repo)
            # GitHub's auto-initialized README belongs to the repository we just
            # created. Mark only colliding generated paths as managed so the
            # first reviewed save can replace that placeholder without treating
            # unrelated remote files as disposable.
            current = files.export(sandbox.source_dir(project_id))
            baseline = {'head': state['head'], 'branch': state['branch'],
                        'files': {path: value for path, value in current.items()
                                  if path in state['entries']}}
            expected_head = state['head']
        else:
            repo = row['repo']
            expected_head = body.expected_head
        result = github.save(repo, sandbox.source_dir(project_id), body.message, baseline,
                             expected_head, body.source_digest)
        db.query('UPDATE projects SET repo=%s,sync_state=%s WHERE id=%s',
                 (repo, json.dumps(result['baseline']), project_id))
        db.event(run_id, 'github', 'Saved reviewed source to GitHub.', url=result['url'])
    return launch(project_id, 'github', action)


@app.post('/api/projects/{project_id}/documents/reindex')
def reindex_documents(project_id: str):
    def action(run_id, cancelled):
        db.event(run_id, 'status', 'Rebuilding the local document index…')
        result = documents.rebuild(run_id)
        db.event(run_id, 'documents', f'Indexed {result["indexed_files"]} files into {result["chunks"]} chunks.')
    return launch(project_id, 'documents_index', action)


@app.get('/api/projects/{project_id}/documents/search')
def search_documents(project_id: str, q: str):
    project(project_id)
    if not 2 <= len(q.strip()) <= 500:
        raise ValueError('Search query must contain 2–500 characters.')
    return {'results': documents.query(q.strip(), 12)}


@app.post('/api/projects/{project_id}/file-plans/{plan_id}/apply')
def apply_file_plan(project_id: str, plan_id: str):
    sandbox.validate_id(plan_id)
    return launch(project_id, 'file_apply', lambda run_id, cancelled:
                  db.event(run_id, 'files', 'File plan applied. Undo remains available.',
                           plan=automations.apply(plan_id, project_id)))


@app.post('/api/projects/{project_id}/file-plans/{plan_id}/undo')
def undo_file_plan(project_id: str, plan_id: str):
    sandbox.validate_id(plan_id)
    return launch(project_id, 'file_undo', lambda run_id, cancelled:
                  db.event(run_id, 'files', 'File plan undone.',
                           plan=automations.undo(plan_id, project_id)))


@app.post('/api/projects/{project_id}/recovery')
def create_recovery(project_id: str, body: RecoveryPassword):
    def action(run_id, cancelled):
        db.event(run_id, 'status', 'Creating database backup and encrypted recovery archive…')
        record = recovery.create(project_id, body.password)
        db.event(run_id, 'recovery', 'Encrypted recovery archive is ready.', export=record)
    return launch(project_id, 'recovery', action)


@app.get('/api/projects/{project_id}/recovery/{export_id}')
def download_recovery(project_id: str, export_id: str):
    project(project_id)
    path, row = recovery.export_path(project_id, export_id)
    return FileResponse(path, media_type='application/octet-stream', filename=row['filename'])


@app.post('/api/recovery/import')
async def import_recovery(request: Request):
    password = unquote(request.headers.get('x-foundry-recovery-password', ''))
    encoded_name = request.headers.get('x-foundry-recovery-name') or ''
    name = unquote(encoded_name) if encoded_name else None
    recovery.validate_password(password)
    imports = config.DATA / 'imports'
    imports.mkdir(exist_ok=True)
    path = imports / (uuid.uuid4().hex + '.partial')
    size = 0
    try:
        with path.open('xb') as stream:
            path.chmod(0o600)
            async for chunk in request.stream():
                size += len(chunk)
                if size > recovery.MAX_ARCHIVE:
                    raise ValueError('Recovery upload exceeds 10 GB.')
                stream.write(chunk)
        if size < 48:
            raise ValueError('Recovery upload is incomplete.')
        return await run_in_threadpool(recovery.import_archive, path, password, name)
    finally:
        path.unlink(missing_ok=True)


@app.post('/api/projects/{project_id}/backups')
def create_backup(project_id: str):
    def action(run_id, cancelled):
        db.event(run_id, 'status', 'Creating PostgreSQL backup…')
        record = backups.create(project_id, 'Manual backup')
        db.event(run_id, 'backup', 'Database backup created.', backup=record)
    return launch(project_id, 'backup', action)


@app.post('/api/projects/{project_id}/backups/{backup_id}/restore')
def restore_backup(project_id: str, backup_id: str):
    sandbox.validate_id(backup_id)
    def action(run_id, cancelled):
        db.event(run_id, 'status', 'Creating safeguard and restoring database…')
        safeguard = backups.restore(project_id, backup_id)
        db.query('UPDATE projects SET preview_url=NULL,last_validation=NULL WHERE id=%s', (project_id,))
        db.event(run_id, 'backup', 'Database restored. Preview stopped; a pre-restore safeguard was kept.',
                 backup=safeguard)
    return launch(project_id, 'backup_restore', action)


@app.get('/api/projects/{project_id}/download')
def download(project_id: str):
    project(project_id)
    with guard:
        lock = locks.setdefault(project_id, threading.Lock())
        if not lock.acquire(blocking=False):
            raise HTTPException(409, 'Wait for the current operation before downloading.')
    try:
        content = files.export(sandbox.source_dir(project_id))
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path, value in content.items():
                archive.writestr(path, value)
        return Response(output.getvalue(), media_type='application/zip',
                        headers={'Content-Disposition': f'attachment; filename="app-{project_id[:8]}.zip"'})
    finally:
        lock.release()


@app.get('/api/runs/{run_id}')
def run_status(run_id: str, after: int = 0):
    sandbox.validate_id(run_id)
    row = db.query('SELECT * FROM runs WHERE id=%s', (run_id,), one=True)
    if not row:
        raise HTTPException(404, 'Run not found.')
    events = db.query('SELECT id,payload FROM events WHERE run_id=%s AND id>%s ORDER BY id LIMIT 100', (run_id, after))
    row['events'] = [{'id': e['id'], **json.loads(e['payload'])} for e in events]
    row['usage'] = parse_json(row.get('usage'))
    row['more'] = len(events) == 100
    return row


@app.post('/api/runs/{run_id}/cancel')
def cancel(run_id: str):
    row = db.query('SELECT kind FROM runs WHERE id=%s', (run_id,), one=True)
    if row and row['kind'] not in {'build', 'milestones', 'documents', 'files', 'validation', 'mobile_apk', 'mobile_aab', 'mobile_ipa'}:
        raise ValueError('This operation cannot be cancelled.')
    event = cancellations.get(run_id)
    if event:
        event.set()
    return {'message': 'Stop requested; an in-flight model call or sandbox command may finish first.'}


@app.get('/api/mobile/capabilities')
def mobile_capabilities():
    return mobile_builds.capabilities()


@app.get('/api/projects/{project_id}/mobile/builds')
def mobile_history(project_id: str):
    project(project_id)
    return mobile_builds.listing(project_id)


@app.post('/api/projects/{project_id}/mobile/builds', status_code=202)
def mobile_build(project_id: str, body: MobileBuild):
    project(project_id)
    data = mobile_builds.validate_request(body.model_dump())
    if files.digest(sandbox.source_dir(project_id)) != data['source_digest']:
        raise ValueError('Project changed. Refresh before starting a mobile build.')
    return launch(project_id, 'mobile_' + data['target'],
                  lambda run_id, cancelled: mobile_builds.execute(project_id, run_id, cancelled, data))


@app.get('/api/projects/{project_id}/mobile/builds/{build_id}/download')
def mobile_download(project_id: str, build_id: str):
    project(project_id)
    path, item = mobile_builds.artifact(project_id, build_id)
    media = {'apk': 'application/vnd.android.package-archive'}.get(item['target'], 'application/octet-stream')
    return FileResponse(path, media_type=media, filename=item['filename'])


@app.get('/api/projects/{project_id}/mobile/builds/{build_id}/log')
def mobile_log(project_id: str, build_id: str):
    project(project_id)
    return {'log': mobile_builds.log(project_id, build_id)}


dist = config.ROOT / 'frontend/dist'
if dist.exists():
    app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')


@app.get('/')
def index():
    if not (dist / 'index.html').exists():
        return JSONResponse({'detail': 'Build the UI with ./scripts/setup.sh.'}, status_code=503)
    return FileResponse(dist / 'index.html')
