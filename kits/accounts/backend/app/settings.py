"""Runtime settings. Secrets belong in deployment configuration, never app source."""
import json
import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit


def secret(name):
    filename = os.getenv(name + '_FILE')
    if filename:
        from pathlib import Path
        return Path(filename).read_text().strip()
    return os.getenv(name, '')


def https_url(value):
    u = urlsplit(value)
    if u.scheme != 'https' or not u.hostname or u.username or u.password or u.port not in (None, 443) or u.fragment:
        raise ValueError('An HTTPS URL without credentials or a custom port is required.')
    return u


@dataclass
class Settings:
    database_url: str
    env: str = 'preview'
    origin: str = ''
    signup: bool = False
    online: bool = False
    payment_mode: str = 'off'
    stripe_key: str = ''
    stripe_webhook_secret: str = ''
    catalog: dict = field(default_factory=dict)
    resend_key: str = ''
    email_from: str = ''
    webhook_url: str = ''
    webhook_secret: str = ''
    encryption_key: str = ''
    ops_token: str = ''
    proxy: str = 'http://egress:8888'

    @property
    def production(self):
        return self.env == 'production'

    def validate(self):
        if self.env not in {'preview', 'production', 'test'}:
            raise ValueError('APP_ENV must be preview, test, or production.')
        if self.database_url.startswith('sqlite:') and self.env != 'test':
            raise ValueError('SQLite is only available to the unit test harness.')
        if self.env == 'preview' and (self.online or self.payment_mode != 'off'):
            raise ValueError('Preview integrations must stay offline.')
        if self.production:
            u = https_url(self.origin)
            if u.path or u.query:
                raise ValueError('PUBLIC_ORIGIN must contain only the HTTPS origin.')
            if len(self.ops_token) < 32:
                raise ValueError('A private OPS_TOKEN of at least 32 characters is required.')
        if self.payment_mode not in {'off', 'test', 'live'}:
            raise ValueError('PAYMENT_MODE must be off, test, or live.')
        if self.payment_mode != 'off':
            if not self.online or not self.stripe_key.startswith('sk_' + self.payment_mode + '_') or not self.stripe_webhook_secret.startswith('whsec_'):
                raise ValueError('Payments require explicit network access and matching Stripe secrets.')
        if self.online:
            from cryptography.fernet import Fernet
            Fernet(self.encryption_key.encode())
            if self.proxy != 'http://egress:8888':
                raise ValueError('Use the restricted deployment egress proxy.')
        if self.webhook_url:
            https_url(self.webhook_url)
            if len(self.webhook_secret) < 32:
                raise ValueError('The outgoing webhook signing secret must contain at least 32 characters.')
        if self.signup and self.production and not (self.online and self.resend_key and self.email_from):
            raise ValueError('Public signup requires working email verification configuration.')
        if len(self.catalog) > 20:
            raise ValueError('At most 20 products are supported.')
        for key, item in self.catalog.items():
            if (not re.fullmatch(r'[a-z0-9_-]{1,40}', key) or not isinstance(item, dict)
                or set(item) != {'name', 'price_id', 'amount', 'currency'}
                or not isinstance(item['name'], str) or not 1 <= len(item['name']) <= 100
                or not re.fullmatch(r'price_[A-Za-z0-9]+', item['price_id'])
                or type(item['amount']) is not int or not 50 <= item['amount'] <= 99999999
                or not re.fullmatch(r'[a-z]{3}', item['currency'])):
                raise ValueError('Invalid server-side product catalog.')
        return self

    @classmethod
    def from_env(cls):
        return cls(database_url=os.environ['DATABASE_URL'], env=os.getenv('APP_ENV', 'preview'),
            origin=os.getenv('PUBLIC_ORIGIN', '').rstrip('/'), signup=os.getenv('ALLOW_SIGNUP', 'false') == 'true',
            online=os.getenv('ENABLE_INTEGRATIONS', 'false') == 'true', payment_mode=os.getenv('PAYMENT_MODE', 'off'),
            stripe_key=secret('STRIPE_SECRET_KEY'), stripe_webhook_secret=secret('STRIPE_WEBHOOK_SECRET'),
            catalog=json.loads(os.getenv('PRODUCT_CATALOG', '') or '{}'), resend_key=secret('RESEND_API_KEY'),
            email_from=os.getenv('EMAIL_FROM', ''), webhook_url=os.getenv('OUTGOING_WEBHOOK_URL', ''),
            webhook_secret=secret('OUTGOING_WEBHOOK_SECRET'), encryption_key=secret('APP_ENCRYPTION_KEY'),
            ops_token=secret('OPS_TOKEN')).validate()
