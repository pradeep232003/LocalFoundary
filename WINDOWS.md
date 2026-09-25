# Local Foundry v0.10.1: Windows 11

Run the builder, agents, Python backend and PostgreSQL previews inside **WSL2
Ubuntu 24.04**, with **Docker Desktop** supplying Linux containers. The interface
opens in your normal Windows browser. This release includes a PowerShell launcher;
it is not a native Windows Python installation or an `.exe` installer.

Use the v0.10.1 archive: it includes the Accounts starter packaging fix introduced
in v0.7.1 after the first v0.7 download omitted those files. If that install failed while caching the Accounts image,
extract this release and rerun `Install`. Existing settings and data are preserved.

## 1. Prepare Windows and Ubuntu once, while connected

In an administrator PowerShell window, if WSL is not already installed:

```powershell
wsl --install -d Ubuntu-24.04
```

Restart Windows if requested. Open Ubuntu and create your Linux username/password.
Use `wsl --update` and `wsl --list --verbose` to confirm the distribution uses WSL
**version 2**. Install current [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/),
start it, enable the WSL2 engine, and enable **Settings → Resources → WSL
Integration → Ubuntu-24.04**. Use Linux containers. Do not install a second Docker
Engine inside Ubuntu; Desktop supplies the integration.

In the Ubuntu terminal:

```bash
sudo apt-get update
sudo apt-get install -y python3.12-venv git ca-certificates
python3 --version
docker info
docker compose version
```

Python must be 3.12. GitHub CLI and OCR are optional. Install/authenticate `gh`
**inside Ubuntu**, when you want GitHub saves. Ubuntu's `tesseract-ocr` and
`poppler-utils` packages enable scanned-document indexing.

Official prerequisites: [Microsoft WSL installation](https://learn.microsoft.com/en-us/windows/wsl/install)
and [Docker WSL integration](https://docs.docker.com/desktop/features/wsl/).

## 2. Install the builder

Extract `local-foundry.zip` on Windows. Open a normal PowerShell window in the
extracted `local-foundry` folder containing `Windows.ps1`:

```powershell
Unblock-File .\Windows.ps1
Set-ExecutionPolicy -Scope Process RemoteSigned
.\Windows.ps1 Install
.\Windows.ps1 Start
```

The policy change lasts only for this PowerShell window. If your organization
controls script execution, use its approved procedure. No administrator privileges
are needed for Local Foundry after installing WSL/Docker prerequisites.

Installation copies only program files into your Ubuntu home, creates a Linux
Python environment, builds React, and caches the five Docker images. It uses an
existing Linux Node.js 22+ with npm if available; otherwise it downloads official
**Node 24 LTS**, verifies its published SHA-256, and installs it privately. This is
an online setup step; it also downloads Python/npm packages and container layers.
It does not download or choose a language model.

`Start` starts the local database with `--pull never`, starts the builder in the
background, checks authenticated access from Windows, then opens the browser with
the private launch token. It does not invoke pip, npm, apt, or Docker image pulls.
Keep Docker Desktop running. Closing the browser or PowerShell does not stop it.

If your Ubuntu distribution has another name, use the same flag on every command:

```powershell
.\Windows.ps1 Start -Distribution Ubuntu
```

That distro still needs Python 3.12 and WSL2. Each distro has its own installation.

## 3. Set up fully disconnected AI

New Windows installations have `OFFLINE_ONLY=true`. Start a tool-capable,
OpenAI-compatible model server **inside the same Ubuntu distribution**, and
download/load its model while connected. For example, follow the official
[Ollama Linux setup](https://docs.ollama.com/linux) inside Ubuntu, then pull the
specific model you intend to use. GPU support depends on your hardware and drivers;
the launcher does not configure GPU drivers or promise a particular model speed.

Use the model ID your server actually lists. In PowerShell:

```powershell
.\Windows.ps1 Stop
# Replace YOUR_DOWNLOADED_MODEL_ID before running:
.\Windows.ps1 Configure -Model YOUR_DOWNLOADED_MODEL_ID
.\Windows.ps1 Start -Offline
.\Windows.ps1 OfflineCheck
```

`Configure` sets the local model, loopback endpoint and offline-only setting.
The default endpoint is `http://127.0.0.1:11434/v1`; use `-ApiBase` for another
literal loopback HTTP endpoint. It does not start/download the model for you.
`OfflineCheck` verifies the configured model is listed, cached images, PostgreSQL,
Linux-side storage, the running builder's mode, and Windows-to-WSL access. A
missing prerequisite returns a nonzero exit code. A listed model must still prove
that it supports the agent's tool calls in an actual build.

The usual WSL NAT network does not make a **Windows-hosted** model server available
at Ubuntu's `127.0.0.1`. Run the model in Ubuntu for the default supported path.
Windows 11 22H2+ mirrored networking can provide Windows/WSL loopback access, but
is an optional advanced configuration you must verify on your machine. The builder
continues to reject LAN model addresses. Do not expose your model or builder on
`0.0.0.0` to work around this. See [Microsoft WSL networking](https://learn.microsoft.com/en-us/windows/wsl/networking).

Before disconnecting, run a complete local-model edit, preview and validation.
Cache any additional approved project dependencies too. Then disable Wi-Fi/Ethernet,
restart the builder and local model, and repeat the edit/check workflow. Document
search, file plans and previews stay local. Claude/OpenAI APIs, GitHub, payments,
external integrations and public deployments require internet access. The
offline-only switch governs builder features; physical disconnection provides
the requested machine-wide network boundary.

## Commands and storage

| PowerShell command | Purpose |
| --- | --- |
| `.\Windows.ps1 Install` | Install/update program files while connected |
| `.\Windows.ps1 Start` | Start the builder and open the private browser session |
| `.\Windows.ps1 Start -Offline` | Enforce offline-only for this running session |
| `.\Windows.ps1 Stop` | Gracefully stop the builder; retain previews and databases |
| `.\Windows.ps1 Stop -Previews -Database` | Also stop previews and builder database; retain all volumes |
| `.\Windows.ps1 Doctor` | Show diagnostics and verify Windows localhost access |
| `.\Windows.ps1 OfflineCheck` | Fail unless offline preflight and Windows access pass |
| `.\Windows.ps1 Paths` | Show Explorer paths for settings, documents, files, logs and reports |
| `.\Windows.ps1 OpenFiles` | Open the managed file-automation folder in Explorer |
| `.\Windows.ps1 Test` | Run target-WSL builds, tests and real Docker acceptance |

Inside Ubuntu, everything lives under `~/.local/share/local-foundry/`:

- `current` points to the installed program release. Older releases are retained.
- `state/.env` holds private settings and tokens; `state/data` holds projects,
  documents, file plans and recovery archives. PostgreSQL data uses Docker volumes.
- `state/builder.log` contains server startup errors without printing the private
  launch URL. `state/acceptance-results` contains the latest target test report.
- `tools` holds a privately installed Node runtime if one was needed.

Use the `Paths` output to open folders through `\\wsl.localhost\Ubuntu-24.04\...`
in Explorer. Copy documents/files into the managed folders, then reindex or create
a file plan in the UI. Projects and database mounts must stay on the Linux
filesystem; installing from `C:\Downloads\...` is fine, running the workspace
directly from `/mnt/c` is rejected. Paths with spaces are passed as arguments.

For cloud APIs/GitHub, stop the builder, open the settings file shown by `Paths`,
set `OFFLINE_ONLY=false`, add the intended API key, then start while connected.
If Git needs an author, configure `git config --global user.name` and `user.email`
inside Ubuntu. Authenticate `gh` there too. Keep keys out of chat/source control.

## Upgrade or move from Mac

Create an encrypted Recovery export before upgrading. Run `Stop -Previews`, extract
the new ZIP to a separate Windows folder, and run its `Windows.ps1 Install`.
Only a completely installed release becomes `current`. Failed setup leaves the
old program selected. Settings, project files and Docker database volumes are
preserved. Do not manually copy `.venv`, `.env`, `.data`, or Docker volume files
from macOS or another computer. Install fresh on Windows, import the encrypted
project recovery archives in the UI, then rerun validation. Configure model/API
and GitHub credentials separately. Keep the original machine/export until verified.

Do not unregister the Ubuntu distro, delete Docker Desktop data, or reset Docker
volumes as an upgrade step. Program rollback alone does not undo database schema
changes; use a verified recovery export when moving to an older release.

## Target-laptop acceptance and troubleshooting

Run `Start`, `Doctor`, then `Test`. The Docker tests use uniquely named disposable
apps/volumes and do not contact models, publish apps or push to GitHub. The report
distinguishes failed and blocked gates; exit 2 means evidence is still incomplete.

For fixture UI screenshots, install **Linux** Chrome/Chromium inside WSL, or set
`CHROME_PATH` to its Linux executable when running `scripts/acceptance.py --mode
windows` from Ubuntu with the installed venv and state environment. Windows Chrome
opens the real app normally, but is not the Linux screenshot runner's executable.
The screenshot runner produces the 29 builder and 16 Accounts states using
deterministic fixtures; the Docker browser journeys exercise real application data.
No screenshots are included as proof of Windows execution in this package.

Manually verify on Windows: create a project, start its preview, save a note,
restart, confirm the note remains, make a real local-model edit, index a document,
apply/undo a file plan, export/import recovery, and repeat while disconnected.
For optional GitHub save, reconnect, enable online mode, authenticate `gh`, review
the diff and save. Never treat a unit-test pass as that full acceptance evidence.

- **Docker missing:** start Docker Desktop and enable this distro's WSL integration.
- **Builder opens but preview fails:** check the project's loopback URL from Windows,
  Docker container health, VPN rules and Windows localhost forwarding. Keep port
  bindings on `127.0.0.1`; the installer never changes firewall or `.wslconfig` rules.
- **Windows cannot reach the builder:** inspect `Doctor` and the log from `Paths`.
  Default WSL localhost forwarding must be enabled. Check WSL updates and your VPN.
- **Model unavailable:** check the exact ID and `/v1/models` endpoint inside Ubuntu;
  ensure the server is in the same distro and its weights are already downloaded.
- **Port occupied:** stop the other builder or edit `BUILDER_PORT` in the private
  settings file, then restart. No process is killed merely because it owns a port.
- **Stop is waiting:** let active work finish and retry. The launcher verifies
  process identity and never uses `wsl --shutdown`, `taskkill`, or volume deletion.

This version's Linux regression suite/builds were verified during packaging.
Windows PowerShell, WSL2, Docker Desktop and disconnected laptop acceptance still
need to run on the actual Windows machine; see `VALIDATION.md`.

## Android builds from the Mobile tab

Install a Linux JDK 21+ and the Linux Android SDK command-line tools **inside the
same Ubuntu distribution** as the builder. A Windows Android Studio SDK cannot be
used by Linux Gradle. Follow the official [Android command-line setup](https://developer.android.com/tools/sdkmanager),
accept the SDK licenses, and install platform 36, platform-tools and build-tools:

```bash
sdkmanager --licenses
sdkmanager "platforms;android-36" "platform-tools" "build-tools;36.0.0" "build-tools;35.0.0"
```

Set `ANDROID_HOME=/home/YOUR_USER/Android/Sdk` to the actual Linux SDK path in the
private settings file shown by `Windows.ps1 Paths`. Restart the builder after setup.
Mobile builds require `OFFLINE_ONLY=false` and the Mobile tab's download permission.
They produce a debug-signed APK for testing; the same project's signing key is kept
privately so later builds can update its installed app. Keep that private key with
your machine backup. The generated app's API and database remain on the deployed
server; this feature does not create an offline mobile backend.

IPA compilation is available when Local Foundry runs on a Mac with Xcode and signing
configured. The Windows UI displays that requirement; no remote Mac connection is
configured by this release. See `MOBILE.md` for signing and build/download steps.
