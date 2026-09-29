"""Icons and store screenshots.

Both are upload-gated: a wrong pixel size or a stray alpha channel is rejected by the
store after the build, which is a slow and confusing way to find out. These check the
rules that decide acceptance, plus the guard that catches `cap add` quietly restoring
Capacitor's placeholder logo.
"""
import hashlib
import importlib.util
import json
import subprocess
from types import SimpleNamespace

import pytest
from PIL import Image

from app import config

spec = importlib.util.spec_from_file_location('foundry_mobile_assets', config.ROOT / 'scripts/mobile.py')
mobile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mobile)


def source_image(path, size=1024, mode='RGBA'):
    image = Image.new(mode, (size, size), (35, 64, 42, 255)[:len(mode)])
    for box, colour in (((size // 4, size // 4, size * 3 // 4, size * 3 // 4), (207, 224, 198, 255)),):
        Image.Image.paste(image, Image.new(mode, (box[2] - box[0], box[3] - box[1]), colour[:len(mode)]), box[:2])
    image.save(path, 'PNG')
    return path


def project_with_platforms(tmp_path, android=True, ios=True):
    project = tmp_path / 'mobile-build'
    (project).mkdir()
    (project / 'capacitor.config.json').write_text(json.dumps({'appId': 'com.example.app', 'version': '1.0.0'}))
    if android:
        (project / 'android/app/src/main/res').mkdir(parents=True)
    if ios:
        (project / 'ios/App/App').mkdir(parents=True)
    return project


def generate(project, source, background='#101510'):
    mobile.do_icons(mobile.SimpleNamespace(source=str(source), background=background, output=str(project)))


# --- icons ------------------------------------------------------------------

def test_source_image_must_be_square_and_large_enough(tmp_path):
    small = Image.new('RGBA', (256, 256)); small.save(tmp_path / 'small.png')
    with pytest.raises(mobile.InvalidInput, match='at least 512'):
        mobile.load_source(tmp_path / 'small.png')
    oblong = Image.new('RGBA', (1024, 600)); oblong.save(tmp_path / 'oblong.png')
    with pytest.raises(mobile.InvalidInput, match='square'):
        mobile.load_source(tmp_path / 'oblong.png')
    with pytest.raises(mobile.InvalidInput, match='No icon source'):
        mobile.load_source(tmp_path / 'absent.png')
    (tmp_path / 'notimage.png').write_text('not an image')
    with pytest.raises(mobile.InvalidInput, match='Could not read'):
        mobile.load_source(tmp_path / 'notimage.png')


def test_icon_source_must_not_be_a_symlink(tmp_path):
    real = source_image(tmp_path / 'real.png')
    link = tmp_path / 'link.png'
    link.symlink_to(real)
    with pytest.raises(mobile.InvalidInput, match='symbolic link'):
        mobile.load_source(link)


@pytest.mark.parametrize('value', ['red', '#12345', 'FFFFFFF', ''])
def test_background_must_be_hex(value):
    with pytest.raises(mobile.InvalidInput):
        mobile.parse_colour(value)


def test_android_icons_cover_every_density_at_the_right_size(tmp_path):
    project = project_with_platforms(tmp_path, ios=False)
    generate(project, source_image(tmp_path / 'logo.png'))
    res = project / 'android/app/src/main/res'
    for density, size in mobile.ANDROID_LAUNCHER.items():
        for name in ('ic_launcher.png', 'ic_launcher_round.png'):
            with Image.open(res / f'mipmap-{density}/{name}') as image:
                assert image.size == (size, size), f'{density}/{name}'
    for density, size in mobile.ANDROID_ADAPTIVE.items():
        with Image.open(res / f'mipmap-{density}/ic_launcher_foreground.png') as image:
            assert image.size == (size, size)
    # Every splash bucket Capacitor ships must be replaced, or a stale placeholder
    # survives at whichever density the device happens to use.
    for folder, expected in mobile.ANDROID_SPLASH.items():
        with Image.open(res / folder / 'splash.png') as image:
            assert image.size == expected, folder
    assert '#101510' in (res / 'values/ic_launcher_background.xml').read_text()


def test_adaptive_foreground_keeps_the_safe_zone(tmp_path):
    """Android masks adaptive icons to arbitrary shapes; artwork drawn to the edge of
    the 108dp canvas gets cropped on most launchers."""
    project = project_with_platforms(tmp_path, ios=False)
    generate(project, source_image(tmp_path / 'logo.png'), background='#000000')
    path = project / 'android/app/src/main/res/mipmap-xxxhdpi/ic_launcher_foreground.png'
    with Image.open(path) as image:
        assert image.size == (432, 432)
        # The outer ring must be transparent padding, not artwork.
        assert image.getpixel((4, 4))[3] == 0
        assert image.getpixel((216, 216))[3] > 0


def test_ios_icon_is_opaque_because_the_app_store_rejects_alpha(tmp_path):
    project = project_with_platforms(tmp_path)
    generate(project, source_image(tmp_path / 'logo.png'))
    icon = project / 'ios/App/App/Assets.xcassets/AppIcon.appiconset/AppIcon-512@2x.png'
    with Image.open(icon) as image:
        assert image.size == (1024, 1024)
        assert image.mode == 'RGB', 'an alpha channel fails App Store validation at upload'
    contents = json.loads((icon.parent / 'Contents.json').read_text())
    assert contents['images'][0]['size'] == '1024x1024'


def test_store_listing_artwork_is_generated_opaque(tmp_path):
    project = project_with_platforms(tmp_path)
    generate(project, source_image(tmp_path / 'logo.png'))
    expected = {'play-listing-icon-512.png': (512, 512),
                'play-feature-graphic-1024x500.png': (1024, 500),
                'app-store-icon-1024.png': (1024, 1024)}
    for name, size in expected.items():
        with Image.open(project / 'store/assets' / name) as image:
            assert image.size == size and image.mode == 'RGB', name


def test_check_flags_a_project_that_would_ship_the_placeholder_logo(tmp_path, capsys):
    project = project_with_platforms(tmp_path, ios=False)
    assert mobile.do_check(mobile.SimpleNamespace(output=str(project))) == 1
    assert 'placeholder logo' in capsys.readouterr().err


def test_check_detects_icons_restored_by_a_cap_add(tmp_path, capsys):
    project = project_with_platforms(tmp_path, ios=False)
    generate(project, source_image(tmp_path / 'logo.png'))
    overwritten = project / 'android/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png'
    Image.new('RGBA', (192, 192), (255, 0, 0, 255)).save(overwritten)
    assert mobile.do_check(mobile.SimpleNamespace(output=str(project))) == 1
    assert 'restored placeholders' in capsys.readouterr().err


def test_harden_regenerates_icons_from_the_recorded_source(tmp_path):
    project = project_with_platforms(tmp_path, ios=False)
    logo = source_image(tmp_path / 'logo.png')
    generate(project, logo)
    target = project / 'android/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png'
    before = hashlib.sha256(target.read_bytes()).hexdigest()
    Image.new('RGBA', (192, 192), (255, 0, 0, 255)).save(target)
    assert mobile.reapply_icons(project) == ['icons: regenerated from logo.png']
    assert hashlib.sha256(target.read_bytes()).hexdigest() == before


def test_harden_reports_rather_than_guesses_when_the_source_changed(tmp_path):
    project = project_with_platforms(tmp_path, ios=False)
    logo = source_image(tmp_path / 'logo.png')
    generate(project, logo)
    source_image(logo, size=800)
    assert 'run the icons command again' in mobile.reapply_icons(project)[0]
    logo.unlink()
    assert 'is missing' in mobile.reapply_icons(project)[0]


# --- store screenshots ------------------------------------------------------

def config_for(**overrides):
    base = {'origin': 'https://app.example.com', 'devices': ['iphone-6.9'],
            'screens': [{'name': '01-home', 'path': '/'}]}
    base.update(overrides)
    return base


def test_device_profiles_match_the_published_store_requirements():
    """CSS viewport times device pixel ratio must equal the required pixel size, or
    the upload is rescaled or refused."""
    from_node = {'iphone-6.9': (1260, 2736), 'iphone-6.5': (1284, 2778),
                 'ipad-13': (2064, 2752), 'android-phone': (1080, 1920),
                 'android-tablet-10': (1600, 2560)}
    for key, pixels in from_node.items():
        assert mobile.STORE_DEVICES[key]['pixels'] == pixels


def test_capture_configuration_is_validated():
    assert mobile.validate_screens_config(config_for())['origin'] == 'https://app.example.com'
    for label, cfg in [
        ('http origin', config_for(origin='http://app.example.com')),
        ('loopback origin', config_for(origin='http://127.0.0.1:8210')),
        ('unknown device', config_for(devices=['iphone-99'])),
        ('no devices', config_for(devices=[])),
        ('no screens', config_for(screens=[])),
        ('over the store limit', config_for(screens=[{'name': f'{i:02}', 'path': '/'} for i in range(11)])),
        ('duplicate names', config_for(screens=[{'name': 'a', 'path': '/'}, {'name': 'a', 'path': '/b'}])),
        ('name with path characters', config_for(screens=[{'name': '../x', 'path': '/'}])),
        ('protocol-relative path', config_for(screens=[{'name': 'a', 'path': '//evil.example'}])),
        ('dot-dot path', config_for(screens=[{'name': 'a', 'path': '/../admin'}])),
        ('arbitrary step action', config_for(screens=[{'name': 'a', 'path': '/', 'steps': [
            {'action': 'evaluate', 'selector': 'body', 'value': 'fetch("/x")'}]}])),
    ]:
        with pytest.raises(mobile.InvalidInput):
            mobile.validate_screens_config(cfg)
        assert label


def test_loopback_is_allowed_only_when_explicitly_requested():
    local = config_for(origin='http://127.0.0.1:8210')
    assert mobile.validate_screens_config(local, allow_local=True)['origin'] == 'http://127.0.0.1:8210'
    # Still not a licence to capture anything else over plaintext.
    with pytest.raises(mobile.InvalidInput):
        mobile.validate_screens_config(config_for(origin='http://example.com'), allow_local=True)


def test_finalise_strips_alpha_and_enforces_the_exact_size(tmp_path):
    path = tmp_path / 'shot.png'
    Image.new('RGBA', (1260, 2736), (255, 255, 255, 128)).save(path)
    assert mobile.finalise_screenshot(path, (1260, 2736)) is True
    with Image.open(path) as image:
        assert image.mode == 'RGB', 'Apple rejects a screenshot carrying an alpha channel'
    # A page that forces its own viewport produces the wrong size; that must fail
    # here rather than at upload.
    wrong = tmp_path / 'wrong.png'
    Image.new('RGB', (1170, 2532), 'white').save(wrong)
    with pytest.raises(mobile.InvalidInput, match='store requires'):
        mobile.finalise_screenshot(wrong, (1260, 2736))


@pytest.mark.parametrize('devices,limit', [
    (['iphone-6.9', 'ipad-13'], 10),
    (['android-phone'], 8),
    (['android-tablet-10'], 8),
    (['iphone-6.5', 'android-phone'], 8),
])
def test_screenshot_limits_follow_every_selected_store(devices, limit):
    screens = [{'name': f'screen-{i}'} for i in range(limit + 1)]
    accepted = mobile.validate_screens_config(config_for(devices=devices, screens=screens[:limit]))
    assert len(accepted['screens']) == limit
    with pytest.raises(mobile.InvalidInput, match=f'at most {limit}'):
        mobile.validate_screens_config(config_for(devices=devices, screens=screens))


@pytest.mark.parametrize('outcome', ['success', 'failure', 'timeout', 'invalid-image', 'interruption'])
def test_capture_never_writes_credentials_to_output(tmp_path, monkeypatch, capsys, outcome):
    password = 'disposable-screenshot-password'
    raw = config_for(screens=[{'name': 'home', 'steps': [
        {'action': 'fill', 'selector': '#password', 'value': password}]}])
    config_path = tmp_path / 'user-config.json'
    config_path.write_text(json.dumps(raw))
    output = tmp_path / 'mobile-build'
    monkeypatch.setattr(mobile.shutil, 'which', lambda _: '/test/node')

    def run(argv, **kwargs):
        assert argv[2] == '-'
        assert password not in ' '.join(map(str, argv))
        assert json.loads(kwargs['input']) == raw
        folder = output / 'store/screenshots'
        assert not (folder / 'config.json').exists()
        if outcome == 'failure':
            return SimpleNamespace(returncode=1, stdout=password, stderr='Page showed: ' + password)
        if outcome == 'timeout':
            raise subprocess.TimeoutExpired(argv, 1800)
        if outcome == 'interruption':
            raise KeyboardInterrupt
        image = folder / 'home.png'
        Image.new('RGBA', (16, 16) if outcome == 'invalid-image' else (1260, 2736)).save(image)
        (folder / 'captured.json').write_text(json.dumps({'written': [
            {'file': str(image), 'device': 'iphone-6.9', 'screen': 'home', 'expected': [1260, 2736]}]}))
        return SimpleNamespace(returncode=0, stdout=password, stderr='')

    monkeypatch.setattr(mobile.subprocess, 'run', run)
    args = SimpleNamespace(config=str(config_path), output=str(output), allow_local=False)
    if outcome == 'success':
        assert mobile.do_screenshots(args) == 0
    else:
        with pytest.raises(KeyboardInterrupt if outcome == 'interruption' else mobile.InvalidInput) as error:
            mobile.do_screenshots(args)
        assert password not in str(error.value)
    captured = capsys.readouterr()
    assert password not in captured.out + captured.err
    assert not (output / 'store/screenshots/config.json').exists()
    for path in output.rglob('*.json'):
        assert password not in path.read_text()
