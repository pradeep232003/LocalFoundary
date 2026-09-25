# Validation record · v0.10.1 · 2026-09-25

This patch corrects the six issues confirmed in the v0.10.0 review. The included
`acceptance-results/acceptance.json`, `ACCEPTANCE.md` and numbered logs record the
checks run for this release. Overall acceptance remains **incomplete** because
native builds, target operating systems and external services are unavailable here.

## Verified for this patch

- **300 Python tests passed; 86 skipped** on Linux with Python 3.12. Skips require
  PostgreSQL or Docker. One Starlette/AnyIO deprecation warning is non-failing.
- AAB command tests now assert that both `cap add` and `cap sync` select Android.
  The test double no longer generates Android regardless of the requested platform.
- Authenticated AAB downloads pass the same checks as APK and IPA: successful
  response and filename, unauthenticated/origin rejection, project isolation,
  byte count, changed-content rejection and preservation of project source.
- The production bundle verifier was exercised with real disposable RSA upload
  keys and the installed OpenJDK 17 jarsigner module. It accepts the selected
  self-signed certificate and rejects a different alias, modified signed content
  and added unsigned entries. The artifact guard rejects a wholly unsigned ZIP.
  Passwords remain out of argv, saved build metadata and logs.
- Those signature fixtures are ZIP archives with test content. Native generation
  and Gradle compilation are stubbed. They are **not installable AABs** and do not
  prove Android compilation, a production JDK 21+ toolchain or Play acceptance.
- Real Chromium 153 captures a loopback test app at Android phone and tablet sizes.
  Each device signs in independently with a disposable test account; a second
  screen reuses login within that device. Both HttpOnly cookies and local storage
  are isolated. All four PNGs are read back at the expected sizes with RGB output.
- Screenshot credential tests cover success, child failure, timeout, invalid image
  output and interruption. The configuration travels through stdin; no credential
  copy is written into the screenshot output directory. Diagnostic fill values are
  redacted. The user's original configuration file remains the user's responsibility.
- Boundary tests accept eight screenshots for Play and ten for Apple, rejecting the
  next image. Mixed-store configurations use the Play limit.
- Builder, basic starter and Accounts starter React production builds pass, along
  with all ten frontend render-smoke cases. Ruff, Prettier and JavaScript syntax
  checks also pass. Chromium captured 29 builder and 16 Accounts UI states with no
  new accessibility findings against the existing baselines. Existing findings
  remain: 206 serious occurrences across builder states and 267 across Accounts
  states. This regression gate is not a clean accessibility audit or certification.

## What still requires a target host

No APK, AAB or IPA was compiled with a native SDK, installed on a device, uploaded
or submitted to a store in this environment. Android requires Node 22+, npm,
JDK 21+, SDK platform 36, build-tools and accepted SDK licenses. Use Linux tools
inside the builder's WSL distribution on Windows. AAB additionally needs jarsigner
and your upload keystore; see `MOBILE.md`.

IPA requires the builder on macOS with Xcode 26+, developer-account configuration,
certificates and provisioning. Windows/WSL cannot build an IPA locally; a remote
Mac build service is not integrated. Verify an actual build, cancellation, repeat
build, download and installation on the intended devices for every target you use.

Actual Windows 11/PowerShell/WSL2 installation, macOS launch, Docker previews,
PostgreSQL persistence, backup/restore, physically disconnected restart, live
models, GitHub, payments, deployment and external monitoring remain target-host
checks. Follow `WINDOWS.md`, `PROVIDER-ACCEPTANCE.md` and the exported operations
instructions. The automated tests do not replace those checks.

New native builds require online mode and explicit dependency-download permission.
The current Capacitor wrapper loads a deployed HTTPS site, so the mobile app needs
connectivity and its Python/PostgreSQL backend stays hosted. Remote-URL mode remains
experimental; production mobile architecture and store review are separate work.
Compilation uses fixed host tools outside the Docker preview sandbox, with a
30-minute deadline and cancellable process groups. No agent-authored native scripts
or provider API secrets enter the native workspace.

## Distribution and existing artifacts

The source packager verifies required files, including the store-screenshot runner,
and writes a SHA-256 source manifest. It includes the Accounts kit and the matching
acceptance report/logs. Private state, dependencies, signing files and generated
build outputs are excluded. Connected setup is required before disconnected
builder use. Screenshots under `screenshots/mobile-v0.8/` are historical v0.8 UI
fixtures; they are not native-build evidence for this patch.

A failed v0.10.0 screenshot capture may have left login values in
`store/screenshots/config.json`. Remove that old generated copy before sharing
an existing output folder; v0.10.1 does not create it. Keep your original
`screens.json` private when it includes sign-in values.

```bash
python3 scripts/package-source.py --output ../local-foundry-v0.10.1.zip \
  --evidence acceptance-results
```
