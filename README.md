# Local Foundry · v0.10.1

A personal app builder for macOS and Windows 11 (WSL2): describe an app in chat, edit it with Claude,
OpenAI, or a local OpenAI-compatible model, preview it in Docker, and save the
source to a private GitHub repository. It also has read-only document research,
approval-only file organization, encrypted recovery archives, and a native macOS
app packager. The builder and generated apps use React, FastAPI, and PostgreSQL.

This is an independent starter implementation of that workflow. It does not use
Emergent's code or branding.

## New in v0.10.1 — corrected mobile release workflows

Mobile supports a testing APK, an upload-key-signed Play AAB and a signed iOS IPA.
This patch fixes AAB platform selection, upload-key verification and downloads.
App icons and listing artwork can be generated from one source image. Store
screenshot capture now isolates login sessions between devices, passes credentials
through a pipe and enforces each store's screenshot limit. See [MOBILE.md](MOBILE.md)
for setup and [VALIDATION.md](VALIDATION.md) for tested behavior and remaining
native compiler/device checks.

## New in v0.8 — mobile build and download

Open **Mobile** to build an Android testing APK or a signed iOS IPA and download
successful artifacts. The panel includes tool checks, progress, cancellation,
logs and history. Android uses installed Linux tools in WSL on Windows; IPA needs
macOS, Xcode and signing. See [MOBILE.md](MOBILE.md). Native compiler/device checks
remain required on your target computer; the UI and build-job tests passed here.

## New in v0.7 — Windows 11

The v0.7.1 download restores the complete Accounts starter omitted from the first
v0.7 archive and makes Windows `Doctor` display its diagnostic report. Release
packaging now checks required files and includes a SHA-256 source manifest.

Start with [WINDOWS.md](WINDOWS.md). `Windows.ps1` installs into WSL2 Ubuntu,
starts/stops the builder, opens the Windows browser, reports Explorer paths, and
checks offline readiness and Windows-to-WSL loopback access. Docker Desktop supplies
Linux containers. Program updates preserve a separate settings/data directory.
New Windows installations default to offline mode; setup requires a connection
to cache software/images, and local model weights must be prepared separately.

```powershell
# After WSL2 Ubuntu 24.04 + Docker Desktop prerequisites in WINDOWS.md:
.\Windows.ps1 Install
.\Windows.ps1 Start
```

Windows support uses Linux processes inside WSL2. It does not run the macOS `.app`
or require native Windows Python/Node. The launcher and regression tests are
included; actual Windows/Docker acceptance remains to be run on the target laptop.

## Included in v0.6 — priorities 1–6

1. **Acceptance evidence:** `scripts/acceptance.py` records passed, failed, and
   blocked gates separately. Real Mac/Docker/model acceptance and interactive
   provider test-account acceptance are runnable; they were not executable on
   this build host. See `acceptance-results/ACCEPTANCE.md` and `VALIDATION.md`.
2. **Persistent project memory:** the **Context** tab stores requirements,
   architecture, data model, decisions, and questions. Agent notes are separate.
   Context follows future coding sessions and encrypted recovery exports.
3. **Resumable milestones:** the **Roadmap** tab accepts up to 12 testable features.
   The agent can propose a roadmap from chat. Every feature snapshots source and
   runs validation. Completed features are skipped on resume; recorded usage and
   uncertain in-flight estimates carry forward. Interrupted work requires review.
4. **Authenticated user journeys:** Accounts projects run builder-owned security
   contracts and, with browser checks enabled, desktop/mobile registration,
   verification, private records, viewer/admin screens, billing-off and logout
   journeys against a disposable PostgreSQL stack. Evidence appears in **Visual**.
5. **More precise changes:** inspect-with-hash, atomic exact replacements, literal
   code search, and a symbol/import index help the model change existing files.
   The JavaScript index is approximate. Protected security tests are stored
   outside the editable app and cannot be weakened through the coding tools.
6. **Release operations:** Accounts releases include separate staging, exact image
   IDs, health checks, migration-compatible rollback, encrypted streaming backups,
   restore drills, scheduler templates, and an independent-host outage monitor.
   Follow the exported `OPERATIONS.md` to configure and run these on your host.

These checks cover the starter's contracts. A new product still needs its own
business acceptance tests and review; passing them is not a general security audit.
Editing accessible names or the starter's protected API contracts can fail the
trusted journey suite. Extend the builder-owned suite deliberately for such a
product change; agents cannot silently remove those checks.

### Upgrade from v0.5

Stop the builder, keep your existing private settings/data and cached images,
replace the program files, rebuild the frontend, and restart. Startup creates the
two new metadata tables without altering generated application databases. Existing
projects initially have empty Context and Roadmap panels. Interrupted plans remain
paused after a restart. Accounts projects must rerun v0.6 checks before GitHub save;
release export also requires the authenticated browser journeys. Earlier recovery
archives still import. New recovery exports include context and plans, with restored
plans paused for review. Keep prior app/recovery copies until verifying the upgrade.

```sh
.venv/bin/python scripts/acceptance.py --mode local
# On the target Mac, with cached dependencies and Docker Desktop:
.venv/bin/python scripts/acceptance.py --mode mac
# With a running builder and model; cloud choices can incur charges:
.venv/bin/python scripts/acceptance.py --mode live --provider local
```

The report exits 0 only when all listed gates pass, 1 on failure, and 2 when gates
remain blocked. Physical offline launch, live providers and independent monitoring
need evidence from your actual equipment/accounts. `PROVIDER-ACCEPTANCE.md` describes
the interactive test-account path. Local previews never enable these integrations.

## Included from v0.5

Choose **Accounts & billing** when creating a project. The original simple
notebook remains available; existing projects are not overwritten.

- **Authentication:** login/logout, verification, invitations, password resets,
  revocable HttpOnly cookie sessions, CSRF and Origin checks, and scrypt passwords.
- **Roles:** admin/member/viewer, server-side permission checks, private user
  records, session revocation after access changes, and last-administrator protection.
- **Payments:** server-priced one-time Stripe Checkout, persisted idempotency,
  signed webhooks, duplicate-event protection, delayed payment and refund state.
- **Integrations:** Resend transactional email and signed outgoing webhooks,
  encrypted delivery payloads, a separate retry worker, and visible delivery failures.
- **Public deployment:** optional Caddy HTTPS, generated private settings,
  internal PostgreSQL, and restricted outbound connections to configured providers.
- **Monitoring and security:** administrator operations/audit UI, structured
  redacted logs, private Prometheus/Alertmanager, rate limits, request limits,
  secure production cookies, CSP, and bounded container resources.

Preview remains fully disconnected with payments and integrations disabled.
Account verification/reset flows use local preview links. Public deployment
requires your own domain, server, and provider credentials; none are created or
activated by installing this release. Payments cover one-time purchases, not
subscriptions/tax/invoices. The deployment is single-host; MFA/SSO and a
product-specific security review remain separate work.

Create a preview administrator from the project's source directory:

```sh
docker compose -f ../runtime.json exec api python -m app.manage create-admin --email owner@example.com
```

The command asks privately for a password. Self-registration creates members,
never administrators. Use disposable preview credentials. For public deployment,
export a validated **Release** and follow its `DEPLOY.md`; the source version is
[release-template/DEPLOY.md](release-template/DEPLOY.md).

### Migrating an existing app

Make a recovery export, create a new Accounts & billing project, then port its
business logic using `backend/PLATFORM.md` as the contract. Existing anonymous
records have no trusted owner: write a reviewed ownership migration instead of
assigning them automatically. Extend role/ownership tests for your product. Keep
the old app and its database until the new app passes checks and you verify the
data migration. This release does not retrofit arbitrary existing code silently.

## Included from v0.4

- **Bounded automatic repair:** a failed code/build/test/browser check feeds back
  into the same coding conversation, with up to three repair attempts. All attempts
  share one cost and token meter. Infrastructure failures stop instead of triggering
  repeated paid calls. Before/after snapshots still preserve partial work.
- **Approved packages:** the agent proposes exact npm or Python package versions
  and pauses. Review them in **Packages**; registry downloads require a separate
  checkbox and are blocked by `OFFLINE_ONLY`. Packages are built into isolated,
  content-addressed runtime images. npm lifecycle scripts and Python source builds
  are disabled. The resolved npm lock and Python package inventory are recorded.
- **Visual testing:** **Visual** captures desktop/mobile screenshots, console errors,
  horizontal overflow, and bounded click/fill/visibility checks using a dedicated
  Playwright container. Browser validation is enabled by default for coding runs.
- **Screenshot feedback:** opt in under **Build controls** to let the selected model
  see preview pixels. Off by default; without it, only textual tool/check results
  reach the model. Local vision requires `LOCAL_VISION=true` and a compatible model.
- **Reviewed releases:** **Release** exports the exact validated source plus trusted
  Docker production files and a deployment checklist. Builds use cached runtime
  images, static React serving, FastAPI without reload, and a separate PostgreSQL
  volume. Nothing is deployed or made public automatically.
- **Recovery and Mac reliability:** multi-version recovery ordering is fixed;
  imported metadata commits atomically. The Mac packager caches verified wheels
  and creates a fresh Python environment at its final location. Diagnostics check
  cached images and the exact local model ID before you disconnect.

This is a tested development release, not a claim of unrestricted or production-
certified autonomous app building. See [VALIDATION.md](VALIDATION.md) for what ran
here versus the target-Mac acceptance checks still required.

## Upgrade an existing source installation

1. Stop the builder UI. Keep the existing folder, `.env`, `.data`, and Docker volumes.
   Keep an encrypted recovery export and a backup of the original installation.
2. Replace only application code with this release; never replace your private
   `.env` or `.data` with files from another installation.
3. While connected, rerun `./scripts/setup.sh` to refresh dependencies and the five
   cached images, including the Accounts runtime. This does not delete databases.
4. Start the builder. Database schema upgrades are idempotent. Run the checks on
   an existing project, inspect the screenshots, and make a recovery export.
5. Run `./scripts/mac-smoke-test.sh` before relying on the upgraded installation.

Custom additions made by manually changing the old template/runtime manifests may
need a deliberate migration. The approved package manager accepts the trusted
React/FastAPI base and exact additional dependencies, not arbitrary install hooks.

## Start on your Mac

Prerequisites: macOS 13+, Docker Desktop running with Linux containers, Python
3.12, Node.js 22, Git, and Google Chrome for the screenshot suite. GitHub CLI is
needed only for GitHub saves. Both Apple Silicon and Intel use multi-architecture
base images. For remote models, 16 GB memory is enough for one preview. For a
useful fully local coding model, 32 GB unified memory is the practical starting
point; 64 GB leaves substantially more model and Docker headroom.

If you already use Homebrew:

```bash
brew install python@3.12 node@22 gh
brew install --cask docker
# Optional document OCR:
brew install tesseract poppler
export PATH="$(brew --prefix node@22)/bin:$PATH"
open -a Docker
```

Wait for Docker Desktop to finish starting, then from this folder:

```bash
chmod +x scripts/*.sh
./scripts/setup.sh
open -e .env
```

Choose at least one AI provider in `.env`:

- For Claude or OpenAI, add the corresponding API key and select a tool-capable
  model available to your account.
- For disconnected use, start an OpenAI-compatible server on loopback, set
  `LOCAL_MODEL` to its already-downloaded tool-capable model ID, and leave
  `LOCAL_API_BASE=http://127.0.0.1:11434/v1` unless your server uses another
  loopback port/path. Set `OFFLINE_ONLY=true` to block remote AI and GitHub calls.

Keep keys out of chat and generated source. Then:

```bash
./scripts/start.sh
```

When you want GitHub saving, connect temporarily, set `OFFLINE_ONLY=false`, and
run `gh auth login` before starting the builder.

The browser opens at `http://127.0.0.1:8765` with a private launch token. If it does
not open, use the complete launch link printed in Terminal. The token is stored
in this tab's session storage, never in the preview or URL query. Keep the launch
link private. The builder runs in the foreground; Ctrl+C stops it. Preview
containers remain running until you stop them from the UI or run
`./scripts/stop-previews.sh`. Neither command deletes databases.

Setup downloads dependencies and Docker images, so run it while connected. Claude,
OpenAI, and GitHub require a connection; Local AI, document search, file plans, and
previews can run disconnected after their software, model weights, and images are
cached. `OFFLINE_ONLY=true` enforces that boundary in the backend: remote provider
and GitHub endpoints refuse to run. Local model traffic is accepted only at a
literal `127.0.0.1` or `::1` HTTP address. There is no silent provider fallback.

Prompts, selected project source, and tool results go only to the provider you
choose. The Documents agent sends cited document excerpts to that provider; use
Local AI when those excerpts must remain on the laptop. The Files agent receives
filenames, sizes, and timestamps—but never file contents. Source, chats, indexes,
recovery exports, and database volumes remain local.

## First project

1. Choose **New project** and give it a name.
2. Choose **Start preview**. The template has a working notes app backed by
   PostgreSQL; no model key is needed to try this part.
3. Add a note, stop the sandbox, and restart it to verify persistence.
4. Select **Coder** plus Claude, OpenAI, or Local AI. Open the cost/token control,
   then try: “Build a reading list with books, authors, status, and filters. Store
   everything in PostgreSQL.” Local AI has a zero API-cost budget but retains hard
   token caps.
5. Watch **Activity**, **Logs**, and **Preview**. A build is successful only after
   syntax, React, migrations, isolated database tests, backup, and health checks pass.
6. Use **Data** for validation and database backup/restore. Use **Versions** to
   restore source independently, or **Download** for a source ZIP.
7. Put local reference files in the managed documents folder, choose **Docs →
   Reindex**, then use the **Documents** agent for citation-backed answers.
8. Put files to organize in the managed files folder. Use the **Files** agent to
   draft a plan, inspect every move/trash/mkdir operation, then explicitly apply it.
   Applied plans remain undoable until the visible workspace changes.
9. Choose **Recovery** to create a password-encrypted `.lfr` archive containing
   source, versions, chat history, and a verified PostgreSQL dump.
10. While connected and with `OFFLINE_ONLY=false`, choose **Save to GitHub**,
    review every diff/conflict warning, then confirm the private-repository save.

The UI displays step-level events as the model works; this version does not stream
individual model tokens. The default per-build limits are $2 estimated cost,
180,000 cumulative input tokens, 24,000 cumulative output tokens, and 16 model
turns. Before each call it reserves a conservative prompt estimate; after each call
it records provider-reported usage. Missing usage fails closed. Retryable network,
408/409/429, and 5xx failures are retried twice with bounded backoff and visible
events. Provider billing remains authoritative, so also set account-level controls.
Only one operation per project can run at a time, with at most three active
operations overall. Run one backend process; multiple workers are not supported.

## Scoped agents

| Agent | Can inspect | Can change | Required control |
| --- | --- | --- | --- |
| Coder | Generated app source and sandbox output | Allowed source roots only | Full validation after each build |
| Documents | Managed document index and cited chunks | Nothing | Read-only; document text is treated as untrusted data |
| Files | Managed filenames, sizes, and timestamps | Nothing directly | One dry-run plan, explicit apply, recoverable trash, guarded undo |

Document citations use `relative/path#chunk-N`. Supported indexing includes text,
code, CSV, JSON, DOCX, and PDF. Images and scanned PDFs use optional Tesseract and
Poppler. The file agent is confined to its one managed folder, rejects symlinks and
collisions, and verifies a whole-workspace digest before apply or undo.

## Fully disconnected checklist

Before disconnecting:

1. Run `./scripts/setup.sh` and start every Docker image once.
2. Download a tool-capable model into your loopback OpenAI-compatible server and
   verify its `/v1/models` endpoint.
3. Set `LOCAL_MODEL`, confirm the Local AI diagnostic passes, and complete one test
   build with that provider.
4. Set `OFFLINE_ONLY=true`, restart Local Foundry, and confirm the **Offline only**
   badge appears. GitHub and remote AI are intentionally unavailable in this mode.
5. Create and download an encrypted recovery export; store its password separately.

Run `.venv/bin/python scripts/doctor.py` for the same non-secret readiness report
shown by the activity icon in the app header.

## GitHub saving

The in-app button creates a **new private repository in your personal account**
using the Mac's `gh` login. It uploads the app's text source and reusable Docker
configuration. Later saves create new commits on that same repository's default
branch. Existing unrelated repositories cannot be selected from the UI.

Every save is a two-step reviewed source snapshot. Local Foundry records the last
published source and Git head, shows added/modified/deleted diffs, preserves files
it never managed, and refuses to write if GitHub changed since the last save or
after the review. It deletes only previously managed files and never force-pushes.
The exact current source must first pass validation. A failed first upload can leave
an initialized private repository; review and retry from the same project.

Keys, chat history, `.data`, and PostgreSQL data are excluded. A basic secret-pattern
check is included, but it cannot recognize every secret or private document.
Review the source you choose to publish. Do not store private data in source files.

To save the **builder itself**, configure your Git author identity and run:

```bash
git config --global user.name "Your Name"
git config --global user.email "Your GitHub email"
./scripts/save-builder.sh local-foundry
```

GitHub saving is deliberately disabled in offline-only mode. Turn
`OFFLINE_ONLY=false`, restart, perform the reviewed save while connected, then turn
offline-only mode back on before disconnecting.

## Build the macOS app

After setup succeeds on the target Mac and Docker Desktop is running:

```bash
./scripts/build-macos-app.sh
open "release/Local Foundry.app"
```

The packager creates `release/Local Foundry.app`, applies an ad-hoc signature by
default, and embeds the five prepared Docker images so the packaged app does not
need to pull them later. Finder launches get Homebrew paths, can start Docker
Desktop, and write mutable state under
`~/Library/Application Support/Local Foundry/`. The application log is stored
there as `local-foundry.log`.

Packaging downloads binary Python wheels while connected. On first launch the app
verifies their hashes and installs them without network access into its own state
directory; it does **not** copy `.venv`. Python 3.12 and Docker Desktop must still
be installed on the target Mac. Build for that Mac's CPU architecture. Model
weights and extra project dependency images are not embedded in the base app.

Before the **first** packaged-app launch, optionally migrate an existing source
installation on the same Mac with both builder UIs stopped:

```bash
.venv/bin/python scripts/migrate-macos-state.py --source "$PWD"
```

This copies state, preserves credentials and the existing Docker database volume,
and refuses to overwrite existing packaged-app state. The original installation
is kept. Reindex documents after migration. Do not run the old and new UIs at the
same time. A fresh app installation uses a distinct builder database namespace and
available loopback port, preventing an accidental old-volume/new-password mismatch.

For Developer ID distribution, set `APPLE_SIGN_IDENTITY` to your signing identity.
If `APPLE_NOTARY_PROFILE` names a configured `notarytool` keychain profile, the
script also submits, waits, and staples. The `.app` must be built on macOS; signing
and notarization require your own Apple credentials. Build it after dependencies,
model weights, and Docker images are prepared.

## Encrypted recovery

Recovery exports use a fresh salt and nonce, Scrypt password derivation, and
streaming AES-256-GCM authenticated encryption. The plaintext staging archive is
removed after export. Import verifies archive paths and bounds, source and version
checksums, secret patterns, the PostgreSQL custom-dump header and checksum, then
creates a new project instead of overwriting an existing one. GitHub connections,
API keys, `.env`, document collections, and the general file-automation folder are
never included.

The password is never stored and cannot be reset. Keep a downloaded `.lfr` copy
away from the laptop and keep its password in a separate password manager.

## How the sandbox works

- The trusted FastAPI builder runs on your Mac and is the only component that
  invokes Docker or GitHub CLI. Model tools cannot run arbitrary host commands.
- Each generated app has frontend, backend, and PostgreSQL containers on its own
  internal Docker network. Only the frontend has a host port, bound to `127.0.0.1`.
- App containers run as non-root users, drop Linux capabilities, use read-only
  filesystems, have process/memory/CPU limits, and receive read-only app source.
  Commands can write temporary results to `/tmp`. They time out inside the container.
- Container configuration is regenerated from trusted Python code outside the
  editable source. The agent cannot change mounts, Dockerfiles, dependency
  manifests, container users, ports, or security settings.
- App containers have no provider keys, GitHub credentials, Docker socket, home
  directory, or other project's files. The app's own development database is
  accessible to its generated code; an agent can change that data.
- Schema changes use immutable, numbered SQL migrations. Backend tests and migration
  trials run against a recreated `foundry_test` database, never the preview database.
  Before validated migrations touch preview data, Local Foundry makes a verified
  custom-format `pg_dump` with a SHA-256 checksum.
- The preview runs on a different browser origin in a sandboxed iframe. The builder
  uses bearer-token authorization, Origin checks, and Host checks. The preview's
  browser content policy blocks external scripts, fetches, and assets. Docker's
  internal network also restricts container egress.

This is a container boundary for personal development, not a security guarantee
for deliberately hostile third-party workloads. Keep Docker and your operating system updated and
review generated code. Do not expose the builder or development previews publicly.

## Scope and limitations

- Focused stack: React + Vite, FastAPI + SQLAlchemy + psycopg. Additional exact
  registry packages require approval; changing frameworks or core tooling still
  requires a builder/template upgrade.
  The agent can edit `frontend/src`, `frontend/public`, `backend/app`, and
  `backend/tests`, and inspect a small set of runtime files. It can compile the
  frontend, run backend tests, read logs, and run commands in those app containers.
- Generated app source is text only; each file is at most 256 KB, with 400 files /
  5 MB per app. Document indexing is a separate read-only facility and recovery
  archives have separate verified limits. Image generation, arbitrary install
  scripts, managed-cloud deployment, and shared access to the builder are outside
  this scope. The Accounts starter supports multiple application users. Its release
  includes HTTPS, authentication, provider adapters and monitoring; configure and
  test them on your deployment before public use.
- Browser checks are evidence, not proof of complete UX correctness. They do not
  replace accessibility, security, cross-browser, or business-logic testing. The
  runner uses Docker as its isolation boundary; Chromium's additional sandbox is
  disabled inside this constrained container. It never uses your host browser
  profile and must never be repurposed for arbitrary external browsing.
- **Source rollback does not restore database data.** Use the separate **Data** view
  to create or restore database backups. A database restore first creates a
  safeguard dump, stops app containers, verifies the selected checksum, and leaves
  source unchanged.
- A builder restart marks unfinished runs as interrupted. Partial source edits
  remain available and a pre-build snapshot exists. Review before resuming.
- Logs in the UI are manually refreshed. A stored preview URL is the last start
  result; after a Docker restart choose Stop sandbox, then Start sandbox to refresh it.
- The preview policy allows embedding on builder port 8765. If you change
  `BUILDER_PORT`, update `template/frontend/vite.config.js` and rebuild the frontend
  sandbox image as well. Existing generated repos keep their original template.

## Files and backups

| Location | Contents |
| --- | --- |
| `frontend/` | Builder UI |
| `backend/app/` | API, agent loop, provider adapters, sandbox control, export |
| `template/` | Generated app starter and trusted Docker image definitions |
| `kits/accounts/` | Optional accounts, roles, billing, integrations and operations starter |
| `release-template/` | Trusted local/public deployment files and operating guide |
| `.env` | Private API keys, builder token, and builder database connection |
| `.data/projects/<id>/source/` | Actual generated app source |
| `.data/projects/<id>/snapshots/` | Local source versions |
| `.data/projects/<id>/backups/` | Private PostgreSQL dumps and checksum metadata |
| `.data/projects/<id>/recovery/` | Password-encrypted full-project `.lfr` exports |
| `.data/workspace/documents/` | User-managed inputs for the read-only document index |
| `.data/workspace/files/` | User-managed scope for reviewed file plans and recoverable trash |
| `.data/document-index.sqlite` | Local full-text index rebuilt from the documents folder |
| Docker `builder-data` volume | Builder projects, messages, runs, versions |
| Docker per-project `database` volume | Generated app data |

Back up `.data` and PostgreSQL volumes. The **Data** view creates per-project
`pg_dump` archives, but an off-device backup is still your responsibility. A
downloaded recovery archive is the portable project backup. GitHub stores source
only, not chats or database contents. Preserve the `.env` database password if you
plan to restore the builder database directly.

## Development and checks

```bash
PYTHONPATH=backend .venv/bin/python -m pytest tests -q
npm --prefix frontend run build
npm --prefix template/frontend run build
npm --prefix frontend run smoke          # server-renders App and the tool panels
npm --prefix frontend run format:check   # Prettier
ruff check .                             # optional, if ruff is installed
```

Point `FOUNDRY_TEST_DATABASE_URL` at a scratch PostgreSQL database and the same
suite runs a second time against real storage rather than the SQLite double. The
account needs CREATEDB, because the accounts kit pins its own libpq options and so
gets a throwaway database per test rather than a schema:

```bash
createdb foundry_checks
FOUNDRY_TEST_DATABASE_URL=postgresql://localhost/foundry_checks \
  PYTHONPATH=backend .venv/bin/python -m pytest tests -q
```

Expect 231 passed with the variable set and 162 passed with 73 skipped without it.
Nothing is written outside the scratch database; each test creates and drops its own
schema or database.

### Accessibility

`scripts/capture-ui.mjs` visits every primary UI state with a real browser, so it is
the only check that sees resolved CSS. It now runs axe-core (WCAG 2.1 A and AA) at each
state, plus a contrast check for text inside form controls, which axe reports as
`incomplete` rather than as a violation and therefore cannot fail on. That gap is not
theoretical: a builder field once shipped at 1.2:1 because an undefined custom property
fell back to white, and axe alone does not catch it.

Serious and critical findings fail the run; minor and moderate are recorded only.
Findings that pre-date the gate are listed in `screenshots/a11y-baseline.*.json`, so the
run fails on new regressions instead of on accumulated debt. Shrink the baseline
deliberately and regenerate it:

```bash
node scripts/capture-ui.mjs --a11y-baseline            # builder states
node scripts/capture-ui.mjs --accounts --a11y-baseline # generated accounts app
node scripts/capture-ui.mjs --no-a11y                  # screenshots only
```

Chrome is found automatically, or set `CHROME_PATH`. The current baselines hold 109
builder findings and 63 in the accounts app; the accounts app is the weaker of the two
and is the code your users actually receive.

### Android and iOS

Open a project’s **Mobile** tab to configure its deployed HTTPS origin, app name,
app ID, version and build number. **Build APK** compiles a debug-signed Android
package for device testing. **Build IPA** archives and exports a signed iOS package
on macOS, using your Apple Team ID and existing Xcode signing setup. Successful
builds show **Download APK** or **Download IPA**, a checksum, logs and build history.
Running builds can be cancelled. Missing tools and offline mode disable building
with an explanation; existing artifacts can still be downloaded.

On Windows, Android compilation runs inside WSL with Linux JDK 21+ and Android SDK
platform 36/build-tools installed. IPA compilation requires running this builder
on a Mac with Xcode 26+; a remote Mac build service is not integrated. Mobile builds
run fixed builder-owned tooling outside the preview sandbox and require explicit
permission to download native dependencies. Agent-authored build scripts are never
copied into the native build workspace.

This remains an **experimental wrapper around a deployed website**. Your API and
database stay hosted, and the mobile app needs a connection. APK/IPA output is not
proof of device compatibility or store acceptance. See `MOBILE.md` for setup,
signing and manual generator commands. Native compilation was not executable on
this build host; automated job tests use clearly identified compiler fixtures.

### Capability benchmark

`scripts/benchmark.py` measures how much the builder can actually build, which no other
check here answers. It runs a graded prompt set (`scripts/benchmark/prompts.json`)
against a running builder and a configured model, and records per case whether the build
completed, whether validation and the browser checks passed, how many automatic repairs
it needed, and what it cost.

```bash
.venv/bin/python scripts/benchmark.py --list
.venv/bin/python scripts/benchmark.py --provider local --confirm
.venv/bin/python scripts/benchmark.py --provider anthropic --tier 1 --budget 2 --confirm
```

Nothing runs without `--confirm`, because each case creates a project, executes sandbox
commands, and on a remote provider spends money. Results land in `benchmark-results/`
as JSON plus a markdown summary with a pass rate per tier.

A passing row means the build finished and the automated checks passed. It does not
mean the app is good, so each case carries a short review checklist of things only a
person can judge, printed next to its result. Run the same prompt set after upgrading a
model or changing the system prompt; the trend is the measurement, not any single run.

The automated suite covers file confinement, exact source restore layout, GitHub
diff/conflict behavior, migration immutability, backup checksums, isolated database
testing, usage budgets, provider retries, local-provider loopback enforcement,
document citations, reversible file plans, recovery encryption/import, sandbox
boundaries, and API workflows.
See `VALIDATION.md` for the checks actually performed when this starter was packaged.

For an end-to-end test on the target laptop, including a disposable Docker app,
PostgreSQL persistence across restart, isolated migrations/tests, and all UI captures:

```bash
./scripts/mac-smoke-test.sh
```

The script deletes only its uniquely named temporary containers and test volume.
It writes 27 deterministic desktop/mobile screenshots under `screenshots/ui/`.
To capture the UI alone, run `node scripts/capture-ui.mjs`. The capture server uses
fixture data and never reads `.env`, real projects, provider keys, or GitHub auth.

After reviewing an initial capture, establish the local baseline and compare later
captures:

```bash
.venv/bin/python scripts/visual-regression.py --update
.venv/bin/python scripts/visual-regression.py
```

The comparison fails when more than 0.5% of pixels change in any screen and writes
reviewable images under `screenshots/diff/`. The Mac smoke test runs this comparison
automatically when a baseline exists.

## Troubleshooting

- **Docker unavailable:** Open Docker Desktop; verify `docker info` and
  `docker compose version` in the same Terminal where you start the builder.
- **401 / locked UI:** Reopen the private launch link printed by `start.sh`.
- **Model 401/403/404:** Check `.env`, model access, and API billing, then restart.
- **Local AI unavailable:** Confirm its server is already running, `LOCAL_MODEL`
  exactly matches a listed model, and `LOCAL_API_BASE` is a literal loopback HTTP
  URL. Run `.venv/bin/python scripts/doctor.py`.
- **Document search is empty:** Copy supported files into the displayed managed
  documents folder and choose Reindex. Install Tesseract and Poppler for OCR.
- **File-plan apply/undo is blocked:** The visible managed folder changed after the
  preview/apply step. Keep the files safe and create a fresh plan; the guard is
  intentionally fail-closed.
- **Recovery import fails:** Check that the password is exact and the `.lfr` file is
  complete. Authentication/checksum failures are not bypassable.
- **Preview won't start:** Open Logs; repair the app's `/api/health` endpoint or
  restore an earlier source version. Then restart the sandbox.
- **Missing dependency:** Ask the coding agent to request exact package versions.
  Review **Packages**, approve the listed changes (with downloads only when needed),
  then continue the build. Older source snapshots automatically select their older
  dependency image tags. Keep those cached images for offline rollback. Restoring
  a recovery archive on another Mac does not also restore its Docker images.
- **Browser image missing:** Run setup while connected to cache
  `local-foundry-browser:4`. No host-browser fallback or implicit image pull occurs.
- **Package approval is stale:** Source changed after the proposal. Ask for a new
  proposal; the approval cannot silently apply to a different source version.
- **GitHub save fails:** Run `gh auth status`. Use a fresh private repository name
  on the first save; repository creation requires account permission. If a remote
  edit is reported, reconcile deliberately instead of bypassing the guard.
- **Validation fails at migration:** Never edit an applied migration. Restore its
  original contents and add a new higher-numbered SQL file for the next change.
- **Backup restore is blocked:** Preserve the dump and metadata. A checksum mismatch
  means Local Foundry intentionally refused to send that file to PostgreSQL.
- **Screenshot capture cannot find Chrome:** Install Google Chrome or set
  `CHROME_PATH` to a Chromium-compatible executable.
- **Packaged app stops:** Start Docker Desktop and inspect
  `~/Library/Application Support/Local Foundry/local-foundry.log`.
- **Port 55432 in use:** Stop the other service or edit the generated database URL
  port in `.env`, then rerun setup. Preview ports are dynamically assigned.

Official references: [OpenAI tool calling](https://developers.openai.com/api/docs/guides/function-calling),
[Anthropic tool definitions](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools),
[Docker Compose services](https://docs.docker.com/reference/compose-file/services/),
[GitHub Git trees API](https://docs.github.com/en/rest/git/trees),
[GitHub CLI authentication](https://cli.github.com/manual/gh_auth_login).
