# Mobile build and download · v0.10.1

`scripts/mobile.py` generates an Android/iOS wrapper prototype around a **deployed**
Local Foundry app. The standalone generator does not compile binaries; the Mobile tab runs the native build tools described below.

Capacitor documents `server.url` as a live-reload option that is not intended for
production. Keep this prototype separate from a claim of store readiness; choose and
test a production mobile architecture before shipping. See the
[Capacitor configuration docs](https://capacitorjs.com/docs/config).

Read the two constraints below before starting. Both are load-bearing.

## 1. The app must be deployed first

The wrapper does not contain your app. It opens your deployed HTTPS origin in a
native WebView. So the order is: export a **Release**, deploy it following
`DEPLOY.md`, confirm it works in a normal browser, and only then generate the mobile
project. Pointing the wrapper at `localhost` is refused, because a store build that
does that is broken on every device but yours.

## 2. Why remote content, and not a bundled build

The obvious approach is to bundle the compiled React app inside the native app and
have it call your API. It is also the one that quietly breaks authentication.

The accounts kit authenticates with an `HttpOnly` session cookie set `SameSite=Lax`,
verifies an `Origin` header against your configured public origin, and requires a
CSRF token on every mutating request. A bundled app runs at `capacitor://localhost`,
so every API call is **cross-site**:

- the session cookie is not sent at all, because `SameSite=Lax` forbids it;
- `origin_check()` rejects the request with 403, because the Origin is not your
  configured origin;
- the kit ships no CORS middleware, so the browser discards the response anyway.

Making that work means `SameSite=None` cookies, a CORS allowlist, and accepting a
non-web Origin — which removes the cross-site protections the kit is built around
and leaves the CSRF token as the only remaining layer.

Loading the deployed origin directly avoids all of it. The WebView's origin *is* the
API origin, so cookies, CSRF and Origin checks behave exactly as they do in a
browser, and **no backend change is required**. That is the trade this tool makes.

The cost is that the app needs a connection. `scripts/mobile.py` generates an offline
screen with a retry button so that a reviewer on a bad connection sees something
sensible instead of a blank white view.

## Generate the project

```sh
python3 scripts/mobile.py toolchain     # what this machine can build

python3 scripts/mobile.py init \
    --origin https://app.example.com \
    --name "Reading Room" \
    --app-id com.example.readingroom \
    --version 1.0.0 \
    --output mobile-build
```

The app id is permanent once published on either store, so choose it deliberately. It
must be reverse-DNS on a domain you control.

```sh
cd mobile-build
npm install
npx cap add android
npx cap add ios                         # macOS only
cd .. && python3 scripts/mobile.py harden --output mobile-build
python3 scripts/mobile.py check --output mobile-build
```

`harden` applies what Capacitor's template leaves at its defaults: your version
number (the template hardcodes `1.0`), `usesCleartextTraffic="false"`, a network
security config that denies cleartext outright, and `allowBackup="false"` so the
WebView's cookie store is not copied off the device by system backup.

**`npx cap add` rewrites the native project and discards all of that**, so run
`harden` again after any `cap add`. `check` fails if it is missing, which is there to
stop a build going to a store without it.

## Build

### Android

Two different artifacts, for two different purposes:

| Target | Signing | Where it goes |
| --- | --- | --- |
| **APK** | Debug key, generated automatically | Sideloading onto test devices. **Play will not accept it.** |
| **AAB** | Your own upload key | Google Play |

The Mobile tab builds both. From the command line:

```sh
cd mobile-build/android
./gradlew assembleDebug                 # sideloadable APK
./gradlew bundleRelease                 # AAB for Play, needs the signing config
```

Needs a JDK (including `jarsigner`, which verifies bundle signatures; `apksigner`
cannot read an AAB) and the Android SDK with `ANDROID_HOME` set.

#### Creating the upload key

Do this once. Losing this key means you cannot ship updates to an existing listing,
so back it up somewhere durable and separate from the project.

```sh
keytool -genkeypair -v -keystore upload.jks -keyalg RSA -keysize 2048 \
    -validity 10000 -alias upload
```

Enrol in Play App Signing when you first upload. Google then holds the app signing
key and re-signs your uploads, so this key only ever proves the upload is yours.

#### How the builder uses it

Give the Mobile tab the keystore path, the alias and the password. Then:

- the file is read in place during the build and never copied, moved or uploaded;
- passwords are passed to Gradle through the **environment**, not the command line,
  because `/proc/<pid>/cmdline` is world-readable while `/proc/<pid>/environ` is not;
- the generated signing config reads `System.getenv(...)`, so no password is written
  to any file;
- the build record stores the alias only, never a password;
- anything a build tool echoes is scrubbed from the log before it is stored;
- the finished bundle is verified with `jarsigner -verify -strict` against the selected
  upload keystore and alias. Self-signed upload certificates are supported; unsigned
  entries, tampering and a different signing alias still fail. The verifier receives
  the password via `-storepass:env`, never as a command-line value.

None of that protects a keystore you commit to a repository. `key.properties`,
`*.jks`, `*.p12` and `*.keystore` are gitignored in the generated project.

### iOS

```sh
npx cap open ios
```

Then Product ▸ Archive in Xcode, and distribute through the Organizer.

iOS builds require macOS and Xcode, on your Mac or a macOS CI runner. App Store
distribution also requires the appropriate Apple Developer membership and signing
credentials. Windows/WSL does not supply this toolchain. The generator uses the
supported `capacitor` local iOS scheme; `harden` adds the remote hostname and
`localhost` to `WKAppBoundDomains`, while `check` detects missing entries.

## App icons and splash screens

`npx cap add` ships **Capacitor's own logo** at every density. Shipping that is an
obvious branding error and an immediate rejection, so generate your own from one
square source image, 1024x1024 recommended:

```sh
python3 scripts/mobile.py icons --source logo.png --background '#101510' \
    --output mobile-build
```

That writes, from the one source:

- Android launcher icons at all five densities, plus round variants;
- adaptive-icon foregrounds at 108dp with the artwork inside the 72dp safe zone, so
  a launcher that masks to a circle or squircle does not crop it;
- the adaptive background colour resource;
- every splash bucket Capacitor ships, portrait and landscape;
- the iOS `AppIcon.appiconset` at 1024x1024, **flattened onto an opaque
  background** because the App Store rejects an icon with an alpha channel;
- listing artwork in `store/assets/`: the 512x512 Play icon, the 1024x500 Play
  feature graphic, and the 1024x1024 App Store icon.

`npx cap add` restores the placeholders, so `harden` regenerates icons from the
recorded source and `check` fails if any generated file no longer matches. If you
change the source image, run the icons command again; `harden` will say so rather
than silently using the old one.

## Store screenshots

```sh
python3 scripts/mobile.py screenshots --config screens.json --output mobile-build
```

`screens.json` names the deployed origin, the device profiles and the screens.
Apple device sets allow up to ten screenshots; Google Play device sets allow eight.
A configuration containing both stores is limited to eight screens.

```json
{
  "origin": "https://app.example.com",
  "devices": ["iphone-6.9", "ipad-13", "android-phone"],
  "screens": [
    {"name": "01-sign-in", "path": "/", "wait": ".auth-card"},
    {"name": "02-workspace", "path": "/", "wait": ".notes article", "steps": [
      {"action": "fill", "selector": "input[type=email]", "value": "demo@example.com"},
      {"action": "fill", "selector": "input[type=password]", "value": "…"},
      {"action": "click", "selector": "button[type=submit]"}
    ]}
  ]
}
```

Steps are limited to `fill`, `click` and `wait` — there is no arbitrary evaluation —
and they exist so signed-in screens can be captured with the same demo account you
give App Review. Values are never echoed to the console.

Each device starts with its own clean browser context. Screens within that device
share the signed-in session, so log in on the first protected screen and reuse it
on later screens. Cookies and browser storage do not carry over to the next device.
The capture configuration is passed to Node through standard input; login values
are never copied into the screenshot output directory, including after a failure.
Keep your original `screens.json` private. If a v0.10.0 capture failed, remove its
leftover `store/screenshots/config.json` before sharing that output folder.

Capture runs in Chrome at a viewport and pixel ratio chosen so the output is exactly
the chosen device profile size, and the alpha channel is stripped afterwards:

| Profile | Output | Where it is required |
| --- | --- | --- |
| `iphone-6.9` | 1260x2736 | iPhone, if supplied, becomes the primary set |
| `iphone-6.5` | 1284x2778 | iPhone, required unless 6.9" is supplied |
| `ipad-13` | 2064x2752 | required if the app runs on iPad |
| `android-phone` | 1080x1920 | Play phone listing |
| `android-tablet-10` | 1600x2560 | Play tablet listing |

Wrong sizes fail at capture rather than at upload. Confirm the current requirements
at [Apple's screenshot specifications](https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications/),
since they change with each device generation.

Two limits worth knowing. The origin must be your deployed HTTPS app — `--allow-local`
exists only to verify the pipeline against `http://127.0.0.1` and prints a warning
that the results are not submittable. And an automated capture is a starting point,
not a finished asset: Apple expects screenshots to represent the app honestly, and
most listings want captions and framing added afterwards.

## Before you submit

`mobile-build/store/STORE-CHECKLIST.md` is generated with your app's details filled
in. Two items there are worth repeating because they sink submissions:

**Apple guideline 4.2.2.** Apple rejects apps it considers "simply a web clipping".
A WebView wrapper is precisely that shape, so plan to add at least one real native
capability — push notifications, biometric unlock, camera capture, a share target —
before submitting. Each Capacitor plugin you add is reachable from your remotely
served pages through the native bridge, so add them one at a time and only where a
feature needs one.

**Payments.** Review current rules for your product and target storefronts. Apple's
requirements include regional exceptions and programs; this wrapper implements
neither IAP nor storefront-specific purchasing controls. Check the current
[Apple payment rules](https://developer.apple.com/app-store/review/guidelines/#payments)
and the corresponding Google Play policy before exposing Stripe checkout.

## Security notes

- `server.allowNavigation` lists only your app's host. Do not add wildcards. A
  wildcard lets a redirect or an injected link move the WebView to another site while
  the native bridge is still attached, handing native APIs to whatever loads next.
  `check` fails on any wildcard.
- The remote page has bridge access, so an XSS on your site becomes an XSS with
  native capability. Keep the plugin list minimal and the site's CSP strict.
- `webContentsDebuggingEnabled` is off. `--debuggable` turns it on for local
  diagnosis; `check` fails if it is left on.
- Certificate pinning is not configured. It is worth considering if you handle
  clinical or financial data, but it makes certificate rotation a release event.

### One thing to verify on a real device

Your deployed site sends `script-src 'self'` (see `release-template/frontend/server.mjs`).
Capacitor injects its bridge script into the page, and whether a strict `script-src`
interferes depends on the platform's injection mechanism. **This has not been tested
on a device here** — there is no way to run a WebView in the build environment.

Check it early: if `window.Capacitor` is undefined in the WebView while the site
works normally in a browser, that is the cause. The fix is to add the Capacitor
scheme to `script-src` in `server.mjs` for that deployment. Do not relax the CSP
pre-emptively.

## Build from the Mobile tab

The builder has **Build APK**, **Build AAB**, **Build IPA**, and artifact download buttons.
The standalone generator above remains available for manual workflows.

1. Deploy your web app and confirm its HTTPS origin works on your phone.
2. Open **Mobile** in the project. Enter the deployed origin, app name, reverse-DNS
   app ID, version and build number. This packages the deployed site, not unpublished
   local source changes.
3. Prepare the native tools. The panel displays missing prerequisites and has a
   refresh button. Android requires Node 22+, npm, JDK 21+, SDK platform 36 and
   Android build-tools. Set `ANDROID_HOME`; accept the SDK licenses. On Windows,
   these must be Linux tools in the same WSL distro as the builder; see `WINDOWS.md`.
   For AAB, enter the upload keystore path, alias and passwords. The JDK must include
   `jarsigner`. Supply an app icon for store builds to replace the placeholder.
4. For IPA, run Local Foundry on macOS with Xcode 26+ selected. Complete Xcode's
   initial setup, sign in to your developer account, and configure certificates,
   provisioning and the app ID. Enter the 10-character Team ID. Development and
   registered-device exports need eligible devices in the provisioning profile.
5. Enable the permission to download dependencies and run native build tools, then
   choose **Build APK**, **Build AAB** or **Build IPA**. Offline-only mode blocks new mobile builds.
6. Watch phases in Mobile or Activity. Cancel stops the compiler process group.
   A successful build exposes its APK, AAB or IPA download, size and
   SHA-256 checksum. Failures show the reason and a bounded, redacted build log.

APK output is a **debug-signed testing build**, not a Play Store release. A private
per-project debug keystore is retained so subsequent builds can update the app.
Keep it in your machine backup; source exports do not include signing keys.
IPA uses Xcode automatic signing and an explicit export method: development,
registered test devices, or App Store Connect. Export only saves an IPA; it never
uploads to a store. The exported IPA's provisioning determines where it can install.
There is no remote Mac service configured in this version; Windows shows the IPA
requirement and can still download an existing IPA belonging to the project.

The builder generates a new wrapper in a private build directory and calls fixed
native commands. It never copies agent-authored npm hooks, Gradle scripts, Xcode
projects or plugins into that directory. npm lifecycle scripts are disabled,
provider secrets are removed from child environments, and compilation has a
30-minute timeout. SDK/Gradle/Xcode are **host tools outside the preview sandbox**;
the per-build checkbox authorizes their dependency downloads and execution. Xcode
uses the local signing keychain and may update provisioning through its configured
account. Android upload-key passwords are entered in the UI for that build and are
excluded from saved build records and redacted from logs. The keystore stays on the
builder host; Apple signing uses the Mac's keychain.

Only verified successful outputs up to 512 MiB become downloadable. Downloads
require builder authentication, are scoped to the project/build ID and recheck the
artifact checksum. Completed history survives restarts; unfinished jobs are shown
as interrupted and must be started again. Normal completion/cancellation removes
the temporary native workspace. After a machine crash, a stopped build's `work/`
folder may remain under the private project `mobile-builds/` directory and can be
removed manually after confirming no compiler is running.

The automated suite exercises jobs, failure/cancellation, real subprocess shutdown,
command generation, authenticated downloads and modified/linked artifact rejection.
Actual APK/IPA compilation, signing and device behavior still require acceptance on
your target SDK/Xcode installation. The experimental remote-URL architecture and
store limitations described above continue to apply.
