# Deployment operations · v0.7

This kit targets one Docker host and modest databases. It does not provision cloud
servers. Keep your deployment directory, private environment, operations state,
backup key, and recorded image IDs when installing a newer release.

## Stage and deploy

After the required validation and browser journeys pass in Local Foundry, export
the release. On the target host:

```sh
bash build-release.sh
python3 ops.py stage
```

Staging has its own database volume, password and encryption key. It binds only
127.0.0.1:8081, disables all integrations, and checks the real database migrations
and service health. Review the staged UI through a local connection or SSH tunnel.
The builder's authenticated browser journey evidence covers the exported source;
staging health does not certify live integrations.

Configure production using DEPLOY.md, including cached public/monitoring images.
Enable only the overlays you configured:

```sh
python3 ops.py deploy --overlays public,online,monitoring
python3 ops.py status
```

For a loopback-only deployment use `--overlays none`. Exact staged image IDs must
match, and staging must have passed within 24 hours. Deployment creates an
encrypted backup and successfully restores it to a disposable database before
running migrations. Health failures remain recorded as `failed_needs_review`.
An interruption leaves a durable `deploying` record. Neither automatically replays
deployment or restores old database contents. Review logs and the database first.
Use `ops.py` for subsequent deployments and rollbacks; direct Compose commands
bypass the lifecycle journal and its staging/backup gates.

`ops.py rollback` restores the recorded prior image IDs only when the current
database migration ledger is exactly the same as the prior release. This
conservative gate refuses rollback across added or changed migrations. Keep
recorded images; do not prune them. Image rollback preserves current data, and it
cannot prove application-level data compatibility. Review semantic data changes
before rollback. There is no automatic destructive production data restore.

## Encrypted scheduled backups and restore drills

```sh
python3 ops.py backup
python3 ops.py schedule
python3 ops.py restore-drill --backup BACKUP_FILENAME.lfb
```

Every backup uses a consistent PostgreSQL custom-format dump, AES-256-GCM, a random
nonce, and a private 32-byte key. Dumps stream directly into encryption. Decryption
authenticates the whole file in bounded container temporary storage before emitting
plaintext. A checksum supplements authenticated encryption; it does not replace it.
Each backup command also restores into a disposable PostgreSQL container with no
network access and records restoration time and the number of restored tables.
It does not overwrite the production database or certify business-level invariants.

The current envelope supports dumps up to 512 MiB. The restore drill's temporary
database has a 1 GiB limit. A larger restore fails visibly; use a separately tested
backup design for larger databases. All operations share a host lock. Operations
must run under the same deployment user. The key is at `.ops/backup.key`; copy it
to a separate secure location. Losing it makes the encrypted backups unrecoverable.
Encrypted files and JSON drill records live in `.ops/backups`.

`schedule` creates a daily 03:15 launchd job on macOS or a cron entry on Linux and
prints installation instructions. Install it on the actual deployment host; the
builder does not install a scheduler remotely. The host must be awake and Docker
running. Inspect the scheduler logs. Backups are retained until the operator
removes them; monitor disk space and copy encrypted backups off the deployment
host. Scheduled local backups do not survive loss of that host by themselves.

## Alerts when the whole application host is down

Run `ops/external_monitor.py` on a **different host** with a private configuration:

```json
{"name":"My app","health_url":"https://app.example.com/api/health","alert_webhook":"https://YOUR-ALERT-RECEIVER/PRIVATE-ENDPOINT"}
```

```sh
chmod 600 monitor.json
python3 ops/external_monitor.py --config /absolute/path/monitor.json
```

Schedule that command once per minute on the monitoring host. It checks HTTPS and
database health, sends a generic JSON webhook after three consecutive failures,
and sends recovery after success. The receiver must accept the documented JSON
payload; configure its email/push destination there. Failed delivery retries on
the next run. No receiver is configured or contacted by exporting this kit.
Test an outage and recovery before relying on it. Local Prometheus remains useful
for application metrics but cannot notify you after its own host disappears.

Reference behavior: [Docker Compose health waits](https://docs.docker.com/reference/cli/docker/compose/up/)
and [PostgreSQL transactional restore](https://www.postgresql.org/docs/17/app-pgrestore.html).
