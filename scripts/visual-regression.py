#!/usr/bin/env python3
import argparse
import shutil
from pathlib import Path

from PIL import Image, ImageChops

root = Path(__file__).resolve().parents[1]
current = root / 'screenshots/ui'
baseline = root / 'screenshots/baseline'
diffs = root / 'screenshots/diff'

parser = argparse.ArgumentParser()
parser.add_argument('--update', action='store_true', help='Replace the local baseline with current captures.')
parser.add_argument('--threshold', type=float, default=0.005, help='Maximum changed-pixel fraction.')
args = parser.parse_args()

images = sorted(current.glob('*.png'))
if not images:
    raise SystemExit('No current screenshots. Run node scripts/capture-ui.mjs first.')
if args.update:
    if baseline.exists():
        shutil.rmtree(baseline)
    baseline.mkdir(parents=True)
    for image in images:
        shutil.copy2(image, baseline / image.name)
    print(f'Updated {len(images)} visual baselines in {baseline}')
    raise SystemExit(0)
if not baseline.exists():
    raise SystemExit('No visual baseline. Review captures, then run scripts/visual-regression.py --update.')

if diffs.exists():
    shutil.rmtree(diffs)
diffs.mkdir(parents=True)
failed = []
current_names = {image.name for image in images}
for expected_path in sorted(baseline.glob('*.png')):
    if expected_path.name not in current_names:
        failed.append((expected_path.name, 'capture missing for existing baseline'))
for image in images:
    expected_path = baseline / image.name
    if not expected_path.exists():
        failed.append((image.name, 'missing baseline'))
        continue
    actual, expected = Image.open(image).convert('RGBA'), Image.open(expected_path).convert('RGBA')
    if actual.size != expected.size:
        failed.append((image.name, f'size {actual.size} != {expected.size}'))
        continue
    difference = ImageChops.difference(actual, expected)
    changed = sum(1 for pixel in difference.getdata() if pixel != (0, 0, 0, 0))
    fraction = changed / (actual.width * actual.height)
    if fraction > args.threshold:
        difference.save(diffs / image.name)
        failed.append((image.name, f'{fraction:.2%} pixels changed'))
if failed:
    for name, detail in failed:
        print(f'FAIL {name}: {detail}')
    raise SystemExit(1)
print(f'Visual regression passed for {len(images)} screenshots.')
