"""Generate an Android/iOS wrapper around a deployed Local Foundry app.

This produces a Capacitor project in **remote-URL mode**: the WebView loads your
deployed HTTPS origin directly. That choice is deliberate. Because the WebView's
origin then *is* the API origin, the accounts kit's session cookies, CSRF token and
Origin checks keep working exactly as they do in a browser. The alternative —
bundling the web build and calling the API cross-origin — would require CORS,
SameSite=None cookies and an Origin allowlist, which measurably weakens the
protections the kit ships with.

What this script does NOT do: build an APK or an IPA. It writes the project and the
platform scaffolding. Compiling needs the Android SDK, and an IPA additionally needs
macOS, Xcode and a paid Apple Developer account. Those steps run on your machine and
are described in MOBILE.md.

    python scripts/mobile.py init --origin https://app.example.com \\
        --name "Reading Room" --app-id com.example.readingroom
    python scripts/mobile.py check --output mobile-build
"""
import argparse
import datetime
import hashlib
import html
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / 'mobile' / 'template'
CAPACITOR_VERSION = '8.5.2'

# Reserved on one platform or the other; a build fails late and confusingly otherwise.
JAVA_RESERVED = {
    'abstract', 'assert', 'boolean', 'break', 'byte', 'case', 'catch', 'char', 'class',
    'const', 'continue', 'default', 'do', 'double', 'else', 'enum', 'extends', 'final',
    'finally', 'float', 'for', 'goto', 'if', 'implements', 'import', 'instanceof', 'int',
    'interface', 'long', 'native', 'new', 'package', 'private', 'protected', 'public',
    'return', 'short', 'static', 'strictfp', 'super', 'switch', 'synchronized', 'this',
    'throw', 'throws', 'transient', 'try', 'void', 'volatile', 'while', 'true', 'false', 'null',
}


class InvalidInput(Exception):
    """A configuration problem the user can fix, reported without a traceback."""


def validate_origin(value):
    """The WebView loads this origin with the native bridge attached, so anything
    weaker than a bare HTTPS origin is refused rather than warned about."""
    try:
        parsed = urlsplit((value or '').strip())
        port = parsed.port
    except ValueError as exc:
        raise InvalidInput('The origin has an invalid hostname or port.') from exc
    if parsed.scheme != 'https':
        raise InvalidInput('The origin must use https. Plain http would expose every '
                           'session cookie on the network and is blocked by both stores.')
    if not parsed.hostname:
        raise InvalidInput('The origin must include a hostname, for example https://app.example.com.')
    if parsed.path.rstrip('/') or parsed.query or parsed.fragment:
        raise InvalidInput('Give only the origin, with no path, query or fragment.')
    if parsed.username or parsed.password:
        raise InvalidInput('Credentials must not be embedded in the origin.')
    host = parsed.hostname
    if host in {'localhost', '127.0.0.1', '::1'} or host.endswith(('.local', '.localhost')):
        raise InvalidInput('A store build cannot point at localhost. Deploy the app first, '
                           'then use its public origin.')
    if re.fullmatch(r'[\d.]+', host) or ':' in host:
        raise InvalidInput('Use a hostname rather than an IP address; certificates and '
                           'app-store review both expect one.')
    try:
        host = host.encode('idna').decode('ascii')
    except UnicodeError as exc:
        raise InvalidInput('The hostname cannot be encoded as a DNS name.') from exc
    if len(host) > 253 or '.' not in host or any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label) for label in host.split('.')):
        raise InvalidInput('Use a valid public DNS hostname.')
    if port == 0:
        raise InvalidInput('The HTTPS port must be between 1 and 65535.')
    return f'https://{host}' + (f':{port}' if port and port != 443 else '')


def validate_app_id(value):
    """Must satisfy both an Android package name and an iOS bundle identifier."""
    value = (value or '').strip()
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9]*(\.[A-Za-z][A-Za-z0-9]*)+', value):
        raise InvalidInput('The app id must be reverse-DNS with at least two segments, each '
                           'starting with a letter, for example com.example.readingroom.')
    if len(value) > 155:
        raise InvalidInput('The app id is too long for an Android package name.')
    segments = value.split('.')
    reserved = sorted({segment for segment in segments if segment.lower() in JAVA_RESERVED})
    if reserved:
        raise InvalidInput(f'The app id may not contain the Java reserved word(s): {", ".join(reserved)}. '
                           'The Android build would fail on the generated package.')
    return value


def validate_name(value):
    value = (value or '').strip()
    if not 1 <= len(value) <= 30:
        raise InvalidInput('The app name must be 1–30 characters; App Store Connect '
                           'rejects anything longer.')
    if any(ord(char) < 32 for char in value):
        raise InvalidInput('The app name must not contain control characters.')
    return value


def validate_version(value):
    value = (value or '').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise InvalidInput('Use a three-part version such as 1.0.0; both stores expect one.')
    return value


def capacitor_config(name, app_id, origin, version, debuggable=False):
    """Remote-URL configuration, locked down.

    allowNavigation lists only the app's own host. A wildcard would let a redirect
    or an injected link move the WebView to another site while the Capacitor bridge
    is still attached, handing native APIs to whatever loaded next.
    """
    host = urlsplit(origin).netloc
    return {
        'appId': app_id,
        'appName': name,
        'webDir': 'www',
        'bundledWebRuntime': False,
        'version': version,
        'server': {
            'url': origin,
            # https on Android so the WebView origin matches the site's own scheme and
            # its cookies, storage and service worker registration all line up.
            'androidScheme': 'https',
            # WKWebView already owns http/https; its local fallback needs a custom scheme.
            'iosScheme': 'capacitor',
            'allowNavigation': [host],
            # Shown when the origin cannot be reached, instead of a blank screen.
            'errorPath': 'index.html',
            'cleartext': False,
        },
        'android': {
            'allowMixedContent': False,
            # Remote content plus remote debugging is a live console into a signed
            # build on someone else's phone.
            'webContentsDebuggingEnabled': bool(debuggable),
            'captureInput': False,
        },
        'ios': {
            'contentInset': 'always',
            'limitsNavigationsToAppBoundDomains': True,
            'webContentsDebuggingEnabled': bool(debuggable),
        },
        'plugins': {},
    }


def package_json(name, app_id, version):
    slug = re.sub(r'[^a-z0-9-]+', '-', name.lower()).strip('-') or 'foundry-app'
    return {
        'name': slug + '-mobile',
        'version': version,
        'private': True,
        'description': f'Mobile wrapper for {name} ({app_id})',
        'scripts': {
            'add:android': 'cap add android',
            'add:ios': 'cap add ios',
            'sync': 'cap sync',
            'open:android': 'cap open android',
            'open:ios': 'cap open ios',
            'check': 'python3 tools/mobile.py check --output .',
            'harden': 'python3 tools/mobile.py harden --output .',
        },
        'dependencies': {
            '@capacitor/core': CAPACITOR_VERSION,
            '@capacitor/android': CAPACITOR_VERSION,
            '@capacitor/ios': CAPACITOR_VERSION,
        },
        'devDependencies': {'@capacitor/cli': CAPACITOR_VERSION},
    }


def render_offline_page(name, origin):
    source = (TEMPLATE / 'www' / 'index.html').read_text(encoding='utf-8')
    initial = next((char for char in name if char.isalnum()), 'A').upper()
    return (source
            .replace('__APP_NAME__', html.escape(name, quote=True))
            .replace('__ORIGIN__', origin)
            .replace('__APP_INITIAL__', html.escape(initial, quote=True)))


def next_steps(name, app_id, origin, output):
    return f"""# {name} — mobile wrapper

Generated by `scripts/mobile.py`. The app loads **{origin}** in a native WebView.
This is an experimental remote-URL prototype. Capacitor documents `server.url` as
a live-reload option, not a production deployment mode. Static checks do not certify
a native build or store acceptance; test a production mobile architecture on devices
before shipping.
Because that is the same origin as the API, the accounts kit's session cookies, CSRF
token and Origin checks work unchanged. Nothing about the backend's security model
had to be relaxed to make this work.

App id: `{app_id}`

## Build it

```sh
cd {output.name}
npm install
npx cap add android          # needs the Android SDK
npx cap add ios              # needs macOS and Xcode
npx cap sync
npm run harden
npm run check
```

Then:

- **Android** — `npx cap open android`, or `cd android && ./gradlew assembleDebug`
  for a sideloadable build. A Play release needs an upload key; see `MOBILE.md`.
- **iOS** — `npx cap open ios`, then Product ▸ Archive in Xcode. Needs a paid Apple
  Developer account.

Re-run `npx cap sync` after changing `capacitor.config.json`. Nothing here needs
rebuilding when your website changes: the WebView loads it live.

## Before you submit

Work through `store/STORE-CHECKLIST.md`. The App Store item about guideline 4.2.2 is
the one that most often decides whether a wrapper like this is accepted.

## What is deliberately absent

No analytics, no crash reporting, no push, no third-party SDKs. Every plugin you add
gets access to the native bridge from remotely-served pages, so add them one at a
time and only when a feature needs one.
"""


def store_checklist(name, app_id, origin):
    return f"""# Store submission checklist — {name}

App id `{app_id}` · content served from {origin}

## Apple: guideline 4.2.2 is the real risk

This app shows a website in a WebView. Apple rejects submissions it judges to be
"simply a web clipping, content aggregator, or a collection of links". A remote-URL
wrapper is exactly the shape reviewers look for, so treat acceptance as something you
have to earn rather than assume.

What reduces the risk, roughly in order of how much it helps:

- [ ] Add at least one capability the website cannot provide on its own — push
      notifications, biometric unlock, camera capture, offline reading, a share
      target, or a home-screen widget. One genuinely useful native feature is worth
      more than several token ones.
- [ ] Make sure the offline screen appears instead of a blank view. Reviewers do test
      on poor connections, and a white screen reads as a broken app.
- [ ] App icon and splash generated from your own artwork\n      (`python3 scripts/mobile.py icons --source logo.png`), not Capacitor defaults.
- [ ] Respect safe areas on notched devices; no content under the status bar.
- [ ] Sign-in must work on a fresh device with the demo account you supply.

If the app has no native capability at all, expect rejection and consider shipping as
a PWA instead, which needs no review.

## Apple: the rest

- [ ] Paid Apple Developer Program membership, active.
- [ ] Bundle identifier `{app_id}` registered in the developer portal.
- [ ] App Store Connect record created, with a demo account for review.
- [ ] Privacy nutrition labels completed. Declare what the *server* collects, not just
      the app: accounts, email addresses and any payment records all count.
- [ ] Privacy policy URL that resolves publicly.
- [ ] Review current storefront-specific payment rules before exposing Stripe
      Checkout. Digital purchases may require **In-App Purchase**, with regional
      exceptions and programs. This wrapper implements neither IAP nor storefront
      policy.
      See https://developer.apple.com/app-store/review/guidelines/#payments
- [ ] Account deletion must be reachable from inside the app if it supports sign-up.
- [ ] Screenshots at every required device size\n      (`python3 scripts/mobile.py screenshots --config screens.json`), reviewed by eye\n      before upload so they represent the app honestly.
- [ ] Export compliance: the app uses HTTPS, so answer the encryption questions
      accordingly rather than skipping them.

## Google Play

- [ ] Play Console developer account, identity verification completed.
- [ ] Upload key generated and backed up. Losing it means you cannot update the app.
      Enrol in Play App Signing.
- [ ] `applicationId` `{app_id}` — permanent once published.
- [ ] `targetSdkVersion` meets Play's current minimum.
- [ ] Data safety form completed, consistent with the privacy policy.
- [ ] Account deletion route declared, including the web URL for deleting an account.
- [ ] Content rating questionnaire.
- [ ] Android App Bundle (.aab) for the store. A bare .apk is sideload-only.

## Both

- [ ] Version `1.0.0` and a build number you increment on every upload.
- [ ] Test on a real device, not only a simulator.
- [ ] Confirm sign-in, sign-out and session expiry all behave in the WebView.
- [ ] Confirm the back gesture and hardware back button behave sensibly.
"""


def do_init(args):
    origin = validate_origin(args.origin)
    app_id = validate_app_id(args.app_id)
    name = validate_name(args.name)
    version = validate_version(args.version)
    output = Path(args.output).resolve()
    if output.exists() and any(output.iterdir()) and not args.force:
        raise InvalidInput(f'{output} already exists and is not empty. Pass --force to overwrite it.')
    if not TEMPLATE.is_dir():
        raise InvalidInput(f'Missing template directory: {TEMPLATE}')

    (output / 'www').mkdir(parents=True, exist_ok=True)
    (output / 'store').mkdir(parents=True, exist_ok=True)
    config = capacitor_config(name, app_id, origin, version, debuggable=args.debuggable)
    (output / 'capacitor.config.json').write_text(json.dumps(config, indent=2) + '\n')
    (output / 'package.json').write_text(json.dumps(package_json(name, app_id, version), indent=2) + '\n')
    (output / 'www' / 'index.html').write_text(render_offline_page(name, origin), encoding='utf-8')
    (output / 'README.md').write_text(next_steps(name, app_id, origin, output), encoding='utf-8')
    (output / 'store' / 'STORE-CHECKLIST.md').write_text(store_checklist(name, app_id, origin), encoding='utf-8')
    (output / '.gitignore').write_text('node_modules/\nandroid/\nios/\nkey.properties\n*.keystore\n*.jks\n*.mobileprovision\n*.p8\n*.p12\n')
    (output / 'tools').mkdir(exist_ok=True)
    shutil.copyfile(Path(__file__), output / 'tools/mobile.py')

    print(f'Wrote {output}')
    print(f'  origin  {origin}')
    print(f'  app id  {app_id}')
    print(f'  name    {name} ({version})')
    if args.debuggable:
        print('  WARNING: WebView debugging is enabled. Never ship this to a store.')
    print('\nNext: cd', output.name, '&& npm install && npx cap add android')
    print('Read', output / 'store' / 'STORE-CHECKLIST.md', 'before submitting.')
    return 0


def do_check(args):
    """Re-validate a generated project. Catches a config edited by hand into a state
    that would ship, for example a wildcard navigation rule or debugging left on."""
    output = Path(args.output).resolve()
    config_path = output / 'capacitor.config.json'
    if not config_path.is_file():
        raise InvalidInput(f'No capacitor.config.json in {output}. Run init first.')
    config = json.loads(config_path.read_text())
    problems, notes = [], []

    server = config.get('server') or {}
    try:
        origin = validate_origin(server.get('url', ''))
    except InvalidInput as exc:
        problems.append(f'server.url: {exc}')
        origin = None
    try:
        validate_app_id(config.get('appId', ''))
    except InvalidInput as exc:
        problems.append(f'appId: {exc}')
    try:
        validate_name(config.get('appName', ''))
    except InvalidInput as exc:
        problems.append(f'appName: {exc}')

    allowed = server.get('allowNavigation') or []
    if not allowed:
        problems.append('server.allowNavigation is empty; the WebView may navigate anywhere '
                        'with the native bridge attached.')
    if any('*' in str(entry) for entry in allowed):
        problems.append(f'server.allowNavigation contains a wildcard ({allowed}); a redirect '
                        'could hand native APIs to another site. List exact hosts only.')
    if origin and allowed != [urlsplit(origin).netloc]:
        problems.append('server.allowNavigation must contain only the exact app host.')
    if server.get('iosScheme') != 'capacitor':
        problems.append('server.iosScheme must be capacitor; WKWebView cannot register http/https as local schemes.')
    if (config.get('ios') or {}).get('limitsNavigationsToAppBoundDomains') is not True:
        problems.append('ios.limitsNavigationsToAppBoundDomains must be true for this template.')
    try:
        validate_version(config.get('version', ''))
    except InvalidInput as exc:
        problems.append(f'version: {exc}')
    if server.get('cleartext'):
        problems.append('server.cleartext is true; plaintext HTTP would expose session cookies.')
    if (config.get('android') or {}).get('allowMixedContent'):
        problems.append('android.allowMixedContent is true; mixed content defeats HTTPS.')
    for platform in ('android', 'ios'):
        if (config.get(platform) or {}).get('webContentsDebuggingEnabled'):
            problems.append(f'{platform}.webContentsDebuggingEnabled is true; turn this off before '
                            'building for a store.')

    if not (output / 'www' / 'index.html').is_file():
        problems.append('www/index.html is missing; the app would show a blank screen when offline.')
    plugins = config.get('plugins') or {}
    if plugins:
        notes.append(f'{len(plugins)} plugin(s) configured. Each one is reachable from remotely '
                     'served pages through the bridge; keep the list minimal.')
    if not (output / 'android').is_dir() and not (output / 'ios').is_dir():
        notes.append('No platform added yet. Run npx cap add android (and ios on macOS).')

    # `npx cap add android` rewrites the native project and drops these, so they are
    # verified here rather than assumed to have survived the last sync.
    manifest_path = output / 'android' / 'app' / 'src' / 'main' / 'AndroidManifest.xml'
    if (output / 'android').is_dir() and not manifest_path.is_file():
        problems.append('Android native project is incomplete; its manifest is missing.')
    if manifest_path.is_file():
        try:
            application = ElementTree.parse(manifest_path).getroot().find('application')
            for key, expected in {'usesCleartextTraffic':'false', 'allowBackup':'false',
                                  'networkSecurityConfig':'@xml/network_security_config'}.items():
                if application is None or application.get(ANDROID + key) != expected:
                    problems.append(f'Android cleartext/backup protection: manifest must set android:{key}="{expected}". Run harden.')
        except ElementTree.ParseError:
            problems.append('AndroidManifest.xml is not valid XML.')
        gradle_path = output / 'android' / 'app' / 'build.gradle'
        expected = config.get('version')
        if gradle_path.is_file() and expected and f'versionName "{expected}"' not in gradle_path.read_text():
            problems.append(f'android versionName does not match the configured version '
                            f'({expected}). Run the harden command.')
        try:
            network = ElementTree.parse(output / 'android/app/src/main/res/xml/network_security_config.xml').getroot()
            bases = network.findall('base-config')
            if (network.tag != 'network-security-config' or len(bases) != 1 or
                    bases[0].get('cleartextTrafficPermitted') != 'false' or
                    any(n.get('cleartextTrafficPermitted') == 'true' for n in network.iter()) or
                    [n.get('src') for n in network.findall('.//certificates')] != ['system']):
                problems.append('Android network security config must deny all cleartext and trust system certificates only.')
        except (OSError, ElementTree.ParseError):
            problems.append('Android network_security_config.xml is missing or invalid. Run harden.')
    if (output / 'ios').is_dir():
        try:
            with (output / 'ios/App/App/Info.plist').open('rb') as stream:
                info = plistlib.load(stream)
            expected_domains = {urlsplit(origin).hostname, 'localhost'} if origin else set()
            if set(info.get('WKAppBoundDomains', [])) != expected_domains:
                problems.append('iOS Info.plist needs the app hostname and localhost in WKAppBoundDomains. Run harden.')
        except (OSError, ValueError, plistlib.InvalidFileException):
            problems.append('iOS Info.plist is missing or invalid. Add the iOS platform, then run harden.')
    # Capacitor's placeholder logo ships at every density; a store build must not carry
    # it. The manifest records what was generated, so a `cap add` that quietly restored
    # the default is caught by a hash rather than by a reviewer.
    if (output / 'android').is_dir() or (output / 'ios').is_dir():
        manifest_path = output / ICON_MANIFEST
        if not manifest_path.is_file():
            # A build with no icon source supplied is allowed to proceed — it is a
            # test build — but a store-readiness check treats the placeholder as a
            # failure, because it is a guaranteed rejection.
            message = ("App icons have not been generated, so this would ship Capacitor's "
                       'placeholder logo. Run: python3 scripts/mobile.py icons --source logo.png')
            if getattr(args, 'require_icons', True):
                problems.append(message)
            else:
                notes.append(message)
        else:
            try:
                recorded = json.loads(manifest_path.read_text()).get('files', {})
            except ValueError:
                recorded = {}
                problems.append(f'{ICON_MANIFEST} is invalid JSON. Run the icons command again.')
            stale = sorted(name for name, digest in recorded.items()
                           if not (output / name).is_file()
                           or hashlib.sha256((output / name).read_bytes()).hexdigest() != digest)
            if stale:
                problems.append(f'{len(stale)} icon file(s) no longer match the generated set, so a '
                                f'`cap add` has restored placeholders (for example {stale[0]}). '
                                'Run the icons command again.')

    for native in ('android/app/src/main/assets/capacitor.config.json', 'ios/App/App/capacitor.config.json'):
        copied = output / native
        if copied.is_file():
            try:
                native_config = json.loads(copied.read_text())
                if any(native_config.get(key) != config.get(key) for key in ('appId', 'server', 'android', 'ios')):
                    problems.append(f'{native} is stale. Run npx cap sync after changing configuration.')
            except ValueError:
                problems.append(f'{native} is invalid JSON.')

    for note in notes:
        print(f'note: {note}')
    if problems:
        for problem in problems:
            print(f'PROBLEM: {problem}', file=sys.stderr)
        print(f'\n{len(problems)} problem(s) found in {config_path}.', file=sys.stderr)
        return 1
    print(f'{config_path} passed static checks; native builds, devices and store review remain unverified.')
    return 0


NETWORK_SECURITY_CONFIG = """<?xml version="1.0" encoding="utf-8"?>
<!-- Generated by scripts/mobile.py. The app talks to exactly one HTTPS origin, so
     cleartext is denied outright rather than left to the platform default, which
     varies with targetSdkVersion and with whatever a future dependency requests. -->
<network-security-config>
    <base-config cleartextTrafficPermitted="false">
        <trust-anchors>
            <certificates src="system" />
        </trust-anchors>
    </base-config>
</network-security-config>
"""

ANDROID = '{http://schemas.android.com/apk/res/android}'
ElementTree.register_namespace('android', ANDROID[1:-1])


def harden_android(project, config):
    """Apply the parts Capacitor's template leaves at its own defaults.

    `npx cap add android` writes versionName "1.0" regardless of the configured
    version, and emits no network security config, so cleartext is governed only by
    the platform default. Both are re-applied here because `cap add` overwrites the
    native project.
    """
    android = project / 'android'
    if not android.is_dir():
        raise InvalidInput('No android/ directory. Run npx cap add android first.')
    version = validate_version(config.get('version', '1.0.0'))
    changes = []

    gradle_path = android / 'app' / 'build.gradle'
    gradle = gradle_path.read_text()
    updated = re.sub(r'versionName\s+"[^"]*"', f'versionName "{version}"', gradle, count=1)
    if updated != gradle:
        changes.append(f'versionName → {version}')
    gradle = updated

    manifest_path = android / 'app' / 'src' / 'main' / 'AndroidManifest.xml'
    manifest = ElementTree.parse(manifest_path)
    application = manifest.getroot().find('application')
    if application is None:
        raise InvalidInput('AndroidManifest.xml has no application element.')
    for key, value in {'usesCleartextTraffic':'false', 'allowBackup':'false',
                       'networkSecurityConfig':'@xml/network_security_config'}.items():
        if application.get(ANDROID + key) != value:
            application.set(ANDROID + key, value)
            changes.append('manifest: ' + key + ' → ' + value)

    xml_dir = android / 'app' / 'src' / 'main' / 'res' / 'xml'
    xml_dir.mkdir(parents=True, exist_ok=True)
    security_path = xml_dir / 'network_security_config.xml'
    if not security_path.is_file() or security_path.read_text() != NETWORK_SECURITY_CONFIG:
        security_path.write_text(NETWORK_SECURITY_CONFIG)
        changes.append('wrote res/xml/network_security_config.xml')

    gradle_path.write_text(gradle)
    manifest.write(manifest_path, encoding='utf-8', xml_declaration=True)
    return changes


def harden_ios(project, config):
    path = project / 'ios/App/App/Info.plist'
    if not path.is_file():
        raise InvalidInput('No iOS Info.plist. Run npx cap add ios on macOS first.')
    with path.open('rb') as stream:
        info = plistlib.load(stream)
    domains = sorted({urlsplit(validate_origin(config['server']['url'])).hostname, 'localhost'})
    version = validate_version(config.get('version', '1.0.0'))
    changed = info.get('WKAppBoundDomains') != domains or info.get('CFBundleShortVersionString') != version
    info.update(WKAppBoundDomains=domains, CFBundleShortVersionString=version)
    if changed:
        with path.open('wb') as stream:
            plistlib.dump(info, stream)
    return ['iOS: configured app-bound domains and version'] if changed else []


def reapply_icons(project):
    """Regenerate icons from the recorded source after a `cap add` wiped them."""
    manifest_path = project / ICON_MANIFEST
    if not manifest_path.is_file():
        return []
    manifest = json.loads(manifest_path.read_text())
    source = Path(manifest['source'])
    if not source.is_file():
        return [f'icons: source image {source} is missing; existing icons were left alone']
    if hashlib.sha256(source.read_bytes()).hexdigest() != manifest.get('source_sha256'):
        return [f'icons: {source} changed since icons were generated; run the icons command again']
    do_icons(SimpleNamespace(source=str(source), background=manifest.get('background', '#FFFFFF'),
                             output=str(project)))
    return ['icons: regenerated from ' + source.name]


def do_harden(args):
    output = Path(args.output).resolve()
    config_path = output / 'capacitor.config.json'
    if not config_path.is_file():
        raise InvalidInput(f'No capacitor.config.json in {output}. Run init first.')
    config = json.loads(config_path.read_text())
    changes = []
    if (output / 'android').is_dir():
        changes += harden_android(output, config)
    if (output / 'ios').is_dir():
        changes += harden_ios(output, config)
    if not (output / 'android').is_dir() and not (output / 'ios').is_dir():
        raise InvalidInput('Add an Android or iOS platform first.')
    changes += reapply_icons(output)
    if changes:
        for change in changes:
            print(f'applied: {change}')
    else:
        print('Native project already hardened; nothing to change.')
    print('\nRe-run this after every `npx cap add`, then run check.')
    return 0



# --- App icons, splash screens, and the store listing assets -----------------
# Capacitor's `cap add` ships its own logo at every density. Shipping that is an
# immediate rejection and an obvious branding error, so these are regenerated from
# one source image and re-applied by `harden`, which `cap add` would otherwise undo.

# Launcher icon, in px, per density bucket.
ANDROID_LAUNCHER = {'mdpi': 48, 'hdpi': 72, 'xhdpi': 96, 'xxhdpi': 144, 'xxxhdpi': 192}
# Adaptive-icon foreground is 108dp; only the middle 72dp is guaranteed visible, so
# the artwork is drawn at 72/108 of the canvas and the rest is safe-zone padding.
ANDROID_ADAPTIVE = {'mdpi': 108, 'hdpi': 162, 'xhdpi': 216, 'xxhdpi': 324, 'xxxhdpi': 432}
ADAPTIVE_SAFE_FRACTION = 72 / 108
ANDROID_SPLASH = {
    'drawable': (480, 320),
    'drawable-port-mdpi': (320, 480), 'drawable-land-mdpi': (480, 320),
    'drawable-port-hdpi': (480, 800), 'drawable-land-hdpi': (800, 480),
    'drawable-port-xhdpi': (720, 1280), 'drawable-land-xhdpi': (1280, 720),
    'drawable-port-xxhdpi': (960, 1600), 'drawable-land-xxhdpi': (1600, 960),
    'drawable-port-xxxhdpi': (1280, 1920), 'drawable-land-xxxhdpi': (1920, 1280),
}
PLAY_LISTING_ICON = 512
IOS_APP_ICON = 1024
ICON_MANIFEST = '.foundry-icons.json'


def load_source(path):
    from PIL import Image
    source = Path(path).expanduser()
    if source.is_symlink():
        raise InvalidInput('The icon source must not be a symbolic link.')
    if not source.is_file():
        raise InvalidInput(f'No icon source at {source}.')
    try:
        image = Image.open(source)
        image.load()
    except Exception as exc:
        raise InvalidInput(f'Could not read {source} as an image: {exc}') from None
    image = image.convert('RGBA')
    if min(image.size) < 512:
        raise InvalidInput(f'The icon source is {image.width}x{image.height}. Supply at least '
                           '512x512; 1024x1024 square is what both stores expect.')
    if image.width != image.height:
        raise InvalidInput(f'The icon source must be square; this one is {image.width}x{image.height}.')
    return image


def parse_colour(value):
    text = str(value).strip().lstrip('#')
    if not re.fullmatch(r'[0-9A-Fa-f]{6}', text):
        raise InvalidInput('Background colour must be a six-digit hex value such as #101510.')
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


def flatten(image, background):
    """Composite onto an opaque background.

    App Store icons must not carry an alpha channel; an upload with one is rejected
    after the build, which is a slow way to find out.
    """
    from PIL import Image
    canvas = Image.new('RGB', image.size, background)
    canvas.paste(image, mask=image.split()[3] if image.mode == 'RGBA' else None)
    return canvas


def rounded(image, background):
    from PIL import Image, ImageDraw
    size = image.size[0]
    mask = Image.new('L', (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    mask = mask.resize((size, size), Image.LANCZOS)
    circular = Image.new('RGBA', image.size, (0, 0, 0, 0))
    circular.paste(flatten(image, background).convert('RGBA'), mask=mask)
    return circular


def scaled(image, size):
    from PIL import Image
    return image.resize((size, size), Image.LANCZOS)


def write_png(image, path, digests, root):
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, 'PNG', optimize=True)
    digests[str(path.relative_to(root)).replace(os.sep, '/')] = hashlib.sha256(path.read_bytes()).hexdigest()


def generate_android_icons(project, source, background, digests):
    from PIL import Image
    res = project / 'android/app/src/main/res'
    if not res.is_dir():
        return []
    written = []
    for density, size in ANDROID_LAUNCHER.items():
        icon = scaled(source, size)
        write_png(icon, res / f'mipmap-{density}/ic_launcher.png', digests, project)
        write_png(rounded(icon, background), res / f'mipmap-{density}/ic_launcher_round.png', digests, project)
        written.append(f'mipmap-{density}')
    for density, size in ANDROID_ADAPTIVE.items():
        canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        inner = int(size * ADAPTIVE_SAFE_FRACTION)
        offset = (size - inner) // 2
        canvas.paste(scaled(source, inner), (offset, offset))
        write_png(canvas, res / f'mipmap-{density}/ic_launcher_foreground.png', digests, project)
    # The adaptive background is a flat colour resource, so it matches the launcher.
    colour = res / 'values/ic_launcher_background.xml'
    colour.parent.mkdir(parents=True, exist_ok=True)
    colour.write_text('<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
                      f'    <color name="ic_launcher_background">#{"%02X%02X%02X" % background}</color>\n'
                      '</resources>\n')
    digests['android/app/src/main/res/values/ic_launcher_background.xml'] = hashlib.sha256(colour.read_bytes()).hexdigest()
    for folder, (width, height) in ANDROID_SPLASH.items():
        canvas = Image.new('RGBA', (width, height), background + (255,))
        logo = int(min(width, height) * 0.3)
        canvas.paste(scaled(source, logo), ((width - logo) // 2, (height - logo) // 2), scaled(source, logo))
        write_png(canvas, res / folder / 'splash.png', digests, project)
    written.append('splash screens')
    return written


def generate_ios_icons(project, source, background, digests):
    app_icon = project / 'ios/App/App/Assets.xcassets/AppIcon.appiconset'
    if not (project / 'ios').is_dir():
        return []
    app_icon.mkdir(parents=True, exist_ok=True)
    # Xcode 14+ accepts a single 1024 icon and derives the rest. It must be opaque.
    icon = flatten(scaled(source, IOS_APP_ICON), background)
    path = app_icon / 'AppIcon-512@2x.png'
    path.parent.mkdir(parents=True, exist_ok=True)
    icon.save(path, 'PNG', optimize=True)
    digests[str(path.relative_to(project)).replace(os.sep, '/')] = hashlib.sha256(path.read_bytes()).hexdigest()
    contents = {'images': [{'filename': 'AppIcon-512@2x.png', 'idiom': 'universal',
                            'platform': 'ios', 'size': '1024x1024'}],
                'info': {'author': 'local-foundry', 'version': 1}}
    (app_icon / 'Contents.json').write_text(json.dumps(contents, indent=2) + '\n')
    digests['ios/App/App/Assets.xcassets/AppIcon.appiconset/Contents.json'] = \
        hashlib.sha256((app_icon / 'Contents.json').read_bytes()).hexdigest()
    return ['iOS AppIcon (opaque, 1024x1024)']


def generate_store_assets(project, source, background):
    """Listing artwork, which is uploaded to the console rather than built into the app."""
    from PIL import Image
    folder = project / 'store/assets'
    folder.mkdir(parents=True, exist_ok=True)
    flatten(scaled(source, PLAY_LISTING_ICON), background).save(folder / 'play-listing-icon-512.png', 'PNG')
    graphic = Image.new('RGB', (1024, 500), background)
    logo = 320
    art = scaled(source, logo)
    graphic.paste(art, ((1024 - logo) // 2, (500 - logo) // 2), art)
    graphic.save(folder / 'play-feature-graphic-1024x500.png', 'PNG')
    flatten(scaled(source, IOS_APP_ICON), background).save(folder / 'app-store-icon-1024.png', 'PNG')
    return folder


def do_icons(args):
    project = Path(args.output).resolve()
    config_path = project / 'capacitor.config.json'
    if not config_path.is_file():
        raise InvalidInput(f'No capacitor.config.json in {project}. Run init first.')
    background = parse_colour(args.background)
    source = load_source(args.source)
    digests = {}
    applied = generate_android_icons(project, source, background, digests)
    applied += generate_ios_icons(project, source, background, digests)
    assets = generate_store_assets(project, source, background)
    if not applied:
        raise InvalidInput('No native project found. Run npx cap add android (and ios) first.')
    manifest = {'source': str(Path(args.source).resolve()),
                'source_sha256': hashlib.sha256(Path(args.source).expanduser().read_bytes()).hexdigest(),
                'background': '#%02X%02X%02X' % background,
                'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'files': digests}
    (project / ICON_MANIFEST).write_text(json.dumps(manifest, indent=2) + '\n')
    for item in applied:
        print('wrote', item)
    print(f'wrote {len(digests)} icon file(s) and listing artwork in {assets}')
    print('\nRe-run this after every `npx cap add`, which restores Capacitor\'s placeholder logo.')
    return 0


# --- Store screenshots -------------------------------------------------------
# Capture runs in Chrome (scripts/store-screenshots.mjs) because exact pixel sizes
# need a real renderer. Everything that decides whether an upload is accepted is
# enforced here: dimensions, the absence of an alpha channel, and the per-set limit.

# Apple's required sets, from developer.apple.com/help/app-store-connect — 6.5" is
# required for iPhone unless 6.9" is supplied, and 13" is required for iPad.
STORE_DEVICES = {
    'iphone-6.9': {'label': 'iPhone 6.9"', 'pixels': (1260, 2736), 'store': 'apple'},
    'iphone-6.5': {'label': 'iPhone 6.5"', 'pixels': (1284, 2778), 'store': 'apple'},
    'ipad-13': {'label': 'iPad 13"', 'pixels': (2064, 2752), 'store': 'apple'},
    'android-phone': {'label': 'Android phone', 'pixels': (1080, 1920), 'store': 'play'},
    'android-tablet-10': {'label': 'Android 10" tablet', 'pixels': (1600, 2560), 'store': 'play'},
}
MAX_SCREENSHOTS = {'apple': 10, 'play': 8}
STEP_ACTIONS = {'fill', 'click', 'wait'}


def validate_screens_config(raw, allow_local=False):
    if not isinstance(raw, dict):
        raise InvalidInput('The screenshot configuration must be a JSON object.')
    origin = str(raw.get('origin', '')).strip()
    if allow_local and re.fullmatch(r'http://127\.0\.0\.1(:\d+)?', origin):
        pass  # Local verification only; the caller is told these are not submittable.
    else:
        origin = validate_origin(origin)
    devices = raw.get('devices') or []
    if not isinstance(devices, list) or not devices:
        raise InvalidInput('List at least one device profile. Choose from: ' + ', '.join(sorted(STORE_DEVICES)))
    unknown = [item for item in devices if item not in STORE_DEVICES]
    if unknown:
        raise InvalidInput(f'Unknown device profile(s): {", ".join(map(str, unknown))}. '
                           'Choose from: ' + ', '.join(sorted(STORE_DEVICES)))
    screens = raw.get('screens') or []
    if not isinstance(screens, list) or not screens:
        raise InvalidInput('Define at least one screen to capture.')
    for store in sorted({STORE_DEVICES[device]['store'] for device in devices}):
        limit = MAX_SCREENSHOTS[store]
        if len(screens) > limit:
            label = 'Google Play' if store == 'play' else 'App Store'
            raise InvalidInput(f'{label} accepts at most {limit} screenshots per device set; '
                               f'this configuration has {len(screens)}.')
    names = set()
    for screen in screens:
        if not isinstance(screen, dict):
            raise InvalidInput('Each screen must be an object.')
        name = str(screen.get('name', ''))
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,60}', name):
            raise InvalidInput(f'Screen name {name!r} must be short and free of path characters.')
        if name in names:
            raise InvalidInput(f'Duplicate screen name: {name}')
        names.add(name)
        path = str(screen.get('path', '/'))
        if not path.startswith('/') or '\\' in path or path.startswith('//'):
            raise InvalidInput(f'Screen {name}: path must be relative to the origin and start with /.')
        # A browser normalises these back onto the host, so they cannot leave the
        # origin, but they are always a mistake and hide what is really captured.
        if '..' in path.split('/') or '\x00' in path:
            raise InvalidInput(f'Screen {name}: path must not contain .. segments.')
        for step in screen.get('steps') or []:
            if not isinstance(step, dict) or step.get('action') not in STEP_ACTIONS:
                raise InvalidInput(f'Screen {name}: each step needs an action of '
                                   + ', '.join(sorted(STEP_ACTIONS)) + '.')
            if not 1 <= len(str(step.get('selector', ''))) <= 300:
                raise InvalidInput(f'Screen {name}:each step needs a short CSS selector.')
            if len(str(step.get('value', ''))) > 500:
                raise InvalidInput(f'Screen {name}: step values must be under 500 characters.')
    return {'origin': origin, 'devices': devices, 'screens': screens}


def finalise_screenshot(path, expected):
    """Strip the alpha channel and confirm the exact pixel size.

    Apple rejects a screenshot carrying an alpha channel, and the rejection arrives
    at upload rather than at capture, so it is removed here instead of trusted.
    """
    from PIL import Image
    with Image.open(path) as image:
        size, mode = image.size, image.mode
        flat = image.convert('RGB')
        flat.save(path, 'PNG', optimize=True)
    if size != tuple(expected):
        raise InvalidInput(f'{path.name} is {size[0]}x{size[1]}, but the store requires '
                           f'{expected[0]}x{expected[1]}. The page may have forced its own viewport.')
    return mode in {'RGBA', 'LA', 'P'}


def do_screenshots(args):
    project = Path(args.output).resolve()
    config_path = Path(args.config).expanduser()
    if not config_path.is_file():
        raise InvalidInput(f'No screenshot configuration at {config_path}.')
    try:
        raw = json.loads(config_path.read_text())
    except ValueError as exc:
        raise InvalidInput(f'{config_path} is not valid JSON: {exc}') from None
    config = validate_screens_config(raw, allow_local=args.allow_local)
    if not shutil.which('node'):
        raise InvalidInput('Node.js is required to drive the browser. Install Node 22 or newer.')

    destination = project / 'store/screenshots'
    destination.mkdir(parents=True, exist_ok=True)
    capture = Path(__file__).resolve().parent / 'store-screenshots.mjs'
    # Sign-in steps may contain credentials. Send them through a pipe, never a
    # file beside the screenshots (including on failure, timeout or interruption).
    secrets = [str(step.get('value', '')) for screen in config['screens']
               for step in screen.get('steps') or [] if step.get('action') == 'fill']
    def redacted(text):
        for secret in sorted(set(secrets), key=len, reverse=True):
            if secret:
                text = text.replace(secret, '[redacted step value]')
        return text
    try:
        result = subprocess.run(['node', str(capture), '-', str(destination)],
                                input=json.dumps(config), capture_output=True, text=True,
                                timeout=1800, check=False)
    except subprocess.TimeoutExpired:
        raise InvalidInput('Screenshot capture exceeded the 30-minute limit.') from None
    sys.stdout.write(redacted(result.stdout))
    if result.returncode:
        raise InvalidInput('Capture failed: ' + redacted(result.stderr.strip() or 'no detail').splitlines()[-1])

    manifest = json.loads((destination / 'captured.json').read_text())
    stripped, records = 0, []
    for item in manifest['written']:
        had_alpha = finalise_screenshot(Path(item['file']), item['expected'])
        stripped += int(had_alpha)
        records.append({'device': item['device'], 'screen': item['screen'],
                        'file': str(Path(item['file']).relative_to(project)),
                        'pixels': item['expected']})
    summary = {'origin': config['origin'], 'devices': config['devices'],
               'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'local_only': bool(args.allow_local), 'screenshots': records}
    (destination / 'screenshots.json').write_text(json.dumps(summary, indent=2) + '\n')

    by_device = {}
    for record in records:
        by_device.setdefault(record['device'], []).append(record)
    print()
    for device, rows in by_device.items():
        spec = STORE_DEVICES[device]
        print(f"{spec['label']}: {len(rows)} screenshot(s) at {spec['pixels'][0]}x{spec['pixels'][1]}")
    if stripped:
        print(f'Removed an alpha channel from {stripped} file(s); the stores reject it.')
    print(f'Written to {destination}')
    if args.allow_local:
        print('\nThese were captured against a local address, so they show a development build. '
              'Recapture against the deployed origin before submitting.')
    else:
        print('\nReview each one before uploading. A screenshot must show the real app, and '
              'Apple rejects submissions whose screenshots misrepresent what the app does.')
    return 0

def do_toolchain(args):
    """Report which build steps are possible here, so a missing SDK is a clear
    message rather than a Gradle stack trace twenty minutes later."""
    rows = []
    java = shutil.which('java')
    rows.append(('Java (Android builds)', java or 'missing', bool(java)))
    sdk = None
    for variable in ('ANDROID_HOME', 'ANDROID_SDK_ROOT'):
        import os
        if os.environ.get(variable) and Path(os.environ[variable]).is_dir():
            sdk = os.environ[variable]
            break
    rows.append(('Android SDK', sdk or 'missing (set ANDROID_HOME)', bool(sdk)))
    rows.append(('Android APK build', 'possible' if (java and sdk) else 'not possible here', bool(java and sdk)))
    macos = sys.platform == 'darwin'
    xcode = shutil.which('xcodebuild') if macos else None
    rows.append(('macOS', 'yes' if macos else f'no ({sys.platform})', macos))
    rows.append(('Xcode', xcode or 'missing', bool(xcode)))
    rows.append(('iOS IPA build', 'possible' if (macos and xcode) else 'not possible here', bool(macos and xcode)))
    width = max(len(label) for label, _, _ in rows)
    for label, detail, ok in rows:
        print(f'{"ok " if ok else "-- "} {label.ljust(width)}  {detail}')
    if not macos:
        print('\niOS builds require macOS and Xcode, locally or on a macOS CI host. '
              'App Store distribution also needs the appropriate Apple signing credentials.')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)

    init = sub.add_parser('init', help='Generate the mobile wrapper project.')
    init.add_argument('--origin', required=True, help='Deployed HTTPS origin, e.g. https://app.example.com')
    init.add_argument('--name', required=True, help='App name shown on the device (1-30 characters).')
    init.add_argument('--app-id', required=True, help='Reverse-DNS id, e.g. com.example.readingroom')
    init.add_argument('--version', default='1.0.0')
    init.add_argument('--output', default='mobile-build')
    init.add_argument('--force', action='store_true', help='Overwrite a non-empty output directory.')
    init.add_argument('--debuggable', action='store_true',
                      help='Enable WebView debugging. For local diagnosis only; never ship it.')
    init.set_defaults(handler=do_init)

    check = sub.add_parser('check', help='Re-validate a generated project before building.')
    check.add_argument('--output', default='mobile-build')
    check.set_defaults(handler=do_check)

    harden = sub.add_parser('harden', help='Re-apply hardening to the generated native project.')
    harden.add_argument('--output', default='mobile-build')
    harden.set_defaults(handler=do_harden)

    icons = sub.add_parser('icons', help='Generate app icons, splash screens and listing artwork.')
    icons.add_argument('--source', required=True, help='Square source image, 1024x1024 recommended.')
    icons.add_argument('--background', default='#FFFFFF',
                       help='Opaque backdrop for adaptive icons, splash screens and the iOS icon.')
    icons.add_argument('--output', default='mobile-build')
    icons.set_defaults(handler=do_icons)

    shots = sub.add_parser('screenshots', help='Capture store screenshots at exact submission sizes.')
    shots.add_argument('--config', required=True, help='JSON file listing the origin, devices and screens.')
    shots.add_argument('--output', default='mobile-build')
    shots.add_argument('--allow-local', action='store_true',
                       help='Permit an http://127.0.0.1 origin for verifying the pipeline. Not submittable.')
    shots.set_defaults(handler=do_screenshots)

    tools = sub.add_parser('toolchain', help='Report which build steps this machine can perform.')
    tools.set_defaults(handler=do_toolchain)

    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except InvalidInput as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
