"""Prepare public deployment configuration interactively. Does not start or publish anything."""
import argparse
import base64
import getpass
import json
import os
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit


def read_env(path):
    return dict(line.split('=', 1) for line in path.read_text().splitlines() if line and not line.startswith('#') and '=' in line)


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', required=True)
    parser.add_argument('--acme-email', required=True)
    parser.add_argument('--stripe-mode', choices=['off', 'test', 'live'], default='off')
    parser.add_argument('--enable-email', action='store_true')
    parser.add_argument('--allow-signup', action='store_true')
    parser.add_argument('--webhook-url', default='')
    args = parser.parse_args()
    domain_pattern = r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}'
    domain = args.domain.lower()
    if len(domain) > 253 or not re.fullmatch(domain_pattern, domain) or domain.endswith(('.localhost', '.local', '.internal')):
        parser.error('Use a public DNS hostname without a protocol, path, or port.')
    if not re.fullmatch(r'[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}', args.acme_email):
        parser.error('Enter a valid ACME contact email address.')
    marker = root / 'backend/foundry.json'
    accounts = marker.exists() and json.loads(marker.read_text()).get('profile') == 'accounts'
    if not accounts:
        parser.error('Public deployment preparation requires the Accounts & billing starter. Port and review your app first.')
    if args.allow_signup and not args.enable_email:
        parser.error('Public signup requires --enable-email.')
    destination = root / '.env'
    if not destination.exists():
        parser.error('Run python3 configure-release.py first.')
    settings = read_env(destination)
    if settings.get('APP_ENV') == 'production':
        parser.error('Production configuration already exists. Follow DEPLOY.md for deliberate edits; this tool will not overwrite live settings.')
    settings.update(APP_ENV='production', PUBLIC_ORIGIN='https://' + domain, APP_DOMAIN=domain, ACME_EMAIL=args.acme_email,
                    ALLOW_SIGNUP=str(args.allow_signup).lower(), PAYMENT_MODE=args.stripe_mode)
    hosts = []
    def prompt(name, prefix=''):
        value = getpass.getpass(name + ': ').strip()
        # Strict alphabet prevents Compose interpolation, shell syntax, and newline injection.
        if len(value) < 20 or not re.fullmatch(r'[A-Za-z0-9_./=+-]+', value) or (prefix and not value.startswith(prefix)):
            raise SystemExit('Invalid credential format. No configuration was changed.')
        return value
    if args.stripe_mode != 'off':
        if args.stripe_mode == 'live' and input('Type ENABLE LIVE PAYMENTS to allow real charges after deployment: ') != 'ENABLE LIVE PAYMENTS':
            raise SystemExit('Live payments were not enabled.')
        settings['STRIPE_SECRET_KEY'] = prompt('Stripe secret key', 'sk_' + args.stripe_mode + '_')
        settings['STRIPE_WEBHOOK_SECRET'] = prompt('Stripe webhook signing secret', 'whsec_')
        hosts.append('api.stripe.com')
    if args.enable_email:
        settings['RESEND_API_KEY'] = prompt('Resend API key', 're_')
        address = input('Verified sender email (address only): ').strip()
        if not re.fullmatch(r'[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}', address):
            raise SystemExit('Invalid sender address. No configuration was changed.')
        settings['EMAIL_FROM'] = address
        hosts.append('api.resend.com')
    if args.webhook_url:
        u = urlsplit(args.webhook_url)
        if (u.scheme != 'https' or not u.hostname or u.username or u.password or u.port not in (None,443) or u.fragment
            or not re.fullmatch(domain_pattern, u.hostname) or not re.fullmatch(r'https://[A-Za-z0-9./_~%-]+', args.webhook_url)):
            parser.error('Use an HTTPS webhook hostname/path without credentials, query parameters, or a custom port.')
        settings['OUTGOING_WEBHOOK_URL'] = args.webhook_url
        settings['OUTGOING_WEBHOOK_SECRET'] = secrets.token_urlsafe(32)
        hosts.append(u.hostname)
    settings['CONNECT_ALLOWED_HOSTS'] = ','.join(sorted(set(hosts)))
    settings['ENABLE_INTEGRATIONS'] = str(bool(hosts)).lower()
    settings.setdefault('APP_ENCRYPTION_KEY', base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
    settings.setdefault('OPS_TOKEN', secrets.token_urlsafe(32))
    private = root / '.secrets'
    private.mkdir(mode=0o700, exist_ok=True)
    if private.is_symlink():
        raise SystemExit('Refusing a symlink secrets directory.')
    private.chmod(0o700)
    token_path = private / 'ops-token'
    fd = os.open(token_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o444)
    os.fchmod(fd, 0o444)  # readable inside the container even when the host umask is 077
    with os.fdopen(fd, 'w') as stream:
        stream.write(settings['OPS_TOKEN'])
    temporary = root / '.env.new'
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as stream:
        for key, value in settings.items():
            stream.write(key + '=' + value + '\n')
    os.replace(temporary, destination)
    print('Prepared production settings. Nothing was published. Keep .env and .secrets private and backed up.')
    print('Configure PRODUCT_CATALOG in .env before testing payments. Follow DEPLOY.md for image transfer, DNS, startup, and checks.')
    print('Include compose.online.yaml at startup.' if hosts else 'Integrations remain disabled.')


if __name__ == '__main__':
    main()
