"""Interactive account bootstrap inside the application container. Never a default password."""
import argparse
import getpass
from .db import Database, audit, now, uid
from .settings import Settings
from .security import email, hash_password


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['create-admin'])
    parser.add_argument('--email', required=True)
    args = parser.parse_args()
    address = email(args.email)
    password = getpass.getpass('New administrator password (12–128 characters): ')
    if password != getpass.getpass('Confirm password: '):
        raise SystemExit('Passwords do not match.')
    encoded = hash_password(password)
    with Database(Settings.from_env().database_url).connect() as c:
        c.lock()
        if c.one('SELECT id FROM app_users WHERE email=%s', (address,)):
            raise SystemExit('Account already exists. No changes made.')
        identifier = uid()
        c.execute('INSERT INTO app_users(id,email,password,role,verified,created_at) VALUES(%s,%s,%s,%s,1,%s)', (identifier, address, encoded, 'admin', now()))
        audit(c, 'operator', 'admin.bootstrap', identifier)
    print('Administrator created. Sign in through the app.')


if __name__ == '__main__':
    main()
