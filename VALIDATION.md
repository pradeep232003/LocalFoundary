# Validation record · v0.11.0 · 2026-09-29

Reviewed base: `d48ce2248a3fc02e5235bbf1878bfa3556106b0a`.
This release restores the actual engine removed by the September Express prototype.
The earlier release's validation totals are not evidence for this rewrite.

## Checks run on this revision

- GitHub Actions on code commit `6b262fb9b120690eeb78334131bf5df7936fe242`:
  **396 Python tests passed, 4 skipped**, using PostgreSQL 16 as well as the
  SQLite test double. Both branch and pull-request checks passed. The four skips
  are the two opt-in live Docker acceptance tests in both storage configurations.
  [Verified CI run](https://github.com/pradeep232003/LocalFoundary/actions/runs/36548423394).
- Local restricted-host Python 3.12 suite: **300 passed, 100 skipped**. Its storage
  tests use a file-backed SQLite test double; PostgreSQL coverage comes from CI.
- `npm test`: **2 passed**, covering workspace-token forwarding, binary requests,
  and rejecting unauthenticated responses/downloads.
- `npm run build`: TypeScript check and Vite production build passed.
- `npm --prefix frontend run smoke`: **5 views rendered** (builder, Agent Studio,
  source search, project settings, workspace unlock).
- `ruff check backend scripts tests`: passed.
- Source packaging verifies required files, ZIP integrity and per-file SHA-256 values.
  Release archives generate their own current `SOURCE-MANIFEST.json`; a stale
  manifest is no longer committed at the repository root.

Regression coverage specifically checks unauthenticated access and hostile origins;
real SQLite integrity, rows, persisted configuration and source-change reindexing;
nonexistent mobile downloads, incomplete native requests and invalid recovery input;
failed-closed retailer verification; and project/source reads through a new API client.
Existing suites cover model tool dispatch, bounded edits, sandbox configuration,
GitHub conflicts, encryption/tampering, mobile signing guards, downloads and cancellation.
External commands and services are substituted in unit tests unless a test explicitly
requires a live dependency. A passing unit test does not demonstrate an installable app.

## Remaining environment-dependent acceptance

This host does not provide PostgreSQL, Docker, Windows/WSL2, macOS/Xcode, an Android
SDK or configured model/GitHub provider accounts for the application. Those live
checks are skipped, not reported as passes. One WSL process-termination integration
test also skips because this host blocks reading the required `/proc` identity files;
the stale-PID rejection test still runs using controlled identities.

Chromium 153 reports its version but exits with SIGTRAP before rendering in this
restricted host. Browser screenshots, CSS/layout and interactive browser acceptance
are therefore **not verified on this revision**. Historical screenshots in the
repository are not current acceptance evidence.

CI passed the real database paths, frontend tests/build/render checks, Python lint
and source archive verification. These are not a substitute for the opt-in live
Docker gates. Run `scripts/acceptance.py` and the mobile/provider checklists on the
target laptop before treating the release as accepted. No application was deployed
and no APK, AAB or IPA was compiled here.

The legacy Firestore rules were hardened in source, but have **not been deployed or
run against a Firebase emulator**. The current builder removes the Firebase client
and uses the local backend token. Existing Firebase installations must separately
apply and validate the rules and remove any previously forged privileged profile data.
