import ast
import json
import time

from . import backups, db, files, journeys, profiles, sandbox, visual


class ValidationFailed(RuntimeError):
    pass


def run(project_id, run_id, cancelled, browser_checks=False):
    checks = []
    source = sandbox.source_dir(project_id)
    source_digest = files.digest(source)
    db.query('UPDATE projects SET last_validation=NULL WHERE id=%s', (project_id,))

    def check(name, action):
        if cancelled.is_set():
            raise InterruptedError('Stopped before the next validation check.')
        db.event(run_id, 'check', name, status='running')
        started = time.monotonic()
        try:
            result = action()
        except Exception as exc:
            checks.append({'name': name, 'status': 'failed', 'detail': str(exc)[:3000]})
            db.event(run_id, 'check', name + ' failed: ' + str(exc)[:3000], status='failed')
            raise ValidationFailed(name + ' failed. Review the logs and repair or restore the app.') from exc
        checks.append({'name': name, 'status': 'passed', 'seconds': round(time.monotonic() - started, 2)})
        db.event(run_id, 'check', name + ' passed.', status='passed')
        return result

    def syntax():
        for path in files.list_files(source):
            if path.endswith('.py'):
                ast.parse(files.read(source, path), filename=path)

    try:
        check('Python syntax', syntax)
        check('React production build', lambda: sandbox.command(project_id, 'run', '--rm', '--no-deps', 'web',
            '/app/node_modules/.bin/vite', 'build', '--configLoader', 'runner', '--outDir', '/tmp/foundry-dist', timeout=120))
        check('Prepare isolated test database', lambda: sandbox.prepare_test_database(project_id))
        check('Database migrations in test database', lambda: sandbox.test_command(project_id, 'python', '/opt/foundry/runtime.py', 'migrate'))
        check('Backend tests', lambda: sandbox.test_command(project_id, 'python', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '/app/tests'))
        if profiles.get(source) == 'accounts':
            check('Protected security contracts', lambda: journeys.contracts(project_id))
        check('Preview database backup', lambda: backups.create(project_id, 'Before validated migrations'))
        check('Preview database migrations', lambda: sandbox.apply_migrations(project_id))
        url = check('Preview and database health', lambda: sandbox.start(project_id))
        if browser_checks:
            check('Desktop and mobile browser checks', lambda: visual.check(project_id))
            if profiles.get(source) == 'accounts':
                check('Authenticated user journeys', lambda: journeys.check(project_id))
        if files.digest(source) != source_digest:
            raise ValidationFailed('Source changed during validation. Run the checks again.')
        db.query('UPDATE projects SET preview_url=%s WHERE id=%s', (url, project_id))
        status = 'passed'
    except (ValidationFailed, InterruptedError):
        status = 'failed'
        raise
    finally:
        report = {'status': locals().get('status', 'failed'), 'source_digest': source_digest, 'gate_version': 6,
                  'checks': checks, 'browser_checks': browser_checks, 'created_at': db.now()}
        db.query('UPDATE projects SET last_validation=%s WHERE id=%s', (json.dumps(report), project_id))
    return report
