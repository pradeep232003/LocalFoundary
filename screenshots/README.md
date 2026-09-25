# UI screenshots

Run `node scripts/capture-ui.mjs` on the target Mac or WSL2 Ubuntu to populate `screenshots/ui/` with
27 deterministic PNGs of the production frontend, including the v0.6 Context and
Roadmap panels, starter selector, package review, browser checks, and release view. The capture uses fixture data,
not provider keys, GitHub credentials, live projects, or database contents.

`./scripts/mac-smoke-test.sh` runs the same capture after its Docker and PostgreSQL
checks. Run `node scripts/capture-ui.mjs --accounts` for 16 additional Accounts
screens under `screenshots/accounts/`: sign-in, registration, reset request,
new password, verification, private workspace, billing, disabled payments,
people/roles, operations, audit/alerts, viewer access, empty workspace, mobile
workspace, mobile people, and mobile sign-in. The Mac smoke test runs both suites.
The Accounts suite builds the real starter UI against an in-memory fixture and
does not contact payment/email providers. The PNGs are intentionally tracked when you run `scripts/save-builder.sh`,
so the private GitHub repository can keep visual review artifacts with the code.

After reviewing the first set, run
`.venv/bin/python scripts/visual-regression.py --update` to establish
`screenshots/baseline/`. Later captures can be compared with
`.venv/bin/python scripts/visual-regression.py`; material differences are written
to `screenshots/diff/` for review.

See `VALIDATION.md` for the complete screen manifest and the distinction between
fixture-backed visual capture and the live generated-app smoke test.

No screenshot PNGs from v0.6 are supplied in this source release: this build host
has no Chrome or Docker, and the managed browser cannot open the local app.
The capture script is included so actual UI images can be produced on your Mac;
they are not substituted with design mockups.

## v0.8 Mobile controls

`mobile-v0.8/` contains actual browser captures of the production React UI with
controlled API fixtures. They cover app details, build controls, running progress,
Android download, a narrow layout, and the Mac IPA download state. No native binary
was built by this browser test. The separate accessibility JSON applies only to
the Mobile panel. The standard capture runner also includes states 28 and 29 for
mobile configuration and downloads; its other screens retain their existing gates.
