# v0.10.1 — 2026-09-25

- Fixed AAB builds selecting the iOS platform. Both Android targets now generate
  and sync Android, and completed AABs support authenticated, hash-checked downloads.
- Verify bundles against the selected upload keystore and alias with strict checks.
  Self-signed upload keys work without accepting unsigned, modified or differently
  signed content; passwords remain in the environment rather than command arguments.
- Store screenshot captures use a fresh browser context for each device. Screens
  within one device retain login, while cookies and storage cannot affect the next.
- Send screenshot configuration through standard input instead of writing credentials
  beside the generated images. Failure, interruption and timeout leave no copied
  credential file, and capture diagnostics redact configured fill values.
- Enforce eight screenshots per Google Play device set and ten per Apple set.
  Mixed-store configurations use the lower limit.
- Added regressions for AAB downloads, platform selection, real signature checking,
  screenshot credential handling, per-store limits and real-browser session isolation.
- Updated validation evidence; native SDK, device, Windows/WSL and macOS acceptance
  remain separate target-host checks.

# v0.10.0 — 2026-09-25

- Added app icon generation. `npx cap add` ships Capacitor's own logo at every
  density, which is an immediate store rejection; one square source image now
  produces the five Android launcher densities with round variants, adaptive
  foregrounds at 108dp with the artwork kept inside the 72dp safe zone, the adaptive
  background colour, all eleven splash buckets, and the iOS AppIcon at 1024x1024.
- The iOS icon and all listing artwork are flattened onto an opaque background,
  because the App Store rejects an icon carrying an alpha channel and the rejection
  arrives at upload rather than at build time.
- Also generates listing artwork: the 512x512 Play icon, the 1024x500 Play feature
  graphic and the 1024x1024 App Store icon.
- `harden` regenerates icons from the recorded source after a `cap add`, and `check`
  fails when any generated file no longer matches its recorded hash — the same
  pattern that already protects the manifest. If the source image changed, harden
  says so rather than silently using the old one.
- Added store screenshot capture at exact submission sizes: iPhone 6.9" 1260x2736,
  iPhone 6.5" 1284x2778, iPad 13" 2064x2752, Play phone 1080x1920 and Play 10"
  tablet 1600x2560, each from a viewport and pixel ratio chosen to land on that size
  exactly. A wrong size fails at capture instead of at upload.
- The alpha channel is stripped from every screenshot for the same reason as the
  icon, and the per-set limit of ten is enforced before Chrome is even started.
- Signed-in screens are capturable through bounded `fill`, `click` and `wait` steps
  with no arbitrary evaluation, so the demo account given to App Review can be used.
  Step values are never echoed.
- The capture origin must be the deployed HTTPS app; `--allow-local` exists only to
  verify the pipeline against loopback and says plainly that the output is not
  submittable.
- 18 new tests. Verified end to end here: icons generated against a real Capacitor
  project and checked density by density, and four device sets captured from a live
  app behind a sign-in step, then confirmed pixel-exact and alpha-free by reading the
  files back independently.

# v0.9.0 — 2026-09-24

- Added a Play Store app bundle target. The APK button produces a debug-signed
  testing build that Google Play does not accept; an .aab signed with your own
  upload key is what a Play release actually requires, and the Mobile tab now builds
  one. This closes the gap where the iOS path could reach App Store Connect and the
  Android path could not reach Play at all.
- Upload-key handling is the sensitive part, so it is constrained rather than
  trusted: the keystore is checked for JKS/PKCS#12 magic bytes before being handed to
  Gradle (an arbitrary host path is refused with a clear message, not a keystore
  exception), symlinked paths and non-absolute paths are rejected, passwords travel
  in the environment rather than argv because /proc/<pid>/cmdline is world-readable,
  the generated signing config reads them via System.getenv so nothing is written to
  a file, the build record persists the alias only, and any password echoed by a
  build tool is scrubbed from the stored log.
- The signing config is applied as a separate signing.gradle rather than patched into
  Capacitor's generated build.gradle, so a template change cannot silently skip the
  injection and leave an unsigned release.
- Bundles are verified with jarsigner -strict; apksigner cannot read an AAB. An
  unsigned bundle fails artifact inspection instead of being offered for download.
- Ten new tests, including a mutation-checked guard that fails if a password ever
  reaches a command line, and artifact checks that reject an unsigned bundle.
- Target cards now reflow for three targets, and the panel tolerates callers that
  omit the signing fields — caught by the render smoke test rather than at runtime.

# v0.8.0 — 2026-09-23

- Added a Mobile tab with Build APK and Build IPA, platform/tool checks, app and
  signing details, live job phases, cancellation, logs and authenticated downloads.
- Native builds generate a fresh trusted Capacitor 8.5.2 wrapper around a deployed
  HTTPS app. Agent source and build hooks never enter the native workspace.
- APK builds run Gradle with Android SDK/JDK and verify the debug signature. IPA
  builds use Xcode archive/export and existing Mac signing configuration. Windows
  exposes the macOS requirement instead of attempting an unsupported iOS build.
- Builds require explicit network permission and online mode. Artifacts have bounded
  sizes, SHA-256 verification and project-scoped downloads; failed or interrupted
  builds never expose downloads. Provider secrets are excluded from child processes.
- Existing preview and source-download workflows remain available. Native compiler,
  signing and device acceptance must run on the target host; this build environment
  does not have Android SDK or Xcode.

# v0.7.1 — 2026-09-22

- Restored all 19 Accounts starter files omitted from the v0.7.0 source ZIP by an
  overbroad screenshot-directory exclusion. This fixes the missing Accounts build
  context used by setup and project creation.
- Added `scripts/package-source.py`: validate required source files, exclude local
  state and generated outputs by path, include SHA-256 hashes, verify ZIP contents,
  and replace the output atomically. Optional acceptance evidence includes only
  matching-version reports and their referenced logs.
- Added regression tests that extract the archive, create an Accounts project from
  it, preserve source folders named `accounts` and `ui`, reject incomplete releases,
  and exclude private files and stale acceptance logs.
- Windows `Doctor` and successful `OfflineCheck` now display their diagnostic
  reports before the Windows localhost probe.
- Validation distinguishes checks run on this Linux host from Windows, Docker,
  browser, PostgreSQL and live-provider checks still requiring the target machine.

# v0.7.0 — 2026-09-21

- Windows 11 PowerShell entry point with WSL2 Ubuntu installation, background
  launch, authenticated Windows loopback probe, graceful stop, diagnostics,
  offline preflight, local model configuration and Explorer paths.
- Linux-side versioned installs and persistent private state. Updates copy program
  files only, normalize shell line endings, and activate after successful setup.
  Failed setup keeps the previous release selected; no database volumes are deleted.
- Optional official Node 24 LTS bootstrap with SHA-256 verification and confined
  extraction. All dependency downloads occur during explicit online installation.
- New Windows installs default to offline-only. Start uses cached images only;
  loopback model restrictions remain enforced. Added Windows/WSL acceptance mode.
- Fixed setup's external state-directory handling, made automatic browser launch
  controllable, and replaced Mac-only UI/model context with host-aware descriptions.
- Linux regression coverage for upgrade preservation, process ownership, locked
  operations, offline startup, mount confinement and unsafe archive rejection.
  Native PowerShell/WSL/Docker validation remains a target-machine gate.
- Database calls no longer replay an arbitrary statement after an ambiguous
  connection failure; the stale connection is discarded and the caller receives
  the uncertain result. This prevents duplicate writes while preserving reuse for
  healthy worker-thread connections.

# v0.6.3 — 2026-09-21

- Added scripts/mobile.py and MOBILE.md: generate an Android and iOS wrapper around a
  deployed app with Capacitor 8.5.2, for App Store and Play submission.
- Chose remote-URL mode deliberately. A bundled build runs at capacitor://localhost,
  which makes every API call cross-site: the SameSite=Lax session cookie is not sent,
  origin_check() returns 403, and the kit ships no CORS middleware, so authentication
  fails three separate ways. Loading the deployed origin keeps the WebView origin and
  the API origin identical, so nothing in the accounts kit had to be weakened.
- `harden` applies what Capacitor's template leaves at its defaults: the configured
  version (the template hardcodes 1.0), usesCleartextTraffic="false", a network
  security config denying cleartext, and allowBackup="false" so the WebView cookie
  store is not copied off the device by system backup. `npx cap add` discards all of
  it, so `check` fails when it is missing rather than letting a build reach a store.
- `check` refuses wildcard allowNavigation, cleartext, mixed content and WebView
  debugging left enabled. A wildcard would let a redirect carry the native bridge to
  another site.
- init validates the origin (HTTPS, public hostname, no path or credentials), the app
  id against both Android package and iOS bundle rules including Java reserved words,
  the name against App Store length limits, and the version shape.
- Generates an offline screen with a retry button, so a reviewer on a poor connection
  sees something rather than a blank view.
- Generates a store checklist covering Apple guideline 4.2.2 (thin wrappers) and 3.1.1
  (Stripe Checkout conflicts with the In-App Purchase requirement), Play upload keys,
  data safety and account deletion.
- Verified as far as this host allows: the generated project was accepted by the real
  Capacitor CLI and produced a valid Android project, and the hardened manifest and
  network security config parse as XML. Neither an APK nor an IPA was built — the
  Android SDK and Maven are unreachable here and an IPA requires macOS.

# v0.6.2 — 2026-09-21

- Added an accessibility gate to the UI capture. Every primary state is scanned with
  axe-core against WCAG 2.1 A and AA; serious and critical findings fail the run.
  Wired into scripts/acceptance.py as two new gates.
- Added a contrast check for text inside form controls. axe classifies inputs,
  textareas and selects as `incomplete` because it cannot resolve their background,
  so the 1.2:1 Context field fixed in v0.6.1 produced no axe violation at all. The
  new check computes the ratio from resolved styles and does catch it; verified by
  reintroducing the defect, seeing the gate fail at 1.33, and fixing it again.
- Added baselines (screenshots/a11y-baseline.*.json) so the gate fails on new
  findings rather than on 172 pre-existing ones, which would only have got it muted.
- Fixed the accounts UI capture, which had never worked: it copied a hand-listed
  subset of the template that omitted vite.config.js, losing esbuild's automatic JSX
  runtime, so every page died on "React is not defined" and all 16 states were blank.
- Fixed an unlabelled sidebar button. Below 1250px the project name is display:none,
  leaving a button of decorative icons with no accessible name; it now carries
  aria-label and aria-current.
- Fixed a teardown race that removed Chrome's profile before Chrome exited, failing
  the capture with ENOTEMPTY after all the work had been done.
- A capture that never reaches its ready state now reports the URL, title, visible
  text and recorded page errors instead of only the selector it wanted.
- Added scripts/benchmark.py and a six-case graded prompt set, to measure how much
  the builder can build rather than only whether it still works. Records outcome,
  validation, repairs, tokens and cost per case, with a per-tier pass rate and a
  manual review checklist. Requires --confirm; results in benchmark-results/.

# v0.6.1 — 2026-09-18

- Ran the whole test suite against real PostgreSQL. The `client` and accounts-kit
  fixtures are parameterized over SQLite and PostgreSQL; set FOUNDRY_TEST_DATABASE_URL
  to enable the second pass. 231 tests pass with it, 162 pass and 73 skip without it.
- Added a schema-drift guard that diffs the hand-written SQLite double against the
  schema db.init() builds, so a new table or column cannot silently lose coverage.
- Added PostgreSQL-only checks: BIGSERIAL ordering, ON CONFLICT ... RETURNING under
  concurrent writers, batch rollback, foreign-key rejection and connection reuse.
- Fixed four tests that only passed because SQLite does not enforce foreign keys;
  they emitted events for run identifiers that were never inserted.
- Replaced connect-per-statement storage access with one autocommit connection per
  worker thread, an explicit transaction for db.batch, a single reconnect on a
  dropped connection, and connection cleanup at shutdown. No new dependency.
- Rejected DTD and entity declarations before parsing DOCX XML, instead of relying
  on the amplification limit of whichever libexpat the host Python links.
- Formatted the frontend with Prettier and extracted the documents, files and
  recovery panels out of App.jsx. Rendered output was verified byte-identical to the
  previous inline markup across 12 prop combinations before the originals were removed.
- Added `npm run smoke`, a server-render check of App and the extracted panels, plus
  PostgreSQL and render-smoke gates in scripts/acceptance.py.
- Added ruff.toml; `ruff check .` is clean across backend, tests, scripts, kits and
  the release template.
- Fixed unreadable Context fields. `.continuity textarea` used `background:
  var(--surface, #fff)` with `color: inherit`, and no `--surface` is defined anywhere
  in the stylesheet, so saved requirements rendered as light text on white at about
  1.2:1 contrast. Now 12.1:1, measured in a browser. The stale light-theme fieldset
  border alongside it was corrected too.

# v0.6.0 — 2026-09-18

- Implemented the six-priority reliability upgrade: acceptance reporting, persistent
  context, resumable feature plans, authenticated journeys, guarded editing, and operations.
- Added Context and Roadmap panels, agent memory/planning tools, cumulative usage
  checkpoints, review on resume, and continuity metadata in encrypted recovery archives.
- Added SHA256-guarded atomic patches, bounded reference search, and a Python/JS index.
- Added builder-owned account/payment security contracts and disposable PostgreSQL
  desktop/mobile journeys. Accounts releases require both current v0.6 gates.
- Added immutable release image tracking, staging, health checks, compatible rollback,
  encrypted streaming backups, verified restore drills, scheduler files and an
  independently hosted outage/recovery webhook monitor.
- Added a real provider test-account runner and an explicit incomplete acceptance
  report. Expanded deterministic UI capture to 27 builder and 16 Accounts states.
- Passed 162 automated tests and all three frontend production builds. Two Docker
  tests were skipped. Mac/Docker/model/provider/deployment acceptance and screenshots
  remain blocked by this build environment and are not represented as passed.

# v0.5.0 — 2026-09-18

- Added an optional Accounts & billing starter: authentication, email verification,
  invitations, resets, revocable sessions, private records, and admin/member/viewer roles.
- Added one-time Stripe Checkout with server-side prices, idempotency, raw-body
  signature verification, atomic event deduplication, delayed payments, and refund state.
- Added encrypted Resend/webhook outbox, leasing, retry/backoff, dead deliveries,
  request metrics, audit activity, and an administrator Operations dashboard.
- Added opt-in Caddy HTTPS, private Prometheus/Alertmanager, runtime configuration,
  restricted egress proxy, and a deployment/backup/upgrade guide.
- Hardened production request/cookie boundaries and headers. Retained offline,
  no-credentials previews and explicit public deployment/provider configuration.
- Added Accounts selection to project creation, a cached Accounts API image,
  Mac packaging/readiness support, and 16 Accounts UI capture states.
- Existing apps remain unchanged. Port their logic and data into the new starter
  with explicit ownership rules; see README.md and backend/PLATFORM.md in the starter.

# v0.4.0 — 2026-09-17

## Build workflow

- Generate → validate → repair loop, up to three retries, one shared run budget.
- Infrastructure failures, cancellation, and budget exhaustion fail closed.
- Human-approved exact npm/Python packages; separate network permission; cached-image offline reuse.
- Manifest-only download/build contexts, no model source or provider credentials.
- Read-only, content-addressed runtime images; previous source versions select their previous image tags.
- Dedicated browser checks, same-origin navigation, bounded interactions, desktop/mobile artifacts.
- Explicit screenshot-sharing opt-in for OpenAI, Anthropic, or a configured local vision model.
- Reviewed production Docker bundle, static React server, migration job, generated local database password.

## Reliability

- Fixed sorting of multiple recovery snapshots; hardened malformed metadata and expanded-file bounds.
- Recovery project, chat, and version metadata commits in a single transaction.
- Mac app builds cache wheel files and verify hashes; first launch builds its own offline Python environment.
- Non-destructive source-to-app migration and separate fresh-install database names/ports.
- Offline preflight includes required images and exact model availability.
- New Packages, Visual, Release, and Build controls views; 25-state UI capture script.
- Opt-in Docker/browser/recovery/release acceptance test and separate explicitly authorized live-model smoke script.

## Still intentionally bounded

React/FastAPI/PostgreSQL remains the supported stack. No automatic public cloud deployment,
unrestricted package scripts, provider/account setup, or multi-user production security is implied.
No live Mac, Docker, provider, GitHub, or browser acceptance results are claimed from the build host.

## Implementation references

- [OpenAI image inputs](https://developers.openai.com/api/docs/guides/images-vision)
- [Anthropic vision inputs](https://platform.claude.com/docs/en/build-with-claude/vision)
- [Playwright Docker](https://playwright.dev/python/docs/docker)

These informed the image adapters and the dedicated runner, including the matching
Playwright package/image version. The runner intentionally does not use host IPC,
SYS_ADMIN, host mounts, or an existing browser profile.
