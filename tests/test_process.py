import sys
import pytest
from app.process import run, transfer


def test_host_subprocess_does_not_receive_provider_keys(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'private-key')
    assert run([sys.executable, '-c', 'import os; print(os.environ.get("OPENAI_API_KEY", "absent"))']).strip() == 'absent'


def test_command_output_is_bounded_and_ends_with_latest_logs():
    result = run([sys.executable, '-c', 'print("a"*100000); print("finished")'])
    assert len(result) <= 24000
    assert result.endswith('finished\n')


def test_nonzero_exit_surfaces_useful_error():
    with pytest.raises(RuntimeError, match='useful failure'):
        run([sys.executable, '-c', 'import sys; print("useful failure"); sys.exit(2)'])


def test_binary_database_transfer_never_enters_text_logs(tmp_path):
    path = tmp_path / 'backup.dump'
    transfer([sys.executable, '-c',
              'import sys; sys.stdout.buffer.write(b"PGDMP\\x00\\xffprivate")'],
             path, 'download')
    assert path.read_bytes() == b'PGDMP\x00\xffprivate'
    assert path.stat().st_mode & 0o777 == 0o600

    transfer([sys.executable, '-c',
              'import sys; data=sys.stdin.buffer.read(); raise SystemExit(0 if data.startswith(b"PGDMP") else 4)'],
             path, 'upload')
